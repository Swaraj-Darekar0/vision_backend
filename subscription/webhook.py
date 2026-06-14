import hmac
import hashlib
import os
import logging
from typing import Any

import requests
from flask import Blueprint, request, current_app

import config


MIPOE_URL = "https://enrich-prominent-backspace.ngrok-free.dev/api/webhooks/subscription/11"

subscription_webhook_bp = Blueprint("subscription_webhook", __name__)


def _get_gateway_secret() -> str | None:
    # Prefer explicit config attribute, fall back to env var
    return getattr(config, "RAZORPAY_WEBHOOK_SECRET", None) or os.getenv("RAZORPAY_WEBHOOK_SECRET")


def _get_mipoe_key() -> str | None:
    return getattr(config, "MIPOE_API_KEY", None) or os.getenv("MIPOE_API_KEY")


@subscription_webhook_bp.route("/webhooks/razorpay", methods=["POST"])
def razorpay_webhook() -> tuple[str, int]:
    """Handle Razorpay webhooks, verify signature, extract fields and forward to Mipoe.

    This endpoint always returns HTTP 200 to the gateway (per requirements) but logs
    verification/forwarding failures for operators to inspect.
    """
    logger: logging.Logger = current_app.logger

    raw_body = request.get_data()
    signature = request.headers.get("X-Razorpay-Signature") or request.headers.get("x-razorpay-signature")

    try:
        secret = _get_gateway_secret()
        if not secret:
            logger.error("RAZORPAY_WEBHOOK_SECRET is not configured; rejecting verification")
            return "", 200

        if not signature:
            logger.error("Missing Razorpay signature header")
            return "", 200

        expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, signature):
            logger.error("Invalid Razorpay webhook signature")
            return "", 200

        payload: dict[str, Any] = request.get_json(force=True) or {}

        # Try common locations for the payment/subscription entity
        entity = (
            payload.get("payload", {}).get("payment", {}).get("entity")
            or payload.get("payload", {}).get("subscription", {}).get("entity")
            or payload.get("payload", {}).get("invoice", {}).get("entity")
            or payload
        )

        # Extract fields with sensible fallbacks
        transaction_id = entity.get("id") or entity.get("payment_id") or entity.get("transaction_id") or ""
        amount = entity.get("amount") or entity.get("amount_paid") or 0
        try:
            amount = int(amount)
        except Exception:
            amount = 0

        currency = (entity.get("currency") or entity.get("currency_code") or "INR").upper()
        email = entity.get("email") or entity.get("contact") or ""

        notes = entity.get("notes") or {}
        affiliate_code = (
            notes.get("ref")
            or notes.get("affiliate")
            or notes.get("affiliate_code")
            or notes.get("affiliate_id")
            or ""
        )

        plan_id = (
            entity.get("plan_id")
            or notes.get("app_plan")
            or payload.get("payload", {}).get("subscription", {}).get("entity", {}).get("plan_id")
            or "unknown"
        )

        forward_payload = {
            "event": "subscription.created",
            "transaction_id": transaction_id,
            "customer_email": email,
            "amount": amount,
            "currency": currency,
            "plan_id": plan_id,
            "affiliate_code": affiliate_code,
        }

        mipoe_key = _get_mipoe_key()
        if not mipoe_key:
            logger.error("MIPOE_API_KEY not configured; skipping forwarding to Mipoe")
            return "", 200

        headers = {"Authorization": f"Bearer {mipoe_key}", "Content-Type": "application/json"}

        try:
            resp = requests.post(MIPOE_URL, json=forward_payload, headers=headers, timeout=10)
            if resp.status_code >= 400:
                logger.error("Mipoe webhook responded %s: %s", resp.status_code, resp.text)
            else:
                logger.info("Successfully forwarded event to Mipoe (status=%s)", resp.status_code)
        except Exception:
            logger.exception("Error forwarding event to Mipoe")

        # Always return 200 OK to the payment gateway per requirement
        return "", 200

    except Exception:
        logger.exception("Unexpected error while handling Razorpay webhook")
        return "", 200
