from typing import Optional

from flask import Request

from common.supabase_client import get_supabase_client, get_supabase_service_client


def _get_bearer_token(req: Request) -> Optional[str]:
    auth_header = req.headers.get("Authorization", "").strip()
    if not auth_header.lower().startswith("bearer "):
        return None
    token = auth_header[7:].strip()
    return token or None


def require_bearer_user(req: Request) -> tuple[Optional[str], Optional[dict], Optional[int]]:
    token = _get_bearer_token(req)
    if not token:
        return None, {"error": "Missing bearer token"}, 401

    client = get_supabase_client()
    if client is None:
        return None, {"error": "Supabase client not initialized"}, 500

    try:
        auth_response = client.auth.get_user(token)
        user_id = getattr(getattr(auth_response, "user", None), "id", None)
    except Exception:
        user_id = None

    if not user_id:
        return None, {"error": "Invalid or expired bearer token"}, 401

    return user_id, None, None


def require_admin_user(req: Request) -> tuple[Optional[str], Optional[dict], Optional[int]]:
    user_id, err, status = require_bearer_user(req)
    if err:
        return None, err, status

    db = get_supabase_service_client()
    if db is None:
        return None, {"error": "Supabase service client not initialized"}, 500

    try:
        result = (
            db.table("admin_users")
            .select("user_id,is_active")
            .eq("user_id", user_id)
            .eq("is_active", True)
            .limit(1)
            .execute()
        )
    except Exception:
        return None, {"error": "Failed to verify admin access"}, 500

    if not result.data:
        return None, {"error": "Admin access required"}, 403

    return user_id, None, None
