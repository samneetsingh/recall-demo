# Task 5a — The bot leaves when the intake is complete: todo

Written in ASD-STE100 Simplified Technical English.

## Scope

The bot stays in the call after the intake ends. It says the closing line and then it
waits, silent, until the patient closes the call. The patient must remove it, or wait
for the automatic timeout. This task makes the bot leave by itself.

New work, found in session 10. Section 5a of [`../TASKS.md`](../TASKS.md).
**`backend/` only.** The frontend does not change.

## Answers from Sam

| Question | Answer |
|---|---|
| Build it | **Yes, in this session** |
| The wait between the closing line and the leave | **A short fixed delay, near 3 seconds.** One constant in `config.py`, so a live call can tune it with no code change |
| A session that goes to `error` | **No. The bot leaves only when the status is `complete`** |

## Verified before the plan

Method: the `recall-ai` MCP against the live documents.

- **`POST /api/v1/bot/{id}/leave_call/` removes the bot from the meeting.** `get_doc`
  for `bot_leave_call_create`. It is **irreversible**. The result is HTTP 200 with the
  bot object, or HTTP 400 with no body. The limit is 300 requests each minute for one
  workspace. There is no request body.
- **No endpoint ends a meeting for all participants.** The bot is an ordinary
  participant and not the host, and Google Meet gives that action to the host only. The
  bot can remove itself and nothing more.
- **The bot already leaves 2 seconds after the patient.**
  `automatic_leave.everyone_left_timeout` has the default 2 seconds, from
  `get_doc` for `automatic-leaving-behavior`. This task does not repair a bot that stays
  for ever. It makes the bot leave **at the end of the intake, while the patient is
  still there**, which is what a person expects.
- **The other timeouts are long.** `silence_detection` is 3600 seconds after a buffer of
  1200 seconds, and `in_call_not_recording_timeout` is 3600 seconds. A patient who keeps
  the call open sees the bot for one hour.
- **`bot.call_ended` after the intake is complete makes no change.** `apply_bot_event`
  has `AND status != 'complete'` in the same statement as the write. The event that this
  leave makes thus needs no new code, and the `complete` status cannot go backwards.

## New dependencies

**None.** `httpx` sends the request, and `_post` in `app/recall/client.py` already holds
the API key, the timeout, the error handling and the redaction.

## Decisions

- **The leave is not on the mode boundary.** `send_notice` went on the boundary in
  section 5, because *how* a notice reaches the patient is mode-specific: chat pins a
  message and voice will speak it. A leave is **not** mode-specific. It is one HTTP call
  to Recall, and voice mode makes the same call. A `leave()` method on `TurnMode` would
  be the same code two times.
- **`routes/webhooks.py` calls `recall/client.py` for it.** `../CLAUDE.md` and
  `../IMPLEMENTATION.md` permit this: "A route handler reads the request, calls into
  `engine/`, `recall/`, or `db/`". `routes/sessions.py` already calls `create_bot` in
  the same manner.
- **`engine/loop.py` does not send it.** The closing line is not a turn and
  `engine/loop.py` does not send it either. The leave is the same class of action: it is
  not part of the conversation, so it is not in the engine.
- **A failed leave is a log line and nothing more.** The summary is written and the
  status is `complete`. A bot that stays in the call is untidy and it costs no data. A
  failed leave must never change a `complete` session.

## Files

```
backend/
  app/
    config.py             edit  BOT_LEAVE_DELAY_SECONDS
    recall/
      client.py           edit  leave_call(bot_id)
    routes/
      webhooks.py         edit  _finish_intake: the closing line, the wait, the leave
  tests/
    test_recall_client.py edit  The leave call: the URL, the failures, the redaction
    test_routes_webhooks.py edit The wire: a complete intake leaves the call one time
docs/
  API_CONTRACT.md         edit  The leave endpoint
  API_REFERENCE.md        edit  What the backend does at the end of an intake
  FLOW.md                 edit  Flow C, and part 9
  TASKS.md                edit  Section 5a
  task-05a-bot-leave/todo.md    new
  session-logs/10-frontend.md   edit  Part 2 of this session
```

**`app/engine/intake.py`, `summary.py`, `prompts.py` and `loop.py` get no change.**
`app/modes/` gets no change, because the leave is not on the boundary. `frontend/` gets
no change: the page stops its poll at `complete` and it never learns about the bot.

## Procedure — the Recall call

- [x] `leave_call(bot_id: str) -> None` in `app/recall/client.py`, next to
      `send_chat_message`.
- [x] It is `_post(f"/api/v1/bot/{bot_id}/leave_call/", {})`. The endpoint takes no
      body, and `_post` gives the API key, the timeout, the HTTP 400 test and the
      redaction of the key.
- [x] It gives `None`. The answer holds the bot object, and this backend does not use it.
- [x] Write a log line with the bot id. A bot that left is the end of a session, and the
      container log must show it.
- [x] Write in a comment that the call is **irreversible**. A reader must not think that
      the bot can come back.

## Procedure — the wire

- [x] `BOT_LEAVE_DELAY_SECONDS: float = 3.0` in `app/config.py`, with a comment that
      gives the reason: Recall accepted the closing line, and the bot has still to type
      it into the meeting.
- [x] `_send_closing_message` becomes `_finish_intake(session_id, mode)`. It keeps its
      guard, which is that the status is `complete` now, sends the closing line, and
      then takes the bot out of the call.
- [x] The leave is a second private function, `_leave_call(session)`. It gives nothing
      for a session with no `bot_id`.
- [x] The wait is `time.sleep(settings.BOT_LEAVE_DELAY_SECONDS)`, and a delay of 0
      makes no call to `sleep`. The handler runs after the answer to Recall, so the wait
      costs no time in the request. **A test sets the delay to 0.**
- [x] A `RecallError` from the leave gives a log line. The status stays `complete`.
- [x] The guard of `_run_chat_turn` does not change: it reads the status from **before**
      the turn, so a message that arrives after the intake makes no second closing line
      and no second leave.

## Procedure — the tests

The tests use no network. Each Recall call is a fake.

- [x] **`leave_call` goes in the `offline` fixture of `tests/test_routes_webhooks.py`.**
      That fixture fakes `ask_model` and `send_chat_message` today. A route that gains a
      caller makes a test file that was offline go online. This is lesson 3 of
      `../../tasks/lessons.md`, and it is the fault that this file had in session 09.
- [x] `tests/test_recall_client.py`:
  - `leave_call` uses `POST /api/v1/bot/{id}/leave_call/` and the `Authorization` header;
  - the body is empty;
  - an HTTP 400 raises `RecallError`, and the message holds no API key;
  - no API key raises before a request;
  - a network error raises `RecallError`.
- [x] `tests/test_routes_webhooks.py`:
  - a complete intake sends the closing line **and then** leaves the call, in that
    order, one time;
  - an intake that is not complete does not leave the call;
  - a message that arrives after the intake makes no second leave;
  - a `RecallError` from the leave keeps the status `complete` and keeps the summary;
  - a session with no `bot_id` does not raise;
  - a session that goes to `error` does not leave the call. Sam selected this.
- [x] Run the full suite with each socket refused, with the plugin of lesson 3.
      `poetry run pytest -q -p block_network`.

## Procedure — the proof

- [x] The full suite passes. It is 250 tests now.
- [x] No test uses the network.
- [x] `git diff --stat -- backend/app/engine/ backend/app/modes/ frontend/` gives no line.
- [ ] **A live Google Meet call.** The intake runs to the end, the closing line arrives
      in the chat, **and the bot then leaves the call by itself.** `get_bot_logs` gives
      the `leave_call` request after the closing message, and `get_bot` gives the status
      `done`.
- [ ] The page still shows the summary after the bot leaves. The page stops its poll at
      `complete`, so this must be true, and a call proves it.
- [ ] **The delay is correct.** Read the Meet chat in the live call: the closing line
      must be visible before the bot goes. If it is cut, make
      `BOT_LEAVE_DELAY_SECONDS` larger. This is the one value that a test cannot prove.

## Out of scope

- **A leave on the status `error`.** Sam selected this. An error usually means that the
  bot cannot take a command, so the leave would fail as well.
- **An end of the meeting for all participants.** Recall has no such endpoint, and the
  bot is not the host.
- **A change to `automatic_leave` in the create-bot body.** The defaults operate, and
  this task does not need them.
- **Voice mode.** The leave is mode-neutral, so section 6 gets it at no cost.
- **A commit or a push**, unless Sam asks.

## At the end

- [x] Check the completed boxes in this file.
- [x] Add section 5a to `../TASKS.md` and mark what passes.
- [x] Update flow C and part 9 of `../FLOW.md`.
- [x] Add the endpoint to `../API_CONTRACT.md` and the end-of-intake behavior to
      `../API_REFERENCE.md`.
- [x] Add part 2 to `../session-logs/10-frontend.md`. It is the same session.
