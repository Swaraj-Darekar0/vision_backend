from flask import Blueprint, request, jsonify
from pose.pipeline import run_pose_pipeline
import uuid
import os
import logging
import threading

pose_bp = Blueprint("pose", __name__, url_prefix="/pose")
logger = logging.getLogger(__name__)

# In-memory store: { job_id -> { "status": str, "result": dict, "error": str } }
jobs = {}

def _pose_worker(job_id, video_path, session_id):
    """
    Background worker to run the pose pipeline.
    """
    logger.info(f"[{job_id}] Worker started for session {session_id}")
    jobs[job_id] = {"status": "processing", "result": None, "error": None}

    try:
        # Run the full pose pipeline
        result = run_pose_pipeline(video_path, session_id)
        jobs[job_id]["status"] = "done"
        jobs[job_id]["result"] = result
        logger.info(f"[{job_id}] Pipeline completed successfully")
    except Exception as e:
        logger.error(f"[{job_id}] Pipeline failed: {e}")
        jobs[job_id]["status"] = "error"
        jobs[job_id]["error"] = str(e)
    finally:
        # Clean up temporary file
        if os.path.exists(video_path):
            os.remove(video_path)
            logger.info(f"[{session_id}] Cleaned up temp file: {video_path}")

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
    logger.info(f"[{session_id}] Upload received. Spawning background worker.")

    # Create job
    job_id = str(uuid.uuid4())
    jobs[job_id] = {"status": "processing", "result": None, "error": None}

    # Spawn background thread
    thread = threading.Thread(target=_pose_worker, args=(job_id, tmp_path, session_id))
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
