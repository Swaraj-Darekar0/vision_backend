import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from audio.filler_detector import detect_fillers


# ============================================================================
# Test Case 1: Strong Fillers (um, uh, hmm, elongated variants)
# ============================================================================
STRONG_FILLER_TEXT = (
    "So um I think uh we should basically hmm review the data "
    "and err consider all the options."
)

# ============================================================================
# Test Case 2: Repetition Disfluencies (I I, the the, and and)
# ============================================================================
REPETITION_TEXT = (
    "I I think the the idea is good. We we should and and start "
    "implementing it now."
)

# ============================================================================
# Test Case 3: Contextual Phrase Fillers with Pause Context
# ============================================================================
CONTEXTUAL_PHRASE_TEXT = (
    "The first approach you know is simple. The second i mean is complex. "
    "We sort of understand it kind of."
)

# ============================================================================
# Test Case 4: Contextual Single Fillers with Pause Context
# ============================================================================
CONTEXTUAL_SINGLE_TEXT = (
    "This is like really important. We basically need to start now. "
    "The results actually show improvement."
)

# ============================================================================
# Test Case 5: Mixed Filler Types
# ============================================================================
MIXED_TEXT = (
    "So um I I think you know the approach is basically good but uh "
    "we we need to like consider the the costs and sort of prioritize."
)

# ============================================================================
# Test Case 6: Original Long Transcript
# ============================================================================
ORIGINAL_TRANSCRIPT = (
    "So to talk about the discovery science that fascinates me the most, "
    "let's start by talking about the discovery of the exoplanet that is "
    "discovered by the scientists. Which is an exoplanet basically means the "
    "planet which is not in your solar system, but orbits the star itself "
    "that our solar system orbits. So the sun, basically. Then why this "
    "exoplanet? Because it is discovered is the greatest, is one of the "
    "greatest milestone because it's one of the most youngest planet that "
    "is currently there, which scientists have discovered and it's only one "
    "point five million years old. Then another discovery is the increase "
    "in the lifespan of a mouse by twenty percent. Labs in Australia have "
    "patented a technology by which they have successfully increased the "
    "lifespan of a mouse by almost twenty percent. And the human trials are "
    "basically next. So this is the step in which humans are being evolved, "
    "Human life expectancy is being evolved. So yeah, that's a great "
    "discovery for me basically and it fascinates me. Another one is the "
    "manipulation of the source code in our dnas to fight multiple diseases "
    "which we were not able to fight until now because of the DNA imbalances "
    "that we faced. And now we have figured out a way to like this module or "
    "modify this source code. So it's. It can also be considered as one of "
    "these discoveries. The third one that we can talk about is the human "
    "human neurons placed on a silicon shell to create a processor chip that "
    "thinks and processes like human and does not consume as much as much "
    "electricity as a normal processor would. So it's an advancement in "
    "technical and biological."
)

WORD_PATTERN = re.compile(r"\.{3}|[A-Za-z0-9']+[,.?!]?")


def build_mock_transcript(full_text: str, pause_factor: float = 1.0) -> dict:
    """
    Build a mock transcript with word timing data.
    
    Args:
        full_text: The text to convert into transcript format.
        pause_factor: Multiplier for pause durations (useful for simulating
                     fast/slow speakers).
    """
    words = []
    current_time = 0.0

    for token in WORD_PATTERN.findall(full_text.replace("—", " ")):
        clean_word = token.strip()
        if not clean_word:
            continue
        start = current_time
        duration = _duration_for_token(clean_word)
        end = start + duration
        words.append({
            "word": clean_word.lower(),
            "start": round(start, 3),
            "end": round(end, 3),
        })
        current_time = end + _pause_after_token(clean_word) * pause_factor

    return {
        "full_text": full_text,
        "words": words,
        "segments": [{"start": 0.0, "end": words[-1]["end"] if words else 0.0, "text": full_text}],
        "total_words": len(words),
    }


def _duration_for_token(token: str) -> float:
    """Word duration scales with token length."""
    stripped = token.strip(",.?!")
    if stripped.isdigit():
        return 0.18
    return max(0.12, min(0.34, len(stripped) * 0.03))


def _pause_after_token(token: str) -> float:
    """Pause duration depends on punctuation context."""
    if token.endswith(("?", "!")):
        return 0.42
    if token.endswith((".", "...")):
        return 0.4
    if token.endswith(","):
        return 0.34
    return 0.08


def print_test_result(test_name: str, transcript_data: dict, result: dict) -> None:
    """Pretty-print a test result."""
    print(f"\n{'='*70}")
    print(f"TEST: {test_name}")
    print(f"{'='*70}")
    print(f"Total words: {transcript_data['total_words']}")
    print(f"Filler count: {result['filler_count']}")
    print(f"Filler ratio: {result['filler_ratio']:.4f}")
    print(f"Filler ratio (normalized): {result['filler_ratio_normalized']:.4f}")
    print(f"Fillers detected: {result['filler_words_used']}")


if __name__ == "__main__":
    print("\n" + "="*70)
    print("FILLER DETECTOR TEST SUITE")
    print("Testing new filler detection logic:")
    print("  • FIX 1: Expanded STRONG_FILLERS with elongated variants")
    print("  • FIX 2: Repetition disfluencies (I I, the the, and and)")
    print("  • FIX 3: Speaker-relative pause threshold")
    print("="*70)

    # Test 1: Strong Fillers
    transcript_1 = build_mock_transcript(STRONG_FILLER_TEXT)
    result_1 = detect_fillers(transcript_1)
    print_test_result("STRONG FILLERS (um, uh, hmm, err)", transcript_1, result_1)
    print("Expected: um, uh, hmm, err should all be detected unconditionally")

    # Test 2: Repetition Disfluencies
    transcript_2 = build_mock_transcript(REPETITION_TEXT)
    result_2 = detect_fillers(transcript_2)
    print_test_result("REPETITION DISFLUENCIES (I I, the the, we we, and and)", transcript_2, result_2)
    print("Expected: Consecutive function word repetitions detected as disfluencies")

    # Test 3: Contextual Phrase Fillers
    transcript_3 = build_mock_transcript(CONTEXTUAL_PHRASE_TEXT)
    result_3 = detect_fillers(transcript_3)
    print_test_result("CONTEXTUAL PHRASE FILLERS (you know, i mean, sort of, kind of)", transcript_3, result_3)
    print("Expected: Phrase fillers detected when pause context is present")

    # Test 4: Contextual Single Fillers
    transcript_4 = build_mock_transcript(CONTEXTUAL_SINGLE_TEXT)
    result_4 = detect_fillers(transcript_4)
    print_test_result("CONTEXTUAL SINGLE FILLERS (like, basically, actually)", transcript_4, result_4)
    print("Expected: Single-word fillers detected when pause context is present")

    # Test 5: Mixed Types
    transcript_5 = build_mock_transcript(MIXED_TEXT)
    result_5 = detect_fillers(transcript_5)
    print_test_result("MIXED FILLER TYPES (all categories combined)", transcript_5, result_5)
    print("Expected: All filler types counted together in a single metric")

    # Test 6: Original Long Transcript
    transcript_6 = build_mock_transcript(ORIGINAL_TRANSCRIPT)
    result_6 = detect_fillers(transcript_6)
    print_test_result("ORIGINAL LONG TRANSCRIPT", transcript_6, result_6)
    print("Expected: Real-world-like filler distribution")

    # Test 7: Fast Speaker (smaller pause multiplier effect)
    print(f"\n{'='*70}")
    print("TEST: FAST SPEAKER (pause_factor=0.5)")
    print(f"{'='*70}")
    print("Testing speaker-relative pause threshold adaptation")
    transcript_7 = build_mock_transcript(CONTEXTUAL_PHRASE_TEXT, pause_factor=0.5)
    result_7 = detect_fillers(transcript_7)
    print_test_result("FAST SPEAKER with Contextual Fillers", transcript_7, result_7)
    print("Expected: Contextual fillers detected based on speaker's own median pause")

    # Test 8: Slow Speaker (larger pauses naturally)
    print(f"\n{'='*70}")
    print("TEST: SLOW SPEAKER (pause_factor=2.0)")
    print(f"{'='*70}")
    print("Testing that normal words aren't flagged as fillers due to long pauses")
    transcript_8 = build_mock_transcript("The approach is valid. We should proceed.", pause_factor=2.0)
    result_8 = detect_fillers(transcript_8)
    print_test_result("SLOW SPEAKER with Normal Content", transcript_8, result_8)
    print("Expected: Normal words NOT flagged as fillers despite long inter-word gaps")

    # Summary
    print(f"\n{'='*70}")
    print("SUMMARY OF ALL TESTS")
    print(f"{'='*70}")
    test_results = [
        ("Strong Fillers", result_1),
        ("Repetition Disfluencies", result_2),
        ("Contextual Phrases", result_3),
        ("Contextual Singles", result_4),
        ("Mixed Types", result_5),
        ("Original Transcript", result_6),
        ("Fast Speaker", result_7),
        ("Slow Speaker", result_8),
    ]
    
    for test_name, result in test_results:
        filler_ratio_pct = result['filler_ratio'] * 100
        print(f"{test_name:.<30} {result['filler_count']:3d} fillers "
              f"({filler_ratio_pct:5.2f}% ratio, normalized: {result['filler_ratio_normalized']:.2f})")
