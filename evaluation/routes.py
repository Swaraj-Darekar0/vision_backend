from flask import Blueprint, request, jsonify
from evaluation.pipeline import run_evaluation_pipeline
import logging

eval_bp = Blueprint("evaluation", __name__, url_prefix="/evaluate")
logger = logging.getLogger(__name__)

@eval_bp.route("", methods=["POST"])
def evaluate():
    """
    POST /evaluate handler.
    Expects JSON body with: pose_json, audio_json, user_id.
    Source: backend_SKILL.md Section 6 (evaluation/routes.py).
    """
    data = request.get_json()
    
    if not data:
        return jsonify({"error": "Missing request body"}), 400
        
    pose_data = data.get("pose_json")
    audio_data = data.get("audio_json")
    user_id = data.get("user_id")
    
    if not all([pose_data, audio_data, user_id]):
        return jsonify({"error": "Missing required fields: pose_json, audio_json, and user_id are all required"}), 400

    logger.info(f"Received evaluation request for user: {user_id}")

    try:
        # Run the full evaluation pipeline
        result = run_evaluation_pipeline(pose_data, audio_data, user_id)
        return jsonify(result), 200
    except ValueError as ve:
        logger.error(f"Validation error for user {user_id}: {ve}")
        return jsonify({"error": "Input validation failed", "detail": str(ve)}), 400
    except Exception as e:
        logger.error(f"Evaluation pipeline failed for user {user_id}: {e}")
        return jsonify({"error": "Evaluation processing failed", "detail": str(e)}), 500
