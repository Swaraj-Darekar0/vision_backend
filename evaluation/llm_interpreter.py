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
- Keep feedback professional, encouraging, and highly actionable.
- Output must be valid JSON with this exact structure:
  {
    "overall_summary":        "<2-3 sentence session summary>",
    "progress_narrative":     "<progress since last session based on headline>",
    "timestamped_moments":    [{"time": "MM:SS", "note": "<observation>"}],
    "top_3_action_items":     ["<item>", "<item>", "<item>"],
    "motivational_closing":   "<1 encouraging sentence>"
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
