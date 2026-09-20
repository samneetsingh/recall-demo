# 05 — The Recall connection

Written in ASD-STE100 Simplified Technical English.

- **Date:** 2026-09-20
- **Task:** Section 2 of [`../TASKS.md`](../TASKS.md), items 2e and 2h. Step 2 of the
  build order in [`../IMPLEMENTATION.md`](../IMPLEMENTATION.md)
- **Result:** complete — `POST /sessions` makes a Recall bot, and
  `POST /webhooks/recall` verifies the signature and maps the bot events to the session
  status. No live bot joined a call. Sam decided this.

## Summary

The session made `app/recall/client.py` with the create-bot call, `app/recall/events.py`
with the signature check and the event parser, and `app/routes/webhooks.py` with the
route and the status map. `POST /sessions` now makes the bot and keeps the bot id. The
tests went from 18 to 66. The session did not change `frontend/`, and it did not deploy
to the homelab server.

## Files changed

| File | Change | Reason |
|---|---|---|
| `backend/app/recall/__init__.py` | new | The package |
| `backend/app/recall/client.py` | new | The create-bot call, `RecallError` and the key redaction |
| `backend/app/recall/events.py` | new | The signature check, `RecallEvent`, `SignatureError`, `PayloadError` |
| `backend/app/routes/webhooks.py` | new | `POST /webhooks/recall` and the status map |
| `backend/app/routes/sessions.py` | edit | The create-bot call and the bad path |
| `backend/app/db/session_store.py` | edit | `set_bot_id` and `get_session_by_bot_id` |
| `backend/app/config.py` | edit | Five new settings |
| `backend/app/main.py` | edit | The webhook router, and the root logger level |
| `backend/.env.example` | edit | The five new names |
| `backend/pyproject.toml` | edit | `svix` in main, `httpx` from dev to main |
| `backend/poetry.lock` | edit | Poetry wrote it |
| `backend/tests/conftest.py` | edit | The fake secret, the fake key, and `signed_headers` |
| `backend/tests/test_recall_client.py` | new | 9 tests of the create-bot call |
| `backend/tests/test_recall_events.py` | new | 12 tests of the check and the parser |
| `backend/tests/test_routes_webhooks.py` | new | 20 tests of the route and the map |
| `backend/tests/test_session_store.py` | edit | 4 tests of the two new helpers |
| `backend/tests/test_routes_sessions.py` | edit | The good path and the bad path |
| `docs/API_CONTRACT.md` | edit | The region, and how the verification operates |
| `docs/API_REFERENCE.md` | edit | The new `POST /sessions` status, and the webhook map |
| `docs/TASKS.md` | edit | Items 2e and 2h |
| `docs/task-02-recall-connection/todo.md` | new | The plan of this session |
| `docs/session-logs/05-recall-connection.md` | new | This log |
| `tasks/lessons.md` | new | The first lesson |

`backend/Dockerfile` and `backend/deploy/docker-compose.yml` did not change. The
`Dockerfile` copies the full `app` directory, so the new modules need no change to it.

## Decisions

Sam made the first seven decisions in this session. A later session must not make them
again.

- **The region is `us-west-2`, the pay-as-you-go region.** The setting
  `RECALL_API_BASE` holds the host. A key from another region gives HTTP 401.
- **The client is plain HTTP with `httpx`. This project has no Recall SDK.** The build
  calls two endpoints: create bot now, and send chat message in section 5.
- **The verification uses the `svix` package.** It is a main dependency.
- **There was no live bot test in this session.** The first real bot join goes with the
  chat loop of section 5, when the bot has something to say.
- **Sam makes the dashboard webhook endpoint in the Recall dashboard.**
- **Sam puts the workspace verification secret in `backend/.env`.** The name is
  `RECALL_WEBHOOK_SECRET`. No secret is in a transcript or a commit.
- **An empty `RECALL_WEBHOOK_SECRET` refuses every webhook request with HTTP 401.** The
  backend fails closed. The container stays healthy, and only `/webhooks/recall` refuses.
- **`bot.call_ended` before the intake is complete makes the status `error`, with the
  reason `call_ended:<sub_code>`.** Two sentences of `../API_CONTRACT.md` did not agree.
  The session has no summary, and `error` is the only terminal status that is not
  `complete`. The prefix shows that the call ended in a normal manner and that the bot
  did not fail to join. A status that is `complete` does not change.
- **`POST /sessions` gives HTTP 201 with the status `error` when Recall refuses the
  bot.** The session resource exists, so 201 is correct. The body shape does not change,
  and the frontend reads the reason from its poll.
- **One `recording_config` serves both modes.** It has `transcript.data` and
  `participant_events.chat_message` together. Chat mode does not read the transcript, but
  a second shape must be kept correct and gives nothing.
- **`create_bot` sends `metadata: {"session_id": ...}`.** Recall shows it in the
  dashboard and in the bot logs, which makes a failed bot easy to find. The webhook route
  does not read it: it finds the session with the bot id.
- **The create-bot call is synchronous, in the request.** The frontend gets a true status
  in the first answer. The handler stays thin.
- **`bot.done` makes no status change.** It always comes after `bot.call_ended` or
  `bot.fatal`, which set the status.
- **The `sub_code` is a plain string.** There is no enum of sub-codes. An unknown value
  goes in the `error_reason` column and does not stop the application.
- **The webhook route uses `BackgroundTasks`.** The work now is one SQLite write, but the
  chat loop of section 5 calls an LLM and takes seconds. A failure in the work is
  invisible to Recall, so it must be in the log.

## Verified facts

- **The 66 tests pass.** Method: `poetry run pytest -q` in `backend/`. The result is
  `66 passed`. Session 04 had 18.
- **The container builds and becomes healthy.** Method:
  `docker compose -f deploy/docker-compose.yml up -d --build`, then a loop on
  `docker inspect --format '{{.State.Health.Status}}' recall-api`. The result is
  `Up 6 seconds (healthy)`.
- **`GET /health` gives HTTP 200 and `{"status":"ok"}`.** Method:
  `docker exec recall-api curl -i -s http://localhost:8000/health`.
- **The CORS behavior did not change.** Method: `docker exec recall-api curl -i -s -H
  'Origin: ...'`. The origin `https://recall.samneet.com` gives
  `access-control-allow-origin: https://recall.samneet.com` and `vary: Origin`. The
  origin `https://evil.example.com` gives HTTP 200 with no
  `access-control-allow-origin` header. The preflight for `POST /sessions` gives
  `access-control-allow-methods: GET, POST, OPTIONS`.
- **`svix` and `httpx` are in the image, and `pytest` is not.** Method:
  `docker exec recall-api python -c "import svix, httpx"` is successful.
  `import pytest` gives `ModuleNotFoundError`.
- **The bad path operates against the live Recall API.** Method: a second container
  `recall-api-proof`, from the same image, with `RECALL_API_KEY=a-deliberately-bad-api-key`.
  `POST /sessions` gives HTTP 201 and `{"session_id":"...","status":"error"}`.
  `GET /sessions/{id}` gives the `error_reason`
  `recall http 401: {"code":"authentication_failed","detail":"Invalid API token. ..."}`.
  The result is not HTTP 500. The key is not in the message.
- **The webhook route refuses a bad signature.** Method: a signed body with the
  signature changed to `v1,AAAA...`. The result is HTTP 401 and
  `{"detail":"bad signature"}`. The log line is
  `refused a webhook request: No matching signature found`. `GET /sessions/{id}` shows
  the same status as before the request.
- **The route does not read a refused payload.** Method: the test
  `test_a_bad_signature_does_not_read_the_body` patches `json.loads` in
  `app/recall/events.py` to raise. A bad signature gives `SignatureError`, and
  `json.loads` is not called.
- **`bot.fatal` makes the status `error` with the sub-code.** Method: a signed payload
  to the proof container. `GET /sessions/{id}` gives `"status":"error"` and
  `"error_reason":"meeting_link_invalid"`.
- **`bot.in_call_recording` makes the status `in_progress`.** Method: a signed payload.
  `GET /sessions/{id}` gives `"status":"in_progress"` and a null `error_reason`.
- **An unknown sub-code operates.** Method: a signed `bot.fatal` with the sub-code
  `a_sub_code_from_next_year`. The result is HTTP 200, and the value is in the
  `error_reason` column.
- **`bot.call_ended` obeys the rule.** Method: two signed payloads. With the status
  `in_progress`, the result is `"error"` and `"call_ended:call_ended_by_host"`. With the
  status `complete`, the status stays `complete` and the log says
  `session ... is complete, event bot.call_ended makes no change`.
- **A real-time event gives HTTP 200 and no status change.** Method: a signed
  `participant_events.chat_message`. The log says
  `real-time event participant_events.chat_message for bot bot-proof-001`.
- **The named volume kept the data through the rebuild.** Method:
  `docker exec recall-api python -c "... SELECT count(*) FROM sessions"` gives 2, the
  rows of session 04. `docker volume ls --filter name=recall-api` shows
  `recall-api_db-data`.
- **`svix` reads the `webhook-*` header names.** Method: the installed source
  `backend/.venv/.../svix/webhooks.py`. It maps `svix-id` or `webhook-id` to one name,
  and the same for the timestamp and the signature.
- **`standardwebhooks` refuses a timestamp more than 5 minutes from now.** Method: the
  installed source `standardwebhooks/webhooks.py`, the function `__verify_timestamp`.
- **The real workspace verification secret operates.** Sam put the secret in
  `backend/.env` at the end of this session. Method:
  `docker compose -f deploy/docker-compose.yml up -d` to recreate the container, then
  `docker exec recall-api python -c "from app.config import settings; ..."` gives a
  70 character value with the prefix `whsec_`. A payload signed with the secret from
  `backend/.env` gives HTTP 200: `bot.in_call_recording` makes the status
  `in_progress`, and `bot.fatal` makes the status `error` with the `error_reason`
  `meeting_link_invalid`. The secret was not written to a terminal at any time.
- **The deployed backend on the homelab accepts a webhook that Recall signed.** Sam
  deployed at the end of this session. Method: `recall-ai` MCP,
  `send_test_webhook_endpoint` for the endpoint `ep_3JZumFBubz7xBTnyeUonK4U1MfH` with
  the event `bot.done`, message `msg_3JZykC3VSu08pFCG5KUPpJ0kBxP`. The container log on
  the server gives `POST /webhooks/recall HTTP/1.1" 200 OK` and
  `no rule for event bot.done, no change`. This proves the full path: Recall, Cloudflare,
  the tunnel, nginx, FastAPI and the signature check with the workspace secret.
- **A request signed with the workspace secret is accepted over the live URL.** Method:
  a `curl` command to `https://recall-api.ss-ubuntu-01.net/webhooks/recall` with a
  signature made from the secret in `backend/.env`. The result is HTTP 200 and
  `{"ok":true}`. An unsigned request to the same URL gives HTTP 401 and
  `{"detail":"bad signature"}`.
- **A real Google Meet call proved the full connection.** Method: `POST /sessions` on
  the live URL with the meeting `https://meet.google.com/sfm-eepj-mjg`. The result is
  HTTP 201 and `waiting_for_bot`. Sam admitted the bot. The session then went to
  `in_progress`, and at the end of the call to `error` with the `error_reason`
  `call_ended:timeout_exceeded_everyone_left`. The bot id is
  `92627318-0bee-4ddc-89e7-8cf484724b18`, and its `metadata` holds the session id.
- **Each bot status webhook was delivered and accepted.** Method: `recall-ai` MCP,
  `list_webhook_deliveries` for the bot. The events `bot.joining_call`,
  `bot.in_waiting_room`, `bot.in_call_not_recording` and `bot.in_call_recording` each
  give `delivery_status: success`, `response_status_code: 200` and the body
  `{"ok":true}`. The times are 132 ms to 153 ms.
- **The real-time endpoint delivers the chat messages.** Method: a chat message in the
  meeting. The container log on the server gives
  `real-time event participant_events.chat_message for bot 92627318-...`. This path is
  the `realtime_endpoints` object of the create-bot request, not the dashboard endpoint.
- **Recall delivers the bot status events out of order.** Method: the `attempted_at`
  times from `list_webhook_deliveries`. The four events were made in 48 ms. Recall
  attempted `bot.in_waiting_room` at `.556` and `bot.joining_call` at `.612`, which is
  the opposite of the order the events were made in. The handler is last-write-wins, so
  an event that arrives late can put an old status on the session. This run was correct
  because the two first events map to the same status and `bot.in_call_recording` came
  last. See the open items.
- **The old test secret is refused by the container.** Method: a payload signed with
  `whsec_MfKQ9r8...`, the fake secret of `tests/conftest.py`, gives HTTP 401. This
  proves that the container uses the real secret and not a default. A changed signature
  also gives HTTP 401, and the session does not change after either refused request.

## Corrections

- **Wrong:** `svix.webhooks.Webhook.verify` gives the parsed payload, so the code does
  not need `json.loads`. **Correct:** `svix` 2.5.0 gives `None`. It calls
  `standardwebhooks` with `json_parse=False`. `app/recall/events.py` calls `json.loads`
  itself, after the check. A test patches `json.loads` to prove the order.
- **Wrong:** the message of `RecallError` is safe, because Recall does not echo the API
  key. **Correct:** the message holds the body of the answer, and a body can hold the
  key. The `error_reason` column is shown to the user. `client.py` now has a `_redact`
  function, and a test proves it.
- **Wrong:** a `logger.info` line in a route is in the container log. **Correct:**
  uvicorn configures its own loggers only, and the root logger stays at WARNING. The
  first proof run showed a correct status change with no log line. `app/main.py` now
  calls `logging.basicConfig(level=logging.INFO)`.
- **Wrong:** `docker run` gives a health status, because the image has a healthcheck.
  **Correct:** the healthcheck is in `deploy/docker-compose.yml`, not in the
  `Dockerfile`. A container from `docker run` has no `.State.Health` key, and a loop on
  it does not stop. Use a loop on `curl` for a container that compose did not start.
- **Wrong:** a test can patch `httpx.Client` with a function that calls `httpx.Client`.
  **Correct:** the function then calls itself. `tests/test_recall_client.py` keeps the
  real class in `REAL_CLIENT` before the patch.

## Open items

- [ ] Commit and push the changes of this session. Owner: Sam.
- [x] `RECALL_WEBHOOK_SECRET` in `backend/.env`. Owner: Sam. **Done at the end of this
      session.** The local container accepts a signed payload and refuses the old test
      secret. The secret is not on the homelab server yet.
- [x] The dashboard webhook endpoint. Owner: Sam. **Done at the end of this session.**
      The id is `ep_3JZumFBubz7xBTnyeUonK4U1MfH`, the URL is
      `https://recall-api.ss-ubuntu-01.net/webhooks/recall`, and `active` is true. It has
      the 9 necessary `bot.*` events and the 4 `bot.breakout_room_*` events. The 4 extra
      events do no harm: the handler has no rule for them, so it writes a log line and
      makes no change. Method: `recall-ai` MCP, `list_webhook_endpoints`.
- [ ] A test session row is in the live database, with the bot id `bot-live-001` and
      the status `error`. It comes from the proof of the real secret. It is demo data
      and it does no harm. `session_store` has no delete helper.
- [x] `backend/.env` on the homelab server, and a new deploy. Owner: Sam. **Done at the
      end of this session.** The stack is at `~/docker/recall-demo/backend` on
      `ss-ubuntu-01`. `GET /health` gives HTTP 200, an unsigned POST to
      `/webhooks/recall` gives HTTP 401, and a signed POST gives HTTP 200. The server
      has its own empty `recall-api_db-data` volume.
- [x] A live test with a real Google Meet call. **Done at the end of this session.**
      The bot joined, the status went to `in_progress`, a chat message arrived, and the
      end of the call gave `error` with `call_ended:timeout_exceeded_everyone_left`. The
      bot said nothing, because the intake engine of section 3 does not exist.
- [x] **The webhook handler is last-write-wins, and Recall delivers out of order.**
      Session 06 fixed this. See `../task-02-event-ordering/todo.md`.
- [ ] Starlette says that `httpx` with `TestClient` is deprecated, and it tells you to
      install `httpx2`. The 66 tests pass with a warning only. `httpx` is a main
      dependency now, because `client.py` uses it. Owner: the next session that touches
      the tests.

## Next session starts here

Do section 3 of [`../TASKS.md`](../TASKS.md): the mock intake engine. It needs no Recall
call, and it is testable with a scripted conversation.

1. Make `app/engine/prompts.py` with all the prompt text. No prompt text in another
   module.
2. Make `app/engine/intake.py`. It takes the conversation log and gives the next
   question or a signal that the intake is complete.
3. Make `app/engine/summary.py`. It takes the log and gives the eight fields of
   `../SPEC.md`.
4. LiteLLM is a new dependency. Flag it to Sam and wait for the answer.
5. Test the engine standalone, with no Recall and no webhook.

Do not change `frontend/` in the same turn as a `backend/` task. Ask Sam before a deploy
to the homelab server.
