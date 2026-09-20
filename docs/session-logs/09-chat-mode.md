# 09 — Chat mode

Written in ASD-STE100 Simplified Technical English.

- **Date:** 2026-09-20
- **Task:** Section 5 of [`../TASKS.md`](../TASKS.md). See
  [`../task-05-chat-mode/todo.md`](../task-05-chat-mode/todo.md)
- **Result:** partial — chat mode is built, wired and proved with no network. The live
  Google Meet call is the one item that is open. The tests went from 195 to 245.

## Summary

The engine was complete and no production code called it. This session made
`app/modes/chat.py`, put it in the `MODES` registry, added `send_chat_message` to the
Recall client, and connected the webhook handler to `loop.start_intake` and
`loop.run_turn`. A signed chat event against the container now makes a patient turn, a
call to the model and a call to Recall. The four engine modules are byte for byte the
same, which is the test of the mode boundary of session 07, and it passed a second time.

## Files changed

| File | Change | Reason |
|---|---|---|
| `backend/app/modes/chat.py` | new | `ChatMode`: the parser, the echo filter, the 500 character split, the send |
| `backend/app/modes/base.py` | edit | One entry in `MODES`. `CLOSING_MESSAGE` |
| `backend/app/recall/client.py` | edit | `send_chat_message`, the shared `_post`, `CONSENT_NOTICE`, the `chat.on_bot_join` hook |
| `backend/app/recall/events.py` | edit | `_dig` is `dig` now. `chat.py` reads the payload with it |
| `backend/app/routes/webhooks.py` | edit | `start_intake`, `run_turn`, the closing line, `_session_of` |
| `backend/scripts/intake_console.py` | edit | The comment that said that chat mode does not exist |
| `backend/tests/test_modes_chat.py` | new | 30 tests: the parse, the echo, the split, the send |
| `backend/tests/conftest.py` | edit | `chat_payload`, `mock_httpx_client`, a `message_id` for `signed_headers` |
| `backend/tests/test_recall_client.py` | edit | 18 tests. The send call, and the chat hook of the body |
| `backend/tests/test_routes_webhooks.py` | edit | 63 tests. The `offline` fixture, and the chat wire |
| `backend/tests/test_engine_loop.py` | edit | One test now uses the mode `voice` for "no implementation" |
| `docs/FLOW.md` | edit | The header, flow B, flow C and part 9 |
| `docs/TASKS.md` | edit | Section 5, and two lines that went out of date |
| `docs/API_CONTRACT.md` | edit | The send endpoint, the chat hook and the true event shape |
| `docs/API_REFERENCE.md` | edit | What each event does, and how to add a mode |
| `docs/task-05-chat-mode/todo.md` | new | The plan of this session |
| `docs/session-logs/09-chat-mode.md` | new | This log |

`frontend/`, the `Dockerfile`, the compose file, `pyproject.toml`, `poetry.lock` and
`app/db/` did not change. **This session added no package.**
**`app/engine/intake.py`, `summary.py`, `prompts.py` and `loop.py` did not change.**

## Decisions

- **The echo filter is the sender name.** Sam selected it. The chat payload has no
  field that says "the bot sent this", so the name is the only test that is available.
  It catches each message that the bot sends: the pinned notice, the questions and the
  closing line. A test of the text against the log would catch the questions only,
  because the notice and the closing line are not in the log.
- **A long question goes out in two messages.** Sam selected it against a cut and
  against a refusal. `split_message` cuts at the end of a sentence, then at a space,
  and at the limit if it must. Google Meet refuses a message of more than 500
  characters, and the count is the guarantee, not the prompt.
- **The pinned consent notice goes through the create-bot hook, not through the send
  endpoint.** `chat.on_bot_join` sends it when the bot joins, so it is there before the
  first question, and Recall sends it without a call from this backend. **The pin needs
  continuous chat disabled in the Meet call.** If it is on, the message goes out and the
  pin does not.
- **A `RecallError` becomes a `ModeError` in the mode.** `engine/loop.py` catches
  `ModeError` and puts the session in `error` with the reason. A `RecallError` goes past
  that `except`, and the conversation then stops with no sign and with the status
  `in_progress`. The conversion is the one line that makes a failed send visible to the
  frontend.
- **`CLOSING_MESSAGE` is in `base.py` and not in `chat.py`.** The words are
  mode-neutral, so voice mode says the same line through TTS in section 6.
- **The closing line goes out through `send_outgoing_turn`.** It is not a turn, so
  `engine/loop.py` does not send it and it is not in the log. The route sends it after
  `run_turn`, and only if the session was not complete before the turn.
- **`create_bot` and `send_chat_message` share one `_post`.** The API key test, the
  timeout, the network error and the redaction are written one time. A second copy of
  that block is a second place to forget the redaction.
- **`chat.py` imports `ModeError` inside the function that raises it.** `base.py`
  imports `chat.py` to put it in the registry. A module-level import in both directions
  is a cycle that fails in one direction only, and which direction fails depends on
  which module a test imports first. The local import is one line, and it cannot fail.
- **The route calls `handle_incoming_turn`, and the loop does not.** This is the shape
  of flow C of `../FLOW.md` and of `../IMPLEMENTATION.md`: the mode turns an event into
  text, and the loop takes text only. The loop thus stays free of the webhook.

## Verified facts

- **The 245 tests pass.** Method: `poetry run pytest -q` in `backend/`. Session 08 had
  195.
- **No test uses the network.** Method: a pytest plugin that makes
  `socket.socket.connect`, `connect_ex` and `socket.create_connection` raise, then
  `poetry run pytest -q -p block_network`. The result is 245 passed. This check was
  necessary: the first run of the suite after the wire went in sent a real request to
  `api.openai.com` and got HTTP 401.
- **The four engine modules are byte for byte the same.** Method:
  `git diff --stat -- backend/app/engine/` gives no line.
- **The echo filter is necessary.** Method: remove the filter, then run the two tests of
  the bot's own message. Both fail, and the route test shows the damage: the log gains
  the row `{'role': 'patient', 'text': 'question 1'}`, which is the assistant answering
  itself. Restore the filter, and the tests pass.
- **The guard on the closing line is necessary.** Method: remove the test of the status
  before the turn, then run
  `test_a_message_after_the_intake_sends_no_second_closing_line`. It fails with a second
  copy of the closing line in the list of messages.
- **The container builds and becomes healthy.** Method:
  `docker compose -f deploy/docker-compose.yml up -d --build` in `backend/`, then a loop
  on `docker inspect --format '{{.State.Health.Status}}' recall-api`. The result is
  `Up 6 seconds (healthy)`.
- **`GET /health` gives HTTP 200, and the CORS behavior did not change.** Method:
  `docker exec recall-api curl -i -s`. The origin `https://recall.samneet.com` gives
  `access-control-allow-origin`, and an origin that is not in the list gives no such
  header.
- **A signed chat event against the container makes a turn, a question and a visible
  failure.** Method: a script in the container made a session with the bot of session 05
  and the status `in_progress`, then posted a signed
  `participant_events.chat_message` with the true payload shape to
  `http://localhost:8000/webhooks/recall`. The result is HTTP 200 `{"ok":true}`. The
  container log then gives, in order: the OpenAI call `HTTP/1.1 200 OK`,
  `model gpt-4o-mini answered for intake_turn`, the Recall send
  `POST /api/v1/bot/92627318-.../send_chat_message/ "HTTP/1.1 400 Bad Request"`, and
  `session ... failed: recall http 400: {"code":"cannot_command_unstarted_bot"}`. The
  session status is `error` with that reason, and the turns table holds the patient turn
  only. **This proves three things in one run: the signature and the parse operate, a
  failed send is not silent, and a question that the patient never got is not in the
  log.**
- **The real-time chat event is not in the dashboard webhook console.** Method:
  `list_webhook_deliveries` for the bot of session 05 gives the 4 `bot.*` messages and
  no chat message. The document `real-time-webhook-endpoints` says the same, and it
  gives the retry policy: 60 attempts, one each second.

## Corrections

- **Wrong:** `base.py` must import `chat.py` at the end of the file, because the two
  modules make a cycle. **Correct:** there is no cycle. `chat.py` imports `ModeError`
  inside the function that raises it, so the import in `base.py` is in the normal
  position at the top.
- **Wrong:** `test_engine_loop.py` does not need a change. **Correct:** one test,
  `test_a_mode_with_no_implementation_puts_the_session_in_error`, was written against an
  empty registry. It uses the mode `voice` now. The rule that matters is that the
  **engine modules** did not change, and they did not.
- **Wrong:** the closing line goes out when the status is `complete` after a turn.
  **Correct:** that sends the line again for each message that arrives after the intake
  ended. The route reads the status from before the turn now.

## Open items

- [ ] **The live Google Meet call.** Owner: Sam. Deploy first, then host a call. Read:
      the pinned notice when the bot joins, the first question, one question for each
      answer, no message from the bot to itself, the summary on
      `GET /sessions/{id}/summary`, and the closing line at the end. Disable continuous
      chat if you want the pin.
- [ ] **Is the `webhook-id` of a real-time retry the same each time?** The repeat
      protection of a chat turn is that header. Svix keeps the id for a dashboard event.
      Recall retries a real-time message with its own policy, and the document does not
      say what the id does. Read it in the live call. Owner: the live call, or section 6.
- [ ] Commit and push the changes of sessions 07, 08 and 09. Owner: Sam.
- [ ] Deploy to the homelab server. Owner: Sam. The server needs `OPENAI_API_KEY` in its
      `.env`.
- [ ] The five weak points of `../FLOW.md` part 9 go in the README as limitations.
      Owner: the docs pass of section 9.
- [ ] The prompts are not tuned. Section 8a. A question that reads badly in the live
      call goes in that section, not in `prompts.py` today. Owner: a later session.
- [ ] Starlette says that `httpx` with `TestClient` is deprecated. The 245 tests pass
      with the warning only. Owner: the next session that touches the tests.

## Next session starts here

Section 6 of [`../TASKS.md`](../TASKS.md): voice mode. It is a second class next to
`app/modes/chat.py`, and one more entry in `MODES`. Nothing above the boundary changes,
and chat mode must not change.

1. `app/tts/openai_tts.py` wraps the OpenAI TTS call.
2. `send_outgoing_turn` for voice: make the audio, then send it with the Recall output
   audio endpoint. The bot needs an `automatic_audio_output` configuration in the
   create-bot request. See `../API_CONTRACT.md`.
3. `handle_incoming_turn` for voice: buffer the `transcript.data` parts of one speaker,
   and give the text when no new part arrives for 2 to 3 seconds. The timer is state
   that is not in the database, which is new for this application. Plan where it lives
   before you write it.
4. `routes/webhooks.py` gives `transcript.data` to the mode. The `event_id` of a voice
   turn is not the message id of one part, because a turn is made of many parts. Decide
   what it is.

Do not start section 6 before the live call of section 5 passes.
