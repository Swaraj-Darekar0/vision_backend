from flask import Blueprint, request, jsonify
from audio.pipeline import run_audio_pipeline
import uuid
import os
import logging
import threading

audio_bp = Blueprint("audio", __name__, url_prefix="/audio")
logger = logging.getLogger(__name__)

# In-memory store: { job_id -> { "status": str, "result": dict, "error": str } }
jobs = {}

def _audio_worker(job_id, audio_path, session_id):
    """
    Background worker to run the audio pipeline.
    """
    logger.info(f"[{job_id}] Worker started for session {session_id}")
    jobs[job_id] = {"status": "processing", "result": None, "error": None}

    try:
        # Run the full audio pipeline
        result = run_audio_pipeline(audio_path, session_id)
        jobs[job_id]["status"] = "done"
        jobs[job_id]["result"] = result
        logger.info(f"[{job_id}] Pipeline completed successfully")
    except Exception as e:
        logger.error(f"[{job_id}] Audio pipeline failed: {e}")
        jobs[job_id]["status"] = "error"
        jobs[job_id]["error"] = str(e)
    finally:
        # Clean up temporary file
        if os.path.exists(audio_path):
            os.remove(audio_path)
            logger.info(f"[{session_id}] Cleaned up temp file.")
        # Also clean up the processed wav from preprocessor
        # Note: Using hardcoded path structure from original code
        processed_path = f"tmp/{session_id}_processed.wav"
        if os.path.exists(processed_path):
            os.remove(processed_path)

@audio_bp.route("/analyze", methods=["POST"])
def analyze():
    """
    POST /audio/analyze handler.
    Accepts MP4, WAV, or MP3.
    Source: backend_SKILL.md Section 6 (audio/routes.py).
    """
    if "audio" not in request.files:
        return jsonify({"error": "No audio/video file provided"}), 400

    file = request.files["audio"]
    if file.filename == "":
        return jsonify({"error": "Empty filename"}), 400

    session_id = str(uuid.uuid4())
    # Identify extension
    ext = os.path.splitext(file.filename)[1].lower()
    if not ext:
        ext = ".mp4" # Default if unknown
        
    tmp_dir = os.path.join(os.getcwd(), "tmp")
    os.makedirs(tmp_dir, exist_ok=True)
    tmp_path = os.path.join(tmp_dir, f"{session_id}{ext}")
    
    file.save(tmp_path)
    logger.info(f"[{session_id}] Upload received. Spawning background worker for: {file.filename}")

    # Create job
    job_id = str(uuid.uuid4())
    jobs[job_id] = {"status": "processing", "result": None, "error": None}

    # Spawn background thread
    thread = threading.Thread(target=_audio_worker, args=(job_id, tmp_path, session_id))
    thread.daemon = True
    thread.start()

    return jsonify({"job_id": job_id, "session_id": session_id}), 202

@audio_bp.route("/status/<job_id>", methods=["GET"])
def get_status(job_id):
    """
    GET /audio/status/<job_id> handler.
    Poll this endpoint to get the result of the background job.
    """
    job = jobs.get(job_id)
    if not job:
        return jsonify({"status": "not_found"}), 404
    
    return jsonify(job), 200
