from flask import Blueprint, request, jsonify
from pose.pipeline import run_pose_pipeline
import uuid
import os
import logging
import threading
import json

pose_bp = Blueprint("pose", __name__, url_prefix="/pose")
logger = logging.getLogger(__name__)

# In-memory store: { job_id -> { "status": str, "result": dict, "error": str } }
jobs = {}

def _pose_worker(job_id, landmark_payload, session_id):
    """
    Background worker to run the pose pipeline.
    """
    logger.info(f"[{job_id}] Worker started for session {session_id}")
    jobs[job_id] = {"status": "processing", "result": None, "error": None}

    try:
        # Run the full pose pipeline
        result = run_pose_pipeline(landmark_payload, session_id)
        jobs[job_id]["status"] = "done"
        jobs[job_id]["result"] = result
        logger.info(f"[{job_id}] Pipeline completed successfully")
    except Exception as e:
        logger.error(f"[{job_id}] Pipeline failed: {e}")
        jobs[job_id]["status"] = "error"
        jobs[job_id]["error"] = str(e)

@pose_bp.route("/analyze", methods=["POST"])
def analyze():
    """
    POST /pose/analyze handler.
    
    Accepts landmark JSON from the React Native frontend (BlazePose/TF.js).
    Multipart field: 'pose_landmarks' — JSON file containing frame-by-frame
    landmark arrays extracted on-device.
    """
    if "pose_landmarks" not in request.files:
        return jsonify({"error": "Missing field: pose_landmarks"}), 400

    session_id = request.form.get("session_id", str(uuid.uuid4()))
    landmark_file = request.files["pose_landmarks"]

    try:
        landmark_payload = json.loads(landmark_file.read().decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        logger.error(f"[{session_id}] Failed to parse landmark JSON: {e}")
        return jsonify({"error": "Invalid landmark JSON payload"}), 400

    logger.info(f"[{session_id}] Landmark JSON received. Spawning background worker.")

    # Create job
    job_id = str(uuid.uuid4())
    jobs[job_id] = {"status": "processing", "result": None, "error": None}

    # Spawn background thread
    thread = threading.Thread(target=_pose_worker, args=(job_id, landmark_payload, session_id))
    thread.daemon = True
    thread.start()

    return jsonify({"job_id": job_id, "session_id": session_id}), 202

@pose_bp.route("/status/<job_id>", methods=["GET"])
def get_status(job_id):
    """
    GET /pose/status/<job_id> handler.
    Poll this endpoint to get the result of the background job.
    """
    job = jobs.get(job_id)
    if not job:
        return jsonify({"status": "not_found"}), 404
    
    return jsonify(job), 200
