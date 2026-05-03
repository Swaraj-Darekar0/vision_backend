# config.py
import os
from dotenv import load_dotenv

load_dotenv()
# ═══════════════════════════════════════════════
# POSE — VIDEO SETTINGS
# ═══════════════════════════════════════════════
MIN_VISIBILITY_THRESHOLD        = 0.5


BASE_DIR = os.path.dirname(os.path.abspath(__file__))

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
AUDIO_TRANSCRIPTION_FORMAT      = "mp3"
AUDIO_TRANSCRIPTION_BITRATE     = "64k"
PYIN_FRAME_LENGTH               = 2048
PYIN_HOP_LENGTH                 = 1024

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
FILLER_PAUSE_MULTIPLIER    = 1.8   # pause must be 1.8× speaker's own median to count
FILLER_BASELINE_MIN_WORDS  = 10    # minimum words needed to compute a reliable baseline
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
CLARITY_FUSION_WEIGHTS      = { "posture_stability_index": 0.1, "audio_instability": 0.3, "reasoning_clarity": 0.6 } # clarity is inverse of instability
CONTENT_EFFECTIVENESS_WEIGHTS = { "reasoning_clarity": 0.55, "topic_relevance": 0.45 }
ENGAGEMENT_FUSION_WEIGHTS   = { "pose_engagement": 0.45, "audio_engagement": 0.45, "content_effectiveness": 0.10 }
NERVOUSNESS_FUSION_WEIGHTS  = { "pose_nervousness": 0.5, "audio_nervousness": 0.5 }
OVERALL_FUSION_WEIGHTS      = { "confidence": 0.25, "clarity": 0.25, "engagement": 0.20, "nervousness": 0.15, "content_effectiveness": 0.15 }

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
# Prefer Universal-3 Pro, but allow Universal-2 fallback for multilingual audio.
# ═══════════════════════════════════════════════
ASSEMBLYAI_KEY                  = os.getenv("ASSEMBLYAI_API_KEY", "")
ASSEMBLYAI_SPEECH_MODELS        = ["universal-3-pro", "universal-2"]
ASSEMBLYAI_LANGUAGE_DETECTION   = True
ASSEMBLYAI_PUNCTUATE            = True
ASSEMBLYAI_FORMAT_TEXT          = False
ASSEMBLYAI_TEMPERATURE          = 0.1
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
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
SUPABASE_NOTIFICATION_IMAGE_BUCKET = os.getenv("SUPABASE_NOTIFICATION_IMAGE_BUCKET", "notification-images")
NOTIFICATION_IMAGE_SIGNED_URL_SECONDS = int(os.getenv("NOTIFICATION_IMAGE_SIGNED_URL_SECONDS", "86400"))
NOTIFICATION_IMAGE_DELETE_DELAY_SECONDS = int(os.getenv("NOTIFICATION_IMAGE_DELETE_DELAY_SECONDS", "900"))

EXPO_PUSH_SEND_URL = os.getenv("EXPO_PUSH_SEND_URL", "https://exp.host/--/api/v2/push/send")
NOTIFICATION_RATE_LIMIT_PER_SECOND = int(os.getenv("NOTIFICATION_RATE_LIMIT_PER_SECOND", "590"))

# ═══════════════════════════════════════════════
# INFRASTRUCTURE — LLM (Groq)
# ═══════════════════════════════════════════════
GROQ_API_KEY    = os.getenv("GROQ_API_KEY",  "")
GROQ_MODEL      = "openai/gpt-oss-20b"
GROQ_TOPIC_MODEL = os.getenv("GROQ_TOPIC_MODEL", "llama-3.3-70b-versatile")
GROQ_TOPIC_MAX_TOKENS = 4000
GROQ_WEEKLY_REVIEW_MAX_TOKENS = 400
GROQ_REQUEST_TIMEOUT_SECONDS = 30

# Training system enums
SPEAKER_LEVEL_VALUES = ("developing", "competent", "advanced")
SUBSCRIPTION_PLAN_VALUES = ("weekly", "monthly")

# Subscription durations and billing
SUBSCRIPTION_WEEKLY_DAYS = 7
SUBSCRIPTION_MONTHLY_DAYS = 30
SUBSCRIPTION_PRICE_WEEKLY = 90
SUBSCRIPTION_PRICE_MONTHLY = 480
RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID", "")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET", "")
RAZORPAY_WEBHOOK_SECRET = os.getenv("RAZORPAY_WEBHOOK_SECRET", "")
RAZORPAY_WEEKLY_PLAN_ID = os.getenv("RAZORPAY_WEEKLY_PLAN_ID", "")
RAZORPAY_MONTHLY_PLAN_ID = os.getenv("RAZORPAY_MONTHLY_PLAN_ID", "")
RAZORPAY_WEEKLY_TOTAL_COUNT = int(os.getenv("RAZORPAY_WEEKLY_TOTAL_COUNT", "52"))
RAZORPAY_MONTHLY_TOTAL_COUNT = int(os.getenv("RAZORPAY_MONTHLY_TOTAL_COUNT", "12"))
RAZORPAY_CURRENCY = os.getenv("RAZORPAY_CURRENCY", "INR")
RAZORPAY_BUSINESS_NAME = os.getenv("RAZORPAY_BUSINESS_NAME", "Speaking Coach")

PLAN_TOPIC_MIN_WORDS = 6
PLAN_SESSION_DURATION_MAX_MINUTES = 2

PLAN_TOPIC_SYSTEM_PROMPT = """
You are a topic generator for a public speaking training application.
Your job is to generate personalized speaking session topics for a user
based on their profile and plan context.

STRICT OUTPUT RULES:
- Respond ONLY with valid JSON. No preamble, no explanation, no markdown.
- The JSON must contain a single top-level key: "topics".
- "topics" must be an array of session topic objects.
- Every topic object must contain:
  day, session, tier, topic_title, target_skill, duration_minutes, resources
- duration_minutes must be an integer less than or equal to 2.
- resources must contain:
  hint, research_prompt, youtube_search
- Every topic_title must be a complete, speakable prompt, not a short label.
- Never repeat a topic that appears in previously_used_topics.
- research_prompt and youtube_search may be null.
- Hints must be actionable and brief.
- For youtube_search, return a search query, not a URL.
"""

WEEKLY_REVIEW_SYSTEM_PROMPT = """
You are a public speaking coach writing a brief weekly review for a user.
You receive pre-computed performance statistics for the week.
Your ONLY job: write a 2-3 sentence narrative summary in second person ("You...").

STRICT RULES:
- Do NOT compute, recalculate, or modify any numeric value.
- Reference the completion_rate, weakest_metric, and strongest_metric by name.
- If missed_days is non-empty, acknowledge it briefly but constructively.
- Output plain text only. No JSON, no markdown, no bullet points.
- Maximum 3 sentences.
"""

REASONING_CLARITY_PROMPT = """
You are a content analysis engine for a public speaking coach. 
Your task: Evaluate a transcript against a given topic title.
Criteria:
1. Relevance: Is the speaker actually talking about the topic?
2. Reasoning: Is the content logical and clear in its flow?
3. Accuracy: Does the speaker seem to have a correct understanding of the topic?

Output: Return ONLY a JSON object with these keys:
- reasoning_clarity_score: float from 0.0 to 1.0
- topic_relevance_score: float from 0.0 to 1.0

Scoring guidance:
- reasoning_clarity_score:
  0.0 = illogical, unclear, or nonsensical reasoning
  1.0 = very logical, clear, and easy to follow reasoning
- topic_relevance_score:
  0.0 = completely off-topic
  1.0 = fully on-topic and consistently relevant
"""
