import logging
from datetime import datetime
from typing import Dict, Optional

import numpy as np

import config
from common.supabase_client import get_supabase_service_client

logger = logging.getLogger(__name__)

CADENCE_SESSION_COLUMNS = [
    "speech_rate_wpm",
    "wpm_sigma_raw",
    "pause_count_per_minute",
    "mean_pause_duration_seconds",
    "inter_word_gap_sigma",
    "f0_contour_mean_slope",
    "voiced_filler_proxy_ratio",
    "stutter_ratio",
    "disfluency_burden",
]


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
        "speech_rate_wpm": a_metrics.get("speech_rate_wpm", 0.0),
        "wpm_sigma_raw": a_metrics.get("wpm_sigma_raw", 0.0),
        "pause_count_per_minute": audio_data.get("cadence_metrics", {}).get("pause_count_per_minute", 0.0),
        "mean_pause_duration_seconds": audio_data.get("cadence_metrics", {}).get("mean_pause_duration_seconds", 0.0),
        "inter_word_gap_sigma": audio_data.get("cadence_metrics", {}).get("inter_word_gap_sigma", 0.0),
        "f0_contour_mean_slope": audio_data.get("cadence_metrics", {}).get("f0_contour_mean_slope", 0.0),
        "voiced_filler_proxy_ratio": audio_data.get("cadence_metrics", {}).get("voiced_filler_proxy_ratio", 0.0),
        "stutter_ratio": audio_data.get("cadence_metrics", {}).get("stutter_ratio", 0.0),
        "disfluency_burden": audio_data.get("cadence_metrics", {}).get("disfluency_burden", 0.0),
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
        logger.error(f"Supabase write_session failed with cadence fields: {exc}")
        try:
            fallback_dict = dict(row_dict)
            for key in CADENCE_SESSION_COLUMNS:
                fallback_dict.pop(key, None)
            res = db.table("session_scores").insert(fallback_dict).execute()
            return len(res.data) > 0
        except Exception as fallback_exc:
            logger.error(f"Supabase write_session fallback failed: {fallback_exc}")
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


def read_cadence_profile(user_id: str) -> Optional[Dict]:
    db = get_supabase_service_client()
    if db is None:
        return None

    try:
        res = (
            db.table("user_profiles")
            .select(
                "cadence_profile,cadence_label,cadence_subtype,profile_locked_at,"
                "next_cadence_review_at,cadence_natural_wpm_baseline,cadence_wpm_sigma_raw,"
                "cadence_pause_count_per_minute,cadence_mean_pause_duration_seconds,"
                "cadence_inter_word_gap_sigma,cadence_f0_contour_mean_slope"
            )
            .eq("id", user_id)
            .limit(1)
            .execute()
        )
        row = res.data[0] if res.data else None
        if not row or not row.get("cadence_profile"):
            return None
        profile = row.get("cadence_profile")
        return {
            "profile": profile,
            "label": row.get("cadence_label") or config.CADENCE_DISPLAY_LABELS.get(profile, "Expressive"),
            "subtype": row.get("cadence_subtype"),
            "profile_locked_at": row.get("profile_locked_at"),
            "next_review_at": row.get("next_cadence_review_at"),
            "natural_wpm_baseline": row.get("cadence_natural_wpm_baseline", 0.0),
            "wpm_sigma_raw": row.get("cadence_wpm_sigma_raw", 0.0),
            "pause_count_per_minute": row.get("cadence_pause_count_per_minute", 0.0),
            "mean_pause_duration_seconds": row.get("cadence_mean_pause_duration_seconds", 0.0),
            "inter_word_gap_sigma": row.get("cadence_inter_word_gap_sigma", 0.0),
            "f0_contour_mean_slope": row.get("cadence_f0_contour_mean_slope", 0.0),
            "is_locked": True,
            "is_provisional": False,
        }
    except Exception as exc:
        logger.error(f"Supabase read_cadence_profile failed for {user_id}: {exc}")
        return None


def write_cadence_profile(user_id: str, cadence_profile: Dict) -> None:
    db = get_supabase_service_client()
    if db is None or not cadence_profile:
        return

    update_dict = {
        "cadence_profile": cadence_profile.get("profile"),
        "cadence_label": cadence_profile.get("label"),
        "cadence_subtype": cadence_profile.get("subtype"),
        "profile_locked_at": cadence_profile.get("profile_locked_at"),
        "next_cadence_review_at": cadence_profile.get("next_review_at"),
        "cadence_natural_wpm_baseline": cadence_profile.get("natural_wpm_baseline", 0.0),
        "cadence_wpm_sigma_raw": cadence_profile.get("wpm_sigma_raw", 0.0),
        "cadence_pause_count_per_minute": cadence_profile.get("pause_count_per_minute", 0.0),
        "cadence_mean_pause_duration_seconds": cadence_profile.get("mean_pause_duration_seconds", 0.0),
        "cadence_inter_word_gap_sigma": cadence_profile.get("inter_word_gap_sigma", 0.0),
        "cadence_f0_contour_mean_slope": cadence_profile.get("f0_contour_mean_slope", 0.0),
    }

    try:
        db.table("user_profiles").update(update_dict).eq("id", user_id).execute()
    except Exception as exc:
        logger.error(f"Supabase write_cadence_profile failed for {user_id}: {exc}")


def fetch_recent_cadence_sessions(user_id: str, limit: int) -> list[Dict]:
    db = get_supabase_service_client()
    if db is None:
        return []

    try:
        res = (
            db.table("session_scores")
            .select(",".join(CADENCE_SESSION_COLUMNS))
            .eq("user_id", user_id)
            .order("session_date", desc=True)
            .limit(limit)
            .execute()
        )
        return list(res.data or [])
    except Exception as exc:
        logger.error(f"Supabase fetch_recent_cadence_sessions failed for {user_id}: {exc}")
        return []


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
