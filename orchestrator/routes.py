from flask import Blueprint, request, jsonify
from pose.pipeline import run_pose_pipeline
from audio.pipeline import run_audio_pipeline
from evaluation.pipeline import run_evaluation_pipeline
import logging
import uuid
import os
import concurrent.futures
import threading
import json
import config

orchestrator_bp = Blueprint("orchestrator", __name__, url_prefix="/analyze")
logger = logging.getLogger(__name__)

# In-memory store: { job_id -> { "status": str, "result": dict, "error": str } }
jobs = {}


def _parse_optional_int(value):
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_optional_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() == "true"

def _orchestrator_worker(job_id, landmark_payload, audio_path, user_id, session_id, metadata):
    """
    Background worker to run the full orchestrator pipeline.
    """
    logger.info(f"[{job_id}] Worker started for session {session_id}")
    jobs[job_id] = {"status": "processing", "result": None, "error": None}

    try:
        topic_title = metadata.get("topic_title", "Untitled Session")
        
        # 1. Run Pose and Audio pipelines in parallel
        # Note: ThreadPoolExecutor runs in the same process, so global variables are shared.
        # Ensure pipelines are stateless as per Law 3.
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            future_pose = executor.submit(run_pose_pipeline, landmark_payload, session_id)
            future_audio = executor.submit(run_audio_pipeline, audio_path, session_id, topic_title)
            
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
        # Cleanup temp audio file
        if os.path.exists(audio_path):
            os.remove(audio_path)
            logger.info(f"[{session_id}] Cleaned up temp audio file.")
        
        for generated_name in (
            f"{session_id}_processed.wav",
            f"{session_id}_transcription.{config.AUDIO_TRANSCRIPTION_FORMAT}",
        ):
            generated_path = os.path.join(os.path.dirname(audio_path), generated_name)
            if os.path.exists(generated_path):
                os.remove(generated_path)
                logger.info(f"[{session_id}] Cleaned up generated audio file: {generated_name}")

@orchestrator_bp.route("/full", methods=["POST"])
def analyze_full():
    """
    POST /analyze/full
    Accepts: pose_landmarks (json file), audio (audio file), user_id, topic_title, 
             duration_label, is_first_session (form data)
             
    Runs Pose and Audio pipelines in PARALLEL, then Evaluation.
    """
    if "pose_landmarks" not in request.files:
        return jsonify({"error": "Missing field: pose_landmarks"}), 400
    if "audio" not in request.files:
        return jsonify({"error": "Missing field: audio"}), 400
    
    user_id = request.form.get("user_id")
    if not user_id:
        return jsonify({"error": "Missing user_id"}), 400

    session_id = request.form.get("session_id", str(uuid.uuid4()))
    landmark_file = request.files["pose_landmarks"]
    audio_file = request.files["audio"]

    try:
        landmark_payload = json.loads(landmark_file.read().decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return jsonify({"error": "Invalid landmark JSON"}), 400

    # Save audio to temp file
    tmp_dir = os.path.join(os.getcwd(), "tmp")
    os.makedirs(tmp_dir, exist_ok=True)
    # Try to keep original extension if possible, default to wav
    audio_ext = audio_file.filename.split('.')[-1] if '.' in audio_file.filename else "wav"
    audio_path = os.path.join(tmp_dir, f"{session_id}.{audio_ext}")
    audio_file.save(audio_path)

    # Extract metadata for history sync
    metadata = {
        "topic_title": request.form.get("topic_title", "Untitled Session"),
        "duration_label": request.form.get("duration_label", "--"),
        "is_first_session": _parse_optional_bool(request.form.get("is_first_session", "false")),
        "week_number": _parse_optional_int(request.form.get("week_number")),
        "plan_day": _parse_optional_int(request.form.get("plan_day")),
        "plan_session_num": _parse_optional_int(request.form.get("plan_session_num")),
        "is_recovery": _parse_optional_bool(request.form.get("is_recovery", "false")),
        "target_skill": request.form.get("target_skill"),
        "is_diagnostic": _parse_optional_bool(request.form.get("is_diagnostic", "false")),
        "speaker_level": request.form.get("speaker_level"),
    }

    logger.info(f"[{session_id}] Full analysis request received. Spawning background worker.")

    # Create job
    job_id = str(uuid.uuid4())
    jobs[job_id] = {"status": "processing", "result": None, "error": None}

    # Spawn background thread
    thread = threading.Thread(target=_orchestrator_worker, args=(job_id, landmark_payload, audio_path, user_id, session_id, metadata))
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
