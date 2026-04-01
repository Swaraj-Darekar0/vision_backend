import math
from datetime import datetime, timedelta, timezone
from typing import Optional

import config
from common.supabase_client import get_supabase_service_client


def update_profile(user_id: str, profile_data: dict) -> Optional[dict]:
    db = get_supabase_service_client()
    if db is None:
        return None

    update_payload = {
        "identity": profile_data.get("identity"),
        "work_domain": profile_data.get("work_domain"),
        "interest_areas": profile_data.get("interest_areas", []),
        "speaking_goal": profile_data.get("speaking_goal"),
        "practice_frequency": profile_data.get("practice_frequency"),
        "onboarding_complete": True,
    }

    if profile_data.get("speaker_level") in config.SPEAKER_LEVEL_VALUES:
        update_payload["speaker_level"] = profile_data["speaker_level"]
    if "diagnostic_complete" in profile_data:
        update_payload["diagnostic_complete"] = bool(profile_data["diagnostic_complete"])

    result = (
        db.table("user_profiles")
        .update(update_payload)
        .eq("id", user_id)
        .execute()
    )
    return result.data[0] if result.data else None


def activate_subscription(user_id: str, plan: str) -> Optional[dict]:
    db = get_supabase_service_client()
    if db is None:
        return None

    now = datetime.now(timezone.utc)
    duration_days = (
        config.SUBSCRIPTION_WEEKLY_DAYS
        if plan == "weekly"
        else config.SUBSCRIPTION_MONTHLY_DAYS
    )
    subscription_end = now + timedelta(days=duration_days)

    update_payload = {
        "subscription_status": "active",
        "subscription_plan": plan,
        "subscription_start": now.isoformat(),
        "subscription_end": subscription_end.isoformat(),
    }

    result = (
        db.table("user_profiles")
        .update(update_payload)
        .eq("id", user_id)
        .execute()
    )

    if not result.data:
        return None

    return {
        "success": True,
        "status": "active",
        "plan": plan,
        "subscription_end": subscription_end.isoformat(),
    }


def get_subscription_status(user_id: str) -> Optional[dict]:
    db = get_supabase_service_client()
    if db is None:
        return None

    result = (
        db.table("user_profiles")
        .select("subscription_status, subscription_plan, subscription_end")
        .eq("id", user_id)
        .limit(1)
        .execute()
    )
    if not result.data:
        return None

    row = result.data[0]
    status = row.get("subscription_status") or "free"
    plan = row.get("subscription_plan")
    subscription_end = row.get("subscription_end")
    now = datetime.now(timezone.utc)

    if status == "active" and subscription_end:
        end_dt = datetime.fromisoformat(subscription_end.replace("Z", "+00:00"))
        if end_dt < now:
            status = "expired"
            (
                db.table("user_profiles")
                .update({"subscription_status": "expired"})
                .eq("id", user_id)
                .execute()
            )
        days_remaining = max(0, math.ceil((end_dt - now).total_seconds() / 86400))
    else:
        days_remaining = 0

    return {
        "status": status,
        "plan": plan,
        "subscription_end": subscription_end,
        "days_remaining": days_remaining,
    }
