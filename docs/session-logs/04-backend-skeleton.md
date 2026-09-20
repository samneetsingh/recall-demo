# 04 — Backend skeleton

Written in ASD-STE100 Simplified Technical English.

- **Date:** 2026-09-19
- **Task:** Section 2 of [`../TASKS.md`](../TASKS.md), step 1 of the build order in
  [`../IMPLEMENTATION.md`](../IMPLEMENTATION.md)
- **Result:** complete — the database, the configuration and the three stub routes
  operate in the container. The four open questions in
  [`../API_CONTRACT.md`](../API_CONTRACT.md) have an answer.

## Summary

The session changed `config.py` to a `pydantic-settings` class, made the SQLite sessions
table on a Docker named volume, and made the three session routes with stub data. No
code in this session calls the Recall API. The session also answered the four open
questions in `../API_CONTRACT.md` with the `recall-ai` MCP server. The session did not
change `frontend/`, and it did not deploy to the homelab server.

## Files changed

| File | Change | Reason |
|---|---|---|
| `backend/app/config.py` | edit | The `Settings` class. The three CORS names stay as aliases |
| `backend/app/db/__init__.py` | new | The database package |
| `backend/app/db/models.py` | new | The schema statement, the `Session` type, the status and mode values |
| `backend/app/db/session_store.py` | new | The read and write helpers. All query SQL |
| `backend/app/routes/__init__.py` | new | The route package |
| `backend/app/routes/sessions.py` | new | The three routes and `STUB_SUMMARY` |
| `backend/app/main.py` | edit | The lifespan that makes the table, and the router |
| `backend/Dockerfile` | edit | Make `/app/data` with the owner `appuser` |
| `backend/deploy/docker-compose.yml` | edit | The named volume `db-data` on `/app/data` |
| `backend/.dockerignore` | edit | Ignore `tests/` and `data/` |
| `backend/.env.example` | edit | `DB_PATH` and the CORS variables, with the JSON format |
| `backend/pyproject.toml` | edit | `pydantic-settings`, `pytest`, `httpx`, the pytest configuration |
| `backend/poetry.lock` | edit | Poetry wrote it |
| `backend/tests/conftest.py` | new | The temporary test database |
| `backend/tests/test_session_store.py` | new | 9 tests of the helpers |
| `backend/tests/test_routes_sessions.py` | new | 9 tests of the routes |
| `.gitignore` | edit | `*.sqlite3` |
| `docs/API_CONTRACT.md` | edit | The four answers, and the webhook configuration item |
| `docs/API_REFERENCE.md` | edit | HTTP 201 on POST, and the `error_reason` field |
| `docs/TASKS.md` | edit | The items of section 2 that now pass |
| `docs/task-02-backend-skeleton/todo.md` | new | The plan of this session |
| `docs/session-logs/04-backend-skeleton.md` | new | This log |

## Decisions

Sam made the first four decisions in this session. A later session must not make them
again.

- **The SQLite file goes on a Docker named volume, `recall-api_db-data`.** The mount
  point is `/app/data`. The data stays through a rebuild of the image. No new directory
  is on the host file system.
- **The sessions table has a `mode` column now.** The default is `chat`. This project has
  no migrations framework, so a column that comes later needs a new database file.
- **The project has pytest, as a development dependency.** `poetry install --only main`
  in the `Dockerfile` keeps it out of the image.
- **`GET /sessions/{id}/summary` gives 404 until the status is `complete`.** This agrees
  with `../API_REFERENCE.md`.
- **`app/config.py` keeps the three names `CORS_ORIGINS`, `CORS_METHODS` and
  `CORS_HEADERS` as module aliases.** The import in `app/main.py` does not change, which
  was a condition of the task. New code reads the object `settings`.
- **The table has four columns more than `../TASKS.md` lists:** `mode`, `error_reason`,
  `bot_id`, `created_at` and `updated_at`. `error_reason` and `bot_id` come from
  `../IMPLEMENTATION.md` and `../API_CONTRACT.md`. Each necessary column must exist now,
  because there is no migrations framework.
- **The schema statement is in `models.py`. All query SQL is in `session_store.py`.** No
  other module has SQL in it. A route handler calls a helper.
- **Each helper opens a new connection and closes it.** FastAPI runs a synchronous route
  handler in a thread pool, and one SQLite connection is not safe in more than one
  thread.
- **The session id is a full `uuid4().hex`, 32 characters.** `../API_REFERENCE.md` shows
  a short example id, but a short id has a risk of a collision and gives no benefit.
- **`POST /sessions` gives HTTP 201, not 200.** The route makes a resource. The frontend
  does not exist yet, so no code depends on 200. `../API_REFERENCE.md` now says 201.
- **`GET /sessions/{id}` gives an `error_reason` field.** `../IMPLEMENTATION.md` says the
  frontend shows the reason text to the user, so the frontend must be able to read it.
  `../API_REFERENCE.md` now has the field.
- **`STUB_SUMMARY` is a constant in `routes/sessions.py`.** The route gives it when the
  status is `complete` and the database holds no summary. The task that makes
  `engine/summary.py` removes the constant. A comment in the file says this.
- **The tests set `DB_PATH` to a temporary file in `conftest.py`, before the import of
  the application.** `app.config` reads the environment one time, at its import. An
  environment variable has precedence over the value in `backend/.env`.

## Verified facts

- **The 18 tests pass.** Method: `poetry run pytest -q` in `backend/`. The result is
  `18 passed`.
- **The container builds and becomes healthy.** Method:
  `docker compose -f deploy/docker-compose.yml up -d --build`, then a loop on
  `docker inspect --format '{{.State.Health.Status}}' recall-api`. The result is
  `healthy` after approximately 8 seconds. `docker ps` shows `Up 12 seconds (healthy)`.
- **`GET /health` gives HTTP 200 and `{"status":"ok"}`.** Method:
  `docker exec recall-api curl -i -s http://localhost:8000/health`. The compose file does
  not publish port 8000 to the host, so each check runs in the container.
- **The CORS behavior did not change.** Method: `docker exec recall-api curl -i -s -H
  'Origin: ...' http://localhost:8000/health`. The origin `https://recall.samneet.com`
  gives `access-control-allow-origin: https://recall.samneet.com` and `vary: Origin`.
  The origin `https://evil.example.com` gives HTTP 200 with no
  `access-control-allow-origin` header, which agrees with session 03.
- **The preflight request for `POST /sessions` is successful.** Method:
  `curl -i -X OPTIONS -H 'Origin: https://recall.samneet.com' -H
  'Access-Control-Request-Method: POST' http://localhost:8000/sessions`. The result is
  HTTP 200 with `access-control-allow-methods: GET, POST, OPTIONS`. `CORS_METHODS` needs
  no change for the new routes.
- **`POST /sessions` gives HTTP 201 and a session id.** Method: a `curl` command with the
  body `{"meeting_url":"https://meet.google.com/abc-defg-hij","mode":"chat"}`. The result
  is `{"session_id":"e3c6d93f02f241a89c78837956a67432","status":"creating_bot"}`.
- **A bad `mode` value gives HTTP 422.** Method: the same command with
  `"mode":"telepathy"`.
- **`GET /sessions/{id}` gives the status.** Method: a `curl` command. The result is
  `{"session_id":"...","status":"creating_bot","summary":null,"error_reason":null}`. An
  unknown id gives HTTP 404.
- **`GET /sessions/{id}/summary` gives 404 before the session is complete.** Method: a
  `curl` command. The result is
  `{"detail":"the session is not complete, the status is creating_bot"}`.
- **`GET /sessions/{id}/summary` gives the eight fields when the session is complete.**
  Method: `docker exec recall-api python -c "..."` with `session_store.append_turn` two
  times and `session_store.set_status(..., 'complete')`, then a `curl` command. The
  result is HTTP 200 and the `STUB_SUMMARY` object. The command used the helpers, not
  SQL.
- **`appuser` owns the database file.** Method: `docker exec recall-api ls -l /app/data`
  gives `-rw-r--r-- 1 appuser appuser 12288 recall_demo.sqlite3`. `docker exec recall-api
  id` gives `uid=10001(appuser)`. The line in the `Dockerfile` that makes `/app/data`
  gives the correct owner to the new volume.
- **The data stays after a restart and after a rebuild.** Method:
  `docker compose restart`, then `docker compose down` and `up -d --build`. After each
  one, `GET /sessions/{id}` gives HTTP 200 and the same row with the status `complete`.
  The rebuild is the stronger proof: a new image, the same data.
- **pytest is not in the image.** Method: `docker exec recall-api python -c "import
  pytest"` gives `ModuleNotFoundError`. `poetry install --only main` keeps the
  development group out.
- **The volume `recall-api_db-data` exists.** Method:
  `docker volume ls --filter name=recall-api`.
- **The workspace has no dashboard webhook endpoint.** Method: `recall-ai` MCP,
  `list_webhook_endpoints` gives an empty list. The next task needs this endpoint.

## Corrections

- **Wrong:** Poetry writes a development dependency to
  `[tool.poetry.group.dev.dependencies]`. **Correct:** Poetry 2.3.3 writes it to the
  `[dependency-groups]` table, which is the PEP 735 format. `poetry install --only main`
  operates the same way with this format. Do not look for the old table in
  `pyproject.toml`.
- **Wrong:** The local Python is 3.13, the same as the image. **Correct:**
  `backend/.venv` is Python 3.14, but the image is `python:3.13-slim`. `pyproject.toml`
  says `python = "^3.13"`, which permits both. The tests on the local machine thus do not
  run on the version of the container. The code uses no new syntax, and the tests in the
  container are not necessary at this time. Look at this again if a test result and the
  container are different.

## Open items

- [ ] Commit and push the changes of this session. Owner: Sam.
- [ ] `backend/.env` on the homelab server, and a new deploy of the backend stack. Owner:
      Sam. The stub routes do not need the keys, but the next task does.
- [ ] A dashboard webhook endpoint in the Recall dashboard, with the URL
      `https://recall-api.ss-ubuntu-01.net/webhooks/recall`. Owner: Sam. A human must do
      this in the dashboard. The next task needs it for the bot status events.
- [ ] Starlette says that `httpx` with `TestClient` is deprecated, and it tells you to
      install `httpx2`. The 18 tests pass with a warning only. Change the dependency if
      the warning becomes an error. Owner: the next session that touches the tests.
- [ ] The `Upgrade` and `Connection` headers in the nginx configuration. Owner: Sam.
      `../API_CONTRACT.md` says that the real-time transcript can use a webhook, so this
      item is no longer a condition for mode 2. Keep it as an option.
- [ ] The two `overseerr` files in `~/docker/nginx-proxy/conf.d.disabled/`. Owner: Sam.

## Next session starts here

Do part 2 of section 2 of [`../TASKS.md`](../TASKS.md): the Recall connection.

1. Make `app/recall/client.py`. Put the create-bot call in it. Use bot schema v1.11.
   `../API_CONTRACT.md` has the correct `recording_config` shape, with the real-time
   endpoint and the chat message event.
2. Make `app/routes/webhooks.py` and `app/recall/events.py`. Verify each request with the
   workspace verification secret before you read the payload.
   `dashboard_uses_workspace_verification_secret` is true, so one secret is sufficient
   for the dashboard events and the real-time events.
3. Change `POST /sessions` to make the bot and to keep the bot id with
   `session_store`. The place for the call has a comment in `routes/sessions.py`.
4. Make a helper `set_bot_id` in `session_store.py`. The column exists, but no helper
   writes it.
5. Sam must make the dashboard webhook endpoint first. See the open items.

Do not change `frontend/` in the same turn as a `backend/` task. Ask Sam before a deploy
to the homelab server.
