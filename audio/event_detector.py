import numpy as np
import logging
from typing import Dict, List
import config

logger = logging.getLogger(__name__)

# Event type string constants
EVENT_HIGH_FUMBLE       = "high_fumble_spike"
EVENT_EXCESSIVE_PAUSE   = "excessive_pause"
EVENT_RAPID_SPEECH      = "rapid_speech_segment"
EVENT_MONOTONE          = "monotone_segment"
EVENT_VOCAL_INSTABILITY = "vocal_instability_spike"
EVENT_ADAPTIVE_SPIKE    = "adaptive_spike"
EVENT_FILLER_HEAVY      = "filler_heavy_segment"
EVENT_STUTTERED         = "stuttered_delivery_segment"
EVENT_EXTENDED_PAUSE    = "extended_pause_segment"

def detect_events(windows: List[Dict], cadence_metrics: Dict | None = None) -> List[Dict]:
    """
    Detects 6 event types from windowed data.
    Source: backend_SKILL.md Section 6 (audio/event_detector.py).
    
    Args:
        windows: List of windowed metric dicts.
        
    Returns:
        List[Dict]: { "time_start": float, "time_end": float, "event": str }
    """
    if not windows:
        return []
    cadence_metrics = cadence_metrics or {}
    events = []
    
    # 1. Calculate session-level stats for adaptive spike detection
    fumble_scores = [w["fumble_score"] for w in windows]
    session_mean_fumble = np.mean(fumble_scores)
    session_std_fumble = np.std(fumble_scores)
    
    cadence_profile = cadence_metrics.get("profile")
    rapid_threshold = config.RAPID_SPEECH_WPM_THRESHOLD
    if cadence_profile == "fast_driver":
        rapid_threshold += config.CADENCE_EVENT_WPM_BUFFER_FAST_DRIVER
    elif cadence_profile == "measured_pacer":
        rapid_threshold += config.CADENCE_EVENT_WPM_BUFFER_MEASURED_PACER

    for w in windows:
        t_start = w["time_start"]
        t_end = w["time_end"]
        
        # 2. High Fumble Spike
        if w["fumble_score"] > config.FUMBLE_SPIKE_THRESHOLD:
            events.append({"time_start": t_start, "time_end": t_end, "event": EVENT_HIGH_FUMBLE})
            
        # 3. Excessive Pause
        if w["pause_ratio"] > config.EXCESSIVE_PAUSE_THRESHOLD:
            events.append({"time_start": t_start, "time_end": t_end, "event": EVENT_EXCESSIVE_PAUSE})

        if w.get("extended_pause_score", 0.0) > config.CADENCE_EXTENDED_PAUSE_THRESHOLD:
            events.append({"time_start": t_start, "time_end": t_end, "event": EVENT_EXTENDED_PAUSE})

        if w.get("filler_ratio", 0.0) > config.CADENCE_FILLER_HEAVY_THRESHOLD:
            events.append({"time_start": t_start, "time_end": t_end, "event": EVENT_FILLER_HEAVY})

        if w.get("stutter_ratio", 0.0) > config.CADENCE_STUTTER_CLUSTER_THRESHOLD:
            events.append({"time_start": t_start, "time_end": t_end, "event": EVENT_STUTTERED})
            
        # 4. Rapid Speech
        if w["speech_rate_wpm"] > rapid_threshold:
            events.append({"time_start": t_start, "time_end": t_end, "event": EVENT_RAPID_SPEECH})
            
        # 5. Monotone Segment
        if w["pitch_variance_normalized"] < config.MONOTONE_PITCH_THRESHOLD:
            events.append({"time_start": t_start, "time_end": t_end, "event": EVENT_MONOTONE})
            
        # 6. Vocal Instability Spike
        # PitchVar > 0.70 OR (using jitter proxy if available in window)
        if w["pitch_variance_normalized"] > config.VOCAL_INSTABILITY_PITCH_THRESH:
            events.append({"time_start": t_start, "time_end": t_end, "event": EVENT_VOCAL_INSTABILITY})
            
        # 7. Adaptive Spike (Speaker-relative)
        delta = w["fumble_score"] - session_mean_fumble
        if delta > config.ADAPTIVE_SPIKE_STD_MULTIPLIER * session_std_fumble:
            events.append({"time_start": t_start, "time_end": t_end, "event": EVENT_ADAPTIVE_SPIKE})
            
    logger.info(f"Detected {len(events)} audio events.")
    return events
