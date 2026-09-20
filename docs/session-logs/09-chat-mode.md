# 09 — Chat mode

Written in ASD-STE100 Simplified Technical English.

- **Date:** 2026-09-20
- **Task:** Section 5 of [`../TASKS.md`](../TASKS.md). See
  [`../task-05-chat-mode/todo.md`](../task-05-chat-mode/todo.md)
- **Result:** complete — chat mode is built, wired, deployed and proved in a live
  Google Meet call. The call found one fault of order, which this session then repaired.
  The tests went from 195 to 250.

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
| `backend/app/modes/base.py` | edit | One entry in `MODES`. `CLOSING_MESSAGE`, `CONSENT_NOTICE` and `send_notice` |
| `backend/app/recall/client.py` | edit | `send_chat_message` with `pin`, and the shared `_post` |
| `backend/app/recall/events.py` | edit | `_dig` is `dig` now. `chat.py` reads the payload with it |
| `backend/app/routes/webhooks.py` | edit | `_start_chat_intake`, `_run_chat_turn`, the closing line, `_session_of` |
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
- **After the live call: the backend sends the consent notice, not Recall.** The hook
  `chat.on_bot_join` put the notice after the first question, because Recall must send
  the message and then pin it, and this backend answers the `bot.in_call_recording`
  webhook in 1.74 seconds. Sam selected the exact order. The hook is out of the
  create-bot body, `send_chat_message` takes `pin`, and the route sends the notice
  immediately before `loop.start_intake`.
- **The boundary has a third method, `send_notice`.** The notice is not a turn, and it
  is not a question, but how it reaches the patient is mode-specific: chat mode pins a
  message, and voice mode will speak it. A `pin` parameter on `send_outgoing_turn` would
  put a Google Meet word in the protocol. The text, `CONSENT_NOTICE`, is in `base.py`
  next to `CLOSING_MESSAGE`, because both are mode-neutral.
- **A notice that fails does not stop the intake.** The route writes a log line and
  calls `start_intake`. If the meeting refuses each message, the first question fails in
  the same manner and `engine/loop.py` writes the reason on the session. A pin that
  Google Meet refuses must not cost the interview.
- **The route calls `handle_incoming_turn`, and the loop does not.** This is the shape
  of flow C of `../FLOW.md` and of `../IMPLEMENTATION.md`: the mode turns an event into
  text, and the loop takes text only. The loop thus stays free of the webhook.

## Verified facts

- **The 250 tests pass.** Method: `poetry run pytest -q` in `backend/`. Session 08 had
  195. The last 5 are the notice: the order of the two messages, the pin on the notice,
  no pin on a question, a notice that fails, and the `pin` key in the request body.
- **No test uses the network.** Method: a pytest plugin that makes
  `socket.socket.connect`, `connect_ex` and `socket.create_connection` raise, then
  `poetry run pytest -q -p block_network`. The result is 250 passed. This check was
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
- **The deployed backend on the homelab runs chat mode.** Sam deployed at the end of
  this session. Method: `docker exec recall-api python -c ...` gives `modes: ['chat']`,
  the three keys present, and `pin: True` in the create-bot body. Then a signed
  `participant_events.chat_message` for a bot id that no other session holds gives
  HTTP 200, one patient turn in the log, and the status `error` with the reason
  `recall http 404: {"detail":"Not found."}`. Recall does not know that bot, which is
  the expected end of this check: the signature, the parse, the model and the failure
  path each operate on the server.
- **The full loop operates in a live Google Meet call.** Method: `POST /sessions` on
  the live URL for `https://meet.google.com/gmh-vrxf-xgg`, bot
  `2277e43d-3f55-4d9a-9730-a1a90b5de8c7`, session `ac7fe64a52114045acb4180f241ad88b`.
  Sam admitted the bot and answered in the chat. The bot asked 5 questions, the model
  gave the complete signal, and `GET /sessions/{id}` gave `complete` with the eight
  fields. `GET /sessions/{id}/summary` gave the same fields on the public URL. The turns
  table holds 10 rows that alternate, with the patient text as Sam typed it.
- **The bot does not receive its own chat messages.** Method: the log line
  `session <id> got its own message, no turn` is not in the container log of the call,
  and no bot question is in the log as a patient turn. Google Meet with Recall thus does
  not send an event for a message that the bot sent. **The echo filter did not operate
  one time in the live call.** Keep it: it costs 4 lines, the document does not promise
  this behavior, and another platform can be different. But it is not proved by a call.
- **The first question goes out 1.74 seconds after the join, and the pinned notice comes
  after it.** Method: `get_bot_logs` for the bot. `A participant (is_host: true) has
  joined the meeting` at 08:23:38.383, then
  `POST /api/v1/bot/.../send_chat_message/ -> 200` with the first question at
  08:23:40.120. The notice of `chat.on_bot_join` is not an API request, so its time is
  not in the log; the chat of the meeting shows it after the question. Recall must send
  the notice and then pin it, which is a second action in the Meet interface.
- **Each message went out one time, and each send gave HTTP 200.** Method:
  `get_bot_logs` gives 6 `send_chat_message` requests: 5 questions and the closing line.
  No question went out two times, so no delivery was repeated in this call and the
  `webhook-id` question is still not answered.
- **A question of more than 500 characters did not occur.** The 5 questions were 48 to
  93 characters. The split is proved by the tests only.
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
- **Wrong:** a check on the server can use the bot id of an earlier live call.
  **Correct:** the database holds the session of that call, and
  `get_session_by_bot_id` gives an arbitrary row of the two. The first check on the
  homelab thus applied the event to the session of session 05, which is `error`, and it
  made no turn. The check uses a new bot id now. See `../FLOW.md` part 9, item 6.
- **Wrong:** the closing line goes out when the status is `complete` after a turn.
  **Correct:** that sends the line again for each message that arrives after the intake
  ended. The route reads the status from before the turn now.

## Open items

- [x] **The live Google Meet call.** Done. The notice pinned, the intake ran, the
      closing line went out, and the summary is on the public URL.
- [x] **The order of the first two messages.** Repaired. The backend sends the notice
      with `pin`, immediately before the first question.
- [x] **Deploy the notice change, and prove the order in a second live call.** Done in
      session 10. The notice went out at 08:56:18.327 and the first question at
      08:56:20.437, so the order is correct on the server. See
      [`10-frontend.md`](10-frontend.md).
- [x] **Is `pin` the correct field name of the send endpoint?** Yes. The live call of
      session 10 sent `{"to": "everyone", "message": ..., "pin": true}`, the endpoint
      gave HTTP 200, and **the notice was pinned in the Meet chat**. The HTTP 200 alone
      is not the proof, because an API that ignores an unknown key also gives 200. The
      pin in the interface is the proof. See [`10-frontend.md`](10-frontend.md).
- [ ] **Is the `webhook-id` of a real-time retry the same each time?** The repeat
      protection of a chat turn is that header. Svix keeps the id for a dashboard event.
      Recall retries a real-time message with its own policy, and the document does not
      say what the id does. The live call gave no failed delivery, so no retry occurred
      and the question is still open. Owner: section 6, or a call where a delivery
      fails.
- [x] Deploy to the homelab server. Done. The server has the three keys, and
      `modes: ['chat']`.
- [ ] Commit the documents of session 09. The code went up before the live call, and
      the findings of the call did not. Owner: Sam.
- [ ] The six weak points of `../FLOW.md` part 9 go in the README as limitations.
      Owner: the docs pass of section 9.
- [ ] The prompts are not tuned. Section 8a holds three items from this call: the
      first question introduces the assistant a second time, the model stopped after 5
      turns of 6, and `prior_treatments` came back `not discussed` because of that stop.
      Owner: a later session.
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
