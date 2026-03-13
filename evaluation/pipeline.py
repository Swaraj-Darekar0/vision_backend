import logging
from evaluation.input_validator import validate_inputs
from evaluation.score_fusion import fuse_scores
from evaluation.db_handler import fetch_baseline, write_session
from evaluation.delta_engine import compute_deltas
from evaluation.json_builder import build_evaluation_json
from evaluation.llm_interpreter import interpret_with_llm

logger = logging.getLogger(__name__)

def run_evaluation_pipeline(pose_data: dict, audio_data: dict, user_id: str) -> dict:
    """
    Critical orchestrator for the Final Evaluation Engine.
    Enforces mandatory sequence of fusion, baseline, deltas, DB write, and LLM.
    Source: backend_SKILL.md Section 6 (evaluation/pipeline.py).
    
    Args:
        pose_data: Full JSON output from Pose Pipeline.
        audio_data: Full JSON output from Audio Pipeline.
        user_id: Unique user identifier for history lookup.
        
    Returns:
        Dict: Final evaluation package with coaching feedback.
    """
    logger.info(f"Starting Evaluation Pipeline for user: {user_id}")

    # 1. Validate inputs — reject early if fields are missing
    valid, err = validate_inputs(pose_data, audio_data)
    if not valid:
        logger.error(f"Input validation failed: {err}")
        raise ValueError(err)

    # 2. Fuse scores from both pipelines (Pose behavioral + Audio behavioral)
    scores = fuse_scores(pose_data, audio_data)

    # 3. Fetch history BEFORE writing (diff against prior session)
    baseline = fetch_baseline(user_id)

    # 4. Compute deltas and classifications
    # Inject raw behavioral metrics needed for delta engine
    current_behavioral = {
        "filler_ratio": audio_data["acoustic_metrics"]["filler_ratio"],
        "pause_ratio": audio_data["acoustic_metrics"]["pause_ratio"],
        "posture_stability_index": pose_data["derived_pose_attributes"]["posture_stability_index"]
    }
    progress = compute_deltas({**scores, **current_behavioral}, baseline)

    # 5. WRITE TO DB — must happen before LLM call
    # If LLM fails, scores are still saved.
    db_success = write_session(user_id, scores, pose_data, audio_data)
    if not db_success:
        logger.warning(f"Failed to write session results to database for user {user_id}")

    # 6. Assemble final read-only JSON package
    final_json = build_evaluation_json(scores, progress, audio_data, pose_data, user_id)

    # 7. LLM interpretation — read-only, always last
    feedback = interpret_with_llm(final_json)


    # Combine all into final response
    result = {
        **final_json,
        "llm_feedback": feedback
    }

    logger.info(f"Evaluation Pipeline completed successfully for user {user_id}")
    return result
