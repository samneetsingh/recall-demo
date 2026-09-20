"""The tests of the session routes and the health route."""

from fastapi.testclient import TestClient

from app.db import session_store
from app.routes.sessions import STUB_SUMMARY

MEETING_URL = "https://meet.google.com/abc-defg-hij"


def test_health_gives_ok(client: TestClient) -> None:
    result = client.get("/health")

    assert result.status_code == 200
    assert result.json() == {"status": "ok"}


def test_post_sessions_makes_a_session(client: TestClient) -> None:
    result = client.post("/sessions", json={"meeting_url": MEETING_URL})

    assert result.status_code == 201
    body = result.json()
    assert body["status"] == "creating_bot"
    assert session_store.get_session(body["session_id"]) is not None


def test_post_sessions_refuses_a_bad_mode(client: TestClient) -> None:
    result = client.post(
        "/sessions",
        json={"meeting_url": MEETING_URL, "mode": "telepathy"},
    )

    assert result.status_code == 422


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
        "status": "creating_bot",
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
    assert "creating_bot" in result.json()["detail"]


def test_get_summary_gives_the_stub_when_no_engine_wrote_one(
    client: TestClient,
) -> None:
    session_id = client.post("/sessions", json={"meeting_url": MEETING_URL}).json()[
        "session_id"
    ]
    session_store.set_status(session_id, "complete")

    result = client.get(f"/sessions/{session_id}/summary")

    assert result.status_code == 200
    assert result.json() == STUB_SUMMARY


def test_get_summary_gives_the_stored_summary(client: TestClient) -> None:
    session_id = client.post("/sessions", json={"meeting_url": MEETING_URL}).json()[
        "session_id"
    ]
    session_store.set_summary(session_id, {"chief_complaint": "headache"})
    session_store.set_status(session_id, "complete")

    result = client.get(f"/sessions/{session_id}/summary")

    assert result.status_code == 200
    assert result.json() == {"chief_complaint": "headache"}
