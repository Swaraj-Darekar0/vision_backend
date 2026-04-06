# Referenced Formuals

**Date:** 2026-04-02  
**Purpose:** This is the exact frontend reference file for formulas, thresholds, weights, and required backend config values that must remain numerically aligned with backend behavior during device pipeline offload.

Use this file together with:

- [master_formula.md](/e:/vision/reference_documents/master_formula.md)
- [device_pipeline_offload_spec.md](/e:/vision/reference_documents/device_pipeline_offload_spec.md)

Important rule:

- frontend implementations must match backend math exactly
- if any formula or threshold changes in backend `config.py`, this file must be updated before frontend logic is changed

---

## 1. General Rules

- All normalized scores must be clamped to `[0.0, 1.0]`.
- Use float math, not integer math.
- Preserve the same window size used by backend.
- Preserve the same sample rate used by backend for audio preprocessing.
- Preserve the same metric names in outgoing payloads.

Canonical clamp rule:

```text
clamp01(x) = min(max(x, 0.0), 1.0)
```

---

## 2. Frontend-Required Config Values

These values come from backend `config.py` and must be treated as canonical.

## 2.1 Pose constants

```text
MIN_VISIBILITY_THRESHOLD      = 0.5

POSE_SMOOTHING_MIN_CUTOFF     = 1.0
POSE_SMOOTHING_BETA           = 0.01
POSE_SMOOTHING_D_CUTOFF       = 1.0

SHOULDER_ALIGNMENT_THRESHOLD  = 0.1
SPINE_STRAIGHTNESS_THRESHOLD  = 0.2
HEAD_STABILITY_THRESHOLD      = 0.05
BODY_SWAY_THRESHOLD           = 0.05
FIDGET_THRESHOLD              = 0.1
MOVEMENT_VARIANCE_THRESHOLD   = 0.1
GAZE_DEVIATION_THRESHOLD      = 0.1

SWAY_DEAD_ZONE                = 0.01
POSTURE_OPENNESS_MAX_WIDTH    = 1.0
GESTURE_OPTIMAL_PER_MINUTE    = 6.0
GESTURE_DURATION_MIN_SEC      = 0.3
OPTIMAL_HAND_AMPLITUDE        = 0.45
STILLNESS_OPTIMAL_RATIO       = 0.5
```

## 2.2 Pose derived-attribute weights

```text
POSTURE_STABILITY_WEIGHTS =
  shoulder_alignment: 0.30
  spine_straightness: 0.25
  head_stability: 0.20
  body_sway: 0.15
  symmetry_score: 0.10

POSE_CONFIDENCE_WEIGHTS =
  posture_stability_index: 0.40
  posture_openness: 0.30
  gaze_stability: 0.20
  symmetry_score: 0.10

POSE_NERVOUSNESS_WEIGHTS =
  head_stability: 0.35
  body_sway: 0.30
  fidget_score: 0.20
  movement_variance_normalized: 0.15

POSE_ENGAGEMENT_WEIGHTS =
  gesture_score: 0.40
  amplitude_score: 0.30
  posture_openness: 0.30
```

## 2.3 Audio constants

```text
AUDIO_SAMPLE_RATE              = 16000
AUDIO_TRANSCRIPTION_FORMAT     = "mp3"
AUDIO_TRANSCRIPTION_BITRATE    = "64k"
PYIN_FRAME_LENGTH              = 2048
PYIN_HOP_LENGTH                = 1024

PITCH_VARIANCE_MIN             = 0.05
PITCH_VARIANCE_MAX             = 0.50
JITTER_THRESHOLD               = 0.02
ENERGY_VAR_THRESHOLD           = 0.1
PAUSE_RMS_THRESHOLD            = 0.01
SPEECH_RATE_INSTABILITY_THRESH = 10.0
FILLER_RATIO_CEILING           = 0.20
OPTIMAL_WPM                    = 145.0
FILLER_PAUSE_CONTEXT           = 0.3

WINDOW_SIZE_SECONDS            = 5.0
```

## 2.4 Audio derived-attribute weights

```text
AUDIO_INSTABILITY_WEIGHTS =
  pitch_variance_normalized: 0.30
  jitter_normalized: 0.20
  filler_ratio: 0.20
  pause_ratio: 0.15
  speech_rate_instability_normalized: 0.15

AUDIO_CONFIDENCE_WEIGHTS =
  filler_ratio: 0.40
  pitch_variance_normalized: 0.30
  speech_rate_score: 0.20
  pause_ratio: 0.10

AUDIO_ENGAGEMENT_WEIGHTS =
  pitch_expressiveness: 0.35
  energy_expressiveness: 0.35
  speech_rate_score: 0.30
```

## 2.5 Event thresholds

```text
FUMBLE_SPIKE_THRESHOLD         = 0.60
EXCESSIVE_PAUSE_THRESHOLD      = 0.40
RAPID_SPEECH_WPM_THRESHOLD     = 180.0
MONOTONE_PITCH_THRESHOLD       = 0.10
VOCAL_INSTABILITY_PITCH_THRESH = 0.70
VOCAL_INSTABILITY_JITTER_THRESH = 0.65
ADAPTIVE_SPIKE_STD_MULTIPLIER  = 2.0
```

## 2.6 Evaluation fusion weights

```text
CONFIDENCE_FUSION_WEIGHTS =
  pose_confidence: 0.5
  audio_confidence: 0.5

CLARITY_FUSION_WEIGHTS =
  posture_stability_index: 0.1
  audio_instability: 0.3
  reasoning_clarity: 0.6

ENGAGEMENT_FUSION_WEIGHTS =
  pose_engagement: 0.5
  audio_engagement: 0.5

NERVOUSNESS_FUSION_WEIGHTS =
  pose_nervousness: 0.5
  audio_nervousness: 0.5

OVERALL_FUSION_WEIGHTS =
  confidence: 0.3
  clarity: 0.3
  engagement: 0.2
  nervousness: 0.2
```

## 2.7 Progress thresholds

```text
SIGNIFICANT_IMPROVEMENT_THRESHOLD = 0.05
MODERATE_IMPROVEMENT_THRESHOLD    = 0.02
NOTICEABLE_DECLINE_THRESHOLD      = -0.05
ROLLING_BASELINE_SESSIONS         = 3
```

---

## 3. Pose Formulas

These formulas are required if pose processing is moved to device.

## 3.1 Pose normalization

### Translation

```text
hip_mid = (left_hip + right_hip) / 2
K_translated = K_i - hip_mid
```

### Scaling

```text
shoulder_mid = (left_shoulder + right_shoulder) / 2
torso_length = distance(shoulder_mid, hip_mid)
K_normalized = K_translated / torso_length
```

Guardrail:

- if `torso_length <= 0`, mark frame invalid

## 3.2 Pose metrics

### Shoulder alignment

```text
diff = abs(left_shoulder_y - right_shoulder_y)
score = clamp01(1.0 - diff)
```

### Spine straightness

```text
spine_vec = shoulder_mid - hip_mid
vertical = [0, -1, 0]
angle = arccos(dot(spine_vec, vertical) / norm(spine_vec))
score = clamp01(1.0 - (angle / SPINE_STRAIGHTNESS_THRESHOLD))
```

### Posture openness

```text
width = abs(left_shoulder_x - right_shoulder_x)
score = clamp01(width / POSTURE_OPENNESS_MAX_WIDTH)
```

### Head stability

```text
std_z = std(nose_z across rolling window)
score = clamp01(1.0 - (std_z / HEAD_STABILITY_THRESHOLD))
```

### Body sway

```text
std_x = std(hip_mid_x across rolling window)
if std_x < SWAY_DEAD_ZONE:
  score = 1.0
else:
  score = clamp01(1.0 - (std_x / BODY_SWAY_THRESHOLD))
```

### Gesture score

```text
left_hand_dist = norm(left_wrist - left_hip)
right_hand_dist = norm(right_wrist - right_hip)
mean_dist = (left_hand_dist + right_hand_dist) / 2
score = clamp01(mean_dist / 0.5)
```

### Amplitude score

```text
shoulder_y = mean(left_shoulder_y, right_shoulder_y)
left_amp = max(0, shoulder_y - left_wrist_y)
right_amp = max(0, shoulder_y - right_wrist_y)
max_amp = max(left_amp, right_amp)
score = clamp01(max_amp / OPTIMAL_HAND_AMPLITUDE)
```

### Symmetry score

```text
shoulder_mid_x = mean(left_shoulder_x, right_shoulder_x)
left_dist = abs(left_wrist_x - shoulder_mid_x)
right_dist = abs(right_wrist_x - shoulder_mid_x)
diff = abs(left_dist - right_dist)
score = clamp01(1.0 - diff)
```

### Fidget score

```text
diffs = diff(left_wrist_y across rolling window)
fidget_val = std(diffs)
score = clamp01(fidget_val / FIDGET_THRESHOLD)
```

### Stillness score

```text
for each joint in [left_elbow, right_elbow, left_wrist, right_wrist]:
  dist_to_spine = norm(cross(shoulder_mid - hip_mid, joint - hip_mid)) / norm(shoulder_mid - hip_mid)
mean_dist = average(dist_to_spine values)
score = clamp01(1.0 - (mean_dist / 0.5))
```

## 3.3 Pose session aggregation

- use `WINDOW_SIZE_SECONDS = 5.0`
- for each metric, average valid frame scores inside the window
- for session aggregation, average each metric across all windows

## 3.4 Pose derived attributes

### Posture stability index

```text
stability =
  0.30 * shoulder_alignment +
  0.25 * spine_straightness +
  0.20 * head_stability +
  0.15 * body_sway +
  0.10 * symmetry_score
stability = clamp01(stability)
```

### Pose confidence

```text
gaze_stability = head_stability
pose_confidence =
  0.40 * posture_stability_index +
  0.30 * posture_openness +
  0.20 * gaze_stability +
  0.10 * symmetry_score
pose_confidence = clamp01(pose_confidence)
```

### Pose nervousness

```text
head_instability = 1.0 - head_stability
sway_instability = 1.0 - body_sway
movement_variance_normalized = 1.0 - stillness_score

pose_nervousness =
  0.35 * head_instability +
  0.30 * sway_instability +
  0.20 * fidget_score +
  0.15 * movement_variance_normalized
pose_nervousness = clamp01(pose_nervousness)
```

### Pose engagement

```text
pose_engagement =
  0.40 * gesture_score +
  0.30 * amplitude_score +
  0.30 * posture_openness
pose_engagement = clamp01(pose_engagement)
```

---

## 4. Audio Formulas

These formulas are required if deterministic acoustic processing moves to device.

## 4.1 Audio preprocessing

Frontend must match:

- mono audio
- `16kHz` sample rate
- compressed upload format: `mp3`
- transcription bitrate target: `64k`

## 4.2 Acoustic metrics

### Pitch variance raw

```text
PV = std(voiced_f0) / mean(voiced_f0)
```

### Pitch variance normalized

```text
PV_norm = (PV - PITCH_VARIANCE_MIN) / (PITCH_VARIANCE_MAX - PITCH_VARIANCE_MIN)
PV_norm = clamp01(PV_norm)
```

### Jitter normalized

```text
jitter_raw = mean(abs(diff(voiced_f0))) / mean(voiced_f0)
jitter_norm = clamp01(jitter_raw / JITTER_THRESHOLD)
```

### Energy variation normalized

```text
energy_var_raw = std(rms_array) / mean(rms_array)
energy_var_norm = clamp01(energy_var_raw / ENERGY_VAR_THRESHOLD)
```

### Pause ratio

```text
pause_frames = count(rms_array < PAUSE_RMS_THRESHOLD)
pause_ratio = pause_frames / total_frames
```

## 4.3 Timing metrics

These are still backend-derived today, but they are listed here because frontend must understand downstream dependencies.

### Speech rate WPM

```text
total_duration = end_time - start_time
pause_duration = sum(gaps between consecutive words where gap > 0)
speaking_duration = max(0.1, total_duration - pause_duration)
speech_rate_wpm = total_words / (speaking_duration / 60.0)
```

### Speech rate score

```text
speech_rate_score = clamp01(1.0 - (abs(speech_rate_wpm - OPTIMAL_WPM) / OPTIMAL_WPM))
```

### Speech rate instability normalized

```text
instability_raw = std(wpm_per_window)
instability_norm = clamp01(instability_raw / SPEECH_RATE_INSTABILITY_THRESH)
```

## 4.4 Filler ratio

These are currently backend-derived from transcript:

```text
filler_ratio = filler_count / total_words
filler_ratio_normalized = clamp01(filler_ratio / FILLER_RATIO_CEILING)
```

## 4.5 Fumble score

Final backend window logic uses:

```text
fumble_score =
  0.35 * filler_ratio +
  0.25 * pause_ratio +
  0.20 * pitch_variance_normalized +
  0.20 * speech_rate_instability_normalized
fumble_score = clamp01(fumble_score)
```

## 4.6 Audio derived attributes

### Audio instability

```text
audio_instability =
  0.30 * pitch_variance_normalized +
  0.20 * jitter_normalized +
  0.20 * filler_ratio_normalized +
  0.15 * pause_ratio +
  0.15 * speech_rate_instability_normalized
audio_instability = clamp01(audio_instability)
```

### Audio confidence

```text
audio_confidence =
  0.40 * (1.0 - filler_ratio) +
  0.30 * (1.0 - pitch_variance_normalized) +
  0.20 * speech_rate_score +
  0.10 * (1.0 - pause_ratio)
audio_confidence = clamp01(audio_confidence)
```

### Audio engagement

```text
audio_engagement =
  0.35 * pitch_variance_normalized +
  0.35 * energy_variation_normalized +
  0.30 * speech_rate_score
audio_engagement = clamp01(audio_engagement)
```

### Audio nervousness

```text
audio_nervousness = audio_instability
```

---

## 5. Event Logic Reference

These event rules are currently backend-owned and should not be redefined differently on frontend without an intentional architecture change.

### High fumble spike

```text
if fumble_score > FUMBLE_SPIKE_THRESHOLD
```

### Excessive pause

```text
if pause_ratio > EXCESSIVE_PAUSE_THRESHOLD
```

### Rapid speech segment

```text
if speech_rate_wpm > RAPID_SPEECH_WPM_THRESHOLD
```

### Monotone segment

```text
if pitch_variance_normalized < MONOTONE_PITCH_THRESHOLD
```

### Vocal instability spike

```text
if pitch_variance_normalized > VOCAL_INSTABILITY_PITCH_THRESH
```

### Adaptive spike

```text
delta = window_fumble_score - mean(session_fumble_scores)
if delta > ADAPTIVE_SPIKE_STD_MULTIPLIER * std(session_fumble_scores)
```

---

## 6. Evaluation Formulas

These formulas remain backend-owned today, but frontend must preserve compatible metric names and semantics.

## 6.1 Multimodal fusion

### Confidence

```text
confidence =
  0.5 * pose_confidence +
  0.5 * audio_confidence
confidence = clamp01(confidence)
```

### Clarity

```text
clarity =
  0.1 * posture_stability_index +
  0.3 * (1.0 - audio_instability) +
  0.6 * reasoning_clarity
clarity = clamp01(clarity)
```

### Engagement

```text
engagement =
  0.5 * pose_engagement +
  0.5 * audio_engagement
engagement = clamp01(engagement)
```

### Nervousness

```text
nervousness =
  0.5 * pose_nervousness +
  0.5 * audio_nervousness
nervousness = clamp01(nervousness)
```

### Overall

```text
overall =
  0.3 * confidence +
  0.3 * clarity +
  0.2 * engagement +
  0.2 * (1.0 - nervousness)
overall = clamp01(overall)
```

## 6.2 Delta computation

### Generic improvement-oriented deltas

```text
confidence_delta = confidence_current - confidence_baseline
clarity_delta = clarity_current - clarity_baseline
engagement_delta = engagement_current - engagement_baseline
overall_delta = overall_current - overall_baseline
```

### Nervousness delta

```text
nervousness_delta = nervousness_baseline - nervousness_current
```

### Behavioral deltas

```text
filler_reduction = filler_ratio_baseline - filler_ratio_current
pause_optimization = pause_ratio_baseline - pause_ratio_current
posture_stability_delta = posture_stability_current - posture_stability_baseline
reasoning_clarity_delta = reasoning_clarity_current - reasoning_clarity_baseline
```

### Delta classification

```text
if delta > 0.05: Significant Improvement
elif delta > 0.02: Moderate Improvement
elif delta < -0.05: Noticeable Decline
else: Stable
```

---

## 7. Frontend Payload Naming Requirements

Frontend device-generated payloads must preserve these keys exactly when offloading logic:

### Pose output keys

- `posture_metrics.shoulder_alignment`
- `posture_metrics.spine_straightness`
- `posture_metrics.posture_openness`
- `posture_metrics.head_stability`
- `posture_metrics.body_sway`
- `posture_metrics.gesture_score`
- `posture_metrics.amplitude_score`
- `posture_metrics.symmetry_score`
- `posture_metrics.fidget_score`
- `posture_metrics.stillness_score`
- `derived_pose_attributes.posture_stability_index`
- `derived_pose_attributes.pose_confidence`
- `derived_pose_attributes.pose_nervousness`
- `derived_pose_attributes.pose_engagement`
- `derived_pose_attributes.movement_variance_normalized`
- `derived_pose_attributes.gaze_stability`

### Audio output keys

- `acoustic_metrics.pitch_variance_normalized`
- `acoustic_metrics.jitter_normalized`
- `acoustic_metrics.energy_variation_normalized`
- `acoustic_metrics.pause_ratio`

Important:

- `filler_ratio`
- `speech_rate_wpm`
- `speech_rate_score`
- `speech_rate_instability_normalized`
- `timestamp_events`

remain backend-derived in the current target architecture.

---

## 8. Change-Control Rule

If backend changes any of the following, this file must be updated before frontend code is changed:

- any threshold
- any weight
- any formula
- any required metric key
- any preprocessing constant
- any window size

This file is the frontend implementation reference for device-side deterministic scoring.
