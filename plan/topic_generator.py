import json
import logging
from typing import Any

from groq import Groq

import config

logger = logging.getLogger(__name__)

_client = Groq(api_key=config.GROQ_API_KEY) if config.GROQ_API_KEY else None


class TopicGenerationError(Exception):
    pass


class TopicValidationError(Exception):
    pass


def generate_plan_topics(payload: dict) -> dict:
    if _client is None:
        raise TopicGenerationError("Groq client is not configured on the backend")

    logger.info("Groq plan generation starting")
    prompt_payload = {
        "user_profile": payload["user_profile"],
        "plan_context": payload["plan_context"],
        "previously_used_topics": payload.get("previously_used_topics", []),
        "output_schema": {
            "topics": [
                {
                    "day": 1,
                    "session": 1,
                    "tier": "tier_1",
                    "topic_title": "Complete, speakable prompt text",
                    "target_skill": "confidence",
                    "duration_minutes": 2,
                    "resources": {
                        "hint": "Short actionable hint",
                        "research_prompt": "Optional short learning suggestion or null",
                        "youtube_search": "Optional search query or null",
                    },
                }
            ]
        },
    }

    try:
        response = _client.chat.completions.create(
            model=config.GROQ_TOPIC_MODEL,
            max_tokens=config.GROQ_TOPIC_MAX_TOKENS,
            timeout=config.GROQ_REQUEST_TIMEOUT_SECONDS,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": config.PLAN_TOPIC_SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(prompt_payload, ensure_ascii=False)},
            ],
        )
        logger.info("Groq plan generation completed")
    except Exception as exc:
        logger.error(f"Groq plan generation failed: {exc}")
        raise TopicGenerationError("Groq topic generation failed") from exc

    raw_content = (response.choices[0].message.content or "").strip()
    return _parse_and_normalize_topics(raw_content, payload.get("previously_used_topics", []))


def _parse_and_normalize_topics(raw_content: str, previously_used_topics: list[str]) -> dict:
    cleaned = raw_content.replace("```json", "").replace("```", "").strip()

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        logger.error(f"Plan topic JSON parsing failed: {exc}")
        raise TopicValidationError("Groq returned malformed JSON") from exc

    if isinstance(parsed, dict):
        topics = parsed.get("topics")
    elif isinstance(parsed, list):
        logger.warning("Groq returned a top-level topics array instead of an object; accepting and normalizing it.")
        topics = parsed
    else:
        logger.error(f"Plan topic validation failed: unexpected top-level JSON type {type(parsed).__name__}")
        raise TopicValidationError("Groq response must be a JSON object or array of topics")

    if not isinstance(topics, list) or not topics:
        logger.error("Plan topic validation failed: missing topics array")
        raise TopicValidationError("Groq response must contain a non-empty topics array")

    seen_titles = {title.strip().lower() for title in previously_used_topics if isinstance(title, str)}
    normalized_topics = [_normalize_topic(topic, seen_titles) for topic in topics]
    return {"topics": normalized_topics}


def _normalize_topic(topic: Any, seen_titles: set[str]) -> dict:
    if not isinstance(topic, dict):
        logger.error("Plan topic validation failed: topic item is not an object")
        raise TopicValidationError("Each topic must be an object")

    required_fields = ["day", "session", "tier", "topic_title", "target_skill", "duration_minutes", "resources"]
    missing = [field for field in required_fields if topic.get(field) is None]
    if missing:
        logger.error(f"Plan topic validation failed: missing fields {missing}")
        raise TopicValidationError(f"Topic missing required fields: {', '.join(missing)}")

    tier = str(topic["tier"]).strip()
    target_skill = str(topic["target_skill"]).strip()
    if not tier or not target_skill:
        logger.error(f"Plan topic validation failed: empty tier/target_skill in topic {topic}")
        raise TopicValidationError("tier and target_skill are required")

    topic_title = _normalize_topic_title(str(topic["topic_title"]).strip(), target_skill)
    normalized_title = topic_title.lower()
    if normalized_title in seen_titles:
        logger.error(f"Plan topic validation failed: repeated topic detected: {topic_title}")
        raise TopicValidationError("Groq returned a repeated topic")
    seen_titles.add(normalized_title)

    resources = topic["resources"]
    if not isinstance(resources, dict):
        logger.error("Plan topic validation failed: resources is not an object")
        raise TopicValidationError("resources must be an object")

    hint = str(resources.get("hint", "")).strip()
    if not hint:
        logger.error("Plan topic validation failed: missing resources.hint")
        raise TopicValidationError("resources.hint is required")

    try:
        day = int(topic["day"])
        session_num = int(topic["session"])
        duration_minutes = int(topic["duration_minutes"])
    except (TypeError, ValueError) as exc:
        logger.error(f"Plan topic validation failed: invalid numeric fields in topic {topic}")
        raise TopicValidationError("day, session, and duration_minutes must be integers") from exc

    if day < 1 or session_num < 1 or duration_minutes < 1:
        logger.error(f"Plan topic validation failed: non-positive numeric values in topic {topic}")
        raise TopicValidationError("day, session, and duration_minutes must be positive integers")

    if duration_minutes > config.PLAN_SESSION_DURATION_MAX_MINUTES:
        logger.warning(
            "Clamped duration_minutes from %s to %s for topic '%s'",
            duration_minutes,
            config.PLAN_SESSION_DURATION_MAX_MINUTES,
            topic_title,
        )
        duration_minutes = config.PLAN_SESSION_DURATION_MAX_MINUTES

    return {
        "day": day,
        "session": session_num,
        "tier": tier,
        "topic_title": topic_title,
        "target_skill": target_skill,
        "duration_minutes": duration_minutes,
        "completed": False,
        "completed_at": None,
        "session_id": None,
        "resources": {
            "hint": hint,
            "research_prompt": _normalize_nullable_text(resources.get("research_prompt")),
            "youtube_search": _normalize_nullable_text(resources.get("youtube_search")),
        },
    }


def _normalize_nullable_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_topic_title(topic_title: str, target_skill: str) -> str:
    if not topic_title:
        logger.error("Plan topic validation failed: empty topic_title")
        raise TopicValidationError("topic_title is required")

    if len(topic_title.split()) >= config.PLAN_TOPIC_MIN_WORDS:
        return topic_title

    repaired = _label_to_prompt(topic_title, target_skill)
    logger.warning(f"Repaired short topic_title into speakable prompt: '{topic_title}' -> '{repaired}'")
    return repaired


def _label_to_prompt(label: str, target_skill: str) -> str:
    clean_label = label.strip().rstrip(".")
    skill_clause = _skill_clause(target_skill)
    return f"Speak about {clean_label} and share your perspective with one concrete example{skill_clause}."


def _skill_clause(target_skill: str) -> str:
    skill = target_skill.strip().lower()
    prompts = {
        "confidence": " so your answer sounds calm and confident",
        "clarity": " while keeping your ideas clear and easy to follow",
        "engagement": " in a way that keeps a listener interested from start to finish",
        "structure": " using a clear beginning, middle, and end",
        "authority": " with language that sounds decisive and credible",
        "pacing": " while maintaining steady pacing and control",
        "filler_words": " while avoiding unnecessary filler words",
    }
    return prompts.get(skill, "")
