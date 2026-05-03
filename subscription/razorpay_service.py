import hmac
import hashlib
from typing import Any

import requests

import config


RAZORPAY_API_BASE = "https://api.razorpay.com/v1"


class RazorpayConfigError(RuntimeError):
    pass


class RazorpayRequestError(RuntimeError):
    pass


def _require_credentials() -> tuple[str, str]:
    if not config.RAZORPAY_KEY_ID or not config.RAZORPAY_KEY_SECRET:
        raise RazorpayConfigError("Razorpay API credentials are not configured")
    return config.RAZORPAY_KEY_ID, config.RAZORPAY_KEY_SECRET


def get_plan_id(plan: str) -> str:
    plan_id = config.RAZORPAY_WEEKLY_PLAN_ID if plan == "weekly" else config.RAZORPAY_MONTHLY_PLAN_ID
    if not plan_id:
        raise RazorpayConfigError(f"Razorpay {plan} plan id is not configured")
    return plan_id


def get_total_count(plan: str) -> int:
    return config.RAZORPAY_WEEKLY_TOTAL_COUNT if plan == "weekly" else config.RAZORPAY_MONTHLY_TOTAL_COUNT


def get_amount(plan: str) -> int:
    rupees = config.SUBSCRIPTION_PRICE_WEEKLY if plan == "weekly" else config.SUBSCRIPTION_PRICE_MONTHLY
    return rupees * 100


def _request(method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    key_id, key_secret = _require_credentials()
    response = requests.request(
        method,
        f"{RAZORPAY_API_BASE}{path}",
        auth=(key_id, key_secret),
        json=payload,
        timeout=20,
    )
    if response.status_code >= 400:
        raise RazorpayRequestError(response.text)
    return response.json()


def create_subscription(user_id: str, plan: str) -> dict[str, Any]:
    payload = {
        "plan_id": get_plan_id(plan),
        "total_count": get_total_count(plan),
        "quantity": 1,
        "customer_notify": True,
        "notes": {
            "user_id": user_id,
            "app_plan": plan,
        },
    }
    return _request("POST", "/subscriptions", payload)


def fetch_subscription(razorpay_subscription_id: str) -> dict[str, Any]:
    return _request("GET", f"/subscriptions/{razorpay_subscription_id}")


def cancel_subscription(razorpay_subscription_id: str, cancel_at_cycle_end: bool = True) -> dict[str, Any]:
    return _request(
        "POST",
        f"/subscriptions/{razorpay_subscription_id}/cancel",
        {"cancel_at_cycle_end": int(cancel_at_cycle_end)},
    )


def verify_checkout_signature(payment_id: str, subscription_id: str, signature: str) -> bool:
    if not config.RAZORPAY_KEY_SECRET:
        raise RazorpayConfigError("Razorpay key secret is not configured")

    message = f"{payment_id}|{subscription_id}".encode("utf-8")
    expected = hmac.new(
        config.RAZORPAY_KEY_SECRET.encode("utf-8"),
        message,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


def verify_webhook_signature(raw_body: bytes, signature: str) -> bool:
    if not config.RAZORPAY_WEBHOOK_SECRET:
        raise RazorpayConfigError("Razorpay webhook secret is not configured")

    expected = hmac.new(
        config.RAZORPAY_WEBHOOK_SECRET.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)
