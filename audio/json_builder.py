import logging
from datetime import datetime
from typing import Dict, List

logger = logging.getLogger(__name__)

def build_audio_json(transcript: Dict, acoustics: Dict, timing: Dict, 
                     fillers: Dict, derived: Dict, events: List[Dict], 
                     session_id: str) -> Dict:
    """
    Assembles final Audio JSON (5 blocks).
    Source: backend_SKILL.md Section 6 (audio/json_builder.py).
    
    Returns:
        Structured JSON dictionary.
    """
    # 1. Acoustic Metrics block (filtered from raw arrays)
    acoustic_metrics = {
        "pitch_variance_normalized": acoustics["pitch_variance_normalized"],
        "jitter_normalized": acoustics["jitter_normalized"],
        "energy_variation_normalized": acoustics["energy_variation_normalized"],
        "pause_ratio": acoustics["pause_ratio"],
        "speech_rate_wpm": timing["speech_rate_wpm"],
        "speech_rate_score": timing["speech_rate_score"],
        "speech_rate_instability_normalized": timing["speech_rate_instability_normalized"],
        "filler_ratio": fillers["filler_ratio"]
    }

    # 2. Assemble the blocks
    final_json = {
        "session_metadata": {
            "session_id": session_id,
            "processed_at": datetime.utcnow().isoformat() + "Z",
            "pipeline": "audio-speech-v1"
        },
        "transcript": {
            "full_text": transcript["full_text"],
            "segments": transcript["segments"],
            "total_words": transcript["total_words"]
        },
        "acoustic_metrics": acoustic_metrics,
        "filler_words_used": fillers["filler_words_used"],
        "derived_audio_attributes": derived,
        "timestamp_events": events
    }
    
    logger.info(f"Assembled final Audio JSON for session {session_id}")
    return final_json
