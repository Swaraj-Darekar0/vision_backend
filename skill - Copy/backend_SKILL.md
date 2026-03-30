---
name: pose-pipeline-backend
description: >
  Use this skill whenever writing, generating, extending, or debugging backend Python/Flask
  code for the Public Speaking Coach App. This skill governs ALL three backend pipelines:
  the Pose (Video) Pipeline, the Audio/Speech Pipeline, and the Final Evaluation Engine.
  Trigger any time the user says "write the code", "implement", "build the pipeline",
  "start development", "create the Flask route", "code the metrics", or references any
  pipeline stage by name — landmark extraction, normalizer, aggregator, derived attributes,
  filler detection, assemblyai transcription, acoustic extractor,
  window aggregator, event detector, score fusion, delta computation, LLM interpreter.
  Also trigger when
  the user asks about file structure, import rules, or data contracts. This skill must
  ALWAYS be read before writing any backend code for this project — it is the single
  source of truth for all three pipelines.
---

# Public Speaking Coach App — Complete Backend Development Skill

---

## 1. Project Overview

This is the Python/Flask backend for a mobile public speaking coaching application.
Users record themselves presenting on their phone. The backend:

1. Analyses body language from the video using MediaPipe → **Pose Pipeline**
2. Analyses speech from the audio using AssemblyAI and Librosa → **Audio Pipeline**
3. Fuses both outputs into composite scores, compares against history, sends a
   read-only JSON to an LLM for coaching feedback → **Evaluation Engine**

**Architecture principle:** The backend is fully deterministic. Every score, delta,
and classification is computed by Python code. The LLM is used only at the final step
for natural language generation — it never computes, classifies, or modifies any number.

---

## 2. Critical Reference Files

Before writing any code, locate and read these two project documents. Never invent
formulas, thresholds, or weights — source them exclusively from these files.

| File | What It Contains | When to Read |
|------|-----------------|--------------|
| `reference_documents/master_formula.md` | Every formula, threshold constant (T1–T7), normalization rule, and composite weight for all three pipelines. The single source of numerical truth. | Before writing ANY metric, score, or weight computation |
| `reference_documents\backend_implementation_plan.md` | Phase-by-phase build plan. Each phase defines Goal, Tasks, Libraries, and Outputs. | Before starting any new module or phase |

**Hard rule:** If a number appears in your code — a threshold, a weight, an FPS value,
a WPM target — it must come from `reference_documents/master_formula.md` and live in `config.py`.
Never hardcode it inline.

---

## 3. Technology Stack

| Layer | Technology | Notes |
|-------|-----------|-------|
| Language | Python 3.10+ | Type hints required throughout |
| Web Framework | Flask 3.x | Blueprint pattern — one per pipeline |
| Pose Detection | MediaPipe 0.10+ | 33-keypoint pose model |
| Video Processing | OpenCV (cv2) 4.x | Frame extraction only |
| Speech Transcription | AssemblyAI SDK (Universal-3 Pro) | Word-level timestamps, raw disfluency preservation, silence markers |
| Audio Features | Librosa 0.10+ | F0, RMS, jitter, energy |
| Audio I/O | SoundFile, PyDub | Format conversion and resampling |
| Numerical Computation | NumPy 1.24+ | All array math |
| Signal Processing | SciPy 1.10+ | Fidget index, jitter filtering |
| NLP (filler context) | spaCy or NLTK | Optional POS tagging for "like" disambiguation |
| Database | Supabase (PostgreSQL) | Session score history — cloud-hosted, accessed via supabase-py |
| DB Client | supabase-py | DB access in db_handler.py only — never SQLite |
| LLM API | Groq (`openai/gpt-4o-mini`) | Read-only JSON interpretation, last step only |

---

## 4. Canonical File Structure

This structure is fixed. Every new file belongs in exactly one location.
The comment on each line is that file's complete job description — nothing more,
nothing less.

```
backend/
│
├── app.py                           # Flask factory — creates app, registers blueprints
├── config.py                        # ALL numeric constants for all three pipelines
├── requirements.txt                 # Pinned dependencies
│
├── pose/                            # ── PIPELINE 1: Video / Pose ──────────────────
│   ├── __init__.py                  # Empty — marks as Python package
│   ├── routes.py                    # Blueprint — POST /pose/analyze endpoint only
│   ├── pipeline.py                  # Orchestrator — calls stages in order, zero math
│   ├── frame_extractor.py           # OpenCV: MP4 → List of RGB frames + timestamps
│   ├── landmark_extractor.py        # MediaPipe: frames → (33,4) pose vectors per frame
│   ├── normalizer.py                # Hip-anchor translation + torso-length scaling
│   ├── metrics.py                   # 10 core posture metric functions (one per metric)
│   ├── aggregator.py                # Frame → 5s Window → Session aggregation
│   ├── derived_attributes.py        # 6 behavioral composite scores from session metrics
│   └── json_builder.py              # Assembles + validates final Pose JSON
│
├── audio/                           # ── PIPELINE 2: Audio / Speech ─────────────────
│   ├── __init__.py
│   ├── routes.py                    # Blueprint — POST /audio/analyze endpoint only
│   ├── pipeline.py                  # Orchestrator — calls stages in order, zero math
│   ├── preprocessor.py              # Mono, 16kHz resample, amplitude normalization
│   ├── transcriber.py               # AssemblyAI Universal-3 Pro: audio → raw transcript + word timestamps
│   ├── filler_detector.py           # Dictionary match + contextual pause-proximity rules
│   ├── acoustic_extractor.py        # Librosa: F0, RMS, jitter, energy variation, pauses
│   ├── timing_metrics.py            # WPM, speech rate score, speech rate instability
│   ├── window_aggregator.py         # 5s window grouping + FumbleScore per window
│   ├── event_detector.py            # 6 timestamp event types flagged from window data
│   ├── derived_attributes.py        # 4 audio behavioral composite scores
│   └── json_builder.py              # Assembles final Audio JSON (5 blocks)
│
├── evaluation/                      # ── PIPELINE 3: Final Evaluation Engine ────────
│   ├── __init__.py
│   ├── routes.py                    # Blueprint — POST /evaluate endpoint only
│   ├── pipeline.py                  # Orchestrator — full eval sequence, zero math
│   ├── input_validator.py           # Validates all required fields in both input JSONs
│   ├── score_fusion.py              # Weighted fusion of pose + audio → 4 composite scores
│   ├── db_handler.py                # ALL database access: fetch history + write session
│   ├── delta_engine.py              # Delta computation + threshold-based classification
│   ├── json_builder.py              # Final evaluation JSON assembly (5 blocks)
│   └── llm_interpreter.py           # Groq API (openai/gpt-4o-mini) — read-only JSON → coaching text
│
└── tests/                           # ── TESTS ──────────────────────────────────────
    ├── conftest.py                  # Shared pytest fixtures for all test files
    ├── test_pose_normalizer.py
    ├── test_pose_metrics.py
    ├── test_pose_aggregator.py
    ├── test_pose_derived_attributes.py
    ├── test_audio_preprocessor.py
    ├── test_audio_filler_detector.py
    ├── test_audio_acoustic_extractor.py
    ├── test_audio_event_detector.py
    ├── test_audio_derived_attributes.py
    ├── test_evaluation_score_fusion.py
    ├── test_evaluation_delta_engine.py
    └── test_evaluation_db_handler.py
```

---

## 5. The Three Laws of Modularity

Every import decision in the codebase is governed by exactly three laws.
Violating any of them breaks the architecture.

### Law 1 — Vertical Isolation (no upward imports)

A stage file must never import from its orchestrator or from a later stage.
`metrics.py` cannot import from `pipeline.py`. `normalizer.py` cannot import
from `aggregator.py`. Data flows **downward only** — passed as arguments from
`pipeline.py` to each stage function in sequence.

```
pipeline.py  →  calls  →  frame_extractor.py
             →  calls  →  landmark_extractor.py
             →  calls  →  normalizer.py
             →  calls  →  metrics.py
             ✅ This direction only. Never the reverse.
```

### Law 2 — Horizontal Isolation (no cross-package imports)

Files inside `pose/` never import from `audio/` or `evaluation/`.
Files inside `audio/` never import from `pose/` or `evaluation/`.
The three packages are siblings with zero dependency on each other.
`evaluation/pipeline.py` receives both pipeline outputs as **function arguments**,
not through imports.

### Law 3 — No Shared Mutable State

No module-level variables are written to during request processing. Every pipeline
run is completely stateless. All intermediate data lives in local variables passed
between functions explicitly.

**One allowed exception:** Module-level objects initialized once at import
time and only *read* during requests — the AssemblyAI API key assignment
(`aai.settings.api_key`) in `audio/transcriber.py` is the canonical example.

---

## 6. File-by-File Responsibility Rules

### Root Files

#### `app.py` — Application Factory
- **Owns:** Flask app creation + blueprint registration only
- **Allowed imports:** `flask`, the three `routes.py` blueprint objects, `logging`
- **Forbidden:** Any stage module, any formula, any config constants
- **Rule:** Always use `create_app()` factory — never instantiate Flask at module level

#### `config.py` — Central Constants Registry
- **Owns:** Every numeric constant used anywhere in the entire backend
- **Allowed imports:** `os` only (for env var reading)
- **Forbidden:** Flask, numpy, any pipeline module, any function or class definition
- **Rules:**
  - Contains only assignment statements — no functions, no logic, no classes
  - `ALL_CAPS_SNAKE_CASE` naming throughout
  - Variable names must match `master_formula_reference.md` exactly so any developer
    can cross-reference instantly
  - Organized into sections with a comment header per pipeline (see Section 9 below)
  - Sensitive values loaded from environment variables:
    ```python
    import os
    DATABASE_URL  = os.getenv("DATABASE_URL", "sqlite:///sessions.db")
    ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY", "")
    ```

---

### Pose Package — File-by-File

#### `pose/__init__.py`
- **Contents:** Empty. Never add imports here.
- Imports in `__init__.py` create hidden coupling — any code importing `from pose import X`
  would silently trigger MediaPipe initialization even if it only needed a utility.

#### `pose/routes.py` — HTTP Boundary
- **Owns:** Blueprint definition + POST `/pose/analyze` handler
- **Allowed imports:** `flask`, `pose.pipeline`, `uuid`, `os`, `logging`
- **Forbidden:** `cv2`, `mediapipe`, `numpy`, any stage module except `pipeline`
- **Responsibility:** Receive upload → validate → save temp → call `run_pose_pipeline()`
  → return JSON response → clean up temp file
- **Must NOT contain:** Any formula, array operation, or threshold comparison

#### `pose/pipeline.py` — Orchestrator
- **Owns:** Call sequence of all pose stages
- **Allowed imports:** All `pose/` stage modules, `logging`
- **Forbidden:** `cv2`, `mediapipe`, `numpy`, `config`
- **Must NOT contain:** Any arithmetic, any threshold comparison, any array operation.
  If you see math in `pipeline.py` it is a violation.
- **Shape — exactly this, no logic between calls:**
  ```python
  def run_pose_pipeline(video_path: str, session_id: str) -> dict:
      frames         = extract_frames(video_path)
      landmarks      = extract_landmarks(frames)
      normalized     = normalize_landmarks(landmarks)
      frame_metrics  = compute_all_metrics(normalized)
      window_scores  = aggregate_windows(frame_metrics)
      session_scores = aggregate_session(window_scores)
      derived        = compute_derived_attributes(session_scores)
      return build_pose_json(session_scores, derived, session_id)
  ```

#### `pose/frame_extractor.py`
- **Owns:** OpenCV video reading and frame extraction
- **Allowed imports:** `cv2`, `numpy`, `logging`, `config` (TARGET_FPS)
- **Key behaviors:**
  - Converts BGR → RGB before returning (MediaPipe requires RGB)
  - Samples frames to match TARGET_FPS if source video FPS is higher
  - Raises `ValueError` with clear message if file cannot be opened
- **Output contract:**
  ```python
  List[Dict]: { "frame": np.ndarray,  "timestamp": float }
  ```

#### `pose/landmark_extractor.py`
- **Owns:** MediaPipe Pose model init and inference
- **Allowed imports:** `mediapipe`, `numpy`, `logging`, `config` (MIN_VISIBILITY_THRESHOLD)
- **Key behaviors:**
  - Initialize `mp.solutions.pose.Pose()` **once before the loop** — never inside it
  - Set `valid=False` when `results.pose_landmarks` is None
  - Set `valid=False` when mean visibility of key landmarks < MIN_VISIBILITY_THRESHOLD
  - Never raise inside the per-frame loop — catch exceptions, mark frame invalid, log warning
  - Call `.close()` on the model after all frames are processed (resource cleanup)
- **Output contract:**
  ```python
  List[Dict]: { "landmarks": np.ndarray,  # shape (33, 4)
                "timestamp": float,
                "valid":     bool }
  ```

#### `pose/normalizer.py`
- **Owns:** Hip-midpoint translation and torso-length scaling
- **Allowed imports:** `numpy`, `logging`
- **Forbidden:** `mediapipe`, `cv2`, `config` — normalization is pure formula, no thresholds
- **Key behaviors:**
  - Passes frames with `valid=False` through unchanged
  - If `torso_length == 0`, marks frame invalid and logs warning — never divides by zero
  - Only modifies X, Y, Z columns — visibility column (index 3) passes through unchanged
  - Landmark index constants (LEFT_HIP=23, RIGHT_HIP=24, etc.) defined at top of this file
    as module-level integers — never imported from elsewhere
- **Output contract:**
  ```python
  List[Dict]: { "landmarks_norm": np.ndarray,  # shape (33, 4)
                "timestamp":      float,
                "valid":          bool }
  ```

#### `pose/metrics.py`
- **Owns:** One public `compute_<metric_name>()` function per metric + one dispatcher
- **Allowed imports:** `numpy`, `scipy.signal`, `logging`, `config` (all T-constants and targets)
- **Forbidden:** `mediapipe`, `cv2` — this file is pure math on normalized arrays
- **Landmark index constants** defined at top of file:
  ```python
  NOSE=0, LEFT_SHOULDER=11, RIGHT_SHOULDER=12, LEFT_HIP=23, RIGHT_HIP=24  # ... all 33
  ```
- **Function naming law:** Function name matches the dict key it produces.
  `compute_shoulder_alignment()` → key `"shoulder_alignment"`. No exceptions.
- **Window-dependent metrics:** Head Stability and Body Sway require std deviation across time.
  These two functions accept `List[Dict]` (a window of frames), not a single frame array.
  Document this clearly in the docstring.
- **Every metric function must:**
  1. Accept typed parameters
  2. Reference threshold constants from `config` by name — never inline numbers
  3. Apply `float(np.clip(score, 0.0, 1.0))` before returning
  4. Return Python `float`, not `np.float64`
  5. Have a docstring citing the exact section in `master_formula_reference.md`
- **Output from dispatcher** `compute_all_metrics()`:
  ```python
  List[Dict]: { "timestamp": float, "shoulder_alignment": float,
                "spine_straightness": float, "posture_openness": float,
                "head_stability": float, "body_sway": float,
                "gesture_score": float, "amplitude_score": float,
                "symmetry_score": float, "fidget_score": float,
                "stillness_score": float }   # all values [0,1]
  ```

#### `pose/aggregator.py`
- **Owns:** Two-level aggregation — keep the two functions separate
- **Allowed imports:** `numpy`, `logging`, `config` (WINDOW_SIZE_SECONDS)
- **Two public functions:**
  - `aggregate_windows(frame_metrics: List[Dict]) -> List[Dict]`
    Groups frames into WINDOW_SIZE_SECONDS windows. Computes mean per metric per window.
    Output includes `time_start`, `time_end`, and all 10 metric means.
  - `aggregate_session(window_scores: List[Dict]) -> Dict`
    Means each metric across all windows → 10-key session dict, all values in [0,1]
- **Why two separate functions:** The `window_scores` list is also consumed by
  `audio/window_aggregator.py` for cross-modal alignment. Keeping it separate allows reuse.

#### `pose/derived_attributes.py`
- **Owns:** 6 weighted behavioral composite computations
- **Allowed imports:** `numpy`, `logging`, `config` (all pose weight dicts)
- **Forbidden:** Anything touching video, frames, or landmarks
- **Structure:** One function per composite + one `compute_all_derived()` dispatcher
- **Output contract:**
  ```python
  Dict: { "movement_variance_normalized": float,  "gaze_stability": float,
          "posture_stability_index": float,        "pose_confidence": float,
          "pose_engagement": float,                "pose_nervousness": float }
  ```

#### `pose/json_builder.py`
- **Owns:** Shape of the Pose JSON output — nothing else
- **Allowed imports:** `logging`, `datetime`
- **Forbidden:** `numpy`, `mediapipe`, `cv2`
- Validates all expected keys are present and in [0,1] before returning.
  Logs a warning for missing keys but does not crash.

---

### Audio Package — File-by-File

#### `audio/routes.py`
- Same pattern as `pose/routes.py`
- Accepts audio file OR MP4 (extracts audio from video using PyDub if needed)
- Links result to existing `session_id` from the pose run so both can be joined downstream

#### `audio/pipeline.py`
- Same orchestrator pattern — zero math, pure sequencing:
  ```python
  def run_audio_pipeline(audio_path: str, session_id: str) -> dict:
      clean_path  = preprocess_audio(audio_path)
      transcript  = transcribe(clean_path)           # AssemblyAI Universal-3 Pro
      fillers     = detect_fillers(transcript)
      acoustics   = extract_acoustic_features(clean_path)
      timing      = compute_timing_metrics(transcript)
      windows     = aggregate_windows(acoustics, timing, fillers, transcript)
      events      = detect_events(windows)
      derived     = compute_derived_attributes(acoustics, timing, fillers)
      return build_audio_json(transcript, acoustics, timing, fillers, derived, events, session_id)
  ```

#### `audio/preprocessor.py`
- **Owns:** Audio format standardization — mono, 16kHz, amplitude normalization
- **Allowed imports:** `librosa`, `soundfile`, `pydub`, `numpy`, `logging`, `config`
- **Output:** File path to preprocessed WAV — not an in-memory array.
  AssemblyAI and Librosa each load the file themselves.

#### `audio/transcriber.py`
- **Owns:** AssemblyAI client configuration and transcription only
- **Allowed imports:** `assemblyai`, `logging`, `config` (all `ASSEMBLYAI_*` constants)
- **Forbidden:** `openai-whisper`, filler detection, WPM computation, any analysis beyond transcription
- **Client configuration rule:** Set `aai.settings.api_key` **once at module level** —
  never inside the `transcribe()` function:
  ```python
  import assemblyai as aai
  from config import ASSEMBLYAI_API_KEY, ASSEMBLYAI_SPEECH_MODEL, \
                     ASSEMBLYAI_PUNCTUATE, ASSEMBLYAI_FORMAT_TEXT, \
                     ASSEMBLYAI_TRANSCRIPTION_PROMPT
  aai.settings.api_key = ASSEMBLYAI_API_KEY   # set once at import time
  ```
- **Model:** Always use `aai.SpeechModel.universal` (Universal-3 Pro).
  Never downgrade to a lighter model — raw disfluency preservation requires this model.
- **TranscriptionConfig must set:**
  - `speech_model = aai.SpeechModel.universal`
  - `punctuate = ASSEMBLYAI_PUNCTUATE` (True)
  - `format_text = ASSEMBLYAI_FORMAT_TEXT` (False — disables text cleaning,
    preserves fillers, repeated words, and disfluencies exactly as spoken)
  - The prompt string from `ASSEMBLYAI_TRANSCRIPTION_PROMPT` instructs the model to:
    represent audible silences as `...`, include all `um`/`uh`/`hmm`/`erm` exactly,
    preserve consecutive repeated words both times (e.g. "the the garden"), and
    never clean, deduplicate, or grammar-correct the output
- **Timestamp conversion:** AssemblyAI returns timestamps in milliseconds.
  Always divide by 1000.0 before storing — all downstream files expect seconds.
- **Error handling:** If `result.status == aai.TranscriptStatus.error`, raise
  `RuntimeError` with `result.error`. Let `pipeline.py` catch it.
- **speaking_duration_seconds** = `words[-1]["end"] − words[0]["start"]` in seconds.
  This is the actual speech span — used by `timing_metrics.py` for WPM.
  Do NOT use total audio file duration here.
- **total_words**: Count from `len(words)` — not from `len(full_text.split())`.
  Splitting on spaces will miscount repeated words and filler tokens.
- **Output contract — identical to before, downstream files unchanged:**
  ```python
  Dict: { "full_text":                  str,         # raw unformatted, fillers included
          "segments":                   List[Dict],  # {start: float, end: float, text: str}
          "words":                      List[Dict],  # {word: str, start: float, end: float, confidence: float}
          "total_words":                int,
          "speaking_duration_seconds":  float }
  ```
- **Implementation template:**
  ```python
  def transcribe(audio_path: str) -> dict:
      """
      Transcribes audio using AssemblyAI Universal-3 Pro.
      Preserves fillers, repetitions, and silence markers exactly as spoken.
      Timestamps converted from ms to seconds before returning.
      """
      config = aai.TranscriptionConfig(
          speech_model = aai.SpeechModel.universal,
          punctuate    = ASSEMBLYAI_PUNCTUATE,
          format_text  = ASSEMBLYAI_FORMAT_TEXT,
      )
      result = aai.Transcriber().transcribe(audio_path, config=config)

      if result.status == aai.TranscriptStatus.error:
          raise RuntimeError(f"AssemblyAI error: {result.error}")

      words = [
          {"word": w.text, "start": w.start / 1000.0,
           "end": w.end / 1000.0, "confidence": w.confidence}
          for w in result.words
      ]
      speaking_duration = (words[-1]["end"] - words[0]["start"]) if words else 0.0

      return {
          "full_text":                 result.text or "",
          "segments":                  _build_segments(result, words),
          "words":                     words,
          "total_words":               len(words),
          "speaking_duration_seconds": speaking_duration,
      }
  ```

#### `audio/filler_detector.py`
- **Owns:** Filler word identification with contextual validation
- **Allowed imports:** `logging`, `config` (FILLER_WORDS, FILLER_PAUSE_CONTEXT),
  optionally `spacy` or `nltk` for POS tagging
- **Input:** `words` list from transcriber output
- **Both conditions must pass to flag as filler:**
  1. Word exists in `FILLER_WORDS` set (from config)
  2. `pause_before > FILLER_PAUSE_CONTEXT` OR `pause_after > FILLER_PAUSE_CONTEXT`
  3. For "like" specifically: if followed by a noun phrase → valid usage, not a filler
- **Output contract:**
  ```python
  Dict: { "filler_count":              int,
          "filler_ratio":              float,
          "filler_ratio_normalized":   float,    # [0,1] clamped
          "filler_words_used":         Dict[str, int] }  # per-word counts
  ```

#### `audio/acoustic_extractor.py`
- **Owns:** All Librosa feature extraction
- **Allowed imports:** `librosa`, `numpy`, `scipy`, `logging`, `config` (all audio thresholds)
- **Takes:** Preprocessed audio file path
- **Returns raw arrays alongside scalar scores** because `window_aggregator.py` needs
  per-window slices of the arrays for windowed computation
- **Output contract:**
  ```python
  Dict: { "f0_array":                     np.ndarray,   # Hz per frame
          "rms_array":                    np.ndarray,   # energy per frame
          "pitch_variance_normalized":    float,        # [0,1]
          "jitter_normalized":            float,        # [0,1]
          "energy_variation_normalized":  float,        # [0,1]
          "pause_ratio":                  float }       # [0,1]
  ```

#### `audio/timing_metrics.py`
- **Owns:** WPM calculation, speech rate score, speech rate instability
- **Allowed imports:** `numpy`, `logging`, `config` (OPTIMAL_WPM, WINDOW_SIZE_SECONDS, thresholds)
- **Key rule:** SpeechRate divides total words by *speaking* duration — pause time excluded
- **Output contract:**
  ```python
  Dict: { "speech_rate_wpm":                    float,
          "speech_rate_score":                  float,        # [0,1]
          "speech_rate_instability_normalized": float,        # [0,1]
          "wpm_per_window":                     List[float] } # needed by window_aggregator
  ```

#### `audio/window_aggregator.py`
- **Owns:** 5-second window grouping and FumbleScore computation
- **Allowed imports:** `numpy`, `logging`, `config` (WINDOW_SIZE_SECONDS, FUMBLE_SCORE_WEIGHTS)
- **Output contract — one dict per 5-second window:**
  ```python
  List[Dict]: { "window_index":                       int,
                "time_start":                         float,
                "time_end":                           float,
                "filler_ratio":                       float,
                "pause_ratio":                        float,
                "pitch_variance_normalized":          float,
                "speech_rate_wpm":                    float,
                "speech_rate_instability_normalized": float,
                "fumble_score":                       float }  # [0,1]
  ```

#### `audio/event_detector.py`
- **Owns:** All 6 event type detection
- **Allowed imports:** `numpy`, `logging`, `config` (all event threshold constants)
- **Event type string constants — defined here, imported by json_builder, never duplicated:**
  ```python
  EVENT_HIGH_FUMBLE       = "high_fumble_spike"
  EVENT_EXCESSIVE_PAUSE   = "excessive_pause"
  EVENT_RAPID_SPEECH      = "rapid_speech_segment"
  EVENT_MONOTONE          = "monotone_segment"
  EVENT_VOCAL_INSTABILITY = "vocal_instability_spike"
  EVENT_ADAPTIVE_SPIKE    = "adaptive_spike"
  ```
- **Adaptive spike detection:** Computes `Delta_k = FumbleScore_k − session_mean(FumbleScore)`,
  flags if `Delta_k > ADAPTIVE_SPIKE_STD_MULTIPLIER × session_std`. Speaker-relative, not absolute.
- **Output contract:**
  ```python
  List[Dict]: { "time_start": float, "time_end": float, "event": str }
  ```

#### `audio/derived_attributes.py`
- Same structural pattern as `pose/derived_attributes.py`
- 4 composites: AudioInstability, AudioConfidence, AudioEngagement, AudioNervousness
- AudioNervousness = AudioInstability (same formula, different semantic framing — document this)
- All weights from `config.py`, all formulas from `master_formula_reference.md` Section 7
- **Output contract:**
  ```python
  Dict: { "audio_instability":  float, "audio_confidence": float,
          "audio_engagement":   float, "audio_nervousness": float }
  ```

#### `audio/json_builder.py`
- Assembles all 5 required blocks:
  `transcript`, `acoustic_metrics`, `filler_words_used`,
  `derived_audio_attributes`, `timestamp_events`

---

### Evaluation Package — File-by-File

#### `evaluation/routes.py`
- Accepts `pose_json` and `audio_json` as POST body fields, plus `user_id`
- Same error-handling wrapper pattern as other pipeline routes

#### `evaluation/pipeline.py`
- The most critical orchestrator — enforces the mandatory sequence:
  ```python
  def run_evaluation_pipeline(pose_data: dict, audio_data: dict, user_id: str) -> dict:
      # 1. Validate inputs — reject early if fields are missing
      valid, err = validate_inputs(pose_data, audio_data)
      if not valid:
          raise ValueError(err)

      # 2. Fuse scores from both pipelines
      scores = fuse_scores(pose_data, audio_data)

      # 3. Fetch history BEFORE writing (diff against prior session)
      baseline = fetch_baseline(user_id)

      # 4. Compute deltas and classifications
      progress = compute_deltas(scores, baseline)

      # 5. WRITE TO DB — must happen before LLM call
      #    If LLM fails, scores are still saved.
      write_session(user_id, scores, pose_data, audio_data)

      # 6. Assemble final read-only JSON package
      final_json = build_evaluation_json(scores, progress, audio_data, pose_data, user_id)

      # 7. LLM interpretation — read-only, always last
      feedback = interpret_with_llm(final_json)

      return {**final_json, "llm_feedback": feedback}
  ```

#### `evaluation/input_validator.py`
- **Returns** `(bool, str)` — never raises exceptions
- Required field lists defined as module-level constants (doubles as input contract docs)
- Validates: field presence, value type is `float`, value in range `[0.0, 1.0]`

#### `evaluation/score_fusion.py`
- **Owns:** Cross-modal weighted arithmetic only — 4 composites + overall
- **Allowed imports:** `numpy`, `logging`, `config` (all fusion weight dicts)
- **Forbidden:** DB access, LLM calls, file I/O
- **Input:** pose derived dict + audio derived dict
- **Output contract:**
  ```python
  Dict: { "confidence":  float, "clarity":     float,
          "engagement":  float, "nervousness":  float,
          "overall":     float }   # all [0,1]
  ```

#### `evaluation/db_handler.py`
- **This is the only file in the entire backend that touches the database**
- **Allowed imports:** `supabase`, `logging`, `config` (`SUPABASE_URL`, `SUPABASE_KEY`,
  `ROLLING_BASELINE_SESSIONS`)
- **Forbidden:** `sqlite3`, `sqlalchemy`, score computation, delta arithmetic, LLM calls
- **Client initialization:** Create the Supabase client once at module level:
```python
  from supabase import create_client
  from config import SUPABASE_URL, SUPABASE_KEY
  _db = create_client(SUPABASE_URL, SUPABASE_KEY)
```
- **fetch_baseline pattern:**
```python
  res = _db.table("session_scores") \
            .select("*") \
            .eq("user_id", user_id) \
            .order("session_date", desc=True) \
            .limit(ROLLING_BASELINE_SESSIONS) \
            .execute()
  rows = res.data
```
- **write_session pattern:**
```python
  res = _db.table("session_scores").insert(row_dict).execute()
  return len(res.data) > 0
```
- **Two public functions:**
  ```python
  def fetch_baseline(user_id: str) -> dict | None:
      """
      Returns previous session scores as dict.
      Uses rolling average of last ROLLING_BASELINE_SESSIONS sessions.
      Returns None if no history exists (first session).
      """

  def write_session(user_id: str, scores: dict,
                    pose_data: dict, audio_data: dict) -> bool:
      """
      Writes current session to session_scores table.
      Returns True on success, False on failure. Never raises.
      """
  ```
- **DB schema** (created on first run if not exists):
  ```sql
  CREATE TABLE IF NOT EXISTS session_scores (
      session_id                TEXT PRIMARY KEY,
      user_id                   TEXT NOT NULL,
      session_date              DATETIME NOT NULL,
      confidence                REAL,
      clarity                   REAL,
      engagement                REAL,
      nervousness               REAL,
      overall                   REAL,
      filler_ratio              REAL,
      pitch_variance_normalized REAL,
      posture_stability_index   REAL,
      pause_ratio               REAL,
      gesture_score             REAL
  );
  ```

#### `evaluation/delta_engine.py`
- **Owns:** Delta arithmetic and threshold-based classification — nothing else
- **Allowed imports:** `numpy`, `logging`, `config` (all classification thresholds)
- **Forbidden:** DB access, LLM calls, file I/O
- **Input:** `current_scores: dict`, `baseline: dict | None`
- **If baseline is None:** All deltas return as `None`, classification `"Baseline Session"`
- **Behavioral delta directions** (positive value = improvement in each case):
  - `filler_change = baseline_filler − current_filler` (lower filler is better)
  - `pause_ratio_change = baseline_pause − current_pause` (lower pause is better)
  - `posture_stability_change = current − baseline` (higher stability is better)
  - `pitch_variance_change = current − baseline` (context-dependent — document inline)
- **Classification from config thresholds:**
  - `> SIGNIFICANT_IMPROVEMENT_THRESHOLD` → `"Significant Improvement"`
  - `> MODERATE_IMPROVEMENT_THRESHOLD` → `"Moderate Improvement"`
  - within ±MODERATE range → `"Stable"`
  - `< NOTICEABLE_DECLINE_THRESHOLD` → `"Noticeable Decline"`

#### `evaluation/json_builder.py`
- **Assembles 5 blocks of the Final Evaluation JSON:**
  1. `overall_scores` — confidence, clarity, engagement, nervousness, overall
  2. `progress_comparison` — headline, psychological, skill, behavioral delta sub-blocks
  3. `timestamp_events` — passed through from audio JSON unchanged
  4. `raw_metrics_snapshot` — all pose + audio raw metrics for app UI drill-down
  5. `session_metadata` — session_id, user_id, date, duration, is_first_session

#### `evaluation/llm_interpreter.py`
- **This is the only file that calls the Groq API**
- **Allowed imports:** `groq`, `json`, `logging`, `config` (`GROQ_API_KEY`, `GROQ_MODEL`)
- **Client initialization:** Create the Groq client once at module level:
```python
  from groq import Groq
  from config import GROQ_API_KEY, GROQ_MODEL
  _client = Groq(api_key=GROQ_API_KEY)
```
- **API call pattern:**
```python
  response = _client.chat.completions.create(
      model=GROQ_MODEL,
      messages=[
          {"role": "system", "content": SYSTEM_PROMPT},
          {"role": "user",   "content": json.dumps(evaluation_json)}
      ]
  )
  raw = response.choices[0].message.content
  return json.loads(raw)
```
- **System prompt** as module-level constant:
  ```python
  SYSTEM_PROMPT = """
  You are a public speaking coach. You receive a pre-computed evaluation JSON.
  Your ONLY job: interpret the provided scores and generate coaching feedback.

  HARD RULES:
  - Do NOT compute, recalculate, or modify any numeric value
  - Do NOT fetch or reference external data
  - Do NOT reclassify deltas — classifications are already in the JSON
  - Reference timestamp events by exact times from timestamp_events list
  - Output must be valid JSON with this exact structure:
    {
      "overall_summary":        "<2-3 sentence session summary>",
      "progress_narrative":     "<progress since last session>",
      "timestamped_moments":    [{"time": "MM:SS", "note": "<observation>"}],
      "top_3_action_items":     ["<item>", "<item>", "<item>"],
      "motivational_closing":   "<1 encouraging sentence>"
    }
  """
  ```
- **Failure handling:** If API call fails, returns fallback dict with empty coaching fields
  and `"llm_available": false`. Evaluation response is still returned with all scores.
- **Never called** from any file other than `evaluation/pipeline.py`

---

### Tests Package

#### `tests/conftest.py` — Shared Fixtures
Provides pre-built fixtures so individual test files have zero setup duplication:
- `sample_normalized_frame` — valid (33,4) landmarks_norm ndarray
- `sample_frame_metrics_list` — 90 frames of metric dicts (3s at 30fps)
- `sample_window_list` — 3 window dicts with all required fields
- `sample_session_scores` — 10-key session dict, all values in [0,1]
- `sample_pose_json` — complete valid Pose JSON
- `sample_audio_json` — complete valid Audio JSON

#### Test Rules
- Test stage functions directly — never spin up a Flask server for unit tests
- Every metric test must assert output is `float` and in `[0.0, 1.0]`
- `test_pose_normalizer.py` must cover: torso_length=0 does not raise,
  `valid=False` frames pass through unchanged, visibility column preserved
- `test_audio_filler_detector.py` must cover: clear filler, clear non-filler,
  "like" before noun (valid), "like" after pause (filler)
- `test_audio_event_detector.py` must test each of the 6 event types independently
- `test_evaluation_delta_engine.py` must cover: first session, all 4 classification
  labels, behavioral delta direction correctness for each field

---

## 7. Complete Import Dependency Graph

Every allowed import path is shown here. Any arrow not in this graph is forbidden.

```
app.py
  ├─ pose/routes.py
  │      └─ pose/pipeline.py
  │               ├─ pose/frame_extractor.py      ← config
  │               ├─ pose/landmark_extractor.py   ← config
  │               ├─ pose/normalizer.py
  │               ├─ pose/metrics.py              ← config
  │               ├─ pose/aggregator.py           ← config
  │               ├─ pose/derived_attributes.py   ← config
  │               └─ pose/json_builder.py
  │
  ├─ audio/routes.py
  │      └─ audio/pipeline.py
  │               ├─ audio/preprocessor.py        ← config
  │               ├─ audio/transcriber.py         ← config
  │               ├─ audio/filler_detector.py     ← config
  │               ├─ audio/acoustic_extractor.py  ← config
  │               ├─ audio/timing_metrics.py      ← config
  │               ├─ audio/window_aggregator.py   ← config
  │               ├─ audio/event_detector.py      ← config
  │               ├─ audio/derived_attributes.py  ← config
  │               └─ audio/json_builder.py
  │
  └─ evaluation/routes.py
         └─ evaluation/pipeline.py
                  ├─ evaluation/input_validator.py
                  ├─ evaluation/score_fusion.py      ← config
                  ├─ evaluation/db_handler.py        ← config
                  ├─ evaluation/delta_engine.py      ← config
                  ├─ evaluation/json_builder.py
                  └─ evaluation/llm_interpreter.py   ← config

config  ←  read by stage files only. Never by routes or pipeline orchestrators.
```

---

## 8. End-to-End Data Flow

```
Mobile App (React Native)
     │
     ├─ POST /pose/analyze (MP4 video)
     │       └─ frame_extractor
     │              → landmark_extractor
     │              → normalizer
     │              → metrics (10 functions)
     │              → aggregator (window + session)
     │              → derived_attributes (6 composites)
     │              → json_builder
     │                  └─► Pose JSON
     │
     ├─ POST /audio/analyze (audio/MP4)
     │       └─ preprocessor
     │              → transcriber (AssemblyAI Universal-3 Pro)
     │              → filler_detector
     │              → acoustic_extractor (Librosa)
     │              → timing_metrics
     │              → window_aggregator (FumbleScore)
     │              → event_detector (6 event types)
     │              → derived_attributes (4 composites)
     │              → json_builder
     │                  └─► Audio JSON
     │
     └─ POST /evaluate (Pose JSON + Audio JSON + user_id)
             └─ input_validator
                    → score_fusion (4 composites + overall)
                    → db_handler.fetch_baseline
                    → delta_engine (deltas + classifications)
                    → db_handler.write_session  ← BEFORE LLM
                    → json_builder (5 blocks)
                    → llm_interpreter (read-only)
                        └─► Final Response to App
```

---

## 9. config.py — Complete Skeleton

Write `config.py` first, before any pipeline code.
Fill all `...` values by reading `master_formula_reference.md`.

```python
# config.py
import os

# ═══════════════════════════════════════════════
# POSE — VIDEO SETTINGS
# ═══════════════════════════════════════════════
TARGET_FPS                      = 30
MIN_VISIBILITY_THRESHOLD        = 0.5

# ═══════════════════════════════════════════════
# POSE — METRIC THRESHOLDS  (T1–T7)
# Source: master_formula_reference.md Section 4
# ═══════════════════════════════════════════════
SHOULDER_ALIGNMENT_THRESHOLD    = ...   # T1
SPINE_STRAIGHTNESS_THRESHOLD    = ...   # T2 (radians)
HEAD_STABILITY_THRESHOLD        = ...   # T3
BODY_SWAY_THRESHOLD             = ...   # T4
FIDGET_THRESHOLD                = ...   # T5
MOVEMENT_VARIANCE_THRESHOLD     = ...   # T6
GAZE_DEVIATION_THRESHOLD        = ...   # T7

POSTURE_OPENNESS_MAX_WIDTH      = ...
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
POSE_NERVOUSNESS_WEIGHTS    = { ... }
POSE_CONFIDENCE_WEIGHTS     = { ... }
POSE_ENGAGEMENT_WEIGHTS     = { ... }

# ═══════════════════════════════════════════════
# AUDIO — ASSEMBLYAI TRANSCRIPTION
# Model: Universal-3 Pro — do not downgrade
# ═══════════════════════════════════════════════
ASSEMBLYAI_API_KEY              = os.getenv("ASSEMBLYAI_API_KEY", "")
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
# AUDIO — PREPROCESSING
# ═══════════════════════════════════════════════
AUDIO_SAMPLE_RATE               = 16000

# ═══════════════════════════════════════════════
# AUDIO — ACOUSTIC THRESHOLDS
# Source: master_formula_reference.md Section 4
# ═══════════════════════════════════════════════
PITCH_VARIANCE_MIN              = 0.05
PITCH_VARIANCE_MAX              = 0.50
JITTER_THRESHOLD                = ...   # T1 audio
ENERGY_VAR_THRESHOLD            = ...   # T2 audio
PAUSE_RMS_THRESHOLD             = ...   # theta — silence energy floor
SPEECH_RATE_INSTABILITY_THRESH  = ...   # T3 audio
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
AUDIO_INSTABILITY_WEIGHTS   = { ... }
AUDIO_CONFIDENCE_WEIGHTS    = { ... }
AUDIO_ENGAGEMENT_WEIGHTS    = { ... }

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
# Source: master_formula_reference.md — Fusion Layer
# ═══════════════════════════════════════════════
CONFIDENCE_FUSION_WEIGHTS   = { ... }
CLARITY_FUSION_WEIGHTS      = { ... }
ENGAGEMENT_FUSION_WEIGHTS   = { ... }
NERVOUSNESS_FUSION_WEIGHTS  = { ... }
OVERALL_FUSION_WEIGHTS      = { ... }

# ═══════════════════════════════════════════════
# EVALUATION — PROGRESS CLASSIFICATION
# Source: master_formula_reference.md Section 5
# ═══════════════════════════════════════════════
SIGNIFICANT_IMPROVEMENT_THRESHOLD   = 0.05
MODERATE_IMPROVEMENT_THRESHOLD      = 0.02
NOTICEABLE_DECLINE_THRESHOLD        = -0.05
ROLLING_BASELINE_SESSIONS           = 3

# ═══════════════════════════════════════════════
# INFRASTRUCTURE — DATABASE (Supabase)
# ═══════════════════════════════════════════════
SUPABASE_URL    = os.getenv("SUPABASE_URL",  "")
SUPABASE_KEY    = os.getenv("SUPABASE_KEY",  "")   # anon/service role key

# ═══════════════════════════════════════════════
# INFRASTRUCTURE — LLM (Groq)
# ═══════════════════════════════════════════════
GROQ_API_KEY    = os.getenv("GROQ_API_KEY",  "")
GROQ_MODEL      = "openai/gpt-4o-mini"             # do not change without team sign-off

# Note: ASSEMBLYAI_API_KEY is defined above in the AssemblyAI section
```

---

## 10. Code Templates

### Flask Route (all three pipelines — same pattern)

```python
from flask import Blueprint, request, jsonify
from <package>.pipeline import run_<package>_pipeline
import uuid, os, logging

<pkg>_bp = Blueprint("<package>", __name__, url_prefix="/<url>")
logger   = logging.getLogger(__name__)

@<pkg>_bp.route("/analyze", methods=["POST"])
def analyze():
    if "<file_field>" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file       = request.files["<file_field>"]
    session_id = str(uuid.uuid4())
    tmp_path   = f"/tmp/{session_id}.<ext>"
    file.save(tmp_path)
    logger.info(f"[{session_id}] Starting pipeline")

    try:
        result = run_<package>_pipeline(tmp_path, session_id)
        return jsonify(result), 200
    except Exception as e:
        logger.error(f"[{session_id}] Pipeline failed: {e}")
        return jsonify({"error": "Processing failed"}), 500
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
```

### Metric / Score Function (all computation functions)

```python
def compute_<metric_name>(<input>: np.ndarray) -> float:
    """
    <One sentence: what this measures and what 1.0 means>.
    Source: master_formula_reference.md Section <N>, Metric <N>.
    Returns float in [0, 1].
    """
    raw = <formula — reference config constants by name, never inline numbers>
    return float(np.clip(raw, 0.0, 1.0))
```

### Per-Frame Stage Error Handling (all stage files)

```python
logger = logging.getLogger(__name__)

def <stage_function>(input_list: list) -> list:
    results = []
    for item in input_list:
        try:
            processed = <process item>
            results.append({**processed, "valid": True})
        except Exception as e:
            logger.warning(f"Stage failed at t={item.get('timestamp')}: {e}")
            results.append({"timestamp": item.get("timestamp"), "valid": False})
    return results
```

### Weighted Composite (derived_attributes.py — all three pipelines)

```python
from config import <WEIGHT_DICT>
import numpy as np

def compute_<composite_name>(scores: dict) -> float:
    """
    Weighted composite.
    Source: master_formula_reference.md Section <N>.<N>.
    """
    w   = <WEIGHT_DICT>
    raw = sum(w[key] * scores[key] for key in w)
    return float(np.clip(raw, 0.0, 1.0))
```

### app.py Factory

```python
from flask import Flask
from pose.routes       import pose_bp
from audio.routes      import audio_bp
from evaluation.routes import eval_bp
import logging

def create_app() -> Flask:
    app = Flask(__name__)
    logging.basicConfig(level=logging.INFO)
    app.register_blueprint(pose_bp)
    app.register_blueprint(audio_bp)
    app.register_blueprint(eval_bp)
    return app

if __name__ == "__main__":
    create_app().run(debug=True, port=5000)
```

---

## 11. Absolute Enforcement Rules

Flag a violation immediately if any of these are broken in generated code.

| # | Rule | Scope |
|---|------|-------|
| 1 | No magic numbers — every constant in `config.py`, sourced from `master_formula_reference.md` | All files |
| 2 | No math or threshold comparisons in `pipeline.py` or `routes.py` | All 3 pipelines |
| 3 | No LLM API calls outside `evaluation/llm_interpreter.py` | Entire codebase |
| 4 | No database access outside `evaluation/db_handler.py` | Entire codebase |
| 5 | All output scores clamped with `float(np.clip(val, 0.0, 1.0))` before returning | Every metric + score function |
| 6 | No `print()` — use `logging` throughout | Every file |
| 7 | DB write happens before LLM call — enforced in `evaluation/pipeline.py` | Evaluation orchestrator |
| 8 | Invalid/failed frames skipped with logged warning, never raise and crash | All per-frame loops |
| 9 | Type hints on every public function signature | Every file |
| 10 | One public function per metric in `metrics.py` — no bundled metric functions | `pose/metrics.py` |
| 11 | No cross-package imports — `pose/` never imports from `audio/` or `evaluation/` | All package files |
| 12 | AssemblyAI client API key set once at module level (`aai.settings.api_key`), never per request | `audio/transcriber.py` |
| 13 | `__init__.py` files are always empty | All 3 packages |
| 14 | `config.py` contains only assignment statements — no functions, classes, or logic | `config.py` |
| 15 | Build phases in order — `config.py` first, then stage files, then pipeline orchestrator last | Build sequence |
