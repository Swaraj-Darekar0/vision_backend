import logging
import re
from typing import Dict, List, Tuple

import numpy as np

import config

logger = logging.getLogger(__name__)

STRONG_FILLERS = {
    "um",
    "uh",
    "erm",
    "er",
    "hmm",
    "ah",
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


def detect_fillers(transcript_data: Dict) -> Dict:
    """
    Identify filler words and phrases from transcript word timings.

    Strong fillers such as "uh" and "um" are counted directly, while more
    lexical terms such as "like" or "you know" still require pause context so
    we do not overcount normal language usage.
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

    filler_count, filler_words_used = _count_fillers(words)
    filler_ratio = filler_count / total_words
    filler_ratio_normalized = float(np.clip(filler_ratio / config.FILLER_RATIO_CEILING, 0.0, 1.0))

    output = {
        "filler_count": filler_count,
        "filler_ratio": float(filler_ratio),
        "filler_ratio_normalized": filler_ratio_normalized,
        "filler_words_used": filler_words_used,
    }

    logger.info("Filler detection complete: %s fillers found (%s)", filler_count, filler_words_used)
    return output


def count_fillers_in_words(words: List[Dict]) -> Tuple[int, Dict[str, int]]:
    """
    Shared helper for session-level and window-level filler counting.
    """
    return _count_fillers(words)


def _count_fillers(words: List[Dict]) -> Tuple[int, Dict[str, int]]:
    normalized_words = [_normalize_word_item(word_item) for word_item in words]
    filler_count = 0
    filler_words_used: Dict[str, int] = {}

    i = 0
    while i < len(words):
        token = normalized_words[i]
        if not token:
            i += 1
            continue

        phrase_match = _match_phrase(normalized_words, i)
        if phrase_match:
            phrase, phrase_length = phrase_match
            if _has_pause_context(words, i, i + phrase_length - 1):
                filler_count += 1
                filler_words_used[phrase] = filler_words_used.get(phrase, 0) + 1
                i += phrase_length
                continue

        if token in STRONG_FILLERS:
            filler_count += 1
            filler_words_used[token] = filler_words_used.get(token, 0) + 1
            i += 1
            continue

        if token in CONTEXTUAL_SINGLE_FILLERS and _has_pause_context(words, i, i):
            filler_count += 1
            filler_words_used[token] = filler_words_used.get(token, 0) + 1

        i += 1

    return filler_count, filler_words_used


def _match_phrase(tokens: List[str], start_index: int) -> Tuple[str, int] | None:
    for phrase, phrase_length in CONTEXTUAL_PHRASE_FILLERS.items():
        candidate = " ".join(tokens[start_index:start_index + phrase_length])
        if candidate == phrase:
            return phrase, phrase_length
    return None


def _has_pause_context(words: List[Dict], start_index: int, end_index: int) -> bool:
    pause_before = 0.0
    if start_index > 0:
        pause_before = float(words[start_index]["start"]) - float(words[start_index - 1]["end"])

    pause_after = 0.0
    if end_index < len(words) - 1:
        pause_after = float(words[end_index + 1]["start"]) - float(words[end_index]["end"])

    return pause_before > config.FILLER_PAUSE_CONTEXT or pause_after > config.FILLER_PAUSE_CONTEXT


def _normalize_word_item(word_item: Dict) -> str:
    raw_word = str(word_item.get("word", "")).lower()
    normalized = re.sub(r"[^a-z']+", "", raw_word)
    return normalized.strip("'")
