from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Dict, Iterable, Optional

import numpy as np

import config


def build_session_cadence_metrics(
    transcript: Dict,
    timing: Dict,
    fillers: Dict,
    frontend_metrics: Optional[Dict] = None,
) -> Dict:
    frontend_metrics = frontend_metrics or {}
    words = transcript.get("words", [])
    total_words = max(1, len(words))

    inter_word_gaps = []
    repeated_transitions = 0
    total_pause_like_seconds = 0.0
    filler_pause_seconds = 0.0

    for index in range(1, len(words)):
        previous = words[index - 1]
        current = words[index]
        gap = max(0.0, float(current.get("start", 0.0)) - float(previous.get("end", 0.0)))
        inter_word_gaps.append(gap)

        prev_token = _normalize_token(previous.get("word", ""))
        curr_token = _normalize_token(current.get("word", ""))
        if prev_token and curr_token and prev_token == curr_token:
            repeated_transitions += 1

        if gap >= config.CADENCE_MIN_SILENCE_PAUSE_SECONDS:
            total_pause_like_seconds += gap

        if gap >= config.CADENCE_FILLER_PAUSE_SECONDS and (
            prev_token in config.FILLER_WORDS or curr_token in config.FILLER_WORDS
        ):
            filler_pause_seconds += gap
            total_pause_like_seconds += gap

    speech_rate_wpm = float(timing.get("speech_rate_wpm", 0.0))
    wpm_sigma_raw = float(timing.get("wpm_sigma_raw", 0.0))
    stutter_ratio = repeated_transitions / total_words
    filler_ratio = float(fillers.get("filler_ratio", 0.0))
    disfluency_burden = min(1.0, filler_ratio + stutter_ratio)

    return {
        "speech_rate_wpm": speech_rate_wpm,
        "wpm_sigma_raw": wpm_sigma_raw,
        "pause_count_per_minute": float(frontend_metrics.get("pause_count_per_minute", 0.0)),
        "mean_pause_duration_seconds": float(frontend_metrics.get("mean_pause_duration_seconds", 0.0)),
        "f0_contour_mean_slope": float(frontend_metrics.get("f0_contour_mean_slope", 0.0)),
        "voiced_filler_proxy_ratio": float(frontend_metrics.get("voiced_filler_proxy_ratio", 0.0)),
        "inter_word_gap_sigma": float(np.std(inter_word_gaps)) if len(inter_word_gaps) > 1 else 0.0,
        "stutter_ratio": float(stutter_ratio),
        "disfluency_burden": float(disfluency_burden),
        "extended_pause_seconds": float(total_pause_like_seconds),
        "filler_pause_seconds": float(filler_pause_seconds),
    }


def classify_cadence_profile(metrics: Dict, *, is_provisional: bool) -> Dict:
    speech_rate_wpm = float(metrics.get("speech_rate_wpm", 0.0))
    pause_count = float(metrics.get("pause_count_per_minute", 0.0))
    mean_pause = float(metrics.get("mean_pause_duration_seconds", 0.0))
    rhythm_sigma = float(metrics.get("inter_word_gap_sigma", 0.0))
    pitch_slope = float(metrics.get("f0_contour_mean_slope", 0.0))
    wpm_sigma = float(metrics.get("wpm_sigma_raw", 0.0))

    if speech_rate_wpm >= config.CADENCE_FAST_WPM_MIN:
        profile = "fast_driver"
    elif speech_rate_wpm <= config.CADENCE_PACER_WPM_MAX:
        profile = "measured_pacer"
    else:
        profile = "melodic_speaker"

    # Let rhythm/pitch override the middle band when the signal is very expressive.
    if (
        profile != "fast_driver"
        and rhythm_sigma >= config.CADENCE_RHYTHM_SIGMA_HIGH
        and pitch_slope >= config.CADENCE_PITCH_SLOPE_FALL
    ):
        profile = "melodic_speaker"

    subtype = _derive_subtype(profile, pause_count, mean_pause, wpm_sigma)
    label = config.CADENCE_DISPLAY_LABELS.get(profile, "Expressive")

    result = {
        "profile": profile,
        "label": label,
        "subtype": subtype,
        "is_provisional": bool(is_provisional),
        "is_locked": not is_provisional,
        "natural_wpm_baseline": round(speech_rate_wpm, 4),
        "wpm_sigma_raw": round(wpm_sigma, 4),
        "pause_count_per_minute": round(pause_count, 4),
        "mean_pause_duration_seconds": round(mean_pause, 4),
        "inter_word_gap_sigma": round(rhythm_sigma, 4),
        "f0_contour_mean_slope": round(pitch_slope, 4),
        "voiced_filler_proxy_ratio": round(float(metrics.get("voiced_filler_proxy_ratio", 0.0)), 4),
        "stutter_ratio": round(float(metrics.get("stutter_ratio", 0.0)), 4),
        "disfluency_burden": round(float(metrics.get("disfluency_burden", 0.0)), 4),
    }
    result["coaching_directive"] = _build_coaching_directive(result)
    return result


def build_cadence_snapshot(cadence_profile: Optional[Dict]) -> Optional[Dict]:
    if not cadence_profile:
        return None
    return {
        "profile": cadence_profile["profile"],
        "label": cadence_profile["label"],
        "subtype": cadence_profile.get("subtype"),
        "is_provisional": cadence_profile.get("is_provisional", False),
        "is_locked": cadence_profile.get("is_locked", False),
        "natural_wpm_baseline": cadence_profile.get("natural_wpm_baseline", 0.0),
        "wpm_sigma_raw": cadence_profile.get("wpm_sigma_raw", 0.0),
        "pause_count_per_minute": cadence_profile.get("pause_count_per_minute", 0.0),
        "mean_pause_duration_seconds": cadence_profile.get("mean_pause_duration_seconds", 0.0),
        "inter_word_gap_sigma": cadence_profile.get("inter_word_gap_sigma", 0.0),
        "f0_contour_mean_slope": cadence_profile.get("f0_contour_mean_slope", 0.0),
    }


def build_cadence_display(cadence_profile: Optional[Dict], *, is_diagnostic: bool) -> Optional[Dict]:
    if not cadence_profile:
        return None

    profile = cadence_profile["profile"]
    label = cadence_profile["label"]
    inspiration = config.CADENCE_INSPIRATIONS.get(profile)
    title = f"{label} cadence"

    if profile == "fast_driver":
        description = (
            f"You move through ideas with speed and urgency, similar to the momentum you hear in {inspiration}."
        )
        coaching = "Keep the energy, then add cleaner brakes before your key points so the audience can land with you."
    elif profile == "measured_pacer":
        description = (
            f"You speak with a calm, grounded rhythm that can feel authoritative, much like {inspiration}."
        )
        coaching = "Preserve your deliberate pace, but create sharper contrast by tightening pauses that slow the message too much."
    else:
        description = (
            f"You sound naturally expressive and dynamic, with a cadence that can feel engaging like {inspiration}."
        )
        coaching = "Use your natural variation selectively so the biggest shifts in tone and speed highlight your most important ideas."

    if cadence_profile.get("is_provisional"):
        description = f"This is your early cadence read. {description}"

    return {
        "profile": profile,
        "label": label,
        "title": title,
        "description": description,
        "coaching_direction": coaching,
        "inspiration_name": inspiration,
        "show_image_placeholder": bool(is_diagnostic),
        "is_provisional": cadence_profile.get("is_provisional", False),
        "is_locked": cadence_profile.get("is_locked", False),
    }


def maybe_refresh_cadence_profile(
    *,
    existing_profile: Optional[Dict],
    cadence_history: Iterable[Dict],
    session_metrics: Dict,
    is_diagnostic: bool,
    processed_at: Optional[str] = None,
) -> tuple[Optional[Dict], Optional[Dict]]:
    processed_dt = _parse_datetime(processed_at) or datetime.now(timezone.utc)
    history = [row for row in cadence_history if row]

    if existing_profile and existing_profile.get("next_review_at"):
        review_dt = _parse_datetime(existing_profile.get("next_review_at"))
        if review_dt and processed_dt < review_dt:
            return existing_profile, None

    candidate_rows = [*history, session_metrics]
    candidate_rows = candidate_rows[-config.CADENCE_HISTORY_SESSIONS :]

    if len(candidate_rows) < config.CADENCE_CALIBRATION_SESSIONS:
        provisional = classify_cadence_profile(session_metrics, is_provisional=True)
        return None, provisional

    averaged = _average_metrics(candidate_rows)
    locked = classify_cadence_profile(averaged, is_provisional=False)
    locked["profile_locked_at"] = processed_dt.isoformat()
    locked["next_review_at"] = (processed_dt + timedelta(days=config.CADENCE_REVIEW_DAYS)).isoformat()
    return locked, None


def _average_metrics(rows: Iterable[Dict]) -> Dict:
    numeric_keys = [
        "speech_rate_wpm",
        "wpm_sigma_raw",
        "pause_count_per_minute",
        "mean_pause_duration_seconds",
        "inter_word_gap_sigma",
        "f0_contour_mean_slope",
        "voiced_filler_proxy_ratio",
        "stutter_ratio",
        "disfluency_burden",
    ]
    averaged = {}
    for key in numeric_keys:
        values = [float(row.get(key, 0.0)) for row in rows]
        averaged[key] = float(np.mean(values)) if values else 0.0
    return averaged


def _derive_subtype(profile: str, pause_count: float, mean_pause: float, wpm_sigma: float) -> str:
    if profile == "fast_driver":
        return "fast_locked" if wpm_sigma <= config.CADENCE_TEMPO_SIGMA_LOW else "fast_variable"
    if profile == "measured_pacer":
        if mean_pause >= config.CADENCE_PAUSE_MEAN_LONG or pause_count >= config.CADENCE_PAUSE_FREQ_HIGH:
            return "deliberate_pause_heavy"
        return "measured_balanced"
    return "melodic_rising" if wpm_sigma >= config.CADENCE_TEMPO_SIGMA_HIGH else "melodic_balanced"


def _build_coaching_directive(cadence_profile: Dict) -> str:
    profile = cadence_profile.get("profile")
    if profile == "fast_driver":
        return "Do not frame pace itself as the main problem. Focus on strategic braking, transitions, and clarity under speed."
    if profile == "measured_pacer":
        return "Do not tell the speaker to simply speed up. Focus on contrast, momentum, and removing pauses that break flow."
    return "Treat expressiveness as a strength first, then coach selectivity so key moments stand out."


def _parse_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        normalized = value.replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def _normalize_token(word: str) -> str:
    return "".join(char for char in str(word).lower() if char.isalpha() or char == "'").strip("'")
