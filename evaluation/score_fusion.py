import numpy as np
import logging
from typing import Dict
import config

logger = logging.getLogger(__name__)

def fuse_scores(pose_data: Dict, audio_data: Dict) -> Dict:
    """
    Weighted fusion of pose + audio → 4 composite scores + overall.
    Source: backend_SKILL.md Section 6 (evaluation/score_fusion.py).
    
    Args:
        pose_data: Full Pose JSON dictionary.
        audio_data: Full Audio JSON dictionary.
        
    Returns:
        Dict: { "confidence": float, "clarity": float, "engagement": float, 
                "nervousness": float, "overall": float }
    """
    p_derived = pose_data.get("derived_pose_attributes", {})
    a_derived = audio_data.get("derived_audio_attributes", {})
    
    # 1. Confidence Fusion (0.50 Pose, 0.50 Audio)
    w_c = config.CONFIDENCE_FUSION_WEIGHTS
    confidence = (w_c["pose_confidence"] * p_derived.get("pose_confidence", 0.0) +
                  w_c["audio_confidence"] * a_derived.get("audio_confidence", 0.0))
    
    # 2. Clarity Fusion (0.40 PostureStability, 0.60 AudioStability)
    # Note: Clarity is inversely related to instability.
    w_cl = config.CLARITY_FUSION_WEIGHTS
    clarity = (w_cl["posture_stability_index"] * p_derived.get("posture_stability_index", 0.0) +
               w_cl["audio_instability"] * (1.0 - a_derived.get("audio_instability", 0.0)))
               
    # 3. Engagement Fusion (0.50 Pose, 0.50 Audio)
    w_e = config.ENGAGEMENT_FUSION_WEIGHTS
    engagement = (w_e["pose_engagement"] * p_derived.get("pose_engagement", 0.0) +
                  w_e["audio_engagement"] * a_derived.get("audio_engagement", 0.0))
                  
    # 4. Nervousness Fusion (0.50 Pose, 0.50 Audio)
    w_n = config.NERVOUSNESS_FUSION_WEIGHTS
    nervousness = (w_n["pose_nervousness"] * p_derived.get("pose_nervousness", 0.0) +
                   w_n["audio_nervousness"] * a_derived.get("audio_nervousness", 0.0))
                   
    # 5. Overall Fusion (Weighted sum of above four)
    w_o = config.OVERALL_FUSION_WEIGHTS
    # 0.30(Confidence) + 0.30(Clarity) + 0.20(Engagement) + 0.20(Nervousness Inverse)
    overall = (w_o["confidence"] * confidence +
               w_o["clarity"] * clarity +
               w_o["engagement"] * engagement +
               w_o["nervousness"] * (1.0 - nervousness))
               
    output = {
        "confidence": float(np.clip(confidence, 0.0, 1.0)),
        "clarity": float(np.clip(clarity, 0.0, 1.0)),
        "engagement": float(np.clip(engagement, 0.0, 1.0)),
        "nervousness": float(np.clip(nervousness, 0.0, 1.0)),
        "overall": float(np.clip(overall, 0.0, 1.0))
    }
    
    logger.info("Fused scores successfully.")
    return output
