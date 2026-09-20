# 06 — Out-of-order webhook events

Written in ASD-STE100 Simplified Technical English.

- **Date:** 2026-09-20
- **Task:** A fault that the live test of
  [`05-recall-connection.md`](05-recall-connection.md) found. See
  [`../task-02-event-ordering/todo.md`](../task-02-event-ordering/todo.md)
- **Result:** complete — the webhook handler no longer uses the order of arrival. The
  database has a schema version, and the migration kept the rows of the container.

## Summary

The live call of session 05 showed that Recall delivers the bot status events out of
order. The handler was last-write-wins, so a late event could put an old status on a
session. This session made the handler use the time of the event, added a
`last_event_at` column, and gave the database a schema version with `PRAGMA
user_version`. The tests went from 66 to 112. The session added no dependency, and it
did not change `frontend/`.

## Files changed

| File | Change | Reason |
|---|---|---|
| `backend/app/db/models.py` | edit | `MIGRATIONS`, and `last_event_at` on `Session` |
| `backend/app/db/session_store.py` | edit | `init_db` applies the migrations. `schema_version`, `apply_bot_event` |
| `backend/app/recall/events.py` | edit | `event_at` on `RecallEvent`, and `_event_time` |
| `backend/app/routes/webhooks.py` | edit | The guarded write. The route keeps no state rule |
| `backend/tests/test_db_migrations.py` | new | 5 tests of the version and the migration |
| `backend/tests/test_routes_webhooks.py` | edit | The 24 orders, the duplicate, and the late event |
| `backend/tests/test_recall_events.py` | edit | The format of `event_at` |
| `docs/API_REFERENCE.md` | edit | The order of the events does not change the result |
| `docs/task-02-event-ordering/todo.md` | new | The plan of this session |
| `docs/session-logs/06-event-ordering.md` | new | This log |

`Dockerfile`, `deploy/docker-compose.yml`, `pyproject.toml` and `poetry.lock` did not
change. This session added no package.

## Decisions

- **The time of the event decides, not the order of arrival.** A bot status event carries
  `data.data.updated_at`. The handler applies an event only if it is newer than the last
  event that the session applied. This is correct for a duplicate too, which matters
  because Svix delivers at least one time.
- **A rank of the statuses was refused.** It is smaller, but it puts the lifecycle of
  Recall in our code, and that model is already wrong: `bot.in_call_not_recording` also
  comes **after** `bot.in_call_recording` when a recording is paused. A rank would refuse
  that event with no trace, and it breaks when Recall adds a status. This is the same
  reason that `sub_code` is not an enum.
- **A read of the bot from the Recall API was refused for this task.** It is more
  correct, and it also repairs a webhook that never arrived, but it puts an HTTP call in
  the write path and makes the status depend on the availability of Recall. It is a next
  step in the README, not in this task.
- **The database has a schema version with `PRAGMA user_version`. There is no Alembic.**
  SQLite holds the version in the file. A list of statements in order is approximately 20
  lines and no new package. `CLAUDE.md` refuses a migrations framework, and this is not
  one. A framework for one table invites the opposite criticism.
- **A migration entry that shipped must never change and must never be removed.** A
  database in use has applied it. A change goes at the end of the list. A comment in
  `models.py` says this.
- **The test and the write are one SQL statement.** Two webhook handlers can operate at
  the same time. The live log shows answers of 132 ms to 153 ms that overlap. A read and
  then a write has a race, and one statement has none. The `complete` rule of session 05
  moved into the same statement for this reason: it had the same fault.
- **An event with no time is applied.** The test webhook of the dashboard has no
  `data.data`. A true event that is lost is worse than an event in the wrong order.
- **A refused event gives HTTP 200.** A 4xx or a 5xx makes Svix retry a message that is
  correct to ignore.
- **The time is put in one format before it is stored.** Recall can write `Z` or
  `+00:00`. The SQL compares the values as text, so each value must have one shape.

## Verified facts

- **The 112 tests pass.** Method: `poetry run pytest -q` in `backend/`. Session 05 had
  66. The 66 tests of session 05 pass with no change to them.
- **The test finds the fault that it protects against.** Method: remove the time
  condition from the SQL statement, then run the test. The result is
  `19 failed, 6 passed`. 18 of the 24 orders of the four live events fail. Only 6 are
  correct. **The live call of session 05 was one of the 6.** After the restore of the
  condition, all 112 tests pass.
- **The migration keeps the data in the container.** Method: read the database on the
  named volume before and after `docker compose up -d --build`. Before: 3 rows,
  `user_version` 0, 10 columns. After: 3 rows, `user_version` 2, 11 columns, and each row
  has the same `status` and `error_reason`. This is the item that a fault makes
  expensive.
- **A file at version 0 takes every migration in one call.** Method:
  `tests/test_db_migrations.py` makes a file with the schema of task 2, puts a row in it,
  and calls `init_db()` one time. The version becomes 2, the column exists, and the row
  keeps its values.
- **`init_db()` two times changes nothing.** Method: a test. The lifespan calls it at
  each start of the container.
- **The container builds and becomes healthy.** Method:
  `docker compose -f deploy/docker-compose.yml up -d --build`, then a loop on
  `docker inspect --format '{{.State.Health.Status}}' recall-api`. The result is
  `Up 6 seconds (healthy)`.
- **`GET /health` gives HTTP 200, and the CORS behavior did not change.** Method:
  `docker exec recall-api curl -i -s ...`. The origin `https://recall.samneet.com` gives
  `access-control-allow-origin`. An origin that is not in the list does not.
- **The four live events in the worst order give the correct status.** Method: a
  throwaway container, and the four events of the live call signed and sent newest first.
  The result is `in_progress`. The log gives
  `did not take event bot.in_call_not_recording of 2026-09-20T05:47:04.532000+00:00` for
  each of the three refused events, and each answer is HTTP 200.

## Corrections

- **Wrong:** the `complete` test in the route was safe. **Correct:** it was a read and
  then a write, which has the same race as the ordering fault. Two handlers can read
  `in_progress` at the same time and both write. It is now part of the one statement.
- **Wrong:** a text comparison of the times from Recall is safe. **Correct:** it is safe
  only if each value has one shape. Recall can write `Z` or `+00:00`, and a different
  number of decimal digits. `_event_time` puts each value in one format first, and a test
  proves that three ways to write the same moment give the same text.

## Open items

- [ ] Commit and push the changes of this session. Owner: Sam.
- [ ] Deploy to the homelab server. Owner: Sam. The server has the code of session 05.
      The migration applies at the start of the container and keeps the rows, as the
      local container proved.
- [ ] A read of the bot from the Recall API on each status event. This repairs a webhook
      that never arrived, which the time guard does not do. Write it in the README as a
      next step. Owner: the docs pass of section 9.
- [ ] Starlette says that `httpx` with `TestClient` is deprecated. The 112 tests pass with
      a warning only. Owner: the next session that touches the tests.

## Next session starts here

Do section 3 of [`../TASKS.md`](../TASKS.md): the mock intake engine. It needs no Recall
call, and it is testable with a scripted conversation.

1. Make `app/engine/prompts.py` with all the prompt text. No prompt text in another
   module.
2. Make `app/engine/intake.py`. It takes the conversation log and gives the next question
   or a signal that the intake is complete.
3. Make `app/engine/summary.py`. It takes the log and gives the eight fields of
   `../SPEC.md`.
4. LiteLLM is a new dependency. Flag it to Sam and wait for the answer.
5. Test the engine standalone, with no Recall and no webhook.

Do not change `frontend/` in the same turn as a `backend/` task. Ask Sam before a deploy
to the homelab server.
