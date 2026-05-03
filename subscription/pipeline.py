from subscription import razorpay_service
from subscription.db_handler import (
    apply_subscription_entitlement,
    create_pending_razorpay_subscription,
    expire_subscription_entitlement,
    fetch_active_razorpay_subscription,
    fetch_subscription_by_razorpay_id,
    get_subscription_status,
    record_webhook_event,
    update_profile,
    update_subscription_from_razorpay,
)


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


def create_checkout_subscription(user_id: str, plan: str) -> dict | None:
    subscription = razorpay_service.create_subscription(user_id, plan)
    saved = create_pending_razorpay_subscription(user_id, plan, subscription)
    if not saved:
        return None
    return {
        "key_id": razorpay_service.config.RAZORPAY_KEY_ID,
        "business_name": razorpay_service.config.RAZORPAY_BUSINESS_NAME,
        "subscription_id": subscription.get("id"),
        "plan": plan,
        "amount": razorpay_service.get_amount(plan),
        "currency": razorpay_service.config.RAZORPAY_CURRENCY,
        "status": subscription.get("status"),
    }


def verify_checkout_subscription(user_id: str, payload: dict) -> dict | None:
    payment_id = payload.get("razorpay_payment_id")
    subscription_id = payload.get("razorpay_subscription_id")
    signature = payload.get("razorpay_signature")
    if not payment_id or not subscription_id or not signature:
        return None

    if not razorpay_service.verify_checkout_signature(payment_id, subscription_id, signature):
        return None

    local = fetch_subscription_by_razorpay_id(subscription_id)
    if not local or local.get("user_id") != user_id:
        return None

    subscription = razorpay_service.fetch_subscription(subscription_id)
    plan = local.get("app_plan") or _plan_from_notes(subscription)
    update_subscription_from_razorpay(subscription_id, subscription, app_plan=plan, user_id=user_id)
    return apply_subscription_entitlement(user_id, plan, subscription)


def fetch_subscription_status(user_id: str) -> dict | None:
    active = fetch_active_razorpay_subscription(user_id)
    if active:
        try:
            subscription = razorpay_service.fetch_subscription(active["razorpay_subscription_id"])
            plan = active.get("app_plan")
            update_subscription_from_razorpay(active["razorpay_subscription_id"], subscription, app_plan=plan, user_id=user_id)
            status = subscription.get("status")
            if status in ("authenticated", "active"):
                apply_subscription_entitlement(user_id, plan, subscription)
            elif status in ("cancelled", "completed", "expired", "halted"):
                expire_subscription_entitlement(user_id, status)
        except Exception:
            pass
    return get_subscription_status(user_id)


def cancel_user_subscription(user_id: str) -> dict | None:
    active = fetch_active_razorpay_subscription(user_id)
    if not active:
        return None
    cancelled = razorpay_service.cancel_subscription(active["razorpay_subscription_id"])
    update_subscription_from_razorpay(active["razorpay_subscription_id"], cancelled, app_plan=active.get("app_plan"), user_id=user_id)
    return fetch_subscription_status(user_id)


def handle_razorpay_webhook(event_id: str, event_name: str, payload: dict) -> dict:
    if not record_webhook_event(event_id, event_name, payload):
        return {"processed": False, "duplicate": True}

    subscription = payload.get("payload", {}).get("subscription", {}).get("entity")
    if not subscription:
        return {"processed": True, "ignored": True}

    subscription_id = subscription.get("id")
    if not subscription_id:
        return {"processed": True, "ignored": True}

    local = fetch_subscription_by_razorpay_id(subscription_id)
    user_id = (local or {}).get("user_id") or _user_id_from_notes(subscription)
    plan = (local or {}).get("app_plan") or _plan_from_notes(subscription)
    if not user_id or not plan:
        return {"processed": True, "ignored": True}

    update_subscription_from_razorpay(subscription_id, subscription, app_plan=plan, user_id=user_id)
    status = subscription.get("status")
    if event_name in ("subscription.activated", "subscription.charged") or status in ("authenticated", "active"):
        apply_subscription_entitlement(user_id, plan, subscription)
    elif event_name in ("subscription.cancelled", "subscription.completed", "subscription.expired", "subscription.halted"):
        expire_subscription_entitlement(user_id, status or event_name)

    return {"processed": True}


def _user_id_from_notes(subscription: dict) -> str | None:
    notes = subscription.get("notes") or {}
    return notes.get("user_id") if isinstance(notes, dict) else None


def _plan_from_notes(subscription: dict) -> str | None:
    notes = subscription.get("notes") or {}
    plan = notes.get("app_plan") if isinstance(notes, dict) else None
    return plan if plan in ("weekly", "monthly") else None
