# Audio Offload Migration Plan Refresh

**Date:** 2026-04-06  
**Status:** Corrected implementation plan  
**Audience:** React Native frontend team, backend team

This document replaces the earlier draft migration note with a plan that matches the live backend contract and rollout behavior in this repo.

Canonical backend references:

- [`orchestrator/routes.py`](/e:/vision/orchestrator/routes.py)
- [`audio/pipeline.py`](/e:/vision/audio/pipeline.py)
- [`audio/window_aggregator.py`](/e:/vision/audio/window_aggregator.py)
- [`reference_documents/referenced_formuals.md`](/e:/vision/reference_documents/referenced_formuals.md)

---

## 1. Summary

We are still moving deterministic acoustic extraction to the React Native client, but the integration contract must follow the current backend path instead of the earlier draft.

The correct target behavior is:

- frontend uploads `audio` plus `audio_acoustic_json`
- backend uses device acoustics when `audio_acoustic_json.acoustic_metrics` is valid
- backend keeps transcription, filler detection, timing, window aggregation, event detection, and derived attributes
- malformed device `acoustic_metrics` fall back to legacy backend acoustic compute during rollout
- missing or malformed `acoustic_windows` do not block the request; backend drops them and uses coarse session-level fallback windows

This plan is a corrected replacement, not a verbatim copy, of the downloaded migration note.

---

## 2. Correct Request Contract

### Live endpoint

The active device-offload route is:

- `POST /analyze/full`

Do not document `/audio/analyze` as the target offload path for this migration.

### Multipart fields

The frontend should send:

- `audio`: compressed speech audio artifact for transcription
- `audio_acoustic_json`: JSON payload as a multipart string or JSON file part
- `user_id`
- existing metadata fields already supported by `/analyze/full`

### `audio_acoustic_json` payload shape

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

Contract notes:

- `audio_acoustic_json` replaces the older idea of sending four standalone form fields
- `acoustic_windows` is optional in phase 1
- `acoustic_windows: []` is valid and should be treated the same as omission
- metric values should be numeric JSON values, not strings where possible
- export values rounded to 4 decimals to reduce frontend/backend drift

### Artifact rules

For the new device acoustic path, the frontend should upload an actual audio artifact such as:

- `mp3`
- `m4a`
- `aac`
- `wav`

Do not send `mp4`, `mov`, or `m4v` when using the device acoustic path. The live backend rejects video-container uploads when `audio_acoustic_json.acoustic_metrics` is present.

Preferred new-client artifact:

- mono
- `16kHz`
- compressed for speech transcription

---

## 3. Frontend Acoustic Extraction Parity Spec

### Implementation rule

The frontend is free to use a different DSP stack from Librosa. It does **not** need to recreate backend internals line-for-line.

However, the frontend must preserve the **meaning** of the four backend-facing metrics so downstream scoring remains stable. The goal is behavioral equivalence, not implementation identity.

### Metric intent

- `pitch_variance_normalized`: normalized pitch expressiveness across voiced speech frames
- `jitter_normalized`: normalized short-horizon pitch instability across consecutive voiced estimates
- `energy_variation_normalized`: normalized loudness variability across voiced frames
- `pause_ratio`: proportion of frames classified as silent using the shared silence threshold

### Frontend parity requirements

Use frontend-native extraction, but keep these compatibility rules:

- compute F0 per analysis frame using the chosen React Native pitch detector
- compute RMS per analysis frame using the frontend frame extractor
- ignore unvoiced frames for pitch-derived metrics
- use backend thresholds from `config.py` / `referenced_formuals.md`
- clamp exported scalar scores to `[0.0, 1.0]`
- round exported scalar scores to 4 decimals

### Parity formulas

These formulas preserve current backend metric semantics while allowing a frontend-specific extraction stack.

#### 3.1 Pitch variance normalized

Intent:

- measure how much voiced pitch varies relative to the speaker's average voiced pitch

Frontend parity formula:

```text
voiced_f0 = f0_frames filtered to frames with valid voiced pitch

if len(voiced_f0) < 2:
  pitch_variance_normalized = 0.0
else:
  pv_raw = std(voiced_f0) / max(mean(voiced_f0), eps)
  pitch_variance_normalized =
    clamp01((pv_raw - PITCH_VARIANCE_MIN) / (PITCH_VARIANCE_MAX - PITCH_VARIANCE_MIN))
```

Why:

- current backend semantics are coefficient-of-variation style pitch expressiveness
- frontend should preserve that meaning even if the pitch detector differs from `librosa.pyin`

#### 3.2 Jitter normalized

Intent:

- measure local pitch instability between consecutive voiced estimates

Frontend parity formula:

```text
voiced_f0 = f0_frames filtered to frames with valid voiced pitch

if len(voiced_f0) < 2:
  jitter_normalized = 0.0
else:
  jitter_raw = mean(abs(diff(voiced_f0))) / max(mean(voiced_f0), eps)
  jitter_normalized = clamp01(jitter_raw / JITTER_THRESHOLD)
```

Why:

- current backend behavior uses frame-to-frame F0 delta semantics
- frontend should preserve this metric meaning rather than switching to a different vocal-jitter definition during this migration

#### 3.3 Energy variation normalized

Intent:

- measure loudness variability across the session

Frontend parity formula:

```text
if len(rms_frames) < 2:
  energy_variation_normalized = 0.0
else:
  energy_raw = std(rms_frames) / max(mean(rms_frames), eps)
  energy_variation_normalized = clamp01(energy_raw / ENERGY_VAR_THRESHOLD)
```

Why:

- current backend semantics are coefficient-of-variation style loudness variability
- frontend should preserve that meaning with frontend-native RMS extraction

#### 3.4 Pause ratio

Intent:

- measure how much of the session is silent

Frontend parity formula:

```text
silent_frames = count(rms_frames where rms <= PAUSE_RMS_THRESHOLD)
pause_ratio = silent_frames / total_frames
pause_ratio = clamp01(pause_ratio)
```

Why:

- pause classification remains tied to the shared silence floor
- the frontend may use a different frame extractor, but not a different silence concept

### DSP calibration guidance

The frontend extractor should be tuned for parity, not novelty.

Calibrate the following against backend outputs:

- frame size
- hop size
- sample rate conversion
- normalization strategy
- voiced/unvoiced gating
- pitch confidence threshold
- any smoothing applied before exported metrics are computed

The frontend must validate its acoustic outputs against the legacy backend extractor on a shared audio sample set. If drift exceeds the agreed tolerance band, tune detector settings and framing first; do not redefine the metrics.

Recommended parity target:

- keep all four exported scores within a small agreed tolerance band, such as `+/- 0.05`, on representative speech samples

---

## 4. Backend Hardening Requirements

The backend already supports `audio_acoustic_json`, `acoustic_payload`, and optional `acoustic_windows`. This migration work is now about validation, clamping, and clearer rollout behavior, not greenfield route design.

### 4.1 `audio/pipeline.py` validation for `acoustic_metrics`

Before normalizing device acoustics:

- require `acoustic_metrics` to be a JSON object
- require all four keys:
  - `pitch_variance_normalized`
  - `jitter_normalized`
  - `energy_variation_normalized`
  - `pause_ratio`
- coerce numeric-like values to float
- reject non-numeric values
- reject `NaN` and infinite values
- clamp accepted metric values into `[0.0, 1.0]`

### 4.2 Rollout behavior for invalid metrics

During rollout:

- if `audio_acoustic_json.acoustic_metrics` is malformed, treat the device payload as invalid
- log that invalid device acoustics were received
- fall back to legacy backend preprocessing and acoustic extraction

Do **not** silently trust malformed device metric values.

### 4.3 `acoustic_windows` validation before aggregation

If `acoustic_windows` is present:

- require it to be a list
- require every element to be an object
- require `window_index` to be an integer `>= 0`
- require `time_start` and `time_end` to be finite numbers
- require `0 <= time_start < time_end`
- require `pitch_variance_normalized` and `pause_ratio` to be numeric
- clamp `pitch_variance_normalized` and `pause_ratio` to `[0.0, 1.0]`
- resolve duplicate `window_index` values deterministically

Recommended duplicate handling:

- last valid window wins for a duplicated `window_index`
- backend should sort normalized windows by `window_index` before use

### 4.4 Rollout behavior for invalid windows

This behavior is intentionally softer than invalid metrics.

If session-level `acoustic_metrics` is valid but `acoustic_windows` is malformed:

- log the issue
- ignore invalid windows
- continue using session-level acoustics
- let `audio/window_aggregator.py` fall back to coarse transcript-aligned windows

Missing or empty `acoustic_windows` should remain valid.

---

## 5. Backend Reality Check

Describe the backend changes as follow-up hardening against the current codebase, not as new feature creation.

Already true in this repo:

- `orchestrator/routes.py` already accepts `audio_acoustic_json`
- `audio/pipeline.py` already accepts `acoustic_payload`
- `audio/window_aggregator.py` already accepts optional `acoustic_windows`

The migration work here is:

- tighten request-contract documentation
- align frontend upload behavior to the live route contract
- validate and clamp device acoustic values
- clarify fallback behavior
- preserve transcript, filler, timing, window aggregation, event detection, and derived attributes on backend

What stays on backend:

- transcription
- filler detection
- timing metrics
- window aggregation merge with transcript-derived data
- event detection
- derived audio attributes
- evaluation and persistence

---

## 6. Verification Plan

### Request contract checks

- valid `audio_acoustic_json` with valid `acoustic_metrics` and no `acoustic_windows`
- valid `audio_acoustic_json` with valid `acoustic_metrics` and valid `acoustic_windows`
- absence of `audio_acoustic_json` to confirm legacy backend acoustic path still works
- new-client request using `mp3` audio artifact
- new-client request using `mp4` artifact to confirm documented rejection on `/analyze/full`

### Validation checks

- malformed `acoustic_metrics` values such as strings that are not numeric, `null`, `NaN`, infinite values, and out-of-range numbers
- valid `acoustic_metrics` plus malformed `acoustic_windows`
- duplicate `window_index` values in `acoustic_windows`
- negative or reversed `time_start` / `time_end`

### Parity checks

- compare frontend acoustic outputs against the legacy backend extractor on a shared sample set
- verify tolerance on:
  - `pitch_variance_normalized`
  - `jitter_normalized`
  - `energy_variation_normalized`
  - `pause_ratio`

### Downstream regression checks

- window aggregation still produces usable fallback windows
- event detection still triggers off the merged window payload
- derived audio attributes remain stable
- final evaluation response shape remains unchanged

---

## 7. Assumptions And Defaults

- This document is the corrected replacement for the downloaded migration note.
- Frontend formula design optimizes for backend parity, using frontend-native DSP methods.
- Invalid `acoustic_metrics` trigger fallback to legacy backend acoustic compute during rollout.
- Missing or malformed `acoustic_windows` are tolerated and dropped in favor of session-level fallback behavior.
- Current threshold values continue to come from `config.py` and `reference_documents/referenced_formuals.md`.
