from flask import Blueprint, jsonify, request
import logging

import config
from common.auth import resolve_request_user
from plan.pipeline import (
    build_weekly_review,
    generate_plan,
    get_current_plan,
    get_personal_bests,
    mark_topic_complete,
    set_review_shown,
)
from plan.topic_generator import TopicGenerationError, TopicValidationError

plan_bp = Blueprint("plan", __name__, url_prefix="/plan")
logger = logging.getLogger(__name__)


def _require_json():
    payload = request.get_json(silent=True)
    if payload is None:
        return None, (jsonify({"error": "Missing or invalid JSON body"}), 400)
    return payload, None


def _serialize_plan(plan: dict) -> dict:
    return {
        "plan_id": plan.get("id"),
        "week_number": plan.get("week_number"),
        "week_start_date": plan.get("week_start_date"),
        "speaker_level": plan.get("speaker_level"),
        "sessions_per_day": plan.get("sessions_per_day"),
        "plan_data": plan.get("plan_data", {}),
        "generated_at": plan.get("generated_at"),
        "is_current": plan.get("is_current"),
    }


@plan_bp.route("/generate", methods=["POST"])
def generate():
    payload, error_response = _require_json()
    if error_response:
        return error_response

    user_id, err, status = resolve_request_user(request)
    if err:
        return jsonify(err), status

    logger.info("Accepted /plan/generate request")

    required_fields = [
        "week_number",
        "week_start_date",
        "speaker_level",
        "sessions_per_day",
        "user_profile",
        "plan_context",
    ]
    missing = [field for field in required_fields if payload.get(field) is None]
    if missing:
        return jsonify({"error": f"Missing required fields: {', '.join(missing)}"}), 400
    if payload["speaker_level"] not in config.SPEAKER_LEVEL_VALUES:
        return jsonify({"error": "speaker_level must be one of: developing, competent, advanced"}), 400
    if not isinstance(payload.get("user_profile"), dict):
        return jsonify({"error": "user_profile must be an object"}), 400
    if not isinstance(payload.get("plan_context"), dict):
        return jsonify({"error": "plan_context must be an object"}), 400
    if not isinstance(payload.get("previously_used_topics", []), list):
        return jsonify({"error": "previously_used_topics must be an array"}), 400

    try:
        payload["week_number"] = int(payload["week_number"])
        payload["sessions_per_day"] = int(payload["sessions_per_day"])
    except (TypeError, ValueError):
        return jsonify({"error": "week_number and sessions_per_day must be integers"}), 400

    user_profile = payload["user_profile"]
    profile_fields = ["identity", "work_domain", "interest_areas", "speaking_goal", "practice_frequency"]
    missing_profile = [field for field in profile_fields if user_profile.get(field) is None]
    if missing_profile:
        return jsonify({"error": f"Missing user_profile fields: {', '.join(missing_profile)}"}), 400
    if not isinstance(user_profile.get("interest_areas"), list):
        return jsonify({"error": "user_profile.interest_areas must be an array"}), 400

    plan_context = payload["plan_context"]
    context_fields = ["speaker_level", "current_week", "tier", "sessions_this_week", "performance_last_week"]
    missing_context = [field for field in context_fields if field not in plan_context]
    if missing_context:
        return jsonify({"error": f"Missing plan_context fields: {', '.join(missing_context)}"}), 400
    if plan_context.get("speaker_level") != payload["speaker_level"]:
        return jsonify({"error": "plan_context.speaker_level must match speaker_level"}), 400
    if not str(plan_context.get("tier", "")).strip():
        return jsonify({"error": "plan_context.tier is required"}), 400
    try:
        plan_context["current_week"] = int(plan_context.get("current_week"))
        plan_context["sessions_this_week"] = int(plan_context.get("sessions_this_week"))
    except (TypeError, ValueError):
        return jsonify({"error": "plan_context.current_week and sessions_this_week must be integers"}), 400
    if plan_context.get("performance_last_week") is not None and not isinstance(plan_context.get("performance_last_week"), dict):
        return jsonify({"error": "plan_context.performance_last_week must be an object or null"}), 400
    if plan_context.get("current_week") != payload["week_number"]:
        return jsonify({"error": "plan_context.current_week must match week_number"}), 400

    try:
        stored_plan = generate_plan(user_id, payload)
    except TopicValidationError as exc:
        logger.error(f"/plan/generate validation failure: {exc}")
        return jsonify({"error": str(exc)}), 502
    except TopicGenerationError as exc:
        logger.error(f"/plan/generate Groq failure: {exc}")
        return jsonify({"error": str(exc)}), 502
    except Exception as exc:
        logger.exception(f"/plan/generate unexpected failure: {exc}")
        return jsonify({"error": "Unexpected plan generation failure"}), 500

    if not stored_plan:
        logger.error("/plan/generate database insert failed")
        return jsonify({"error": "Failed to generate weekly plan"}), 500
    logger.info("Stored weekly plan successfully")
    return jsonify(_serialize_plan(stored_plan)), 200


@plan_bp.route("/current", methods=["GET"])
def current():
    user_id, err, status = resolve_request_user(request)
    if err:
        return jsonify(err), status

    plan = get_current_plan(user_id)
    if not plan:
        return jsonify({"error": "Current weekly plan not found"}), 404
    return jsonify(_serialize_plan(plan)), 200


@plan_bp.route("/mark-complete", methods=["PATCH"])
def mark_complete():
    payload, error_response = _require_json()
    if error_response:
        return error_response

    user_id, err, status = resolve_request_user(request)
    if err:
        return jsonify(err), status

    required_fields = ["week_number", "day", "session", "session_id"]
    missing = [field for field in required_fields if payload.get(field) is None]
    if missing:
        return jsonify({"error": f"Missing required fields: {', '.join(missing)}"}), 400

    updated_plan = mark_topic_complete(
        user_id=user_id,
        week_number=int(payload["week_number"]),
        day=int(payload["day"]),
        session=int(payload["session"]),
        session_id=payload["session_id"],
    )
    if not updated_plan:
        return jsonify({"error": "Plan topic not found or update failed"}), 404
    return jsonify({"success": True, "plan": _serialize_plan(updated_plan)}), 200


@plan_bp.route("/weekly-review", methods=["POST"])
def weekly_review():
    payload, error_response = _require_json()
    if error_response:
        return error_response

    user_id, err, status = resolve_request_user(request)
    if err:
        return jsonify(err), status

    week_number = payload.get("week_number")
    if week_number is None:
        return jsonify({"error": "week_number is required"}), 400

    review = build_weekly_review(user_id, int(week_number))
    if not review:
        return jsonify({"error": "Failed to build weekly review"}), 404
    return jsonify(review), 200


@plan_bp.route("/review-shown", methods=["PATCH"])
def review_shown():
    payload, error_response = _require_json()
    if error_response:
        return error_response

    user_id, err, status = resolve_request_user(request)
    if err:
        return jsonify(err), status

    week_number = payload.get("week_number")
    if week_number is None:
        return jsonify({"error": "week_number is required"}), 400

    success = set_review_shown(user_id, int(week_number))
    if not success:
        return jsonify({"error": "Failed to update review visibility"}), 404
    return jsonify({"success": True}), 200


@plan_bp.route("/personal-bests", methods=["GET"])
def personal_bests():
    user_id, err, status = resolve_request_user(request)
    if err:
        return jsonify(err), status

    bests = get_personal_bests(user_id)
    if not bests:
        return jsonify({"error": "Personal bests not found"}), 404
    return jsonify(bests), 200
