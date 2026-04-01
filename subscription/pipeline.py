from subscription.db_handler import activate_subscription, get_subscription_status, update_profile


def save_profile(user_id: str, payload: dict) -> dict | None:
    saved = update_profile(user_id, payload)
    if not saved:
        return None
    return {
        "user_id": user_id,
        "identity": saved.get("identity"),
        "work_domain": saved.get("work_domain"),
        "interest_areas": saved.get("interest_areas", []),
        "speaking_goal": saved.get("speaking_goal"),
        "practice_frequency": saved.get("practice_frequency"),
        "speaker_level": saved.get("speaker_level"),
        "diagnostic_complete": saved.get("diagnostic_complete"),
        "onboarding_complete": saved.get("onboarding_complete", False),
    }


def activate_user_subscription(user_id: str, plan: str) -> dict | None:
    return activate_subscription(user_id, plan)


def fetch_subscription_status(user_id: str) -> dict | None:
    return get_subscription_status(user_id)

