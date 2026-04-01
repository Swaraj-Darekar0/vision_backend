import base64
import json
import logging
from typing import Optional

from supabase import Client, create_client

import config

logger = logging.getLogger(__name__)

_public_db: Optional[Client] = None
_service_db: Optional[Client] = None


def get_supabase_client() -> Optional[Client]:
    """
    Public/anon client.
    Used for auth-oriented operations like resolving a bearer token.
    """
    global _public_db

    if _public_db is not None:
        return _public_db

    if not config.SUPABASE_URL or not config.SUPABASE_KEY:
        logger.warning("Public Supabase credentials missing in config.")
        return None

    try:
        _public_db = create_client(config.SUPABASE_URL, config.SUPABASE_KEY)
        logger.info("Public Supabase client initialized successfully.")
        return _public_db
    except Exception as exc:
        logger.error(f"Failed to initialize public Supabase client: {exc}")
        return None


def get_supabase_service_client() -> Optional[Client]:
    """
    Service-role client.
    Used for trusted backend reads/writes that must bypass RLS.
    """
    global _service_db

    if _service_db is not None:
        return _service_db

    service_key = config.SUPABASE_SERVICE_ROLE_KEY or _service_key_fallback()
    if not config.SUPABASE_URL or not service_key:
        logger.error(
            "Service-role Supabase credentials missing. Set SUPABASE_SERVICE_ROLE_KEY for trusted backend writes."
        )
        return None

    try:
        _service_db = create_client(config.SUPABASE_URL, service_key)
        logger.info("Service-role Supabase client initialized successfully.")
        return _service_db
    except Exception as exc:
        logger.error(f"Failed to initialize service-role Supabase client: {exc}")
        return None


def _service_key_fallback() -> str:
    if _jwt_role(config.SUPABASE_KEY) == "service_role":
        logger.warning("SUPABASE_SERVICE_ROLE_KEY missing; falling back to SUPABASE_KEY because it is service_role.")
        return config.SUPABASE_KEY
    return ""


def _jwt_role(key: str) -> str:
    try:
        parts = key.split(".")
        if len(parts) < 2:
            return ""
        payload = parts[1]
        payload += "=" * (-len(payload) % 4)
        decoded = base64.urlsafe_b64decode(payload.encode("utf-8"))
        claims = json.loads(decoded.decode("utf-8"))
        return str(claims.get("role", ""))
    except Exception:
        return ""
