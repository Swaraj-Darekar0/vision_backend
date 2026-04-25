import logging
import re
from typing import Dict, List, Optional, Tuple

import numpy as np

import config

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# FIX 1 — Expanded STRONG_FILLERS with elongated variants
#
# Previous set missed every elongated vocalization that AssemblyAI transcribes
# when format_text=False is active. A speaker saying "uhhh" produces "uhh" in
# the transcript — not "uh" — so it passed through undetected.
#
# Rules for membership in STRONG_FILLERS:
#   - Never a legitimate English word in any context
#   - No pause context check required — always a disfluency signal
#   - Includes phonetic elongations that AssemblyAI preserves verbatim
# ---------------------------------------------------------------------------

STRONG_FILLERS = {
    # Core um-family
    "um",
    "umm",
    "uum",
    "uhm",
    # Core uh-family
    "uh",
    "uhh",
    # Core er/erm-family
    "er",
    "err",
    "erm",
    # Hmm-family (thinking sounds)
    "hmm",
    "hm",
    "mm",
    "mmm",
    "mhm",
    # Ah-family
    "ah",
    "ahh",
    # Miscellaneous vocalizations
    "huh",
    "eh",
}

CONTEXTUAL_SINGLE_FILLERS = {
    "like",
    "basically",
    "actually",
}

CONTEXTUAL_PHRASE_FILLERS = {
    "you know": 2,
    "i mean": 2,
    "sort of": 2,
    "kind of": 2,
}

# ---------------------------------------------------------------------------
# FIX 2 — Repetition disfluency: consecutive repeated function words
#
# AssemblyAI with format_text=False preserves consecutive word repetitions
# exactly as spoken — e.g. "I I think" or "the the point". These are strong
# disfluency signals that the original code discarded entirely.
#
# Only function words are checked because content word repetition ("the best
# best approach") is occasionally intentional emphasis. Function word
# repetition ("I I", "the the", "and and") is almost never intentional.
#
# Repetitions are tracked separately in filler_words_used under the key
# "<word> <word>" (e.g. "i i") so they are distinguishable from standalone
# filler counts in the output. They are added to filler_count so that
# filler_ratio reflects all disfluency signals in a single metric.
# ---------------------------------------------------------------------------

REPETITION_FUNCTION_WORDS = {
    "i", "we", "you", "he", "she", "they", "it",
    "the", "a", "an",
    "and", "but", "or", "so",
    "in", "on", "at", "to", "of", "for", "with",
    "this", "that", "these", "those",
    "is", "was", "are", "were",
}


def _detect_repetitions(
    words: List[Dict],
    normalized_words: List[str],
) -> Tuple[int, Dict[str, int]]:
    """
    Detects consecutive repeated function words as disfluency signals.

    Iterates through normalized tokens and flags any adjacent pair where both
    tokens are identical and the token is a known function word.  Each such
    pair counts as one repetition event.  The loop advances by 2 after a hit
    so that triple repetitions ("I I I") are counted as one event rather than
    two overlapping pairs.

    Args:
        words:            Raw word dicts from the transcript (used for bounds
                          checking only — repetition needs no pause context).
        normalized_words: Lower-cased, punctuation-stripped tokens parallel to
                          the words list.

    Returns:
        Tuple of (repetition_count, repetition_breakdown_dict).
        breakdown keys are formatted as "<word> <word>" (e.g. "i i").
    """
    repetition_count = 0
    repetition_breakdown: Dict[str, int] = {}

    i = 0
    while i < len(normalized_words) - 1:
        current = normalized_words[i]
        nxt = normalized_words[i + 1]

        if current and current == nxt and current in REPETITION_FUNCTION_WORDS:
            key = f"{current} {current}"
            repetition_count += 1
            repetition_breakdown[key] = repetition_breakdown.get(key, 0) + 1
            logger.debug(
                "Repetition disfluency detected: '%s' at word index %d", key, i
            )
            # Advance past both tokens so a triple ("I I I") counts once
            i += 2
            continue

        i += 1

    return repetition_count, repetition_breakdown


# ---------------------------------------------------------------------------
# FIX 3 — Speaker-relative pause threshold
#
# The original _has_pause_context() used a fixed FILLER_PAUSE_CONTEXT threshold
# (0.3 s) applied identically to every speaker.  This produces two failure
# modes:
#
#   Fast speaker  — natural inter-word gap ~0.10 s.  A genuine filler pause of
#                   0.25 s is well above their norm but below 0.3 s, so the
#                   contextual filler is missed entirely.
#
#   Slow speaker  — natural inter-word gap ~0.35 s.  Their normal speech
#                   already exceeds 0.3 s everywhere, so content words with
#                   natural gaps are incorrectly flagged as fillers.
#
# The fix computes the speaker's own median inter-word gap once per session,
# then treats a pause as "filler-like" only when it is FILLER_PAUSE_MULTIPLIER
# times above that personal median.  The multiplier lives in config.py so it
# can be tuned without touching this file.
#
# FILLER_PAUSE_CONTEXT (the fixed 0.3 s constant) is kept as a fallback for
# sessions with fewer than MIN_WORDS_FOR_BASELINE words — not enough data to
# compute a reliable median.
#
# New constant required in config.py:
#   FILLER_PAUSE_MULTIPLIER = 1.8
#   FILLER_BASELINE_MIN_WORDS = 10
# ---------------------------------------------------------------------------

# Gaps beyond this value are treated as sentence boundaries, not inter-word
# gaps, and are excluded from the baseline median calculation.
_SENTENCE_BOUNDARY_GAP_SECONDS = 2.0


def _compute_speaker_pause_baseline(words: List[Dict]) -> Optional[float]:
    """
    Computes the median inter-word gap for this speaker/session.

    Gaps at sentence boundaries (> _SENTENCE_BOUNDARY_GAP_SECONDS) are
    excluded because they represent deliberate pauses between thoughts, not
    the speaker's natural inter-word rhythm.

    Returns:
        Median gap in seconds, or None if there are too few words to compute
        a reliable baseline (fewer than FILLER_BASELINE_MIN_WORDS words).
    """
    if len(words) < config.FILLER_BASELINE_MIN_WORDS:
        logger.debug(
            "Too few words (%d) to compute speaker pause baseline — "
            "falling back to fixed threshold %.2f s",
            len(words),
            config.FILLER_PAUSE_CONTEXT,
        )
        return None

    gaps: List[float] = []
    for i in range(len(words) - 1):
        try:
            gap = float(words[i + 1]["start"]) - float(words[i]["end"])
        except (KeyError, ValueError, TypeError):
            continue

        # Only include intra-sentence gaps
        if 0.0 < gap < _SENTENCE_BOUNDARY_GAP_SECONDS:
            gaps.append(gap)

    if not gaps:
        return None

    baseline = float(np.median(gaps))
    logger.debug(
        "Speaker pause baseline computed: median=%.3f s over %d inter-word gaps",
        baseline,
        len(gaps),
    )
    return baseline


def _has_pause_context_relative(
    words: List[Dict],
    start_index: int,
    end_index: int,
    baseline_gap: Optional[float],
) -> bool:
    """
    Speaker-relative pause context check.

    Replaces the original _has_pause_context() function.  A pause qualifies
    as "filler-like" when it exceeds the speaker's own median inter-word gap
    multiplied by FILLER_PAUSE_MULTIPLIER.

    When baseline_gap is None (session too short for a reliable baseline),
    falls back to the original fixed FILLER_PAUSE_CONTEXT threshold so
    behaviour degrades gracefully rather than failing.

    Args:
        words:       Raw word dicts from the transcript.
        start_index: Index of the first word of the candidate filler token.
        end_index:   Index of the last word of the candidate filler token
                     (same as start_index for single-word candidates).
        baseline_gap: Median inter-word gap for this speaker in seconds, or
                      None to trigger fixed-threshold fallback.

    Returns:
        True if there is a filler-indicative pause before or after the token.
    """
    if baseline_gap is not None:
        threshold = baseline_gap * config.FILLER_PAUSE_MULTIPLIER
    else:
        # Graceful fallback — original fixed threshold
        threshold = config.FILLER_PAUSE_CONTEXT

    pause_before = 0.0
    if start_index > 0:
        try:
            pause_before = (
                float(words[start_index]["start"])
                - float(words[start_index - 1]["end"])
            )
        except (KeyError, ValueError, TypeError):
            pass

    pause_after = 0.0
    if end_index < len(words) - 1:
        try:
            pause_after = (
                float(words[end_index + 1]["start"])
                - float(words[end_index]["end"])
            )
        except (KeyError, ValueError, TypeError):
            pass

    return pause_before > threshold or pause_after > threshold


def detect_fillers(transcript_data: Dict) -> Dict:
    """
    Identify filler words, phrases, and repetition disfluencies from
    transcript word timings.

    Detection strategy by category:

        Strong fillers (um, uh, hmm, elongated variants):
            Counted unconditionally — never legitimate speech sounds.

        Repetition disfluencies (I I, the the, and and …):
            Counted unconditionally when consecutive identical function words
            are found.  AssemblyAI preserves these with format_text=False.

        Contextual phrase fillers (you know, i mean, sort of, kind of):
            Counted only when a pause exceeding the speaker's relative
            threshold is detected immediately before or after the phrase.

        Contextual single-word fillers (like, basically, actually):
            Counted only when a pause exceeding the speaker's relative
            threshold is detected immediately before or after the word.

    The pause threshold adapts to each speaker's natural rhythm rather than
    applying a fixed 0.3 s cutoff to everyone.

    Output contract — identical to original, no downstream changes required:
        {
            "filler_count":             int,
            "filler_ratio":             float,   # filler_count / total_words
            "filler_ratio_normalized":  float,   # clamped to [0, 1]
            "filler_words_used":        Dict[str, int],
        }
    """
    words = transcript_data.get("words", [])
    total_words = len(words)

    if total_words == 0:
        return {
            "filler_count": 0,
            "filler_ratio": 0.0,
            "filler_ratio_normalized": 0.0,
            "filler_words_used": {},
        }

    # FIX 3 — compute speaker-relative pause baseline once for the session
    baseline_gap = _compute_speaker_pause_baseline(words)

    filler_count, filler_words_used = _count_fillers(words, baseline_gap)

    filler_ratio = filler_count / total_words
    filler_ratio_normalized = float(
        np.clip(filler_ratio / config.FILLER_RATIO_CEILING, 0.0, 1.0)
    )

    output = {
        "filler_count": filler_count,
        "filler_ratio": float(filler_ratio),
        "filler_ratio_normalized": filler_ratio_normalized,
        "filler_words_used": filler_words_used,
    }

    logger.info(
        "Filler detection complete: %d fillers in %d words "
        "(ratio=%.3f, baseline_gap=%s s) — breakdown: %s",
        filler_count,
        total_words,
        filler_ratio,
        f"{baseline_gap:.3f}" if baseline_gap is not None else "fallback",
        filler_words_used,
    )
    return output


def count_fillers_in_words(words: List[Dict]) -> Tuple[int, Dict[str, int]]:
    """
    Shared helper for session-level and window-level filler counting.

    Window-level calls pass a subset of the full word list so the baseline
    computed here reflects only the words in that window.  For windows shorter
    than FILLER_BASELINE_MIN_WORDS the fixed threshold fallback activates
    automatically.
    """
    baseline_gap = _compute_speaker_pause_baseline(words)
    return _count_fillers(words, baseline_gap)


def _count_fillers(
    words: List[Dict],
    baseline_gap: Optional[float],
) -> Tuple[int, Dict[str, int]]:
    """
    Core filler counting loop.

    Processes words in a single left-to-right pass.  Priority order within
    the loop:

        1. Phrase filler match  — consume multiple tokens, skip ahead
        2. Strong filler match  — unconditional count, advance by 1
        3. Repetition check     — handled separately before the main loop
        4. Contextual single    — pause-gated, advance by 1

    Repetition disfluencies are detected in a dedicated pre-pass
    (_detect_repetitions) rather than inside this loop because they require
    looking at adjacent token pairs without interfering with the phrase-match
    index advancement logic.

    Args:
        words:        Raw word dicts from the transcript.
        baseline_gap: Speaker median inter-word gap, or None for fallback.

    Returns:
        Tuple of (total_filler_count, filler_breakdown_dict).
    """
    normalized_words = [_normalize_word_item(w) for w in words]
    filler_count = 0
    filler_words_used: Dict[str, int] = {}

    # FIX 2 — repetition disfluency pre-pass
    rep_count, rep_breakdown = _detect_repetitions(words, normalized_words)
    if rep_count > 0:
        filler_count += rep_count
        for key, val in rep_breakdown.items():
            filler_words_used[key] = filler_words_used.get(key, 0) + val

    # Main left-to-right filler scan
    i = 0
    while i < len(words):
        token = normalized_words[i]
        if not token:
            i += 1
            continue

        # Priority 1 — phrase filler (consumes multiple tokens)
        phrase_match = _match_phrase(normalized_words, i)
        if phrase_match:
            phrase, phrase_length = phrase_match
            # FIX 3 — use speaker-relative threshold
            if _has_pause_context_relative(
                words, i, i + phrase_length - 1, baseline_gap
            ):
                filler_count += 1
                filler_words_used[phrase] = filler_words_used.get(phrase, 0) + 1
                i += phrase_length
                continue

        # Priority 2 — strong filler (unconditional, no pause check needed)
        if token in STRONG_FILLERS:
            filler_count += 1
            filler_words_used[token] = filler_words_used.get(token, 0) + 1
            i += 1
            continue

        # Priority 3 — contextual single-word filler (pause-gated)
        # FIX 3 — use speaker-relative threshold
        if token in CONTEXTUAL_SINGLE_FILLERS and _has_pause_context_relative(
            words, i, i, baseline_gap
        ):
            filler_count += 1
            filler_words_used[token] = filler_words_used.get(token, 0) + 1

        i += 1

    return filler_count, filler_words_used


def _match_phrase(tokens: List[str], start_index: int) -> Optional[Tuple[str, int]]:
    """
    Attempts to match a contextual phrase filler starting at start_index.

    Returns a (phrase_string, phrase_length_in_tokens) tuple on match,
    or None if no phrase filler starts at this position.
    """
    for phrase, phrase_length in CONTEXTUAL_PHRASE_FILLERS.items():
        end = start_index + phrase_length
        if end > len(tokens):
            continue
        candidate = " ".join(tokens[start_index:end])
        if candidate == phrase:
            return phrase, phrase_length
    return None


def _normalize_word_item(word_item: Dict) -> str:
    """
    Lowercases a word and strips all characters except ASCII letters and
    apostrophes.  Leading/trailing apostrophes are also removed.

    Unchanged from original — downstream logic depends on this exact
    normalisation contract.
    """
    raw_word = str(word_item.get("word", "")).lower()
    normalized = re.sub(r"[^a-z']+", "", raw_word)
    return normalized.strip("'")