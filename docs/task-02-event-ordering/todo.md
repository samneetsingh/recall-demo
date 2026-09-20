# Task 2, part 3 — Out-of-order webhook events: todo

Written in ASD-STE100 Simplified Technical English.

## Scope

The live test at the end of session 05 showed that Recall delivers the bot status events
out of order. The webhook handler is last-write-wins, so a late event can put an old
status on a session. This task makes the handler order-independent.

It also adds a schema version to the database, because the fix needs a new column and
"make the database file again" is not an acceptable answer.

This task changes no behavior that a correct sequence of events gives. It only refuses
an event that must not change the session.

## The problem

Method: `recall-ai` MCP, `list_webhook_deliveries` for the bot
`92627318-0bee-4ddc-89e7-8cf484724b18` of the live test.

| Event | Made at | Recall sent it at |
|---|---|---|
| `bot.joining_call` | `05:47:04.508` | `05:47:04.612` |
| `bot.in_waiting_room` | `05:47:04.524` | `05:47:04.556` |
| `bot.in_call_not_recording` | `05:47:04.532` | `05:47:04.612` |
| `bot.in_call_recording` | `05:47:04.556` | `05:47:04.652` |

`bot.in_waiting_room` went out before `bot.joining_call`, which is the opposite of the
order the events were made in. The four answers took 132 ms to 153 ms, so the handlers
also overlap in time.

This run gave the correct result, but only by luck: the first two events map to the same
status, and `bot.in_call_recording` was last. If `bot.in_call_recording` had come before
`bot.in_call_not_recording`, the session would show `waiting_for_bot` while the bot is in
the call. The demo would look like a hang, and no chat message would get an answer.

**This is not a fault of Recall.** Webhook delivery is at-least-once and has no order.
Svix retries each message independently. Any receiver can get the events out of order or
two times. The fault is that the handler uses the order of arrival as the truth.

## Answers from Sam

- **The fix uses the time of the event, not the order of arrival.** A bot status event
  carries `data.data.updated_at`. The handler applies an event only if it is newer than
  the last event that the session applied.
- **The database gets a schema version with `PRAGMA user_version`. There is no Alembic.**
  SQLite has the version integer in the file. A list of statements in order, applied at
  the start, is approximately 20 lines and no new package. `CLAUDE.md` refuses a
  migrations framework, and this is not one.

### Why not a rank of the statuses

The first idea was to give each status a number and to permit only a move up. It is
smaller, but it puts the lifecycle of Recall in our code, and that model is already
wrong: the document for `bot.in_call_not_recording` says that this status also comes
**after** `bot.in_call_recording` when a recording is paused. A rank would refuse that
event without a trace. It also breaks when Recall adds a status. This is the same reason
that `sub_code` is not an enum.

### Why not a read of the bot from the Recall API

A call to `GET /api/v1/bot/{id}` on each event gives the true status, and it also repairs
a webhook that never arrived. It is more correct. It also puts an HTTP call in the write
path, makes the status depend on the availability of Recall, and uses the rate limit. The
time guard gives most of the correctness for a small part of the cost. Keep the API read
as the next step in the README, not in this task.

## New dependencies

**None.** `PRAGMA user_version` is part of SQLite, and the time comparison uses
`datetime` from the standard library.

## Files

```
backend/
  app/
    db/
      models.py               edit  MIGRATIONS, and last_event_at on the Session type
      session_store.py        edit  init_db applies the migrations. apply_bot_event
    recall/
      events.py               edit  event_at on RecallEvent, in one format
    routes/
      webhooks.py             edit  Call apply_bot_event. The route keeps no state rule
  tests/
    test_db_migrations.py     new   The version, and an old file that keeps its rows
    test_routes_webhooks.py   edit  Each order of the four live events
    test_recall_events.py     edit  event_at, and a payload with no updated_at
docs/
  API_REFERENCE.md            edit  A sentence on the order of the events
  task-02-event-ordering/todo.md    new
  session-logs/06-event-ordering.md new
```

`frontend/`, the `Dockerfile` and the compose file do not change.

## Procedure — the schema version

- [x] Put a list `MIGRATIONS` in `app/db/models.py`. The index in the list is the schema
      version. Entry 1 is the `CREATE TABLE` statement that exists now. Entry 2 is
      `ALTER TABLE sessions ADD COLUMN last_event_at TEXT;`.
- [x] Write a comment that says the rule: an entry that shipped must never change and
      must never be removed. A change goes at the end of the list.
- [x] Change `init_db()` in `session_store.py`. It reads `PRAGMA user_version`, applies
      each statement after that version in order, and writes the new version after each
      one.
- [x] A database file that exists now has the version 0 and has the sessions table. The
      first statement is `CREATE TABLE IF NOT EXISTS`, so it does nothing and the version
      becomes 1. The second statement then adds the column. **No data is lost, on this
      machine or on the server.** A test must prove this.
- [x] `PRAGMA user_version = ?` does not accept a parameter, so the statement uses the
      value of the loop index. Write a short comment that says the value is an integer
      from the code and never from a request.
- [x] Add `last_event_at: str | None` to the `Session` dataclass and to `from_row`.

## Procedure — the time of the event

- [x] Add `event_at: str | None` to `RecallEvent` in `app/recall/events.py`.
- [x] Read `data.data.updated_at` for the value.
- [x] Put the value in one format before it is stored: parse it with
      `datetime.fromisoformat`, change it to UTC, and write it with
      `isoformat(timespec="microseconds")`. Each stored value then has the same shape, so
      a text comparison gives the same result as a time comparison.
- [x] A value that does not parse, or a payload with no `updated_at`, gives `None`. An
      event with `None` is applied, and it does not change `last_event_at`. **Do not
      refuse an event because its time is absent.** A refused true event is worse than an
      event that is applied in the wrong order.

## Procedure — the guard

- [x] Write `apply_bot_event(session_id, status, error_reason, event_at) -> bool` in
      `session_store.py`. It gives `True` if the event changed the session.
- [x] The check and the write are **one** SQL statement. Two webhook handlers can operate
      at the same time, so a read and then a write has a race. One statement has no race.

```sql
UPDATE sessions
   SET status = ?, error_reason = ?, updated_at = ?,
       last_event_at = COALESCE(?, last_event_at)
 WHERE id = ?
   AND status != 'complete'
   AND (? IS NULL OR last_event_at IS NULL OR last_event_at < ?)
```

- [x] `status != 'complete'` keeps the rule of session 05 in the same statement. The
      route no longer reads the session and then writes it.
- [x] Give `cursor.rowcount > 0` as the result.
- [x] Keep all query SQL in this file.

## Procedure — the route

- [x] `handle_event` in `app/routes/webhooks.py` calls `apply_bot_event`.
- [x] Remove the read of `session.status` and the `complete` test from the route. The
      statement does that work now.
- [x] `False` writes a log line that says the event did not change the session, and the
      time of the event. This line is how you see a late event in the log.
- [x] The map `BOT_EVENT_STATUS`, the `call_ended` rule and the real-time events do not
      change.
- [x] The route keeps giving HTTP 200 for an event that it refuses. A 4xx or a 5xx makes
      Svix retry a message that is correct to ignore.

## Procedure — the tests

- [x] `test_db_migrations.py`: a new file gets the newest version; a file at version 0
      with the old table gets the column and keeps its rows; `init_db()` two times
      changes nothing.
- [x] `test_routes_webhooks.py`: **each of the 24 orders** of the four events of the live
      test gives the status `in_progress`. Use `itertools.permutations` and the true
      timestamps from the table above. This is the test that fails with the code of
      session 05.
- [x] The same event two times changes the session one time. Svix delivers at least one
      time, so a duplicate is normal.
- [x] A late `bot.in_call_not_recording` after `bot.in_call_recording` does not make the
      status `waiting_for_bot` again.
- [x] An event with no `updated_at` is applied. The test webhook of the dashboard has no
      `data.data`, so this is a real shape.
- [x] A status that is `complete` does not change, with a new event or an old one.
- [x] `test_recall_events.py`: `event_at` has the same format for `Z`, for `+00:00` and
      for a different number of decimal digits. A bad value gives `None`.
- [x] All tests of session 05 must pass with no change to them.

## Proof

- [x] `poetry run pytest` in `backend/` passes. The count is more than 66.
- [x] The 24-order test fails if you remove the guard. Prove this, do not assume it: the
      test must show the fault that it protects against.
- [x] `docker compose -f deploy/docker-compose.yml up -d --build`, then a loop on
      `docker inspect --format '{{.State.Health.Status}}' recall-api` gives `healthy`.
      Do not read the value in the same second as the start.
- [x] The database on the named volume keeps its rows through the migration. Method:
      count the rows before and after. This is the item that a fault makes expensive.
- [x] `PRAGMA user_version` in the container gives the newest version.
- [x] `GET /health` gives HTTP 200, and the CORS behavior does not change.
- [x] Each `curl` command runs in the container. Use `curl -i`, not `curl -I`.
- [x] Send the four live events to a test container in the worst order and show that the
      status is `in_progress`.

## Done criteria

- [x] Each of the 24 orders of the four live events gives `in_progress`.
- [x] A duplicate event changes nothing.
- [x] An event with no time is applied.
- [x] The database file on this machine and on the server keeps its rows.
- [x] The tests pass, and the container is healthy.
- [x] `../session-logs/06-event-ordering.md` is complete.

## Out of scope

- A read of the bot from the Recall API to repair a webhook that never arrived. Write it
  in the README as a next step.
- Alembic or another migrations framework. Sam decided this.
- The chat loop, the intake engine, LiteLLM and the TTS code.
- A change to `frontend/`.
- A deploy to the homelab server. Ask Sam first.
- A commit and a push.

## What changed against the plan

- **`session_store.schema_version()` is new.** The plan did not name it. The tests and a
  container check need to read `PRAGMA user_version`, and a route or a test must not have
  SQL in it.
- **The route no longer reads the session status.** The plan said this, and the result is
  better than the plan said: the `complete` rule of session 05 was a read and then a
  write, which has the same race as the ordering fault. It is now one statement with the
  time test.
- **The proof that the test finds the fault gave a number.** With the guard removed, 18 of
  the 24 orders fail. Only 6 are correct. The live call of session 05 was one of the 6.
