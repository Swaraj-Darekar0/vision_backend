# config.py
import os
from dotenv import load_dotenv

load_dotenv()
# ═══════════════════════════════════════════════
# POSE — VIDEO SETTINGS
# ═══════════════════════════════════════════════
TARGET_FPS                      = 30
MIN_VISIBILITY_THRESHOLD        = 0.5
POSE_LANDMARKER_MODEL_PATH      = "pose\pose_model\pose_landmarker_full.task"
FRAME_RESIZE_WIDTH              = 640
FRAME_RESIZE_HEIGHT             = 360

# Smoothing (One Euro Filter)
POSE_SMOOTHING_MIN_CUTOFF       = 1.0  # Lower = less jitter at low speed
POSE_SMOOTHING_BETA             = 0.01 # Higher = less lag at high speed
POSE_SMOOTHING_D_CUTOFF         = 1.0  # Standard value

# ═══════════════════════════════════════════════
# POSE — METRIC THRESHOLDS  (T1–T7)
# Source: master_formula_reference.md Section 4
# ═══════════════════════════════════════════════
SHOULDER_ALIGNMENT_THRESHOLD    = 0.1   # T1
SPINE_STRAIGHTNESS_THRESHOLD    = 0.2   # T2 (radians)
HEAD_STABILITY_THRESHOLD        = 0.05  # T3
BODY_SWAY_THRESHOLD             = 0.05  # T4
FIDGET_THRESHOLD                = 0.1   # T5
MOVEMENT_VARIANCE_THRESHOLD     = 0.1   # T6
GAZE_DEVIATION_THRESHOLD        = 0.1   # T7

# Stability Warning Thresholds
SWAY_WARNING_THRESHOLD          = 0.40  # Trigger if score < 0.40
POSTURE_STABILITY_WARNING       = 0.50  # Trigger if score < 0.50
SWAY_DEAD_ZONE                  = 0.01  # 1% of normalized width - ignore micro-sways


POSTURE_OPENNESS_MAX_WIDTH      = 1.0
GESTURE_OPTIMAL_PER_MINUTE      = 6.0
GESTURE_DURATION_MIN_SEC        = 0.3
OPTIMAL_HAND_AMPLITUDE          = 0.45
STILLNESS_OPTIMAL_RATIO         = 0.5

# ═══════════════════════════════════════════════
# POSE — DERIVED ATTRIBUTE WEIGHTS
# Source: master_formula_reference.md Section 6
# ═══════════════════════════════════════════════
POSTURE_STABILITY_WEIGHTS   = { "shoulder_alignment": 0.30, "spine_straightness": 0.25,
                                "head_stability": 0.20, "body_sway": 0.15, "symmetry_score": 0.10 }
POSE_CONFIDENCE_WEIGHTS     = { "posture_stability_index": 0.40, "posture_openness": 0.30, 
                                "gaze_stability": 0.20, "symmetry_score": 0.10 }
POSE_NERVOUSNESS_WEIGHTS    = { "head_stability": 0.35, "body_sway": 0.30, 
                                "fidget_score": 0.20, "movement_variance_normalized": 0.15 }
POSE_ENGAGEMENT_WEIGHTS     = { "gesture_score": 0.40, "amplitude_score": 0.30, "posture_openness": 0.30 }

# ═══════════════════════════════════════════════
# AUDIO — PREPROCESSING
# ═══════════════════════════════════════════════
AUDIO_SAMPLE_RATE               = 16000
WHISPER_MODEL_SIZE              = "base"

# ═══════════════════════════════════════════════
# AUDIO — ACOUSTIC THRESHOLDS
# Source: master_formula_reference.md Section 4
# ═══════════════════════════════════════════════
PITCH_VARIANCE_MIN              = 0.05
PITCH_VARIANCE_MAX              = 0.50
JITTER_THRESHOLD                = 0.02  # T1 audio (Placeholder)
ENERGY_VAR_THRESHOLD            = 0.1   # T2 audio (Placeholder)
PAUSE_RMS_THRESHOLD             = 0.01  # theta — silence energy floor
SPEECH_RATE_INSTABILITY_THRESH  = 10.0  # T3 audio (Placeholder)
FILLER_RATIO_CEILING            = 0.20
OPTIMAL_WPM                     = 145.0
FILLER_PAUSE_CONTEXT            = 0.3   # seconds

# ═══════════════════════════════════════════════
# AUDIO — FILLER DICTIONARY
# ═══════════════════════════════════════════════
FILLER_WORDS = {
    "um", "uh", "erm", "hmm", "like", "basically",
    "actually", "you know", "i mean", "sort of", "kind of"
}

# ═══════════════════════════════════════════════
# AUDIO — WINDOW & FUMBLE SCORE
# Source: master_formula_reference.md Section 9
# ═══════════════════════════════════════════════
WINDOW_SIZE_SECONDS             = 5.0
FUMBLE_SCORE_WEIGHTS = {
    "filler_ratio":                         0.35,
    "pause_ratio":                          0.25,
    "pitch_variance_normalized":            0.20,
    "speech_rate_instability_normalized":   0.20,
}

# ═══════════════════════════════════════════════
# AUDIO — DERIVED ATTRIBUTE WEIGHTS
# Source: master_formula_reference.md Section 7
# ═══════════════════════════════════════════════
AUDIO_INSTABILITY_WEIGHTS   = { "pitch_variance_normalized": 0.30, "jitter_normalized": 0.20, 
                                "filler_ratio": 0.20, "pause_ratio": 0.15, "speech_rate_instability_normalized": 0.15 }
AUDIO_CONFIDENCE_WEIGHTS    = { "filler_ratio": 0.40, "pitch_variance_normalized": 0.30, 
                                "speech_rate_score": 0.20, "pause_ratio": 0.10 }
AUDIO_ENGAGEMENT_WEIGHTS    = { "pitch_expressiveness": 0.35, "energy_expressiveness": 0.35, "speech_rate_score": 0.30 }
AUDIO_NERVOUSNESS_WEIGHTS   = AUDIO_INSTABILITY_WEIGHTS

# ═══════════════════════════════════════════════
# AUDIO — EVENT DETECTION THRESHOLDS
# Source: master_formula_reference.md Section 9
# ═══════════════════════════════════════════════
FUMBLE_SPIKE_THRESHOLD          = 0.60
EXCESSIVE_PAUSE_THRESHOLD       = 0.40
RAPID_SPEECH_WPM_THRESHOLD      = 180.0
MONOTONE_PITCH_THRESHOLD        = 0.10
VOCAL_INSTABILITY_PITCH_THRESH  = 0.70
VOCAL_INSTABILITY_JITTER_THRESH = 0.65
ADAPTIVE_SPIKE_STD_MULTIPLIER   = 2.0

# ═══════════════════════════════════════════════
# EVALUATION — FUSION WEIGHTS
# Source: master_formula.md — Fusion Layer
# ═══════════════════════════════════════════════
# These are weights for fusing Pose Behavioral Attributes and Audio Behavioral Attributes
CONFIDENCE_FUSION_WEIGHTS   = { "pose_confidence": 0.5, "audio_confidence": 0.5 }
CLARITY_FUSION_WEIGHTS      = { "posture_stability_index": 0.4, "audio_instability": 0.6 } # clarity is inverse of instability
ENGAGEMENT_FUSION_WEIGHTS   = { "pose_engagement": 0.5, "audio_engagement": 0.5 }
NERVOUSNESS_FUSION_WEIGHTS  = { "pose_nervousness": 0.5, "audio_nervousness": 0.5 }
OVERALL_FUSION_WEIGHTS      = { "confidence": 0.3, "clarity": 0.3, "engagement": 0.2, "nervousness": 0.2 }

# ═══════════════════════════════════════════════
# EVALUATION — PROGRESS CLASSIFICATION
# Source: master_formula_reference.md Section 5
# ═══════════════════════════════════════════════
SIGNIFICANT_IMPROVEMENT_THRESHOLD   = 0.05
MODERATE_IMPROVEMENT_THRESHOLD      = 0.02
NOTICEABLE_DECLINE_THRESHOLD        = -0.05
ROLLING_BASELINE_SESSIONS           = 3

# ═══════════════════════════════════════════════
# AUDIO — ASSEMBLYAI TRANSCRIPTION
# Model: Universal-3 Pro — do not downgrade
# ═══════════════════════════════════════════════
ASSEMBLYAI_KEY              = os.getenv("ASSEMBLYAI_API_KEY", "")
ASSEMBLYAI_SPEECH_MODEL         = "universal"   # Universal-3 Pro
ASSEMBLYAI_PUNCTUATE            = True
ASSEMBLYAI_FORMAT_TEXT          = False         # preserve raw spoken text exactly
ASSEMBLYAI_TRANSCRIPTION_PROMPT = (
    "Transcribe exactly what is spoken without any cleanup or correction. "
    "Include all filler sounds such as um, uh, hmm, and erm exactly as uttered. "
    "If a word is repeated consecutively, include it both times as spoken. "
    "Represent audible silences or long pauses with '...'. "
    "Do not remove repetitions, do not fix grammar, do not deduplicate words."
)

# ═══════════════════════════════════════════════
# INFRASTRUCTURE — DATABASE (Supabase)
# ═══════════════════════════════════════════════
SUPABASE_URL    = os.getenv("SUPABASE_URL",  "")
SUPABASE_KEY    = os.getenv("SUPABASE_KEY",  "")   # anon/service role key

# ═══════════════════════════════════════════════
# INFRASTRUCTURE — LLM (Groq)
# ═══════════════════════════════════════════════
GROQ_API_KEY    = os.getenv("GROQ_API_KEY",  "")
GROQ_MODEL      = "openai/gpt-oss-20b"
