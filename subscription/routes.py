from flask import Blueprint, jsonify, request

import config
from common.auth import require_bearer_user
from subscription import razorpay_service
from subscription.pipeline import (
    cancel_user_subscription,
    create_checkout_subscription,
    fetch_subscription_status,
    handle_razorpay_webhook,
    save_profile,
    verify_checkout_subscription,
)

subscription_bp = Blueprint("subscription", __name__, url_prefix="/subscription")


@subscription_bp.route("/profile", methods=["POST"])
def save_subscription_profile():
    payload = request.get_json(silent=True)
    if payload is None:
        return jsonify({"error": "Missing or invalid JSON body"}), 400

    user_id, err, status = require_bearer_user(request)
    if err:
        return jsonify(err), status

    interest_areas = payload.get("interest_areas", [])
    if not isinstance(interest_areas, list):
        return jsonify({"error": "interest_areas must be an array"}), 400

    result = save_profile(user_id, payload)
    if not result:
        return jsonify({"error": "Failed to save user profile"}), 500
    return jsonify(result), 200


@subscription_bp.route("/create", methods=["POST"])
def create_subscription():
    payload = request.get_json(silent=True)
    if payload is None:
        return jsonify({"error": "Missing or invalid JSON body"}), 400

    user_id, err, status = require_bearer_user(request)
    if err:
        return jsonify(err), status

    plan = payload.get("plan")
    if plan not in config.SUBSCRIPTION_PLAN_VALUES:
        return jsonify({"error": "plan must be one of: weekly, monthly"}), 400

    try:
        result = create_checkout_subscription(user_id, plan)
    except razorpay_service.RazorpayConfigError as exc:
        return jsonify({"error": str(exc)}), 500
    except razorpay_service.RazorpayRequestError as exc:
        return jsonify({"error": "Razorpay subscription creation failed", "details": str(exc)}), 502

    if not result:
        return jsonify({"error": "Failed to create subscription"}), 500
    return jsonify(result), 201


@subscription_bp.route("/verify", methods=["POST"])
def verify_subscription():
    payload = request.get_json(silent=True)
    if payload is None:
        return jsonify({"error": "Missing or invalid JSON body"}), 400

    user_id, err, status = require_bearer_user(request)
    if err:
        return jsonify(err), status

    try:
        result = verify_checkout_subscription(user_id, payload)
    except razorpay_service.RazorpayConfigError as exc:
        return jsonify({"error": str(exc)}), 500
    except razorpay_service.RazorpayRequestError as exc:
        return jsonify({"error": "Razorpay subscription verification failed", "details": str(exc)}), 502

    if not result:
        return jsonify({"error": "Invalid or unverified Razorpay subscription"}), 400
    return jsonify(result), 200


@subscription_bp.route("/cancel", methods=["POST"])
def cancel_subscription():
    user_id, err, status = require_bearer_user(request)
    if err:
        return jsonify(err), status

    try:
        result = cancel_user_subscription(user_id)
    except razorpay_service.RazorpayRequestError as exc:
        return jsonify({"error": "Razorpay subscription cancellation failed", "details": str(exc)}), 502

    if not result:
        return jsonify({"error": "Active subscription not found"}), 404
    return jsonify(result), 200


@subscription_bp.route("/webhook", methods=["POST"])
def razorpay_webhook():
    raw_body = request.get_data()
    signature = request.headers.get("X-Razorpay-Signature", "")

    try:
        if not razorpay_service.verify_webhook_signature(raw_body, signature):
            return jsonify({"error": "Invalid webhook signature"}), 400
    except razorpay_service.RazorpayConfigError as exc:
        return jsonify({"error": str(exc)}), 500

    payload = request.get_json(silent=True)
    if payload is None:
        return jsonify({"error": "Missing or invalid JSON body"}), 400

    event_id = request.headers.get("x-razorpay-event-id") or payload.get("id") or ""
    result = handle_razorpay_webhook(event_id, payload.get("event", ""), payload)
    return jsonify(result), 200


@subscription_bp.route("/status", methods=["GET"])
def status():
    user_id, err, status_code = require_bearer_user(request)
    if err:
        return jsonify(err), status_code

    result = fetch_subscription_status(user_id)
    if not result:
        return jsonify({"error": "Subscription status not found"}), 404
    return jsonify(result), 200
