# 02 — Backend container and CORS

Written in ASD-STE100 Simplified Technical English.

- **Date:** 2026-09-19
- **Task:** Section 1 of [`../TASKS.md`](../TASKS.md), items 1b and 1d
- **Result:** partial — the backend container operates on the local machine. The
  deploy to the homelab server is not done.

## Summary

The session made the backend Poetry project, the FastAPI placeholder application, the
Dockerfile and the Compose stack. The session added the CORS configuration for the
frontend origin. The session built the image and started the stack on the local
machine. The `/health` route gives HTTP 200. The session did not change `frontend/` and
did not deploy to the homelab server.

## Files changed

| File | Change | Reason |
|---|---|---|
| `backend/pyproject.toml` | new | The Poetry project. fastapi and uvicorn[standard] |
| `backend/poetry.lock` | new | The exact versions. The Docker build uses this file |
| `backend/app/__init__.py` | new | The application package |
| `backend/app/main.py` | new | The FastAPI application, middleware, `GET /` and `GET /health` |
| `backend/app/config.py` | new | The configuration values. Plain module constants |
| `backend/Dockerfile` | new | The container image. Two stages, curl for the healthcheck |
| `backend/.dockerignore` | new | Keeps the build context small and the secrets out |
| `backend/deploy/docker-compose.yml` | new | The `recall-api` stack |
| `backend/.env.example` | new | The names of the environment variables |
| `.gitignore` | edit | One root file. Keeps `.env`, `.venv/` and caches out of git |
| `docs/task-01-infra/todo.md` | edit | Marked the completed items |
| `docs/IMPLEMENTATION.md` | edit | Named `pydantic-settings` for `config.py` in task 2 |
| `docs/TASKS.md` | edit | Added the `config.py` migration to section 2 |
| `docs/session-logs/02-backend-container.md` | new | This log |

## Decisions

- **The Poetry project uses `package-mode = false`.** The application is not a library.
  Only the dependencies are necessary. This mode needs no name, no version and no
  README. The Dockerfile copies `app/` directly.
- **The Dockerfile has two stages.** Stage 1 installs Poetry and makes the virtual
  environment in `/app/.venv`. Stage 2 copies only that environment. Poetry, pip and
  the caches stay out of the final image. The image is 274 MB with curl.
- **Poetry is a build tool, not a new project dependency.** It is in the builder stage
  only. `pyproject.toml` has fastapi and uvicorn[standard] only.
- **The user is `appuser`, uid 10001.** A high uid does not conflict with a user on the
  host.
- **The healthcheck uses curl. The image installs curl.** The slim image has no curl
  and no wget. The first version of the healthcheck used the Python interpreter. Sam
  refused it. curl costs 15.6 MB, and it gives two things that are worth more than the
  space: the healthcheck is one readable line, and you can debug the container from the
  inside. `docker exec recall-api curl -v http://localhost:8000/health` tells you if the
  fault is in the application or in the network. There is no SSH access to the homelab
  server from a session, so this debug path has real value.
- **`env_file` has `required: false`.** The stack starts when `backend/.env` does not
  exist. This lets the local check operate with no secrets.
- **The CORS method list and header list are exact.** The origin list must not use the
  `*` character. The method list and the header list use the same rule. Starlette adds
  the browser-safelisted headers to the response. Add to these lists when a route in
  task 2 needs more.
- **`allow_credentials` is `true`.** A wildcard origin is not permitted with
  credentials. The exact origin list satisfies this rule.
- **The localhost origin is port 8787.** This is the default port of `wrangler dev`.
  `http://127.0.0.1:8787` is a different origin to the browser, so both are in the list.
- **There is one `.gitignore`, in the repository root.** git reads every `.gitignore`
  in the tree and the rules add together. There is no inheritance and no override. A
  pattern with no slash matches at any depth, so the root rule `.env` catches
  `backend/.env`. A per-directory `.gitignore` is the usual pattern in a large
  monorepo, because it keeps the rules near the code and anchors them with a leading
  slash. This repository has two directories and one author. Three files to hold seven
  rules is overhead. Add `frontend/.gitignore` later, if the Worker gets a build
  pipeline with many artifacts. The rule in `CLAUDE.md` to keep `backend/` and
  `frontend/` separate is about runtime coupling, imports and deploys. A shared
  `.gitignore` makes no runtime coupling.
- **The configuration is in `app/config.py`, not in `main.py` and not in a YAML
  file.** `main.py` must hold the application object and the wiring only.
  `docs/IMPLEMENTATION.md` already specified `config.py`, so this module is the
  documented home.
- **A YAML configuration file is refused.** Three reasons. The file ships in the image,
  so a change needs a rebuild and gives no dynamism. It cannot hold the secrets, which
  are most of the configuration, so the environment variables stay and you get two
  systems. It has no validation, so a typo gives a fault at run time. YAML is correct
  for structured non-secret data that a person tunes, for example an intake question
  tree. It is not correct for infrastructure configuration.
- **Task 1 uses plain module constants. Task 2 changes them to
  `pydantic-settings`.** The constants cost no dependency and they set the import
  pattern now. `pydantic-settings` gives types that are checked at start, an `.env`
  file read and a list parsed from an environment variable. It earns its dependency
  when the API keys and the database path arrive, which is task 2.
- **`CORS_METHODS` and `CORS_HEADERS` are constants, not configuration.** They change
  when a route changes. A route change is a code change. Only `CORS_ORIGINS` becomes an
  environment variable in task 2.
- **The migration is now in the documents.** `docs/IMPLEMENTATION.md` names
  `pydantic-settings` in the module layout and in step 1 of task 2.
  `docs/TASKS.md` section 2 has a checkbox for it. Task 2 must not decide this again.
- **The done criterion "The session log is complete" stays open.** The frontend session
  and the deploy session each need a log. Mark this criterion at the end of task 1.

## Verified facts

- **The Compose network name is `recall-api_default`.** Method:
  `docker compose -f deploy/docker-compose.yml config`. The output shows
  `networks: default: name: recall-api_default`.
- **The image builds and the container starts.** Method:
  `docker compose -f deploy/docker-compose.yml up -d --build`. The output shows
  `Network recall-api_default Created` and `Container recall-api Started`.
- **`/health` gives HTTP 200 and `{"status": "ok"}`.** Method:
  `docker compose -f deploy/docker-compose.yml exec -T api curl -sS
  http://127.0.0.1:8000/health`.
- **`/` gives HTTP 200 and the placeholder response.** Method: the same command on the
  `/` route. The body is
  `{"service":"recall-demo-backend","status":"placeholder","docs":"/docs"}`.
- **The nginx path operates.** Method:
  `docker run --rm --network recall-api_default curlimages/curl -sS
  http://recall-api:8000/health`. The result is HTTP 200. A second container on the
  network finds the container by the name `recall-api`. The nginx stack uses the same
  path.
- **The healthcheck passes.** Method: `docker compose ps` gives `Up (healthy)`.
  `docker inspect --format '{{json (index .State.Health.Log 0)}}' recall-api` gives
  `ExitCode: 0` and the output `{"status":"ok"}`.
- **The healthcheck detects a fault.** Method:
  `docker compose exec -T api curl -fsS http://127.0.0.1:8000/nope`. The exit code is
  22. The `-f` option makes curl give a non-zero exit code when the status is 400 or
  more, so Docker marks a sick container as unhealthy.
- **The port is not published to the host.** Method: `curl http://localhost:8000/health`
  on the host gives no connection. `docker inspect` shows `{"8000/tcp":null}`.
- **The process is not root.** Method: `docker compose exec -T api id`. The result is
  `uid=10001(appuser) gid=10001(appuser)`.
- **Poetry is not in the runtime image.** Method:
  `docker compose exec -T api sh -c 'command -v poetry'`. The command finds nothing.
- **The CORS preflight from `https://recall.samneet.com` is successful.** Method:
  `curl -X OPTIONS http://recall-api:8000/health -H 'Origin: https://recall.samneet.com'
  -H 'Access-Control-Request-Method: POST' -H 'Access-Control-Request-Headers:
  content-type'`. The result is HTTP 200 with
  `access-control-allow-origin: https://recall.samneet.com`,
  `access-control-allow-methods: GET, POST, OPTIONS` and
  `access-control-allow-credentials: true`.
- **The CORS preflight from `http://localhost:8787` is successful.** Method: the same
  command with the localhost origin. The result is HTTP 200 with the matched origin.
- **An origin that is not in the list is refused.** Method: the same command with
  `Origin: https://evil.example.com`. The result is HTTP 400 with no
  `access-control-allow-origin` header. The browser stops the request.
- **The root `.gitignore` covers `backend/`.** Method: `git check-ignore -v`.
  `backend/.env` matches `.gitignore:4:.env`. `backend/.venv` matches
  `.gitignore:7:.venv/`. `backend/app/__pycache__/x.pyc` matches
  `.gitignore:8:__pycache__/`. `backend/.env.example` stays tracked, because the
  pattern `.env` is an exact match and does not match `.env.example`.
- **curl is not in `python:3.13-slim`, and it costs 15.6 MB.** Method:
  `docker run --rm python:3.13-slim sh -c 'command -v curl'` finds nothing.
  `apt-get install --no-install-recommends curl` reports
  `After this operation, 15.6 MB of additional disk space will be used`. The image goes
  from 255 MB to 274 MB.
- **The configuration refactor changed no behavior.** Method: rebuild, then the same
  CORS checks. `https://recall.samneet.com`, `http://localhost:8787` and
  `http://127.0.0.1:8787` each give HTTP 200 with the origin returned.
  `https://evil.example.com` gives HTTP 400 with no `access-control-allow-origin`
  header. `/health` and `/` each give HTTP 200.
- **`config.py` is in the image.** Method:
  `docker compose exec -T api ls -1 /app/app/`. The output is `__init__.py`,
  `config.py`, `main.py`. The Dockerfile copies the whole `app` directory, so a new
  module needs no Dockerfile change.
- **`pydantic-settings` was not in the documents before this session.** Method:
  `grep -rn "pydantic.settings" docs/ backend/`. The only hits were in the optional
  extras metadata of fastapi in `poetry.lock`. That metadata is not a dependency of
  this project.
- **`backend/.env` is ignored.** Method: `git check-ignore -v backend/.env` gives
  `.gitignore:4:.env`. The file is on the local machine and will not go into git.
- **The `recall-ai` MCP server is authorized and operates.** Method:
  `get_info`. The user is Sam Singh. The organization is
  `Samneet Singh (Candidate)`. The workspace is `Sandbox`,
  id `871468b0-0115-4ac8-b3fe-bcaf2febb9e5`.
- **The workspace supports bot schema v1.11 only.** Method: `get_info`.
  `supported_bot_schema_versions` is `["v1.11"]` and
  `legacy_compatibility_enabled` is `false`. Task 2 must write v1.11 payloads. Do not
  copy a v1 example from an old document.
- **Dashboard webhooks use the workspace verification secret.** Method: `get_info`.
  `dashboard_uses_workspace_verification_secret` is `true`. Task 2 verifies the
  signature against that secret. `get_webhook_verification_secret` gives it.
- **The resolved dependency versions are fastapi 0.141.1 and uvicorn 0.53.0.** Method:
  `poetry add fastapi "uvicorn[standard]"`. The versions are in `poetry.lock`.
- **Docker Desktop was not in operation at the start of the session.** Method:
  `docker compose up` gave `Cannot connect to the Docker daemon`. `open -a Docker`
  corrected this.

## Corrections

- **Wrong:** The session log 01 said the Compose key `name: recall-api` makes the
  network `recall-api_default`, but gave no test of a real stack. **Correct:** The
  statement is true. A real `docker compose up` made the network with this name.
- **Wrong:** The session started to make changes when Sam asked a question about the
  design. **Correct:** A question is not an instruction. Answer the question first.
  Make the change after the decision.
- **Wrong:** The first `main.py` held the CORS lists directly.
  **Correct:** `docs/IMPLEMENTATION.md` already specified `app/config.py`. Read the
  module layout in that document before you put a value in `main.py`.

## Open items

- [ ] Copy `backend/` to the homelab server and start the stack. Owner: Sam. This
      session had no SSH access to the server.
- [ ] Restart the nginx stack after the first start of the backend stack. Owner: Sam.
      The network `recall-api_default` does not exist before the first start.
- [ ] Check `https://recall-api.ss-ubuntu-01.net/health` from outside the network.
      Owner: Sam.
- [ ] The tunnel configuration for `recall-api.ss-ubuntu-01.net`. Owner: Sam.
- [ ] `backend/.env` on the homelab server. Owner: Sam. Copy `.env.example` and put the
      values in it. Task 2 needs the keys. The placeholder routes do not need them.
- [ ] The frontend Worker, item 1c. Owner: the next session.
- [ ] Approval for `wrangler deploy`. Owner: Sam. The command changes a live domain.
- [ ] Section 1 of `../TASKS.md` is not changed. Owner: the deploy session. Mark items
      1b, 1c and 1d when the live URLs give HTTP 200.
- [ ] The four open questions in [`../API_CONTRACT.md`](../API_CONTRACT.md). Owner: the
      task 2 session. The `recall-ai` MCP server is authorized and can answer them.

## Next session starts here

Build the frontend Worker. Follow the frontend procedure in
[`../task-01-infra/todo.md`](../task-01-infra/todo.md).

1. Make `frontend/package.json` with `wrangler` as a development dependency.
2. Make `frontend/wrangler.jsonc` with the content in the todo file.
3. Make `frontend/public/index.html`.
4. Run `npx wrangler deploy --dry-run`.
5. Ask Sam for approval before `npx wrangler deploy`.

Do not change `backend/` in the same turn as a `frontend/` task.

For task 2: `backend/app/config.py` exists with plain module constants. Change it
to a `pydantic-settings` `BaseSettings` class. Add the `pydantic-settings`
dependency. The import in `app/main.py` does not change.
