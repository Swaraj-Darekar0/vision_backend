import logging
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
        logger.info(f"[{session_id}] Using device-provided acoustic metrics.")
        transcription_path = audio_path
        acoustics = _normalize_device_acoustics(acoustic_metrics)
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
    required_keys = [
        "pitch_variance_normalized",
        "jitter_normalized",
        "energy_variation_normalized",
        "pause_ratio",
    ]
    missing = [key for key in required_keys if key not in acoustic_metrics]
    if missing:
        raise ValueError(f"audio_acoustic_json.acoustic_metrics missing required fields: {', '.join(missing)}")

    normalized = {
        "pitch_variance_normalized": float(acoustic_metrics.get("pitch_variance_normalized", 0.0)),
        "jitter_normalized": float(acoustic_metrics.get("jitter_normalized", 0.0)),
        "energy_variation_normalized": float(acoustic_metrics.get("energy_variation_normalized", 0.0)),
        "pause_ratio": float(acoustic_metrics.get("pause_ratio", 0.0)),
    }
    return normalized
