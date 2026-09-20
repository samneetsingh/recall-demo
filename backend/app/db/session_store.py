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
from app.db.models import MIGRATIONS, Mode, Role, Session, Status


def _now() -> str:
    """Get current time as ISO 8601 text in UTC, to the microsecond.

    The width is fixed, so `<` and `<=` on the text are the same on the time.
    The voice buffer needs that: it measures a silence of a few seconds, and
    it compares `last_part_at` in SQL.
    """
    return datetime.now(UTC).isoformat(timespec="microseconds")


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
    """Bring the database file to the newest schema version."""
    with connect() as connection:
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        for index, statement in enumerate(MIGRATIONS[version:], start=version + 1):
            connection.executescript(statement)
            # PRAGMA does not accept a parameter. `index` is a position in
            # MIGRATIONS, never a value from a request.
            connection.execute(f"PRAGMA user_version = {index}")


def schema_version() -> int:
    """Give the schema version of the database file."""
    with connect() as connection:
        return int(connection.execute("PRAGMA user_version").fetchone()[0])


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
                id, meeting_url, mode, status, created_at, updated_at
            )
            VALUES (?, ?, ?, 'creating_bot', ?, ?)
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


def set_bot_id(session_id: str, bot_id: str) -> Session | None:
    """Keep the Recall bot id against a session."""
    with connect() as connection:
        connection.execute(
            "UPDATE sessions SET bot_id = ?, updated_at = ? WHERE id = ?",
            (bot_id, _now(), session_id),
        )
        return _fetch(connection, session_id)


def get_session_by_bot_id(bot_id: str) -> Session | None:
    """Give the session of a bot id, or None.

    A Recall event carries the bot id and not the session id, so the webhook
    route needs this direction.
    """
    with connect() as connection:
        row = connection.execute(
            "SELECT * FROM sessions WHERE bot_id = ?",
            (bot_id,),
        ).fetchone()
        return Session.from_row(row) if row is not None else None


def apply_bot_event(
    session_id: str,
    status: Status,
    error_reason: str | None,
    event_at: str | None,
) -> bool:
    """Apply a bot status event. Give False if the event changed nothing.

    Recall delivers the events out of order, so the time of the event decides,
    not the time it arrived. An event that is not newer than the last one is
    refused, and a session that is `complete` does not change.
    """
    with connect() as connection:
        cursor = connection.execute(
            """
            UPDATE sessions
               SET status = ?, error_reason = ?, updated_at = ?,
                   last_event_at = COALESCE(?, last_event_at)
             WHERE id = ?
               AND status != 'complete'
               AND (? IS NULL OR last_event_at IS NULL OR last_event_at < ?)
            """,
            (status, error_reason, _now(), event_at, session_id, event_at, event_at),
        )
        return cursor.rowcount > 0


def set_summary(session_id: str, summary: dict[str, Any]) -> Session | None:
    """Write the structured summary of a session."""
    with connect() as connection:
        connection.execute(
            "UPDATE sessions SET summary = ?, updated_at = ? WHERE id = ?",
            (json.dumps(summary), _now(), session_id),
        )
        return _fetch(connection, session_id)


def append_turn(
    session_id: str,
    role: Role,
    text: str,
    event_id: str | None = None,
) -> int | None:
    """Add one turn. Give its id, or None if the turn did not go in.

    The conversation is half-duplex, as docs/SPEC.md says for voice mode. A
    turn goes in only if its role is not the role of the last turn, so the
    log always alternates. A second patient message that arrives before the
    assistant has answered the first is refused, and it is not queued.

    Three rules, one statement, so two handlers that operate at the same
    time cannot lose a turn or write past each other:

    - the session must exist. SQLite does not apply a foreign key unless
      `PRAGMA foreign_keys` is on;
    - the role must change. `IS NOT` gives true for an empty log, so the
      first turn is accepted;
    - `event_id` must be new. It is the Svix message id, which stays the
      same for each retry of one message.
    """
    with connect() as connection:
        cursor = connection.execute(
            """
            INSERT OR IGNORE INTO turns (
                session_id, role, text, event_id, created_at
            )
            SELECT ?, ?, ?, ?, ?
             WHERE EXISTS (SELECT 1 FROM sessions WHERE id = ?)
               AND ? IS NOT (
                   SELECT role FROM turns WHERE session_id = ? ORDER BY id DESC LIMIT 1
               )
            """,
            (session_id, role, text, event_id, _now(), session_id, role, session_id),
        )
        # Read rowcount first. After an insert that the index refused,
        # `lastrowid` is not the id of this turn.
        if not cursor.rowcount:
            return None
        connection.execute(
            "UPDATE sessions SET updated_at = ? WHERE id = ?",
            (_now(), session_id),
        )
        return cursor.lastrowid


def get_turns(session_id: str) -> list[dict[str, str]]:
    """Give the conversation log, in order."""
    with connect() as connection:
        rows = connection.execute(
            "SELECT role, text FROM turns WHERE session_id = ? ORDER BY id",
            (session_id,),
        ).fetchall()
        return [{"role": row["role"], "text": row["text"]} for row in rows]


def add_voice_part(session_id: str, text: str) -> int | None:
    """Add one transcript utterance to the open buffer of a session.

    Give the id of the buffer. One `transcript.data` event is one utterance and
    not one turn, so the parts wait here until a silence ends the turn.
    """
    with connect() as connection:
        row = connection.execute(
            """
            INSERT INTO voice_buffers (session_id, text, last_part_at, created_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(session_id) WHERE flushed_at IS NULL
            DO UPDATE SET text = voice_buffers.text || ' ' || excluded.text,
                          last_part_at = excluded.last_part_at
            RETURNING id
            """,
            (session_id, text, _now(), _now()),
        ).fetchone()
        return int(row["id"]) if row is not None else None


def claim_voice_buffer(session_id: str, not_after: str) -> tuple[int, str] | None:
    """Close the open buffer of a session and give its id and its words.

    `not_after` is the newest `last_part_at` that still counts as silence. A
    part that arrived after it means that the patient is still speaking, and
    the buffer stays open for a later wake-up.
    """
    with connect() as connection:
        row = connection.execute(
            """
            UPDATE voice_buffers
               SET flushed_at = ?
             WHERE session_id = ?
               AND flushed_at IS NULL
               AND last_part_at <= ?
            RETURNING id, text
            """,
            (_now(), session_id, not_after),
        ).fetchone()
        return (int(row["id"]), row["text"]) if row is not None else None


def open_voice_buffer(session_id: str) -> tuple[int, str] | None:
    """Give the open buffer of a session, or None."""
    with connect() as connection:
        row = connection.execute(
            """
            SELECT id, text FROM voice_buffers
             WHERE session_id = ? AND flushed_at IS NULL
            """,
            (session_id,),
        ).fetchone()
        return (int(row["id"]), row["text"]) if row is not None else None
