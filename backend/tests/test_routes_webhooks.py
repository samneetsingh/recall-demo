"""The tests of POST /webhooks/recall and the map from an event to a status."""

import itertools
import json

import pytest
from fastapi.testclient import TestClient

from app.db import session_store
from tests.conftest import signed_headers

BOT_ID = "bot-abc"
MEETING_URL = "https://meet.google.com/abc-defg-hij"


@pytest.fixture
def session_id() -> str:
    """Make a session with a bot id, the state after `POST /sessions`."""
    session = session_store.create_session(MEETING_URL)
    session_store.set_bot_id(session.id, BOT_ID)
    session_store.set_status(session.id, "waiting_for_bot")
    return session.id


def _post(client: TestClient, payload: dict):
    body = json.dumps(payload).encode()
    return client.post("/webhooks/recall", content=body, headers=signed_headers(body))


def _bot_event(name: str, sub_code: str | None = None, bot_id: str = BOT_ID) -> dict:
    data: dict = {"bot": {"id": bot_id, "metadata": {}}}
    if sub_code is not None:
        data["data"] = {"code": name.split(".")[-1], "sub_code": sub_code}
    return {"event": name, "data": data}


def test_a_bad_signature_gives_401(client: TestClient) -> None:
    body = json.dumps(_bot_event("bot.fatal", "meeting_link_invalid")).encode()
    headers = signed_headers(body)
    headers["webhook-signature"] = "v1,AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="

    result = client.post("/webhooks/recall", content=body, headers=headers)

    assert result.status_code == 401


def test_no_signature_headers_give_401(client: TestClient) -> None:
    result = client.post("/webhooks/recall", json=_bot_event("bot.fatal"))

    assert result.status_code == 401


def test_a_bad_signature_does_not_change_the_session(
    client: TestClient, session_id: str
) -> None:
    body = json.dumps(_bot_event("bot.fatal", "meeting_link_invalid")).encode()
    headers = signed_headers(body)
    headers["webhook-signature"] = "v1,AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="

    client.post("/webhooks/recall", content=body, headers=headers)

    session = session_store.get_session(session_id)
    assert session is not None
    assert session.status == "waiting_for_bot"


def test_a_signed_body_that_is_not_an_event_gives_400(client: TestClient) -> None:
    body = json.dumps({"data": {}}).encode()

    result = client.post("/webhooks/recall", content=body, headers=signed_headers(body))

    assert result.status_code == 400


def test_bot_fatal_gives_the_status_error_and_the_sub_code(
    client: TestClient, session_id: str
) -> None:
    result = _post(client, _bot_event("bot.fatal", "meeting_link_invalid"))

    assert result.status_code == 200
    session = session_store.get_session(session_id)
    assert session is not None
    assert session.status == "error"
    assert session.error_reason == "meeting_link_invalid"


def test_bot_in_call_recording_gives_in_progress(
    client: TestClient, session_id: str
) -> None:
    result = _post(client, _bot_event("bot.in_call_recording"))

    assert result.status_code == 200
    session = session_store.get_session(session_id)
    assert session is not None
    assert session.status == "in_progress"
    assert session.error_reason is None


@pytest.mark.parametrize(
    "name",
    [
        "bot.joining_call",
        "bot.in_waiting_room",
        "bot.in_call_not_recording",
        "bot.recording_permission_allowed",
    ],
)
def test_the_join_events_give_waiting_for_bot(
    client: TestClient, session_id: str, name: str
) -> None:
    session_store.set_status(session_id, "creating_bot")

    _post(client, _bot_event(name))

    session = session_store.get_session(session_id)
    assert session is not None
    assert session.status == "waiting_for_bot"


def test_recording_permission_denied_gives_error(
    client: TestClient, session_id: str
) -> None:
    _post(client, _bot_event("bot.recording_permission_denied", "permission_denied"))

    session = session_store.get_session(session_id)
    assert session is not None
    assert session.status == "error"
    assert session.error_reason == "permission_denied"


def test_an_unknown_sub_code_goes_in_the_column(
    client: TestClient, session_id: str
) -> None:
    """Recall adds sub-codes. A new value must not stop the application."""
    _post(client, _bot_event("bot.fatal", "a_sub_code_from_next_year"))

    session = session_store.get_session(session_id)
    assert session is not None
    assert session.status == "error"
    assert session.error_reason == "a_sub_code_from_next_year"


def test_call_ended_before_the_intake_gives_error_with_a_prefix(
    client: TestClient, session_id: str
) -> None:
    session_store.set_status(session_id, "in_progress")

    _post(client, _bot_event("bot.call_ended", "call_ended_by_host"))

    session = session_store.get_session(session_id)
    assert session is not None
    assert session.status == "error"
    assert session.error_reason == "call_ended:call_ended_by_host"


def test_call_ended_after_complete_makes_no_change(
    client: TestClient, session_id: str
) -> None:
    session_store.set_status(session_id, "complete")

    result = _post(client, _bot_event("bot.call_ended", "call_ended_by_host"))

    assert result.status_code == 200
    session = session_store.get_session(session_id)
    assert session is not None
    assert session.status == "complete"
    assert session.error_reason is None


def test_bot_fatal_after_complete_makes_no_change(
    client: TestClient, session_id: str
) -> None:
    session_store.set_status(session_id, "complete")

    _post(client, _bot_event("bot.fatal", "bot_errored"))

    session = session_store.get_session(session_id)
    assert session is not None
    assert session.status == "complete"


def test_bot_done_makes_no_change(client: TestClient, session_id: str) -> None:
    session_store.set_status(session_id, "error", "meeting_link_invalid")

    result = _post(client, _bot_event("bot.done"))

    assert result.status_code == 200
    session = session_store.get_session(session_id)
    assert session is not None
    assert session.status == "error"
    assert session.error_reason == "meeting_link_invalid"


def test_an_unknown_event_name_gives_200_and_no_change(
    client: TestClient, session_id: str
) -> None:
    result = _post(client, _bot_event("bot.an_event_from_next_year"))

    assert result.status_code == 200
    session = session_store.get_session(session_id)
    assert session is not None
    assert session.status == "waiting_for_bot"


def test_an_unknown_bot_id_gives_200(client: TestClient, session_id: str) -> None:
    result = _post(client, _bot_event("bot.fatal", "bot_errored", bot_id="bot-other"))

    assert result.status_code == 200
    session = session_store.get_session(session_id)
    assert session is not None
    assert session.status == "waiting_for_bot"


@pytest.mark.parametrize(
    "name", ["participant_events.chat_message", "transcript.data"]
)
def test_a_realtime_event_gives_200_and_no_status_change(
    client: TestClient, session_id: str, name: str
) -> None:
    """The chat loop and the voice loop are later tasks."""
    result = _post(client, {"event": name, "data": {"bot": {"id": BOT_ID}}})

    assert result.status_code == 200
    session = session_store.get_session(session_id)
    assert session is not None
    assert session.status == "waiting_for_bot"


# The four events of the live test of session 05, with the times that Recall
# gave them. Recall sent them out of order: `bot.in_waiting_room` went out
# before `bot.joining_call`. See ../../docs/task-02-event-ordering/todo.md.
LIVE_EVENTS = [
    ("bot.joining_call", "2026-09-20T05:47:04.508000Z"),
    ("bot.in_waiting_room", "2026-09-20T05:47:04.524000Z"),
    ("bot.in_call_not_recording", "2026-09-20T05:47:04.532000Z"),
    ("bot.in_call_recording", "2026-09-20T05:47:04.556000Z"),
]


def _timed_event(name: str, updated_at: str | None, bot_id: str) -> dict:
    data: dict = {"bot": {"id": bot_id, "metadata": {}}}
    if updated_at is not None:
        data["data"] = {"code": name.split(".")[-1], "updated_at": updated_at}
    return {"event": name, "data": data}


def _session_with_bot(bot_id: str) -> str:
    session = session_store.create_session(MEETING_URL)
    session_store.set_bot_id(session.id, bot_id)
    session_store.set_status(session.id, "waiting_for_bot")
    return session.id


@pytest.mark.parametrize("order", list(itertools.permutations(LIVE_EVENTS)))
def test_every_order_of_the_live_events_ends_in_progress(
    client: TestClient, order: tuple
) -> None:
    """Recall has no delivery order. Each of the 24 orders must give the same end."""
    bot_id = f"bot-order-{abs(hash(order))}"
    session_id = _session_with_bot(bot_id)

    for name, updated_at in order:
        result = _post(client, _timed_event(name, updated_at, bot_id))
        assert result.status_code == 200

    session = session_store.get_session(session_id)
    assert session is not None
    assert session.status == "in_progress", f"order {[n for n, _ in order]}"


def test_a_late_event_does_not_put_back_an_old_status(
    client: TestClient, session_id: str
) -> None:
    """The failure this task prevents: the bot is recording, the session is not."""
    _post(client, _timed_event("bot.in_call_recording", LIVE_EVENTS[3][1], BOT_ID))
    _post(client, _timed_event("bot.in_call_not_recording", LIVE_EVENTS[2][1], BOT_ID))

    session = session_store.get_session(session_id)
    assert session is not None
    assert session.status == "in_progress"


def test_the_same_event_two_times_changes_the_session_one_time(
    client: TestClient, session_id: str
) -> None:
    """Svix delivers at least one time, so a duplicate is normal."""
    payload = _timed_event("bot.in_call_recording", LIVE_EVENTS[3][1], BOT_ID)

    assert _post(client, payload).status_code == 200
    first = session_store.get_session(session_id)
    assert _post(client, payload).status_code == 200
    second = session_store.get_session(session_id)

    assert first is not None and second is not None
    assert first.status == second.status == "in_progress"
    assert first.updated_at == second.updated_at


def test_an_event_with_no_time_is_applied(client: TestClient, session_id: str) -> None:
    """The test webhook of the dashboard has no `data.data`. Do not lose a true event."""
    result = _post(client, _timed_event("bot.in_call_recording", None, BOT_ID))

    assert result.status_code == 200
    session = session_store.get_session(session_id)
    assert session is not None
    assert session.status == "in_progress"
    assert session.last_event_at is None


def test_an_event_with_no_time_keeps_the_last_time(
    client: TestClient, session_id: str
) -> None:
    _post(client, _timed_event("bot.in_call_recording", LIVE_EVENTS[3][1], BOT_ID))
    before = session_store.get_session(session_id)

    _post(client, _timed_event("bot.in_call_not_recording", None, BOT_ID))
    after = session_store.get_session(session_id)

    assert before is not None and after is not None
    assert after.last_event_at == before.last_event_at


def test_an_old_event_does_not_change_a_complete_session(
    client: TestClient, session_id: str
) -> None:
    session_store.set_status(session_id, "complete")

    _post(client, _timed_event("bot.in_call_recording", LIVE_EVENTS[3][1], BOT_ID))

    session = session_store.get_session(session_id)
    assert session is not None
    assert session.status == "complete"


def test_the_event_time_is_stored_in_one_format(
    client: TestClient, session_id: str
) -> None:
    _post(client, _timed_event("bot.in_call_recording", LIVE_EVENTS[3][1], BOT_ID))

    session = session_store.get_session(session_id)
    assert session is not None
    assert session.last_event_at == "2026-09-20T05:47:04.556000+00:00"
