# Device Pipeline Offload Specification

**Date:** 2026-04-02  
**Status:** Proposed migration plan  
**Audience:** Backend team, React Native frontend team  
**Goal:** Move heavy deterministic media-processing stages from backend to device while preserving the current evaluation quality and response shape.

**Formula and config reference:** [referenced_formuals.md](/e:/vision/reference_documents/referenced_formuals.md)

---

## 1. Why We Are Doing This

The current backend still spends a meaningful amount of time on deterministic local processing, especially:

- pose normalization and metric computation
- audio preprocessing
- local acoustic feature extraction

The slowest backend stage is still AssemblyAI transcription, but moving deterministic computation to the device will:

- reduce backend CPU usage
- reduce backend memory pressure
- reduce `/analyze/full` latency
- make the backend closer to a scoring/orchestration service rather than a media-processing service

This migration is especially suitable because the product context is:

- single speaker
- presentation/public-speaking audio
- mobile app already extracting pose landmarks on device

---

## 2. Current Optimized Backend Architecture

### Pose

Current backend pose flow:

1. Receive `pose_landmarks` JSON
2. Parse landmarks
3. Normalize landmarks
4. Compute 10 posture metrics
5. Aggregate window/session metrics
6. Compute derived pose attributes
7. Build final `pose_json`

### Audio

Current backend audio flow:

1. Preprocess audio into:
   - normalized WAV for local DSP
   - compressed upload file for AssemblyAI
2. Transcribe with AssemblyAI
3. Detect fillers from transcript
4. Compute acoustic features locally
5. Compute timing metrics from transcript
6. Aggregate windows
7. Detect events
8. Compute derived audio attributes
9. Build final `audio_json`

### Evaluation

Current backend evaluation flow:

1. Validate pose/audio inputs
2. Fetch baseline history
3. Build provisional evaluation package
4. Call final LLM
5. Read `reasoning_clarity_score` from the LLM result
6. Fuse final scores
7. Compute deltas
8. Write session to Supabase
9. Save full final JSON in `session_scores.raw_result`

Important current behavior:

- `reasoning_clarity` is no longer computed inside the audio pipeline
- `reasoning_clarity_score` comes from the final evaluation LLM response
- session history does **not** require a dedicated SQL column for reasoning clarity because it is saved inside `raw_result`

---

## 3. Correct Target Architecture

The earlier draft missed some backend responsibilities. This is the corrected target split.

### Device Responsibilities

#### Pose on device

The device should perform the full deterministic pose pipeline:

1. capture/extract pose landmarks
2. normalize landmarks
3. compute all 10 posture metrics
4. aggregate window/session pose metrics
5. compute derived pose attributes
6. build a compact `pose_json`

The backend should no longer need raw landmark arrays for pose analysis once this migration is complete.

#### Audio on device

The device should perform deterministic acoustic preprocessing only:

1. preprocess/standardize audio
2. create compressed upload audio for backend/transcription
3. compute acoustic features:
   - RMS-based values
   - F0/pitch values
   - jitter
   - energy variation
   - pause ratio
4. optionally compute acoustic-only window summaries

The device should **not** compute the final backend event system unless we intentionally redesign that logic.

### Backend Responsibilities

The backend should keep transcript-dependent and evaluation-dependent stages:

1. receive compact pose data instead of raw landmark payload
2. receive compressed audio file plus acoustic summaries
3. call AssemblyAI transcription
4. detect fillers from transcript
5. compute timing metrics from transcript
6. merge transcript-derived timing/filler data with acoustic data
7. perform final event detection
8. compute final derived audio attributes
9. run evaluation, delta computation, persistence, and final LLM interpretation

---

## 4. What Must Stay On Backend

These stages should remain on backend in the target design.

### 4.1 AssemblyAI transcription

Reason:

- API key should remain server-side
- transcript and word timings are required by downstream logic

### 4.2 Filler detection

Reason:

- current filler detector uses transcript words and pause context
- it depends on transcript word timings from AssemblyAI

### 4.3 Timing metrics

Reason:

- WPM and speech-rate instability are transcript-derived in the current architecture

### 4.4 Final window aggregation and event detection

Reason:

- current window/event logic uses both:
  - acoustic metrics
  - transcript-derived metrics
  - filler ratio per window
  - speech rate per window

If event detection moves fully on-device today, it will become a different event system from the current backend implementation.

### 4.5 Evaluation and final LLM interpretation

Reason:

- score fusion and delta computation depend on backend history access
- Supabase writes must stay backend-side
- final LLM prompt uses the full structured evaluation package

---

## 5. What Can Move Safely To Device

### 5.1 Pose pipeline

This is the cleanest offload.

Move all of this:

- normalization
- metric computation
- aggregation
- derived pose attributes

Result:

- backend receives compact pose results only
- large raw landmark payloads are no longer needed

### 5.2 Audio preprocessing

Move all of this:

- format normalization
- mono conversion
- sample-rate conversion
- compressed upload file creation

Result:

- backend no longer runs local FFmpeg/PyDub preprocessing

### 5.3 Acoustic feature extraction

Move these to device:

- `pitch_variance_normalized`
- `jitter_normalized`
- `energy_variation_normalized`
- `pause_ratio`

Optional:

- acoustic window summaries by 5-second windows

Result:

- backend no longer runs Librosa pitch/RMS extraction

---

## 6. Proposed New API Contract

This section defines the target contract after migration.

## 6.1 New `/analyze/full` request

The endpoint should evolve from:

- `pose_landmarks` file
- `audio` file

to:

- compact pose JSON
- compact acoustic JSON
- compressed audio file for transcription

### Multipart fields

Required multipart fields:

- `pose_json`
- `audio_acoustic_json`
- `audio`
- `user_id`

Optional metadata fields:

- `session_id`
- `topic_title`
- `duration_label`
- `is_first_session`
- `week_number`
- `plan_day`
- `plan_session_num`
- `is_recovery`
- `target_skill`
- `is_diagnostic`
- `speaker_level`

### `pose_json` target shape

```json
{
  "session_metadata": {
    "session_id": "uuid-or-client-session-id",
    "pipeline": "pose-device-v1"
  },
  "posture_metrics": {
    "shoulder_alignment": 0.0,
    "spine_straightness": 0.0,
    "posture_openness": 0.0,
    "head_stability": 0.0,
    "body_sway": 0.0,
    "gesture_score": 0.0,
    "amplitude_score": 0.0,
    "symmetry_score": 0.0,
    "fidget_score": 0.0,
    "stillness_score": 0.0
  },
  "derived_pose_attributes": {
    "posture_stability_index": 0.0,
    "pose_confidence": 0.0,
    "pose_nervousness": 0.0,
    "pose_engagement": 0.0,
    "movement_variance_normalized": 0.0,
    "gaze_stability": 0.0
  }
}
```

### `audio_acoustic_json` target shape

```json
{
  "session_metadata": {
    "session_id": "uuid-or-client-session-id",
    "pipeline": "audio-device-v1"
  },
  "acoustic_metrics": {
    "pitch_variance_normalized": 0.0,
    "jitter_normalized": 0.0,
    "energy_variation_normalized": 0.0,
    "pause_ratio": 0.0
  },
  "acoustic_windows": [
    {
      "window_index": 0,
      "time_start": 0.0,
      "time_end": 5.0,
      "pitch_variance_normalized": 0.0,
      "pause_ratio": 0.0
    }
  ]
}
```

Notes:

- `acoustic_windows` is optional in phase 1
- if omitted, backend may rebuild coarse windows from transcript timing only
- an empty `acoustic_windows: []` is valid and should be treated the same as omission

## 6.2 Request compatibility and precedence rules

This section defines the exact fallback contract for rollout safety.

### New-client required fields

For the new device-offload client path, the frontend should send:

- `pose_json`
- `audio_acoustic_json`
- `audio`
- `user_id`

### Legacy-client required fields

For the legacy backend-compute path, the frontend may send:

- `pose_landmarks`
- `audio`
- `user_id`

### Coexistence rules

During migration, old and new fields may coexist in the same request.

Allowed coexistence:

- `pose_json` and `pose_landmarks`
- `audio_acoustic_json` together with legacy `pose_landmarks`

### Precedence rules

If both `pose_json` and `pose_landmarks` are present:

- `pose_json` wins
- `pose_landmarks` must be ignored

If `audio_acoustic_json` is present and valid:

- backend should use the device acoustic path
- backend should skip local preprocessing and local acoustic extraction

If `audio_acoustic_json` is absent:

- backend should use the legacy backend acoustic path

### Fallback matrix

#### Case A: `pose_json` present, `audio_acoustic_json` present

Backend behavior:

- use device pose path
- use device acoustic path

#### Case B: `pose_json` present, `audio_acoustic_json` absent

Backend behavior:

- use device pose path
- use legacy backend audio compute path

#### Case C: `pose_landmarks` present, `audio_acoustic_json` present

Backend behavior:

- use legacy backend pose path
- use device acoustic path

#### Case D: `pose_landmarks` present, `audio_acoustic_json` absent

Backend behavior:

- use full legacy backend path

#### Case E: `pose_json` and `pose_landmarks` both present

Backend behavior:

- use `pose_json`
- ignore `pose_landmarks`

#### Case F: malformed or partial `audio_acoustic_json`

Recommended rollout behavior:

- early rollout: allow backend fallback to legacy backend acoustic compute
- stable rollout: reject explicitly with a validation error

#### Case G: malformed `pose_json`

Recommended behavior:

- do not silently fall back if `pose_json` was intentionally sent by a new client
- return a structured validation error unless the request is clearly legacy-only

### Recommended backend priority order

For pose:

1. valid `pose_json`
2. else valid `pose_landmarks`
3. else request error

For audio acoustics:

1. valid `audio_acoustic_json`
2. else legacy backend acoustic path

## 6.3 Numeric precision and serialization rules

To reduce frontend/backend drift from float serialization differences:

- JSON metrics must be sent as numeric JSON values, not strings
- frontend should compute using native float precision internally
- frontend should serialize exported metrics rounded to **4 decimal places**
- backend should parse them as floats
- backend must not reject values solely because they are rounded

### Precision rule for payload fields

Applies to:

- all `posture_metrics.*`
- all `derived_pose_attributes.*`
- all `acoustic_metrics.*`
- all `acoustic_windows[*].pitch_variance_normalized`
- all `acoustic_windows[*].pause_ratio`
- all `acoustic_windows[*].time_start`
- all `acoustic_windows[*].time_end`

Recommended frontend helper:

```text
round4(x) = round(x, 4)
```

Additional serialization rules:

- booleans must be sent as true JSON booleans
- `window_index` must be an integer
- identifiers such as `session_id` must remain strings

## 6.4 Validation and error response contract

Backend should return structured validation errors so frontend can show precise retry and failure states.

### Recommended error response shape

```json
{
  "error": {
    "code": "INVALID_POSE_JSON",
    "message": "pose_json must contain posture_metrics and derived_pose_attributes",
    "details": {
      "field": "pose_json",
      "missing_keys": ["posture_metrics"]
    },
    "fallback_used": false
  }
}
```

### Recommended validation error codes

- `MISSING_AUDIO`
- `MISSING_USER_ID`
- `MISSING_POSE_INPUT`
- `INVALID_POSE_JSON`
- `INVALID_POSE_LANDMARKS`
- `INVALID_AUDIO_ACOUSTIC_JSON`
- `UNSUPPORTED_PIPELINE_VERSION`
- `MISSING_REQUIRED_KEYS`
- `INVALID_NUMERIC_RANGE`

### Fallback-related response behavior

If backend rejects malformed device payloads:

- return `400`
- include `fallback_used: false`

If backend accepts the request but falls back to legacy backend compute:

- the final success payload should include a metadata note
- recommended response field:

```json
{
  "session_metadata": {
    "fallbacks_used": ["legacy_backend_audio_compute"]
  }
}
```

## 6.5 Session artifact expectations

### Accepted upload media during migration

Backend should accept these media types during migration:

- `audio/mpeg`
- `audio/mp3`
- `audio/mp4`
- `video/mp4`
- `audio/wav`
- `audio/x-wav`
- `audio/m4a`
- `audio/aac`

### Migration rule

During migration:

- frontend should prefer a true compressed speech audio artifact
- backend should still accept `video/mp4` temporarily for compatibility

### Preferred new-client artifact

- mono
- `16kHz`
- `mp3`
- approximately `64k` bitrate

### Upload size expectation

Recommended current contract:

- frontend should target uploads under `25 MB`
- backend hard-reject size should be added explicitly when request-size enforcement is implemented

### Audio-only vs video upload

Target end state:

- frontend sends a compressed audio artifact for transcription

Temporary compatibility:

- backend may still accept `video/mp4`
- backend may still work with current media temporarily while clients migrate

### MIME-type rule

Frontend should set the correct multipart MIME type when possible.

If the mobile stack cannot reliably set the correct MIME type:

- backend may infer from extension as a compatibility fallback

---

## 7. Backend Change List

This section describes exact backend ownership and file changes.

## 7.1 Files to modify

### `orchestrator/routes.py`

Current behavior:

- expects `pose_landmarks` file
- expects `audio` file
- runs `run_pose_pipeline()` and `run_audio_pipeline()`

Required update:

- accept `pose_json` instead of `pose_landmarks`
- accept `audio_acoustic_json` in addition to `audio`
- stop calling backend pose pipeline once device pose output is trusted
- call a new backend audio pipeline entry that merges:
  - compressed audio upload
  - device acoustic metrics

Target behavior:

- parse compact pose JSON directly
- pass compact pose JSON straight into evaluation
- call only backend transcription + transcript-dependent audio steps

### `audio/pipeline.py`

Current behavior:

- preprocesses audio locally
- transcribes
- computes acoustics locally
- computes fillers/timing/windows/events/derived

Required update:

- stop local preprocessing
- stop local acoustic extraction
- accept precomputed device acoustic metrics
- keep:
  - transcription
  - filler detection
  - timing metrics
  - final window/event assembly
  - derived audio attributes

Target function shape:

```python
run_audio_pipeline(
    transcription_audio_path: str,
    session_id: str,
    topic_title: str,
    acoustic_payload: dict,
) -> dict
```

### `audio/preprocessor.py`

Current role:

- backend standardizes audio

Required update:

- likely remove from `/analyze/full` path
- keep only if needed as fallback for older clients

Recommendation:

- mark as legacy fallback support
- do not delete immediately

### `audio/acoustic_extractor.py`

Current role:

- backend Librosa feature extraction

Required update:

- remove from default `/analyze/full` flow
- keep only if backend fallback mode is needed for old clients

Recommendation:

- preserve file during migration
- stop calling it in the new client path

### `audio/window_aggregator.py`

Required update:

- support device acoustic windows if present
- merge those windows with:
  - filler counts
  - transcript timing
  - speech-rate metrics

Important:

- this becomes the merge point between on-device acoustics and backend transcript-derived signals

### `audio/event_detector.py`

Required update:

- keep current final event detection on backend
- no major logic rewrite required if merged window payload shape is preserved

### `evaluation/input_validator.py`

Required update:

- validate the new compact pose contract
- validate the new audio contract
- keep requiring `timestamp_events`

### `test/test_command.md`

Required update after migration:

- replace `pose_landmarks` upload with `pose_json`
- add `audio_acoustic_json`
- keep `audio` upload

---

## 8. Frontend Change List

This section defines what the React Native app must build.

## 8.1 Pose functions to add on frontend

Frontend must implement:

- `normalizeLandmarks()`
- `computePoseMetrics()`
- `aggregatePoseWindows()`
- `computeDerivedPoseAttributes()`
- `buildPoseJson()`

The frontend output must match the current backend `pose_json` schema closely enough that evaluation does not need to know whether pose was computed on backend or device.

## 8.2 Audio functions to add on frontend

Frontend must implement:

- `preprocessAudioForUpload()`
- `buildCompressedTranscriptionFile()`
- `computeRmsArray()` or equivalent pause feature extraction
- `computePitchFeatures()` using `react-native-pitchy` or equivalent
- `computeJitterNormalized()`
- `computeEnergyVariationNormalized()`
- `computePauseRatio()`
- `buildAudioAcousticJson()`

Optional later:

- `aggregateAcousticWindows()`

## 8.3 Frontend request construction

Frontend must send multipart data containing:

- compact `pose_json` file/string
- compact `audio_acoustic_json` file/string
- compressed `audio` file
- existing metadata fields

## 8.4 Frontend feature flags

The app should use a migration flag during rollout:

- `useDevicePosePipeline`
- `useDeviceAcousticPipeline`

This allows partial rollout and backend fallback support.

---

## 9. What We Are Adding, Removing, And Keeping

## 9.1 Adding

### Backend

- support for compact `pose_json` input
- support for compact `audio_acoustic_json` input
- merge logic between device acoustics and transcript-derived signals

### Frontend

- deterministic pose scoring pipeline
- deterministic acoustic preprocessing pipeline
- multipart upload of compact analysis payloads plus compressed audio

## 9.2 Removing from backend hot path

### Remove from default `/analyze/full` path

- backend pose normalization
- backend pose metric computation
- backend pose aggregation
- backend pose derived-attribute computation
- backend audio preprocessing
- backend Librosa acoustic extraction

### Keep as fallback during migration

- `pose/pipeline.py`
- `audio/preprocessor.py`
- `audio/acoustic_extractor.py`

## 9.3 Keeping on backend

- AssemblyAI transcription
- filler detection
- timing metrics
- final event detection
- derived audio attributes if they depend on transcript-derived metrics
- score fusion
- delta engine
- Supabase persistence
- final LLM interpretation

---

## 10. Migration Strategy

Do not switch everything at once.

## Phase 1: Device pose only

Goal:

- device sends compact pose JSON
- backend still handles current audio pipeline

Benefits:

- lowest migration risk
- immediate backend CPU reduction

## Phase 2: Device audio preprocessing + acoustic metrics

Goal:

- device sends compressed audio plus acoustic metrics
- backend still handles transcription and transcript-dependent logic

Benefits:

- large backend CPU/memory reduction
- preserves current transcript/event/evaluation behavior

## Phase 3: Optional device acoustic windows

Goal:

- device also sends windowed acoustic summaries
- backend merges these with transcript-derived windows

Benefits:

- reduced backend acoustic-window compute
- keeps final event logic centralized

## Phase 4: Deprecate old backend media-processing path

Goal:

- old raw-pose/raw-audio computation remains only as fallback or is removed later

Recommendation:

- do not delete legacy code until new mobile clients are fully deployed

---

## 11. Exact Backend Outcome We Want

After migration, backend should behave like this:

1. receive compact pose scores from device
2. receive compact acoustic metrics from device
3. receive compressed speech audio for transcription
4. call AssemblyAI
5. compute transcript-derived signals
6. fuse transcript-derived signals with device acoustic signals
7. compute final evaluation
8. write session to Supabase
9. return the same final evaluation JSON shape as today

This is the key rule:

> The output contract should remain stable even if the compute location changes.

That allows the frontend and backend teams to refactor internals without breaking results UI, session history, or weekly review logic.

---

## 12. Risks And Guardrails

## 12.1 Risk: frontend/backend formula drift

Guardrail:

- all formulas and thresholds must still come from the same `config.py` / shared spec
- if frontend reimplements formulas, they must match backend math exactly
- frontend and backend teams must use [referenced_formuals.md](/e:/vision/reference_documents/referenced_formuals.md) as the implementation reference for formulas and required config settings

## 12.2 Risk: event logic divergence

Guardrail:

- keep final event detection on backend
- do not move transcript-dependent event logic to device yet

## 12.3 Risk: schema mismatch

Guardrail:

- do not add new SQL columns unless there is a real reporting need
- continue storing full final payload in `session_scores.raw_result`

## 12.4 Risk: breaking older mobile builds

Guardrail:

- keep fallback backend processing path until the new client is fully rolled out

---

## 13. Summary For Each Team

## Backend team summary

Backend should stop being the primary media-compute layer.

Backend must:

- accept compact pose payloads
- accept compact acoustic payloads
- keep transcript-dependent logic
- keep evaluation, persistence, and LLM logic
- preserve the final evaluation response contract

## Frontend team summary

Frontend must become responsible for deterministic media feature extraction.

Frontend must:

- compute final pose metrics and derived pose attributes on device
- preprocess audio on device
- compute acoustic metrics on device
- upload compressed speech audio plus compact JSON payloads
- preserve numeric compatibility with backend formulas
- implement deterministic formulas and thresholds by following [referenced_formuals.md](/e:/vision/reference_documents/referenced_formuals.md)

---

## 14. Immediate Next Step

Recommended immediate implementation order:

1. device pose offload first
2. backend contract update for `pose_json`
3. device acoustic metrics second
4. backend merge logic for transcript + acoustic signals
5. final cleanup of old backend heavy compute path

This is the safest path that preserves output quality while delivering the biggest real latency gain.
