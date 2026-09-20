"""The session routes.

A handler reads the request, calls ``app.db.session_store`` and gives a
response.
"""

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, HttpUrl

from app.db import session_store
from app.db.models import Mode, Session

router = APIRouter(prefix="/sessions", tags=["sessions"])

# The stub summary.
#
# `GET /sessions/{id}/summary` gives this object when the status is `complete`
# and the database holds no summary.
STUB_SUMMARY: dict[str, str] = {
    "chief_complaint": "STUB. No intake engine at this time.",
    "onset_duration": "STUB",
    "location_character": "STUB",
    "severity": "STUB",
    "triggers": "STUB",
    "associated_symptoms": "STUB",
    "prior_treatments": "STUB",
    "notes": "This summary is stub data from the backend skeleton.",
}


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
    """Make a new session for a meeting URL."""
    session = session_store.create_session(str(request.meeting_url), request.mode)
    # The next task calls `app/recall/client.py` here. It makes the bot, keeps
    # the bot id on the session row, and sets the status to `waiting_for_bot`.
    return CreateSessionResponse(session_id=session.id, status=session.status)


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
    return session.summary or STUB_SUMMARY
