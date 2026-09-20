"""Tests of the schema version and the migrations."""

import sqlite3
from pathlib import Path

import pytest

from app.config import settings
from app.db import models, session_store

# The schema as task 2 shipped it, with no `last_event_at` column.
TASK_2_SCHEMA = """
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

NEWEST_VERSION = len(models.MIGRATIONS)


@pytest.fixture
def db_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the store at an empty directory."""
    path = tmp_path / "migrate.sqlite3"
    monkeypatch.setattr(settings, "DB_PATH", path)
    return path


# A conversation as task 3 stored it, in the JSON column that task 4 drops.
OLD_TRANSCRIPT = (
    '[{"role": "bot", "text": "What brings you in?"},'
    ' {"role": "patient", "text": "A headache."},'
    ' {"role": "bot", "text": "How long?"}]'
)


def _old_file(path: Path, transcript: str = OLD_TRANSCRIPT) -> None:
    """Make a database file as task 2 left it: version 0, no new column."""
    connection = sqlite3.connect(path)
    connection.executescript(TASK_2_SCHEMA)
    connection.execute(
        """
        INSERT INTO sessions (id, meeting_url, status, transcript, created_at, updated_at)
        VALUES ('old-1', 'https://meet.google.com/abc-defg-hij', 'complete', ?, 'x', 'y')
        """,
        (transcript,),
    )
    connection.commit()
    assert connection.execute("PRAGMA user_version").fetchone()[0] == 0
    connection.close()


def _columns(path: Path) -> set[str]:
    connection = sqlite3.connect(path)
    names = {row[1] for row in connection.execute("PRAGMA table_info(sessions)")}
    connection.close()
    return names


def _tables(path: Path) -> set[str]:
    connection = sqlite3.connect(path)
    names = {
        row[0]
        for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }
    connection.close()
    return names


def test_a_new_file_gets_the_newest_version(db_path: Path) -> None:
    session_store.init_db()

    assert session_store.schema_version() == NEWEST_VERSION
    assert "last_event_at" in _columns(db_path)
    assert "transcript" not in _columns(db_path)
    assert _tables(db_path) >= {"sessions", "turns"}


def test_an_old_file_gets_the_column_and_keeps_its_rows(db_path: Path) -> None:
    """This is the case on this machine and on the homelab server."""
    _old_file(db_path)

    session_store.init_db()

    assert session_store.schema_version() == NEWEST_VERSION
    assert "last_event_at" in _columns(db_path)

    kept = session_store.get_session("old-1")
    assert kept is not None
    assert kept.status == "complete"
    assert kept.meeting_url == "https://meet.google.com/abc-defg-hij"
    assert kept.last_event_at is None


def test_the_backfill_moves_each_json_turn_into_a_row(db_path: Path) -> None:
    """This is the item that a fault makes expensive: a lost conversation."""
    _old_file(db_path)

    session_store.init_db()

    assert session_store.get_turns("old-1") == [
        {"role": "bot", "text": "What brings you in?"},
        {"role": "patient", "text": "A headache."},
        {"role": "bot", "text": "How long?"},
    ]


def test_the_transcript_column_is_gone(db_path: Path) -> None:
    _old_file(db_path)

    session_store.init_db()

    assert "transcript" not in _columns(db_path)


def test_an_empty_transcript_makes_no_turn(db_path: Path) -> None:
    """The rows on the volume have an empty array. The backfill must not fail."""
    _old_file(db_path, transcript="[]")

    session_store.init_db()

    assert session_store.get_turns("old-1") == []


def test_init_db_two_times_changes_nothing(db_path: Path) -> None:
    """The lifespan runs `init_db` at each start of the container."""
    session_store.init_db()
    session = session_store.create_session("https://meet.google.com/abc-defg-hij")

    session_store.init_db()

    assert session_store.schema_version() == NEWEST_VERSION
    assert session_store.get_session(session.id) is not None


def test_an_old_file_takes_every_migration_in_one_call(db_path: Path) -> None:
    """A file that is more than one version behind must not need two starts."""
    _old_file(db_path)

    session_store.init_db()

    assert session_store.schema_version() == NEWEST_VERSION


def test_the_first_migration_is_the_create_table(db_path: Path) -> None:
    """A file at version 0 already has the table, so entry 1 must not fail."""
    assert "CREATE TABLE IF NOT EXISTS sessions" in models.MIGRATIONS[0]
