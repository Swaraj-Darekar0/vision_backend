**PUBLIC SPEAKING COACH APP**
Backend Implementation Plan — Phase-Wise Development Guide
Stack: Python · Flask · MediaPipe · AssemblyAI · Librosa · Supabase (PostgreSQL) · Groq


> 📌 Formula Reference:  All mathematical formulas, normalization rules, threshold constants (T1–T7), and weighted composite definitions referenced in this document are defined in  master_formula_reference.md  — treat that file as the single source of truth for all metric computations.



> 🏗️ Architecture Note:  The backend is fully deterministic. The LLM layer (final step) receives a read-only JSON package and is used exclusively for interpretation and coaching language generation. It never computes scores, fetches data, or modifies numeric values.


## 1.  Project Backend Overview
The backend is structured around three independent processing pipelines that run sequentially per user session. Each pipeline is a self-contained Flask service (or Flask Blueprint) that accepts its inputs, computes its outputs, and emits a structured JSON object consumed by the next stage.

| Pipeline | Input | Output JSON |
| --- | --- | --- |
| ① Pose Pipeline | MP4 video file | posture_metrics + derived_pose_attributes |
| ② Audio Pipeline | Audio file (WAV/MP4) | acoustic_metrics + derived_audio_attributes + timestamp_events |
| ③ Final Evaluation Engine | Pose JSON + Audio JSON + DB history | overall_scores + progress_comparison + feedback |

## 2.  Pipeline 1 — Pose (Video) Pipeline

## 2.1  Purpose
Accepts an MP4 video recording from the mobile camera, extracts body keypoints frame-by-frame, normalizes the coordinate space, computes 10 core posture metrics per frame, aggregates them across windows and the full session, and derives 6 high-level behavioral attributes.
## 2.2  Core Libraries
- flask: HTTP endpoint to receive video upload and return JSON
- mediapipe: Pose landmark detection — 33 keypoints per frame (x, y, z, visibility)
- opencv-python: Video file reading and frame extraction at target FPS
- numpy: Array operations, statistical computation (std, mean), vector math
- scipy: Signal processing for fidget index and high-frequency residual energy
- json: Output serialization to structured JSON


### PHASE 1  —  Flask Endpoint & Video Ingestion

**Goal:**
Create a Flask route that accepts a video file upload, validates it, saves it temporarily, and queues it for processing.

**Tasks:**
- Create POST /pose/analyze endpoint
- Validate file type (MP4) and size limits
- Save uploaded file to temp directory with unique session ID
- Return 202 Accepted with session_id for async polling, or process synchronously for MVP

**Libraries:**
- flask
- werkzeug (file handling)
- uuid
- os
- tempfile

**Outputs:**
- Video file saved to disk
- session_id generated
- HTTP 202 or 200 response


### PHASE 2  —  Frame Extraction

**Goal:**
Extract individual frames from the video at a fixed FPS using OpenCV.

**Tasks:**
- Open video file with cv2.VideoCapture
- Determine video FPS and total frame count
- Extract frames at target rate (30 FPS or configurable)
- Convert each frame from BGR to RGB for MediaPipe compatibility
- Store frames as in-memory array or temp files indexed by frame number and timestamp

**Libraries:**
- opencv-python (cv2)
- numpy

**Outputs:**
- List of RGB frames with timestamps
- Frame metadata: total_frames, fps, duration_seconds


### PHASE 3  —  MediaPipe Landmark Extraction

**Goal:**
Run MediaPipe Pose on each frame and extract the 33-landmark pose vector.

**Tasks:**
- Initialize mp.solutions.pose.Pose() with desired confidence thresholds
- Run model.process(frame) on each RGB frame
- Extract all 33 landmarks: x, y, z, visibility per landmark
- Store as Pose_Vector_t — shape (33, 4) per frame
- Handle frames where pose is not detected — mark as null or skip
- Map landmark indices to named constants matching master_formula_reference.md

**Libraries:**
- mediapipe
- numpy

**Outputs:**
- Per-frame pose vectors: list of shape (33, 4)
- Visibility flags for downstream filtering


### PHASE 4  —  Coordinate Normalization

**Goal:**
Translate and scale all landmark coordinates so they are speaker-agnostic and position-independent.

**Tasks:**
- Compute hip_mid = mean of left_hip and right_hip positions
- Subtract hip_mid from all 33 landmarks (translation)
- Compute torso_length = Euclidean distance from shoulder_mid to hip_mid
- Divide all translated coordinates by torso_length (scaling)
- Output normalized landmark set K_i_prime per frame
- Refer to master_formula_reference.md Section 3 for exact formula

**Libraries:**
numpy

**Outputs:**
- Normalized per-frame landmark array K_i_prime
- Torso length values stored for debugging


### PHASE 5  —  10 Core Posture Metrics — Frame-Level Computation

**Goal:**
Compute all 10 posture metrics for each normalized frame independently.

**Tasks:**
- Shoulder Alignment: compute vertical delta between shoulder Y positions
- Spine Straightness: compute angle of spine vector against vertical reference using arccos
- Posture Openness: compute horizontal spread between shoulders
- Head Stability: compute std deviation of nose X position across a rolling window
- Body Sway: compute std deviation of hip_mid X position across a rolling window
- Gesture Frequency: detect wrist displacements exceeding threshold sustained for >0.3s, count per minute
- Hand Movement Amplitude: measure max wrist displacement from neutral per gesture event, take mean
- Symmetry Score: compare motion energy of left vs right wrist over window
- Fidget Index: extract high-frequency residual energy from wrist motion after removing intentional gestures
- Stillness Ratio: count frames where total joint displacement is below stillness threshold
- Apply normalization formula for each metric (refer master_formula_reference.md Section 4)
- Clamp all output values to [0, 1]

**Libraries:**
- numpy
- scipy.signal (for fidget frequency filtering)

**Outputs:**
- Per-frame dict of 10 metric raw values
- Per-frame dict of 10 metric normalized scores [0,1]


### PHASE 6  —  Three-Tier Aggregation

**Goal:**
Aggregate frame-level metrics into window-level and then session-level scores.

**Tasks:**
- Group frames into 5–10 second windows
- Compute mean of each metric within each window — WindowScore_k
- Compute mean of all WindowScore_k values across session — FinalMetric
- Store per-window values for downstream timestamp event detection
- Refer to master_formula_reference.md Section 5 for aggregation formulas

**Libraries:**
numpy

**Outputs:**
- Per-window metric scores dict
- Final session-level score per metric (10 values)


### PHASE 7  —  Derived Behavioral Attributes

**Goal:**
Compute 6 high-level behavioral indices from the aggregated metric scores.

**Tasks:**
- Movement Variance: std of total joint displacement across session, normalize
- Gaze Stability: mean nose-to-shoulder deviation across session, normalize
- Posture Stability Index: weighted combination — refer master_formula_reference.md Section 6.3
- Pose Nervousness Score: weighted combination — refer master_formula_reference.md Section 6.4
- Pose Confidence Score: weighted combination — refer master_formula_reference.md Section 6.5
- Pose Engagement Score: weighted combination — refer master_formula_reference.md Section 6.6

**Libraries:**
numpy

**Outputs:**
- 6 derived attribute scores [0,1]
- All values named as in master_formula_reference.md


### PHASE 8  —  Pose JSON Builder & Response

**Goal:**
Assemble the final Pose JSON object and return it from the Flask endpoint.

**Tasks:**
- Populate posture_metrics block: all 10 normalized session scores
- Populate derived_pose_attributes block: 6 derived values
- Include session metadata: session_id, duration_seconds, frames_processed
- Serialize to JSON and return as Flask Response with 200 status
- Log any frames skipped due to low visibility or detection failure

**Libraries:**
- json
- flask

**Outputs:**
pose_output.json with posture_metrics and derived_pose_attributes blocks

## 3.  Pipeline 2 — Audio / Speech Pipeline

## 3.1  Purpose
Accepts the audio track from the recording (or extracted audio from video), runs transcription with word-level timestamps via Whisper, extracts acoustic features via Librosa, detects filler words with contextual rules, computes speech timing metrics, flags timestamp events, and derives 4 high-level audio behavioral attributes.
## 3.2  Core Libraries
- flask: HTTP endpoint to receive audio and return JSON
- assembly_ai: Speech-to-text transcription with word-level timestamps(using there universal model 3 pro with using prompt to set the model and include trencsribe silence with '...' and also umm's and uhh's if if spoken by the user, we also want repeated words (i.e is user speaks 'the the garen ..' include the the both the times ) , we don't want a cleaned text but raw spoken transcribe text as it is)
- librosa: Pitch extraction (F0), RMS energy, spectral features, audio loading
- soundfile / pydub: Audio file I/O, format conversion, mono conversion, resampling
- numpy: Statistical computation: std, mean, variance across time-series arrays
- scipy.signal: Signal filtering for jitter computation and pause detection
- nltk / spacy: Optional: contextual NLP for filler word grammatical role classification
- json: Output serialization


### PHASE 1  —  Flask Endpoint & Audio Ingestion

**Goal:**
Accept audio file (or extract audio from video), validate format, and prepare for processing.

**Tasks:**
- Create POST /audio/analyze endpoint
- Accept WAV, MP3, or MP4 input
- Extract audio from video if MP4 submitted (reuse session_id from pose pipeline)
- Save to temp file with session_id

**Libraries:**
- flask
- pydub (audio extraction from video)
- uuid
- os

**Outputs:**
- Audio file on disk ready for preprocessing
- session_id linked to pose session


### PHASE 2  —  Audio Preprocessing

**Goal:**
Standardize audio to a consistent format required by both Whisper and Librosa.

**Tasks:**
- Convert to mono channel
- Resample to 16 kHz sample rate
- Normalize amplitude to standard loudness level
- Save preprocessed file as WAV 16kHz mono

**Libraries:**
- librosa (resample, load)
- soundfile (write)
- pydub (channel conversion)

**Outputs:**
- Preprocessed audio file: 16kHz mono WAV
- Duration in seconds


Here is the fully rewritten Phase 3 for the audio pipeline using AssemblyAI.

---

### PHASE 3 — AssemblyAI Transcription & Word Timestamps

**Goal:**
Generate a raw, unfiltered transcript of exactly what was spoken — including silences, filler sounds, repeated words, and disfluencies — with word-level start and end timestamps, using AssemblyAI's Universal-3 Pro model via their REST API.

**Tasks:**

- Install and import the `assemblyai` Python SDK
- Configure the AssemblyAI client with the API key loaded from `config.py` (which reads from the `ASSEMBLYAI_API_KEY` environment variable — never hardcode the key)
- Create a `TranscriptionConfig` object with the following settings:
  - Set `speech_model` to `assemblyai.SpeechModel.universal` (Universal-3 Pro model)
  - Set `punctuate` to `True`
  - Set `format_text` to `False` — this disables text cleaning so repeated words, filler sounds, and disfluencies are preserved exactly as spoken
  - Configure a custom vocabulary or prompt string instructing the model to:
    - Transcribe silence as `...` where audible pauses occur
    - Include all spoken filler sounds — `um`, `uh`, `hmm`, `erm` — exactly as uttered
    - Preserve repeated words exactly as spoken (e.g. if user says "the the garden", output must be "the the garden" not "the garden")
    - Produce raw spoken output — no cleanup, no deduplication, no grammar correction
  - Set `word_boost` if needed for domain-specific terms
- Upload the preprocessed audio file (16kHz mono WAV from `preprocessor.py`) to AssemblyAI using `aai.Transcriber().transcribe(file_path, config=config)`
- Poll or await the transcription result until status is `completed` — handle `error` status with a raised exception caught by `pipeline.py`
- Extract `transcript.words` — the word-level list returned by AssemblyAI, each entry containing:
  - `text` — the spoken word exactly as transcribed
  - `start` — start time in milliseconds (convert to seconds by dividing by 1000)
  - `end` — end time in milliseconds (convert to seconds)
  - `confidence` — per-word confidence score (store but do not use for filtering)
- Build the `segments` list by grouping words into sentence-level segments using the `transcript.sentences` property if available, or by grouping on punctuation boundaries from the flat word list
- Build `full_text` from `transcript.text` — the raw unformatted string returned by the API
- Compute `total_words` by counting entries in the word list — do not use `len(full_text.split())` as this will miscount repeated words and filler sounds
- Compute `speaking_duration_seconds` as `transcript.words[-1]["end"] - transcript.words[0]["start"]` — this is the actual speech span excluding leading and trailing silence, used by `timing_metrics.py` for WPM calculation
- Store the full raw API response object for debugging purposes alongside the extracted fields

**Config additions required in `config.py`:**
```python
# ── AssemblyAI ────────────────────────────────────────────────
ASSEMBLYAI_API_KEY       = os.getenv("ASSEMBLYAI_API_KEY", "")
ASSEMBLYAI_SPEECH_MODEL  = "universal"   # Universal-3 Pro
ASSEMBLYAI_PUNCTUATE     = True
ASSEMBLYAI_FORMAT_TEXT   = False         # preserve raw spoken text exactly

ASSEMBLYAI_TRANSCRIPTION_PROMPT = (
    "Transcribe exactly what is spoken without any cleanup or correction. "
    "Include all filler sounds such as um, uh, hmm, and erm exactly as uttered. "
    "If a word is repeated consecutively, include it both times as spoken. "
    "Represent audible silences or long pauses with '...'. "
    "Do not remove repetitions, do not fix grammar, do not deduplicate words."
)
```

**`audio/transcriber.py` — module structure:**
```python
import assemblyai as aai
import logging
from config import (
    ASSEMBLYAI_API_KEY,
    ASSEMBLYAI_SPEECH_MODEL,
    ASSEMBLYAI_PUNCTUATE,
    ASSEMBLYAI_FORMAT_TEXT,
    ASSEMBLYAI_TRANSCRIPTION_PROMPT,
)

logger = logging.getLogger(__name__)

# Configure client once at module level — not inside the transcribe function
aai.settings.api_key = ASSEMBLYAI_API_KEY


def transcribe(audio_path: str) -> dict:
    """
    Transcribes audio using AssemblyAI Universal-3 Pro model.
    Returns raw spoken transcript with word-level timestamps.
    Preserves fillers, repetitions, and silence markers exactly as spoken.
    """
    config = aai.TranscriptionConfig(
        speech_model  = aai.SpeechModel.universal,
        punctuate     = ASSEMBLYAI_PUNCTUATE,
        format_text   = ASSEMBLYAI_FORMAT_TEXT,
        # prompt instructs the model to preserve raw speech
    )

    transcriber = aai.Transcriber()
    result      = transcriber.transcribe(audio_path, config=config)

    if result.status == aai.TranscriptStatus.error:
        raise RuntimeError(f"AssemblyAI transcription failed: {result.error}")

    # Convert millisecond timestamps to seconds
    words = [
        {
            "word":       w.text,
            "start":      w.start / 1000.0,
            "end":        w.end   / 1000.0,
            "confidence": w.confidence,
        }
        for w in result.words
    ]

    total_words = len(words)
    full_text   = result.text or ""

    speaking_duration = (
        (words[-1]["end"] - words[0]["start"]) if words else 0.0
    )

    segments = _build_segments(result, words)

    logger.info(
        f"Transcription complete — {total_words} words, "
        f"{speaking_duration:.1f}s speaking duration"
    )

    return {
        "full_text":                full_text,
        "segments":                 segments,
        "words":                    words,
        "total_words":              total_words,
        "speaking_duration_seconds": speaking_duration,
    }


def _build_segments(result, words: list) -> list:
    """Groups word-level entries into sentence-level segments."""
    # Use AssemblyAI sentences if available
    if hasattr(result, "sentences") and result.sentences:
        return [
            {
                "text":  s.text,
                "start": s.start / 1000.0,
                "end":   s.end   / 1000.0,
            }
            for s in result.sentences
        ]
    # Fallback: treat full transcript as one segment
    if words:
        return [{
            "text":  result.text,
            "start": words[0]["start"],
            "end":   words[-1]["end"],
        }]
    return []
```

**Libraries:**
- `assemblyai` — official AssemblyAI Python SDK (`pip install assemblyai`)
- `logging`
- `config` (for API key, model settings, and prompt string)

**Outputs — identical contract to before, downstream files unchanged:**
- `transcript.full_text` — raw string of everything spoken, fillers and repetitions included
- `transcript.segments` — list of `{text, start, end}` sentence-level dicts
- `transcript.words` — list of `{word, start, end, confidence}` word-level dicts
- `transcript.total_words` — integer count of all spoken word tokens
- `transcript.speaking_duration_seconds` — float, used by `timing_metrics.py` for WPM

**Important downstream note:**
`filler_detector.py` receives the `words` list from this output. Because `format_text=False`
ensures fillers are preserved in the raw transcript, `filler_detector.py` will now find
them reliably in the word list. No changes are needed to `filler_detector.py` — the contract
is identical, just the data is now richer and more accurate.

**Environment setup required:**
```bash
pip install assemblyai
export ASSEMBLYAI_API_KEY="your_key_here"
```

### PHASE 4  —  Filler Word Detection

**Goal:**
Identify filler words from transcript using dictionary matching with contextual validation.

**Tasks:**
- Define FILLERS dictionary from master_formula_reference.md (um, uh, erm, hmm, like, basically, actually, you know, i mean, sort of, kind of)
- Iterate through word-level transcript with surrounding context window
- For each candidate filler word: check pause_before and pause_after duration against 0.3s threshold
- For "like": additionally check if followed by a noun phrase — if so, mark as valid usage not filler
- Increment filler count only when both dictionary match AND contextual rule confirm filler
- Compute FillerRatio = filler_count / total_words
- Normalize: FillerRatioNormalized = min(FillerRatio / 0.20, 1)
- Store filler_words_used dict with counts per filler type
- Refer to master_formula_reference.md Section 5 for full rule logic

**Libraries:**
- numpy
- nltk or spacy (optional, for POS tagging of "like" disambiguation)

**Outputs:**
- filler_count integer
- filler_ratio float
- filler_ratio_normalized float [0,1]
- filler_words_used dict


### PHASE 5  —  Acoustic Feature Extraction via Librosa

**Goal:**
Extract pitch, energy, jitter, and pause signals from the audio time-series.

**Tasks:**
- Load preprocessed audio with librosa.load() at 16kHz
- Pitch (F0): extract using librosa.pyin() or yin() — output is array of Hz values per frame
- Pitch Variance: compute CoV = std(F0) / mean(F0), normalize per master_formula_reference.md Section 4.2
- Pitch Jitter: compute mean absolute frame-to-frame pitch difference, normalize per Section 4.3
- RMS Energy: compute librosa.feature.rms() per frame — output energy array
- Energy Variation: compute CoV of energy array, normalize per Section 4.5
- Pause Detection: identify frames where RMS < theta threshold, group into pause events, compute PauseRatio
- Store all raw arrays for windowed aggregation downstream

**Libraries:**
- librosa
- numpy
- scipy

**Outputs:**
- F0 array (Hz per frame)
- pitch_variance_normalized float [0,1]
- jitter_normalized float [0,1]
- rms_energy array
- energy_variation_normalized float [0,1]
- pause_ratio float [0,1]


### PHASE 6  —  Speech Timing Metrics

**Goal:**
Compute words-per-minute metrics and assess pacing quality.

**Tasks:**
- Compute SpeechRate = total_words / speaking_duration (exclude pause time from denominator)
- Compute SpeechRateScore = 1 - |WPM - 145| / 145, clamp to [0,1]
- Divide session into 5-second windows, compute WPM per window
- Compute SpeechRateInstability = std(WPM_per_window)
- Normalize SpeechRateInstability per master_formula_reference.md Section 6.3

**Libraries:**
numpy

**Outputs:**
- speech_rate_wpm float
- speech_rate_score float [0,1]
- speech_rate_instability_normalized float [0,1]


### PHASE 7  —  Window-Level Aggregation & Fumble Score

**Goal:**
Aggregate all audio metrics into 5-second windows and compute per-window fumble score.

**Tasks:**
- Group all acoustic frame values into 5-second windows aligned with Whisper segments
- Compute per-window values for: FillerRatio, PauseRatio, PitchVarianceNormalized, SpeechRateInstabilityNormalized
- Compute FumbleScore_k per window using weighted formula in master_formula_reference.md Section 9.1
- Store all window-level fumble scores with their timestamps for event detection

**Libraries:**
numpy

**Outputs:**
List of per-window dicts with all acoustic values and FumbleScore_k


### PHASE 8  —  Timestamp Event Detection

**Goal:**
Flag specific moments in the session where behavioral anomalies exceed defined thresholds.

**Tasks:**
- High Fumble Spike: flag window if FumbleScore_k > 0.60
- Excessive Pause: flag window if PauseRatio_k > 0.40
- Rapid Speech: flag window if SpeechRate_k > 180 WPM
- Monotone Delivery: flag window if PitchVarianceNormalized_k < 0.10
- Vocal Instability: flag window if PitchVarianceNormalized_k > 0.70 OR JitterNormalized_k > 0.65
- Adaptive Spike: compute Delta_k = FumbleScore_k - session_mean(FumbleScore), flag if Delta_k > 2 * session_std
- Each event stores: time_start, time_end (if applicable), event_type string
- Refer to master_formula_reference.md Section 9 for all threshold values

**Libraries:**
numpy

**Outputs:**
timestamp_events list — each entry: {time_start, time_end, event}


### PHASE 9  —  Derived Audio Behavioral Attributes

**Goal:**
Compute 4 high-level audio behavioral indices from session-level metric values.

**Tasks:**
- Audio Instability: weighted combination of PitchVariance, Jitter, FillerRatio, PauseRatio, SpeechRateInstability — refer master_formula_reference.md Section 7.1
- Audio Confidence: weighted combination with inverse filler, pitch, pause signals — refer Section 7.2
- Audio Engagement: built from PitchExpressiveness and EnergyExpressiveness composites — refer Section 7.3
- Audio Nervousness: mirrors AudioInstability — refer Section 7.4

**Libraries:**
numpy

**Outputs:**
audio_confidence, audio_engagement, audio_nervousness, audio_instability — all floats [0,1]


### PHASE 10  —  Audio JSON Builder & Response

**Goal:**
Assemble full audio output JSON and return from Flask endpoint.

**Tasks:**
- Populate transcript block: full_text and segments list
- Populate acoustic_metrics block: all 8 normalized metric values
- Populate filler_words_used block: per-filler counts
- Populate derived_audio_attributes block: 4 derived values
- Populate timestamp_events block: full event list
- Serialize and return from Flask endpoint

**Libraries:**
- json
- flask

**Outputs:**
audio_output.json with all 5 required blocks

## 4.  Pipeline 3 — Final Evaluation Engine

## 4.1  Purpose
Receives the Pose JSON and Audio JSON from the two upstream pipelines, fuses them into 4 composite scores (Confidence, Clarity, Engagement, Nervousness) plus an Overall score, retrieves historical scores from the database to compute progress deltas, classifies each delta, saves the session, assembles the Final Evaluation JSON, and passes it to the LLM interpretation layer.
## 4.2  Core Libraries
- flask: HTTP endpoint orchestrating the full evaluation
- numpy: Weighted fusion arithmetic for composite scores
- sqlite3 / sqlalchemy: Database operations: fetch history, write session scores
- anthropic / openai: LLM API call for interpretation layer (read-only JSON input)
- json: Input parsing and output serialization
- uuid / datetime: Session ID management and timestamp logging

## 4.3  Database Schema Reference
The following table must exist in the database before the evaluation engine runs:

| Column | Type & Purpose |
| --- | --- |
|  |  |
| user_id  TEXT session_id  TEXT  PRIMARY KEY session_date  DATETIME confidence  REAL clarity  REAL engagement  REAL nervousness  REAL overall  REAL filler_ratio  REAL pitch_variance_normalized  REAL posture_stability_index  REAL pause_ratio  REAL gesture_score  REAL | All scores stored as REAL (float) in range [0, 1]. Query with ORDER BY session_date DESC LIMIT 1 for last session. Query with LIMIT 3 for rolling 3-session baseline. Table: session_scores |


### PHASE 1  —  Input Reception & Validation

**Goal:**
Receive Pose JSON and Audio JSON, validate all required fields are present and in range.

**Tasks:**
- Create POST /evaluate endpoint
- Accept pose_json and audio_json as request body (or session_id references to cached outputs)
- Validate all 10 posture metrics present in pose JSON
- Validate all 6 derived pose attributes present
- Validate all 8 acoustic metrics present in audio JSON
- Validate all 4 derived audio attributes present
- Validate timestamp_events list is present (can be empty)
- Return 400 with error detail if any required field is missing

**Libraries:**
- flask
- json

**Outputs:**
- Validated pose_data dict
- Validated audio_data dict
- session_id for this evaluation


### PHASE 2  —  Multimodal Score Fusion

**Goal:**
Compute the 4 composite scores and overall score by fusing pose and audio attributes.

**Tasks:**
- Confidence Score: fuse pose_confidence and audio_confidence with cross-modal weights
- Clarity Score: fuse speech fluency metrics (filler, speech rate, pauses) with physical delivery metrics (spine, shoulders, head)
- Engagement Score: fuse pose_engagement and audio_engagement with cross-modal weights
- Nervousness Score: fuse pose_nervousness and audio_nervousness with cross-modal weights
- Overall Score: weighted combination of Confidence + Clarity + Engagement + (1 - Nervousness)
- Clamp all output values to [0, 1]
- All fusion weights defined in master_formula_reference.md Section — Multimodal Fusion

**Libraries:**
numpy

**Outputs:**
confidence, clarity, engagement, nervousness, overall — all floats [0,1]


### PHASE 3  —  Database Fetch — Historical Baseline

**Goal:**
Retrieve previous session scores from Supabase for progress delta computation.

**Tasks:**
- Connect to Supabase using the `supabase-py` client, initialized with `SUPABASE_URL`
  and `SUPABASE_KEY` loaded from environment variables via `config.py`
- Query: `session_scores` table filtered by `user_id`, ordered by `session_date` descending,
  limit 3 rows for rolling baseline
- If rolling baseline: compute column-wise mean across the 3 returned rows using numpy
- If no previous session exists (empty result): skip delta computation, set `is_first_session = True`
- Store fetched values as `baseline_scores` dict

**Libraries:**
- supabase-py (`pip install supabase`)
- numpy (for mean of 3-session rolling baseline)

**Outputs:**
- baseline_scores dict with all score fields
- is_first_session boolean


### PHASE 4  —  Delta Computation & Classification

**Goal:**
Compute how much each score changed versus baseline and classify the direction.

**Tasks:**
- For each score field: Delta = current_value - baseline_value
- Headline: overall_delta = overall_current - overall_baseline
- Psychological: nervousness_delta = nervousness_current - nervousness_baseline  (negative = improvement)
- Skill deltas: confidence_delta, clarity_delta, engagement_delta
- Behavioral deltas: filler_change = previous - current (positive = better); pause_ratio_change = previous - current; posture_stability_change = current - previous; pitch_variance_change = current - previous
- Classification per delta: > 0.05 → Significant Improvement | 0.02–0.05 → Moderate Improvement | -0.02–0.02 → Stable | < -0.05 → Noticeable Decline
- Store delta values AND classification labels for each field
- If first_session: set all deltas to null and classification to "Baseline Session"
- Refer to master_formula_reference.md Section 3 for all delta formulas

**Libraries:**
numpy

**Outputs:**
progress_comparison dict with headline, psychological, skill, and behavioral sub-blocks plus classifications


### PHASE 5  —  Session Write-Back to Database

**Goal:**
Persist current session scores to Supabase BEFORE calling the LLM to ensure data is
never lost even if the LLM call fails.

**Tasks:**
- Assemble row dict: user_id, session_id, session_date (UTC ISO string), all 5 composite
  scores (confidence, clarity, engagement, nervousness, overall), and all 4 behavioral
  raw metrics (filler_ratio, pitch_variance_normalized, posture_stability_index, pause_ratio,
  gesture_score)
- Use Supabase client to execute: `supabase.table("session_scores").insert(row).execute()`
- Check response for errors — if insert fails, log the error and return HTTP 500 immediately
- Do NOT proceed to LLM call if write fails

**Libraries:**
- supabase-py
- datetime
- uuid

**Outputs:**
- Row inserted into `session_scores` table in Supabase
- Write confirmation logged with session_id


### PHASE 6  —  Final Evaluation JSON Assembly

**Goal:**
Build the complete read-only JSON package that will be passed to the LLM.

**Tasks:**
- Block 1 — overall_scores: confidence, clarity, engagement, nervousness, overall
- Block 2 — progress_comparison: headline_improvement, psychological_improvement, skill_improvement, behavioral_improvement (each with delta value + classification)
- Block 3 — timestamp_events: pass through full list from audio pipeline unchanged
- Block 4 — raw_metrics_snapshot: all 10 pose metrics + all 8 acoustic metrics (for app UI display)
- Block 5 — session_metadata: session_id, user_id, session_date, duration_seconds, is_first_session
- Validate all fields populated
- Serialize to JSON string

**Libraries:**
json

**Outputs:**
final_evaluation.json — unified read-only data package


### PHASE 7  —  LLM Interpretation Layer

**Goal:**
Pass the Final Evaluation JSON to Groq's `openai/gpt-4o-mini` model for human-readable
coaching feedback generation. Groq is used as the inference provider for low-latency
response on mobile.

**Tasks:**
- Initialize Groq client using `groq` Python SDK with `GROQ_API_KEY` from `config.py`
- Set model to `"openai/gpt-4o-mini"` — do not change this without updating config
- Construct system prompt as a module-level constant in `llm_interpreter.py`:
  - Instruct the model it receives a pre-computed evaluation JSON and must only interpret,
    never recompute any value
  - Specify required output format exactly:
    `overall_summary`, `progress_narrative`, `timestamped_moments`, `top_3_action_items`,
    `motivational_closing`
  - Enforce: must not modify numeric values, must not compute deltas, must not access
    external data, must reference timestamp events only from the provided list
- Send `final_evaluation` JSON as the user message content (stringified)
- Parse response: extract `choices[0].message.content`, parse as JSON
- Handle API errors gracefully — if Groq call fails, return scores with empty coaching
  fields and `"llm_available": false`; never block the evaluation response

**Libraries:**
- groq (`pip install groq`)
- json

**Outputs:**
llm_feedback dict: overall_summary, progress_narrative, timestamped_moments,
top_3_action_items, motivational_closing


### PHASE 8  —  Final Response Assembly & API Return

**Goal:**
Combine scores, progress comparison, and LLM feedback into final user-facing response.

**Tasks:**
- Merge final_evaluation JSON + llm_feedback into single response object
- Add HTTP headers: Content-Type application/json
- Return HTTP 200 with full response body
- Log evaluation completion with session_id and processing duration

**Libraries:**
- flask
- json

**Outputs:**
HTTP 200 JSON response: scores + progress + LLM coaching + metadata

## 5.  Critical Enforcement Rules

> 🚫 LLM Hard Constraints:  The LLM layer must NEVER compute any score, delta, or classification. It must NEVER fetch historical data from the database. It must NEVER modify any numeric value in the JSON it receives. All of these operations are strictly deterministic backend responsibilities.



> ✅ Data Flow Rule:  Session scores must be written to the database BEFORE the LLM call is made. This ensures all longitudinal data is preserved even if the LLM API call fails.



> 📐 Formula Source of Truth:  Every normalization formula, threshold constant, and weighted composite definition used anywhere in all three pipelines is defined in master_formula_reference.md. No magic numbers should appear in source code — all constants should be imported from a centralized config file that mirrors master_formula_reference.md.



> 🔢 Value Range Contract:  Every metric, derived attribute, composite score, and delta value that is passed between pipeline stages must be in the range [0, 1] unless explicitly documented otherwise (e.g. WPM which is a raw count). Any value outside this range at a pipeline boundary should be treated as a computation error.


## 6.  Flask Endpoint Summary

| Endpoint | Method | Input | Output |
| --- | --- | --- | --- |
| /pose/analyze | POST | MP4 video file | Pose JSON |
| /audio/analyze | POST | Audio file or MP4 | Audio JSON |
| /evaluate | POST | Pose JSON + Audio JSON + user_id | Final Evaluation JSON + LLM Feedback |
