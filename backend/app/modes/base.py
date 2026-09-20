"""The boundary between the state machine and the meeting platform.

Chat mode and voice mode each give one implementation of this protocol. Nothing
above the boundary knows which one a session uses. See docs/IMPLEMENTATION.md.
"""

from __future__ import annotations

from typing import Any, Protocol

from app.db.models import Mode
from app.modes.chat import ChatMode


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


# The last message of the intake. It is mode-neutral: voice mode says the same
# words through TTS. It is not a turn, so it is not in the conversation log.
CLOSING_MESSAGE = (
    "Thank you. The intake is complete, and your summary is on the page now. "
    "A clinician reads it before your visit."
)

# Section 6 of docs/TASKS.md puts `voice` here. `ChatMode` holds no state, so
# one instance for the process is correct: the state is in the database.
MODES: dict[Mode, TurnMode] = {"chat": ChatMode()}


def get_mode(mode: Mode) -> TurnMode:
    """Give the implementation of a mode."""
    try:
        return MODES[mode]
    except KeyError as error:
        raise ModeError(f"the mode {mode} has no implementation") from error
