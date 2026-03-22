import logging
from datetime import datetime
from typing import Dict, List, Optional
import config

logger = logging.getLogger(__name__)

def build_evaluation_json(scores: Dict, progress: Dict, 
                          audio_data: Dict, pose_data: Dict, 
                          user_id: str, metadata: Dict) -> Dict:
    """
    Assembles 5 blocks of the Final Evaluation JSON.
    Source: backend_SKILL.md Section 6 (evaluation/json_builder.py).
    
    Returns:
        Structured JSON dictionary.
    """
    session_id = pose_data.get("session_metadata", {}).get("session_id", "unknown")
    
    # 1. overall_scores
    overall_scores = scores
    
    # 2. progress_comparison (from delta_engine)
    progress_comparison = progress
    
    # 3. transcript (passed through from audio JSON)
    transcript = audio_data.get("transcript", {})
    
    # 4. timestamp_events (passed through from audio JSON)
    timestamp_events = audio_data.get("timestamp_events", [])
    
    # 5. filler_words_used (passed through from audio JSON)
    filler_words_used = audio_data.get("filler_words_used", {})
    
    # 6. raw_metrics_snapshot (drill-down data)
    raw_metrics_snapshot = {
        "pose": pose_data.get("posture_metrics", {}),
        "audio": audio_data.get("acoustic_metrics", {})
    }
    
    # 7. session_metadata
    session_metadata = {
        "session_id": session_id,
        "user_id": user_id,
        "processed_at": datetime.utcnow().isoformat() + "Z",
        "is_first_session": metadata.get("is_first_session", False),
        "topic_title": metadata.get("topic_title", "Untitled Session"),
        "duration_label": metadata.get("duration_label", "--")
    }
    
    final_json = {
        "session_metadata": session_metadata,
        "overall_scores": overall_scores,
        "progress_comparison": progress_comparison,
        "transcript": transcript,
        "timestamp_events": timestamp_events,
        "filler_words_used": filler_words_used,
        "raw_metrics_snapshot": raw_metrics_snapshot
    }
    
    logger.info(f"Final evaluation JSON built for session {session_id}")
    return final_json
