import numpy as np
import logging
from typing import Dict
import config

logger = logging.getLogger(__name__)

def compute_audio_instability(acoustics: Dict, timing: Dict, fillers: Dict) -> float:
    """
    Weighted combination of pitch, jitter, fillers, pauses, and rate instability.
    Source: master_formula.md Section 1.3 & 7.1.
    """
    # Note: Using weights from config or master_formula
    # PV_norm (0.30) + Jitter (0.20) + Filler (0.20) + Pause (0.15) + RateInstab (0.15)
    pv = acoustics["pitch_variance_normalized"]
    jitter = acoustics["jitter_normalized"]
    filler = fillers["filler_ratio_normalized"]
    pause = acoustics["pause_ratio"]
    instab = timing["speech_rate_instability_normalized"]
    
    raw = (0.30 * pv + 0.20 * jitter + 0.20 * filler + 0.15 * pause + 0.15 * instab)
    return float(np.clip(raw, 0.0, 1.0))

def compute_audio_confidence(acoustics: Dict, timing: Dict, fillers: Dict) -> float:
    """
    Weighted combination with inverse filler, pitch, and pause signals.
    Source: master_formula.md Section 1.3.
    """
    # 0.40(1 - FillerRatio) + 0.30(1 - PV_norm) + 0.20(RateScore) + 0.10(1 - PauseRatio)
    filler_inv = 1.0 - fillers.get("filler_ratio", 0.0)
    pv_inv = 1.0 - acoustics["pitch_variance_normalized"]
    rate_score = timing["speech_rate_score"]
    pause_inv = 1.0 - acoustics["pause_ratio"]
    
    raw = (0.40 * filler_inv + 0.30 * pv_inv + 0.20 * rate_score + 0.10 * pause_inv)
    return float(np.clip(raw, 0.0, 1.0))

def compute_audio_engagement(acoustics: Dict, timing: Dict) -> float:
    """
    Built from PitchExpressiveness and EnergyExpressiveness composites.
    Source: master_formula.md Section 1.3.
    """
    # 0.35(PitchExp) + 0.35(EnergyExp) + 0.30(RateScore)
    # PitchExp proxy: PitchVariance; EnergyExp proxy: EnergyVariation
    pitch_exp = acoustics["pitch_variance_normalized"]
    energy_exp = acoustics["energy_variation_normalized"]
    rate_score = timing["speech_rate_score"]
    
    raw = (0.35 * pitch_exp + 0.35 * energy_exp + 0.30 * rate_score)
    return float(np.clip(raw, 0.0, 1.0))

def compute_derived_attributes(acoustics: Dict, timing: Dict, fillers: Dict) -> Dict:
    """
    Dispatcher to compute all 4 audio behavioral attributes.
    """
    instability = compute_audio_instability(acoustics, timing, fillers)
    
    output = {
        "audio_instability": instability,
        "audio_confidence": compute_audio_confidence(acoustics, timing, fillers),
        "audio_engagement": compute_audio_engagement(acoustics, timing),
        "audio_nervousness": instability # Defined as mirrors instability
    }
    
    logger.info("Computed audio derived attributes.")
    return output
