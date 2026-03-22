import logging
from evaluation.input_validator import validate_inputs
from evaluation.score_fusion import fuse_scores
from evaluation.db_handler import fetch_baseline, write_session, update_session_result
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

    # 1. Validate inputs
    valid, err = validate_inputs(pose_data, audio_data)
    if not valid:
        logger.error(f"Input validation failed: {err}")
        raise ValueError(err)

    # 2. Fuse scores
    scores = fuse_scores(pose_data, audio_data)

    # 3. Fetch history (handle manual is_first_session override)
    baseline = None
    if not metadata.get("is_first_session", False):
        baseline = fetch_baseline(user_id)

    # 4. Compute deltas
    current_behavioral = {
        "filler_ratio": audio_data["acoustic_metrics"]["filler_ratio"],
        "pause_ratio": audio_data["acoustic_metrics"]["pause_ratio"],
        "posture_stability_index": pose_data["derived_pose_attributes"]["posture_stability_index"]
    }
    progress = compute_deltas({**scores, **current_behavioral}, baseline)

    # 5. WRITE TO DB (Initial write with scores and metadata)
    write_session(user_id, scores, pose_data, audio_data, metadata)

    # 6. Assemble final read-only JSON package
    final_json = build_evaluation_json(scores, progress, audio_data, pose_data, user_id, metadata)

    # 7. LLM interpretation
    feedback = interpret_with_llm(final_json)

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
