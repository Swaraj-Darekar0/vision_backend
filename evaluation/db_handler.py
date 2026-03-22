import logging
from datetime import datetime
from typing import Dict, Optional, List
from supabase import create_client, Client
import config
import numpy as np

logger = logging.getLogger(__name__)

# Initialize Supabase client once at module level
_db: Optional[Client] = None
if config.SUPABASE_URL and config.SUPABASE_KEY:
    try:
        _db = create_client(config.SUPABASE_URL, config.SUPABASE_KEY)
        logger.info("Supabase client initialized successfully.")
    except Exception as e:
        logger.error(f"Failed to initialize Supabase client: {e}")
else:
    logger.warning("Supabase credentials missing in config.")

def fetch_baseline(user_id: str) -> Optional[Dict]:
    """
    Returns previous session scores as dict from Supabase.
    Uses rolling average of last ROLLING_BASELINE_SESSIONS sessions.
    Returns None if no history exists (first session).
    Source: backend_SKILL.md Section 6 (evaluation/db_handler.py).
    """
    if _db is None:
        logger.error("Supabase client is not initialized.")
        return None

    try:
        # Fetch last N sessions for this user
        res = _db.table("session_scores") \
                 .select("*") \
                 .eq("user_id", user_id) \
                 .order("session_date", desc=True) \
                 .limit(config.ROLLING_BASELINE_SESSIONS) \
                 .execute()
        
        rows = res.data
        if not rows:
            logger.info(f"No history found for user {user_id}. Treating as baseline session.")
            return None

        # Compute averages across fetched sessions
        metrics_to_avg = [
            "confidence", "clarity", "engagement", "nervousness", "overall",
            "filler_ratio", "pause_ratio", "posture_stability_index"
        ]
        
        baseline = {}
        for metric in metrics_to_avg:
            values = [row[metric] for row in rows if metric in row and row[metric] is not None]
            if values:
                baseline[metric] = float(np.mean(values))
            else:
                baseline[metric] = 0.0
                
        logger.info(f"Baseline fetched and averaged over {len(rows)} sessions for {user_id}.")
        return baseline

    except Exception as e:
        logger.error(f"Supabase fetch_baseline failed for {user_id}: {e}")
        return None

def write_session(user_id: str, scores: Dict,
                  pose_data: Dict, audio_data: Dict, metadata: Optional[Dict] = None) -> bool:
    """
    Writes current session scores and metadata to Supabase.
    """
    if _db is None:
        logger.error("Supabase client is not initialized.")
        return False

    if metadata is None:
        metadata = {}

    session_id = pose_data.get("session_metadata", {}).get("session_id", "unknown")
    p_metrics = pose_data.get("posture_metrics", {})
    a_metrics = audio_data.get("acoustic_metrics", {})
    p_derived = pose_data.get("derived_pose_attributes", {})
    
    row_dict = {
        "session_id": session_id,
        "user_id": user_id,
        "session_date": datetime.utcnow().isoformat(),
        "confidence": scores["confidence"],
        "clarity": scores["clarity"],
        "engagement": scores["engagement"],
        "nervousness": scores["nervousness"],
        "overall": scores["overall"],
        "filler_ratio": a_metrics.get("filler_ratio", 0.0),
        "pitch_variance_normalized": a_metrics.get("pitch_variance_normalized", 0.0),
        "posture_stability_index": p_derived.get("posture_stability_index", 0.0),
        "pause_ratio": a_metrics.get("pause_ratio", 0.0),
        "gesture_score": p_metrics.get("gesture_score", 0.0),
        "topic_title": metadata.get("topic_title", "Untitled Session"),
        "duration_label": metadata.get("duration_label", "--"),
        "is_first_session": metadata.get("is_first_session", False)
    }
    
    try:
        res = _db.table("session_scores").insert(row_dict).execute()
        return len(res.data) > 0
    except Exception as e:
        logger.error(f"Supabase write_session failed: {e}")
        return False

def update_session_result(session_id: str, final_result: Dict) -> bool:
    """
    Updates the session record with the full raw_result JSON (including LLM feedback).
    """
    if _db is None:
        return False

    try:
        res = _db.table("session_scores") \
                 .update({"raw_result": final_result}) \
                 .eq("session_id", session_id) \
                 .execute()
        return len(res.data) > 0
    except Exception as e:
        logger.error(f"Supabase update_session_result failed: {e}")
        return False
