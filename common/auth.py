from typing import Any, Optional

from flask import Request

from common.supabase_client import get_supabase_client


def _get_bearer_token(req: Request) -> Optional[str]:
    auth_header = req.headers.get("Authorization", "").strip()
    if not auth_header.lower().startswith("bearer "):
        return None
    token = auth_header[7:].strip()
    return token or None


def _extract_payload_user_id(req: Request) -> Optional[str]:
    if req.method == "GET":
        return req.args.get("user_id")

    if req.is_json:
        payload = req.get_json(silent=True) or {}
        return payload.get("user_id")

    return req.form.get("user_id")


def resolve_request_user(req: Request) -> tuple[Optional[str], Optional[dict], Optional[int]]:
    body_user_id = _extract_payload_user_id(req)
    token = _get_bearer_token(req)

    if token:
        client = get_supabase_client()
        if client is None:
            return None, {"error": "Supabase client not initialized"}, 500

        try:
            auth_response = client.auth.get_user(token)
            token_user_id = getattr(getattr(auth_response, "user", None), "id", None)
        except Exception:
            token_user_id = None

        if not token_user_id:
            return None, {"error": "Invalid or expired bearer token"}, 401

        if body_user_id and body_user_id != token_user_id:
            return None, {"error": "Authenticated user does not match request user_id"}, 403

        return token_user_id, None, None

    if body_user_id:
        return body_user_id, None, None

    return None, {"error": "Missing authentication. Provide a bearer token or user_id."}, 401


def require_bearer_user(req: Request) -> tuple[Optional[str], Optional[dict], Optional[int]]:
    token = _get_bearer_token(req)
    if not token:
        return None, {"error": "Missing bearer token"}, 401

    client = get_supabase_client()
    if client is None:
        return None, {"error": "Supabase client not initialized"}, 500

    try:
        auth_response = client.auth.get_user(token)
        token_user_id = getattr(getattr(auth_response, "user", None), "id", None)
    except Exception:
        token_user_id = None

    if not token_user_id:
        return None, {"error": "Invalid or expired bearer token"}, 401

    return token_user_id, None, None


def get_json(required: bool = True) -> tuple[dict[str, Any], Optional[dict], Optional[int]]:
    from flask import request

    payload = request.get_json(silent=True)
    if payload is None:
        if required:
            return {}, {"error": "Missing or invalid JSON body"}, 400
        return {}, None, None
    return payload, None, None
