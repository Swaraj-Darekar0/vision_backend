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


def create_pending_razorpay_subscription(user_id: str, plan: str, subscription: dict) -> Optional[dict]:
    db = get_supabase_service_client()
    if db is None:
        return None

    row = {
        "user_id": user_id,
        "app_plan": plan,
        "razorpay_plan_id": subscription.get("plan_id"),
        "razorpay_subscription_id": subscription.get("id"),
        "razorpay_customer_id": subscription.get("customer_id"),
        "razorpay_status": subscription.get("status") or "created",
        "current_start": _timestamp_to_iso(subscription.get("current_start")),
        "current_end": _timestamp_to_iso(subscription.get("current_end")),
        "raw_payload": subscription,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    result = db.table("subscriptions").upsert(row, on_conflict="razorpay_subscription_id").execute()
    return result.data[0] if result.data else None


def update_subscription_from_razorpay(
    razorpay_subscription_id: str,
    subscription: dict,
    app_plan: str | None = None,
    user_id: str | None = None,
) -> Optional[dict]:
    db = get_supabase_service_client()
    if db is None:
        return None

    row = {
        "razorpay_plan_id": subscription.get("plan_id"),
        "razorpay_customer_id": subscription.get("customer_id"),
        "razorpay_status": subscription.get("status"),
        "current_start": _timestamp_to_iso(subscription.get("current_start") or subscription.get("start_at")),
        "current_end": _timestamp_to_iso(subscription.get("current_end") or subscription.get("end_at")),
        "cancelled_at": _timestamp_to_iso(subscription.get("ended_at")) if subscription.get("status") == "cancelled" else None,
        "raw_payload": subscription,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if app_plan:
        row["app_plan"] = app_plan
    if user_id:
        row["user_id"] = user_id

    result = (
        db.table("subscriptions")
        .update(row)
        .eq("razorpay_subscription_id", razorpay_subscription_id)
        .execute()
    )
    return result.data[0] if result.data else None


def fetch_subscription_by_razorpay_id(razorpay_subscription_id: str) -> Optional[dict]:
    db = get_supabase_service_client()
    if db is None:
        return None

    result = (
        db.table("subscriptions")
        .select("*")
        .eq("razorpay_subscription_id", razorpay_subscription_id)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


def fetch_active_razorpay_subscription(user_id: str) -> Optional[dict]:
    db = get_supabase_service_client()
    if db is None:
        return None

    result = (
        db.table("subscriptions")
        .select("*")
        .eq("user_id", user_id)
        .in_("razorpay_status", ["authenticated", "active"])
        .order("updated_at", desc=True)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


def apply_subscription_entitlement(user_id: str, plan: str, subscription: dict) -> Optional[dict]:
    db = get_supabase_service_client()
    if db is None:
        return None

    now = datetime.now(timezone.utc)
    start = _timestamp_to_iso(subscription.get("current_start") or subscription.get("start_at")) or now.isoformat()
    end = _timestamp_to_iso(subscription.get("current_end") or subscription.get("end_at"))

    if not end:
        duration_days = (
            config.SUBSCRIPTION_WEEKLY_DAYS
            if plan == "weekly"
            else config.SUBSCRIPTION_MONTHLY_DAYS
        )
        end = (now + timedelta(days=duration_days)).isoformat()

    payload = {
        "subscription_status": "active",
        "subscription_plan": plan,
        "subscription_start": start,
        "subscription_end": end,
        "razorpay_subscription_id": subscription.get("id"),
        "razorpay_customer_id": subscription.get("customer_id"),
    }
    result = db.table("user_profiles").update(payload).eq("id", user_id).execute()
    if not result.data:
        return None
    return {
        "success": True,
        "status": "active",
        "plan": plan,
        "subscription_start": start,
        "subscription_end": end,
        "razorpay_subscription_id": subscription.get("id"),
    }


def expire_subscription_entitlement(user_id: str, razorpay_status: str = "expired") -> Optional[dict]:
    db = get_supabase_service_client()
    if db is None:
        return None

    result = (
        db.table("user_profiles")
        .update({"subscription_status": "expired"})
        .eq("id", user_id)
        .execute()
    )
    if not result.data:
        return None
    return {"success": True, "status": "expired", "razorpay_status": razorpay_status}


def record_webhook_event(event_id: str, event_name: str, payload: dict) -> bool:
    db = get_supabase_service_client()
    if db is None or not event_id:
        return False

    existing = (
        db.table("razorpay_webhook_events")
        .select("event_id")
        .eq("event_id", event_id)
        .limit(1)
        .execute()
    )
    if existing.data:
        return False

    db.table("razorpay_webhook_events").insert({
        "event_id": event_id,
        "event_name": event_name,
        "payload": payload,
    }).execute()
    return True


def get_subscription_status(user_id: str) -> Optional[dict]:
    db = get_supabase_service_client()
    if db is None:
        return None

    result = (
        db.table("user_profiles")
        .select("subscription_status, subscription_plan, subscription_start, subscription_end, razorpay_subscription_id")
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
        "subscription_start": row.get("subscription_start"),
        "subscription_end": subscription_end,
        "days_remaining": days_remaining,
        "razorpay_subscription_id": row.get("razorpay_subscription_id"),
    }


def _timestamp_to_iso(value) -> str | None:
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc).isoformat()
    except (TypeError, ValueError, OSError):
        return None
