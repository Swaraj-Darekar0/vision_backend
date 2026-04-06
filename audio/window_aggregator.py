import numpy as np
import logging
from typing import Dict, List
import config
from audio.filler_detector import count_fillers_in_words

logger = logging.getLogger(__name__)

def aggregate_windows(
    acoustics: Dict,
    timing: Dict,
    fillers: Dict,
    transcript: Dict,
    acoustic_windows: List[Dict] | None = None,
) -> List[Dict]:
    """
    5-second window grouping and FumbleScore computation.
    Source: backend_SKILL.md Section 6 (audio/window_aggregator.py).
    
    Returns:
        List[Dict]: One dict per 5-second window.
    """
    window_size = config.WINDOW_SIZE_SECONDS
    words = transcript.get("words", [])
    if not words:
        return []
        
    total_duration = words[-1]["end"]
    num_windows = int(np.ceil(total_duration / window_size))
    wpm_per_window = timing["wpm_per_window"]
    acoustic_windows = acoustic_windows or []
    windows_by_index = {
        int(window.get("window_index")): window
        for window in acoustic_windows
        if window.get("window_index") is not None
    }
    
    window_results = []
    
    for i in range(num_windows):
        time_start = i * window_size
        time_end = (i + 1) * window_size
        
        # 1. Window-level Filler Ratio
        window_words = [w for w in words if time_start <= w["start"] < time_end]
        if window_words:
            window_filler_count, _ = count_fillers_in_words(window_words)
            filler_ratio = window_filler_count / len(window_words)
        else:
            filler_ratio = 0.0

        # 2. Window-level acoustic features
        source_window = windows_by_index.get(i)
        if source_window:
            pause_ratio = float(np.clip(source_window.get("pause_ratio", acoustics.get("pause_ratio", 0.0)), 0.0, 1.0))
            pv_norm = float(
                np.clip(
                    source_window.get("pitch_variance_normalized", acoustics.get("pitch_variance_normalized", 0.0)),
                    0.0,
                    1.0,
                )
            )
        else:
            # Coarse fallback when the client only sends session-level acoustic metrics.
            pause_ratio = float(np.clip(acoustics.get("pause_ratio", 0.0), 0.0, 1.0))
            pv_norm = float(np.clip(acoustics.get("pitch_variance_normalized", 0.0), 0.0, 1.0))
            
        # 4. Window-level Speech Rate Metrics
        window_wpm = wpm_per_window[i] if i < len(wpm_per_window) else 0.0
        # Speech rate instability per window is tricky; 
        # normally it's session-level, but here we can use deviation from session mean.
        session_wpm_mean = timing["speech_rate_wpm"]
        instab_raw = abs(window_wpm - session_wpm_mean)
        instab_norm = float(np.clip(instab_raw / config.SPEECH_RATE_INSTABILITY_THRESH, 0.0, 1.0))
        
        # 5. FumbleScore_k computation
        # 0.35(Filler_w) + 0.25(Pause_w) + 0.20(PitchVar_w) + 0.20(RateInstab_w)
        weights = config.FUMBLE_SCORE_WEIGHTS
        fumble_score = (weights["filler_ratio"] * filler_ratio +
                        weights["pause_ratio"] * pause_ratio +
                        weights["pitch_variance_normalized"] * pv_norm +
                        weights["speech_rate_instability_normalized"] * instab_norm)
        
        window_results.append({
            "window_index": i,
            "time_start": float(time_start),
            "time_end": float(time_end),
            "filler_ratio": float(filler_ratio),
            "pause_ratio": float(pause_ratio),
            "pitch_variance_normalized": float(pv_norm),
            "speech_rate_wpm": float(window_wpm),
            "speech_rate_instability_normalized": float(instab_norm),
            "fumble_score": float(np.clip(fumble_score, 0.0, 1.0))
        })
        
    logger.info(f"Aggregated {num_windows} windows.")
    return window_results
