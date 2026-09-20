"""The Recall.ai webhook route.

Two configurations send events to this one route: the dashboard endpoint sends
the `bot.*` status changes, and `recording_config.realtime_endpoints` sends the
chat messages and the transcript. The event sets do not intersect.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request

from app.db import session_store
from app.db.models import Status
from app.recall import events as recall_events
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

# The real-time events. A later task gives each one its logic.
REALTIME_EVENTS = {"participant_events.chat_message", "transcript.data"}


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
    if event.name in REALTIME_EVENTS:
        # The chat loop and the voice loop are later tasks.
        logger.info("real-time event %s for bot %s", event.name, event.bot_id)
        return

    if event.name not in BOT_EVENT_STATUS and event.name != "bot.call_ended":
        logger.info("no rule for event %s, no change", event.name)
        return

    if event.bot_id is None:
        logger.warning("event %s has no bot id, no change", event.name)
        return

    session = session_store.get_session_by_bot_id(event.bot_id)
    if session is None:
        logger.warning("no session has bot id %s, no change", event.bot_id)
        return

    if session.status == "complete":
        logger.info("session %s is complete, event %s makes no change", session.id, event.name)
        return

    if event.name == "bot.call_ended":
        # The call stopped before the assessment was complete, so the session has no
        # summary. `error` is the only terminal status that is not `complete`.
        # The prefix shows that the call ended in a normal manner.
        reason = f"call_ended:{event.sub_code or 'unknown'}"
        session_store.set_status(session.id, "error", reason)
        logger.info("session %s ended early: %s", session.id, reason)
        return

    status = BOT_EVENT_STATUS[event.name]
    reason = event.sub_code if event.name in ERROR_EVENTS else None
    session_store.set_status(session.id, status, reason)
    logger.info("session %s is now %s, event %s", session.id, status, event.name)
