import json
import logging
from typing import Dict, Optional
from groq import Groq
import config


logger = logging.getLogger(__name__)

# Initialize Groq client
_client: Optional[Groq] = None
if config.GROQ_API_KEY:
    try:
        _client = Groq(api_key=config.GROQ_API_KEY)
        logger.info("Groq client initialized successfully.")
    except Exception as e:
        logger.error(f"Failed to initialize Groq client: {e}")
else:
    logger.warning("GROQ_API_KEY missing in config.")

SYSTEM_PROMPT = """
You are a public speaking coach. You receive a pre-computed evaluation JSON.
Your job: interpret the provided evaluation JSON, judge topical relevance and reasoning clarity from the transcript, and generate coaching feedback.

HARD RULES:
- reasoning_clarity_score and topic_relevance_score must be based only on session_metadata.topic_title and transcript.full_text.
- reasoning_clarity_score must be a float from 0.0 to 1.0.
- topic_relevance_score must be a float from 0.0 to 1.0.
- Do NOT compute, recalculate, or modify any provided numeric value other than producing reasoning_clarity_score and topic_relevance_score.
- Do NOT fetch or reference external data.
- Do NOT reclassify deltas — classifications are already in the JSON.
- Use transcript, timestamp_events, raw_metrics_snapshot, and provided overall_scores/progress_comparison before writing feedback.
- If cadence_context is present, use it as a binding interpretation layer for pace, pauses, fillers, and timestamped moments.
- For fast-paced profiles, do not give generic advice like "slow down"; focus on where pacing stopped helping clarity.
- For grounded profiles, do not give generic advice like "speed up"; focus on where pauses or fillers broke momentum.
- For expressive profiles, do not flatten their style; focus on controlling variation so the most important moments stand out.
- For timestamped_moments, only use moments that are supported by the provided timestamp_events list.
- Each timestamped moment must be grounded in the actual event windows and explained using the transcript and raw metrics.
- You can combine nearby or duplicate timestamp events into one cleaner, more logical timestamped moment when they clearly describe the same speaking issue.
- Combine consecutive meaningful moments that occur immediately one after another into a single larger moment when they describe the same issue.
- If multiple raw events share the same start/end segment, combine them into one timestamped_moment.
- You are not required to keep the final timestamped_moment locked to a single 5-second detector window.
- You may choose a slightly broader start/end range if that creates a more logical moment, but it must stay faithful to the surrounding detected event region.
- Never invent a new time range, event type, or problem that is not supported by the input JSON.
- Convert the final chosen moment into start/end in MM:SS format.
- Focus on interpreting the meaning of the scores and classifications to generate insights.
- Keep feedback professional, encouraging, and highly actionable.
- topical_relevance_analysis must explicitly assess both topic relevance and reasoning clarity.
- The note inside timestamped_moments must use very simple everyday vocabulary and clearly say what went wrong or what went well in that moment.
- Keep each timestamp note short, concrete, and human. Avoid jargon like "variance", "instability", "engagement metric", or "prosody".
- If the moment is negative, say the actual issue plainly, for example: "You paused too long here and the flow broke."
- If the moment is positive, say what worked plainly, for example: "This part sounded clear and steady."
- When cadence_context is present, explain whether the moment shows the speaker's natural style, an overextension of that style, or a true breakdown.
- Prefer the most meaningful timestamped moments. If there are no useful timestamp events, return an empty list.
- motivational closing include a call to action like "review thisyoutuber's this video on this topic(YOU AS A COACH SUGGEST THE BEST TOPIC ON WHICH HE CAN WHTCH VIDEOS SO HE PINPOINT AND WHICH FACTORS TO IMPROVE BY WATCHING THIS VIDEOS)" or "focus on one item at a time for best results"
- Output must be valid JSON with this exact structure:
    {
    "reasoning_clarity_score": 0.0,
    "topic_relevance_score": 0.0,
    "overall_summary":        "<2-3 sentence session summary>",
    "one_line_headline_mistakes":       "<1 concise headline capturing key insight,mistakes in simple words,be direct good or bad doesn't matter chose your vocabulary wisely>",
    "topical_relevance_analysis":      "<A specific 1-2 sentence assessment of how well the speaker stayed on the topic provided in session_metadata.topic_title and the logical flow of their ideas.>",
    "progress_narrative":     "<progress since last session based on headline>",
    "timestamped_moments":    [{"event": "<event name or a short joined label for the grouped issue>", "start": "MM:SS", "end": "MM:SS", "note": "<simple explanation of what happened in that moment and why it was chosen, based on transcript + event + raw metrics>"}],
    "top_3_action_items":     ["<item>", "<item>", "<item>"],
    "motivational_closing":   "<Youtube video recommendation with specific topic to watch for improvement>",
  }

TIMESTAMPED_MOMENTS RULES:
- "event" must use only event names from timestamp_events.
- If multiple raw events describe the same issue, you may combine them into one timestamped_moment and use a short joined event label.
- If meaningful moments happen in directly adjacent windows, merge them into one larger timestamped_moment when they reflect the same issue.
- "start" and "end" should be a logical range chosen from the detected event area, not necessarily one raw detector window.
- "note" must explain the speaker behavior, not just rename the event.
- The note must clearly explain why this moment was selected.
- Build the note by checking what the transcript content sounds like in that range and what the raw metrics suggest.
- Good notes:
  - "You rushed here, so the line feels hard to follow."
  - "This stretch sounds flat, so the message loses energy."
  - "You paused too much here, and the idea broke in the middle."
  - "This section was picked because you kept stopping and restarting the idea."
- Bad notes:
  - "High fumble spike detected."
  - "Your engagement metric was low."
  - "There is a timestamp event at 00:15."
"""

def interpret_with_llm(evaluation_json: Dict) -> Dict:
    """
    Groq API  — read-only JSON → coaching text.
    Source: backend_SKILL.md Section 6 (evaluation/llm_interpreter.py).
    """
    if _client is None:
        logger.error("Groq client not initialized. Returning fallback feedback.")
        return _get_fallback_feedback()

    try:
        response = _client.chat.completions.create(
            model=config.GROQ_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": json.dumps(evaluation_json, ensure_ascii=False)}
            ],
            response_format={"type": "json_object"}
        )
        
        raw_content = response.choices[0].message.content
        return _postprocess_feedback(json.loads(raw_content))

    except Exception as e:
        logger.error(f"Groq API call failed: {e}")
        return _get_fallback_feedback()

def _get_fallback_feedback() -> Dict:
    """Returns a safe fallback structure if LLM fails."""
    return {
        "reasoning_clarity_score": 0.5,
        "topic_relevance_score": 0.5,
        "overall_summary": "Evaluation complete. Detailed coaching feedback is currently unavailable.",
        "one_line_headline_mistakes": "Detailed mistake summary is unavailable right now.",
        "topical_relevance_analysis": "Topic relevance analysis is currently unavailable.",
        "progress_narrative": "Please refer to the raw score deltas for progress tracking.",
        "timestamped_moments": [],
        "top_3_action_items": ["Review your posture metrics", "Check your speech rate", "Maintain practice consistency"],
        "motivational_closing": "Keep practicing to see more improvements!",
        "suggest_next_presentation_topics": "Daily speaking practice",
        "llm_available": False
    }


def _postprocess_feedback(feedback: Dict) -> Dict:
    try:
        reasoning_score = float(feedback.get("reasoning_clarity_score", 0.5))
    except (TypeError, ValueError):
        reasoning_score = 0.5
    feedback["reasoning_clarity_score"] = max(0.0, min(1.0, reasoning_score))

    try:
        topic_relevance_score = float(feedback.get("topic_relevance_score", 0.5))
    except (TypeError, ValueError):
        topic_relevance_score = 0.5
    feedback["topic_relevance_score"] = max(0.0, min(1.0, topic_relevance_score))

    moments = feedback.get("timestamped_moments")
    if not isinstance(moments, list):
        return feedback

    merged_moments = {}
    for moment in moments:
        if not isinstance(moment, dict):
            continue

        start = str(moment.get("start", "")).strip()
        end = str(moment.get("end", "")).strip()
        if not start or not end:
            continue

        key = (start, end)
        event_value = str(moment.get("event", "")).strip()
        note_value = str(moment.get("note", "")).strip()

        bucket = merged_moments.setdefault(key, {"events": [], "notes": []})
        for event_name in [part.strip() for part in event_value.split("+") if part.strip()]:
            if event_name not in bucket["events"]:
                bucket["events"].append(event_name)
        if note_value and note_value not in bucket["notes"]:
            bucket["notes"].append(note_value)

    normalized_moments = []
    for (start, end), bucket in merged_moments.items():
        normalized_moments.append({
            "event": " + ".join(bucket["events"]),
            "start": start,
            "end": end,
            "note": " ".join(bucket["notes"][:2]).strip(),
        })

    feedback["timestamped_moments"] = normalized_moments
    return feedback
