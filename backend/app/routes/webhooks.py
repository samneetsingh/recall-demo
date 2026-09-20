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
# `bot.call_ended` is not here, because its result depends on the sub-code.
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

# The `bot.call_ended` sub-codes of a call that ended in a normal manner.
# docs/API_CONTRACT.md holds the list. Recall adds sub-codes without a notice,
# so this set must never become the whole set of the values Recall can send.
NORMAL_CALL_ENDED = frozenset(
    {
        "bot_received_leave_call",
        "call_ended_by_host",
        "bot_kicked_from_call",
        "timeout_exceeded_everyone_left",
        "timeout_exceeded_noone_joined",
        "call_ended_by_platform_waiting_room_timeout",
        "timeout_exceeded_silence_detected",
    }
)

# The events of the real-time endpoint. Chat mode reads the chat messages and
# makes no use of the transcript.
REALTIME_EVENTS = {CHAT_EVENT, "transcript.data"}

# A session in one of these statuses never changes again.
TERMINAL_STATUS = frozenset({"complete", "error"})

# The last line of an intake that stopped before the end. The patient must
# learn that it stopped, and not wait on a silent bot.
STOPPED_MESSAGE = (
    "I am sorry. A technical problem stopped the intake. "
    "You can leave the call now, and the page shows the reason."
)


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
    try:
        _dispatch_event(event)
    except Exception as error:
        # A wide catch, because nothing above this reads the result. Without it
        # the session keeps the status it had, with no reason on the row.
        logger.exception("event %s failed for bot %s", event.name, event.bot_id)
        session = _session_of(event)
        if session is None or session.status in TERMINAL_STATUS:
            return
        session_store.set_status(session.id, "error", f"{event.name}: {error}")
        _leave_call(session)


def _dispatch_event(event: RecallEvent) -> None:
    """Send one event to the intake loop, or change the status of its session."""
    if event.name == CHAT_EVENT:
        _run_chat_turn(event)
        return

    if event.name in REALTIME_EVENTS:
        logger.info("real-time event %s for bot %s", event.name, event.bot_id)
        return

    if event.name not in BOT_EVENT_STATUS and event.name != "bot.call_ended":
        logger.info("no rule for event %s, no change", event.name)
        return

    session = _session_of(event)
    if session is None:
        return

    if event.name == "bot.call_ended":
        status, reason = _call_ended_result(event.sub_code)
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

    logger.info(
        "session %s is now %s, event %s, sub-code %s",
        session.id,
        status,
        event.name,
        event.sub_code,
    )

    if status == "in_progress":
        # The bot is in the call. The notice goes out first, then the first
        # question. `apply_bot_event` gave True, so a repeated event does not
        # arrive here and the notice goes out one time.
        _start_chat_intake(session)


def _call_ended_result(sub_code: str | None) -> tuple[Status, str | None]:
    """Give the status and the reason for the end of a call.

    Both results are terminal: the bot is out of the call, so the frontend must
    stop its poll. A sub-code that this code does not know stays an error, and
    keeps its raw value as the reason.
    """
    if sub_code in NORMAL_CALL_ENDED:
        return "complete", None
    return "error", f"call_ended:{sub_code or 'unknown'}"


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
        _fail_session(session, str(error))
        return

    try:
        mode.send_notice(session.id, CONSENT_NOTICE)
    except ModeError as error:
        # The notice is not the intake. If the meeting refuses it, the first
        # question fails in the same manner, and `engine/loop.py` writes the
        # reason on the session.
        logger.warning("session %s sent no notice: %s", session.id, error)

    loop.start_intake(session.id)
    _finish_intake(session.id, mode)


def _run_chat_turn(event: RecallEvent) -> None:
    """Take one chat message into the intake loop."""
    session = _session_of(event)
    if session is None:
        return

    try:
        mode = get_mode(session.mode)
    except ModeError as error:
        logger.warning("session %s has no mode: %s", session.id, error)
        _fail_session(session, str(error))
        return

    text = mode.handle_incoming_turn(session.id, event)
    if text is None:
        return

    # The Svix message id is the same for each retry of one message, so the
    # turns table refuses a repeated delivery by itself.
    loop.run_turn(session.id, text, event.message_id)

    if session.status == "in_progress":
        # `session` is the status before this turn. Only a turn that the loop
        # could take can end the intake, so a message that arrives after the
        # end sends no second line and makes no second leave.
        _finish_intake(session.id, mode)


def _finish_intake(session_id: str, mode: TurnMode) -> None:
    """Say one last line and leave, if the intake ended on this turn."""
    session = session_store.get_session(session_id)
    if session is None or session.status not in TERMINAL_STATUS:
        return

    last_line = CLOSING_MESSAGE if session.status == "complete" else STOPPED_MESSAGE
    try:
        mode.send_outgoing_turn(session_id, last_line)
    except ModeError as error:
        # The status is terminal already. A line that did not go out must not
        # take away the summary or the reason.
        logger.warning("session %s sent no closing message: %s", session_id, error)

    _leave_call(session)


def _fail_session(session: Session, reason: str) -> None:
    """Put a session in `error` and take its bot out of the meeting.

    This is the path with no mode, so no line can go into the meeting first.
    """
    session_store.set_status(session.id, "error", reason)
    _leave_call(session)


def _leave_call(session: Session) -> None:
    """Take the bot out of the meeting. The intake is over.

    The patient must not have to remove the bot. An error takes the bot out in
    the same manner as a success: the usual error is a failed model call, and
    the bot itself is in good health.
    """
    if session.bot_id is None:
        return

    # Recall accepted the last line, and the bot has still to type it into the
    # meeting. A leave with no wait can cut the line. This handler runs after
    # the answer to Recall, so the wait costs nothing in the request.
    if settings.BOT_LEAVE_DELAY_SECONDS > 0:
        time.sleep(settings.BOT_LEAVE_DELAY_SECONDS)

    try:
        recall_client.leave_call(session.bot_id)
    except RecallError as error:
        # The result of the session is decided already. A leave that failed
        # must not change it.
        logger.warning("session %s did not leave the call: %s", session.id, error)
