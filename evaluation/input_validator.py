import logging
from typing import Dict, Tuple, List

logger = logging.getLogger(__name__)

# Required field lists based on data contracts
REQUIRED_POSE_METRICS = [
    "shoulder_alignment", "spine_straightness", "posture_openness",
    "head_stability", "body_sway", "gesture_score", "amplitude_score",
    "symmetry_score", "fidget_score", "stillness_score"
]

REQUIRED_POSE_DERIVED = [
    "posture_stability_index", "pose_confidence", "pose_nervousness",
    "pose_engagement", "movement_variance_normalized", "gaze_stability"
]

REQUIRED_AUDIO_METRICS = [
    "pitch_variance_normalized", "jitter_normalized", "energy_variation_normalized",
    "pause_ratio", "speech_rate_wpm", "speech_rate_score",
    "speech_rate_instability_normalized", "filler_ratio"
]

REQUIRED_AUDIO_DERIVED = [
    "audio_instability", "audio_confidence", "audio_engagement", "audio_nervousness"
]

def validate_inputs(pose_data: Dict, audio_data: Dict) -> Tuple[bool, str]:
    """
    Validates all required fields in both input JSONs.
    Returns (True, "") if valid, or (False, "error message") if not.
    Source: backend_SKILL.md Section 6 (evaluation/input_validator.py).
    """
    
    # 1. Validate Pose Data
    if not pose_data:
        return False, "Missing Pose JSON data"
        
    p_metrics = pose_data.get("posture_metrics", {})
    p_derived = pose_data.get("derived_pose_attributes", {})
    
    for field in REQUIRED_POSE_METRICS:
        if field not in p_metrics:
            return False, f"Missing required pose metric: {field}"
        val = p_metrics[field]
        if not isinstance(val, (float, int)) or not (0.0 <= val <= 1.0):
            logger.warning(f"Pose metric {field} out of range: {val}")
            
    for field in REQUIRED_POSE_DERIVED:
        if field not in p_derived:
            return False, f"Missing required pose derived attribute: {field}"
            
    # 2. Validate Audio Data
    if not audio_data:
        return False, "Missing Audio JSON data"
        
    a_metrics = audio_data.get("acoustic_metrics", {})
    a_derived = audio_data.get("derived_audio_attributes", {})
    
    for field in REQUIRED_AUDIO_METRICS:
        if field not in a_metrics:
            return False, f"Missing required audio metric: {field}"
        # WPM is allowed to be > 1.0
        if field == "speech_rate_wpm":
            continue
        val = a_metrics[field]
        if not isinstance(val, (float, int)) or not (0.0 <= val <= 1.0):
            logger.warning(f"Audio metric {field} out of range: {val}")
            
    for field in REQUIRED_AUDIO_DERIVED:
        if field not in a_derived:
            return False, f"Missing required audio derived attribute: {field}"
            
    # 3. Check for events list
    if "timestamp_events" not in audio_data:
        return False, "Missing timestamp_events list in audio data"

    return True, ""
