import logging
from pose.frame_extractor import extract_frames
from pose.landmark_extractor import extract_landmarks
from pose.normalizer import normalize_landmarks
from pose.metrics import compute_all_metrics
from pose.aggregator import aggregate_windows, aggregate_session
from pose.derived_attributes import compute_all_derived
from pose.json_builder import build_pose_json
from pose.smoother import OneEuroFilter
import config

logger = logging.getLogger(__name__)

def run_pose_pipeline(video_path: str, session_id: str) -> dict:
    """
    Orchestrator for the entire Pose (Video) Pipeline.
    Calls stages in order. No math or threshold comparisons here.
    Source: backend_SKILL.md Section 6.
    
    Args:
        video_path: Path to the uploaded MP4 video.
        session_id: Unique session identifier.
        
    Returns:
        Final Pose JSON response dictionary.
    """
    logger.info(f"[{session_id}] Starting Pose Pipeline for: {video_path}")
    
    # Initialize smoother (local to this pipeline run)
    smoother = OneEuroFilter(
        min_cutoff=config.POSE_SMOOTHING_MIN_CUTOFF,
        beta=config.POSE_SMOOTHING_BETA,
        d_cutoff=config.POSE_SMOOTHING_D_CUTOFF
    )
    
    # 1. Frame Extraction
    frames = extract_frames(video_path)
    
    # 2. Landmark Extraction
    landmarks = extract_landmarks(frames)
    
    # 3. Normalization (with smoothing)
    normalized = normalize_landmarks(landmarks, smoother)
    
    # 4. Metric Computation
    frame_metrics = compute_all_metrics(normalized)
    
    # 5. Aggregation
    window_scores = aggregate_windows(frame_metrics)
    session_scores = aggregate_session(window_scores)
    
    # 6. Derived Attributes
    derived = compute_all_derived(session_scores)
    
    # 7. JSON Assembly
    result = build_pose_json(session_scores, derived, session_id)
    
    logger.info(f"[{session_id}] Pose Pipeline completed successfully")
    return result
