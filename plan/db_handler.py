import logging
from datetime import datetime, timezone
from typing import Optional

from common.supabase_client import get_supabase_service_client

logger = logging.getLogger(__name__)


def deactivate_current_plans(user_id: str) -> None:
    db = get_supabase_service_client()
    if db is None:
        logger.error("Supabase client unavailable while deactivating plans")
        return
    logger.info(f"Deactivating current weekly plans for user {user_id}")
    db.table("weekly_plans").update({"is_current": False}).eq("user_id", user_id).eq("is_current", True).execute()


def create_weekly_plan(user_id: str, payload: dict) -> Optional[dict]:
    db = get_supabase_service_client()
    if db is None:
        logger.error("Supabase client unavailable while creating plan")
        return None

    row = {
        "user_id": user_id,
        "week_number": payload["week_number"],
        "week_start_date": payload["week_start_date"],
        "speaker_level": payload["speaker_level"],
        "sessions_per_day": payload["sessions_per_day"],
        "plan_data": payload["plan_data"],
        "is_current": True,
    }
    logger.info(f"Upserting weekly plan for user {user_id}, week {payload['week_number']}")
    result = db.table("weekly_plans").upsert(row, on_conflict="user_id,week_number").execute()
    if not result.data:
        logger.error(f"Weekly plan upsert failed for user {user_id}, week {payload['week_number']}")
        return None
    logger.info(f"Weekly plan upsert succeeded for user {user_id}, week {payload['week_number']}")
    return result.data[0]


def fetch_current_plan(user_id: str, week_number: int | None = None) -> Optional[dict]:
    db = get_supabase_service_client()
    if db is None:
        logger.error("Supabase client unavailable while fetching plan")
        return None

    query = db.table("weekly_plans").select("*").eq("user_id", user_id)
    if week_number is None:
        query = query.eq("is_current", True)
    else:
        query = query.eq("week_number", week_number)

    result = query.order("generated_at", desc=True).limit(1).execute()
    return result.data[0] if result.data else None


def update_weekly_plan(plan_id: str, plan_data: dict) -> bool:
    db = get_supabase_service_client()
    if db is None:
        logger.error("Supabase client unavailable while updating plan")
        return False

    result = db.table("weekly_plans").update({"plan_data": plan_data}).eq("id", plan_id).execute()
    if not result.data:
        logger.error(f"Weekly plan update failed for plan_id={plan_id}")
    return bool(result.data)


def fetch_sessions_for_week(user_id: str, week_number: int) -> list[dict]:
    db = get_supabase_service_client()
    if db is None:
        return []
    result = (
        db.table("session_scores")
        .select("*")
        .eq("user_id", user_id)
        .eq("week_number", week_number)
        .execute()
    )
    return result.data or []


def upsert_weekly_review(user_id: str, week_number: int, week_start_date: str, review_data: dict) -> Optional[dict]:
    db = get_supabase_service_client()
    if db is None:
        return None

    row = {
        "user_id": user_id,
        "week_number": week_number,
        "week_start_date": week_start_date,
        "completion_rate": review_data["completion_rate"],
        "avg_overall_score": review_data["avg_overall_score"],
        "avg_confidence": review_data["avg_confidence"],
        "avg_clarity": review_data["avg_clarity"],
        "avg_engagement": review_data["avg_engagement"],
        "avg_nervousness": review_data["avg_nervousness"],
        "weakest_metric": review_data["weakest_metric"],
        "strongest_metric": review_data["strongest_metric"],
        "missed_days": review_data["missed_days"],
        "review_narrative": review_data["review_narrative"],
        "shown_to_user": review_data.get("shown_to_user", False),
    }
    result = db.table("weekly_reviews").upsert(row, on_conflict="user_id,week_number").execute()
    return result.data[0] if result.data else None


def mark_review_shown(user_id: str, week_number: int) -> bool:
    db = get_supabase_service_client()
    if db is None:
        return False
    result = (
        db.table("weekly_reviews")
        .update({"shown_to_user": True})
        .eq("user_id", user_id)
        .eq("week_number", week_number)
        .execute()
    )
    return bool(result.data)


def fetch_personal_bests(user_id: str) -> Optional[dict]:
    db = get_supabase_service_client()
    if db is None:
        return None
    result = db.table("personal_bests").select("*").eq("user_id", user_id).limit(1).execute()
    return result.data[0] if result.data else None


def current_timestamp_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
