from flask import Blueprint, request, jsonify
from pose.pipeline import run_pose_pipeline
from audio.pipeline import run_audio_pipeline
from evaluation.pipeline import run_evaluation_pipeline
import logging
import uuid
import os
import concurrent.futures

orchestrator_bp = Blueprint("orchestrator", __name__, url_prefix="/analyze")
logger = logging.getLogger(__name__)

@orchestrator_bp.route("/full", methods=["POST"])
def analyze_full():
    """
    POST /analyze/full
    Accepts: video file (mp4), user_id (form data)
    Runs Pose and Audio pipelines in PARALLEL, then Evaluation.
    """
    if "video" not in request.files:
        return jsonify({"error": "No video file provided"}), 400
    
    video_file = request.files["video"]
    user_id = request.form.get("user_id")
    
    if not user_id:
        return jsonify({"error": "Missing user_id"}), 400

    session_id = str(uuid.uuid4())
    tmp_dir = os.path.join(os.getcwd(), "tmp")
    os.makedirs(tmp_dir, exist_ok=True)
    tmp_path = os.path.join(tmp_dir, f"{session_id}.mp4")
    video_file.save(tmp_path)
    
    logger.info(f"[{session_id}] Starting FULL analysis for user {user_id}")
    
    try:
        # 1. Run Pose and Audio pipelines in parallel
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            future_pose = executor.submit(run_pose_pipeline, tmp_path, session_id)
            future_audio = executor.submit(run_audio_pipeline, tmp_path, session_id)
            
            # Wait for both to complete
            pose_result = future_pose.result()
            audio_result = future_audio.result()

        # 2. Run Evaluation pipeline (Synchronous)
        final_result = run_evaluation_pipeline(pose_result, audio_result, user_id)
        
        return jsonify(final_result), 200

    except Exception as e:
        logger.error(f"[{session_id}] Full pipeline failed: {e}")
        return jsonify({"error": "Processing failed", "detail": str(e)}), 500
        
    finally:
        # Cleanup temp video file
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        
        # Cleanup processed audio file if it exists
        processed_audio_path = os.path.join(tmp_dir, f"{session_id}_processed.wav")
        if os.path.exists(processed_audio_path):
            os.remove(processed_audio_path)
            logger.info(f"[{session_id}] Cleaned up processed audio file.")
