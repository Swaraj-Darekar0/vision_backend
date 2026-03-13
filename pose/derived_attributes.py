import numpy as np
import logging
from typing import Dict
import config

logger = logging.getLogger(__name__)

def compute_posture_stability_index(scores: Dict) -> float:
    """
    Weighted combination of posture alignment and stability.
    Source: master_formula.md Section 2.3.
    """
    w = config.POSTURE_STABILITY_WEIGHTS
    raw = sum(w.get(key, 0.0) * scores.get(key, 0.0) for key in w)
    return float(np.clip(raw, 0.0, 1.0))

def compute_pose_confidence(scores: Dict, stability_index: float) -> float:
    """
    Weighted combination of stability, openness, and symmetry.
    Source: master_formula.md Section 2.3.
    """
    # Gaze stability is a proxy from head stability
    gaze_stability = scores.get("head_stability", 0.0)
    
    w = config.POSE_CONFIDENCE_WEIGHTS
    # w = { "posture_stability_index": 0.40, "posture_openness": 0.30, 
    #       "gaze_stability": 0.20, "symmetry_score": 0.10 }
    
    raw = (w["posture_stability_index"] * stability_index +
           w["posture_openness"] * scores.get("posture_openness", 0.0) +
           w["gaze_stability"] * gaze_stability +
           w["symmetry_score"] * scores.get("symmetry_score", 0.0))
           
    return float(np.clip(raw, 0.0, 1.0))

def compute_pose_nervousness(scores: Dict) -> float:
    """
    Weighted combination of instability, fidgeting, and movement variance.
    Source: master_formula.md Section 2.3.
    """
    # movement_variance_normalized proxy from gesture score or stillness inverse
    movement_var = 1.0 - scores.get("stillness_score", 0.0)
    
    w = config.POSE_NERVOUSNESS_WEIGHTS
    # w = { "head_stability": 0.35, "body_sway": 0.30, 
    #       "fidget_score": 0.20, "movement_variance_normalized": 0.15 }
    
    # Formula uses (1 - stability) in master_formula.md
    head_instab = 1.0 - scores.get("head_stability", 0.0)
    sway_instab = 1.0 - scores.get("body_sway", 0.0)
    
    raw = (w["head_stability"] * head_instab +
           w["body_sway"] * sway_instab +
           w["fidget_score"] * scores.get("fidget_score", 0.0) +
           w["movement_variance_normalized"] * movement_var)
           
    return float(np.clip(raw, 0.0, 1.0))

def compute_pose_engagement(scores: Dict) -> float:
    """
    Weighted combination of gesture activity and openness.
    Source: master_formula.md Section 2.3 (derived).
    """
    w = config.POSE_ENGAGEMENT_WEIGHTS
    # w = { "gesture_score": 0.40, "amplitude_score": 0.30, "posture_openness": 0.30 }
    
    raw = (w["gesture_score"] * scores.get("gesture_score", 0.0) +
           w["amplitude_score"] * scores.get("amplitude_score", 0.0) +
           w["posture_openness"] * scores.get("posture_openness", 0.0))
           
    return float(np.clip(raw, 0.0, 1.0))

def compute_all_derived(session_scores: Dict) -> Dict:
    """
    Dispatcher to compute all 6 derived behavioral attributes.
    """
    stability = compute_posture_stability_index(session_scores)
    
    derived = {
        "posture_stability_index": stability,
        "pose_confidence": compute_pose_confidence(session_scores, stability),
        "pose_nervousness": compute_pose_nervousness(session_scores),
        "pose_engagement": compute_pose_engagement(session_scores),
        "movement_variance_normalized": 1.0 - session_scores.get("stillness_score", 0.0),
        "gaze_stability": session_scores.get("head_stability", 0.0)
    }
    
    logger.info("Computed all derived attributes")
    return derived
