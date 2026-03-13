import librosa
import numpy as np
import scipy.signal as signal
import logging
from typing import Dict
import config

logger = logging.getLogger(__name__)

def extract_acoustic_features(audio_path: str) -> Dict:
    """
    All Librosa feature extraction: F0, RMS, jitter, energy, pauses.
    Source: backend_SKILL.md Section 6 (audio/acoustic_extractor.py).
    
    Args:
        audio_path: Path to preprocessed WAV file.
        
    Returns:
        Dict: { "f0_array":                     np.ndarray,
                "rms_array":                    np.ndarray,
                "pitch_variance_normalized":    float,
                "jitter_normalized":            float,
                "energy_variation_normalized":  float,
                "pause_ratio":                  float }
    """
    logger.info(f"Extracting acoustic features from {audio_path}")
    
    try:
        # Load audio at configured sample rate
        y, sr = librosa.load(audio_path, sr=config.AUDIO_SAMPLE_RATE)
        
        # 1. Pitch (F0) extraction using pyin
        # fmin/fmax roughly match human vocal range
        f0, voiced_flag, voiced_probs = librosa.pyin(
            y, fmin=librosa.note_to_hz('C2'), fmax=librosa.note_to_hz('C7'), 
            sr=sr, frame_length=2048
        )
        # Fill NaNs with 0
        f0_filled = np.nan_to_num(f0)
        
        # 2. RMS Energy
        rms = librosa.feature.rms(y=y, frame_length=2048, hop_length=512)
        rms_array = rms[0] # Single channel
        
        # 3. Scalar computation: Pitch Variance (normalized)
        # CoV = σ(F0) / μ(F0) - only for voiced frames
        voiced_f0 = f0[voiced_flag]
        if len(voiced_f0) > 0:
            pitch_var_raw = np.std(voiced_f0) / np.mean(voiced_f0)
            # Normalize per Section 1.1: (PV - 0.05) / (0.50 - 0.05)
            pv_norm = (pitch_var_raw - config.PITCH_VARIANCE_MIN) / (config.PITCH_VARIANCE_MAX - config.PITCH_VARIANCE_MIN)
        else:
            pv_norm = 0.0
        
        pitch_variance_normalized = float(np.clip(pv_norm, 0.0, 1.0))
        
        # 4. Scalar computation: Jitter (normalized)
        # Jitter = (1 / n-1) * Σ | f_{i+1} - f_i |
        if len(voiced_f0) > 1:
            jitter_raw = np.mean(np.abs(np.diff(voiced_f0))) / np.mean(voiced_f0)
            jitter_norm = jitter_raw / config.JITTER_THRESHOLD
        else:
            jitter_norm = 0.0
            
        jitter_normalized = float(np.clip(jitter_norm, 0.0, 1.0))
        
        # 5. Scalar computation: Energy Variation (normalized)
        # EnergyVar = σ(E) / μ(E)
        if len(rms_array) > 0:
            energy_var_raw = np.std(rms_array) / np.mean(rms_array)
            energy_var_norm = energy_var_raw / config.ENERGY_VAR_THRESHOLD
        else:
            energy_var_norm = 0.0
            
        energy_variation_normalized = float(np.clip(energy_var_norm, 0.0, 1.0))
        
        # 6. Scalar computation: Pause Ratio
        # PauseRatio = PauseDuration / TotalDuration
        # Frames with RMS < theta threshold
        pause_frames = np.sum(rms_array < config.PAUSE_RMS_THRESHOLD)
        pause_ratio = pause_frames / len(rms_array)
        
        output = {
            "f0_array": f0_filled,
            "rms_array": rms_array,
            "pitch_variance_normalized": pitch_variance_normalized,
            "jitter_normalized": jitter_normalized,
            "energy_variation_normalized": energy_variation_normalized,
            "pause_ratio": float(pause_ratio)
        }
        
        logger.info("Acoustic extraction successful.")
        return output
        
    except Exception as e:
        logger.error(f"Acoustic extraction failed: {e}")
        raise ValueError(f"Acoustic extraction failed: {e}")
