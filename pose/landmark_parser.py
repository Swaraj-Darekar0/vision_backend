"""
pose/landmark_parser.py

Parses the landmark JSON payload received from the React Native frontend
(BlazePose via TF.js) into the normalized list-of-dicts format that
normalizer.py expects.

This file replaces frame_extractor.py and landmark_extractor.py entirely.
No MediaPipe, no OpenCV, no video file handling.

Input contract (from frontend):
    {
      "session_id": str,
      "user_id": str,
      "fps_achieved": float,
      "total_frames": int,
      "duration_seconds": float,
      "frames": [
        {
          "timestamp": float,
          "landmarks": [
            { "x": float, "y": float, "z": float, "visibility": float },
            ... 33 total
          ]
        },
        ...
      ]
    }

Output contract (to normalizer.py) — identical to what landmark_extractor.py produced:
    List[Dict]: {
        "landmarks": np.ndarray,  # shape (33, 4) — columns: x, y, z, visibility
        "timestamp": float,
        "valid": bool
    }
"""

import logging
import numpy as np
from typing import List, Dict, Any

from config import MIN_VISIBILITY_THRESHOLD

logger = logging.getLogger(__name__)

# Minimum number of key landmarks that must be visible for a frame to be valid.
# Uses the same threshold constant as the retired landmark_extractor.py.
_KEY_LANDMARK_INDICES = [0, 11, 12, 23, 24]  # nose, shoulders, hips


def parse_landmark_payload(payload: Dict[str, Any]) -> List[Dict]:
    """
    Converts the frontend landmark JSON payload into the list-of-dicts format
    expected by normalizer.py.

    Args:
        payload: Parsed JSON dict from the multipart request field 'pose_landmarks'.

    Returns:
        List of frame dicts with keys: landmarks (np.ndarray shape 33x4),
        timestamp (float), valid (bool).

    Raises:
        ValueError: If payload is missing required top-level fields.
    """
    if 'frames' not in payload:
        raise ValueError("Landmark payload missing required field: 'frames'")
    if not isinstance(payload['frames'], list):
        raise ValueError("Landmark payload 'frames' must be a list")

    frames = payload['frames']
    logger.info(
        f"[LandmarkParser] Parsing {len(frames)} frames "
        f"| fps_achieved={payload.get('fps_achieved', 'unknown')} "
        f"| duration={payload.get('duration_seconds', 'unknown')}s"
    )

    parsed_frames = []

    for i, frame in enumerate(frames):
        try:
            parsed = _parse_single_frame(frame, i)
            parsed_frames.append(parsed)
        except Exception as e:
            logger.warning(
                f"[LandmarkParser] Frame {i} at t={frame.get('timestamp', '?')} "
                f"failed parsing: {e} — marking invalid"
            )
            parsed_frames.append({
                "landmarks": np.zeros((33, 4), dtype=np.float32),
                "timestamp": frame.get('timestamp', 0.0),
                "valid": False,
            })

    valid_count = sum(1 for f in parsed_frames if f['valid'])
    logger.info(
        f"[LandmarkParser] {valid_count}/{len(parsed_frames)} frames valid "
        f"after parsing"
    )

    return parsed_frames


def _parse_single_frame(frame: Dict, frame_index: int) -> Dict:
    """
    Parses one frame dict from the payload into the normalizer.py input format.

    Args:
        frame: Single frame dict with 'timestamp' and 'landmarks' keys.
        frame_index: Index in the frames array (for logging only).

    Returns:
        Dict with 'landmarks' (np.ndarray 33x4), 'timestamp' (float), 'valid' (bool).
    """
    timestamp = float(frame['timestamp'])
    raw_landmarks = frame['landmarks']

    if len(raw_landmarks) != 33:
        raise ValueError(
            f"Expected 33 landmarks, got {len(raw_landmarks)}"
        )

    # Build (33, 4) numpy array — columns: x, y, z, visibility
    # This is the identical shape produced by the retired landmark_extractor.py
    landmark_array = np.array(
        [
            [
                float(lm['x']),
                float(lm['y']),
                float(lm['z']),
                float(lm['visibility']),
            ]
            for lm in raw_landmarks
        ],
        dtype=np.float32,
    )  # shape: (33, 4)

    # Validate frame using the same visibility rule as landmark_extractor.py
    key_visibilities = landmark_array[_KEY_LANDMARK_INDICES, 3]
    mean_visibility = float(np.mean(key_visibilities))
    is_valid = mean_visibility >= MIN_VISIBILITY_THRESHOLD

    if not is_valid:
        logger.warning(
            f"[LandmarkParser] Frame {frame_index} at t={timestamp:.3f}s "
            f"marked invalid — mean key landmark visibility {mean_visibility:.3f} "
            f"< threshold {MIN_VISIBILITY_THRESHOLD}"
        )

    return {
        "landmarks": landmark_array,
        "timestamp": timestamp,
        "valid": is_valid,
    }
