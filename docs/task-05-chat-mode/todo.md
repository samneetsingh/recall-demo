# Task 5 — Chat mode: todo

Written in ASD-STE100 Simplified Technical English.

## Scope

The engine, the state machine and the turns table are built and tested, and **no
production code calls them**. This task adds one implementation of the turn boundary and
connects the webhook to it. It closes the two gaps of [`../FLOW.md`](../FLOW.md) flow C.

Section 5 of [`../TASKS.md`](../TASKS.md). `backend/` only.

## The two gaps

1. `MODES` in `app/modes/base.py` is empty, so `get_mode` raises `ModeError`.
2. `app/routes/webhooks.py` writes a log line for `participant_events.chat_message` and
   returns. Nothing calls `loop.run_turn` and nothing calls `loop.start_intake`.

## Answers from Sam

| Question | Answer |
|---|---|
| A live Google Meet call | **Yes, at the end.** Each other item is proved with no network first |
| A question of more than 500 characters | **Split it over two chat messages.** Google Meet refuses a longer message |
| The greeting | **A pinned notice, then the first question.** The `chat.on_bot_join` hook of the create-bot request sends the consent notice of `../SPEC.md` and pins it |
| The end of the intake | **A short closing line** in the chat |
| The bot's own messages | **Match the bot name.** A message whose `participant.name` is `RECALL_BOT_NAME` is not a patient turn |
| A deploy to the homelab server | **Sam deploys.** This session changes the code only |

## Verified before the plan

Method: the `recall-ai` MCP against the live workspace, and the Recall documents.

- **The true shape of the chat event.** `get_doc` for `real-time-event-payloads`. The
  text is at `data.data.data.text`, and the sender is at
  `data.data.participant.name`:

```json
{
  "event": "participant_events.chat_message",
  "data": {
    "data": {
      "participant": { "id": 100, "name": "Samneet Singh", "is_host": true,
                       "platform": "desktop", "extra_data": {}, "email": null },
      "timestamp": { "absolute": "2026-09-20T05:48:18.360372Z", "relative": 76.8 },
      "data": { "text": "I get bad headaches", "to": "everyone" }
    },
    "realtime_endpoint": { "id": "...", "metadata": {} },
    "participant_events": { "id": "...", "metadata": {} },
    "recording": { "id": "...", "metadata": {} },
    "bot": { "id": "92627318-0bee-4ddc-89e7-8cf484724b18", "metadata": {} }
  }
}
```

- **The payload has no "this is the bot" field.** The participant object gives `id`,
  `name`, `is_host`, `platform`, `extra_data` and `email`. The name is the only test
  that is available, which is why Sam selected it.
- **The live call of session 05 sent one chat message.** `get_bot` for
  `92627318-0bee-4ddc-89e7-8cf484724b18` gives the participant `Samneet Singh` with the
  events `join`, `chat_message` and `leave`. The bot itself sent no message in that
  call, so the echo is not yet proved against this workspace. The live call of **this**
  session proves it.
- **A real-time event is not a dashboard webhook.** `list_webhook_deliveries` for the
  bot gives the 4 `bot.*` messages only. The document `real-time-webhook-endpoints`
  says that real-time events are "not shown in the Webhooks console", and that they are
  dispatched directly to the URL of the create-bot request. The signature is the same
  workspace secret, which session 05 proved: the container accepted the chat event.
- **`POST /api/v1/bot/{id}/send_chat_message/`.** The body is `{"to": ..., "message": ...}`.
  `get_doc` for `sending-chat-messages`. Google Meet takes the recipient `everyone`
  only, it permits 500 characters, and it supports a pinned message.
- **The create-bot `chat` object.** `get_bot` gives the field `chat` on the bot, and
  `sending-chat-messages` gives its shape: `chat.on_bot_join` takes `send_to`, `message`
  and `pin`.
- **A pin on Google Meet has one condition.** The same document: "Pinned chat messages
  require continuous chat to be disabled." If the condition is not met, the message goes
  out and the pin does not. This is a setting of the Meet call, not of the code. **Sam
  must disable continuous chat in the live call**, or the notice is not pinned.

## New dependencies

**None.** `httpx` sends the create-bot request today, and it sends the chat message.

## Files

```
backend/
  app/
    recall/
      client.py           edit  send_chat_message(). CONSENT_NOTICE in the create-bot body
    modes/
      chat.py             new   ChatMode: parse an event, send a message, split at 500
      base.py             edit  One entry in MODES. CLOSING_MESSAGE
    routes/
      webhooks.py         edit  start_intake, run_turn, the closing line
  tests/
    test_modes_chat.py    new   The parser, the echo filter, the split, the send
    test_recall_client.py edit  send_chat_message, and the chat hook in the body
    test_routes_webhooks.py edit The wire: a signed chat event gives a question
  scripts/
    intake_console.py     edit  The comment that says that chat mode does not exist
docs/
  FLOW.md                 edit  Flow C, and part 9
  TASKS.md                edit  Section 5
  API_CONTRACT.md         edit  The create-bot body has the chat hook
  task-05-chat-mode/todo.md     new
  session-logs/09-chat-mode.md  new
```

**`app/engine/intake.py`, `summary.py`, `prompts.py` and `loop.py` get no change.** If
this task needs one, the boundary is wrong. Stop and say why. `git diff --stat` on
those four files must give nothing.

`frontend/`, the `Dockerfile`, the compose file, `pyproject.toml`, `poetry.lock` and
`app/db/` do not change.

## Procedure — the Recall send call

- [x] `send_chat_message(bot_id: str, text: str) -> None` in `app/recall/client.py`.
      `POST {RECALL_API_BASE}/api/v1/bot/{bot_id}/send_chat_message/` with the body
      `{"to": "everyone", "message": text}`.
- [x] Google Meet takes `everyone` only. Write this in a comment, because a reader will
      ask why the recipient is not a parameter.
- [x] Each failure raises `RecallError`, with the same rules as `create_bot`: no API key,
      a network error, and an HTTP status of 400 or more. The API key is redacted from
      each message with `_redact`.
- [x] Put the shared part of the two calls in one private function, `_post(path, body)`.
      The error handling, the redaction and the timeout are then written one time.
      `create_bot` reads the `id` from the answer, and `send_chat_message` does not.
- [x] `CONSENT_NOTICE` is a module constant next to `build_request_body`, because that
      function sends it. It identifies the assistant as an AI and not a physician, which
      is the one disclaimer that `../SPEC.md` permits. It is less than 500 characters.
- [x] `build_request_body` gets the chat hook:

```json
"chat": { "on_bot_join": { "send_to": "everyone", "message": CONSENT_NOTICE, "pin": true } }
```

## Procedure — chat mode

- [x] `app/modes/chat.py` holds the class `ChatMode`. It is the second implementation of
      the protocol in `base.py`, after `ConsoleMode` of `scripts/intake_console.py`.
- [x] `handle_incoming_turn(session_id, raw_event) -> str | None`. `raw_event` is the
      `RecallEvent` of `app/recall/events.py`. It gives `None`, and never an exception,
      for each event that is not a patient turn:
  - the event name is not `participant_events.chat_message`;
  - a level of the payload is absent or has the wrong type;
  - the text is empty after a strip;
  - **the sender is the bot itself.**
- [x] The echo filter compares `data.data.participant.name` with
      `settings.RECALL_BOT_NAME`, with no difference for the case and for the spaces at
      the two ends. The bot receives its own messages back, so without this filter the
      assistant interviews itself. Write this reason in a comment.
- [x] The filter catches each message that the bot sends: the pinned notice, the six
      questions and the closing line. A test of the text against the log would not catch
      the notice or the closing line, because those are not in the log. This is why Sam
      selected the name.
- [x] `send_outgoing_turn(session_id, text) -> None`. It reads the session, takes the
      `bot_id`, and calls `recall_client.send_chat_message` one time for each part of the
      text.
- [x] A session with no `bot_id`, and a `RecallError`, each raise `ModeError`.
      `engine/loop.py` catches `ModeError` and puts the session in `error` with the
      reason. A `RecallError` that is not converted goes past `_advance`, the session
      stays `in_progress`, and the conversation stops with no sign. Do not permit that.
- [x] `split_message(text, limit=500) -> list[str]` is a pure function in the same
      module. It cuts at the end of a sentence if it can, then at a space, and at the
      limit if it must. It never gives an empty part, and it never loses a character
      other than the space at a cut.
- [x] `MEET_CHAT_LIMIT = 500` is a constant with a comment that names Google Meet. The
      limit is a property of the platform, so it belongs in the mode and not in the
      engine.
- [x] Write a log line when a question goes out in more than one part. The engine gives
      two sentences, so this must be rare. Section 8a tunes the prompt; this task does
      not.

### The import order of `base.py` and `chat.py`

`base.py` must hold the entry in `MODES`, and `chat.py` must raise `ModeError`, which
`base.py` defines. A module-level import in the two directions is a cycle, and the
direction that fails depends on which module a test imports first.

- [x] `chat.py` imports `ModeError` **in the function that raises it**, with a one line
      comment that gives the reason. This is one line, it changes no public name, and it
      cannot fail in either direction.
- [ ] **Not selected.** The alternative was to move `ModeError` to
      `app/modes/__init__.py` and re-export it from `base.py`. Sam approved the plan as
      written, so the local import stays.

## Procedure — the registry

- [x] One entry in `app/modes/base.py`:

```python
MODES: dict[Mode, TurnMode] = {"chat": ChatMode()}
```

- [x] `ChatMode` holds no state, so one instance for the process is correct. Each request
      reads the database, which is where the state is.
- [x] `CLOSING_MESSAGE` goes in `base.py` and not in `chat.py`. The text says that the
      intake is complete and that the summary is on the page. It is mode-neutral: voice
      mode says the same words through TTS in section 6.

## Procedure — the wire

- [x] `handle_event` in `app/routes/webhooks.py` calls `loop.start_intake(session.id)`
      when `apply_bot_event` gives `True` **and** the new status is `in_progress`. The
      guard of `apply_bot_event` means that a repeated `bot.in_call_recording` does not
      arrive here two times, and `start_intake` has its own test of the log.
- [x] A chat message goes to a new private function, `_run_chat_turn(event)`, so
      `handle_event` stays short. The route stays thin: it maps an event to a call and it
      makes no decision about the conversation.
- [x] The order in that function: find the session by `bot_id`; get the mode with
      `get_mode(session.mode)`; call `handle_incoming_turn`; stop if the result is
      `None`; call `loop.run_turn(session.id, text, event.message_id)`.
- [x] **`event.message_id` is the `event_id`.** The unique index then refuses a repeated
      delivery, and `run_turn` stops. Do not add a second test.
- [x] Read the session again after `run_turn`. If the status is now `complete`, send
      `CLOSING_MESSAGE` with `send_outgoing_turn`. The closing line is not a turn, so it
      is not in the log. `engine/loop.py` writes the log, and this task does not change
      it.
- [x] `ModeError` from `get_mode` (a session with the mode `voice` today) puts the
      session in `error` with the reason. It must not raise in a background task, where
      the failure is invisible.
- [x] `transcript.data` keeps its log line. Section 6 gives it logic.
- [x] The handler runs after the answer to Recall, as it does today. Recall has a 15
      second timeout, and one turn makes two calls to the model.

## Procedure — the tests

The tests use no network. Each Recall call is a `httpx.MockTransport`, as
`tests/test_recall_client.py` does today, and each model call is a patched `ask_model`,
as `tests/test_engine_loop.py` does today.

- [x] `tests/test_modes_chat.py`:
  - the true payload of the document gives the text;
  - a message from the bot name gives `None`, with a different case and with spaces;
  - an empty text, a text of spaces, an absent `data`, an absent `participant` and a
    wrong event name each give `None` and raise nothing;
  - `send_outgoing_turn` sends `{"to": "everyone", "message": ...}` to
    `/api/v1/bot/{bot_id}/send_chat_message/`;
  - a session with no `bot_id` raises `ModeError`;
  - a `RecallError` becomes a `ModeError`;
  - `split_message` gives one part for a short text;
  - a text of more than 500 characters gives two parts, each of 500 or less, and the
    cut is at the end of a sentence;
  - a text with no sentence end and no space still gives parts of 500 or less;
  - a long question sends two messages, in order.
- [x] `tests/test_recall_client.py`:
  - `send_chat_message` uses the correct URL, body and `Authorization` header;
  - an HTTP 400 raises `RecallError`, and the message holds no API key;
  - no API key raises before a request;
  - a network error raises `RecallError`;
  - `build_request_body` has `chat.on_bot_join` with `send_to` `everyone`, `pin` true,
    and a message of 500 characters or less.
- [x] `tests/test_routes_webhooks.py`:
  - a signed `bot.in_call_recording` starts the intake, and the first question goes out;
  - a signed chat message gives one patient turn and one new question;
  - the same chat message two times gives one turn and one question (the `webhook-id`
    header is the `event_id`);
  - a chat message from the bot itself changes nothing;
  - a chat message for an unknown bot id gives HTTP 200 and no change;
  - a chat message for a session that is not `in_progress` changes nothing;
  - the last answer makes the summary, the status `complete`, and one closing message.
- [x] Each of the 195 tests must pass. `test_engine_intake.py`, `test_engine_summary.py`,
      `test_engine_prompts.py` and `test_engine_loop.py` must not need one change.

## Proof

- [x] `poetry run pytest` in `backend/` passes. The count is more than 195.
- [x] **Prove that the echo filter is necessary.** Method: remove the filter, then run the
      test of the bot's own message. It must fail, and the log must show a patient turn
      with the text of the question. Restore the filter.
- [x] **The engine modules are byte for byte the same.** Method:
      `git diff --stat backend/app/engine/`. It gives no line.
- [x] `docker compose -f deploy/docker-compose.yml up -d --build` in `backend/`, then a
      loop on `docker inspect --format '{{.State.Health.Status}}' recall-api` gives
      `healthy`. Do not read the value in the same second as the start.
- [x] `GET /health` gives HTTP 200, and the CORS behavior does not change. Method:
      `docker exec recall-api curl -i -s ...`. Use `curl -i`, not `curl -I`.
- [x] **A signed chat event against the container makes a question.** Method: make a
      session in the container, put its status at `in_progress`, and send a signed
      `participant_events.chat_message` with the true shape. The container calls the real
      model and tries the real Recall send. Read the turns table after it. The patient
      turn is in the log. The send fails with a `RecallError` for a bot that is not in a
      call, and the session then goes to `error` with that reason — **which is the proof
      that a failed send is not silent.**
- [ ] **The live Google Meet call.** Sam deploys first, then hosts the call. Sam must
      disable continuous chat if he wants the pinned notice. Read:
  - the notice arrives when the bot joins, and it is pinned;
  - the first question arrives with no answer from the patient;
  - each answer gives one new question, and the bot does not answer itself;
  - `GET /sessions/{id}` gives `complete`, and `GET /sessions/{id}/summary` gives the
    eight fields;
  - the closing line is the last message in the chat.
- [ ] **Read the true echo in that call.** The `webhook-id` header of a real-time event
      is not yet proved to stay the same for a retry. Recall retries a real-time message
      up to 60 times. If the header changes, the repeat protection does not operate, and
      that is a finding for the session log and for section 6.

## Done criteria

- [x] A chat message from the patient gives one turn and one new question.
- [x] The bot does not interview itself.
- [x] A repeated delivery makes no second turn and no second question.
- [x] A failed send puts the session in `error`. It is not silent.
- [x] A question of more than 500 characters goes out in two messages.
- [x] `intake.py`, `summary.py`, `prompts.py` and `loop.py` are byte for byte the same.
- [x] The tests pass and the container is healthy.
- [x] `../FLOW.md` flow C has no "NOT BUILT", and part 9 lists no unbuilt item for
      section 5.
- [x] `../session-logs/09-chat-mode.md` is complete.

## Out of scope

- The TTS code and the output audio. That is section 6.
- Prompt tuning. That is section 8a. A bad question from the live call goes in section
  8a, and `prompts.py` does not change.
- A change to `frontend/`.
- A queue for a refused patient message. It stays a known fault of `../FLOW.md` part 9.
- A retry of a turn that failed, and a timeout for a patient who stops answering.
- A deploy to the homelab server. Sam does it.
- A commit and a push.

## What changed against the plan

- **`base.py` imports `ChatMode` at the top, not at the end of the file.** The plan
  expected a cycle. There is none: `chat.py` imports `ModeError` inside the function
  that raises it, so `chat.py` has no module-level import of `base.py`. The import in
  `base.py` is thus in the normal position, and an import of either module first
  operates.
- **`app/recall/events.py` changed. The plan did not list it.** `_dig` is `dig` now,
  and `chat.py` reads the chat payload with it. The alternative was a copy of the same
  7 lines in two modules. The three call sites in `events.py` are the only other
  change, and no test used the name.
- **`tests/conftest.py` changed. The plan did not list it.** It holds
  `chat_payload()`, which is the true shape of the event, and `mock_httpx_client()`,
  which was a private helper of `test_recall_client.py`. Two test files use each one,
  and the true shape must have one copy. `signed_headers` also takes a `message_id`
  now, because a test of a repeated delivery needs two deliveries with one id, and a
  test of two turns needs two different ids.
- **`tests/test_engine_loop.py` changed. The plan said that it must not.** One test,
  `test_a_mode_with_no_implementation_puts_the_session_in_error`, was written against
  an empty registry. Chat is in the registry now, so the test uses the mode `voice`,
  which has no implementation until section 6. The intent of the test did not change.
  **The four engine modules are byte for byte the same**, which was the true rule.
- **`tests/test_routes_webhooks.py` needed an `offline` fixture, and this was a
  finding.** The route reaches the model and Recall now, so the first run of the suite
  sent a real request to `api.openai.com` and got HTTP 401. A test must not do this.
  The fixture puts a fake model and a fake send in place for each test in the file, and
  a new proof runs the full suite with each socket refused.
- **A fault of this task, found and repaired during the build: the closing line went
  out again for each message after the intake ended.** `_run_chat_turn` read the status
  after `run_turn` and sent the line each time it was `complete`. It reads the status
  from before the turn now, so the line goes out one time. A test holds it, and the
  test fails if the guard is removed.
- **`docs/API_REFERENCE.md` also changed.** The plan listed `API_CONTRACT.md` only.
  The webhook route does more than a status change now, and the "Extending this"
  section named a directory that does not hold a mode.
- **The tests went from 195 to 245.**
