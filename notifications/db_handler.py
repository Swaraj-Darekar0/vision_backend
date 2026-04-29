from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Any, Optional
from uuid import uuid4

from common.supabase_client import get_supabase_service_client

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def upsert_push_token(payload: dict[str, Any]) -> bool:
    db = get_supabase_service_client()
    if db is None:
        logger.error("Push token upsert skipped: service-role Supabase client unavailable.")
        return False

    now = _now()
    row = {
        "user_id": payload["user_id"],
        "expo_push_token": payload["expo_push_token"],
        "platform": payload.get("platform"),
        "device_id": payload.get("device_id"),
        "app_version": payload.get("app_version"),
        "is_active": True,
        "last_seen_at": now,
        "updated_at": now,
    }
    device_id = payload.get("device_id")

    try:
        if device_id:
            db.table("push_tokens").update(
                {
                    "is_active": False,
                    "updated_at": now,
                }
            ).eq("device_id", device_id).neq("expo_push_token", payload["expo_push_token"]).execute()

        db.table("push_tokens").upsert(row, on_conflict="expo_push_token").execute()
        logger.info(
            "Push token upserted for user_id=%s platform=%s device_id=%s",
            payload["user_id"],
            payload.get("platform"),
            payload.get("device_id"),
        )
        return True
    except Exception as exc:
        logger.exception("Failed to upsert push token for user_id=%s: %s", payload.get("user_id"), exc)
        return False


def deactivate_push_token(user_id: str, expo_push_token: str) -> bool:
    db = get_supabase_service_client()
    if db is None:
        logger.error("Push token deactivate skipped: service-role Supabase client unavailable.")
        return False

    try:
        db.table("push_tokens").update({"is_active": False, "updated_at": _now()}).eq("user_id", user_id).eq(
            "expo_push_token", expo_push_token
        ).execute()
        logger.info("Push token deactivated for user_id=%s", user_id)
        return True
    except Exception as exc:
        logger.exception("Failed to deactivate push token for user_id=%s: %s", user_id, exc)
        return False


def deactivate_push_tokens_for_device(user_id: str, device_id: str) -> bool:
    db = get_supabase_service_client()
    if db is None:
        logger.error("Push token device deactivate skipped: service-role Supabase client unavailable.")
        return False

    try:
        db.table("push_tokens").update({"is_active": False, "updated_at": _now()}).eq("user_id", user_id).eq(
            "device_id", device_id
        ).execute()
        logger.info("Push tokens deactivated for user_id=%s device_id=%s", user_id, device_id)
        return True
    except Exception as exc:
        logger.exception(
            "Failed to deactivate push tokens for user_id=%s device_id=%s: %s",
            user_id,
            device_id,
            exc,
        )
        return False


def deactivate_tokens(expo_push_tokens: list[str]) -> None:
    if not expo_push_tokens:
        return

    db = get_supabase_service_client()
    if db is None:
        return

    db.table("push_tokens").update({"is_active": False, "updated_at": _now()}).in_(
        "expo_push_token", expo_push_tokens
    ).execute()


def fetch_active_push_tokens() -> list[dict[str, Any]]:
    db = get_supabase_service_client()
    if db is None:
        return []

    rows: list[dict[str, Any]] = []
    page_size = 1000
    start = 0

    while True:
        end = start + page_size - 1
        result = (
            db.table("push_tokens")
            .select("id,user_id,expo_push_token,platform")
            .eq("is_active", True)
            .range(start, end)
            .execute()
        )
        batch = result.data or []
        rows.extend(batch)
        if len(batch) < page_size:
            break
        start += page_size

    return rows


def create_campaign(admin_user_id: str, payload: dict[str, Any], total_tokens: int) -> Optional[dict[str, Any]]:
    db = get_supabase_service_client()
    if db is None:
        return None

    row = {
        "id": str(uuid4()),
        "admin_user_id": admin_user_id,
        "title": payload["title"],
        "body": payload["body"],
        "image_url": payload.get("image_url"),
        "data": payload.get("data") or {},
        "target": payload.get("target", "all"),
        "status": "queued",
        "total_tokens": total_tokens,
        "sent_count": 0,
        "failed_count": 0,
        "created_at": _now(),
    }
    result = db.table("notification_campaigns").insert(row).execute()
    return result.data[0] if result.data else row


def update_campaign(campaign_id: str, values: dict[str, Any]) -> None:
    db = get_supabase_service_client()
    if db is None:
        return
    db.table("notification_campaigns").update(values).eq("id", campaign_id).execute()


def insert_deliveries(rows: list[dict[str, Any]]) -> None:
    if not rows:
        return

    db = get_supabase_service_client()
    if db is None:
        return

    timestamp = _now()
    prepared = [{**row, "id": str(uuid4()), "created_at": timestamp} for row in rows]
    db.table("notification_deliveries").insert(prepared).execute()


def fetch_campaign_history(limit: int = 50) -> list[dict[str, Any]]:
    db = get_supabase_service_client()
    if db is None:
        return []

    result = (
        db.table("notification_campaigns")
        .select("*")
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return result.data or []
