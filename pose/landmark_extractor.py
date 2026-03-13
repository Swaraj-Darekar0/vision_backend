import numpy as np
import logging
import os
from typing import List, Dict
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision
from config import MIN_VISIBILITY_THRESHOLD, POSE_LANDMARKER_MODEL_PATH

logger = logging.getLogger(__name__)

def extract_landmarks(frames_data: List[Dict]) -> List[Dict]:
    """
    Runs MediaPipe Tasks PoseLandmarker on a list of RGB frames.
    Source: backend_implementation_plan.md Phase 3.
    
    Args:
        frames_data: List of dicts with 'frame' (RGB np.ndarray) and 'timestamp'.
        
    Returns:
        List of dicts: { "landmarks": np.ndarray (33,4), "timestamp": float, "valid": bool }
    """
    if not os.path.exists(POSE_LANDMARKER_MODEL_PATH):
        logger.error(f"Model file not found: {POSE_LANDMARKER_MODEL_PATH}. "
                     f"Please download it and place it in the root directory.")
        raise FileNotFoundError(f"MediaPipe Task model file missing: {POSE_LANDMARKER_MODEL_PATH}")

    # 1. Create PoseLandmarker options
    base_options = python.BaseOptions(model_asset_path=POSE_LANDMARKER_MODEL_PATH)
    options = vision.PoseLandmarkerOptions(
        base_options=base_options,
        running_mode=vision.RunningMode.VIDEO,
        num_poses=1,
        min_pose_detection_confidence=0.5,
        min_pose_presence_confidence=0.5,
        min_tracking_confidence=0.5
    )

    results_list = []

    # 2. Initialize landmarker
    with vision.PoseLandmarker.create_from_options(options) as landmarker:
        for item in frames_data:
            frame = item["frame"]
            timestamp = item["timestamp"]
            
            # Convert timestamp to milliseconds for MediaPipe Tasks
            timestamp_ms = int(timestamp * 1000)
            
            try:
                # Convert numpy array to MediaPipe Image object
                mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame)
                
                # Perform detection for video mode
                detection_result = landmarker.detect_for_video(mp_image, timestamp_ms)
                
                if not detection_result or not detection_result.pose_landmarks:
                    logger.warning(f"No landmarks detected at t={timestamp}")
                    results_list.append({
                        "landmarks": np.zeros((33, 4)),
                        "timestamp": timestamp,
                        "valid": False
                    })
                    continue
                
                # MediaPipe Tasks returns a list of poses, each pose is a list of landmarks
                # Since num_poses=1, we take index 0
                pose_landmarks = detection_result.pose_landmarks[0]
                
                # Convert landmarks to (33, 4) numpy array: x, y, z, visibility
                landmarks = np.array([
                    [lm.x, lm.y, lm.z, lm.visibility] 
                    for lm in pose_landmarks
                ])
                
                # Check visibility threshold
                mean_visibility = np.mean(landmarks[:, 3])
                is_valid = mean_visibility >= MIN_VISIBILITY_THRESHOLD
                
                if not is_valid:
                    logger.warning(f"Low visibility ({mean_visibility:.2f}) at t={timestamp}")
                
                results_list.append({
                    "landmarks": landmarks,
                    "timestamp": timestamp,
                    "valid": is_valid
                })
                
            except Exception as e:
                logger.error(f"MediaPipe Tasks inference failed at t={timestamp}: {e}")
                results_list.append({
                    "landmarks": np.zeros((33, 4)),
                    "timestamp": timestamp,
                    "valid": False
                })

    logger.info(f"Processed {len(frames_data)} frames with MediaPipe Tasks")
    return results_list
