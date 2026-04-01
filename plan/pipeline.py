from collections import defaultdict
import logging

from plan.db_handler import (
    create_weekly_plan,
    current_timestamp_iso,
    deactivate_current_plans,
    fetch_current_plan,
    fetch_personal_bests,
    fetch_sessions_for_week,
    mark_review_shown,
    update_weekly_plan,
    upsert_weekly_review,
)
from plan.review_generator import generate_weekly_review_narrative
from plan.topic_generator import generate_plan_topics

logger = logging.getLogger(__name__)


def generate_plan(user_id: str, payload: dict) -> dict | None:
    logger.info(f"Generating weekly plan for user {user_id}, week {payload['week_number']}")
    plan_data = generate_plan_topics(payload)
    deactivate_current_plans(user_id)
    db_payload = {
        "week_number": payload["week_number"],
        "week_start_date": payload["week_start_date"],
        "speaker_level": payload["speaker_level"],
        "sessions_per_day": payload["sessions_per_day"],
        "plan_data": plan_data,
    }
    return create_weekly_plan(user_id, db_payload)


def get_current_plan(user_id: str) -> dict | None:
    return fetch_current_plan(user_id)


def mark_topic_complete(user_id: str, week_number: int, day: int, session: int, session_id: str) -> dict | None:
    plan = fetch_current_plan(user_id, week_number)
    if not plan:
        return None

    plan_data = plan.get("plan_data") or {}
    topics = plan_data.get("topics", [])
    updated = False
    for topic in topics:
        if topic.get("day") == day and topic.get("session") == session:
            topic["completed"] = True
            topic["completed_at"] = current_timestamp_iso()
            topic["session_id"] = session_id
            updated = True
            break

    if not updated:
        return None

    plan_data["topics"] = topics
    success = update_weekly_plan(plan["id"], plan_data)
    if not success:
        return None

    plan["plan_data"] = plan_data
    return plan


def build_weekly_review(user_id: str, week_number: int) -> dict | None:
    plan = fetch_current_plan(user_id, week_number)
    if not plan:
        return None

    sessions = fetch_sessions_for_week(user_id, week_number)
    topics = (plan.get("plan_data") or {}).get("topics", [])
    total_topics = len(topics)

    completed_pairs = {
        (row.get("plan_day"), row.get("plan_session_num"))
        for row in sessions
        if row.get("plan_day") is not None and row.get("plan_session_num") is not None
    }
    completion_rate = (len(completed_pairs) / total_topics) if total_topics else 0.0

    avg_overall = _avg(sessions, "overall")
    avg_confidence = _avg(sessions, "confidence")
    avg_clarity = _avg(sessions, "clarity")
    avg_engagement = _avg(sessions, "engagement")
    avg_nervousness = _avg(sessions, "nervousness")

    metric_scores = {
        "confidence": avg_confidence,
        "clarity": avg_clarity,
        "engagement": avg_engagement,
        "nervousness": 1.0 - avg_nervousness,
    }
    strongest_metric = max(metric_scores, key=metric_scores.get)
    weakest_metric = min(metric_scores, key=metric_scores.get)

    planned_by_day = defaultdict(set)
    completed_by_day = defaultdict(set)
    for topic in topics:
        planned_by_day[int(topic.get("day"))].add(int(topic.get("session")))
    for day, session_num in completed_pairs:
        if day is not None and session_num is not None:
            completed_by_day[int(day)].add(int(session_num))

    missed_days = sorted(
        day for day, planned_sessions in planned_by_day.items()
        if not planned_sessions.issubset(completed_by_day.get(day, set()))
    )

    review_data = {
        "completion_rate": completion_rate,
        "avg_overall_score": avg_overall,
        "avg_confidence": avg_confidence,
        "avg_clarity": avg_clarity,
        "avg_engagement": avg_engagement,
        "avg_nervousness": avg_nervousness,
        "weakest_metric": weakest_metric,
        "strongest_metric": strongest_metric,
        "missed_days": missed_days,
    }
    review_data["review_narrative"] = generate_weekly_review_narrative(review_data)

    return upsert_weekly_review(user_id, week_number, plan["week_start_date"], review_data)


def set_review_shown(user_id: str, week_number: int) -> bool:
    return mark_review_shown(user_id, week_number)


def get_personal_bests(user_id: str) -> dict | None:
    return fetch_personal_bests(user_id)


def _avg(rows: list[dict], key: str) -> float:
    values = [float(row.get(key)) for row in rows if row.get(key) is not None]
    if not values:
        return 0.0
    return sum(values) / len(values)
