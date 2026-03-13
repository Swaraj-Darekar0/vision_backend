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

def run_audio_pipeline(audio_path: str, session_id: str) -> dict:
    """
    Orchestrator for the entire Audio (Speech) Pipeline.
    Calls stages in order. No math or threshold comparisons here.
    Source: backend_SKILL.md Section 6 (audio/pipeline.py).
    
    Args:
        audio_path: Path to input file (MP4 or WAV).
        session_id: Unique session identifier.
        
    Returns:
        Final Audio JSON response dictionary.
    """
    logger.info(f"[{session_id}] Starting Audio Pipeline for: {audio_path}")
    
    # 1. Preprocessing (Format standardization)
    clean_path = preprocess_audio(audio_path)
    
    # 2. Transcription (AssemblyAI)
    transcript = transcribe(clean_path)
    
    # 3. Filler Word Detection
    fillers = detect_fillers(transcript)
    
    # 4. Acoustic Feature Extraction (Librosa)
    acoustics = extract_acoustic_features(clean_path)
    
    # 5. Timing Metrics (WPM, instability)
    timing = compute_timing_metrics(transcript)
    
    # 6. Window Aggregation (5s chunks + FumbleScore)
    windows = aggregate_windows(acoustics, timing, fillers, transcript)
    
    # 7. Event Detection (6 event types)
    events = detect_events(windows)
    
    # 8. Derived Behavioral Attributes
    derived = compute_derived_attributes(acoustics, timing, fillers)
    
    # 9. JSON Assembly
    result = build_audio_json(transcript, acoustics, timing, fillers, derived, events, session_id)
    
    logger.info(f"[{session_id}] Audio Pipeline completed successfully")
    return result
