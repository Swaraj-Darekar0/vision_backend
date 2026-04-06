import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from audio.filler_detector import detect_fillers


TEST_TRANSCRIPT = (
    "So to talk about the discovery science that fascinates me the most, let's start by talking about the discovery of the exoplanet that is discovered by the scientists. Which is an exoplanet basically means the planet which is not in your solar system, but orbits the star itself that our solar system orbits. So the sun, basically. Then why this exoplanet? Because it is discovered is the greatest, is one of the greatest milestone because it's one of the most youngest planet that is currently there, which scientists have discovered and it's only one point five million years old. Then another discovery is the increase in the lifespan of a mouse by twenty percent. Labs in Australia have patented a technology by which they have successfully increased the lifespan of a mouse by almost twenty percent. And the human trials are basically next. So this is the step in which humans are being evolved, Human life expectancy is being evolved. So yeah, that's a great discovery for me basically and it fascinates me. Another one is the manipulation of the source code in our dnas to fight multiple diseases which we were not able to fight until now because of the DNA imbalances that we faced. And now we have figured out a way to like this module or modify this source code. So it's. It can also be considered as one of these discoveries. The third one that we can talk about is the human human neurons placed on a silicon shell to create a processor chip that thinks and processes like human and does not consume as much as much electricity as a normal processor would. So it's an advancement in technical and biological."    )

WORD_PATTERN = re.compile(r"\.{3}|[A-Za-z0-9']+[,.?!]?")
LONG_PAUSE_TOKENS = {",", ".", "?", "!", "..."}


def build_mock_transcript(full_text: str) -> dict:
    words = []
    current_time = 0.0

    for token in WORD_PATTERN.findall(full_text.replace("—", " ")):
        clean_word = token.strip()
        start = current_time
        duration = _duration_for_token(clean_word)
        end = start + duration
        words.append({
            "word": clean_word.lower(),
            "start": round(start, 3),
            "end": round(end, 3),
        })
        current_time = end + _pause_after_token(clean_word)

    return {
        "full_text": full_text,
        "words": words,
        "segments": [{"start": 0.0, "end": words[-1]["end"] if words else 0.0, "text": full_text}],
        "total_words": len(words),
    }


def _duration_for_token(token: str) -> float:
    stripped = token.strip(",.?!")
    if stripped.isdigit():
        return 0.18
    return max(0.12, min(0.34, len(stripped) * 0.03))


def _pause_after_token(token: str) -> float:
    if token.endswith(("?", "!")):
        return 0.42
    if token.endswith((".", "...")):
        return 0.4
    if token.endswith(","):
        return 0.34
    return 0.08


if __name__ == "__main__":
    transcript_data = build_mock_transcript(TEST_TRANSCRIPT)
    filler_result = detect_fillers(transcript_data)

    print("Transcript word count:", transcript_data["total_words"])
    print(json.dumps(filler_result, indent=2))
