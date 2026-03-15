from flask import Blueprint, request, jsonify
from evaluation.pipeline import run_evaluation_pipeline
import logging
import threading
import uuid

eval_bp = Blueprint("evaluation", __name__, url_prefix="/evaluate")
logger = logging.getLogger(__name__)

# In-memory store: { job_id -> { "status": str, "result": dict, "error": str } }
jobs = {}

def _eval_worker(job_id, pose_data, audio_data, user_id):
    """
    Background worker to run the evaluation pipeline.
    """
    logger.info(f"[{job_id}] Worker started for user {user_id}")
    jobs[job_id] = {"status": "processing", "result": None, "error": None}

    try:
        # Run the full evaluation pipeline
        result = run_evaluation_pipeline(pose_data, audio_data, user_id)
        jobs[job_id]["status"] = "done"
        jobs[job_id]["result"] = result
        logger.info(f"[{job_id}] Pipeline completed successfully")
    except Exception as e:
        logger.error(f"[{job_id}] Evaluation pipeline failed for user {user_id}: {e}")
        jobs[job_id]["status"] = "error"
        jobs[job_id]["error"] = str(e)

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

    # Create job
    job_id = str(uuid.uuid4())
    jobs[job_id] = {"status": "processing", "result": None, "error": None}

    # Spawn background thread
    thread = threading.Thread(target=_eval_worker, args=(job_id, pose_data, audio_data, user_id))
    thread.daemon = True
    thread.start()

    return jsonify({"job_id": job_id}), 202

@eval_bp.route("/status/<job_id>", methods=["GET"])
def get_status(job_id):
    """
    GET /evaluate/status/<job_id> handler.
    Poll this endpoint to get the result of the background job.
    """
    job = jobs.get(job_id)
    if not job:
        return jsonify({"status": "not_found"}), 404
    
    return jsonify(job), 200
