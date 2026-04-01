import logging
from datetime import datetime
from typing import Dict, Optional

import numpy as np

import config
from common.supabase_client import get_supabase_service_client

logger = logging.getLogger(__name__)


def fetch_baseline(user_id: str) -> Optional[Dict]:
    """
    Returns previous session scores as dict from Supabase.
    Uses rolling average of last ROLLING_BASELINE_SESSIONS sessions.
    Returns None if no history exists (first session).
    """
    db = get_supabase_service_client()
    if db is None:
        logger.error("Supabase client is not initialized.")
        return None

    try:
        res = (
            db.table("session_scores")
            .select("*")
            .eq("user_id", user_id)
            .order("session_date", desc=True)
            .limit(config.ROLLING_BASELINE_SESSIONS)
            .execute()
        )

        rows = res.data
        if not rows:
            logger.info(f"No history found for user {user_id}. Treating as baseline session.")
            return None

        metrics_to_avg = [
            ("confidence", "confidence"),
            ("clarity", "clarity"),
            ("engagement", "engagement"),
            ("nervousness", "nervousness"),
            ("overall", "overall"),
            ("filler_ratio", "filler_ratio"),
            ("pause_ratio", "pause_ratio"),
            ("posture_stability_index", "posture_stability_index"),
        ]

        baseline = {}
        for output_key, column_name in metrics_to_avg:
            values = [row[column_name] for row in rows if column_name in row and row[column_name] is not None]
            baseline[output_key] = float(np.mean(values)) if values else 0.0

        reasoning_values = [_extract_reasoning_clarity(row) for row in rows]
        reasoning_values = [value for value in reasoning_values if value is not None]
        baseline["reasoning_clarity"] = float(np.mean(reasoning_values)) if reasoning_values else 0.0

        logger.info(f"Baseline fetched and averaged over {len(rows)} sessions for {user_id}.")
        return baseline
    except Exception as exc:
        logger.error(f"Supabase fetch_baseline failed for {user_id}: {exc}")
        return None


def write_session(
    user_id: str,
    scores: Dict,
    pose_data: Dict,
    audio_data: Dict,
    metadata: Optional[Dict] = None,
) -> bool:
    """
    Writes current session scores and metadata to Supabase.
    """
    db = get_supabase_service_client()
    if db is None:
        logger.error("Supabase client is not initialized.")
        return False

    metadata = metadata or {}

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
        "is_first_session": metadata.get("is_first_session", False),
        "week_number": metadata.get("week_number"),
        "plan_day": metadata.get("plan_day"),
        "plan_session_num": metadata.get("plan_session_num"),
        "is_recovery": metadata.get("is_recovery", False),
        "target_skill": metadata.get("target_skill"),
    }

    try:
        res = db.table("session_scores").insert(row_dict).execute()
        return len(res.data) > 0
    except Exception as exc:
        logger.error(f"Supabase write_session failed: {exc}")
        return False


def update_session_result(session_id: str, final_result: Dict) -> bool:
    """
    Updates the session record with the full raw_result JSON (including LLM feedback).
    """
    db = get_supabase_service_client()
    if db is None:
        return False

    try:
        res = (
            db.table("session_scores")
            .update({"raw_result": final_result})
            .eq("session_id", session_id)
            .execute()
        )
        return len(res.data) > 0
    except Exception as exc:
        logger.error(f"Supabase update_session_result failed: {exc}")
        return False


def update_personal_bests(user_id: str, scores: dict, raw_metrics: dict) -> None:
    """
    Upserts personal best metrics.
    Higher is better for all metrics except filler_ratio.
    """
    db = get_supabase_service_client()
    if db is None:
        logger.error("Supabase client is not initialized.")
        return

    new_values = {
        "user_id": user_id,
        "overall": float(scores.get("overall", 0.0)),
        "confidence": float(scores.get("confidence", 0.0)),
        "clarity": float(scores.get("clarity", 0.0)),
        "engagement": float(scores.get("engagement", 0.0)),
        "nervousness": float(scores.get("nervousness", 0.0)),
        "posture_stability": float(raw_metrics.get("posture_stability", 0.0)),
        "gesture_score": float(raw_metrics.get("gesture_score", 0.0)),
        "speech_rate_score": float(raw_metrics.get("speech_rate_score", 0.0)),
        "filler_ratio": float(raw_metrics.get("filler_ratio", 1.0)),
        "updated_at": datetime.utcnow().isoformat(),
    }

    try:
        existing_res = (
            db.table("personal_bests")
            .select("*")
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        existing = existing_res.data[0] if existing_res.data else None

        merged = dict(new_values)
        if existing:
            for field in [
                "overall",
                "confidence",
                "clarity",
                "engagement",
                "nervousness",
                "posture_stability",
                "gesture_score",
                "speech_rate_score",
            ]:
                merged[field] = max(float(existing.get(field, 0.0)), new_values[field])

            merged["filler_ratio"] = min(float(existing.get("filler_ratio", 1.0)), new_values["filler_ratio"])

        db.table("personal_bests").upsert(merged).execute()
    except Exception as exc:
        logger.error(f"Supabase update_personal_bests failed for {user_id}: {exc}")


def update_user_profile_flags(user_id: str, metadata: Optional[Dict] = None) -> None:
    """
    Best-effort update for diagnostic-related profile flags.
    """
    db = get_supabase_service_client()
    if db is None:
        logger.error("Supabase client is not initialized.")
        return

    metadata = metadata or {}
    update_dict = {}

    if metadata.get("is_diagnostic"):
        update_dict["diagnostic_complete"] = True

    speaker_level = metadata.get("speaker_level")
    if speaker_level in config.SPEAKER_LEVEL_VALUES:
        update_dict["speaker_level"] = speaker_level

    if "diagnostic_complete" in metadata:
        update_dict["diagnostic_complete"] = bool(metadata["diagnostic_complete"])

    if not update_dict:
        return

    try:
        db.table("user_profiles").update(update_dict).eq("id", user_id).execute()
    except Exception as exc:
        logger.error(f"Supabase update_user_profile_flags failed for {user_id}: {exc}")


def _extract_reasoning_clarity(row: Dict) -> Optional[float]:
    raw_result = row.get("raw_result")
    if not isinstance(raw_result, dict):
        return None

    llm_feedback = raw_result.get("llm_feedback")
    if not isinstance(llm_feedback, dict):
        return None

    try:
        return float(llm_feedback.get("reasoning_clarity_score"))
    except (TypeError, ValueError):
        return None
