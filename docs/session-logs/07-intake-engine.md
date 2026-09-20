# 07 — The mock intake engine and the mode boundary

Written in ASD-STE100 Simplified Technical English.

- **Date:** 2026-09-20
- **Task:** Section 3 and section 4 of [`../TASKS.md`](../TASKS.md). See
  [`../task-03-intake-engine/todo.md`](../task-03-intake-engine/todo.md)
- **Result:** complete — the engine asks the questions, makes the eight fields, and the
  stub summary is gone. The tests went from 112 to 180.

## Summary

This session made the mock intake engine and the boundary between the state machine and
the meeting platform. The engine takes plain text in and gives plain text out, and no
module above the boundary names chat or voice. The session added one package, `openai`,
and it did not change `frontend/`. A live call to the real model found three faults in
the prompts that no mocked test can find.

## Files changed

| File | Change | Reason |
|---|---|---|
| `backend/app/engine/prompts.py` | new | All prompt text, the red-flag list and the two schemas |
| `backend/app/engine/llm.py` | new | The only module that imports `openai`. `ask_model`, `LLMError` |
| `backend/app/engine/intake.py` | new | `next_turn`, `NextTurn`, the turn count |
| `backend/app/engine/summary.py` | new | `make_summary`, the eight fields |
| `backend/app/engine/loop.py` | new | `start_intake`, `run_turn`. The state machine |
| `backend/app/modes/base.py` | new | The `TurnMode` protocol, `MODES`, `get_mode` |
| `backend/app/config.py` | edit | `OPENAI_MODEL`, `OPENAI_TIMEOUT_SECONDS`, `INTAKE_MAX_TURNS` |
| `backend/app/routes/sessions.py` | edit | `STUB_SUMMARY` removed. HTTP 500 for a complete session with no summary |
| `backend/tests/test_engine_prompts.py` | new | 26 tests. The prompts, and the two rules of `CLAUDE.md` |
| `backend/tests/test_engine_llm.py` | new | 11 tests against the real SDK and a fake transport |
| `backend/tests/test_engine_intake.py` | new | 11 tests. A scripted conversation and the turn limit |
| `backend/tests/test_engine_summary.py` | new | 9 tests. The eight fields |
| `backend/tests/test_engine_loop.py` | new | 11 tests. The standalone proof of the full intake |
| `backend/tests/test_routes_sessions.py` | edit | The stub test is now the 500 test |
| `backend/tests/conftest.py` | edit | `OPENAI_API_KEY` and `OPENAI_MODEL` for the tests |
| `backend/pyproject.toml`, `poetry.lock` | edit | `openai` |
| `backend/.env.example` | edit | The three new values |
| `docs/API_REFERENCE.md` | edit | `not discussed`, `RED FLAG:`, and the 500 |
| `docs/SPEC.md`, `docs/ARCHITECTURE.md`, `CLAUDE.md` | edit | The stack is the `openai` SDK, not LiteLLM |
| `docs/TASKS.md` | edit | Section 3 and section 4 are complete |
| `docs/task-03-intake-engine/todo.md` | new | The plan of this session |
| `docs/session-logs/07-intake-engine.md` | new | This log |

`Dockerfile`, `deploy/docker-compose.yml` and the database schema did not change.
`frontend/` did not change.

## Decisions

- **The `openai` SDK, not LiteLLM.** `CLAUDE.md` named LiteLLM in the stack, and the
  rule says to flag each new package. Sam selected the SDK: the workspace has no
  `ANTHROPIC_API_KEY`, so a provider change has no use in this build, and LiteLLM pulls
  a large tree. `CLAUDE.md`, `SPEC.md` and `ARCHITECTURE.md` now say the SDK.
- **The model is `gpt-4o-mini`, and the limit is 6 questions.** Sam selected both. The
  patient waits in the meeting for the next question, so latency is a part of the
  demonstration. Both values are in `config.py` and in `.env`.
- **The prompt framework came from a synthetic test suite that Sam wrote.** The model
  answers with one JSON object that holds an action. The terminal action is `complete`
  and not `diagnose`: `SPEC.md` makes this bot an intake assistant and not a physician,
  and the summary has no diagnosis field.
- **The engine counts the turns, the model does not.** `next_turn` counts the entries
  with the role `bot` and gives the complete signal at the limit **with no call to the
  model**. A model does not always keep a limit that a prompt gives it. This is also
  what makes the end of the intake the same each time in a test.
- **The `turn` field of the model is in the schema and no code reads it.** It helps the
  model count. A test proves that a model which says turn 99 does not end the intake.
- **The JSON schema is strict, and the prose rule stays.** `response_format` with
  `strict: true` makes the API itself refuse an answer of another shape, so "no Markdown
  and no backticks" is a guarantee and not a request.
- **The summary is a second call with its own prompt.** `SPEC.md` says this. It also
  keeps `summary.py` usable alone: a call that ends early can still give a summary of
  the part of the intake that is complete.
- **The summary is written before the status becomes `complete`.** The frontend reads
  the status and then asks for the summary. The opposite order gives a window in which a
  complete session has none. A test watches `set_status` and proves the order.
- **The question goes out before it goes in the log.** A question that the patient never
  received must not be in the log, because the next call to the model would see it as an
  asked question. A test with a mode that fails proves it.
- **A complete session with no summary gives HTTP 500.** `loop.py` makes this state
  impossible, so it is a fault of the backend. An empty object would hide it.
- **The mode registry is empty in this session.** `MODES` has no entry until section 5
  puts `chat` in it. The tests use a fake mode. An empty registry is what proves that
  nothing above the boundary depends on a mode.
- **`RED_FLAGS` is one constant for both prompts.** If the intake and the summary have
  two lists, they do not agree on what a red flag is.
- **The client is made per call, not at the import.** `app/recall/client.py` does the
  same. A client at the import needs the key before a test can set one.

## Verified facts

- **The 180 tests pass, with no network.** Method: `poetry run pytest -q` in `backend/`.
  Session 06 had 112. The 112 tests pass, and only the stub test changed.
- **The engine runs standalone against a scripted conversation.** Method:
  `tests/test_engine_loop.py`. A fake mode collects the outgoing text, a scripted patient
  answers, and the session goes from the first question to the stored summary: 6
  questions, 12 log entries, the status `complete`, and the eight fields. No Recall, no
  webhook and no network.
- **The turn limit is the engine and not the prompt.** Method: remove the two lines of
  the limit from `intake.py`, then run the tests. The result is `3 failed, 172 passed`.
  After the restore, all tests pass.
- **The order of the summary and the status is a test, not a hope.** Method: change
  `_finish` to write the status first. The result is `1 failed, 174 passed`.
- **A question that failed to go out is not in the log.** Method: change `_advance` to
  log before it sends. The result is `1 failed, 174 passed`.
- **The real model gives the correct shape and keeps the limit.** Method: a script by
  hand with `gpt-4o-mini` and a scripted patient, outside `pytest`. The bot introduced
  itself, asked 6 questions, branched on the answers, and the summary had the eight
  fields. See the corrections below for what the first runs showed.
- **The container builds and becomes healthy.** Method:
  `docker compose -f deploy/docker-compose.yml up -d --build`, then a loop on
  `docker inspect --format '{{.State.Health.Status}}' recall-api`. The result is
  `Up 5 seconds (healthy)`.
- **`GET /health` gives HTTP 200, and the CORS behavior did not change.** Method:
  `docker exec recall-api curl -i -s ...`. The origin `https://recall.samneet.com` gives
  `access-control-allow-origin`, and an origin that is not in the list does not.
- **The image has the new package.** Method:
  `docker exec recall-api python -c "import openai, httpx2"`. The result is
  `openai 3.16.2 | httpx2 2.13.0`.
- **`GET /sessions/{id}/summary` gives a real summary in the container.** Method: write
  a session with the eight fields through `session_store`, then
  `docker exec recall-api curl -i`. The result is HTTP 200 and the eight keys in order.
- **The database kept its rows, and the schema version did not change.** Method: count
  the rows on the named volume before and after the build, and read `PRAGMA
  user_version`. The result is 3 rows and version 2, before and after.

## Corrections

The three faults below came from the live call. **A mocked test cannot find any of
them**, because a mock gives the answer that the test writer expected.

- **Wrong:** a schema test proves a prompt. **Correct:** it proves the shape only. The
  first live run stopped after 5 of the 6 questions and left `prior_treatments` empty,
  and it called nausea a red flag. The prompt now says to use each question, and it names
  the red flags in both prompts.
- **Wrong:** a list of the red flags in the summary prompt is sufficient. **Correct:** it
  made the model invent one. The patient said "really bad headaches" and the summary said
  "the worst headache of my life", which is a specific red flag that the patient did not
  give. This is the worst failure of a clinical summary. The prompt now says not to make
  the words of the patient stronger, and it gives the contrast.
- **Wrong:** the rule against an invented red flag was sufficient. **Correct:** it made
  the opposite fault. A second scripted patient gave three true red flags — the worst
  headache of a life, a peak in ten seconds, and a stiff neck — and the summary said
  "no red flag was reported". A clinician would not see the thunderclap. The rule now has
  two parts: write a red flag that the patient described, and do not make one from words
  that are only near to it. Both live patients now give the correct result.
- **Wrong:** the `openai` SDK uses `httpx`. **Correct:** version 3.16.2 uses `httpx2`,
  which is a different package. The image now has both: `httpx` for the Recall client and
  `httpx2` for the SDK. The test of `llm.py` uses `httpx2.MockTransport`.

## Open items

- [ ] Commit and push the changes of this session. Owner: Sam.
- [ ] Deploy to the homelab server. Owner: Sam. The server needs `OPENAI_API_KEY` in its
      `.env`. The schema did not change, so the container keeps its rows.
- [ ] The model sometimes gives the action `complete` with one question left, although
      the prompt says to use each question. The engine guarantees a maximum of 6 and not
      a minimum. This is correct: a patient who stops the interview must be able to stop
      it. Write it in the README limitations. Owner: the docs pass of section 9.
- [ ] `INTAKE_MAX_TURNS` is 6 for a short demonstration. A live call with a patient who
      speaks more may need a larger value. Owner: Sam, at the demonstration.
- [ ] Starlette says that `httpx` with `TestClient` is deprecated. The 180 tests pass
      with the warning only. Owner: the next session that touches the tests.

## Next session starts here

Do section 5 of [`../TASKS.md`](../TASKS.md): chat mode. The engine and the boundary are
complete, so this section adds one implementation and changes nothing above it.

1. Make `app/modes/chat.py`. `handle_incoming_turn` parses a
   `participant_events.chat_message` event into patient text, and it gives `None` for a
   message that the bot itself sent. `send_outgoing_turn` sends a chat message through
   the Recall API.
2. Put it in `MODES` in `app/modes/base.py`. This is the one line that connects it.
3. `app/routes/webhooks.py` calls `loop.start_intake` when the status becomes
   `in_progress`, and `loop.run_turn` for a chat message. The real-time events are in
   `REALTIME_EVENTS` and they write a log line only at this time.
4. The webhook handler must not take the same chat message two times. Svix delivers at
   least one time.
5. Test the full loop against a real Google Meet call, from the first question to the
   summary.

Ask Sam before a deploy to the homelab server. Do not change `frontend/` in the same
turn as a `backend/` task.
