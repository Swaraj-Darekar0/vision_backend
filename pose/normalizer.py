import numpy as np
import logging
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

# Landmark index constants from MediaPipe
LEFT_HIP = 23
RIGHT_HIP = 24
LEFT_SHOULDER = 11
RIGHT_SHOULDER = 12

from pose.smoother import OneEuroFilter

def normalize_landmarks(landmarks_data: List[Dict], smoother: Optional[OneEuroFilter] = None) -> List[Dict]:
    """
    Translates landmarks to hip-midpoint and scales by torso length.
    Optionally applies smoothing before normalization.
    Source: master_formula.md Section 2.1.
    
    Args:
        landmarks_data: List of dicts with 'landmarks' (33,4), 'timestamp', 'valid'.
        smoother: Optional OneEuroFilter instance.
        
    Returns:
        List of dicts: { "landmarks_norm": np.ndarray (33,4), "timestamp": float, "valid": bool }
    """
    normalized_list = []
    
    for item in landmarks_data:
        landmarks = item["landmarks"]
        timestamp = item["timestamp"]
        valid = item["valid"]
        
        # Pass invalid frames through unchanged
        if not valid:
            normalized_list.append({
                "landmarks_norm": landmarks,
                "timestamp": timestamp,
                "valid": False
            })
            continue
            
        try:
            # 0. Apply Smoothing (One Euro Filter)
            if smoother:
                landmarks = smoother(landmarks, timestamp)

            # 1. Translation: center coordinate system at the midpoint between the hips
            left_hip_pos = landmarks[LEFT_HIP, :3]
            right_hip_pos = landmarks[RIGHT_HIP, :3]
            hip_mid = (left_hip_pos + right_hip_pos) / 2.0
            
            # 2. Scaling: scale by torso length (shoulder-mid to hip-mid)
            left_shoulder_pos = landmarks[LEFT_SHOULDER, :3]
            right_shoulder_pos = landmarks[RIGHT_SHOULDER, :3]
            shoulder_mid = (left_shoulder_pos + right_shoulder_pos) / 2.0
            
            # Compute Euclidean distance (torso length)
            torso_length = np.linalg.norm(shoulder_mid - hip_mid)
            
            if torso_length <= 0:
                logger.warning(f"Torso length is zero at t={timestamp}. Marking frame invalid.")
                normalized_list.append({
                    "landmarks_norm": landmarks,
                    "timestamp": timestamp,
                    "valid": False
                })
                continue
            
            # Apply normalization: (K_i - hip_mid) / torso_length
            # Only affect X, Y, Z columns (0, 1, 2). Visibility (3) remains unchanged.
            normalized_k = landmarks.copy()
            normalized_k[:, :3] = (landmarks[:, :3] - hip_mid) / torso_length
            
            normalized_list.append({
                "landmarks_norm": normalized_k,
                "timestamp": timestamp,
                "valid": True
            })
            
        except Exception as e:
            logger.error(f"Normalization failed at t={timestamp}: {e}")
            normalized_list.append({
                "landmarks_norm": landmarks,
                "timestamp": timestamp,
                "valid": False
            })
            
    logger.info(f"Normalized {len(landmarks_data)} landmark sets")
    return normalized_list
