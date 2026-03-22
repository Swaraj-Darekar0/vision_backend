from flask import Blueprint, request, jsonify
from pose.pipeline import run_pose_pipeline
from audio.pipeline import run_audio_pipeline
from evaluation.pipeline import run_evaluation_pipeline
import logging
import uuid
import os
import concurrent.futures
import threading

orchestrator_bp = Blueprint("orchestrator", __name__, url_prefix="/analyze")
logger = logging.getLogger(__name__)

# In-memory store: { job_id -> { "status": str, "result": dict, "error": str } }
jobs = {}

def _orchestrator_worker(job_id, video_path, user_id, session_id, metadata):
    """
    Background worker to run the full orchestrator pipeline.
    """
    logger.info(f"[{job_id}] Worker started for session {session_id}")
    jobs[job_id] = {"status": "processing", "result": None, "error": None}

    try:
        # 1. Run Pose and Audio pipelines in parallel
        # Note: ThreadPoolExecutor runs in the same process, so global variables are shared.
        # Ensure pipelines are stateless as per Law 3.
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            future_pose = executor.submit(run_pose_pipeline, video_path, session_id)
            future_audio = executor.submit(run_audio_pipeline, video_path, session_id)
            
            # Wait for both to complete
            pose_result = future_pose.result()
            audio_result = future_audio.result()

        # 2. Run Evaluation pipeline (Synchronous)
        final_result = run_evaluation_pipeline(pose_result, audio_result, user_id, metadata)
        
        jobs[job_id]["status"] = "done"
        jobs[job_id]["result"] = final_result
        logger.info(f"[{job_id}] Full pipeline completed successfully")

    except Exception as e:
        logger.error(f"[{job_id}] Full pipeline failed: {e}")
        jobs[job_id]["status"] = "error"
        jobs[job_id]["error"] = str(e)
        
    finally:
        # Cleanup temp video file
        if os.path.exists(video_path):
            os.remove(video_path)
            logger.info(f"[{session_id}] Cleaned up temp video file.")
        
        # Cleanup processed audio file if it exists (created by audio pipeline)
        # Assuming audio pipeline logic: tmp/{session_id}_processed.wav
        processed_audio_path = os.path.join(os.path.dirname(video_path), f"{session_id}_processed.wav")
        if os.path.exists(processed_audio_path):
            os.remove(processed_audio_path)
            logger.info(f"[{session_id}] Cleaned up processed audio file.")

@orchestrator_bp.route("/full", methods=["POST"])
def analyze_full():
    """
    POST /analyze/full
    Accepts: video file (mp4), user_id, topic_title, duration_label, is_first_session (form data)
    Runs Pose and Audio pipelines in PARALLEL, then Evaluation.
    """
    if "video" not in request.files:
        return jsonify({"error": "No video file provided"}), 400
    
    video_file = request.files["video"]
    user_id = request.form.get("user_id")
    
    if not user_id:
        return jsonify({"error": "Missing user_id"}), 400

    # Extract metadata for history sync
    metadata = {
        "topic_title": request.form.get("topic_title", "Untitled Session"),
        "duration_label": request.form.get("duration_label", "--"),
        "is_first_session": request.form.get("is_first_session", "false").lower() == "true"
    }

    session_id = str(uuid.uuid4())
    tmp_dir = os.path.join(os.getcwd(), "tmp")
    os.makedirs(tmp_dir, exist_ok=True)
    tmp_path = os.path.join(tmp_dir, f"{session_id}.mp4")
    video_file.save(tmp_path)
    
    logger.info(f"[{session_id}] Upload received. Spawning background worker for FULL analysis.")

    # Create job
    job_id = str(uuid.uuid4())
    jobs[job_id] = {"status": "processing", "result": None, "error": None}

    # Spawn background thread
    thread = threading.Thread(target=_orchestrator_worker, args=(job_id, tmp_path, user_id, session_id, metadata))
    thread.daemon = True
    thread.start()

    return jsonify({"job_id": job_id, "session_id": session_id}), 202

@orchestrator_bp.route("/status/<job_id>", methods=["GET"])
def get_status(job_id):
    """
    GET /analyze/status/<job_id> handler.
    Poll this endpoint to get the result of the background job.
    """
    job = jobs.get(job_id)
    if not job:
        return jsonify({"status": "not_found"}), 404
    
    return jsonify(job), 200
