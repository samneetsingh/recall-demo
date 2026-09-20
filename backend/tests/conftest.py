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
os.environ["OPENAI_API_KEY"] = "test-openai-api-key"
os.environ["OPENAI_MODEL"] = "gpt-4o-mini"

from datetime import UTC, datetime  # noqa: E402
from typing import Any  # noqa: E402

import httpx  # noqa: E402
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


def signed_headers(
    body: bytes,
    secret: str = TEST_WEBHOOK_SECRET,
    message_id: str = "msg_test_00000001",
) -> dict[str, str]:
    """Sign a body the way Recall signs it. The tests thus use the real check.

    `message_id` becomes the `webhook-id` header, which is the `event_id` of a
    turn. Two deliveries of one message have the same id.
    """
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


# The real class. The tests patch the name `httpx.Client`, so a helper that
# reads the name at call time would call itself.
REAL_HTTPX_CLIENT = httpx.Client


def mock_httpx_client(handler):
    """Give a fake `httpx.Client` that answers with the handler. No network."""

    def make_client(**kwargs):
        kwargs.pop("transport", None)
        return REAL_HTTPX_CLIENT(transport=httpx.MockTransport(handler), **kwargs)

    return make_client


def chat_payload(
    text: str = "I get bad headaches",
    sender: str | None = "Samneet Singh",
    bot_id: str = "bot-abc",
) -> dict[str, Any]:
    """Give the true shape of a `participant_events.chat_message` event.

    The shape is from the Recall document `real-time-event-payloads`. The text
    is at `data.data.data.text`, and the sender is at
    `data.data.participant.name`.
    """
    return {
        "event": "participant_events.chat_message",
        "data": {
            "data": {
                "participant": {
                    "id": 100,
                    "name": sender,
                    "is_host": True,
                    "platform": "desktop",
                    "extra_data": {"google_meet": {"static_participant_id": "abc="}},
                    "email": None,
                },
                "timestamp": {
                    "absolute": "2026-09-20T05:48:18.360372Z",
                    "relative": 76.805558,
                },
                "data": {"text": text, "to": "everyone"},
            },
            "realtime_endpoint": {"id": "b8ed2ca2", "metadata": {}},
            "participant_events": {"id": "pe-1", "metadata": {}},
            "recording": {"id": "6c1cb39d", "metadata": {}},
            "bot": {"id": bot_id, "metadata": {"session_id": "s1"}},
        },
    }


def transcript_payload(
    text: str = "I get bad headaches",
    speaker: str | None = "Samneet Singh",
    bot_id: str = "bot-abc",
    start: float = 10.0,
) -> dict[str, Any]:
    """Give the true shape of a `transcript.data` event.

    The shape is from the Recall document `real-time-event-payloads`, which
    renders it from a component; `agent-quickstarts` gives the same schema as
    text. **There is no sentence field.** The words are at `data.data.words`,
    each with its own `text`, and the speaker is at `data.data.participant`.
    """
    words = text.split()
    return {
        "event": "transcript.data",
        "data": {
            "data": {
                "words": [
                    {
                        "text": word,
                        "start_timestamp": {"relative": start + index * 0.4},
                        "end_timestamp": {"relative": start + index * 0.4 + 0.3},
                    }
                    for index, word in enumerate(words)
                ],
                "language_code": "en",
                "participant": {
                    "id": 100,
                    "name": speaker,
                    "is_host": True,
                    "platform": "desktop",
                    "extra_data": {"google_meet": {"static_participant_id": "abc="}},
                    "email": None,
                },
            },
            "realtime_endpoint": {"id": "b8ed2ca2", "metadata": {}},
            "transcript": {"id": "tr-1", "metadata": {}},
            "recording": {"id": "6c1cb39d", "metadata": {}},
            "bot": {"id": bot_id, "metadata": {"session_id": "s1"}},
        },
    }
