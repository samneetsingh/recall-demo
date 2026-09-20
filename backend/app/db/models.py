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

# The database schema as defined in the architecture doc.
#
# This project has no migrations framework, so a column that comes later needs
# a new database file.
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
]


@dataclass(frozen=True)
class Session:
    """The data of one session.
    ``transcript`` and ``summary`` are JSON text in the database and Python
    objects here.
    """

    id: str
    meeting_url: str
    mode: Mode
    status: Status
    error_reason: str | None
    bot_id: str | None
    transcript: list[dict[str, str]]
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
            transcript=json.loads(row["transcript"]),
            summary=json.loads(row["summary"]) if row["summary"] else None,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            last_event_at=row["last_event_at"],
        )
