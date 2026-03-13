from flask import Blueprint, request, jsonify
from audio.pipeline import run_audio_pipeline
import uuid
import os
import logging

audio_bp = Blueprint("audio", __name__, url_prefix="/audio")
logger = logging.getLogger(__name__)

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
    logger.info(f"[{session_id}] Starting audio analysis for: {file.filename}")

    try:
        # Run the full audio pipeline
        result = run_audio_pipeline(tmp_path, session_id)
        return jsonify(result), 200
    except Exception as e:
        logger.error(f"[{session_id}] Audio pipeline failed: {e}")
        return jsonify({
            "error": "Audio processing failed",
            "detail": str(e)
        }), 500
    finally:
        # Clean up temporary file
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
            logger.info(f"[{session_id}] Cleaned up temp file.")
        # Also clean up the processed wav from preprocessor
        processed_path = f"tmp/{session_id}_processed.wav"
        if os.path.exists(processed_path):
            os.remove(processed_path)
