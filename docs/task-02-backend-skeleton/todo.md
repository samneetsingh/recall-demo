# Task 2 — Backend skeleton: todo

Written in ASD-STE100 Simplified Technical English.

## Scope

This task starts section 2 of [`../TASKS.md`](../TASKS.md). It does step 1 of the build
order in [`../IMPLEMENTATION.md`](../IMPLEMENTATION.md) only:

- 2b. The SQLite schema: the sessions table.
- 2c. `config.py` with `pydantic-settings`.
- 2d. The Recall API key as an environment variable.
- The three session routes, with stub data and no call to the Recall API.
- The four open questions in [`../API_CONTRACT.md`](../API_CONTRACT.md).

Item 2a, the Poetry project with FastAPI, is complete. Task 1 made it.

This task does not call the Recall API. Item 2e is not complete at the end of this
task: the route makes a session row, but it does not make a bot. Item 2h, the webhook
route, is the next task.

## Start state

A check on 2026-09-19 gave these results:

| Item | Result | Effect on this task |
|---|---|---|
| `backend/app/config.py` | Three plain module constants | Item 1 changes the module to a class |
| `backend/app/main.py` | The application object, CORS and two routes | Item 5 adds the router. The `config` import does not change |
| `backend/poetry.lock` | No `pydantic-settings`, no `pytest`, no `httpx`. `python-dotenv` and `anyio` are in the lock | Poetry must get the three packages |
| `backend/.venv/` | The directory exists | `poetry run pytest` operates on this machine |
| `poetry` | 2.3.3, Python 3.13.1 | Sufficient |
| Docker daemon | Not available at the start. Sam started Docker Desktop | Docker 29.8.0. Sufficient |
| Docker Compose | v5.5.1 | Sufficient |

## Answers from Sam

These answers are decisions. A later session must not make them again.

- **The SQLite file goes on a Docker named volume.** The mount point is `/app/data` in
  the container. The `Dockerfile` makes this directory and gives it to `appuser`, so
  Docker gives the new volume the owner uid 10001 at the first start. The data stays
  through a rebuild. No new directory is on the host file system.
- **The sessions table gets a `mode` column now.** The default is `chat`. This project
  has no migrations framework, so a column that comes later needs a new database file.
- **The project gets pytest now.** pytest is a Poetry development dependency. The
  `Dockerfile` uses `poetry install --only main`, so pytest is not in the image.
- **`GET /sessions/{id}/summary` obeys the 404 rule.** The route gives 404 if the
  status is not `complete`. This agrees with [`../API_REFERENCE.md`](../API_REFERENCE.md).

## New dependencies

Sam must approve this list before the build starts.

| Package | Group | Reason |
|---|---|---|
| `pydantic-settings` | main | Session 02 decided this. Item 2c of `../TASKS.md` |
| `pytest` | dev | Sam approved it in this session |
| `httpx` | dev | **New.** The FastAPI `TestClient` does not operate without it. The plain `fastapi` package does not supply it |

`python-dotenv` is already in the lock file, from `uvicorn[standard]`. `pydantic-settings`
uses it to read `backend/.env`. This adds no new package.

LiteLLM, the Recall SDK and the OpenAI client are not part of this task. Task 3 adds them.

## Files

```
backend/
  pyproject.toml            edit  The three new packages, the pytest configuration
  poetry.lock               edit  Poetry makes this
  Dockerfile                edit  One new line: make /app/data with the owner appuser
  .dockerignore             edit  Ignore data/ and tests/
  deploy/docker-compose.yml edit  The named volume
  .env.example              edit  The new variable names
  app/
    config.py               edit  The Settings class
    main.py                 edit  The lifespan and the router
    db/
      __init__.py           new
      models.py             new   The schema, the Session type and the status values
      session_store.py      new   The read and write helpers. The query SQL
    routes/
      __init__.py           new
      sessions.py           new   The three routes
  tests/
    conftest.py             new   The test database path
    test_session_store.py   new
    test_routes_sessions.py new
```

## Procedure — the configuration

- [x] Run `poetry add pydantic-settings` in `backend/`.
- [x] Write the class `Settings(BaseSettings)` in `app/config.py`.
- [x] Give it these fields: `RECALL_API_KEY`, `OPENAI_API_KEY`, `DB_PATH`,
      `CORS_ORIGINS`, `CORS_METHODS`, `CORS_HEADERS`.
- [x] Make the two API keys empty strings by default. The stub routes do not use them.
      A key that is necessary but absent must stop the application in task 3, not now.
- [x] Make `DB_PATH` a `Path`. The default is `/app/data/recall_demo.sqlite3`, which is
      the container path. A local run without Docker must set `DB_PATH` in `backend/.env`.
- [x] Keep the default values of the three CORS fields the same as the values now.
      `CORS_METHODS` stays `GET, POST, OPTIONS`. The new routes use GET and POST only.
- [x] Set `env_file=".env"` and `extra="ignore"` in the model configuration.
- [x] Make the object `settings = Settings()` at the end of the module.
- [x] Keep the three names `CORS_ORIGINS`, `CORS_METHODS` and `CORS_HEADERS` in the
      module as aliases of the fields of `settings`. The import in `app/main.py` must
      not change. New code uses `settings`.
- [x] Write the names and an example value of each variable in `.env.example`. Tell the
      reader that a list variable uses JSON format, because `pydantic-settings` reads a
      list field as JSON.

## Procedure — the database

- [x] Make `app/db/__init__.py`.
- [x] Write the `CREATE TABLE` statement in `app/db/models.py`:

```sql
CREATE TABLE IF NOT EXISTS sessions (
    id            TEXT PRIMARY KEY,
    meeting_url   TEXT NOT NULL,
    mode          TEXT NOT NULL DEFAULT 'chat',
    status        TEXT NOT NULL DEFAULT 'creating_bot',
    error_reason  TEXT,
    bot_id        TEXT,
    transcript    TEXT NOT NULL DEFAULT '[]',
    summary       TEXT,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);
```

- [x] `../TASKS.md` gives five columns: `id`, `meeting_url`, `status`, the transcript log
      and `summary`. These four columns are more than that list. Each has a reason:
      - `mode` — Sam approved it in this session.
      - `error_reason` — `../IMPLEMENTATION.md` says to keep a short reason with the
        `error` status.
      - `bot_id` — `../API_CONTRACT.md` says to keep the bot id against the session. The
        next task writes it. A column that comes later needs a new database file.
      - `created_at` and `updated_at` — a demo with no timestamps is difficult to debug.
- [x] Put the five status values in `models.py`: `creating_bot`, `waiting_for_bot`,
      `in_progress`, `complete`, `error`. Use the same names as `../IMPLEMENTATION.md`.
- [x] Put the two mode values in `models.py`: `chat` and `voice`.
- [x] Make a `Session` dataclass. Add a function that makes a `Session` from a database
      row. The transcript and the summary are JSON text in the database and Python
      objects in the dataclass.
- [x] Make `app/db/session_store.py`.
- [x] Write a `connect()` function. It makes the parent directory of `DB_PATH`, opens
      the connection and sets the row factory.
- [x] Open a new connection for each call and close it at the end. FastAPI runs a
      synchronous route in a thread pool, and an SQLite connection is not safe in more
      than one thread.
- [x] Write `init_db()`. It runs the statement from `models.py`.
- [x] Write these helpers: `create_session`, `get_session`, `set_status`, `set_summary`,
      `append_turn`.
- [x] Keep all query SQL in this file. `models.py` holds the schema statement only. No
      other module has SQL in it.

## Procedure — the routes

- [x] Make `app/routes/__init__.py`.
- [x] Make `app/routes/sessions.py` with an `APIRouter`.
- [x] Write the request model: `meeting_url` and `mode`. `mode` is `chat` or `voice`,
      and the default is `chat`. A different value gives HTTP 422.
- [x] `POST /sessions` makes a session row with the status `creating_bot`. It gives the
      session id and the status. The response code is 201.
- [x] Write no code that calls the Recall API. Put a comment in the route that tells the
      next task where the create-bot call goes.
- [x] `GET /sessions/{id}` gives the session id, the status and the summary. The summary
      is `null` before the status is `complete`. An unknown id gives 404.
- [x] `GET /sessions/{id}/summary` gives 404 if the id is unknown. It gives 404 with a
      clear message if the status is not `complete`.
- [x] Keep a constant `STUB_SUMMARY` in this module. It has the eight fields of
      `../SPEC.md`. If the status is `complete` and the database has no summary, the
      route gives `STUB_SUMMARY`. Task 3 removes the constant, because the engine then
      writes a real summary. Put this instruction in a comment.
- [x] Keep the route handlers thin. A handler calls `session_store` and gives a
      response. It has no business logic and no SQL in it.

## Procedure — main.py

- [x] Add a lifespan function. It calls `session_store.init_db()` at the start.
- [x] Register the router with `app.include_router(sessions.router)`.
- [x] Do not change the `from app.config import ...` line.
- [x] Keep `main.py` as the application object and the wiring only.

## Procedure — the container

- [x] Add this line to the `Dockerfile`, before the `USER appuser` line:
      `RUN mkdir -p /app/data && chown appuser:appuser /app/data`.
- [x] This is a change to the `Dockerfile`. Session 03 says a new module needs no change
      to it, which stays true. The new line is for the directory of the volume only.
      Docker gives a new named volume the owner and the permissions of the directory in
      the image. Without this line, the volume has the owner root, and `appuser` cannot
      write the database file.
- [x] Add the volume to `deploy/docker-compose.yml`: `db-data:/app/data`, and a
      top-level `volumes:` key. The full name of the volume is `recall-api_db-data`,
      because the project name is `recall-api`.
- [x] Add `data/` and `tests/` to `.dockerignore`. The image does not need them.
- [x] Add `*.sqlite3` to the root `.gitignore`.

## Procedure — the tests

- [x] Run `poetry add --group dev pytest httpx`.
- [x] Add `[tool.pytest.ini_options]` to `pyproject.toml` with `testpaths = ["tests"]`
      and `pythonpath = ["."]`. This makes `import app` operate. It adds no plugin.
- [x] Write `tests/conftest.py`. It sets the `DB_PATH` variable to a temporary file
      before the test modules import the application. A test must not write to the
      database of the container.
- [x] Write `tests/test_session_store.py`: make a session, read it, change the status,
      write a summary, add a turn to the transcript, read an unknown id.
- [x] Write `tests/test_routes_sessions.py`: the three routes, the 404 results, the 422
      result for a bad mode value, and `GET /health`.
- [x] Run `poetry run pytest`. All tests must pass.

## Procedure — the four open questions

- [x] Use the `recall-ai` MCP server. It is authorized and read-only.
- [x] Answer: the delivery mechanism of the real-time transcript, webhook or WebSocket.
- [x] Answer: the audio format for the output audio.
- [x] Answer: chat messages, webhook events or polling.
- [x] Answer: the bot sub-codes for the error states.
- [x] Write each answer in `../API_CONTRACT.md`. Give the method that proved it: the
      name of the tool and the document.
- [x] Use bot schema v1.11. Do not copy a v1 example from an old document.

## Proof

Each step is a command with a result. Sam started Docker Desktop before step 2.
`../session-logs/04-backend-skeleton.md` gives each result.

- [x] `poetry run pytest` in `backend/` passes.
- [x] `docker compose -f deploy/docker-compose.yml up -d --build` makes the image and
      starts the container.
- [x] `docker inspect --format '{{.State.Health.Status}}' recall-api` gives `healthy`.
      Read this value in a loop with an interval. Do not read it in the same second as
      the start.
- [x] The compose file does not publish port 8000 to the host. Each `curl` command runs
      in the container: `docker exec recall-api curl -i ...`. Use `curl -i`. Do not use
      `curl -I`, because it sends HEAD and FastAPI gives HTTP 405.
- [x] `GET /health` gives HTTP 200 and `{"status": "ok"}`.
- [x] A GET with the header `Origin: https://recall.samneet.com` gives the header
      `access-control-allow-origin: https://recall.samneet.com`.
- [x] A GET with an origin that is not in the list gives HTTP 200 and no
      `access-control-allow-origin` header.
- [x] `POST /sessions` with a Google Meet URL gives HTTP 201 and a session id.
- [x] `GET /sessions/{id}` gives HTTP 200, the status `creating_bot` and a null summary.
- [x] `GET /sessions/{id}/summary` gives HTTP 404, because the status is not `complete`.
- [x] A command with `docker exec` sets the status to `complete` through
      `session_store`, not with SQL. `GET /sessions/{id}/summary` then gives HTTP 200
      and the eight fields.
- [x] `ls -l /app/data` in the container shows the database file with the owner
      `appuser`.
- [x] `docker compose restart` keeps the data. `GET /sessions/{id}` gives the same row.
- [x] `docker compose down` and `up -d --build` keeps the data. This proves the volume,
      not only the restart.

## Done criteria

- [x] `backend/app/config.py` is a `pydantic-settings` class, and the import in
      `app/main.py` is the same as before.
- [x] The sessions table exists in the database file on the named volume.
- [x] All SQL is in `app/db/`. The routes have no SQL in them.
- [x] The three routes give the correct results, as the proof section shows.
- [x] The container is healthy, and the CORS behavior is the same as task 1.
- [x] The tests pass.
- [x] The four questions in `../API_CONTRACT.md` have an answer and a method.
- [x] These items of section 2 of `../TASKS.md` show as complete: 2a, 2b, 2c, 2d and the
      "get session status" item. Item 2e ("creates a Recall bot"), the summary item and
      item 2h stay open, because they need the Recall API and the engine.
- [x] The session log `../session-logs/04-backend-skeleton.md` is complete.

## Out of scope

These items are for a later task:

- `recall/client.py`, `recall/events.py` and `routes/webhooks.py`. Task 2, part 2.
- The intake engine, the prompts, LiteLLM and the TTS code.
- A migrations framework. `CLAUDE.md` refuses one for this demo.
- A change to `frontend/`.
- A deploy to the homelab server. Sam must approve a deploy first. This session tests
  on the local machine only.
- A commit and a push. The changes stay in the working tree for Sam.
