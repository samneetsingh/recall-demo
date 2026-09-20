"""The session routes.

A handler reads the request, calls ``app.db.session_store`` and gives a
response.
"""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, HttpUrl

from app.db import session_store
from app.db.models import Mode, Session
from app.modes.base import MODES
from app.recall import client as recall_client
from app.recall.client import RecallError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sessions", tags=["sessions"])


class CreateSessionRequest(BaseModel):
    """The body of `POST /sessions`."""

    meeting_url: HttpUrl
    mode: Mode = "chat"


class CreateSessionResponse(BaseModel):
    """The body of the answer to `POST /sessions`."""

    session_id: str
    status: str


class SessionResponse(BaseModel):
    """The body of the answer to `GET /sessions/{id}`.

    The frontend polls this route. It reads `status`, and it shows
    `error_reason` to the user when the status is `error`.
    """

    session_id: str
    status: str
    summary: dict[str, Any] | None = None
    error_reason: str | None = None


def _require_session(session_id: str) -> Session:
    """Give the session, or stop the request with HTTP 404."""
    session = session_store.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="no session has this id")
    return session


@router.post("", status_code=201, response_model=CreateSessionResponse)
def create_session(request: CreateSessionRequest) -> CreateSessionResponse:
    """Make a new session for a meeting URL, and make the Recall bot.

    A failed bot does not fail the request. The session row exists, so the
    result is 201 with the status `error`, and the frontend reads the reason
    from its poll of `GET /sessions/{id}`.
    """
    if request.mode not in MODES:
        # A bot costs money and joins a real meeting. The test is against the
        # modes with an implementation, so a new mode needs no change here.
        raise HTTPException(
            status_code=400, detail=f"the mode {request.mode} has no implementation"
        )

    session = session_store.create_session(str(request.meeting_url), request.mode)

    try:
        bot_id = recall_client.create_bot(
            str(request.meeting_url), session.id, request.mode
        )
    except RecallError as error:
        logger.warning("session %s got no bot: %s", session.id, error)
        session_store.set_status(session.id, "error", str(error))
        return CreateSessionResponse(session_id=session.id, status="error")

    session_store.set_bot_id(session.id, bot_id)
    session_store.set_status(session.id, "waiting_for_bot")
    return CreateSessionResponse(session_id=session.id, status="waiting_for_bot")


@router.get("/{session_id}", response_model=SessionResponse)
def get_session(session_id: str) -> SessionResponse:
    """Give the status of a session. The frontend polls this route."""
    session = _require_session(session_id)
    return SessionResponse(
        session_id=session.id,
        status=session.status,
        summary=session.summary,
        error_reason=session.error_reason,
    )


@router.get("/{session_id}/summary")
def get_summary(session_id: str) -> dict[str, Any]:
    """Give the structured summary. The result is 404 before the status is `complete`."""
    session = _require_session(session_id)
    if session.status != "complete":
        raise HTTPException(
            status_code=404,
            detail=f"the session is not complete, the status is {session.status}",
        )
    if session.summary is None:
        # `engine/loop.py` writes the summary before the status, so a complete
        # session with no summary is a fault of the backend. Do not hide it.
        raise HTTPException(
            status_code=500, detail="the session is complete and has no summary"
        )
    return session.summary
