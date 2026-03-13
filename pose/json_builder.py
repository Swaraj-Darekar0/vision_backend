import logging
from datetime import datetime
from typing import Dict

import config

logger = logging.getLogger(__name__)

def build_pose_json(session_scores: Dict, derived_attributes: Dict, session_id: str) -> Dict:
    """
    Assembles the final Pose JSON object.
    Source: backend_implementation_plan.md Phase 8.
    
    Args:
        session_scores: Dict of 10 posture metrics.
        derived_attributes: Dict of 6 derived attributes.
        session_id: Unique session identifier.
        
    Returns:
        Structured JSON dictionary.
    """
    # 1. Validate scores and generate warnings
    warnings = []
    
    # Sway Thresholding (Stability Warning)
    sway_score = session_scores.get("body_sway", 1.0)
    if sway_score < config.SWAY_WARNING_THRESHOLD:
        warnings.append({
            "type": "STABILITY_WARNING",
            "metric": "body_sway",
            "score": sway_score,
            "message": "High body sway detected. This is a common indicator of nervousness."
        })

    # Overall Stability Warning
    stability_score = derived_attributes.get("posture_stability_index", 1.0)
    if stability_score < config.POSTURE_STABILITY_WARNING:
        warnings.append({
            "type": "POSTURE_WARNING",
            "metric": "posture_stability_index",
            "score": stability_score,
            "message": "Lower overall posture stability. Try to maintain a grounded stance."
        })
            
    # 2. Assemble the blocks
    final_json = {
        "session_metadata": {
            "session_id": session_id,
            "processed_at": datetime.utcnow().isoformat() + "Z",
            "pipeline": "pose-video-v1",
            "warnings": warnings
        },
        "posture_metrics": session_scores,
        "derived_pose_attributes": derived_attributes
    }
    
    logger.info(f"Assembled final Pose JSON for session {session_id} with {len(warnings)} warnings")
    return final_json
