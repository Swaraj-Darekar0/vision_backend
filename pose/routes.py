from flask import Blueprint, request, jsonify
from pose.pipeline import run_pose_pipeline
import uuid
import os
import logging

pose_bp = Blueprint("pose", __name__, url_prefix="/pose")
logger = logging.getLogger(__name__)

@pose_bp.route("/analyze", methods=["POST"])
def analyze():
    """
    POST /pose/analyze handler.
    Source: backend_SKILL.md Section 10.
    """
    if "video" not in request.files:
        return jsonify({"error": "No video file provided"}), 400

    file = request.files["video"]
    if file.filename == "":
        return jsonify({"error": "Empty filename"}), 400

    # Ensure valid MP4 extension
    if not file.filename.lower().endswith(".mp4"):
        return jsonify({"error": "Only MP4 videos are supported"}), 400

    session_id = str(uuid.uuid4())
    # Using a generic temp directory that works across OSes
    tmp_dir = os.path.join(os.getcwd(), "tmp")
    os.makedirs(tmp_dir, exist_ok=True)
    tmp_path = os.path.join(tmp_dir, f"{session_id}.mp4")
    
    file.save(tmp_path)
    logger.info(f"[{session_id}] Starting pose analysis for file: {file.filename}")

    try:
        # Run the full pose pipeline
        result = run_pose_pipeline(tmp_path, session_id)
        return jsonify(result), 200
    except Exception as e:
        logger.error(f"[{session_id}] Pipeline failed: {e}")
        return jsonify({
            "error": "Pose processing failed",
            "detail": str(e)
        }), 500
    finally:
        # Clean up temporary file
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
            logger.info(f"[{session_id}] Cleaned up temp file: {tmp_path}")
