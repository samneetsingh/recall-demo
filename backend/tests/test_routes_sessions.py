"""The tests of the session routes and the health route."""

import pytest
from fastapi.testclient import TestClient

from app.db import session_store
from app.recall.client import RecallError
from app.engine import prompts
from app.routes import sessions as sessions_route

MEETING_URL = "https://meet.google.com/abc-defg-hij"
FAKE_BOT_ID = "bot-test-0001"


@pytest.fixture(autouse=True)
def fake_bot(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make `POST /sessions` succeed with no call to Recall."""
    monkeypatch.setattr(
        sessions_route.recall_client,
        "create_bot",
        lambda meeting_url, session_id, mode="chat": FAKE_BOT_ID,
    )


def test_health_gives_ok(client: TestClient) -> None:
    result = client.get("/health")

    assert result.status_code == 200
    assert result.json() == {"status": "ok"}


def test_post_sessions_makes_a_session(client: TestClient) -> None:
    result = client.post("/sessions", json={"meeting_url": MEETING_URL})

    assert result.status_code == 201
    body = result.json()
    assert body["status"] == "waiting_for_bot"
    session = session_store.get_session(body["session_id"])
    assert session is not None
    assert session.bot_id == FAKE_BOT_ID
    assert session.error_reason is None


def test_post_sessions_refuses_a_bad_mode(client: TestClient) -> None:
    result = client.post(
        "/sessions",
        json={"meeting_url": MEETING_URL, "mode": "telepathy"},
    )

    assert result.status_code == 422


def test_post_sessions_refuses_a_mode_with_no_implementation(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A bot that the backend cannot use must never reach a real meeting."""

    def refuse(meeting_url: str, session_id: str, mode: str = "chat") -> str:
        raise AssertionError("the route made a bot for a mode it cannot serve")

    monkeypatch.setattr(sessions_route.recall_client, "create_bot", refuse)

    result = client.post(
        "/sessions",
        json={"meeting_url": MEETING_URL, "mode": "voice"},
    )

    assert result.status_code == 400
    assert "voice" in result.json()["detail"]


def test_post_sessions_refuses_a_bad_url(client: TestClient) -> None:
    result = client.post("/sessions", json={"meeting_url": "not-a-url"})

    assert result.status_code == 422


def test_get_session_gives_the_status(client: TestClient) -> None:
    session_id = client.post("/sessions", json={"meeting_url": MEETING_URL}).json()[
        "session_id"
    ]

    result = client.get(f"/sessions/{session_id}")

    assert result.status_code == 200
    assert result.json() == {
        "session_id": session_id,
        "status": "waiting_for_bot",
        "summary": None,
        "error_reason": None,
    }


def test_get_session_gives_404_for_an_unknown_id(client: TestClient) -> None:
    assert client.get("/sessions/no-such-id").status_code == 404


def test_get_summary_gives_404_before_the_session_is_complete(
    client: TestClient,
) -> None:
    session_id = client.post("/sessions", json={"meeting_url": MEETING_URL}).json()[
        "session_id"
    ]

    result = client.get(f"/sessions/{session_id}/summary")

    assert result.status_code == 404
    assert "waiting_for_bot" in result.json()["detail"]


def test_get_summary_gives_500_when_a_complete_session_has_no_summary(
    client: TestClient,
) -> None:
    """`engine/loop.py` writes the summary first, so this is a fault to show."""
    session_id = client.post("/sessions", json={"meeting_url": MEETING_URL}).json()[
        "session_id"
    ]
    session_store.set_status(session_id, "complete")

    result = client.get(f"/sessions/{session_id}/summary")

    assert result.status_code == 500


def test_get_summary_gives_the_summary_of_the_engine(client: TestClient) -> None:
    session_id = client.post("/sessions", json={"meeting_url": MEETING_URL}).json()[
        "session_id"
    ]
    summary = {field: f"the {field}" for field in prompts.SUMMARY_FIELDS}
    session_store.set_summary(session_id, summary)
    session_store.set_status(session_id, "complete")

    result = client.get(f"/sessions/{session_id}/summary")

    assert result.status_code == 200
    assert result.json() == summary
    assert tuple(result.json()) == prompts.SUMMARY_FIELDS


def test_a_failed_bot_gives_201_and_the_status_error(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A bad API key must not give HTTP 500. The session keeps the reason."""

    def fail(meeting_url: str, session_id: str, mode: str = "chat") -> str:
        raise RecallError("recall http 401: invalid token")

    monkeypatch.setattr(sessions_route.recall_client, "create_bot", fail)

    result = client.post("/sessions", json={"meeting_url": MEETING_URL})

    assert result.status_code == 201
    body = result.json()
    assert body["status"] == "error"

    status = client.get(f"/sessions/{body['session_id']}").json()
    assert status["status"] == "error"
    assert status["error_reason"] == "recall http 401: invalid token"


def test_a_failed_bot_keeps_the_bot_id_empty(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(meeting_url: str, session_id: str, mode: str = "chat") -> str:
        raise RecallError("no Recall API key")

    monkeypatch.setattr(sessions_route.recall_client, "create_bot", fail)

    session_id = client.post("/sessions", json={"meeting_url": MEETING_URL}).json()[
        "session_id"
    ]
    session = session_store.get_session(session_id)

    assert session is not None
    assert session.bot_id is None
