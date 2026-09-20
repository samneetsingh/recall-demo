"""The Recall.ai HTTP calls.

Bot schema v1.11.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from app.config import settings
from app.db.models import Mode

logger = logging.getLogger(__name__)

_LEAVE_RETRY_SECONDS = 2.0


class RecallError(Exception):
    """A call to Recall failed. The message goes in the `error_reason` column."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        # `None` means the request got no HTTP answer.
        self.status = status


def _redact(text: str) -> str:
    """Take the API key out of text that goes in an error message or a log.

    The `error_reason` column is shown to the user, so the key must never
    reach it.
    """
    key = settings.RECALL_API_KEY
    return text.replace(key, "***") if key else text


def _require_api_key() -> None:
    if not settings.RECALL_API_KEY:
        raise RecallError("no Recall API key")


def _is_transient(error: RecallError) -> bool:
    """True when a second attempt can succeed: a network fault or a Recall fault."""
    return error.status is None or error.status == 429 or error.status >= 500


def _post(path: str, body: dict[str, Any]) -> httpx.Response:
    """Send one POST to Recall. Raise `RecallError` for each failure."""
    _require_api_key()

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
        raise RecallError(
            f"recall http {response.status_code}: {detail}", response.status_code
        )

    return response


def _recording_config(mode: Mode) -> dict[str, Any]:
    """Give the `recording_config`. Chat mode keeps no media and reads no transcript."""
    config: dict[str, Any] = {
        # An empty object turns the participant events on.
        "participant_events": {},
        # Null is zero data retention. Recall keeps no audio, video or transcript.
        "retention": None,
    }
    events = ["participant_events.chat_message"]

    if mode == "voice":
        config["transcript"] = {
            "provider": {
                "recallai_streaming": {
                    # Zero data retention supports this mode only.
                    "mode": "prioritize_low_latency",
                    "language_code": "en",
                }
            }
        }
        events.append("transcript.data")

    config["realtime_endpoints"] = [
        {
            "type": "webhook",
            "url": f"{settings.PUBLIC_BASE_URL.rstrip('/')}/webhooks/recall",
            "events": events,
        }
    ]
    return config


def _automatic_leave() -> dict[str, Any]:
    """Give `automatic_leave`. The defaults suit a recorder, not a live intake."""
    return {
        # The default is 2 seconds, which is less than a Meet tab reload. The
        # bot cannot come back, so the session dies with it.
        "everyone_left_timeout": {"timeout": 120},
        # The default is 1200 seconds. The patient is already in the call.
        "noone_joined_timeout": 300,
    }


def build_request_body(
    meeting_url: str, session_id: str, mode: Mode = "chat"
) -> dict[str, Any]:
    """Give the body of the create-bot request."""
    return {
        "meeting_url": meeting_url,
        "bot_name": settings.RECALL_BOT_NAME,
        # The dashboard and the bot logs show the metadata. A failed bot is easy to find.
        "metadata": {"session_id": session_id},
        # No `chat.on_bot_join` hook. Recall sends that message at join time,
        # which can land after the first question. The backend sends the notice.
        "recording_config": _recording_config(mode),
        "automatic_leave": _automatic_leave(),
    }


def create_bot(meeting_url: str, session_id: str, mode: Mode = "chat") -> str:
    """Make a Recall bot for a meeting. Give the bot id.

    Raise `RecallError` with a short reason for each failure.
    """
    response = _post("/api/v1/bot/", build_request_body(meeting_url, session_id, mode))

    try:
        bot_id = response.json()["id"]
    except (ValueError, KeyError, TypeError) as error:
        raise RecallError("recall gave no bot id") from error

    logger.info("made recall bot %s for session %s, mode %s", bot_id, session_id, mode)
    return str(bot_id)


def send_chat_message(bot_id: str, text: str, pin: bool = False) -> None:
    """Send one chat message into the meeting of a bot.

    Google Meet takes the recipient `everyone` only, so it is not a parameter.
    It also refuses a message of more than 500 characters; the caller applies
    that limit.
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
    # A missing key is not transient, so it must fail before the retry.
    _require_api_key()
    path = f"/api/v1/bot/{bot_id}/leave_call/"

    try:
        _post(path, {})
    except RecallError as error:
        # A bot left behind sits in the patient's meeting, so this one call retries.
        if not _is_transient(error):
            raise
        logger.warning("leave of bot %s failed: %s. one retry.", bot_id, error)
        time.sleep(_LEAVE_RETRY_SECONDS)
        _post(path, {})

    logger.info("bot %s left the call", bot_id)
