from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any

import requests

import config
from notifications import db_handler

logger = logging.getLogger(__name__)

EXPO_BATCH_SIZE = 100


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def is_valid_expo_push_token(token: str) -> bool:
    return token.startswith("ExponentPushToken[") or token.startswith("ExpoPushToken[")


def _chunks(items: list[dict[str, Any]], size: int) -> list[list[dict[str, Any]]]:
    return [items[index : index + size] for index in range(0, len(items), size)]


def _build_message(token: str, payload: dict[str, Any]) -> dict[str, Any]:
    data = dict(payload.get("data") or {})
    image_url = payload.get("image_url")
    if image_url:
        data["image_url"] = image_url

    message = {
        "to": token,
        "title": payload["title"],
        "body": payload["body"],
        "sound": "default",
        "data": data,
    }
    if image_url:
        message["richContent"] = {"image": image_url}
    return message


def _send_batch(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    response = requests.post(
        config.EXPO_PUSH_SEND_URL,
        json=messages,
        headers={
            "Accept": "application/json",
            "Accept-Encoding": "gzip, deflate",
            "Content-Type": "application/json",
        },
        timeout=30,
    )
    response.raise_for_status()
    body = response.json()
    data = body.get("data")
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return [data]
    return []


def send_campaign(campaign_id: str, payload: dict[str, Any], tokens: list[dict[str, Any]]) -> None:
    rate_limit = max(1, int(getattr(config, "NOTIFICATION_RATE_LIMIT_PER_SECOND", 590)))
    valid_tokens = [token for token in tokens if is_valid_expo_push_token(token.get("expo_push_token", ""))]
    invalid_rows = [token for token in tokens if token not in valid_tokens]
    invalid_tokens = [token.get("expo_push_token", "") for token in invalid_rows]
    if invalid_tokens:
        db_handler.deactivate_tokens([token for token in invalid_tokens if token])
        db_handler.insert_deliveries(
            [
                {
                    "campaign_id": campaign_id,
                    "push_token_id": row.get("id"),
                    "expo_push_token": row.get("expo_push_token"),
                    "status": "error",
                    "error": "Invalid Expo push token",
                }
                for row in invalid_rows
            ]
        )

    sent_count = 0
    failed_count = len(invalid_tokens)
    db_handler.update_campaign(campaign_id, {"status": "sending", "started_at": _now()})

    window_started_at = time.monotonic()
    sent_in_window = 0

    try:
        index = 0
        while index < len(valid_tokens):
            if sent_in_window >= rate_limit:
                elapsed = time.monotonic() - window_started_at
                if elapsed < 1:
                    time.sleep(1 - elapsed)
                window_started_at = time.monotonic()
                sent_in_window = 0

            remaining_window = rate_limit - sent_in_window
            batch_size = min(EXPO_BATCH_SIZE, remaining_window, len(valid_tokens) - index)
            batch = valid_tokens[index : index + batch_size]
            messages = [_build_message(row["expo_push_token"], payload) for row in batch]

            try:
                tickets = _send_batch(messages)
            except Exception as exc:
                logger.exception("Expo push batch failed: %s", exc)
                failed_count += len(batch)
                db_handler.insert_deliveries(
                    [
                        {
                            "campaign_id": campaign_id,
                            "push_token_id": row.get("id"),
                            "expo_push_token": row.get("expo_push_token"),
                            "status": "error",
                            "error": str(exc),
                        }
                        for row in batch
                    ]
                )
                index += batch_size
                sent_in_window += batch_size
                continue

            deliveries = []
            tokens_to_deactivate = []
            for row, ticket in zip(batch, tickets):
                status = ticket.get("status", "error")
                details = ticket.get("details") or {}
                error = ticket.get("message") or ticket.get("error") or details.get("error")
                if status == "ok":
                    sent_count += 1
                else:
                    failed_count += 1
                    if details.get("error") == "DeviceNotRegistered":
                        tokens_to_deactivate.append(row["expo_push_token"])

                deliveries.append(
                    {
                        "campaign_id": campaign_id,
                        "push_token_id": row.get("id"),
                        "expo_push_token": row.get("expo_push_token"),
                        "status": status,
                        "expo_ticket_id": ticket.get("id"),
                        "error": error,
                    }
                )

            if len(tickets) < len(batch):
                for row in batch[len(tickets) :]:
                    failed_count += 1
                    deliveries.append(
                        {
                            "campaign_id": campaign_id,
                            "push_token_id": row.get("id"),
                            "expo_push_token": row.get("expo_push_token"),
                            "status": "error",
                            "error": "Missing Expo ticket response",
                        }
                    )

            db_handler.insert_deliveries(deliveries)
            db_handler.deactivate_tokens(tokens_to_deactivate)

            index += batch_size
            sent_in_window += batch_size

        db_handler.update_campaign(
            campaign_id,
            {
                "status": "completed",
                "sent_count": sent_count,
                "failed_count": failed_count,
                "completed_at": _now(),
            },
        )
    except Exception as exc:
        logger.exception("Notification campaign failed: %s", exc)
        db_handler.update_campaign(
            campaign_id,
            {
                "status": "failed",
                "sent_count": sent_count,
                "failed_count": failed_count,
                "completed_at": _now(),
            },
        )
