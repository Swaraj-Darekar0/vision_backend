import numpy as np
import logging
from typing import Dict, List
import config

logger = logging.getLogger(__name__)

def compute_timing_metrics(transcript_data: Dict) -> Dict:
    """
    WPM calculation, speech rate score, speech rate instability.
    Source: backend_SKILL.md Section 6 (audio/timing_metrics.py).
    
    Args:
        transcript_data: Dict from transcriber { "words": List[Dict], "full_text": str }
        
    Returns:
        Dict: { "speech_rate_wpm":                    float,
                "speech_rate_score":                  float,
                "speech_rate_instability_normalized": float,
                "wpm_per_window":                     List[float] }
    """
    words = transcript_data.get("words", [])
    total_words = len(words)
    
    if total_words == 0:
        return {
            "speech_rate_wpm": 0.0,
            "speech_rate_score": 0.0,
            "speech_rate_instability_normalized": 0.0,
            "wpm_per_window": []
        }

    # 1. Compute Overall Speech Rate
    # Formula: WPM = TotalWords / SpeakingDuration (exclude pause time)
    start_time = words[0]["start"]
    end_time = words[-1]["end"]
    total_duration = end_time - start_time
    
    # Calculate total pause duration within speech
    pause_duration = 0.0
    for i in range(1, total_words):
        pause = words[i]["start"] - words[i-1]["end"]
        if pause > 0:
            pause_duration += pause
            
    speaking_duration = max(0.1, total_duration - pause_duration)
    speech_rate_wpm = (total_words / (speaking_duration / 60.0))
    
    # 2. Speech Rate Score
    # RateScore = 1 - | WPM - 145 | / 145
    rate_score = 1.0 - (abs(speech_rate_wpm - config.OPTIMAL_WPM) / config.OPTIMAL_WPM)
    speech_rate_score = float(np.clip(rate_score, 0.0, 1.0))
    
    # 3. Windowed WPM for Instability
    # Divide session into 5-second windows
    window_size = config.WINDOW_SIZE_SECONDS
    num_windows = int(np.ceil(end_time / window_size))
    wpm_per_window = []
    
    for i in range(num_windows):
        w_start = i * window_size
        w_end = (i + 1) * window_size
        
        # Words in this window
        window_words = [w for w in words if w_start <= w["start"] < w_end]
        
        if window_words:
            w_total_words = len(window_words)
            # Duration within window where speech actually happened
            # Simplified: use window_size minus internal pauses
            w_pause = 0.0
            for j in range(1, w_total_words):
                p = window_words[j]["start"] - window_words[j-1]["end"]
                if p > 0:
                    w_pause += p
            
            # Using actual span of words in window as duration
            w_span = window_words[-1]["end"] - window_words[0]["start"]
            w_speaking_dur = max(0.1, w_span - w_pause)
            w_wpm = (w_total_words / (w_speaking_dur / 60.0))
            wpm_per_window.append(float(w_wpm))
        else:
            wpm_per_window.append(0.0)
            
    # 4. Speech Rate Instability
    # Instability = std(WPM_per_window)
    if len(wpm_per_window) > 1:
        instability_raw = float(np.std(wpm_per_window))
        # Normalize: SpeechRateInstabilityNormalized = min(instab / T3, 1)
        instability_norm = instability_raw / config.SPEECH_RATE_INSTABILITY_THRESH
    else:
        instability_norm = 0.0
        
    speech_rate_instability_normalized = float(np.clip(instability_norm, 0.0, 1.0))
    
    output = {
        "speech_rate_wpm": float(speech_rate_wpm),
        "speech_rate_score": speech_rate_score,
        "speech_rate_instability_normalized": speech_rate_instability_normalized,
        "wpm_per_window": wpm_per_window
    }
    
    logger.info(f"Timing metrics complete: {speech_rate_wpm:.2f} WPM")
    return output
