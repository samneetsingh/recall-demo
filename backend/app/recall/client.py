"""The Recall.ai calls: make a bot, and send a chat message.

Bot schema v1.11.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import settings
from app.db.models import Mode

logger = logging.getLogger(__name__)


class RecallError(Exception):
    """A call to Recall failed. The message goes in the `error_reason` column."""


def _redact(text: str) -> str:
    """Take the API key out of text that goes in an error message or a log.

    The `error_reason` column is shown to the user, so the key must never
    reach it.
    """
    key = settings.RECALL_API_KEY
    return text.replace(key, "***") if key else text


# The `chat.on_bot_join` hook sends this when the bot joins. It is the one
# disclaimer that is permitted and it must stay below 500 characters.
CONSENT_NOTICE = (
    "Hello. I am an AI intake assistant, not a physician. "
    "I ask a few questions about your headaches before your visit, and your "
    "answers go into a summary for your clinician. Please answer in the chat."
)


def _post(path: str, body: dict[str, Any]) -> httpx.Response:
    """Send one POST to Recall. Raise `RecallError` for each failure."""
    if not settings.RECALL_API_KEY:
        raise RecallError("no Recall API key")

    url = f"{settings.RECALL_API_BASE.rstrip('/')}{path}"

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

    return response


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
        # No `chat.on_bot_join` hook. Recall sends that message when the bot
        # joins, and it arrived after the first question in the live call of
        # session 09. The backend sends the notice itself now, in order.
        "recording_config": _recording_config(),
    }


def create_bot(meeting_url: str, session_id: str, mode: Mode = "chat") -> str:
    """Make a Recall bot for a meeting. Give the bot id.

    Raise `RecallError` with a short reason for each failure.
    """
    response = _post("/api/v1/bot/", build_request_body(meeting_url, session_id))

    try:
        bot_id = response.json()["id"]
    except (ValueError, KeyError, TypeError) as error:
        raise RecallError("recall gave no bot id") from error

    logger.info("made recall bot %s for session %s, mode %s", bot_id, session_id, mode)
    return str(bot_id)


def send_chat_message(bot_id: str, text: str, pin: bool = False) -> None:
    """Send one chat message into the meeting of a bot.

    Google Meet takes the recipient `everyone` only, so it is not a parameter.
    It also refuses a message of more than 500 characters; `app/modes/chat.py`
    applies that limit before it calls this function.
    """
    body: dict[str, Any] = {"to": "everyone", "message": text}
    if pin:
        body["pin"] = True

    _post(f"/api/v1/bot/{bot_id}/send_chat_message/", body)
    logger.info("sent %s characters to the chat of bot %s, pin %s", len(text), bot_id, pin)


def leave_call(bot_id: str) -> None:
    """Take a bot out of its meeting.

    This is irreversible: the bot cannot come back, and a new bot needs a new
    session. The endpoint takes no body.
    """
    _post(f"/api/v1/bot/{bot_id}/leave_call/", {})
    logger.info("bot %s left the call", bot_id)
