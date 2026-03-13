import numpy as np
import scipy.signal as signal
import logging
from typing import List, Dict
import config

logger = logging.getLogger(__name__)

# Landmark index constants
NOSE = 0
LEFT_SHOULDER = 11
RIGHT_SHOULDER = 12
LEFT_ELBOW = 13
RIGHT_ELBOW = 14
LEFT_WRIST = 15
RIGHT_WRIST = 16
LEFT_HIP = 23
RIGHT_HIP = 24
LEFT_KNEE = 25
RIGHT_KNEE = 26
LEFT_ANKLE = 27
RIGHT_ANKLE = 28

def compute_shoulder_alignment(landmarks: np.ndarray) -> float:
    """
    Measures horizontal shoulder levelness. 1.0 is perfectly aligned.
    Source: master_formula.md Section 2.2.
    """
    left_y = landmarks[LEFT_SHOULDER, 1]
    right_y = landmarks[RIGHT_SHOULDER, 1]
    diff = abs(left_y - right_y)
    score = 1.0 - diff
    return float(np.clip(score, 0.0, 1.0))

def compute_spine_straightness(landmarks: np.ndarray) -> float:
    """
    Measures vertical torso alignment. 1.0 is perfectly straight.
    Source: master_formula.md Section 2.2.
    """
    shoulder_mid = (landmarks[LEFT_SHOULDER, :3] + landmarks[RIGHT_SHOULDER, :3]) / 2.0
    hip_mid = (landmarks[LEFT_HIP, :3] + landmarks[RIGHT_HIP, :3]) / 2.0
    
    spine_vec = shoulder_mid - hip_mid
    vertical = np.array([0, -1, 0]) # Y is down in MediaPipe, so -1 is up
    
    norm_spine = np.linalg.norm(spine_vec)
    if norm_spine == 0:
        return 0.0
        
    cos_theta = np.dot(spine_vec, vertical) / norm_spine
    angle = np.arccos(np.clip(cos_theta, -1.0, 1.0))
    
    # Angle deviation from vertical
    score = 1.0 - (angle / config.SPINE_STRAIGHTNESS_THRESHOLD)
    return float(np.clip(score, 0.0, 1.0))

def compute_posture_openness(landmarks: np.ndarray) -> float:
    """
    Measures how open/expansive the stance is.
    Source: master_formula.md Section 2.2.
    """
    left_x = landmarks[LEFT_SHOULDER, 0]
    right_x = landmarks[RIGHT_SHOULDER, 0]
    width = abs(left_x - right_x)
    
    score = width / config.POSTURE_OPENNESS_MAX_WIDTH
    return float(np.clip(score, 0.0, 1.0))

def compute_head_stability(window_landmarks: List[np.ndarray]) -> float:
    """
    Detects excessive head nodding or twitching across a window.
    Source: master_formula.md Section 2.2.
    """
    if not window_landmarks:
        return 0.0
        
    z_coords = [lm[NOSE, 2] for lm in window_landmarks]
    std_z = np.std(z_coords)
    
    score = 1.0 - (std_z / config.HEAD_STABILITY_THRESHOLD)
    return float(np.clip(score, 0.0, 1.0))

def compute_body_sway(window_landmarks: List[np.ndarray]) -> float:
    """
    Measures lateral center-of-mass shifting across a window.
    Applies a dead zone to ignore micro-sways.
    Source: master_formula.md Section 2.2.
    """
    if not window_landmarks:
        return 0.0
        
    # Using hip midpoint X for sway
    x_coords = [(lm[LEFT_HIP, 0] + lm[RIGHT_HIP, 0]) / 2.0 for lm in window_landmarks]
    std_x = np.std(x_coords)
    
    # Dead Zone Logic: If movement is within natural limits, ignore it.
    if std_x < config.SWAY_DEAD_ZONE:
        return 1.0
    
    score = 1.0 - (std_x / config.BODY_SWAY_THRESHOLD)
    return float(np.clip(score, 0.0, 1.0))

def compute_gesture_score(landmarks: np.ndarray) -> float:
    """
    Measures hand activity level. Placeholder logic for MV.
    """
    # Simply measuring hand distance from hips for now as a proxy
    left_hand_dist = np.linalg.norm(landmarks[LEFT_WRIST, :3] - landmarks[LEFT_HIP, :3])
    right_hand_dist = np.linalg.norm(landmarks[RIGHT_WRIST, :3] - landmarks[RIGHT_HIP, :3])
    
    mean_dist = (left_hand_dist + right_hand_dist) / 2.0
    # Normalize by some arbitrary expected range if not in formula
    score = mean_dist / 0.5 
    return float(np.clip(score, 0.0, 1.0))

def compute_amplitude_score(landmarks: np.ndarray) -> float:
    """
    Measures max wrist displacement from neutral.
    Source: backend_implementation_plan.md Phase 5.
    """
    left_y = landmarks[LEFT_WRIST, 1]
    right_y = landmarks[RIGHT_WRIST, 1]
    
    # Higher up (lower Y) means higher amplitude in MediaPipe
    # Neutral is around shoulder height
    shoulder_y = (landmarks[LEFT_SHOULDER, 1] + landmarks[RIGHT_SHOULDER, 1]) / 2.0
    
    left_amp = max(0, shoulder_y - left_y)
    right_amp = max(0, shoulder_y - right_y)
    
    max_amp = max(left_amp, right_amp)
    score = max_amp / config.OPTIMAL_HAND_AMPLITUDE
    return float(np.clip(score, 0.0, 1.0))

def compute_symmetry_score(landmarks: np.ndarray) -> float:
    """
    Compares motion energy of left vs right wrist.
    Source: backend_implementation_plan.md Phase 5.
    """
    left_wrist = landmarks[LEFT_WRIST, :3]
    right_wrist = landmarks[RIGHT_WRIST, :3]
    
    # Static frame symmetry (distance from vertical axis)
    shoulder_mid_x = (landmarks[LEFT_SHOULDER, 0] + landmarks[RIGHT_SHOULDER, 0]) / 2.0
    
    left_dist = abs(left_wrist[0] - shoulder_mid_x)
    right_dist = abs(right_wrist[0] - shoulder_mid_x)
    
    diff = abs(left_dist - right_dist)
    score = 1.0 - diff
    return float(np.clip(score, 0.0, 1.0))

def compute_fidget_score(window_landmarks: List[np.ndarray]) -> float:
    """
    Extracts high-frequency residual energy from wrist motion.
    Source: backend_implementation_plan.md Phase 5.
    """
    if len(window_landmarks) < 5:
        return 0.0
        
    # Extract left wrist Y sequence
    y_coords = np.array([lm[LEFT_WRIST, 1] for lm in window_landmarks])
    
    # High-pass filter to get "jitter" or "fidget"
    # Placeholder: use standard deviation of differences as simple high-freq measure
    diffs = np.diff(y_coords)
    fidget_val = np.std(diffs)
    
    score = fidget_val / config.FIDGET_THRESHOLD
    return float(np.clip(score, 0.0, 1.0))

def compute_stillness_score(landmarks: np.ndarray) -> float:
    """
    Count frames where total joint displacement is below stillness threshold.
    Source: backend_implementation_plan.md Phase 5.
    """
    # In a single frame, stillness is better measured by lack of deviation from neutral
    # Proxy: lower overall joint displacement from spine axis
    joints = [LEFT_ELBOW, RIGHT_ELBOW, LEFT_WRIST, RIGHT_WRIST]
    shoulder_mid = (landmarks[LEFT_SHOULDER, :3] + landmarks[RIGHT_SHOULDER, :3]) / 2.0
    hip_mid = (landmarks[LEFT_HIP, :3] + landmarks[RIGHT_HIP, :3]) / 2.0
    
    total_dist = 0.0
    for j in joints:
        # Distance to spine vector
        pos = landmarks[j, :3]
        dist = np.linalg.norm(np.cross(shoulder_mid - hip_mid, pos - hip_mid)) / np.linalg.norm(shoulder_mid - hip_mid)
        total_dist += dist
        
    mean_dist = total_dist / len(joints)
    # Lower distance = more still/contained
    score = 1.0 - (mean_dist / 0.5)
    return float(np.clip(score, 0.0, 1.0))

def compute_all_metrics(normalized_data: List[Dict]) -> List[Dict]:
    """
    Dispatcher to compute all 10 metrics for each frame.
    Handles rolling windows for stability metrics.
    """
    results = []
    window_size = 30 # roughly 1 second at 30 FPS
    
    for i, item in enumerate(normalized_data):
        timestamp = item["timestamp"]
        landmarks = item["landmarks_norm"]
        valid = item["valid"]
        
        if not valid:
            results.append({"timestamp": timestamp, "valid": False})
            continue
            
        # Get rolling window for window-dependent metrics
        start_idx = max(0, i - window_size)
        window = [d["landmarks_norm"] for d in normalized_data[start_idx:i+1] if d["valid"]]
        
        try:
            frame_scores = {
                "timestamp": timestamp,
                "valid": True,
                "shoulder_alignment": compute_shoulder_alignment(landmarks),
                "spine_straightness": compute_spine_straightness(landmarks),
                "posture_openness": compute_posture_openness(landmarks),
                "head_stability": compute_head_stability(window),
                "body_sway": compute_body_sway(window),
                "gesture_score": compute_gesture_score(landmarks),
                "amplitude_score": compute_amplitude_score(landmarks),
                "symmetry_score": compute_symmetry_score(landmarks),
                "fidget_score": compute_fidget_score(window),
                "stillness_score": compute_stillness_score(landmarks)
            }
            results.append(frame_scores)
        except Exception as e:
            logger.error(f"Metric computation failed at t={timestamp}: {e}")
            results.append({"timestamp": timestamp, "valid": False})
            
    return results
