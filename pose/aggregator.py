import numpy as np
import logging
from typing import List, Dict
import config

logger = logging.getLogger(__name__)

def aggregate_windows(frame_metrics: List[Dict]) -> List[Dict]:
    """
    Groups frames into WINDOW_SIZE_SECONDS windows and computes mean per metric.
    Source: backend_implementation_plan.md Phase 6.
    
    Args:
        frame_metrics: List of per-frame metric dicts.
        
    Returns:
        List of per-window metric means.
    """
    if not frame_metrics:
        return []
        
    window_size = config.WINDOW_SIZE_SECONDS
    window_results = []
    
    # Identify the 10 metrics (excluding metadata keys)
    metric_keys = [
        "shoulder_alignment", "spine_straightness", "posture_openness",
        "head_stability", "body_sway", "gesture_score", "amplitude_score",
        "symmetry_score", "fidget_score", "stillness_score"
    ]
    
    total_duration = frame_metrics[-1]["timestamp"]
    num_windows = int(np.ceil(total_duration / window_size))
    
    for i in range(num_windows):
        start_time = i * window_size
        end_time = (i + 1) * window_size
        
        # Filter frames within this window
        window_frames = [
            f for f in frame_metrics 
            if start_time <= f["timestamp"] < end_time and f.get("valid", False)
        ]
        
        if not window_frames:
            continue
            
        window_dict = {
            "time_start": float(start_time),
            "time_end": float(end_time),
            "window_index": i
        }
        
        for key in metric_keys:
            values = [f[key] for f in window_frames if key in f]
            if values:
                window_dict[key] = float(np.mean(values))
            else:
                window_dict[key] = 0.0
                
        window_results.append(window_dict)
        
    logger.info(f"Aggregated {len(frame_metrics)} frames into {len(window_results)} windows")
    return window_results

def aggregate_session(window_scores: List[Dict]) -> Dict:
    """
    Means each metric across all windows to produce 10-key session dict.
    Source: backend_implementation_plan.md Phase 6.
    
    Args:
        window_scores: List of per-window metric means.
        
    Returns:
        Dict of session-level metric means.
    """
    if not window_scores:
        return {}
        
    metric_keys = [
        "shoulder_alignment", "spine_straightness", "posture_openness",
        "head_stability", "body_sway", "gesture_score", "amplitude_score",
        "symmetry_score", "fidget_score", "stillness_score"
    ]
    
    session_dict = {}
    
    for key in metric_keys:
        values = [w[key] for w in window_scores if key in w]
        if values:
            session_dict[key] = float(np.mean(values))
        else:
            session_dict[key] = 0.0
            
    logger.info("Computed session-level aggregation")
    return session_dict
