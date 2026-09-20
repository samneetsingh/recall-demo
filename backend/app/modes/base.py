"""The boundary between the state machine and the meeting platform.

Chat mode and voice mode each give one implementation of this protocol. Nothing
above the boundary knows which one a session uses. See docs/IMPLEMENTATION.md.
"""

from __future__ import annotations

from typing import Any, Protocol

from app.db.models import Mode
from app.modes.chat import ChatMode
from app.modes.voice import VoiceMode


class ModeError(Exception):
    """The mode of a session has no implementation."""


class TurnMode(Protocol):
    """How a patient turn arrives, and how an assistant turn goes out."""

    def handle_incoming_turn(self, session_id: str, raw_event: Any) -> str | None:
        """Give the patient text of one event.

        Give None when the event is not a complete patient turn. Voice mode
        needs this: a transcript part in the middle of a sentence is not a turn.
        """

    def send_outgoing_turn(self, session_id: str, text: str) -> None:
        """Send one assistant turn into the meeting."""

    def send_notice(self, session_id: str, text: str) -> None:
        """Send the consent notice, before the first question.

        It is not a turn, so it is not in the conversation log. Chat mode pins
        it, and voice mode will speak it.
        """


# The consent notice, sent one time when the bot is in the call.
CONSENT_NOTICE = (
    "Hello. I am an AI intake assistant, not a physician. "
    "I ask a few questions about your headaches before your visit, and your "
    "answers go into a summary for your clinician. Please answer in the chat."
)

CONSENT_NOTICE_VOICE = (
    "Hello. I am an AI intake assistant, not a physician. "
    "I ask a few questions about your headaches before your visit, and your "
    "answers go into a summary for your clinician. Please answer out loud."
)

# The last message of the intake. It is mode-neutral: voice mode says the same
# words through TTS. It is not a turn, so it is not in the conversation log.
CLOSING_MESSAGE = (
    "Thank you. The intake is complete, and your summary is on the page now. "
    "A clinician reads it before your visit."
)

MODES: dict[Mode, TurnMode] = {"chat": ChatMode(), "voice": VoiceMode()}

# The notice of each mode. The route reads it with the mode of the session
CONSENT_NOTICES: dict[Mode, str] = {
    "chat": CONSENT_NOTICE,
    "voice": CONSENT_NOTICE_VOICE,
}


def get_mode(mode: Mode) -> TurnMode:
    """Give the implementation of a mode."""
    try:
        return MODES[mode]
    except KeyError as error:
        raise ModeError(f"the mode {mode} has no implementation") from error
