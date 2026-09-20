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


def _old_file(path: Path) -> None:
    """Make a database file as task 2 left it: version 0, no new column."""
    connection = sqlite3.connect(path)
    connection.executescript(TASK_2_SCHEMA)
    connection.execute(
        """
        INSERT INTO sessions (id, meeting_url, status, transcript, created_at, updated_at)
        VALUES ('old-1', 'https://meet.google.com/abc-defg-hij', 'complete', '[]', 'x', 'y')
        """
    )
    connection.commit()
    assert connection.execute("PRAGMA user_version").fetchone()[0] == 0
    connection.close()


def _columns(path: Path) -> set[str]:
    connection = sqlite3.connect(path)
    names = {row[1] for row in connection.execute("PRAGMA table_info(sessions)")}
    connection.close()
    return names


def test_a_new_file_gets_the_newest_version(db_path: Path) -> None:
    session_store.init_db()

    assert session_store.schema_version() == NEWEST_VERSION
    assert "last_event_at" in _columns(db_path)


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
