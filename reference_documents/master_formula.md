# Multimodal Public Speaking System: Formula Master Reference

This document provides a structured and systematic breakdown of all deterministic formulas used across the Audio, Pose, and Evaluation pipelines.

---

## 1. Audio Pipeline Formulas

*Analyzes speech acoustics, timing, and linguistic fillers.*

### 1.1 Acoustic & Pitch Metrics

| Metric | Formula | Purpose |
|--------|---------|---------|
| **Pitch Variance (PV)** | `PV = σ(F0) / μ(F0)` | Measures tonal range. High variance = expressive; Low = monotone. |
| **Pitch Normalization** | `PV_norm = (PV - 0.05) / (0.50 - 0.05)` | Maps raw variance to a [0, 1] scale for scoring. |
| **Pitch Jitter** | `Jitter = (1 / n-1) * Σ \| f_{i+1} - f_i \|` | Measures frame-to-frame pitch instability. |
| **Energy Variation** | `EnergyVar = σ(E) / μ(E)` | Measures volume consistency and dynamic range. |

### 1.2 Timing & Linguistic Metrics

| Metric | Formula | Purpose |
|--------|---------|---------|
| **Speech Rate (WPM)** | `WPM = TotalWords / SpeakingDuration` | Raw words per minute count. |
| **Speech Rate Score** | `RateScore = 1 - \| WPM - 145 \| / 145` | Penalizes deviation from the ideal 145 WPM rate. |
| **Filler Ratio** | `FillerRatio = FillerWords / TotalWords` | Measures reliance on vocal crutches (um, uh, like). |
| **Pause Ratio** | `PauseRatio = PauseDuration / TotalDuration` | Measures density of silence vs. speech. |

### 1.3 Audio Behavioral Indices (Derived)

- **Audio Confidence:**
  ```
  0.40(1 - FillerRatio) + 0.30(1 - PV_norm) + 0.20(RateScore) + 0.10(1 - PauseRatio)
  ```

- **Audio Engagement:**
  ```
  0.35(PitchExp) + 0.35(EnergyExp) + 0.30(RateScore)
  ```

- **Audio Nervousness:**
  ```
  0.30(PV_norm) + 0.20(Jitter) + 0.20(FillerRatio) + 0.15(PauseRatio) + 0.15(RateInstab)
  ```

---

## 2. Pose Pipeline Formulas

*Analyzes physical presence, gestures, and stability using normalized MediaPipe coordinates.*

### 2.1 Coordinate Normalization (Pre-Processing)

- **Translation:**
  ```
  K_translated = K_i - (left_hip + right_hip) / 2
  ```

- **Scaling:**
  ```
  K_j = K_translated / distance(shoulder_mid, hip_mid)
  ```

### 2.2 Core Posture Metrics

| Metric | Formula | Purpose |
|--------|---------|---------|
| **Shoulder Alignment** | `1 - min(\| y'_l_sh - y'_r_sh \|, 1)` | Measures horizontal shoulder levelness. |
| **Spine Straightness** | `1 - min(arccos(spine_vec · vertical / \|\|spine_vec\|\|) / T2, 1)` | Measures vertical torso alignment (T2: deviation threshold). |
| **Posture Openness** | `min(\| x'_l_sh - x'_r_sh \|, 1)` | Measures how open/expansive the stance is. |
| **Head Stability** | `1 - min(std(z'_nose,t) / T3, 1)` | Detects excessive head nodding or twitching. |
| **Body Sway** | `1 - min(std(z'_torso,t) / T4, 1)` | Measures lateral center-of-mass shifting. |

### 2.3 Pose Behavioral Indices (Derived)

- **Posture Stability Index:**
  ```
  0.30(Shoulder) + 0.25(Spine) + 0.20(Head) + 0.15(Sway) + 0.10(Symmetry)
  ```

- **Pose Confidence:**
  ```
  0.40(Stability) + 0.30(Openness) + 0.20(Gaze) + 0.10(Symmetry)
  ```

- **Pose Nervousness:**
  ```
  0.35(1 - Head) + 0.30(1 - Sway) + 0.20(Fidget) + 0.15(MovementVar)
  ```

---

## 3. Final Evaluation Engine Formulas

*Computes the longitudinal progress and cross-modal session aggregates.*

### 3.1 Session Aggregation (Multimodal Integration)

The **Final Session Score (S_final)** is the weighted mean of audio and pose behavioral indices.

- **Overall Score:**
  ```
  0.50(AudioScore) + 0.50(PoseScore)
  ```

### 3.2 Progress Engine (Longitudinal Deltas)

This engine computes the change (Δ) between the current session and a baseline (rolling mean of the last 3 sessions).

| Formula | Definition | Purpose |
|---------|------------|---------|
| **Generic Delta** | `ΔM = M_current - M_baseline` | Tracks any metric's trajectory. |
| **Headline Delta** | `overall_delta = S_curr - S_baseline` | Main progress indicator. |
| **Nervousness Delta** | `nervousness_delta = Nerve_curr - Nerve_baseline` | Negative value indicates improvement. |
| **Behavioral Change** | `filler_change = filler_prev - filler_curr` | Positive value indicates filler reduction. |

### 3.3 Progress Classification Logic

Based on Δ values, the backend determines the status string for the LLM to interpret:

| Status | Condition |
|--------|-----------|
| **Significant Improvement** | Δ > 0.05 |
| **Moderate Improvement** | 0.02 < Δ ≤ 0.05 |
| **Stable** | -0.02 ≤ Δ ≤ 0.02 |
| **Noticeable Decline** | Δ < -0.05 |

---

## 4. Window-Level Event Triggers (Coaching Logic)

*Logic for identifying timestamped anomalies in 5-second windows.*

- **Fumble Spike:**
  ```
  0.35(Filler_w) + 0.25(Pause_w) + 0.20(PitchVar_w) + 0.20(RateInstab_w) > 0.60
  ```

- **Monotone Spike:**
  ```
  PitchVar_normalized_w < 0.10
  ```

- **Vocal Instability:**
  ```
  PitchVar_normalized_w > 0.70  OR  Jitter_normalized_w > 0.65
  ```
