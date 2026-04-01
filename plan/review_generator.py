import logging

from groq import Groq

import config

logger = logging.getLogger(__name__)

_client = Groq(api_key=config.GROQ_API_KEY) if config.GROQ_API_KEY else None


def generate_weekly_review_narrative(review_payload: dict) -> str:
    if _client is None:
        return _fallback_narrative(review_payload)

    user_prompt = (
        f"completion_rate={review_payload['completion_rate']:.2f}, "
        f"avg_overall_score={review_payload['avg_overall_score']:.2f}, "
        f"weakest_metric={review_payload['weakest_metric']}, "
        f"strongest_metric={review_payload['strongest_metric']}, "
        f"missed_days={review_payload['missed_days']}"
    )

    try:
        response = _client.chat.completions.create(
            model=config.GROQ_MODEL,
            max_tokens=config.GROQ_WEEKLY_REVIEW_MAX_TOKENS,
            messages=[
                {"role": "system", "content": config.WEEKLY_REVIEW_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
        )
        content = (response.choices[0].message.content or "").strip()
        return content or _fallback_narrative(review_payload)
    except Exception as exc:
        logger.error(f"Weekly review narrative generation failed: {exc}")
        return _fallback_narrative(review_payload)


def _fallback_narrative(review_payload: dict) -> str:
    weakest = review_payload.get("weakest_metric", "clarity")
    strongest = review_payload.get("strongest_metric", "confidence")
    completion_rate = review_payload.get("completion_rate", 0.0)
    if review_payload.get("missed_days"):
        return (
            f"You completed {completion_rate:.0%} of your plan this week. "
            f"Your strongest area was {strongest}, while {weakest} still needs the most attention. "
            "You missed some planned days, but the next week is a clean chance to tighten consistency."
        )
    return (
        f"You completed {completion_rate:.0%} of your plan this week. "
        f"Your strongest area was {strongest}, while {weakest} remains your key focus for next week."
    )
