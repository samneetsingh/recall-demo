"""The Recall.ai webhook route.

Two configurations send events to this one route: the dashboard endpoint sends
the `bot.*` status changes, and `recording_config.realtime_endpoints` sends the
chat messages and the transcript. The event sets do not intersect.
"""

from __future__ import annotations

import logging
import time

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request

from app.config import settings
from app.db import session_store
from app.db.models import Session, Status
from app.engine import loop
from app.modes.base import CLOSING_MESSAGE, CONSENT_NOTICE, ModeError, TurnMode, get_mode
from app.modes.chat import CHAT_EVENT
from app.recall import client as recall_client
from app.recall import events as recall_events
from app.recall.client import RecallError
from app.recall.events import PayloadError, RecallEvent, SignatureError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

# The map from a bot status event to the session status.
#
# `bot.call_ended` is not here, because its result depends on the status now.
# `bot.done` is not here on purpose: it always comes after `bot.call_ended` or
# `bot.fatal`, which set the status. An event that is not in this map makes no
# change.
BOT_EVENT_STATUS: dict[str, Status] = {
    "bot.joining_call": "waiting_for_bot",
    "bot.in_waiting_room": "waiting_for_bot",
    "bot.in_call_not_recording": "waiting_for_bot",
    "bot.recording_permission_allowed": "waiting_for_bot",
    "bot.recording_permission_denied": "error",
    "bot.in_call_recording": "in_progress",
    "bot.fatal": "error",
}

# The events that carry a reason for the `error_reason` column.
ERROR_EVENTS = {"bot.fatal", "bot.recording_permission_denied"}

# The real-time events. `transcript.data` gets its logic in section 6.
REALTIME_EVENTS = {CHAT_EVENT, "transcript.data"}


@router.post("/recall")
async def recall_webhook(request: Request, background: BackgroundTasks) -> dict[str, bool]:
    """Take one event from Recall.ai.

    The signature is over the raw bytes, so this handler reads the body itself
    and does not let FastAPI parse it first.
    """
    raw_body = await request.body()

    try:
        event = recall_events.verify_and_parse(raw_body, request.headers)
    except SignatureError as error:
        logger.warning("refused a webhook request: %s", error)
        raise HTTPException(status_code=401, detail="bad signature") from error
    except PayloadError as error:
        logger.warning("bad webhook payload: %s", error)
        raise HTTPException(status_code=400, detail="bad payload") from error

    background.add_task(handle_event, event)
    return {"ok": True}


def handle_event(event: RecallEvent) -> None:
    """Apply one verified event to the session.

    This runs after the response. A failure here is invisible to Recall, so it
    must be in the log.
    """
    if event.name == CHAT_EVENT:
        _run_chat_turn(event)
        return

    if event.name in REALTIME_EVENTS:
        # The voice loop is section 6 of docs/TASKS.md.
        logger.info("real-time event %s for bot %s", event.name, event.bot_id)
        return

    if event.name not in BOT_EVENT_STATUS and event.name != "bot.call_ended":
        logger.info("no rule for event %s, no change", event.name)
        return

    session = _session_of(event)
    if session is None:
        return

    if event.name == "bot.call_ended":
        # The call stopped before the assessment was complete, so the session has no
        # summary. `error` is the only terminal status that is not `complete`.
        # The prefix shows that the call ended in a normal manner.
        status: Status = "error"
        reason: str | None = f"call_ended:{event.sub_code or 'unknown'}"
    else:
        status = BOT_EVENT_STATUS[event.name]
        reason = event.sub_code if event.name in ERROR_EVENTS else None

    if not session_store.apply_bot_event(session.id, status, reason, event.event_at):
        logger.info(
            "session %s did not take event %s of %s, no change",
            session.id,
            event.name,
            event.event_at,
        )
        return

    logger.info("session %s is now %s, event %s", session.id, status, event.name)

    if status == "in_progress":
        # The bot is in the call. The notice goes out first, then the first
        # question. `apply_bot_event` gave True, so a repeated event does not
        # arrive here and the notice goes out one time.
        _start_chat_intake(session)


def _session_of(event: RecallEvent) -> Session | None:
    """Give the session of the bot of an event, or None."""
    if event.bot_id is None:
        logger.warning("event %s has no bot id, no change", event.name)
        return None

    session = session_store.get_session_by_bot_id(event.bot_id)
    if session is None:
        logger.warning("no session has bot id %s, no change", event.bot_id)
        return None

    return session


def _start_chat_intake(session: Session) -> None:
    """Send the consent notice, then ask the first question."""
    try:
        mode = get_mode(session.mode)
    except ModeError as error:
        logger.warning("session %s has no mode: %s", session.id, error)
        session_store.set_status(session.id, "error", str(error))
        return

    try:
        mode.send_notice(session.id, CONSENT_NOTICE)
    except ModeError as error:
        # The notice is not the intake. If the meeting refuses it, the first
        # question fails in the same manner, and `engine/loop.py` writes the
        # reason on the session.
        logger.warning("session %s sent no notice: %s", session.id, error)

    loop.start_intake(session.id)


def _run_chat_turn(event: RecallEvent) -> None:
    """Take one chat message into the intake loop."""
    session = _session_of(event)
    if session is None:
        return

    try:
        mode = get_mode(session.mode)
    except ModeError as error:
        logger.warning("session %s has no mode: %s", session.id, error)
        session_store.set_status(session.id, "error", str(error))
        return

    text = mode.handle_incoming_turn(session.id, event)
    if text is None:
        return

    # The Svix message id is the same for each retry of one message, so the
    # turns table refuses a repeated delivery by itself.
    loop.run_turn(session.id, text, event.message_id)

    if session.status != "complete":
        # `session` is the status before this turn. A message that arrives
        # after the intake ended must not send the closing line again, and it
        # must not take the bot out of the call a second time.
        _finish_intake(session.id, mode)


def _finish_intake(session_id: str, mode: TurnMode) -> None:
    """Say one last line and leave, if the intake became complete on this turn."""
    session = session_store.get_session(session_id)
    if session is None or session.status != "complete":
        return

    try:
        mode.send_outgoing_turn(session_id, CLOSING_MESSAGE)
    except ModeError as error:
        # The intake is complete and the summary is written. A closing line
        # that did not go out must not take that away.
        logger.warning("session %s sent no closing message: %s", session_id, error)

    _leave_call(session)


def _leave_call(session: Session) -> None:
    """Take the bot out of the meeting. The intake is over.

    The patient must not have to remove the bot. A session in `error` keeps its
    bot: an error usually means that the bot takes no command, and the leave
    would fail in the same manner.
    """
    if session.bot_id is None:
        return

    # Recall accepted the closing line, and the bot has still to type it into
    # the meeting. A leave with no wait can cut the line. This handler runs
    # after the answer to Recall, so the wait costs nothing in the request.
    if settings.BOT_LEAVE_DELAY_SECONDS > 0:
        time.sleep(settings.BOT_LEAVE_DELAY_SECONDS)

    try:
        recall_client.leave_call(session.bot_id)
    except RecallError as error:
        # The summary is written and the status is `complete`. A bot that stays
        # in the call is untidy, and it costs no data.
        logger.warning("session %s did not leave the call: %s", session.id, error)
