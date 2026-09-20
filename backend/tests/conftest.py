"""The test configuration."""

import os
import tempfile
from collections.abc import Iterator
from pathlib import Path

TEST_DB_PATH = Path(tempfile.mkdtemp(prefix="recall-demo-tests-")) / "test.sqlite3"
os.environ["DB_PATH"] = str(TEST_DB_PATH)

import pytest  # noqa: E402  The import must come after the line above.
from fastapi.testclient import TestClient  # noqa: E402

from app.db import session_store  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(autouse=True)
def empty_database() -> None:
    """Give each test an empty sessions table."""
    TEST_DB_PATH.unlink(missing_ok=True)
    session_store.init_db()


@pytest.fixture
def client() -> Iterator[TestClient]:
    """Give a test client. The `with` block runs the lifespan of the application."""
    with TestClient(app) as test_client:
        yield test_client
