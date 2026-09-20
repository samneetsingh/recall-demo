# 02 — Backend container and CORS

Written in ASD-STE100 Simplified Technical English.

- **Date:** 2026-09-19
- **Task:** Section 1 of [`../TASKS.md`](../TASKS.md), items 1b and 1d
- **Result:** complete for 1b and 1d — `https://recall-api.ss-ubuntu-01.net/health`
  gives HTTP 200 from outside the network. Item 1c, the frontend Worker, is not
  started.

## Summary

The session made the backend Poetry project, the FastAPI placeholder application, the
Dockerfile and the Compose stack. The session added the CORS configuration for the
frontend origin. Sam deployed the stack to the homelab server and corrected two faults
in the external infrastructure with commands from the session. Items 1b and 1d are
complete: `https://recall-api.ss-ubuntu-01.net/health` gives HTTP 200 from outside the
network. The session did not change `frontend/`.

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
- **The backend stack operates on the homelab server.** Method: the server pulled
  commit `1adcd6c` with `git clone` over SSH into `~/docker/recall-demo`.
  `docker compose -f deploy/docker-compose.yml up -d --build` gave
  `Network recall-api_default Created` and `Up (healthy)`.
  `docker exec recall-api curl -sS http://127.0.0.1:8000/health` gave
  `{"status":"ok"}`.
- **The internal path from nginx to the container operates.** Method:
  `docker exec nginx curl -sS http://recall-api:8000/health` on the server gives
  `{"status":"ok"}`. The nginx stack is at `~/docker/nginx-proxy`. It is plain
  `nginx:alpine` with files in `conf.d/`, not an automatic proxy image. It joins
  `recall-api_default` as an external network. The file
  `conf.d/recall-api.ss-ubuntu-01.net.conf` sends the requests to
  `http://recall-api:8000`.
- **The server has Docker Compose v2.39.4.** Method: `docker compose version`. This
  version accepts the long `env_file` syntax, which needs 2.24 or more.
- **A `proxy_pass` to a container that does not operate stops all of nginx.** Method:
  the restart of the nginx stack gave
  `[emerg] host not found in upstream "overseerr"`, and the container went into a
  restart loop. nginx resolves a `proxy_pass` host name at the time it reads the
  configuration. One container that is not in operation stops the full proxy. nginx
  had been in operation from before that container stopped, so the restart showed a
  fault that was already there. Start the backend stack, then look at
  `docker logs nginx` after the restart of the nginx stack. Do not assume that the
  restart is successful.
- **The DNS record for `recall-api.ss-ubuntu-01.net` now exists.** Method:
  `dig +short` gives `104.21.47.191` and `172.67.172.34`, which are Cloudflare
  addresses. The start state in `../task-01-infra/todo.md` recorded `NXDOMAIN`.
- **The tunnel has no ingress rule for `recall-api.ss-ubuntu-01.net`.** Method:
  `curl -sSI https://recall-api.ss-ubuntu-01.net/health` gives HTTP 404 with an empty
  body, while `docker exec nginx curl http://recall-api:8000/health` gives HTTP 200.
  nginx gives an HTML page with its 404. An empty body is from cloudflared. A stopped
  nginx gives 502, not 404, so the fault is in the ingress rules.
- **`https://recall-api.ss-ubuntu-01.net/health` gives HTTP 200 from outside the
  network.** Method: `curl` from the local machine with `--resolve`, to go around a
  stale negative DNS entry. The body is `{"status":"ok"}`. The `/` route gives HTTP 200
  and the placeholder body. Item 1b is complete.
- **CORS operates over the live URL.** Method: an `OPTIONS` preflight to
  `https://recall-api.ss-ubuntu-01.net/health`. `https://recall.samneet.com` gives
  HTTP 200 with the origin returned and `access-control-allow-credentials: true`.
  `https://evil.example.com` gives HTTP 400 with no `access-control-allow-origin`
  header. Item 1d is complete.
- **`curl -I` gives HTTP 405 on this API.** Method:
  `curl -I https://recall-api.ss-ubuntu-01.net/health`. `curl -I` sends a `HEAD`
  request. FastAPI registers `@app.get()` for the `GET` method only. Plain Starlette
  adds `HEAD` to a `GET` route, but FastAPI does not. Use `curl -i` or plain `curl` to
  check a route. A 405 with `content-type: application/json` shows that the application
  answered, so the full path operates.
- **`cloudflared tunnel route dns` makes the DNS record only.** Method: the command
  `cloudflared tunnel route dns ss-ubuntu-01-tunnel recall-api.ss-ubuntu-01.net` made
  the record, but the hostname gave HTTP 404 with an empty body. An ingress rule in
  `config.yml` is a second, separate step. cloudflared gives an empty-body 404 when no
  ingress rule matches the hostname.
- **One incorrect ingress rule stops the full tunnel.** Method: the new rule had
  `  - service: http://nginx:80` with a list dash. YAML then made two rules: one
  hostname with no service, and one service with no hostname. cloudflared gave
  `Couldn't start tunnel error=" is an invalid address"` and every hostname on both
  zones gave HTTP 530. The correct form puts `service` on the line after `hostname`,
  with four spaces and no dash. Check a new rule with
  `docker run --rm -v <dir>:/home/nonroot/.cloudflared cloudflare/cloudflared:latest
  tunnel ingress validate` before a restart.
- **The cloudflared image is distroless.** Method: `docker exec cloudflared ls` gives
  `executable file not found`. There is no shell and no coreutils. Read the
  configuration from the host. The mount is
  `~/docker/cloudflare-tunnel/cloudflared -> /home/nonroot/.cloudflared`.
- **macOS keeps a negative DNS entry.** Method: `dig +short` gave the Cloudflare
  addresses, but `curl` gave `Could not resolve host` at the same time. `dig` asks the
  name server directly. `curl` uses the system resolver, which had the earlier
  `NXDOMAIN` in its cache. Correct it with
  `sudo dscacheutil -flushcache; sudo killall -HUP mDNSResponder`.
- **A tunnel needs about 20 seconds to register after a restart.** Method: a check one
  second after `docker restart cloudflared` gave HTTP 530. The same check after 25
  seconds gave HTTP 200. Look for four `Registered tunnel connection` lines in
  `docker logs cloudflared` before a test.
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
- **Wrong:** The session gave commands that test a service immediately after a start or
  a restart. Three checks failed for this reason: the container check one second after
  `up -d`, the tunnel check one second after `docker restart`, and the tunnel check 25
  seconds later. **Correct:** Put a wait or a status check before a test. Look for
  `(healthy)` for a container, and for `Registered tunnel connection` for a tunnel.
- **Wrong:** `../task-01-infra/todo.md` says item 1a, the Cloudflare Tunnel, is
  complete. **Correct:** The tunnel was in operation, but it had no ingress rule and no
  DNS record for this hostname. A component that operates is not the same as a
  component that is configured for your hostname. Test the full path, not the process.

## Open items

- [ ] The two `overseerr` files in `~/docker/nginx-proxy/conf.d.disabled/`. Owner: Sam.
      Put them back after the container operates again, or change them to the
      `resolver` pattern.
- [ ] The `Upgrade` and `Connection` headers in
      `~/docker/nginx-proxy/conf.d/recall-api.ss-ubuntu-01.net.conf`. Owner: Sam. The
      file has no websocket headers now. Task 4 needs them for the real-time
      transcript. `config.yml.bak` and `conf.d.backup` are on the server.
- [ ] The DNS cache on the local machine. Owner: Sam. Run
      `sudo dscacheutil -flushcache; sudo killall -HUP mDNSResponder`. The negative
      entry for `recall-api.ss-ubuntu-01.net` is still in the cache.
- [ ] `backend/.env` on the homelab server. Owner: Sam. Copy `.env.example` and put the
      values in it. Task 2 needs the keys. The placeholder routes do not need them.
- [ ] The frontend Worker, item 1c. Owner: the next session.
- [ ] Approval for `wrangler deploy`. Owner: Sam. The command changes a live domain.
- [ ] Item 1c in `../TASKS.md`. Owner: the next session. Items 1a, 1b and 1d are
      marked complete.
- [ ] The four open questions in [`../API_CONTRACT.md`](../API_CONTRACT.md). Owner: the
      task 2 session. The `recall-ai` MCP server is authorized and can answer them.

## Next session starts here

Items 1a, 1b and 1d are complete. Only item 1c remains in task 1.

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
