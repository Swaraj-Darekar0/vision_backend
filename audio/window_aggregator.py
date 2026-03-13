import numpy as np
import logging
from typing import Dict, List
import config

logger = logging.getLogger(__name__)

def aggregate_windows(acoustics: Dict, timing: Dict, fillers: Dict, transcript: Dict) -> List[Dict]:
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
    
    # Extract raw arrays for window slicing
    f0_array = acoustics["f0_array"]
    rms_array = acoustics["rms_array"]
    wpm_per_window = timing["wpm_per_window"]
    
    # To map frame-based arrays (F0, RMS) to windows, we need to know frame duration
    # Librosa default for 2048/512 at 16kHz is ~32ms per frame
    num_frames = len(rms_array)
    sec_per_frame = total_duration / num_frames if num_frames > 0 else 0
    frames_per_window = int(window_size / sec_per_frame) if sec_per_frame > 0 else 0
    
    window_results = []
    
    for i in range(num_windows):
        time_start = i * window_size
        time_end = (i + 1) * window_size
        
        # 1. Window-level Filler Ratio
        window_words = [w for w in words if time_start <= w["start"] < time_end]
        window_filler_count = 0
        if window_words:
            # Re-detect fillers for this specific window or filter session list
            # For simplicity, we filter the session words if we had a list of filler timestamps
            # But the contract asks for window-level scores.
            for w in window_words:
                if w["word"].lower().strip(",.?!") in config.FILLER_WORDS:
                    # Note: This is a simplified check without pause context for per-window
                    window_filler_count += 1
            
            filler_ratio = window_filler_count / len(window_words)
        else:
            filler_ratio = 0.0
            
        # 2. Window-level Pause Ratio (from RMS array)
        start_frame = i * frames_per_window
        end_frame = (i + 1) * frames_per_window
        window_rms = rms_array[start_frame:end_frame]
        
        if len(window_rms) > 0:
            pause_frames = np.sum(window_rms < config.PAUSE_RMS_THRESHOLD)
            pause_ratio = pause_frames / len(window_rms)
        else:
            pause_ratio = 0.0
            
        # 3. Window-level Pitch Variance (normalized)
        window_f0 = f0_array[start_frame:end_frame]
        voiced_f0 = window_f0[window_f0 > 0]
        if len(voiced_f0) > 1:
            pv_raw = np.std(voiced_f0) / np.mean(voiced_f0)
            pv_norm = (pv_raw - config.PITCH_VARIANCE_MIN) / (config.PITCH_VARIANCE_MAX - config.PITCH_VARIANCE_MIN)
            pv_norm = float(np.clip(pv_norm, 0.0, 1.0))
        else:
            pv_norm = 0.0
            
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
