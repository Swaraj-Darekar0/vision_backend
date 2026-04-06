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
        audio_path: Path to audio file (WAV or M4A).
        
    Returns:
        Dict: { "pitch_variance_normalized":    float,
                "jitter_normalized":            float,
                "energy_variation_normalized":  float,
                "pause_ratio":                  float }
    """
    logger.info(f"Extracting acoustic features from {audio_path}")
    
    try:
        # Load audio at configured sample rate into float32 to reduce peak memory usage
        y, sr = librosa.load(audio_path, sr=config.AUDIO_SAMPLE_RATE, mono=True, dtype=np.float32)

        # Normalize amplitude in-place to avoid an extra copy
        if y.size > 0:
            max_val = np.max(np.abs(y))
            if max_val > 0.0:
                y /= max_val

        # 1. Pitch (F0) extraction using pyin
        # fmin/fmax roughly match human vocal range
        f0, voiced_flag, voiced_probs = librosa.pyin(
            y, fmin=librosa.note_to_hz('C2'), fmax=librosa.note_to_hz('C7'),
            sr=sr,
            frame_length=config.PYIN_FRAME_LENGTH,
            hop_length=config.PYIN_HOP_LENGTH,
        )

        f0 = np.nan_to_num(f0).astype(np.float32)
        voiced_f0 = f0[voiced_flag]

        # 2. RMS Energy
        rms = librosa.feature.rms(y=y, frame_length=2048, hop_length=512)
        rms_array = rms[0].astype(np.float32)

        # 3. Scalar computation: Pitch Variance (normalized)
        if len(voiced_f0) > 0:
            pitch_var_raw = np.std(voiced_f0) / np.mean(voiced_f0)
            pv_norm = (pitch_var_raw - config.PITCH_VARIANCE_MIN) / (config.PITCH_VARIANCE_MAX - config.PITCH_VARIANCE_MIN)
        else:
            pv_norm = 0.0
        pitch_variance_normalized = float(np.clip(pv_norm, 0.0, 1.0))

        # 4. Scalar computation: Jitter (normalized)
        if len(voiced_f0) > 1:
            jitter_raw = np.mean(np.abs(np.diff(voiced_f0))) / np.mean(voiced_f0)
            jitter_norm = jitter_raw / config.JITTER_THRESHOLD
        else:
            jitter_norm = 0.0
        jitter_normalized = float(np.clip(jitter_norm, 0.0, 1.0))

        # 5. Scalar computation: Energy Variation (normalized)
        if rms_array.size > 0:
            energy_var_raw = np.std(rms_array) / np.mean(rms_array)
            energy_var_norm = energy_var_raw / config.ENERGY_VAR_THRESHOLD
        else:
            energy_var_norm = 0.0
        energy_variation_normalized = float(np.clip(energy_var_norm, 0.0, 1.0))

        # 6. Scalar computation: Pause Ratio
        pause_frames = np.sum(rms_array < config.PAUSE_RMS_THRESHOLD)
        pause_ratio = pause_frames / len(rms_array) if rms_array.size > 0 else 0.0

        # Free large arrays before returning metrics
        del y, f0, voiced_f0, rms, rms_array

        logger.info("Acoustic extraction successful.")
        return {
            "pitch_variance_normalized": pitch_variance_normalized,
            "jitter_normalized": jitter_normalized,
            "energy_variation_normalized": energy_variation_normalized,
            "pause_ratio": float(pause_ratio)
        }
        
    except Exception as e:
        logger.error(f"Acoustic extraction failed: {e}")
        raise ValueError(f"Acoustic extraction failed: {e}")
