"""The state machine of one intake session."""

from __future__ import annotations

import logging

from app.db import session_store
from app.db.models import Session
from app.engine import summary as summary_engine
from app.engine.intake import next_turn, turn_count
from app.engine.llm import LLMError
from app.modes.base import ModeError, get_mode

logger = logging.getLogger(__name__)


def start_intake(session_id: str) -> None:
    """Ask the first question. Call this when the assistant is in the call.

    A repeated `bot.in_call_recording` does not arrive here two times, because
    `apply_bot_event` refuses an event that is not newer.
    """
    session = _active_session(session_id)
    if session is None:
        return
    if session_store.get_turns(session_id):
        logger.info("session %s has a log, the intake is running", session_id)
        return
    _advance(session)


def run_turn(session_id: str, patient_text: str, event_id: str | None = None) -> None:
    """Take one patient turn, then ask the next question or end the intake."""
    session = _active_session(session_id)
    if session is None:
        return

    text = patient_text.strip()
    if not text:
        logger.info("session %s got an empty turn, no change", session_id)
        return

    if session_store.append_turn(session_id, "patient", text, event_id) is None:
        # The store refused it: a repeated delivery, or the assistant has not
        # answered the last message yet. This log line holds the text.
        logger.info("session %s refused a turn, event %s: %s", session_id, event_id, text)
        return

    _advance(session)


def _active_session(session_id: str) -> Session | None:
    """Give the session if it can take a turn, else None."""
    session = session_store.get_session(session_id)
    if session is None:
        logger.warning("no session has id %s, no turn", session_id)
        return None
    if session.status != "in_progress":
        logger.info("session %s is %s, no turn", session_id, session.status)
        return None
    return session


def _advance(session: Session) -> None:
    """Ask the next question, or make the summary and end the session."""
    try:
        # Read the log here, after the insert of the caller, so it holds each turn that arrived.
        log = session_store.get_turns(session.id)
        result = next_turn(log)
        if result.complete:
            _finish(session, log)
            return

        question = str(result.question)
        # Send first, then log. A question that the patient never got must not be in the log.
        get_mode(session.mode).send_outgoing_turn(session.id, question)
        session_store.append_turn(session.id, "bot", question)
    except (LLMError, ModeError) as error:
        logger.warning("session %s failed: %s", session.id, error)
        session_store.set_status(session.id, "error", str(error))


def _finish(session: Session, log: list[dict[str, str]]) -> None:
    """Write the summary, then end the session.

    The summary is written before the status. The frontend reads the status and
    then asks for the summary, so the opposite order gives a window in which a
    complete session has none.
    """
    summary = summary_engine.make_summary(log)
    session_store.set_summary(session.id, summary)
    session_store.set_status(session.id, "complete")
    logger.info("session %s is complete after %s turns", session.id, turn_count(log))
