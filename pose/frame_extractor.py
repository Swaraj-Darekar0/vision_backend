import cv2
import numpy as np
import logging
from typing import Generator, Dict, Any
from config import TARGET_FPS

logger = logging.getLogger(__name__)

def extract_frames(video_path: str) -> Generator[Dict[str, Any], None, None]:
    """
    Extracts frames from an MP4 video at TARGET_FPS and converts to RGB.
    Source: backend_implementation_plan.md Phase 2.
    
    Args:
        video_path: Path to the MP4 video file.
        
    Yields:
        Dictionary containing 'frame' (numpy array) and 'timestamp' (float).
        
    Raises:
        ValueError: If the video file cannot be opened or is invalid.
    """
    cap = cv2.VideoCapture(video_path)
    
    if not cap.isOpened():
        logger.error(f"Failed to open video file: {video_path}")
        raise ValueError(f"Could not open video file: {video_path}")
    
    source_fps = cap.get(cv2.CAP_PROP_FPS)
    if source_fps <= 0:
        logger.warning(f"Invalid source FPS detected ({source_fps}). Defaulting to {TARGET_FPS}")
        source_fps = TARGET_FPS
        
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = total_frames / source_fps
    
    logger.info(f"Extracting frames from {video_path}: {source_fps} FPS, {total_frames} total frames, {duration:.2f}s duration")
    
    # Calculate skip factor to match TARGET_FPS if source FPS is higher
    skip_factor = max(1, int(round(source_fps / TARGET_FPS)))
    
    frame_count = 0
    extracted_count = 0
    
    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break
                
            # Only process frames according to skip factor
            if frame_count % skip_factor == 0:
                # Convert BGR (OpenCV default) to RGB (MediaPipe requirement)
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                
                timestamp = frame_count / source_fps
                
                yield {
                    "frame": frame_rgb,
                    "timestamp": float(timestamp)
                }
                extracted_count += 1
                
            frame_count += 1
            
    finally:
        cap.release()
        logger.info(f"Finished extracting. Yielded {extracted_count} frames at approx {source_fps/skip_factor:.2f} FPS")
