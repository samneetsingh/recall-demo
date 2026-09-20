# 08 — The turns table

Written in ASD-STE100 Simplified Technical English.

- **Date:** 2026-09-20
- **Task:** Section 4a of [`../TASKS.md`](../TASKS.md). See
  [`../task-04-turns-table/todo.md`](../task-04-turns-table/todo.md)
- **Result:** complete — the conversation log is its own table. A turn cannot be lost,
  and a repeated delivery changes nothing. The tests went from 180 to 195.

## Summary

Sam read [`../FLOW.md`](../FLOW.md) and asked if the turns must have their own table. The
answer was yes: the log was a JSON array in a column, and `append_turn` was a read and
then a write, which is the same pattern that session 06 removed from the status column.
This session made the `turns` table, moved the data, and dropped the column. Sam also
changed the definition of a turn: it is one message from each party, not one message.
`engine/intake.py` and `engine/summary.py` did not change, which is the proof that the
mode boundary of session 07 was built correctly.

## Files changed

| File | Change | Reason |
|---|---|---|
| `backend/app/db/models.py` | edit | Migrations 3, 4, 5. `Turn`. `Session` lost `transcript` |
| `backend/app/db/session_store.py` | edit | `append_turn` with three rules in one statement, `get_turns` |
| `backend/app/engine/intake.py` | edit | `turn_count` is `len(log) // 2`. `bot_turns` is gone |
| `backend/app/engine/loop.py` | edit | The two guards. The log comes from `get_turns` |
| `backend/app/recall/events.py` | edit | `message_id`, from the `webhook-id` header |
| `backend/tests/test_db_migrations.py` | edit | 8 tests. The backfill with a true conversation |
| `backend/tests/test_session_store.py` | edit | 21 tests. The repeat, the order, the two threads |
| `backend/tests/test_engine_loop.py` | edit | 14 tests. The repeat, and the turn that is overtaken |
| `backend/tests/test_engine_intake.py` | edit | The new definition of a turn |
| `backend/tests/test_recall_events.py` | edit | `message_id` |
| `backend/scripts/intake_console.py` | new | A terminal driver for the full loop, with no Recall |
| `docs/FLOW.md` | new, then edit | The request path, point to point. Parts 2, 3, 6 and 9 |
| `docs/API_REFERENCE.md` | edit | A repeated chat message changes nothing |
| `docs/TASKS.md` | edit | Section 4a |
| `docs/task-04-turns-table/todo.md` | new | The plan of this session |
| `docs/session-logs/08-turns-table.md` | new | This log |

`frontend/`, the `Dockerfile`, the compose file, `pyproject.toml` and `poetry.lock` did
not change. **This session added no package.** `engine/prompts.py` and `engine/summary.py`
did not change.

## Decisions

- **A table, not `json_insert`.** `json_insert(transcript, '$[#]', json(?))` repairs the
  lost turn in one statement, and it repairs nothing else. A table gives the repeat
  protection with a unique index, the order with the rowid, and a place for data about
  one turn. It is 8 lines of schema.
- **The engine gets no state machine of its own.** `status` is the lifecycle of the bot.
  With the turns table, the state of the conversation is calculated from the log: the
  role of the last turn says who is next, and the count says the turn number. A column
  with the state of the engine would be a second truth that can disagree with the log.
  This is the same rule as the turn count.
- **A turn is one message from each party.** Sam changed this during the build.
  `turn_count(log)` is `len(log) // 2`. For a log that alternates it gives the same stop
  point as the old count of the bot messages, so no test of the flow changed.
- **`event_id` is the Svix message id.** Svix keeps the id the same for each retry of one
  message, so it is the natural key of a turn. A bot turn has `NULL`, and SQLite makes
  each `NULL` different from each other `NULL`, so the unique index never refuses one.
- **No `REFERENCES sessions(id)`.** SQLite does not apply a foreign key unless
  `PRAGMA foreign_keys` is on, and this application does not turn it on. A key that does
  nothing tells a reader a lie. The `EXISTS` test in the insert does the work instead.
- **The `EXISTS` test is in the same statement as the insert.** A read and then a write
  would give back the race that this task removes.
- **`Session` lost its `transcript` field.** The frontend polls `GET /sessions/{id}`
  every 2 to 3 seconds and never reads the log. A second query on each poll gets worse as
  the conversation grows. `get_turns(session_id)` is called by the one caller that needs
  it.
- **The conversation is half-duplex, and the rule is in the insert.** Sam gave the rule
  during the build: one full patient message goes in, the assistant answers it, and only
  then does the next message go in. The rule is derivable from the log — the role of a
  new turn must not be the role of the last turn — so it needs no flag and no column. It
  is one more condition in the insert, it deleted `is_newest_turn`, and it left
  `run_turn` with one guard in place of two. `SPEC.md` already gave this rule for voice
  mode; chat mode is the same rule with the message as the unit.
- **The alternation rule is what makes `len(log) // 2` exact.** The log cannot hold two
  messages from one party in sequence, so the count of rows is always two per turn.
- **Part 9 of `FLOW.md` keeps the three faults, marked as repaired.** A list of what was
  wrong, and why, is worth more than a clean page.

## Verified facts

- **The 195 tests pass.** Method: `poetry run pytest -q` in `backend/`. Session 07 had
  180.
- **`engine/intake.py` and `engine/summary.py` needed no change for the store.** Method:
  the two files were not touched for the table. `intake.py` changed only for the new
  definition of a turn, which Sam asked for. `summary.py` and `prompts.py` are the same.
  This is the test of the mode boundary, and it passed.
- **The threaded test finds the lost turn.** Method: put the task 3 pattern back — read
  the turns, then write all of them — and run the test. Two threads give **one** row and
  not two: `assert len(set(ids)) == 2` fails with `1 == 2`. After the restore, all tests
  pass.
- **The migration moved a true conversation on the volume.** Method: read the database on
  the named volume before and after `docker compose up -d --build`. Before:
  `user_version` 2, 3 session rows, one with a two-entry JSON transcript, no `turns`
  table. After: `user_version` 5, the same 3 session rows with the same `status` and
  `error_reason`, a `turns` table with the two messages in the correct order, and no
  `transcript` column.
- **The full loop runs end to end against the real model.** Method:
  `poetry run python scripts/intake_console.py` in `backend/`, with a scripted patient on
  the standard input. The assistant introduced itself, asked 6 questions, branched on the
  answer "I feel sick with it" for the last one, and the session went to `complete` with
  6 turns, 12 rows and the eight fields. No Recall, no webhook and no Meet call.
- **A patient who sends three messages for one question still gets 6 questions.**
  Method: a script appends a question and then three patient messages, in a loop, until
  `turn_count` is 6. The result is 6 questions, 12 rows, and the roles `BPBPBPBPBPBP`.
  The two extra messages of each turn are refused.
- **A repeated event makes one turn and one question.** Method: a test calls `run_turn`
  two times with the same `event_id`. The log has 3 rows and not 4, and the mode sent 2
  messages and not 3.
- **A second patient message before the answer is refused.** Method: a test puts a
  second patient turn in during the first call. The log is `bot, patient, bot`, and the
  second message is not in it.
- **An orphan turn is refused.** Method: `append_turn("no-such-id", ...)` gives `None`.
- **The container builds and becomes healthy.** Method:
  `docker compose -f deploy/docker-compose.yml up -d --build`, then a loop on
  `docker inspect --format '{{.State.Health.Status}}' recall-api`. The result is
  `Up 8 seconds (healthy)`.
- **`GET /health` gives HTTP 200, and the CORS behavior did not change.** Method:
  `docker exec recall-api curl -i -s ...`. The origin `https://recall.samneet.com` gives
  `access-control-allow-origin`, and an origin that is not in the list does not.
- **`GET /sessions/{id}` gives the same answer as before.** Method:
  `docker exec recall-api curl -i -s`. The frontend never read the log.

## Corrections

- **Wrong:** a plain `INSERT` is sufficient for `append_turn`. **Correct:** with no
  foreign key, it puts a turn against a session that is not there. The test
  `test_a_write_to_an_unknown_id_gives_none` of task 2 found it in the first run. The
  `EXISTS` test is now in the same statement.
- **Wrong:** the threaded test can run against "the code of task 3" to show the fault.
  **Correct:** that code reads a JSON column that no longer exists. The check put the
  **pattern** back instead — a read of the turns, then a write of all of them — which
  has the same fault and shows it in the same way.

## Open items

- [ ] Commit and push the changes of sessions 07 and 08. Owner: Sam.
- [ ] Deploy to the homelab server. Owner: Sam. The server needs `OPENAI_API_KEY` in its
      `.env`. The migration applies at the start of the container and keeps the rows, as
      the local volume proved.
- [ ] A turn that fails has no retry. If the handler of the newest turn stops, the
      conversation waits and nothing acts. The turns table makes it visible — the last
      turn has the role `patient` and it is old — and no code reads it. Write it in the
      README as a next step. Owner: the docs pass of section 9.
- [ ] A refused patient message is lost. The half-duplex rule refuses it, and its text
      is in the container log only. A patient who sends an answer in two parts loses the
      second part. Write it in the README as a limitation. Owner: the docs pass of
      section 9.
- [ ] The prompts operate and they are not tuned. Sam called this an optimization for
      the end. It is section 8a of `../TASKS.md` now, with what the live checks of
      session 07 found. Owner: a later session, after the loop works.
- [ ] Starlette says that `httpx` with `TestClient` is deprecated. The 195 tests pass
      with the warning only. Owner: the next session that touches the tests.

## A note on the driver

`scripts/intake_console.py` is a development tool and not application code, so it is not
in `app/` and the `Dockerfile` does not copy it. It puts `ConsoleMode` in the `MODES`
registry, which is the same door that chat mode uses in section 5. It is thus a third
implementation of the turn boundary, and it tests the boundary and not a copy of it.

Two facts from the Recall documents that section 5 needs:

- **Google Meet permits 500 characters in a chat message.** The intake prompt asks for
  two sentences, so a question fits, but no code applies the limit. The driver writes a
  warning if a question is longer.
- **`POST /api/v1/bot/{id}/send_chat_message/` sends the message.** Google Meet permits
  the recipient `everyone` only. `app/recall/client.py` has no send function yet.

## Next session starts here

Do section 5 of [`../TASKS.md`](../TASKS.md): chat mode. The store is safe now, so the
loop is written one time.

1. Make `app/modes/chat.py`. `handle_incoming_turn` reads a
   `participant_events.chat_message` event into patient text, and gives `None` for a
   message that the bot itself sent. `send_outgoing_turn` sends a chat message through
   the Recall API.
2. Put it in `MODES` in `app/modes/base.py`. This is the one line that connects it.
3. Add `send_chat_message(bot_id, text)` to `app/recall/client.py`. It does not exist.
   `POST /api/v1/bot/{id}/send_chat_message/`, and Google Meet takes `everyone` only.
4. `app/routes/webhooks.py` calls `loop.start_intake` when `apply_bot_event` gives `True`
   and the new status is `in_progress`, and `loop.run_turn` for a chat message. **Give
   `event.message_id` as the `event_id`.** The store then refuses a repeat by itself.
5. **The bot gets its own chat messages back.** `handle_incoming_turn` must give `None`
   for a message that the bot sent, or the assistant interviews itself.
6. Test the full loop against a real Google Meet call, from the first question to the
   summary.

Ask Sam before a deploy to the homelab server. Do not change `frontend/` in the same
turn as a `backend/` task.
