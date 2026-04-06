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


def _error_response(
    code: str,
    message: str,
    status_code: int,
    *,
    details: dict | None = None,
    fallback_used: bool = False,
):
    payload = {
        "error": {
            "code": code,
            "message": message,
            "details": details or {},
            "fallback_used": fallback_used,
        }
    }
    return jsonify(payload), status_code


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

def _load_json_payload(field_name: str):
    if field_name in request.files:
        raw_bytes = request.files[field_name].read()
        return json.loads(raw_bytes.decode("utf-8"))

    raw_value = request.form.get(field_name)
    if raw_value:
        return json.loads(raw_value)

    return None


def _normalized_extension(filename: str) -> str:
    ext = os.path.splitext(filename or "")[1].lower().lstrip(".")
    return ext or "wav"


def _orchestrator_worker(job_id, pose_input, audio_path, user_id, session_id, metadata, acoustic_payload, use_device_pose):
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
            if use_device_pose:
                future_pose = executor.submit(_prepare_device_pose_json, pose_input, session_id)
            else:
                future_pose = executor.submit(run_pose_pipeline, pose_input, session_id)
            future_audio = executor.submit(run_audio_pipeline, audio_path, session_id, topic_title, acoustic_payload)
            
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
    Accepts: pose_json OR pose_landmarks (json file), audio (audio file), optional audio_acoustic_json, user_id, topic_title, 
             duration_label, is_first_session (form data)
             
    Runs Pose and Audio pipelines in PARALLEL, then Evaluation.
    """
    if "audio" not in request.files:
        return _error_response("MISSING_AUDIO", "Missing field: audio", 400, details={"field": "audio"})
    
    user_id = request.form.get("user_id")
    if not user_id:
        return _error_response("MISSING_USER_ID", "Missing user_id", 400, details={"field": "user_id"})

    session_id = request.form.get("session_id", str(uuid.uuid4()))
    audio_file = request.files["audio"]
    use_device_pose = False

    try:
        pose_payload = _load_json_payload("pose_json")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return _error_response("INVALID_POSE_JSON", "Invalid pose_json payload", 400, details={"field": "pose_json"})

    if pose_payload is not None:
        use_device_pose = True
    else:
        try:
            pose_payload = _load_json_payload("pose_landmarks")
        except (json.JSONDecodeError, UnicodeDecodeError):
            return _error_response(
                "INVALID_POSE_LANDMARKS",
                "Invalid pose_landmarks payload",
                400,
                details={"field": "pose_landmarks"},
            )
        if pose_payload is None:
            return _error_response(
                "MISSING_POSE_INPUT",
                "Missing field: pose_json or pose_landmarks",
                400,
                details={"fields": ["pose_json", "pose_landmarks"]},
            )

    try:
        acoustic_payload = _load_json_payload("audio_acoustic_json") or {}
    except (json.JSONDecodeError, UnicodeDecodeError):
        return _error_response(
            "INVALID_AUDIO_ACOUSTIC_JSON",
            "Invalid audio_acoustic_json payload",
            400,
            details={"field": "audio_acoustic_json"},
        )

    audio_ext = _normalized_extension(audio_file.filename)
    if acoustic_payload.get("acoustic_metrics") and audio_ext in {"mp4", "mov", "m4v"}:
        return _error_response(
            "INVALID_AUDIO_ARTIFACT",
            "New device-offload requests must upload a compressed audio artifact such as mp3, not a video container.",
            400,
            details={
                "field": "audio",
                "received_extension": audio_ext,
                "expected_extensions": ["mp3", "m4a", "aac", "wav"],
            },
        )

    # Save audio to temp file
    tmp_dir = os.path.join(os.getcwd(), "tmp")
    os.makedirs(tmp_dir, exist_ok=True)
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
        "fallbacks_used": _determine_fallbacks(use_device_pose, acoustic_payload),
    }

    logger.info(f"[{session_id}] Full analysis request received. Spawning background worker.")

    # Create job
    job_id = str(uuid.uuid4())
    jobs[job_id] = {"status": "processing", "result": None, "error": None}

    # Spawn background thread
    thread = threading.Thread(
        target=_orchestrator_worker,
        args=(job_id, pose_payload, audio_path, user_id, session_id, metadata, acoustic_payload, use_device_pose),
    )
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


def _prepare_device_pose_json(pose_payload: dict, fallback_session_id: str) -> dict:
    if not isinstance(pose_payload, dict):
        raise ValueError("pose_json must be a JSON object")

    posture_metrics = pose_payload.get("posture_metrics")
    derived_pose_attributes = pose_payload.get("derived_pose_attributes")
    if not isinstance(posture_metrics, dict) or not isinstance(derived_pose_attributes, dict):
        raise ValueError("pose_json must contain posture_metrics and derived_pose_attributes objects")

    session_metadata = dict(pose_payload.get("session_metadata") or {})
    session_metadata.setdefault("session_id", fallback_session_id)
    session_metadata.setdefault("pipeline", "pose-device-v1")
    pose_payload["session_metadata"] = session_metadata
    return pose_payload


def _determine_fallbacks(use_device_pose: bool, acoustic_payload: dict) -> list[str]:
    fallbacks_used = []
    if not use_device_pose:
        fallbacks_used.append("legacy_backend_pose_compute")
    if not acoustic_payload.get("acoustic_metrics"):
        fallbacks_used.append("legacy_backend_audio_compute")
    return fallbacks_used
