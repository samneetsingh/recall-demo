"""Chat mode: the turn boundary, implemented with meeting chat messages.

The patient answers in the meeting chat, and the assistant asks its questions
there. Voice mode gives a second implementation of the same protocol in section
6 of docs/TASKS.md. Nothing above the boundary changes for either one.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from typing import Any

from app.config import settings
from app.db import session_store
from app.recall import client as recall_client
from app.recall.client import RecallError
from app.recall.events import dig

logger = logging.getLogger(__name__)

CHAT_EVENT = "participant_events.chat_message"

# Google Meet refuses a chat message of more than 500 characters.
MEET_CHAT_LIMIT = 500

# A sentence end is the first choice for a cut. The space is part of the match,
# so the next part starts at a word.
_SENTENCE_END = re.compile(r"[.!?]\s")


def _is_the_bot(sender: Any) -> bool:
    """True if the bot itself sent the message."""
    if not isinstance(sender, str):
        return False
    return sender.strip().casefold() == settings.RECALL_BOT_NAME.strip().casefold()


def _cut_point(head: str) -> int:
    """Give the index to cut at: after the last sentence end, else after a space."""
    ends = [match.end() for match in _SENTENCE_END.finditer(head)]
    if ends:
        return ends[-1]
    space = head.rfind(" ")
    return space + 1 if space > 0 else len(head)


def split_message(text: str, limit: int = MEET_CHAT_LIMIT) -> list[str]:
    """Cut a message into parts that the platform accepts.

    A question of two sentences gives one part. An empty text gives no part.
    """
    rest = text.strip()
    parts: list[str] = []
    while len(rest) > limit:
        cut = _cut_point(rest[:limit])
        parts.append(rest[:cut].strip())
        rest = rest[cut:].strip()
    if rest:
        parts.append(rest)
    return parts


class ChatMode:
    """The turn boundary, implemented with chat messages."""

    def handle_incoming_turn(self, session_id: str, raw_event: Any) -> str | None:
        """Give the patient text of one chat event, or None.

        It gives None, and never an exception, for each event that is not a
        patient turn. Recall adds fields without a notice, and a webhook
        handler must not stop on a shape that it does not know.
        """
        payload = getattr(raw_event, "payload", None)
        if getattr(raw_event, "name", None) != CHAT_EVENT:
            return None
        if not isinstance(payload, Mapping):
            return None

        text = dig(payload, "data", "data", "data", "text")
        if not isinstance(text, str) or not text.strip():
            return None

        if _is_the_bot(dig(payload, "data", "data", "participant", "name")):
            # The bot receives its own messages back. Without this test the
            # assistant answers its own questions.
            logger.info("session %s got its own message, no turn", session_id)
            return None

        return text.strip()

    def send_outgoing_turn(self, session_id: str, text: str) -> None:
        """Send one assistant turn into the meeting chat."""
        # `base.py` imports this module, so this import is not at the top.
        from app.modes.base import ModeError

        session = session_store.get_session(session_id)
        if session is None or not session.bot_id:
            raise ModeError(f"session {session_id} has no bot id, no message went out")

        parts = split_message(text)
        if not parts:
            raise ModeError("the message is empty, nothing went out")
        if len(parts) > 1:
            logger.info(
                "session %s sends %s characters in %s messages",
                session_id,
                len(text),
                len(parts),
            )

        for part in parts:
            try:
                recall_client.send_chat_message(session.bot_id, part)
            except RecallError as error:
                # `engine/loop.py` catches ModeError and puts the session in
                # `error`. A RecallError goes past it, and the intake then
                # stops with no sign.
                raise ModeError(str(error)) from error
