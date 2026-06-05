# Speaker Cadence Profiling System
## Public Speaking Coach App — Feature Integration Document

**Document Type:** Feature Design & Integration Reference  
**Version:** 1.0  
**Date:** 2026-05-17  
**Scope:** Audio Pipeline Extension + Cadence Classifier + Evaluation Engine + LLM Prompt Adaptation  
**Status:** Ready for Implementation Planning

---

## Table of Contents

1. [What This Feature Is](#1-what-this-feature-is)
2. [Why We Are Building It](#2-why-we-are-building-it)
3. [The Three Cadence Categories](#3-the-three-cadence-categories)
4. [Existing Metrics Audit](#4-existing-metrics-audit)
5. [New Metrics We Must Add](#5-new-metrics-we-must-add)
6. [Why Each New Metric Is Necessary](#6-why-each-new-metric-is-necessary)
7. [How New Metrics Feed Into Existing Calculations](#7-how-new-metrics-feed-into-existing-calculations)
8. [The Cadence Classifier](#8-the-cadence-classifier)
9. [How Feedback Changes Per Cadence Type](#9-how-feedback-changes-per-cadence-type)
10. [Database Schema Changes](#10-database-schema-changes)
11. [New Files and Modified Files](#11-new-files-and-modified-files)
12. [config.py Additions](#12-configpy-additions)
13. [Integration Into the Existing Pipeline](#13-integration-into-the-existing-pipeline)
14. [LLM Prompt Changes](#14-llm-prompt-changes)
15. [Build Order](#15-build-order)

---

## 1. What This Feature Is

The **Speaker Cadence Profiling System** is an extension to the existing audio analysis pipeline. It identifies each user's natural speaking rhythm — their cadence — during an initial calibration period of three sessions, classifies them into one of three cadence profiles, and then adapts all coaching feedback to work *with* that natural rhythm rather than against a universal ideal.

A cadence profile is not a score. It is a classification of how someone naturally speaks — their default speed, the way they pause, whether their pitch rises or falls, how rhythmically consistent their words are, and how much their speed varies. Once this profile is established, the system understands the difference between a behaviour that is a deliberate stylistic choice and one that is a genuine coaching problem.

**Example of why this matters:**

A fast speaker at 185 WPM who consistently varies their tempo (sometimes 160, sometimes 210, sometimes 175) is using speed variation as a tool. The coaching message is: *"your variation is good — now add strategic pauses at key transitions."*

A fast speaker at 185 WPM whose tempo variance is flat (always 183–187 WPM) is locked in one gear. The coaching message is: *"you're fast but monotone in pace — vary your speed deliberately to signal what's important."*

Without a cadence profile, both speakers get the same feedback: *"you're speaking too fast."* That is wrong for the first speaker and incomplete for the second.

---

## 2. Why We Are Building It

### The current system's limitation

The current audio pipeline scores every user against fixed universal targets stored in `config.py`. For example:

```python
OPTIMAL_WPM = 145.0
```

Every user's speech rate is scored as a deviation from 145 WPM. This means a naturally fast speaker who delivers brilliantly at 178 WPM will consistently receive a low `speech_rate_score`, and the LLM will generate coaching feedback telling them to slow down — even though their delivery may be perfectly effective for their style.

The same problem applies to pause usage, pitch movement, and rhythm. The thresholds in the current system represent a single idealized speaker. Real speakers are not one type.

### What cadence profiling adds

- **Personalized baselines.** The system learns what *normal* looks like for each individual user over their first three sessions, then coaches relative to that baseline.
- **Context-aware coaching.** The LLM receives the user's cadence profile as part of its prompt, which changes the entire framing of suggestions. A measured pacer is never told to speak faster. A fast driver is never told to simply slow down — they are told where and why to brake.
- **Better progress tracking.** A fast driver improving their tempo variation from σ=8 WPM to σ=22 WPM over four weeks is making real progress. Without cadence profiling, the delta engine never captures this because it is not comparing to the right baseline.
- **Feels genuinely personalized.** Users feel the app understands them rather than judging them against a standard they did not sign up for.

---

## 3. The Three Cadence Categories

These are the three profiles the classifier assigns after the calibration period. Every subsequent session's coaching is framed through this lens.

---

### 3.1 Fast Driver

**Defining characteristics:**
- Natural WPM baseline above 170
- Low inter-word gap σ (consistent rapid firing of words)
- Low pause count per minute (avoids pausing)
- Short mean pause duration (pauses are brief fillers, not deliberate rests)
- Tempo fluctuation varies — this is the key split within the category (see Section 8)

**What this speaker is doing well:**  
Energy, momentum, confidence in delivery. They do not seem hesitant or underprepared.

**What this speaker needs to work on:**  
Strategic deceleration for emphasis. Deliberate pause placement at key transitions. Ensuring that speed does not become a wall of words that the audience cannot process.

**What coaching must NOT do:**  
Tell them to slow down to 145 WPM. That is not their natural voice and they will resist it. Instead, coaching targets specific moments — *"at 01:24, you moved into the conclusion without any pause. Your audience had no signal that a shift was happening."*

---

### 3.2 Measured Pacer

**Defining characteristics:**
- Natural WPM baseline below 135
- High pause count per minute (stops frequently)
- Long mean pause duration (pauses are substantial)
- High inter-word gap σ (deliberate rhythm, not monotone but spaced)
- Often falling or flat pitch contour (authority signal, or flatness)

**What this speaker is doing well:**  
Clarity, deliberateness, makes the audience feel they can follow. Pauses signal importance effectively.

**What this speaker needs to work on:**  
Avoiding monotony. Adding speed bursts during lower-stakes content so that deliberate pauses at high-stakes moments stand out. Ensuring the slow pace reads as authority, not uncertainty.

**What coaching must NOT do:**  
Push them toward 145–160 WPM as a target. Their pace is often a stylistic strength. Instead, coaching introduces *contrast* — *"your average pace is strong, but every sentence is the same speed. Try accelerating through the background context at 01:10 so the key point at 01:45 hits harder."*

---

### 3.3 Melodic Speaker

**Defining characteristics:**
- Natural WPM baseline between 135–170 (the middle zone)
- High pitch variance and high pitch contour oscillation (pitch moves up and down expressively)
- Moderate inter-word gap σ (rhythm varies with emotional content)
- High tempo fluctuation (naturally speeds up and slows down with the narrative)

**What this speaker is doing well:**  
Expressiveness, emotional engagement, the audience feels the speaker's investment in the content.

**What this speaker needs to work on:**  
Using their natural pitch range strategically rather than uniformly. A melodic speaker who uses expressive pitch on *every* sentence trains the audience to tune it out. Coaching targets pitch economy — save the big pitch movements for key moments.

**What coaching must NOT do:**  
Tell them to flatten their delivery for "professionalism." Their expressiveness is their strongest asset. Instead, coaching helps them be selective: *"your pitch variation is excellent, but it peaked at similar levels on 14 different moments. Your audience cannot tell which ones matter. Reserve the biggest pitch drop for your single most important point."*

---

## 4. Existing Metrics Audit

Before adding anything, we must be precise about what the current audio pipeline already computes and what each metric actually captures. This prevents duplication.

### Metrics in `audio/acoustic_extractor.py`

| Metric | What it actually measures | What it does NOT capture |
|--------|--------------------------|--------------------------|
| `pitch_variance_normalized` | How wide the pitch range is across the session — the spread between high and low F0 values, normalized to [0,1] | Which *direction* pitch moves. Does not distinguish rising from falling from oscillating contours |
| `jitter_normalized` | Micro cycle-to-cycle instability in pitch — vocal tremor, nervous wobble | This is about voice quality/steadiness, not about expressive pitch movement |
| `pause_ratio` | Total silent time divided by total audio duration — a fraction | How *many* pauses occurred. How *long* individual pauses were. Completely conflates frequent short pauses with rare long ones |
| `energy_variation_normalized` | How much the RMS (loudness) varies across the session | Directional energy trends — whether the speaker builds to a climax or front-loads energy |
| `rms_array` (raw) | Per-frame energy values passed to downstream stages | Not a scored metric; available for new computations |
| `f0_array` (raw) | Per-frame fundamental frequency values | Not a scored metric; available for new computations |

### Metrics in `audio/timing_metrics.py`

| Metric | What it actually measures | What it does NOT capture |
|--------|--------------------------|--------------------------|
| `speech_rate_wpm` | Total words divided by speaking duration — one number for the whole session | How WPM *changes* over time. Hides all variation behind an average |
| `speech_rate_score` | Scored deviation from `OPTIMAL_WPM` (145) — how far from the universal ideal | The user's natural baseline. A 178 WPM score is always "bad" even if the user is naturally a 178 WPM speaker |
| `speech_rate_instability_normalized` | Standard deviation of WPM across 5-second windows, normalized to [0,1] against a threshold | The *raw* σ value before normalization. The normalized score loses the absolute magnitude, which matters for cadence classification |
| `wpm_per_window` (raw) | Per-window WPM list passed downstream | Available — this is the source for raw WPM σ extraction |

### Metrics in `audio/filler_detector.py`

| Metric | Relevance to cadence |
|--------|---------------------|
| `filler_ratio` | Indirectly relevant — high filler usage often co-occurs with fast drivers filling gaps. Not a primary cadence signal |
| `filler_words_used` | Not relevant to cadence |

### Key finding from this audit

The existing system has **no metric that captures**:
1. How many pauses occurred (only fraction of time in silence)
2. How long individual pauses were on average (only total ratio)
3. The directional movement of pitch (only total range width)
4. The rhythmic consistency of word spacing (nothing in the system touches this)
5. The raw WPM σ value at its natural magnitude (only normalized score)

These five gaps are exactly what the new metrics fill.

---

## 5. New Metrics We Must Add

These are the six raw values that feed the cadence classifier. They are computed once per session and stored alongside existing metrics. After three sessions, the classifier averages them and assigns a profile.

### 5.1 Natural WPM Baseline

**Variable name:** `natural_wpm_baseline`  
**Type:** `float` (raw, not normalized)  
**Unit:** Words per minute  
**Source:** Average of `speech_rate_wpm` across the user's first three sessions, read from `session_scores` in Supabase

**How it is computed:**

```
natural_wpm_baseline = mean(speech_rate_wpm[session_1], speech_rate_wpm[session_2], speech_rate_wpm[session_3])
```

This is not a new per-session extraction — it is computed by the cadence classifier after session 3 by reading stored values from the database. No change to `acoustic_extractor.py` or `timing_metrics.py` required.

**Why it matters:**  
This is the anchor of the entire classification. It separates fast drivers (above 170) from measured pacers (below 135) from melodic speakers (135–170). The current `speech_rate_score` cannot serve this purpose because it is a scored deviation from 145, not the raw speed.

---

### 5.2 Pause Count Per Minute

**Variable name:** `pause_count_per_minute`  
**Type:** `float`  
**Unit:** Pauses per minute of speaking time  
**Source:** New computation in `audio/cadence_extractor.py` using `f0_array`

**How it is computed:**

```
pauses = []
in_pause = False
pause_start = None

for i, f0_val in enumerate(f0_array):
    t = i / frame_rate
    if f0_val < CADENCE_SILENCE_F0_THRESHOLD and rms_array[i] < CADENCE_SILENCE_RMS_THRESHOLD:
        if not in_pause:
            in_pause = True
            pause_start = t
    else:
        if in_pause:
            duration = t - pause_start
            if duration >= CADENCE_MIN_PAUSE_DURATION:
                pauses.append(duration)
            in_pause = False

pause_count_per_minute = len(pauses) / (speaking_duration_seconds / 60.0)
```

Constants from `config.py`: `CADENCE_SILENCE_F0_THRESHOLD`, `CADENCE_SILENCE_RMS_THRESHOLD`, `CADENCE_MIN_PAUSE_DURATION`

**Why it is separate from `pause_ratio`:**  
`pause_ratio` = 0.15 could mean 1 pause of 9 seconds in a 60-second clip, or 18 pauses of 0.5 seconds each. The cadence profile of those two speakers is completely different. This metric captures the *frequency* dimension. `mean_pause_duration` (below) captures the *length* dimension. Together they replace `pause_ratio` as the primary pause signal in cadence computation.

---

### 5.3 Mean Pause Duration

**Variable name:** `mean_pause_duration_seconds`  
**Type:** `float`  
**Unit:** Seconds  
**Source:** Same computation pass as `pause_count_per_minute` in `audio/cadence_extractor.py`

**How it is computed:**

```
mean_pause_duration_seconds = mean(pauses) if len(pauses) > 0 else 0.0
```

Same `pauses` list built in the pause count computation above. No additional pass over the data required.

**Why it matters for cadence classification:**  
A measured pacer has infrequent but long pauses (mean > 0.75s). A fast driver has frequent but very short pauses (mean < 0.35s), often at filler-word locations. A melodic speaker sits in between. The *combination* of count and duration gives a far richer pause signature than the ratio alone.

---

### 5.4 Inter-Word Gap Standard Deviation

**Variable name:** `inter_word_gap_sigma`  
**Type:** `float`  
**Unit:** Seconds  
**Source:** New computation in `audio/cadence_extractor.py` using AssemblyAI `words` list

**How it is computed:**

```
gaps = []
for i in range(1, len(words)):
    gap = words[i]['start'] - words[i-1]['end']
    if gap >= 0:       # exclude negative gaps from transcription artifacts
        gaps.append(gap)

inter_word_gap_sigma = std(gaps) if len(gaps) > 1 else 0.0
```

**Why this approximates syllable timing:**  
True syllable timing requires a syllable boundary detector — a complex acoustic model. Inter-word gap σ from transcript timestamps is a practical approximation that captures the same rhythmic feel at near-zero additional cost. A speaker with consistent rhythmic spacing has low σ. A speaker with expressive rhythmic variation (the melodic profile) has high σ. A fast driver who fires words in bursts has moderate-to-low σ but a different pause signature.

**Why nothing in the existing system captures this:**  
`speech_rate_instability_normalized` measures WPM variance across 5-second windows — that is macro-level speed change. Inter-word gap σ measures micro-level rhythm within sentences — a completely different dimension of cadence.

---

### 5.5 F0 Contour Slope Per Window

**Variable name:** `f0_contour_mean_slope`  
**Type:** `float`  
**Unit:** Hz per second  
**Source:** New computation in `audio/cadence_extractor.py` using `f0_array`

**How it is computed:**

```
window_slopes = []
window_frames = int(WINDOW_SIZE_SECONDS * frame_rate)

for w_start in range(0, len(f0_array) - window_frames, window_frames):
    window = f0_array[w_start : w_start + window_frames]
    voiced = window[window > CADENCE_SILENCE_F0_THRESHOLD]   # exclude silence frames
    
    if len(voiced) < MIN_VOICED_FRAMES_FOR_SLOPE:
        continue
    
    times = linspace(0, WINDOW_SIZE_SECONDS, len(voiced))
    slope, _ = polyfit(times, voiced, deg=1)
    window_slopes.append(slope)

f0_contour_mean_slope = mean(window_slopes) if window_slopes else 0.0
```

Constants from `config.py`: `CADENCE_MIN_VOICED_FRAMES`, `WINDOW_SIZE_SECONDS` (already exists)

**Why this is different from `pitch_variance_normalized`:**  
`pitch_variance_normalized` answers: *"How wide is this speaker's pitch range?"*  
`f0_contour_mean_slope` answers: *"Does the pitch consistently rise, fall, or oscillate?"*

A speaker can have high pitch variance (wide range) while the contour consistently falls — that is an authoritative, decisive cadence. Another speaker can have high pitch variance with a rising contour — that reads as questioning, uncertain. The variance score is identical; the coaching implication is opposite. Contour slope is the missing dimension.

**Interpretation of values:**
- Mean slope > +`CADENCE_PITCH_SLOPE_RISE` threshold → rising pattern (upspeak tendency or melodic build)
- Mean slope < −`CADENCE_PITCH_SLOPE_FALL` threshold → falling pattern (authority, decisiveness)
- Between the two thresholds → oscillating / neutral (melodic speaker signature)

---

### 5.6 Raw WPM Standard Deviation

**Variable name:** `wpm_sigma_raw`  
**Type:** `float`  
**Unit:** Words per minute  
**Source:** Minor change to `audio/timing_metrics.py` — output the raw σ value alongside the existing normalized score

**How it is computed:**

```
# Already computed in timing_metrics.py:
wpm_per_window = [wpm for each 5s window]
wpm_sigma_raw = std(wpm_per_window)

# Already exists:
speech_rate_instability_normalized = clip(wpm_sigma_raw / SPEECH_RATE_INSTABILITY_THRESH, 0.0, 1.0)

# New — just add this to the return dict:
'wpm_sigma_raw': float(wpm_sigma_raw)
```

**Why the normalized score is not sufficient:**  
`speech_rate_instability_normalized` = 0.7 tells you the speaker is quite variable. But a fast driver varies between 160–200 WPM (σ ≈ 20), while a measured pacer varies between 110–155 WPM (σ ≈ 22). The normalized scores are similar. The raw σ combined with the WPM baseline tells you something completely different about each speaker. The raw magnitude is what matters for cadence classification.

**This is not a new computation — it is one extra line in the return dict.** The value is already computed internally. We just need to expose it.

---

## 6. Why Each New Metric Is Necessary

This section answers the question: *could we drop any of these and still classify cadence correctly?*

| Metric | Can we drop it? | What breaks if we do |
|--------|----------------|---------------------|
| `natural_wpm_baseline` | No | This is the primary classifier axis. Without it, fast and slow speakers are indistinguishable |
| `pause_count_per_minute` | No | `pause_ratio` alone cannot separate a speaker with 1 long pause from 20 short pauses — completely different cadence profiles |
| `mean_pause_duration_seconds` | No | Count alone does not distinguish deliberate long pauses (measured pacer) from nervous micro-pauses (anxious fast driver). Both patterns can have similar counts |
| `inter_word_gap_sigma` | Could reduce accuracy | Without it, melodic speakers and fast drivers with similar WPM look identical. This is what distinguishes their rhythmic feel |
| `f0_contour_mean_slope` | Could reduce accuracy | Without it, we cannot separate a speaker with high pitch variance who uses it deliberately (melodic) from one who uses it nervously. Also cannot detect upspeak patterns |
| `wpm_sigma_raw` | No | Without raw σ, we cannot distinguish a fast driver who varies speed intentionally from one who is locked in one gear — which is the most important split within the fast driver category for coaching |

**Minimum viable set if implementation cost is a concern:** `natural_wpm_baseline`, `pause_count_per_minute`, `mean_pause_duration_seconds`, and `wpm_sigma_raw`. These four give a functional classifier. Adding `inter_word_gap_sigma` and `f0_contour_mean_slope` improves accuracy substantially, especially for melodic speaker detection.

---

## 7. How New Metrics Feed Into Existing Calculations

The new cadence metrics do not replace any existing metric. They run alongside the existing pipeline and feed into three places: the cadence classifier (new), the evaluation engine (extended), and the LLM prompt (extended).

### 7.1 Relationship to existing audio derived attributes

The existing `audio/derived_attributes.py` computes four composites: `audio_instability`, `audio_confidence`, `audio_engagement`, `audio_nervousness`. These are weighted combinations of existing metrics.

The cadence system does **not** modify these weights or formulas. Instead, the cadence profile acts as a *reinterpretation layer* in the LLM prompt — the same scores are read differently depending on the user's profile. A `speech_rate_instability_normalized` score of 0.8 is alarming for a measured pacer but positive for a melodic speaker who is correctly varying their tempo.

### 7.2 Relationship to `speech_rate_score`

`speech_rate_score` continues to be computed as a deviation from `OPTIMAL_WPM`. This score still feeds into the existing fusion weights for `clarity` and `confidence` composites.

However, once a cadence profile is established (after session 3), the evaluation engine adds a `cadence_adjusted_rate_note` to the evaluation JSON. This note tells the LLM whether the user's rate is appropriate for their cadence type, separate from the universal score. The LLM uses this to decide whether to surface the rate as a coaching point or frame it as contextual information.

### 7.3 Relationship to `pause_ratio`

`pause_ratio` continues to be computed and scored in the existing pipeline. The new `pause_count_per_minute` and `mean_pause_duration_seconds` are additive — they go into the cadence extractor output and eventually into the cadence profile stored in `user_profiles`.

`pause_ratio` still feeds into `FumbleScore` and the existing derived attribute weights. The new pause metrics feed only into cadence classification and the LLM context block.

### 7.4 Relationship to `pitch_variance_normalized`

`pitch_variance_normalized` continues unchanged in `acoustic_extractor.py`. The new `f0_contour_mean_slope` is computed in the separate `cadence_extractor.py` and does not touch the existing acoustic computation. The LLM receives both: the existing variance score (how wide) and the new contour slope (which direction), and uses them together.

### 7.5 Data flow diagram

```
Audio file
    │
    ├─► acoustic_extractor.py (UNCHANGED)
    │       f0_array, rms_array → pitch_variance, jitter, energy_variation, pause_ratio
    │
    ├─► timing_metrics.py (MINOR CHANGE — add wpm_sigma_raw to return dict)
    │       wpm_per_window → speech_rate_wpm, speech_rate_score,
    │                         speech_rate_instability_normalized, wpm_sigma_raw (NEW)
    │
    ├─► cadence_extractor.py (NEW FILE)
    │       f0_array + rms_array + words list
    │           → pause_count_per_minute (NEW)
    │           → mean_pause_duration_seconds (NEW)
    │           → inter_word_gap_sigma (NEW)
    │           → f0_contour_mean_slope (NEW)
    │
    └─► All outputs → json_builder.py
            Existing audio JSON (UNCHANGED STRUCTURE)
            + cadence_raw_metrics block (NEW BLOCK):
                {
                  "pause_count_per_minute": float,
                  "mean_pause_duration_seconds": float,
                  "inter_word_gap_sigma": float,
                  "f0_contour_mean_slope": float,
                  "wpm_sigma_raw": float
                }

After session 3:
    cadence_classifier.py reads averaged cadence_raw_metrics from session_scores
        → assigns cadence_profile: "fast_driver" | "measured_pacer" | "melodic_speaker"
        → writes to user_profiles.cadence_profile in Supabase

Every subsequent session:
    evaluation/pipeline.py reads cadence_profile from user_profiles
        → adds cadence_context block to evaluation JSON
        → LLM receives cadence_profile in system prompt
        → coaching feedback is framed through cadence lens
```

---

## 8. The Cadence Classifier

The classifier lives in `cadence/classifier.py`. It is called by `evaluation/pipeline.py` after the user's third session completes and is re-evaluated every 10 sessions thereafter to account for genuine improvement.

### 8.1 Input

```python
def classify_cadence(cadence_averages: dict) -> str:
    """
    Input: averaged cadence metrics across sessions 1–3 (or latest 3 sessions for re-evaluation).
    Returns: 'fast_driver' | 'measured_pacer' | 'melodic_speaker'
    All thresholds sourced from config.py — no magic numbers.
    """
```

The `cadence_averages` dict contains:
```python
{
    "natural_wpm_baseline":       float,   # avg speech_rate_wpm across 3 sessions
    "pause_count_per_minute":     float,   # avg across 3 sessions
    "mean_pause_duration_seconds": float,  # avg across 3 sessions
    "inter_word_gap_sigma":       float,   # avg across 3 sessions
    "f0_contour_mean_slope":      float,   # avg across 3 sessions
    "wpm_sigma_raw":              float    # avg across 3 sessions
}
```

### 8.2 Classification logic

The classifier uses a priority-ordered rule set. WPM baseline is checked first because it is the most reliable single signal. Ambiguous WPM cases (the 135–170 range) fall through to secondary signals.

```
STEP 1 — Fast driver check (WPM dominates):
    IF natural_wpm_baseline > CADENCE_FAST_WPM_MIN (170):
        classify as 'fast_driver'
        EXIT

STEP 2 — Measured pacer check:
    IF natural_wpm_baseline < CADENCE_PACER_WPM_MAX (135):
        classify as 'measured_pacer'
        EXIT

STEP 3 — Middle zone (135–170 WPM) — secondary signals decide:
    pitch_melodic = abs(f0_contour_mean_slope) < CADENCE_PITCH_SLOPE_RISE
                    AND inter_word_gap_sigma > CADENCE_RHYTHM_SIGMA_HIGH
    
    IF pitch_melodic AND wpm_sigma_raw > CADENCE_TEMPO_FLUX_HIGH:
        classify as 'melodic_speaker'
    ELIF pause_count_per_minute < CADENCE_PAUSE_FREQ_LOW:
        classify as 'fast_driver'   (borderline fast driver — WPM 155–170, avoids pauses)
    ELSE:
        classify as 'measured_pacer'  (deliberate mid-pace speaker)
```

### 8.3 Within-category split for fast drivers

After the primary classification, fast drivers are additionally sub-tagged with a tempo variation flag. This does not change the profile category but changes the coaching emphasis.

```
IF cadence_profile == 'fast_driver':
    IF wpm_sigma_raw > CADENCE_TEMPO_FLUX_HIGH (28.0):
        cadence_subtype = 'fast_variable'    # intentional variation — coach on pauses
    ELSE:
        cadence_subtype = 'fast_locked'      # single gear — coach on tempo variation first
```

---

## 9. How Feedback Changes Per Cadence Type

This section defines what changes in the LLM coaching output based on cadence profile. The LLM receives a `cadence_context` block in its evaluation JSON. This block contains the profile, the sub-type (for fast drivers), and pre-computed coaching directives that constrain what the LLM should and should not say.

### 9.1 Cadence context block added to evaluation JSON

```json
"cadence_context": {
    "profile": "fast_driver",
    "subtype": "fast_locked",
    "sessions_since_profile_set": 4,
    "natural_wpm_baseline": 183.2,
    "coaching_directive": "This user is a naturally fast speaker. Do NOT suggest slowing to a general pace. Coach on strategic pauses at transitions and deliberate tempo variation. Acknowledge their pace as a strength before suggesting refinements.",
    "forbidden_phrases": [
        "slow down",
        "speak more slowly",
        "your pace is too fast",
        "aim for 145 words per minute"
    ]
}
```

### 9.2 Per-profile coaching constraints

**Fast driver — fast_locked subtype:**
- Must acknowledge their pace as energetic, not as a flaw
- First action item must be about tempo *variation*, not overall slowdown
- Pause coaching should cite specific timestamps from `timestamped_moments`
- Must not reference `OPTIMAL_WPM` as a target

**Fast driver — fast_variable subtype:**
- Acknowledge tempo variation as evidence of intentional delivery
- Focus on *where* pauses land, not whether they exist
- Can coach on pitch if `f0_contour_mean_slope` shows flat contour

**Measured pacer:**
- Must acknowledge deliberateness as a strength
- Action items should target adding *contrast* — brief accelerations — not overall speed
- Pause coaching focuses on variety of pause length, not frequency reduction
- If `f0_contour_mean_slope` shows flat pattern, pitch coaching is the priority

**Melodic speaker:**
- Must acknowledge expressiveness as an asset
- Action items focus on *selectivity* — saving big pitch movements for key moments
- Coach on pitch economy, not pitch reduction
- If `wpm_sigma_raw` is very high, coach on landing moments so variation feels intentional rather than chaotic

### 9.3 Progress framing changes

The existing delta engine computes `speech_rate_instability_normalized` delta. For a fast_locked driver, an increasing delta (more tempo variation) is labelled `"Significant Improvement"` in the cadence system even if the overall rate has not changed. This requires the delta engine to have access to the cadence profile when it generates classification labels for cadence-relevant metrics.

This means `evaluation/delta_engine.py` receives the `cadence_profile` as an additional input and applies different improvement/decline thresholds for `speech_rate_instability_normalized` depending on the profile.

---

## 10. Database Schema Changes

### 10.1 `user_profiles` table — new columns

```sql
ALTER TABLE public.user_profiles
  ADD COLUMN IF NOT EXISTS cadence_profile        text    DEFAULT NULL
    CHECK (cadence_profile IN ('fast_driver', 'measured_pacer', 'melodic_speaker', NULL)),
  ADD COLUMN IF NOT EXISTS cadence_subtype         text    DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS cadence_calibrated      boolean DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS cadence_calibrated_at   timestamptz DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS cadence_next_review_at  integer DEFAULT NULL;  -- session number
```

`cadence_next_review_at` stores the session number at which the profile should be re-evaluated. Set to current session count + 10 each time classification runs.

### 10.2 `session_scores` table — new columns

```sql
ALTER TABLE public.session_scores
  ADD COLUMN IF NOT EXISTS pause_count_per_minute      real DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS mean_pause_duration_seconds real DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS inter_word_gap_sigma        real DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS f0_contour_mean_slope       real DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS wpm_sigma_raw               real DEFAULT NULL;
```

These five columns store the raw cadence metrics per session. The classifier reads them directly from the last three rows when it needs to compute or re-evaluate the profile.

### 10.3 Why session-level storage

The classifier needs session-level raw values, not just averaged values, because:
1. It needs to detect outlier sessions (e.g., one unusually nervous session that skews the average)
2. The re-evaluation logic needs the latest three sessions, not a running average
3. These values are useful for the detailed session analysis view in the app history

---

## 11. New Files and Modified Files

### New files

| File | Purpose |
|------|---------|
| `audio/cadence_extractor.py` | Computes the four new per-session cadence metrics from `f0_array`, `rms_array`, and `words` list |
| `cadence/__init__.py` | Empty package marker |
| `cadence/classifier.py` | Reads averaged cadence metrics from DB, assigns cadence profile, handles re-evaluation |
| `cadence/coaching_directives.py` | Maps cadence profile + subtype → `coaching_directive` string and `forbidden_phrases` list |

### Modified files

| File | What changes |
|------|-------------|
| `audio/timing_metrics.py` | Add `wpm_sigma_raw` to return dict — one line change |
| `audio/pipeline.py` | Call `cadence_extractor.compute_cadence_metrics()` after `acoustic_extractor`, pass result to `json_builder` |
| `audio/json_builder.py` | Add `cadence_raw_metrics` block to output JSON |
| `evaluation/pipeline.py` | Read `cadence_profile` from `user_profiles` after session 3 is confirmed; pass to `delta_engine` and `json_builder`; trigger `cadence/classifier.py` at session 3 and every 10 sessions |
| `evaluation/db_handler.py` | Extend `write_session()` to write the five new cadence metric columns; add `read_cadence_profile()` function; add `write_cadence_profile()` function |
| `evaluation/delta_engine.py` | Accept `cadence_profile` as input; apply profile-aware thresholds for `speech_rate_instability_normalized` delta classification |
| `evaluation/json_builder.py` | Add `cadence_context` block to final evaluation JSON |
| `evaluation/llm_interpreter.py` | System prompt extended to instruct LLM on how to use the `cadence_context` block |
| `config.py` | All new cadence threshold constants (see Section 12) |

---

## 12. config.py Additions

All new constants must be added to `config.py` in a clearly labelled section. No magic numbers anywhere else.

```python
# ═══════════════════════════════════════════════════════════════════
# CADENCE PROFILING — WPM THRESHOLDS
# Source: Research synthesis (NCVS, TED Talk corpus, speech science)
# Note: These are natural baseline WPM ranges, NOT scored deviations
#       from OPTIMAL_WPM. These classify speaker type, not quality.
# ═══════════════════════════════════════════════════════════════════
CADENCE_FAST_WPM_MIN            = 170.0  # above this = fast driver
CADENCE_PACER_WPM_MAX           = 135.0  # below this = measured pacer
                                          # 135–170 = melodic / balanced zone
CADENCE_DANGER_WPM              = 200.0  # always flagged — comprehension drops 17–25%

# ═══════════════════════════════════════════════════════════════════
# CADENCE PROFILING — PAUSE THRESHOLDS
# ═══════════════════════════════════════════════════════════════════
CADENCE_SILENCE_F0_THRESHOLD    = 50.0   # Hz — F0 below this = silence frame
CADENCE_SILENCE_RMS_THRESHOLD   = 0.02   # RMS below this = silence frame
CADENCE_MIN_PAUSE_DURATION      = 0.25   # seconds — shorter gaps are not counted as pauses
CADENCE_PAUSE_FREQ_HIGH         = 4.5    # pauses/min — above this = deliberate pauser
CADENCE_PAUSE_FREQ_LOW          = 1.8    # pauses/min — below this = fast driver pause signature
CADENCE_PAUSE_MEAN_LONG         = 0.75   # seconds — mean duration above this = measured pacer
CADENCE_PAUSE_MEAN_SHORT        = 0.35   # seconds — mean duration below this = fast driver

# ═══════════════════════════════════════════════════════════════════
# CADENCE PROFILING — RHYTHM THRESHOLDS
# ═══════════════════════════════════════════════════════════════════
CADENCE_RHYTHM_SIGMA_HIGH       = 0.38   # seconds — inter-word gap σ above this = melodic/expressive
CADENCE_RHYTHM_SIGMA_LOW        = 0.18   # seconds — inter-word gap σ below this = locked rhythm

# ═══════════════════════════════════════════════════════════════════
# CADENCE PROFILING — PITCH CONTOUR THRESHOLDS
# ═══════════════════════════════════════════════════════════════════
CADENCE_PITCH_SLOPE_RISE        = 1.5    # Hz/second — mean slope above this = rising/upspeak pattern
CADENCE_PITCH_SLOPE_FALL        = -1.5   # Hz/second — mean slope below this = falling/authoritative
CADENCE_MIN_VOICED_FRAMES       = 10     # minimum voiced frames required for slope computation

# ═══════════════════════════════════════════════════════════════════
# CADENCE PROFILING — TEMPO FLUCTUATION THRESHOLDS
# ═══════════════════════════════════════════════════════════════════
CADENCE_TEMPO_FLUX_HIGH         = 28.0   # WPM σ — above this = intentional variation
CADENCE_TEMPO_FLUX_LOW          = 10.0   # WPM σ — below this = locked single gear

# ═══════════════════════════════════════════════════════════════════
# CADENCE PROFILING — CALIBRATION SETTINGS
# ═══════════════════════════════════════════════════════════════════
CADENCE_CALIBRATION_SESSIONS    = 3      # sessions required before first classification
CADENCE_REEVAL_INTERVAL         = 10     # sessions between re-evaluations
CADENCE_OUTLIER_WPM_SIGMA       = 2.0    # sessions beyond this many σ from the 3-session
                                          # mean are excluded from calibration average
```

---

## 13. Integration Into the Existing Pipeline

### 13.1 Where `cadence_extractor.py` is called

In `audio/pipeline.py`, after `acoustic_extractor` and before `json_builder`:

```python
def run_audio_pipeline(audio_path: str, session_id: str) -> dict:
    clean_path  = preprocess_audio(audio_path)
    transcript  = transcribe(clean_path)
    fillers     = detect_fillers(transcript)
    acoustics   = extract_acoustic_features(clean_path)
    timing      = compute_timing_metrics(transcript)
    cadence_raw = compute_cadence_metrics(            # NEW CALL
                      f0_array=acoustics['f0_array'],
                      rms_array=acoustics['rms_array'],
                      words=transcript['words'],
                      speaking_duration=transcript['speaking_duration_seconds']
                  )
    windows     = aggregate_windows(acoustics, timing, fillers, transcript)
    events      = detect_events(windows)
    derived     = compute_derived_attributes(acoustics, timing, fillers)
    return build_audio_json(
        transcript, acoustics, timing, fillers,
        derived, events, cadence_raw, session_id    # cadence_raw added
    )
```

### 13.2 Where classifier is called

In `evaluation/pipeline.py`, after `write_session()`:

```python
def run_evaluation_pipeline(pose_data: dict, audio_data: dict, user_id: str) -> dict:
    # ... existing steps ...
    write_session(user_id, scores, pose_data, audio_data)  # existing

    # NEW — cadence classification trigger
    session_count = get_session_count(user_id)
    cadence_profile = read_cadence_profile(user_id)
    next_review = read_cadence_next_review(user_id)

    if session_count == CADENCE_CALIBRATION_SESSIONS or session_count == next_review:
        cadence_averages = compute_cadence_averages(user_id)    # reads last 3 sessions from DB
        cadence_profile  = classify_cadence(cadence_averages)   # cadence/classifier.py
        write_cadence_profile(user_id, cadence_profile,
                              next_review=session_count + CADENCE_REEVAL_INTERVAL)

    # ... existing json_builder and llm_interpreter calls ...
    # cadence_profile passed to both
```

### 13.3 What the LLM receives additionally

The existing evaluation JSON is extended with one new top-level block:

```json
"cadence_context": {
    "profile": "fast_driver",
    "subtype": "fast_locked",
    "natural_wpm_baseline": 183.2,
    "wpm_sigma_raw": 7.4,
    "coaching_directive": "...",
    "forbidden_phrases": ["..."]
}
```

When `cadence_profile` is `null` (sessions 1–2, before calibration), this block is omitted entirely and the LLM prompt makes no reference to cadence. Coaching during calibration sessions is standard.

---

## 14. LLM Prompt Changes

### 14.1 Addition to system prompt in `llm_interpreter.py`

Appended after the existing hard rules block:

```
CADENCE ADAPTATION RULES (apply only when cadence_context is present in the JSON):

- Read the cadence_context.profile field before generating any coaching.
- Treat cadence_context.coaching_directive as a binding instruction for how to frame
  rate, pause, and rhythm feedback.
- Never use any phrase listed in cadence_context.forbidden_phrases. This is a hard rule.
- If the speaker's speech_rate_score is low but their profile is 'fast_driver', do NOT
  cite this as a primary coaching concern. Reference it only as context.
- For 'measured_pacer' profiles, frame any rate-related feedback as adding contrast,
  not increasing average speed.
- For 'melodic_speaker' profiles, pitch feedback must acknowledge expressiveness as
  an asset before identifying refinements.
- When cadence_context is absent (calibration period), apply no cadence-specific
  framing — use standard coaching language.
```

### 14.2 What does NOT change

- The existing hard rules about never computing or modifying numeric values
- The required JSON output structure (`overall_summary`, `progress_narrative`, etc.)
- The `top_3_action_items` format — cadence coaching simply changes what the items say, not how they are structured
- The `timestamped_moments` format — cadence-aware coaching references the same timestamp events, just with different framing

---

## 15. Build Order

Build in this exact sequence. Each phase depends on the previous.

```
PHASE 0 — Config and Schema
  ├── Add all cadence constants to config.py (Section 12)
  └── Run DB migrations: ALTER TABLE user_profiles (cadence columns)
                         ALTER TABLE session_scores (cadence metric columns)

PHASE 1 — New Extraction
  ├── Create audio/cadence_extractor.py
  │       compute_cadence_metrics() function
  │       pause_count_per_minute, mean_pause_duration_seconds,
  │       inter_word_gap_sigma, f0_contour_mean_slope
  └── Modify audio/timing_metrics.py
          Add wpm_sigma_raw to return dict

PHASE 2 — Pipeline Integration (Audio)
  ├── Modify audio/pipeline.py — add cadence_extractor call
  └── Modify audio/json_builder.py — add cadence_raw_metrics block to output

PHASE 3 — Classifier and Coaching Directives
  ├── Create cadence/__init__.py (empty)
  ├── Create cadence/classifier.py
  │       classify_cadence() with priority-ordered rule set
  │       fast driver subtype logic
  └── Create cadence/coaching_directives.py
          Profile + subtype → coaching_directive + forbidden_phrases map

PHASE 4 — Evaluation Engine Integration
  ├── Modify evaluation/db_handler.py
  │       Extend write_session() with 5 new cadence metric columns
  │       Add read_cadence_profile()
  │       Add write_cadence_profile()
  │       Add compute_cadence_averages() — reads last 3 session rows
  ├── Modify evaluation/pipeline.py
  │       Classifier trigger logic after write_session()
  │       Pass cadence_profile to delta_engine and json_builder
  ├── Modify evaluation/delta_engine.py
  │       Accept cadence_profile input
  │       Profile-aware threshold for speech_rate_instability_normalized
  ├── Modify evaluation/json_builder.py
  │       Add cadence_context block to final JSON
  └── Modify evaluation/llm_interpreter.py
          Extend system prompt with cadence adaptation rules

PHASE 5 — Testing
  ├── Unit: cadence_extractor outputs correct values for known audio fixtures
  ├── Unit: classifier assigns correct profile for inputs at threshold boundaries
  ├── Unit: coaching_directives returns correct forbidden_phrases per profile
  ├── Integration: audio pipeline output JSON contains cadence_raw_metrics block
  ├── Integration: evaluation JSON contains cadence_context after session 3
  └── Integration: LLM output does not contain forbidden_phrases for each profile
```

---

## Summary

| What | Why |
|------|-----|
| `pause_count_per_minute` (new) | `pause_ratio` conflates frequency and duration — cannot classify cadence type without separating them |
| `mean_pause_duration_seconds` (new) | Same source as count, zero extra cost, completes the pause signature |
| `inter_word_gap_sigma` (new) | Nothing in the system captures rhythmic feel. Approximates syllable timing using existing transcript data |
| `f0_contour_mean_slope` (new) | `pitch_variance_normalized` captures range width only. Contour slope captures direction — rising, falling, oscillating — which determines coaching approach |
| `wpm_sigma_raw` (minor change) | Already computed inside `timing_metrics.py`. Exposing the raw value alongside the normalized score costs one line and enables the fast_locked vs fast_variable split |
| Cadence classifier | Turns the six raw values into a persistent user profile after session 3. Profile is the anchor for all subsequent personalized coaching |
| `cadence_context` in evaluation JSON | Gives the LLM the information it needs to frame coaching appropriately per speaker type without changing any score computation |
| `forbidden_phrases` in coaching directive | Prevents the LLM from generating feedback that contradicts the user's cadence strengths — the single most common failure of universal coaching systems |
