# Task 2, part 2 — The Recall connection: todo

Written in ASD-STE100 Simplified Technical English.

## Scope

This task does step 2 of the build order in [`../IMPLEMENTATION.md`](../IMPLEMENTATION.md):
the create-bot call, and the webhook route that receives the bot status events.

- 2e. `POST /sessions` makes a Recall bot and keeps the bot id.
- 2h. `POST /webhooks/recall`, with a signature check.
- The map from a bot event to the session status.

At the end of this task, the backend can make a bot and can follow the bot through the
call. The bot says nothing and hears nothing. The chat loop is section 5 of
[`../TASKS.md`](../TASKS.md), and the intake engine is section 3.

## Start state

A check on 2026-09-19 gave these results:

| Item | Result | Effect on this task |
|---|---|---|
| `backend/app/recall/` | The directory does not exist | Item 1 makes the package |
| `backend/app/routes/webhooks.py` | The file does not exist | Item 5 makes it |
| `backend/app/main.py` | A comment shows the place for the webhook router | Item 7 puts the two lines there |
| `backend/app/routes/sessions.py` | A comment shows the place for the create-bot call | Item 3 puts the call there |
| `backend/app/db/session_store.py` | The column `bot_id` has no helper | Item 2 makes two helpers |
| `backend/.env` | `RECALL_API_KEY` and `OPENAI_API_KEY` only | Sam adds `RECALL_WEBHOOK_SECRET` |
| `httpx` | In `[dependency-groups]`, the group `dev` | It moves to the main group |
| `svix` | Not in the lock file | A new main dependency |
| The tests | 18 tests pass | This task adds more |
| The container `recall-api` | `Up (healthy)` | A rebuild proves the new code |
| `list_webhook_endpoints` | An empty list | Sam makes the endpoint in the dashboard |

## Answers from Sam

These answers are decisions. A later session must not make them again.

- **The region is `us-west-2`, the pay-as-you-go region.** The host is
  `https://us-west-2.recall.ai`. The API key is specific to the region.
- **The client is plain HTTP with `httpx`. There is no Recall SDK in this project.**
  The build calls two endpoints only: create bot now, and send chat message in section 5.
- **The verification uses the `svix` package.** It is a new main dependency.
- **There is no live bot test in this session.** The proof uses pytest, the container and
  synthetic webhook payloads. The first real bot join goes with the chat loop of
  section 5.
- **Sam makes the dashboard webhook endpoint in the Recall dashboard.** The URL is
  `https://recall-api.ss-ubuntu-01.net/webhooks/recall`. This is not a condition for this
  session.
- **Sam puts the workspace verification secret in `backend/.env`.** The name is
  `RECALL_WEBHOOK_SECRET`. No secret goes into a transcript or a commit. The tests use a
  fake secret.
- **An empty `RECALL_WEBHOOK_SECRET` refuses every webhook request with HTTP 401.** The
  backend fails closed. The container stays healthy, and only `/webhooks/recall` refuses.

## New dependencies

Sam approved this list in this session.

| Package | Group | Reason |
|---|---|---|
| `svix` | main | **New.** `svix.webhooks.Webhook.verify` does the signature check |
| `httpx` | dev to main | The create-bot call. The image needs it now |

Two facts about `svix`:

- `svix` depends on `standardwebhooks` and on `httpx`. The image gets these packages too.
- `Webhook.verify` reads `svix-id` or `webhook-id`, and the same for the timestamp and
  the signature. Recall sends the `webhook-*` names. No header change is necessary.
  Method: the source file `python/svix/webhooks.py` in `svix/svix-webhooks`.

LiteLLM, the OpenAI client and the TTS code are not part of this task.

## New settings

`app/config.py` gets five fields. Each one has a default, so the application starts
without `backend/.env`.

| Name | Default | Use |
|---|---|---|
| `RECALL_API_BASE` | `https://us-west-2.recall.ai` | The region host |
| `RECALL_WEBHOOK_SECRET` | `""` | The `whsec_...` workspace secret. Empty refuses all webhooks |
| `PUBLIC_BASE_URL` | `https://recall-api.ss-ubuntu-01.net` | Makes the `realtime_endpoints` URL |
| `RECALL_BOT_NAME` | `FIRY Intake Assistant` | The name of the bot in the meeting |
| `RECALL_TIMEOUT_SECONDS` | `30.0` | The timeout of the create-bot request |

The three CORS aliases at the end of `config.py` do not change.

## The map from an event to the status — Sam must look at this

Two configurations send events to the same route. The event sets do not intersect.

### The bot status events, from the dashboard endpoint

| Event | New status | `error_reason` |
|---|---|---|
| `bot.joining_call` | `waiting_for_bot` | none |
| `bot.in_waiting_room` | `waiting_for_bot` | none |
| `bot.in_call_not_recording` | `waiting_for_bot` | none |
| `bot.recording_permission_allowed` | `waiting_for_bot` | none |
| `bot.recording_permission_denied` | `error` | the `sub_code` |
| `bot.in_call_recording` | `in_progress` | none |
| `bot.call_ended` | see the note | the `sub_code` |
| `bot.done` | no change | none |
| `bot.fatal` | `error` | the `sub_code` |

Rules for the table:

- The `sub_code` is a plain string in the `error_reason` column. It is not an enum.
  Recall adds values, and a value that the code does not know must not stop the
  application.
- A status that is `complete` does not change. `complete` is the end state.
- `bot.done` makes no change. It always comes after `bot.call_ended` or `bot.fatal`,
  which set the status. Two writes of the same fact give no benefit.
- An event with an unknown name makes no change. The route gives 200 and writes a log
  line.

### The note on `bot.call_ended` — a question for Sam

[`../API_CONTRACT.md`](../API_CONTRACT.md) has two sentences that do not agree:

1. "These `bot.call_ended` sub-codes are normal, not an error. Do not make the status
   `error` for them."
2. "A demo that ends before the intake is complete must make the status `complete` or
   `error` with the sub-code as the reason."

The session must get a terminal status, because the frontend polls and must stop. The
state machine in `../IMPLEMENTATION.md` has two end states only: `complete` and `error`.

**The plan uses this rule:**

- `bot.call_ended` and the status is `complete`: no change.
- `bot.call_ended` and the status is not `complete`: the status becomes `error`, and
  the `error_reason` becomes `call_ended:<sub_code>`.

The reason: the call stopped before the intake was complete, so the session has no
summary. `error` is the only terminal status that is not `complete`. The prefix
`call_ended:` lets the frontend and a person see that the call ended in a normal manner,
and that the bot did not fail to join. Sentence 1 stays true, because the sub-code is not
the cause of an error. The session is in `error` because it has no summary.

Sam approved this rule in this session.

The old text: tell me if you want a different rule. The other option is a sixth status, for
example `ended_early`, but that changes the state machine, the frontend and
`../API_REFERENCE.md`.

### The real-time events, from `recording_config.realtime_endpoints`

| Event | This task | Later |
|---|---|---|
| `participant_events.chat_message` | The parser gives the event. No status change. A log line | Section 5, the chat loop |
| `transcript.data` | The parser gives the event. No status change. A log line | Section 6, voice mode |

## Files

```
backend/
  pyproject.toml              edit  svix in main, httpx from dev to main
  poetry.lock                 edit  Poetry makes this
  .env.example                edit  The five new names
  app/
    config.py                 edit  The five new fields
    main.py                   edit  The webhook router, at the comment
    recall/
      __init__.py             new
      client.py               new   The create-bot call, and nothing else
      events.py               new   The signature check and the typed event
    routes/
      sessions.py             edit  The create-bot call, at the comment
      webhooks.py             new   POST /webhooks/recall
    db/
      session_store.py        edit  set_bot_id and get_session_by_bot_id
  tests/
    conftest.py               edit  A fake secret and a fake API key
    test_recall_client.py     new   The request body and the errors
    test_recall_events.py     new   The signature check and the parser
    test_routes_webhooks.py   new   The route, the 401 and the status map
    test_session_store.py     edit  The two new helpers
    test_routes_sessions.py   edit  The good path and the bad path
```

`app/engine/`, `app/tts/` and `frontend/` do not change.

## Procedure — the dependencies

- [x] Run `poetry add svix` in `backend/`.
- [x] Run `poetry add httpx` to move it to the main group. Remove it from the `dev`
      group in `[dependency-groups]`, because a package must be in one group only.
- [x] Poetry 2.3.3 writes a development dependency to `[dependency-groups]`, not to
      `[tool.poetry.group.dev.dependencies]`. Do not look for the old table.
- [x] Check that `poetry install --only main` puts `svix` and `httpx` in the image, and
      that it keeps `pytest` out.

## Procedure — the settings

- [x] Add the five fields of the table above to the `Settings` class in `app/config.py`.
- [x] Give each field a default, so the application starts with no `backend/.env`.
- [x] Do not change the three CORS aliases at the end of the module.
- [x] Add the five names to `.env.example`, with an example value and a short comment.
      Do not put a real secret in the file.

## Procedure — `app/recall/client.py`

- [x] Make `app/recall/__init__.py`.
- [x] Make `app/recall/client.py`. It holds the create-bot call, and nothing else. The
      send-chat-message call is section 5.
- [x] Make one exception class, `RecallError`. It holds a short reason string for the
      `error_reason` column.
- [x] Write `create_bot(meeting_url, session_id, mode) -> str`. It gives the bot id.
- [x] The request is `POST {RECALL_API_BASE}/api/v1/bot/`, with the header
      `Authorization: Token {RECALL_API_KEY}`.
- [x] Use bot schema v1.11. Do not copy a v1.10 example.
- [x] The body:

```json
{
  "meeting_url": "<the meeting URL>",
  "bot_name": "FIRY Intake Assistant",
  "metadata": { "session_id": "<the session id>" },
  "recording_config": {
    "participant_events": {},
    "transcript": {
      "provider": {
        "recallai_streaming": { "mode": "prioritize_low_latency", "language_code": "en" }
      }
    },
    "realtime_endpoints": [
      {
        "type": "webhook",
        "url": "<PUBLIC_BASE_URL>/webhooks/recall",
        "events": ["participant_events.chat_message", "transcript.data"]
      }
    ]
  }
}
```

- [x] The fields `url` and `events` are at the top level of the endpoint object. The text
      of the document says a `config` object, but each example shows the flat shape.
      [`../API_CONTRACT.md`](../API_CONTRACT.md) shows the flat shape.
- [x] `metadata` holds the session id. Recall shows it in the dashboard and in the bot
      logs, which makes a failed bot easy to find. The webhook route does not use it: it
      finds the session with the bot id.
- [x] Both modes use the same body. `chat` does not need the transcript, but two bodies
      give two things to maintain and no benefit.
- [x] Make the request with `httpx.Client`, with the timeout `RECALL_TIMEOUT_SECONDS`.
      The route handler is synchronous, so the client is synchronous.
- [x] Raise `RecallError` with a short reason for each failure:
      - No `RECALL_API_KEY`: `"no Recall API key"`. Do not send a request.
      - HTTP 4xx or 5xx: `"recall http <code>: <the first 200 characters of the body>"`.
      - A timeout or a network error: `"recall request failed: <the class name>"`.
- [x] Never put the API key in an exception message or in a log line.

## Procedure — `app/recall/events.py`

- [x] Make `app/recall/events.py`. It does the signature check, and it makes a typed
      internal event.
- [x] Make two exception classes: `SignatureError` and `PayloadError`.
- [x] Make a frozen dataclass `RecallEvent` with these fields: `name`, `bot_id`,
      `sub_code` and `payload`. `payload` is the full object, for the handlers of
      section 5 and section 6.
- [x] Write `verify_and_parse(raw_body: bytes, headers: Mapping[str, str]) -> RecallEvent`.
- [x] **The check comes first.** The function does these steps in this order:
      1. If `RECALL_WEBHOOK_SECRET` is empty, raise `SignatureError`. Do not read the
         body.
      2. Call `svix.webhooks.Webhook(secret).verify(raw_body, headers)`. A
         `WebhookVerificationError` becomes a `SignatureError`. Do not read the body.
      3. Only after step 2 is successful, read the fields of the payload.
- [x] `svix` 2.5.0 `Webhook.verify` gives `None`, not the payload. It calls
      `standardwebhooks` with `json_parse=False`. The module thus calls `json.loads`
      itself, on the line after the check. A comment says that the order is a rule.
      `standardwebhooks` has a 5 minute timestamp tolerance, so no extra check is
      necessary. Method: the installed source in `backend/.venv`.
- [x] Read `event` for the name, `data.bot.id` for the bot id and `data.data.sub_code`
      for the sub-code. Each one is optional, except the name.
- [x] A payload with no `event` field raises `PayloadError`.
- [x] Do not make the `sub_code` an enum. It stays a string.
- [x] This module does not touch the database and does not know about the session status.
      The map is in the route.

## Procedure — `app/db/session_store.py`

- [x] Add `set_bot_id(session_id, bot_id) -> Session | None`. It writes the column
      `bot_id` and `updated_at`.
- [x] Add `get_session_by_bot_id(bot_id) -> Session | None`. The webhook route needs it,
      because a Recall event carries the bot id and not the session id.
- [x] Keep all query SQL in this file.

## Procedure — `app/routes/sessions.py`

- [x] Put the create-bot call at the comment in `create_session`.
- [x] The good path: call `recall.client.create_bot`, then `session_store.set_bot_id`,
      then `session_store.set_status(session.id, "waiting_for_bot")`.
- [x] The bad path: a `RecallError` sets the status to `error` with the reason from the
      exception. The route gives HTTP 201, not HTTP 500. The session row exists, and the
      frontend reads the reason from `GET /sessions/{id}`.
- [x] The response body does not change: `session_id` and `status`. The status is now
      `waiting_for_bot` or `error`, not `creating_bot`.
      [`../API_REFERENCE.md`](../API_REFERENCE.md) gets this change.
- [x] The call is synchronous, in the request. It takes approximately one second. The
      frontend gets a true status in the first response, which is better than a poll to
      find a failure. The handler stays thin: two calls and no logic.

## Procedure — `app/routes/webhooks.py`

- [x] Make `app/routes/webhooks.py` with an `APIRouter`.
- [x] `POST /webhooks/recall` reads the raw body with `await request.body()`. The
      signature is over the raw bytes, so the handler must be `async def` and must not
      let FastAPI parse the body first.
- [x] Call `events.verify_and_parse`. A `SignatureError` gives HTTP 401. A `PayloadError`
      gives HTTP 400.
- [x] After a successful check, put the work in a `BackgroundTasks` object and give
      HTTP 200 and `{"ok": true}` immediately. Recall sends the events in sequence with a
      15 second timeout, so a slow handler delays the next event. The work now is one
      SQLite write, but the chat loop of section 5 calls an LLM and takes seconds.
- [x] Write the map of the table above in one dictionary in this module, plus the rule
      for `bot.call_ended`.
- [x] The handler finds the session with `get_session_by_bot_id`. An unknown bot id
      writes a log line and stops. The route gave 200 before this, so Recall does not
      retry.
- [x] An event that is not in the map writes a log line and makes no change.
- [x] The two real-time events write a log line only. Section 5 and section 6 add the
      logic.
- [x] Keep the handler thin. It calls `session_store`, and it has no SQL in it.

## Procedure — `app/main.py`

- [x] Put these two lines at the comment:
      `from app.routes import webhooks` and `app.include_router(webhooks.router)`.
- [x] Remove the comment that says the next task adds the router.
- [x] Do not change the `from app.config import ...` line.

## Procedure — the tests

- [x] `tests/conftest.py`: set `RECALL_WEBHOOK_SECRET` to a fake `whsec_...` value and
      `RECALL_API_KEY` to a fake value, before the import of the application.
      `app.config` reads the environment one time, at its import.
- [x] Make a helper in `tests/` that signs a body with the fake secret. Use
      `svix.webhooks.Webhook.sign`. The tests thus prove the real check, not a mock of it.
- [x] `test_recall_client.py`: the request body has the correct shape and the correct
      URL; an empty API key raises before a request; HTTP 400 and HTTP 401 raise
      `RecallError`; the reason has no API key in it. Use a `httpx.MockTransport`.
- [x] `test_recall_events.py`: a good signature gives the event; a bad signature raises
      `SignatureError`; an empty secret raises `SignatureError`; a changed body raises
      `SignatureError`; a `bot.fatal` payload gives the sub-code; a payload with no
      `event` raises `PayloadError`; an unknown sub-code stays a string.
- [x] `test_routes_webhooks.py`: a bad signature gives HTTP 401; `bot.fatal` makes the
      status `error` with the sub-code; `bot.in_call_recording` makes the status
      `in_progress`; `bot.call_ended` after `complete` makes no change; an unknown bot id
      gives HTTP 200; an unknown event name gives HTTP 200 and no change.
- [x] `test_session_store.py`: `set_bot_id` writes the column; `get_session_by_bot_id`
      finds the row and gives `None` for an unknown bot id.
- [x] `test_routes_sessions.py`: the good path gives the status `waiting_for_bot` and
      writes the bot id; the bad path gives HTTP 201 with the status `error` and a reason.
      Patch `app.recall.client.create_bot` for both.
- [x] Run `poetry run pytest`. All tests must pass, the 18 tests of session 04 too.

## Proof

Each step is a command with a result. `../session-logs/05-recall-connection.md` gives
each result.

- [x] `poetry run pytest` in `backend/` passes.
- [x] `docker compose -f deploy/docker-compose.yml up -d --build` makes the image.
- [x] `docker inspect --format '{{.State.Health.Status}}' recall-api` gives `healthy`.
      Read the value in a loop with an interval. Do not read it in the same second as the
      start.
- [x] Each `curl` command runs in the container, because the compose file does not
      publish port 8000: `docker exec recall-api curl -i http://localhost:8000/...`.
      Use `curl -i`. Do not use `curl -I`, because it sends HEAD and FastAPI gives 405.
- [x] `GET /health` gives HTTP 200 and `{"status": "ok"}`.
- [x] The CORS behavior is the same: the origin `https://recall.samneet.com` gives the
      header `access-control-allow-origin`, and an origin that is not in the list does
      not.
- [x] The bad path: `POST /sessions` with a bad `RECALL_API_KEY` gives HTTP 201 and the
      status `error`. `GET /sessions/{id}` shows the reason in `error_reason`. The
      response is not HTTP 500.
- [x] The webhook route refuses a request with a bad signature: HTTP 401. The log shows
      that the payload was not read.
- [x] A signed `bot.fatal` payload makes the status `error` and puts the sub-code in
      `error_reason`.
- [x] A signed `bot.in_call_recording` payload makes the status `in_progress`.
- [x] `docker exec recall-api python -c "import svix, httpx"` is successful, and
      `import pytest` gives `ModuleNotFoundError`.

## Done criteria

- [x] `app/recall/client.py` has the create-bot call, and nothing else.
- [x] `app/recall/events.py` does the check before it reads the payload.
- [x] `POST /sessions` makes a bot, keeps the bot id and sets the status. A failure gives
      `error` with a reason, not HTTP 500.
- [x] `POST /webhooks/recall` answers 2xx immediately and maps the bot events to the
      status.
- [x] The `sub_code` is a string in `error_reason`. There is no enum of sub-codes.
- [x] All SQL is in `app/db/session_store.py`.
- [x] The container is healthy, and the CORS behavior is the same as task 1.
- [x] The tests pass.
- [x] Items 2e and 2h of section 2 of `../TASKS.md` show as complete.
- [x] The session log `../session-logs/05-recall-connection.md` is complete.

## Out of scope

- A change to `frontend/`.
- The chat send and the chat receive logic. Section 5 of `../TASKS.md`.
- The intake engine, the prompts, LiteLLM and the TTS code.
- The output audio call and the silence timer. Section 6.
- A migrations framework. `CLAUDE.md` refuses one for this demo.
- A deploy to the homelab server. Sam must approve a deploy first.
- A live bot in a real Google Meet call. Sam decided this in this session.
- A commit and a push. The changes stay in the working tree for Sam.


## What changed against the plan

- **`svix` 2.5.0 `verify` gives `None`, not the payload.** The plan said the opposite.
  `app/recall/events.py` calls `json.loads` itself, on the line after the check. A test
  patches `json.loads` to prove that a refused body never reaches it.
- **`app/recall/client.py` got a `_redact` function.** A test showed that the message of
  `RecallError` holds the body of the answer from Recall, and the body can hold the API
  key. The `error_reason` column is shown to the user, so the key must never reach it.
- **`app/main.py` got one line: `logging.basicConfig(level=logging.INFO)`.** uvicorn
  configures its own loggers only, so the root logger stayed at WARNING. The webhook
  handler runs after the response, and its result was not in the container log. The
  first proof run showed a correct status change with no log line.
- **The proof used a second container.** The container `recall-api` has the real API key
  in `backend/.env`, and `POST /sessions` now makes a real bot. A throwaway container
  `recall-api-proof` with a bad key and a test secret gave the bad path and the webhook
  proofs, with no bot and no change to the named volume.
