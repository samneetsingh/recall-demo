"""The signature check and the parser for the requests from Recall.ai."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from svix.webhooks import Webhook, WebhookVerificationError

from app.config import settings


class SignatureError(Exception):
    """The request is not from Recall.ai, or the secret is absent."""


class PayloadError(Exception):
    """The signature is good, but the body is not an event."""


@dataclass(frozen=True)
class RecallEvent:
    """One verified event from Recall.ai.

    `sub_code` is a plain string. Recall adds values without a notice, so a
    value that this code does not know must not stop the application.
    `payload` holds the full object for the chat loop and the voice loop.
    `event_at` is the time of the event at Recall, in one format, or None.
    """

    name: str
    bot_id: str | None
    sub_code: str | None
    event_at: str | None
    payload: dict[str, Any]


def _dig(payload: Mapping[str, Any], *keys: str) -> Any:
    """Read a nested key. Give None if a level is absent or is not a mapping."""
    value: Any = payload
    for key in keys:
        if not isinstance(value, Mapping):
            return None
        value = value.get(key)
    return value


def _event_time(value: Any) -> str | None:
    """Put a Recall time in one format, for a comparison as text."""
    if not isinstance(value, str) or not value:
        return None
    try:
        moment = datetime.fromisoformat(value)
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC).isoformat(timespec="microseconds")


def verify_and_parse(raw_body: bytes, headers: Mapping[str, str]) -> RecallEvent:
    """Check the signature, then read the payload. Give the typed event.

    The two steps must stay in this order.
    """
    secret = settings.RECALL_WEBHOOK_SECRET
    if not secret:
        raise SignatureError("no webhook verification secret is configured")

    try:
        # `svix` 2.5.0 gives None here. It checks the signature and a 5 minute
        # timestamp tolerance. It raises on a failure.
        Webhook(secret).verify(raw_body, dict(headers))
    except WebhookVerificationError as error:
        raise SignatureError(str(error)) from error
    except Exception as error:  # A bad secret format raises its own class.
        raise SignatureError(f"verification failed: {type(error).__name__}") from error

    # The signature is good. Only now is the body safe to read.
    try:
        payload = json.loads(raw_body)
    except ValueError as error:
        raise PayloadError("the body is not JSON") from error

    if not isinstance(payload, dict):
        raise PayloadError("the body is not an object")

    name = payload.get("event")
    if not isinstance(name, str) or not name:
        raise PayloadError("the body has no event name")

    bot_id = _dig(payload, "data", "bot", "id")
    sub_code = _dig(payload, "data", "data", "sub_code")

    return RecallEvent(
        name=name,
        bot_id=str(bot_id) if bot_id else None,
        sub_code=str(sub_code) if sub_code else None,
        event_at=_event_time(_dig(payload, "data", "data", "updated_at")),
        payload=payload,
    )
