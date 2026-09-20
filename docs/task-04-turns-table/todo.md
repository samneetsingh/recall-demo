# Task 4 — The turns table: todo

Written in ASD-STE100 Simplified Technical English.

## Scope

The conversation log is a JSON array in the `sessions.transcript` column. This task moves
it to its own table, `turns`, and makes a turn safe against a repeat and against two
handlers that operate at the same time.

This task comes before section 5 of [`../TASKS.md`](../TASKS.md). Section 5 then writes
the chat loop one time against a store that is already safe.

## The problem

[`../FLOW.md`](../FLOW.md) part 9 gives three faults. They have one cause: the status
column has concurrency control and the conversation log has none.

1. **A turn can be lost.** `append_turn` reads the transcript, makes a new array in
   Python, and writes it back in a **different** statement. Two webhook handlers that
   operate at the same time both read the same array, and the second write removes the
   turn of the first. Session 06 removed this same read-then-write pattern from the
   status column and gave the reason. The log kept it.
2. **A turn has no idempotency.** Svix delivers at least one time. The same chat message
   delivered two times puts the same text in the log two times and asks two questions.
   The bot status events do not have this fault, because `last_event_at` refuses a
   repeat.
3. **Two turns of one session can run the engine at the same time.** Nothing holds a
   session while a turn is in progress. A patient who sends two messages quickly can get
   two questions, and the second call does not see the first question.

A `json_insert` statement repairs fault 1 only. A table repairs 1 and 2 with the schema
itself, and it makes 3 cheap to guard.

## Answers from Sam

- **Build the turns table, as its own task, before section 5.**
- **Backfill the JSON, then drop the `transcript` column.** One source of truth. A test
  must prove that the rows keep their data.

### Why a table and not a JSON column with `json_insert`

| Fault | A JSON column | A table |
|---|---|---|
| A lost turn | `json_insert(transcript, '$[#]', json(?))`. Correct, and a reader must know why | `INSERT`. Atomic because it is an insert |
| A repeated event | Application logic that compares ids | `UNIQUE(session_id, event_id)` and `INSERT OR IGNORE` |
| The order | The position in the array | The `rowid` |
| Data on one turn | Change the shape of the object everywhere | A column |

### Why the engine gets no state machine of its own

`status` is the lifecycle of the **bot**: `creating_bot`, `waiting_for_bot`,
`in_progress`. It does not say what the conversation is doing. With the turns table, the
state of the conversation is **calculated** and thus it cannot disagree with the log:

- the last turn has the role `bot` — the assistant waits for the patient;
- the last turn has the role `patient` — the assistant owes a question;
- the count of the turns with the role `bot` — the turn number;
- the last turn has the role `patient` and it is old — the engine lost a turn.

A column with the state of the engine makes the disagreement that this task removes. The
rule is the same rule as the turn count: do not store what you can calculate.

## New dependencies

**None.** The table, the index, `json_each` and `DROP COLUMN` are part of SQLite.

### Verified before the plan

Method: the statements of this plan against the SQLite of the tests and of the image.

- The local Python gives SQLite 3.53.2, the image gives 3.46.1. `DROP COLUMN` needs
  3.35, and `json_each` needs 3.9. Both versions are sufficient.
- The backfill statement moved a two-entry JSON array into two rows, in order.
- `INSERT OR IGNORE` with a repeated `event_id` gives `rowcount` 0.
- A unique index permits more than one row with `event_id` that is `NULL`, so a bot turn
  is never refused. SQLite makes each `NULL` different from each other `NULL`.

## Files

```
backend/
  app/
    db/
      models.py               edit  Migrations 3, 4, 5. Turn. Session loses transcript
      session_store.py        edit  append_turn, get_turns
    engine/
      loop.py                 edit  Read the log with get_turns. The newest-turn guard
    recall/
      events.py               edit  message_id on RecallEvent, from the webhook-id header
  tests/
    test_db_migrations.py     edit  Version 5. A v2 file keeps its turns as rows
    test_session_store.py     edit  The turns table, the repeat, the order
    test_engine_loop.py       edit  get_turns. A repeated turn asks no second question
    test_recall_events.py     edit  message_id
docs/
  FLOW.md                     edit  Part 2, part 3 and part 9
  API_REFERENCE.md            edit  A repeated chat message changes nothing
  TASKS.md                    edit  A new section 4a, before chat mode
  task-04-turns-table/todo.md       new
  session-logs/08-turns-table.md    new
```

`frontend/`, the `Dockerfile`, the compose file, `pyproject.toml` and `poetry.lock` do
not change. **`app/engine/intake.py` and `app/engine/summary.py` do not change.** They
take `list[{role, text}]` and they never learn where it comes from. This is the test of
whether the mode boundary and the engine were built correctly.

The word `transcript` in `app/recall/client.py` and `app/routes/webhooks.py` is the name
of the Recall event `transcript.data`. **Do not change those lines.**

## Procedure — the schema

- [x] Migration 3 makes the table. Put it at the end of `MIGRATIONS` in `models.py`.

```sql
CREATE TABLE IF NOT EXISTS turns (
    id          INTEGER PRIMARY KEY,
    session_id  TEXT NOT NULL,
    role        TEXT NOT NULL,
    text        TEXT NOT NULL,
    event_id    TEXT,
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS turns_session ON turns(session_id, id);
CREATE UNIQUE INDEX IF NOT EXISTS turns_event ON turns(session_id, event_id);
```

- [x] `id INTEGER PRIMARY KEY` is the rowid. It gives the order, and it always goes up.
- [x] Write a comment that says that SQLite makes each `NULL` different, so the unique
      index permits many bot turns with no `event_id`.
- [x] **No `REFERENCES sessions(id)`.** SQLite does not apply a foreign key unless
      `PRAGMA foreign_keys = ON`, and this application does not turn it on. A key that
      does nothing tells a reader a lie.
- [x] Migration 4 copies the JSON into rows. `COALESCE` protects a row with `NULL`.

```sql
INSERT INTO turns (session_id, role, text, created_at)
SELECT s.id, json_extract(t.value, '$.role'), json_extract(t.value, '$.text'), s.updated_at
  FROM sessions s, json_each(COALESCE(s.transcript, '[]')) t;
```

- [x] Migration 5 is `ALTER TABLE sessions DROP COLUMN transcript;`.
- [x] The rule of session 06 does not change: an entry that shipped is never changed and
      never removed. These three go at the end.
- [x] Make a `Turn` dataclass in `models.py`: `id`, `session_id`, `role`, `text`,
      `event_id`, `created_at`, with `from_row`.
- [x] Remove `transcript` from the `Session` dataclass and from `Session.from_row`.

## Procedure — the store

- [x] `append_turn(session_id, role, text, event_id=None) -> int | None`. It gives the
      id of the new turn, or `None` if the event was already applied.

```sql
INSERT OR IGNORE INTO turns (session_id, role, text, event_id, created_at)
VALUES (?, ?, ?, ?, ?)
```

- [x] Read `cursor.rowcount` **before** `lastrowid`. An insert that the index refused
      gives `rowcount` 0, and `lastrowid` is then not the id of this turn.
- [x] The same statement bumps `sessions.updated_at`. It is one more statement in the
      same connection, and a time has no race that matters.
- [x] `get_turns(session_id) -> list[dict[str, str]]` gives
      `[{"role": ..., "text": ...}]` ordered by `id`. This is the exact shape that the
      engine takes, so no caller makes the change.
- [x] ~~`is_newest_turn(session_id, turn_id) -> bool` reads the largest `id` of the
      session and compares it. This is the guard of fault 3.~~ **Superseded.** Sam gave
      the half-duplex rule during the build, and it is in the insert. See the changes
      below.
- [x] Keep all query SQL in this file.

## Procedure — the engine loop

- [x] `run_turn(session_id, patient_text, event_id=None)`.
- [x] Put the patient turn in with `append_turn(..., event_id)`. A result of `None` means
      that this event was already applied: write a log line and **stop**. This is fault 2.
- [x] ~~After the insert, call `is_newest_turn`.~~ **Superseded.** The insert refuses a
      second patient message by itself, so `run_turn` has one guard and not two: a result
      of `None` means a repeat or a message that came too early, and it stops.
- [x] `_advance` reads the log with `get_turns(session.id)` and not from the session
      object. The read is thus after the insert, and it sees each turn.
- [x] `start_intake` uses `get_turns` for its "the intake is running" test.
- [x] A repeated `bot.in_call_recording` does not reach `start_intake` two times, because
      `apply_bot_event` of session 06 gives `False` for an event that is not newer.
      Write this in a comment. The `get_turns` test is the second protection.
- [x] **`intake.py` and `summary.py` get no change.** If this task needs one, the mode
      boundary is wrong and the plan must stop.

## Procedure — the event id

- [x] Add `message_id: str | None` to `RecallEvent` in `app/recall/events.py`. The value
      is the `webhook-id` header, which Svix keeps the same for each retry of one
      message.
- [x] Section 5 gives it to `run_turn` as the `event_id`. This task does not call it, and
      the field makes the unique index real and not theoretical.

## Procedure — the tests

- [x] `test_db_migrations.py`: a new file gets version 5; **a file at version 2 with a
      JSON transcript keeps each turn as a row, in order**; the `transcript` column is
      gone; `init_db()` two times changes nothing.
- [x] The migration test must use a transcript with more than one entry. A test with an
      empty array proves nothing about the backfill.
- [x] `test_session_store.py`: `append_turn` gives an id; `get_turns` gives the order of
      insertion; the same `event_id` two times makes one row and the second call gives
      `None`; two different `event_id` values make two rows; many bot turns with no
      `event_id` are accepted; the log always alternates.
- [x] `test_engine_loop.py`: the full intake still runs, with `get_turns` in place of
      `session.transcript`; **a repeated patient event asks no second question**; a turn
      that is not the newest stops and asks nothing.
- [x] `test_recall_events.py`: `message_id` comes from the `webhook-id` header.
- [x] Each of the 180 tests must pass. `test_engine_intake.py`, `test_engine_summary.py`
      and `test_engine_prompts.py` must not need one change.

## Proof

- [x] `poetry run pytest` in `backend/` passes. The count is more than 180.
- [x] **Prove that the new test finds the fault.** Method: change `INSERT OR IGNORE` to
      `INSERT`, then run the test. The repeat test must fail. Restore it.
- [x] Prove the lost turn is gone. Method: a test with two threads that call
      `append_turn` at the same time for one session. The result must be two rows. The
      same test against the code of task 3 loses one.
- [x] `docker compose -f deploy/docker-compose.yml up -d --build` in `backend/`, then a
      loop on `docker inspect --format '{{.State.Health.Status}}' recall-api` gives
      `healthy`. Do not read the value in the same second as the start.
- [x] **The database on the named volume keeps its rows through the migration.** Method:
      count the session rows and read the turns before and after. `PRAGMA user_version`
      gives 5, and the `transcript` column is gone.
- [x] `GET /health` gives HTTP 200, and the CORS behavior does not change. Method:
      `docker exec recall-api curl -i ...`. Use `curl -i`, not `curl -I`.
- [x] `GET /sessions/{id}` and `GET /sessions/{id}/summary` do not change their answer.
      The frontend never read the transcript.

## Done criteria

- [x] The conversation log is rows in `turns`, and `sessions.transcript` is gone.
- [x] A repeated event makes no second turn and no second question.
- [x] Two appends at the same time keep both turns.
- [x] `intake.py` and `summary.py` are byte for byte the same.
- [x] The tests pass, the container is healthy, and the volume kept its data.
- [x] `../FLOW.md` part 9 no longer lists faults 1 and 2.
- [x] `../session-logs/08-turns-table.md` is complete.

## Out of scope

- The chat send and the chat receive logic. That is section 5.
- A timeout for a patient who stops answering. The turns table makes it visible, and
  nothing acts on it. Write it in the README as a next step.
- A retry of a turn that failed.
- Alembic. The `MIGRATIONS` list is the answer, and Sam decided this in session 06.
- A change to `frontend/`.
- A deploy to the homelab server. Ask Sam first.
- A commit and a push.


## What changed against the plan

- **`append_turn` has an `EXISTS` test.** The plan did not have one. With no foreign key,
  a plain `INSERT` puts a turn against a session that is not there, and the test
  `test_a_write_to_an_unknown_id_gives_none` of task 2 showed it at once. A read and then
  a write would give back the race that this task removes, so the test is in the same
  statement: `INSERT ... SELECT ... WHERE EXISTS (SELECT 1 FROM sessions WHERE id = ?)`.
- **A turn is now one message from each party.** Sam changed the definition during the
  build. `turn_count(log)` is `len(log) // 2`, and `bot_turns` is gone. For a log that
  alternates, the two give the same stop point, so no test of the flow changed. The
  count is of rows, so a patient who sends two messages for one question uses two turns
  and gets 4 questions and not 6. This is written in `../FLOW.md` part 3.
- **The proof of the lost turn found the fault with a different shape.** The plan said to
  run the threaded test against "the code of task 3". That code reads a JSON column that
  no longer exists, so the check put the task 3 **pattern** back instead: a read of the
  turns, then a write of all of them. The two threads then give one row and not two,
  which is the same fault.
- **`FLOW.md` got the change, not only the new parts.** Parts 2, 3, 6 and 9 all describe
  the log. Part 9 keeps the three faults, marked as repaired, so the reason is not lost.

- **The half-duplex rule replaced `is_newest_turn`.** Sam gave the rule during the build:
  one full patient message goes in, the assistant answers it, and only then does the next
  message go in. That rule is derivable from the log — the role of a new turn must not be
  the role of the last turn — so it went in the insert as one more condition, and
  `is_newest_turn` was deleted. The result is less code than the plan, and one guard in
  `run_turn` in place of two.
- **The alternation rule makes `len(log) // 2` exact.** The plan had a known effect: a
  patient who sends two messages for one question used two turns and got 4 questions and
  not 6. With the rule, the log cannot hold two messages from one party in sequence, so
  that effect cannot happen. Method: a patient who sends three messages for each question
  still gets 6 questions and a log of 12 rows.
- **A refused message is lost, and this is new.** The plan queued nothing and said
  nothing about it. The text is in the container log only. It is written in `../FLOW.md`
  part 9 and in `../API_REFERENCE.md`.
