import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from audio.filler_detector import detect_fillers


TEST_TRANSCRIPT = (
    "Okay, take, take this thing into consideration. How to create a working environment where everyone seems to have a pretty good time. And also the productivity rate also increases. So the world. So the thing that great world leaders do is one of the ways is that the culture would be what they seems to be. Fine. So the thing is, if somebody loves you in a way, they tend to work pretty extra for you. Like if somebody hates you, they would already hate the job they would do for you. Right? So it's a simple thing. And making this culture really fit is the responsibility of a leader. So while hiring the people, we must ensure that the people we are hiring, our culture fit and they are perfectly fitted into the organization. And then we must take actions like increasing their social competence level by increasing engaging them in the activities. Like when people enter in the meeting rooms, they should keep their phones outside. Like when the meeting start. People should not be waiting for the meeting to start by holding their phones in their hands. And when does the meeting start? Oh, the meeting has started. They should not be like that. They should be like engaged and respectful. Like a company should have a core values policy where the values like respect, integrity, communication and hindering to each other. And also to have fun and."
    )

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
