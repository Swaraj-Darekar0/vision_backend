from __future__ import annotations

import mimetypes
import threading
from datetime import datetime, timezone
from uuid import uuid4
import logging

from flask import Blueprint, jsonify, request

import config
from common.supabase_client import get_supabase_service_client
from notifications import db_handler
from notifications.admin_auth import require_admin_user, require_bearer_user
from notifications.expo_client import send_campaign

notifications_bp = Blueprint("notifications", __name__)
logger = logging.getLogger(__name__)


def _json_payload():
    payload = request.get_json(silent=True)
    if payload is None:
        return None, (jsonify({"error": "Missing or invalid JSON body"}), 400)
    return payload, None


@notifications_bp.route("/notifications/register-token", methods=["POST"])
def register_token():
    payload, error_response = _json_payload()
    if error_response:
        return error_response

    user_id, err, status = require_bearer_user(request)
    if err:
        return jsonify(err), status

    body_user_id = payload.get("user_id")
    if body_user_id and body_user_id != user_id:
        return jsonify({"error": "Authenticated user does not match request user_id"}), 403

    expo_push_token = str(payload.get("expo_push_token", "")).strip()
    platform = str(payload.get("platform", "")).strip().lower()
    if not expo_push_token:
        return jsonify({"error": "expo_push_token is required"}), 400
    if platform not in {"ios", "android"}:
        return jsonify({"error": "platform must be ios or android"}), 400

    logger.info(
        "Registering push token request for user_id=%s platform=%s device_id=%s",
        user_id,
        platform,
        payload.get("device_id"),
    )

    ok = db_handler.upsert_push_token(
        {
            "user_id": user_id,
            "expo_push_token": expo_push_token,
            "platform": platform,
            "device_id": payload.get("device_id"),
            "app_version": payload.get("app_version"),
        }
    )
    if not ok:
        logger.error("Push token registration failed for user_id=%s", user_id)
        return jsonify({"error": "Failed to register push token"}), 500
    return jsonify({"ok": True}), 200


@notifications_bp.route("/notifications/unregister-token", methods=["POST"])
def unregister_token():
    payload, error_response = _json_payload()
    if error_response:
        return error_response

    user_id, err, status = require_bearer_user(request)
    if err:
        return jsonify(err), status

    expo_push_token = str(payload.get("expo_push_token", "")).strip()
    device_id = str(payload.get("device_id", "")).strip()

    if not expo_push_token and not device_id:
        return jsonify({"error": "expo_push_token or device_id is required"}), 400

    if expo_push_token:
        ok = db_handler.deactivate_push_token(user_id, expo_push_token)
    else:
        ok = db_handler.deactivate_push_tokens_for_device(user_id, device_id)

    if not ok:
        return jsonify({"error": "Failed to unregister push token"}), 500
    return jsonify({"ok": True}), 200


@notifications_bp.route("/admin/notifications/upload-image", methods=["POST"])
def upload_notification_image():
    admin_user_id, err, status = require_admin_user(request)
    if err:
        return jsonify(err), status

    uploaded = request.files.get("image")
    if not uploaded:
        return jsonify({"error": "image file is required"}), 400

    content_type = uploaded.mimetype or "application/octet-stream"
    if not content_type.startswith("image/"):
        return jsonify({"error": "image must be an image file"}), 400

    extension = mimetypes.guess_extension(content_type) or ".jpg"
    storage_path = f"{admin_user_id}/{datetime.now(timezone.utc).strftime('%Y%m%d')}/{uuid4()}{extension}"
    db = get_supabase_service_client()
    if db is None:
        return jsonify({"error": "Supabase service client not initialized"}), 500

    try:
        db.storage.from_(config.SUPABASE_NOTIFICATION_IMAGE_BUCKET).upload(
            storage_path,
            uploaded.read(),
            {"content-type": content_type, "upsert": "false"},
        )
        public_url = db.storage.from_(config.SUPABASE_NOTIFICATION_IMAGE_BUCKET).get_public_url(storage_path)
    except Exception as exc:
        return jsonify({"error": f"Failed to upload image: {exc}"}), 500

    return jsonify({"image_url": public_url}), 200


@notifications_bp.route("/admin/notifications/send", methods=["POST"])
def send_notification():
    admin_user_id, err, status = require_admin_user(request)
    if err:
        return jsonify(err), status

    payload, error_response = _json_payload()
    if error_response:
        return error_response

    title = str(payload.get("title", "")).strip()
    body = str(payload.get("body", "")).strip()
    target = payload.get("target", "all")
    if not title:
        return jsonify({"error": "title is required"}), 400
    if not body:
        return jsonify({"error": "body is required"}), 400
    if target != "all":
        return jsonify({"error": "Only target=all is supported in v1"}), 400
    if payload.get("data") is not None and not isinstance(payload.get("data"), dict):
        return jsonify({"error": "data must be an object"}), 400

    tokens = db_handler.fetch_active_push_tokens()
    campaign = db_handler.create_campaign(admin_user_id, payload, len(tokens))
    if not campaign:
        return jsonify({"error": "Failed to create notification campaign"}), 500

    thread = threading.Thread(
        target=send_campaign,
        args=(campaign["id"], payload, tokens),
        daemon=True,
    )
    thread.start()

    return jsonify({"campaign_id": campaign["id"], "status": "queued", "total_tokens": len(tokens)}), 202


@notifications_bp.route("/admin/notifications/history", methods=["GET"])
def notification_history():
    _, err, status = require_admin_user(request)
    if err:
        return jsonify(err), status

    limit_raw = request.args.get("limit", "50")
    try:
        limit = min(100, max(1, int(limit_raw)))
    except ValueError:
        return jsonify({"error": "limit must be a number"}), 400

    return jsonify({"campaigns": db_handler.fetch_campaign_history(limit)}), 200
