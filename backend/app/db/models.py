"""The SQLite schema and the types of the sessions table.

Query SQL is in ``session_store.py``.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from typing import Any, Literal

# The states of a session.
#
#     creating_bot -> waiting_for_bot -> in_progress -> complete
#                                      \-> error
Status = Literal[
    "creating_bot",
    "waiting_for_bot",
    "in_progress",
    "complete",
    "error",
]

# The interaction mode. The mode selects the implementation of
# `handle_incoming_turn` and `send_outgoing_turn`.
Mode = Literal["chat", "voice"]

# The speaker of one turn in the conversation log.
Role = Literal["bot", "patient"]

# The first schema. This is migration 1, so it must never change.
SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id            TEXT PRIMARY KEY,
    meeting_url   TEXT NOT NULL,
    mode          TEXT NOT NULL DEFAULT 'chat',
    status        TEXT NOT NULL DEFAULT 'creating_bot',
    error_reason  TEXT,
    bot_id        TEXT,
    transcript    TEXT NOT NULL DEFAULT '[]',
    summary       TEXT,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);
"""


# Schema migrations, in order
#
# Rule: an entry that shipped must never change and must never be removed. A
# database in use has already applied it. A change goes at the end of the list.
MIGRATIONS: list[str] = [
    SCHEMA,
    # The time of the last bot status event that the session applied. Recall
    # delivers the events out of order, so the handler compares this value.
    "ALTER TABLE sessions ADD COLUMN last_event_at TEXT;",
    # The conversation log, which was a JSON array in `sessions.transcript`.
    # An INSERT cannot lose a turn, and the unique index refuses an event that
    # Recall delivers more than one time.
    """
    CREATE TABLE IF NOT EXISTS turns (
        id          INTEGER PRIMARY KEY,
        session_id  TEXT NOT NULL,
        role        TEXT NOT NULL,
        text        TEXT NOT NULL,
        event_id    TEXT,
        created_at  TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS turns_session ON turns(session_id, id);
    CREATE UNIQUE INDEX IF NOT EXISTS turns_event ON turns(session_id, event_id);
    """,
    # Move each entry of the old JSON array into a row, in order.
    """
    INSERT INTO turns (session_id, role, text, created_at)
    SELECT s.id,
           json_extract(t.value, '$.role'),
           json_extract(t.value, '$.text'),
           s.updated_at
      FROM sessions s, json_each(COALESCE(s.transcript, '[]')) t;
    """,
    "ALTER TABLE sessions DROP COLUMN transcript;",
    # Voice mode. One `transcript.data` utterance is not a turn: a patient
    # answers in parts. The parts wait here until a silence ends the turn.
    # The partial index is what makes one open buffer for one session.
    """
    CREATE TABLE IF NOT EXISTS voice_buffers (
        id            INTEGER PRIMARY KEY,
        session_id    TEXT NOT NULL,
        text          TEXT NOT NULL,
        last_part_at  TEXT NOT NULL,
        flushed_at    TEXT,
        created_at    TEXT NOT NULL
    );
    CREATE UNIQUE INDEX IF NOT EXISTS voice_buffers_open
        ON voice_buffers(session_id) WHERE flushed_at IS NULL;
    """,
]


@dataclass(frozen=True)
class Turn:
    """One turn of the conversation. The `id` gives the order."""

    id: int
    session_id: str
    role: Role
    text: str
    event_id: str | None
    created_at: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> Turn:
        """Make a turn from one database row."""
        return cls(
            id=row["id"],
            session_id=row["session_id"],
            role=row["role"],
            text=row["text"],
            event_id=row["event_id"],
            created_at=row["created_at"],
        )


@dataclass(frozen=True)
class Session:
    """The data of one session.

    The conversation log is not here. It is in the `turns` table, and
    ``session_store.get_turns`` reads it. ``summary`` is JSON text in the
    database and a Python object here.
    """

    id: str
    meeting_url: str
    mode: Mode
    status: Status
    error_reason: str | None
    bot_id: str | None
    summary: dict[str, Any] | None
    created_at: str
    updated_at: str
    last_event_at: str | None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> Session:
        """Make a session from one database row."""
        return cls(
            id=row["id"],
            meeting_url=row["meeting_url"],
            mode=row["mode"],
            status=row["status"],
            error_reason=row["error_reason"],
            bot_id=row["bot_id"],
            summary=json.loads(row["summary"]) if row["summary"] else None,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            last_event_at=row["last_event_at"],
        )
