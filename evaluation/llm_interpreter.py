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
Your ONLY job: interpret the provided scores and generate coaching feedback.

HARD RULES:
- Do NOT compute, recalculate, or modify any numeric value.
- Do NOT fetch or reference external data.
- Do NOT reclassify deltas — classifications are already in the JSON.
- Reference timestamp events by exact times from timestamp_events list.
- Focus on interpreting the meaning of the scores and classifications to generate insights.
- Keep feedback professional, encouraging, and highly actionable.
- motivational closing include a call to action like "review thisyoutuber's this video on this topic(YOU AS A COACH SUGGEST THE BEST TOPIC ON WHICH HE CAN WHTCH VIDEOS SO HE PINPOINT AND WHICH FACTORS TO IMPROVE BY WATCHING THIS VIDEOS)" or "focus on one item at a time for best results"
- Output must be valid JSON with this exact structure:
  {
    "overall_summary":        "<2-3 sentence session summary>",
    "one_line_headline_mistakes":       "<1 concise headline capturing key insight,mistakes in simple words,be direct good or bad doesn't matter chose your vocabulary wisely>",
    "progress_narrative":     "<progress since last session based on headline>",
    "timestamped_moments":    [{"time": "MM:SS", "note": "<observation(interpret it in simple words, be direct good or bad doesn't matter chose your vocabulary wisely)>"}],
    "top_3_action_items":     ["<item>", "<item>", "<item>"],
    "motivational_closing":   "<Youtube video recommendation with specific topic to watch for improvement>",
    "suggest_next_presentation_topics":  "<Suggest 1 specific presentation topic (max 6 words) for the next session, based on the evaluation. Choose difficulty level appropriate to avoid frustration or boredom.>"
  }
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
        return json.loads(raw_content)

    except Exception as e:
        logger.error(f"Groq API call failed: {e}")
        return _get_fallback_feedback()

def _get_fallback_feedback() -> Dict:
    """Returns a safe fallback structure if LLM fails."""
    return {
        "overall_summary": "Evaluation complete. Detailed coaching feedback is currently unavailable.",
        "progress_narrative": "Please refer to the raw score deltas for progress tracking.",
        "timestamped_moments": [],
        "top_3_action_items": ["Review your posture metrics", "Check your speech rate", "Maintain practice consistency"],
        "motivational_closing": "Keep practicing to see more improvements!",
        "llm_available": False
    }
