import logging
import copy
from evaluation.input_validator import validate_inputs
from evaluation.score_fusion import fuse_scores
from evaluation.db_handler import (
    fetch_baseline,
    write_session,
    update_session_result,
    update_personal_bests,
    update_user_profile_flags,
)
from evaluation.delta_engine import compute_deltas
from evaluation.json_builder import build_evaluation_json
from evaluation.llm_interpreter import interpret_with_llm

logger = logging.getLogger(__name__)

def run_evaluation_pipeline(pose_data: dict, audio_data: dict, user_id: str, metadata: dict = None) -> dict:
    """
    Critical orchestrator for the Final Evaluation Engine.
    """
    logger.info(f"Starting Evaluation Pipeline for user: {user_id}")
    
    if metadata is None:
        metadata = {}

    audio_data = copy.deepcopy(audio_data)
    audio_data.setdefault("derived_audio_attributes", {})
    audio_data["derived_audio_attributes"].setdefault("reasoning_clarity", 1.0)

    # 1. Validate inputs
    valid, err = validate_inputs(pose_data, audio_data)
    if not valid:
        logger.error(f"Input validation failed: {err}")
        raise ValueError(err)

    # 2. Fetch history (handle manual is_first_session override)
    baseline = None
    if not metadata.get("is_first_session", False):
        baseline = fetch_baseline(user_id)

    # 3. Build a provisional package for the final LLM pass.
    provisional_scores = fuse_scores(pose_data, audio_data)
    provisional_behavioral = {
        "filler_ratio": audio_data["acoustic_metrics"]["filler_ratio"],
        "pause_ratio": audio_data["acoustic_metrics"]["pause_ratio"],
        "posture_stability_index": pose_data["derived_pose_attributes"]["posture_stability_index"],
        "reasoning_clarity": audio_data["derived_audio_attributes"].get("reasoning_clarity", 1.0),
    }
    provisional_progress = compute_deltas({**provisional_scores, **provisional_behavioral}, baseline)
    provisional_json = build_evaluation_json(
        provisional_scores, provisional_progress, audio_data, pose_data, user_id, metadata
    )
    feedback = interpret_with_llm(provisional_json)

    # 4. Fold the LLM-derived reasoning clarity back into final fused scoring.
    audio_data["derived_audio_attributes"]["reasoning_clarity"] = feedback.get("reasoning_clarity_score", 1.0)
    scores = fuse_scores(pose_data, audio_data)
    current_behavioral = {
        "filler_ratio": audio_data["acoustic_metrics"]["filler_ratio"],
        "pause_ratio": audio_data["acoustic_metrics"]["pause_ratio"],
        "posture_stability_index": pose_data["derived_pose_attributes"]["posture_stability_index"],
        "reasoning_clarity": audio_data["derived_audio_attributes"]["reasoning_clarity"],
    }
    progress = compute_deltas({**scores, **current_behavioral}, baseline)

    # 5. WRITE TO DB (Initial write with scores and metadata)
    write_session(user_id, scores, pose_data, audio_data, metadata)

    raw_metrics = {
        "posture_stability": pose_data.get("derived_pose_attributes", {}).get("posture_stability_index", 0.0),
        "gesture_score": pose_data.get("posture_metrics", {}).get("gesture_score", 0.0),
        "speech_rate_score": audio_data.get("acoustic_metrics", {}).get("speech_rate_score", 0.0),
        "filler_ratio": audio_data.get("acoustic_metrics", {}).get("filler_ratio", 1.0),
    }

    try:
        update_personal_bests(user_id, scores, raw_metrics)
    except Exception as exc:
        logger.error(f"Personal best update failed for user {user_id}: {exc}")

    try:
        update_user_profile_flags(user_id, metadata)
    except Exception as exc:
        logger.error(f"Diagnostic profile update failed for user {user_id}: {exc}")

    # 6. Assemble final read-only JSON package
    final_json = build_evaluation_json(scores, progress, audio_data, pose_data, user_id, metadata)

    # Combine all into final response
    result = {
        **final_json,
        "llm_feedback": feedback
    }
    
    # 8. UPDATE DB (Save full result for history sync)
    session_id = pose_data.get("session_metadata", {}).get("session_id")
    if session_id:
        update_session_result(session_id, result)

    logger.info(f"Evaluation Pipeline completed successfully for user {user_id}")
    return result
