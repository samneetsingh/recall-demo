"""Voice mode: the turn boundary, implemented with speech.

The assistant speaks its questions with OpenAI TTS and Recall's output audio
endpoint, and it listens to the real-time transcript. It is a second
implementation of the protocol of `base.py`, next to `chat.py`.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from app.config import settings
from app.db import session_store
from app.recall import client as recall_client
from app.recall.client import RecallError
from app.recall.events import dig
from app.tts import openai_tts
from app.tts.openai_tts import TTSError

logger = logging.getLogger(__name__)

TRANSCRIPT_EVENT = "transcript.data"

_SPACES = re.compile(r"\s+")


@dataclass
class VoiceTurnGap:
    """The wake-up that ends a patient turn. It is not an event of Recall.

    `routes/webhooks.py` makes one when the silence timer fires, and
    `handle_incoming_turn` answers it with the whole answer of the patient.
    The mode writes `event_id` back, because the route needs the id of the
    buffer that flushed and the protocol gives text only.
    """

    session_id: str
    event_id: str | None = None


def _is_the_bot(sender: Any) -> bool:
    """True if the bot itself spoke.

    The bot plays its own audio into the meeting, so Recall can transcribe it
    back.
    """
    if not isinstance(sender, str):
        return False
    return sender.strip().casefold() == settings.RECALL_BOT_NAME.strip().casefold()


def utterance_text(payload: Mapping[str, Any]) -> str:
    """Give the words of one finalized utterance, as one line."""
    words = dig(payload, "data", "data", "words")
    if not isinstance(words, list):
        return ""

    parts = [
        word["text"]
        for word in words
        if isinstance(word, Mapping) and isinstance(word.get("text"), str)
    ]
    return _SPACES.sub(" ", " ".join(parts)).strip()


class VoiceMode:
    """The turn boundary, implemented with speech."""

    def handle_incoming_turn(self, session_id: str, raw_event: Any) -> str | None:
        """Give the whole answer of the patient, or None.

        A transcript utterance gives None and goes in the buffer. The gap that
        follows it gives the answer.
        """
        if isinstance(raw_event, VoiceTurnGap):
            return self._take_buffer(raw_event)

        if getattr(raw_event, "name", None) != TRANSCRIPT_EVENT:
            # A chat message in a voice session is not a turn. One session has
            # one mode.
            return None

        payload = getattr(raw_event, "payload", None)
        if not isinstance(payload, Mapping):
            return None

        if _is_the_bot(dig(payload, "data", "data", "participant", "name")):
            logger.info("session %s heard itself, no part", session_id)
            return None

        text = utterance_text(payload)
        if not text:
            return None

        session_store.add_voice_part(session_id, text)
        return None

    def send_outgoing_turn(self, session_id: str, text: str) -> None:
        """Say one assistant turn into the meeting."""
        self._speak(session_id, text)

    def send_notice(self, session_id: str, text: str) -> None:
        """Say the consent notice."""
        self._speak(session_id, text)

    def _take_buffer(self, gap: VoiceTurnGap) -> str | None:
        """Close the buffer if the patient stopped, and give the words."""
        silent_since = datetime.now(UTC) - timedelta(
            seconds=settings.VOICE_TURN_GAP_SECONDS
        )
        claimed = session_store.claim_voice_buffer(
            gap.session_id, silent_since.isoformat(timespec="microseconds")
        )
        if claimed is None:
            return None

        buffer_id, text = claimed
        # One buffer row is one turn
        gap.event_id = f"voice-{buffer_id}"
        logger.info("session %s ended a turn, buffer %s", gap.session_id, buffer_id)
        return text.strip() or None

    def _speak(self, session_id: str, text: str) -> None:
        """Make the audio of one text, then play it into the meeting."""

        from app.modes.base import ModeError

        session = session_store.get_session(session_id)
        if session is None or not session.bot_id:
            raise ModeError(f"session {session_id} has no bot id, no audio went out")

        words = text.strip()
        if not words:
            raise ModeError("the message is empty, nothing went out")

        try:
            audio = openai_tts.speak(words)
        except TTSError as error:
            # `engine/loop.py` catches ModeError and puts the session in
            # `error`.
            raise ModeError(str(error)) from error

        try:
            recall_client.send_output_audio(session.bot_id, audio)
        except RecallError as error:
            raise ModeError(str(error)) from error
