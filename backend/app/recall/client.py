"""The Recall.ai create-bot call.

This module holds the create-bot call only. Bot schema v1.11.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import settings
from app.db.models import Mode

logger = logging.getLogger(__name__)


class RecallError(Exception):
    """A create-bot call failed. The message goes in the `error_reason` column."""


def _redact(text: str) -> str:
    """Take the API key out of text that goes in an error message or a log.

    The `error_reason` column is shown to the user, so the key must never
    reach it.
    """
    key = settings.RECALL_API_KEY
    return text.replace(key, "***") if key else text


def _recording_config() -> dict[str, Any]:
    """Give the `recording_config` of the create-bot request."""
    return {
        # An empty object turns the participant events on.
        "participant_events": {},
        "transcript": {
            "provider": {
                "recallai_streaming": {
                    "mode": "prioritize_low_latency",
                    "language_code": "en",
                }
            }
        },
        "realtime_endpoints": [
            {
                "type": "webhook",
                "url": f"{settings.PUBLIC_BASE_URL.rstrip('/')}/webhooks/recall",
                "events": [
                    "participant_events.chat_message",
                    "transcript.data",
                ],
            }
        ],
    }


def build_request_body(meeting_url: str, session_id: str) -> dict[str, Any]:
    """Give the body of the create-bot request."""
    return {
        "meeting_url": meeting_url,
        "bot_name": settings.RECALL_BOT_NAME,
        # Recall shows the metadata in the dashboard and in the bot logs, which makes a failed bot easy to find.
        "metadata": {"session_id": session_id},
        "recording_config": _recording_config(),
    }


def create_bot(meeting_url: str, session_id: str, mode: Mode = "chat") -> str:
    """Make a Recall bot for a meeting. Give the bot id.

    Raise `RecallError` with a short reason for each failure.
    """
    if not settings.RECALL_API_KEY:
        raise RecallError("no Recall API key")

    url = f"{settings.RECALL_API_BASE.rstrip('/')}/api/v1/bot/"
    body = build_request_body(meeting_url, session_id)

    try:
        with httpx.Client(timeout=settings.RECALL_TIMEOUT_SECONDS) as client:
            response = client.post(
                url,
                json=body,
                headers={
                    "Authorization": f"Token {settings.RECALL_API_KEY}",
                    "Accept": "application/json",
                },
            )
    except httpx.HTTPError as error:
        raise RecallError(f"recall request failed: {type(error).__name__}") from error

    if response.status_code >= 400:
        detail = _redact(response.text)[:200]
        raise RecallError(f"recall http {response.status_code}: {detail}")

    try:
        bot_id = response.json()["id"]
    except (ValueError, KeyError, TypeError) as error:
        raise RecallError("recall gave no bot id") from error

    logger.info("made recall bot %s for session %s, mode %s", bot_id, session_id, mode)
    return str(bot_id)
