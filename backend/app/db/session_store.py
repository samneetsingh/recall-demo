"""
The read and write helpers for the sessions table.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

from app.config import settings
from app.db.models import SCHEMA, Mode, Role, Session, Status


def _now() -> str:
    """Get current time as ISO 8601 text in UTC."""
    return datetime.now(UTC).isoformat(timespec="seconds")


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    """Open the database, write the changes at the end, and close it.

    Each call opens a new connection. FastAPI runs a synchronous route handler
    in a thread pool, and one SQLite connection is not safe in more than one
    thread.
    """
    settings.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(settings.DB_PATH)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


def init_db() -> None:
    """Make the sessions table if it does not exist."""
    with connect() as connection:
        connection.executescript(SCHEMA)


def _fetch(connection: sqlite3.Connection, session_id: str) -> Session | None:
    """Read one session on an open connection."""
    row = connection.execute(
        "SELECT * FROM sessions WHERE id = ?",
        (session_id,),
    ).fetchone()
    return Session.from_row(row) if row is not None else None


def create_session(meeting_url: str, mode: Mode = "chat") -> Session:
    """Make a new session row with the status `creating_bot`."""
    session_id = uuid.uuid4().hex
    now = _now()
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO sessions (
                id, meeting_url, mode, status, transcript, created_at, updated_at
            )
            VALUES (?, ?, ?, 'creating_bot', '[]', ?, ?)
            """,
            (session_id, meeting_url, mode, now, now),
        )
        session = _fetch(connection, session_id)
    if session is None:  # The INSERT above makes the row.
        raise RuntimeError("the new session is not in the database")
    return session


def get_session(session_id: str) -> Session | None:
    """Give one session, or None if no session has this id."""
    with connect() as connection:
        return _fetch(connection, session_id)


def set_status(
    session_id: str,
    status: Status,
    error_reason: str | None = None,
) -> Session | None:
    """Change the status of a session."""
    with connect() as connection:
        connection.execute(
            "UPDATE sessions SET status = ?, error_reason = ?, updated_at = ? WHERE id = ?",
            (status, error_reason, _now(), session_id),
        )
        return _fetch(connection, session_id)


def set_summary(session_id: str, summary: dict[str, Any]) -> Session | None:
    """Write the structured summary of a session."""
    with connect() as connection:
        connection.execute(
            "UPDATE sessions SET summary = ?, updated_at = ? WHERE id = ?",
            (json.dumps(summary), _now(), session_id),
        )
        return _fetch(connection, session_id)


def append_turn(session_id: str, role: Role, text: str) -> Session | None:
    """Add one turn to the end of the conversation log."""
    with connect() as connection:
        session = _fetch(connection, session_id)
        if session is None:
            return None
        log = [*session.transcript, {"role": role, "text": text}]
        connection.execute(
            "UPDATE sessions SET transcript = ?, updated_at = ? WHERE id = ?",
            (json.dumps(log), _now(), session_id),
        )
        return _fetch(connection, session_id)
