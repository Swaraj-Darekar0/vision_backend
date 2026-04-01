from flask import Blueprint, jsonify, request

import config
from common.auth import resolve_request_user
from subscription.pipeline import (
    activate_user_subscription,
    fetch_subscription_status,
    save_profile,
)

subscription_bp = Blueprint("subscription", __name__, url_prefix="/subscription")


@subscription_bp.route("/profile", methods=["POST"])
def save_subscription_profile():
    payload = request.get_json(silent=True)
    if payload is None:
        return jsonify({"error": "Missing or invalid JSON body"}), 400

    user_id, err, status = resolve_request_user(request)
    if err:
        return jsonify(err), status

    interest_areas = payload.get("interest_areas", [])
    if not isinstance(interest_areas, list):
        return jsonify({"error": "interest_areas must be an array"}), 400

    result = save_profile(user_id, payload)
    if not result:
        return jsonify({"error": "Failed to save user profile"}), 500
    return jsonify(result), 200


@subscription_bp.route("/activate", methods=["POST"])
def activate():
    payload = request.get_json(silent=True)
    if payload is None:
        return jsonify({"error": "Missing or invalid JSON body"}), 400

    user_id, err, status = resolve_request_user(request)
    if err:
        return jsonify(err), status

    plan = payload.get("plan")
    payment_reference = payload.get("payment_reference")
    if plan not in config.SUBSCRIPTION_PLAN_VALUES:
        return jsonify({"error": "plan must be one of: weekly, monthly"}), 400
    if not payment_reference:
        return jsonify({"error": "payment_reference is required"}), 400

    result = activate_user_subscription(user_id, plan)
    if not result:
        return jsonify({"error": "Failed to activate subscription"}), 500
    return jsonify(result), 200


@subscription_bp.route("/status", methods=["GET"])
def status():
    user_id, err, status_code = resolve_request_user(request)
    if err:
        return jsonify(err), status_code

    result = fetch_subscription_status(user_id)
    if not result:
        return jsonify({"error": "Subscription status not found"}), 404
    return jsonify(result), 200
