"""The test configuration."""

import os
import tempfile
from collections.abc import Iterator
from pathlib import Path

TEST_DB_PATH = Path(tempfile.mkdtemp(prefix="recall-demo-tests-")) / "test.sqlite3"
os.environ["DB_PATH"] = str(TEST_DB_PATH)

# Fake values. `app.config` reads the environment one time, at its import, so
# these lines must come before the imports below.
TEST_WEBHOOK_SECRET = "whsec_MfKQ9r8GKYqrTwjUPD8ILPZIo2LaLaSw"
os.environ["RECALL_WEBHOOK_SECRET"] = TEST_WEBHOOK_SECRET
os.environ["RECALL_API_KEY"] = "test-recall-api-key"
os.environ["RECALL_API_BASE"] = "https://us-west-2.recall.ai"
os.environ["PUBLIC_BASE_URL"] = "https://recall-api.example.test"

from datetime import UTC, datetime  # noqa: E402

import pytest  # noqa: E402  The import must come after the lines above.
from fastapi.testclient import TestClient  # noqa: E402
from svix.webhooks import Webhook  # noqa: E402

from app.db import session_store  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(autouse=True)
def empty_database() -> None:
    """Give each test an empty sessions table."""
    TEST_DB_PATH.unlink(missing_ok=True)
    session_store.init_db()


def signed_headers(body: bytes, secret: str = TEST_WEBHOOK_SECRET) -> dict[str, str]:
    """Sign a body the way Recall signs it. The tests thus use the real check."""
    message_id = "msg_test_00000001"
    timestamp = datetime.now(tz=UTC)
    signature = Webhook(secret).sign(message_id, timestamp, body.decode())
    return {
        "webhook-id": message_id,
        "webhook-timestamp": str(int(timestamp.timestamp())),
        "webhook-signature": signature,
        "content-type": "application/json",
    }


@pytest.fixture
def client() -> Iterator[TestClient]:
    """Give a test client. The `with` block runs the lifespan of the application."""
    with TestClient(app) as test_client:
        yield test_client
