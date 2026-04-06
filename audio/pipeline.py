import logging
import math
from audio.preprocessor import preprocess_audio
from audio.transcriber import transcribe
from audio.filler_detector import detect_fillers
from audio.acoustic_extractor import extract_acoustic_features
from audio.timing_metrics import compute_timing_metrics
from audio.window_aggregator import aggregate_windows
from audio.event_detector import detect_events
from audio.derived_attributes import compute_derived_attributes
from audio.json_builder import build_audio_json

logger = logging.getLogger(__name__)

REQUIRED_ACOUSTIC_KEYS = (
    "pitch_variance_normalized",
    "jitter_normalized",
    "energy_variation_normalized",
    "pause_ratio",
)

def run_audio_pipeline(
    audio_path: str,
    session_id: str,
    topic_title: str = "Untitled Session",
    acoustic_payload: dict | None = None,
) -> dict:
    """
    Orchestrator for the entire Audio (Speech) Pipeline.
    Calls stages in order. No math or threshold comparisons here.
    Source: backend_SKILL.md Section 6 (audio/pipeline.py).
    
    Args:
        audio_path: Path to input file (M4A, MP4, WAV, etc.).
        session_id: Unique session identifier.
        topic_title: Optional topic title for content analysis.
        
    Returns:
        Final Audio JSON response dictionary.
    """
    logger.info(f"[{session_id}] Starting Audio Pipeline for: {audio_path}")

    acoustic_payload = acoustic_payload or {}
    acoustic_metrics = acoustic_payload.get("acoustic_metrics")
    acoustic_windows = acoustic_payload.get("acoustic_windows", [])

    if acoustic_metrics:
        try:
            acoustics = _normalize_device_acoustics(acoustic_metrics)
            logger.info(f"[{session_id}] Using device-provided acoustic metrics.")
            transcription_path = audio_path
        except ValueError as exc:
            logger.warning(
                "[%s] Invalid device acoustic payload; falling back to legacy backend audio compute: %s",
                session_id,
                exc,
            )
            processed_paths = preprocess_audio(audio_path)
            analysis_path = processed_paths["analysis_path"]
            transcription_path = processed_paths["transcription_path"]
            acoustics = extract_acoustic_features(analysis_path)
            acoustic_windows = []
        else:
            try:
                acoustic_windows = _normalize_acoustic_windows(acoustic_windows)
            except ValueError as exc:
                logger.warning(
                    "[%s] Ignoring malformed acoustic_windows and using session-level acoustics only: %s",
                    session_id,
                    exc,
                )
                acoustic_windows = []
    else:
        # Legacy fallback path for older clients.
        processed_paths = preprocess_audio(audio_path)
        analysis_path = processed_paths["analysis_path"]
        transcription_path = processed_paths["transcription_path"]
        acoustics = extract_acoustic_features(analysis_path)
    
    # 2. Transcription (AssemblyAI)
    transcript = transcribe(transcription_path)
    
    # 3. Filler Word Detection
    fillers = detect_fillers(transcript)
    
    # 4. Timing Metrics (WPM, instability)
    timing = compute_timing_metrics(transcript)
    
    # 5. Window Aggregation (5s chunks + FumbleScore)
    windows = aggregate_windows(acoustics, timing, fillers, transcript, acoustic_windows=acoustic_windows)
    
    # 6. Event Detection (6 event types)
    events = detect_events(windows)
    
    # 7. Derived Behavioral Attributes
    derived = compute_derived_attributes(acoustics, timing, fillers)
    
    # 8. JSON Assembly
    result = build_audio_json(transcript, acoustics, timing, fillers, derived, events, session_id)
    
    logger.info(f"[{session_id}] Audio Pipeline completed successfully")
    return result


def _normalize_device_acoustics(acoustic_metrics: dict) -> dict:
    if not isinstance(acoustic_metrics, dict):
        raise ValueError("audio_acoustic_json.acoustic_metrics must be a JSON object")

    missing = [key for key in REQUIRED_ACOUSTIC_KEYS if key not in acoustic_metrics]
    if missing:
        raise ValueError(f"audio_acoustic_json.acoustic_metrics missing required fields: {', '.join(missing)}")

    normalized = {
        key: _coerce_unit_float(
            acoustic_metrics.get(key),
            field_name=f"audio_acoustic_json.acoustic_metrics.{key}",
        )
        for key in REQUIRED_ACOUSTIC_KEYS
    }
    return normalized


def _normalize_acoustic_windows(acoustic_windows) -> list[dict]:
    if acoustic_windows in (None, []):
        return []
    if not isinstance(acoustic_windows, list):
        raise ValueError("audio_acoustic_json.acoustic_windows must be a list when provided")

    normalized_by_index: dict[int, dict] = {}

    for idx, window in enumerate(acoustic_windows):
        if not isinstance(window, dict):
            raise ValueError(f"audio_acoustic_json.acoustic_windows[{idx}] must be an object")

        raw_index = window.get("window_index")
        if not isinstance(raw_index, int) or raw_index < 0:
            raise ValueError(f"audio_acoustic_json.acoustic_windows[{idx}].window_index must be an integer >= 0")

        time_start = _coerce_non_negative_float(
            window.get("time_start"),
            field_name=f"audio_acoustic_json.acoustic_windows[{idx}].time_start",
        )
        time_end = _coerce_non_negative_float(
            window.get("time_end"),
            field_name=f"audio_acoustic_json.acoustic_windows[{idx}].time_end",
        )
        if time_end <= time_start:
            raise ValueError(
                f"audio_acoustic_json.acoustic_windows[{idx}] must satisfy time_end > time_start"
            )

        normalized_by_index[raw_index] = {
            "window_index": raw_index,
            "time_start": time_start,
            "time_end": time_end,
            "pitch_variance_normalized": _coerce_unit_float(
                window.get("pitch_variance_normalized"),
                field_name=f"audio_acoustic_json.acoustic_windows[{idx}].pitch_variance_normalized",
            ),
            "pause_ratio": _coerce_unit_float(
                window.get("pause_ratio"),
                field_name=f"audio_acoustic_json.acoustic_windows[{idx}].pause_ratio",
            ),
        }

    return [normalized_by_index[index] for index in sorted(normalized_by_index)]


def _coerce_unit_float(value, *, field_name: str) -> float:
    number = _coerce_float(value, field_name=field_name)
    return min(max(number, 0.0), 1.0)


def _coerce_non_negative_float(value, *, field_name: str) -> float:
    number = _coerce_float(value, field_name=field_name)
    if number < 0.0:
        raise ValueError(f"{field_name} must be >= 0")
    return number


def _coerce_float(value, *, field_name: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field_name} must be numeric") from None

    if not math.isfinite(number):
        raise ValueError(f"{field_name} must be finite")

    return number
