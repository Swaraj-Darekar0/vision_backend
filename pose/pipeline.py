import logging
from pose.landmark_parser import parse_landmark_payload
from pose.normalizer import normalize_landmarks
from pose.metrics import compute_all_metrics
from pose.aggregator import aggregate_windows, aggregate_session
from pose.derived_attributes import compute_all_derived
from pose.json_builder import build_pose_json
from pose.smoother import OneEuroFilter
import config

logger = logging.getLogger(__name__)

def run_pose_pipeline(landmark_payload: dict, session_id: str) -> dict:
    """
    Orchestrates the pose analysis pipeline.

    Args:
        landmark_payload: Parsed JSON dict from the 'pose_landmarks' multipart field.
                          Contains 'frames' list with per-frame landmark arrays.
                          Sent by the React Native frontend (BlazePose/TF.js).
        session_id:       UUID string for this session.

    Returns:
        Pose JSON dict (same structure as before — downstream unchanged).

    Pipeline stages:
        landmark_parser     → parse frontend JSON into (33,4) arrays per frame
        normalizer          → hip-anchor translation + torso-length scaling (with smoothing)
        metrics             → 10 posture metric functions
        aggregator          → frame → 5s window → session aggregation
        derived_attributes  → 6 behavioral composite scores
        json_builder        → final pose JSON assembly
    """
    logger.info(f"[{session_id}] Starting Pose Pipeline (Mobile-to-Backend Architecture)")
    
    # Initialize smoother (local to this pipeline run)
    smoother = OneEuroFilter(
        min_cutoff=config.POSE_SMOOTHING_MIN_CUTOFF,
        beta=config.POSE_SMOOTHING_BETA,
        d_cutoff=config.POSE_SMOOTHING_D_CUTOFF
    )
    
    # 1. Parse (replaces frame_extractor + landmark_extractor)
    landmarks = parse_landmark_payload(landmark_payload)
    
    # 2. Normalization (with smoothing)
    normalized = normalize_landmarks(landmarks, smoother)
    
    # 3. Metric Computation
    frame_metrics = compute_all_metrics(normalized)
    
    # 4. Aggregation
    window_scores = aggregate_windows(frame_metrics)
    session_scores = aggregate_session(window_scores)
    
    # 5. Derived Attributes
    derived = compute_all_derived(session_scores)
    
    # 6. JSON Assembly
    result = build_pose_json(session_scores, derived, session_id)
    
    logger.info(f"[{session_id}] Pose Pipeline completed successfully")
    return result
