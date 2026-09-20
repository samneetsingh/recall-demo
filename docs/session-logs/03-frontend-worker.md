# 03 — Frontend Worker

Written in ASD-STE100 Simplified Technical English.

- **Date:** 2026-09-19
- **Task:** Section 1 of [`../TASKS.md`](../TASKS.md), item 1c
- **Result:** complete — `https://recall.samneet.com/` gives HTTP 200 from outside the
  network. Section 1 is complete.

## Summary

The session made the frontend Cloudflare Worker: the npm project with wrangler, the
`wrangler.jsonc` configuration and the placeholder page. Sam approved the deploy after
the dry-run. The Worker is live on the custom domain `recall.samneet.com`. A browser on
that page reads `/health` from the backend, which closes the last done criterion of item
1d. The session did not change `backend/`.

## Files changed

| File | Change | Reason |
|---|---|---|
| `frontend/package.json` | new | The npm project. wrangler as a development dependency |
| `frontend/package-lock.json` | new | The exact versions. wrangler 4.135.0 and 37 more packages |
| `frontend/wrangler.jsonc` | new | The Worker configuration. Static assets and the custom domain |
| `frontend/public/index.html` | new | The placeholder page. It also does the backend check |
| `.gitignore` | edit | Added `node_modules/` and `.wrangler/` |
| `docs/task-01-infra/todo.md` | edit | Marked the completed items of 1c and the done criteria |
| `docs/TASKS.md` | edit | Marked item 1c. Section 1 is now complete |
| `docs/session-logs/03-frontend-worker.md` | new | This log |

## Decisions

- **wrangler is a local development dependency, not the global command.** The local
  machine has wrangler 4.85.0 from Homebrew, but `wrangler.jsonc` has
  `"$schema": "./node_modules/wrangler/config-schema.json"`. This path is correct only
  with a local install. `npx wrangler` then gives the version in `package.json`, which
  is the same version on each machine. The local version is 4.135.0.
- **The account ID is an environment variable, not a key in `wrangler.jsonc`.** The
  OAuth token has six accounts, so wrangler cannot select one. The commands use
  `CLOUDFLARE_ACCOUNT_ID=f25beb959f46731f346dedc78c224cf1`. The account ID is a property
  of the credentials, not of the application, and `../task-01-infra/todo.md` gives the
  exact contents of `wrangler.jsonc`. Keep the file as the todo specifies. Put the
  account ID in the environment or in `.dev.vars`.
- **`package.json` has three scripts: `dev`, `check` and `deploy`.** Each is one line.
  `check` is `wrangler deploy --dry-run`, which is the safe command. The names make the
  safe command and the live command different.
- **The placeholder page does one `fetch` to `/health` on the backend.** The done
  criterion of item 1d needs a browser request from the frontend origin to the backend.
  A `curl` command with an `Origin` header shows the headers, but it is not a browser. A
  small check on the page proves the full path. It is 15 lines and it has a comment that
  tells task 7 to remove it. It is not a user interface: there is no meeting URL form, no
  status display and no summary display.
- **`node_modules/` and `.wrangler/` are in the root `.gitignore`.** Session 02 decided
  that this repository has one `.gitignore`, in the root. This session keeps that
  decision. A pattern with no slash matches at any depth, so the root rule catches
  `frontend/node_modules`.
- **`package-lock.json` goes into git.** The application deploys from this directory.
  The lock file makes the build the same on each machine. This is the same rule as
  `backend/poetry.lock`.

## Verified facts

- **The local wrangler is 4.135.0, and the schema file exists.** Method:
  `npx wrangler --version` gives `4.135.0`.
  `ls node_modules/wrangler/config-schema.json` shows the file, 355784 bytes. The
  `$schema` path in `wrangler.jsonc` is correct.
- **The account `Samneet@gmail.com's Account` owns the zone `samneet.com`.** Method: Sam
  gave this fact. The account ID is `f25beb959f46731f346dedc78c224cf1`, from
  `npx wrangler whoami`.
- **`npx wrangler whoami` gives six accounts.** Method: the command. The OAuth token has
  the scopes `workers (write)`, `workers_routes (write)`, `workers_scripts (write)` and
  `zone (read)`, which are sufficient for a deploy with a custom domain. A deploy with
  six accounts and no account ID is not possible. Set `CLOUDFLARE_ACCOUNT_ID` first.
- **No record is on the exact hostname `recall.samneet.com`, and no Worker route has the
  pattern `*.samneet.com/*`.** Method: Sam looked at the Cloudflare dashboard before the
  deploy. Each condition was clear.
- **The dry-run gives no error and no warning.** Method:
  `CLOUDFLARE_ACCOUNT_ID=... npx wrangler deploy --dry-run`. The output is
  `Read 1 file from the assets directory`, `Total Upload: 0.31 KiB` and
  `--dry-run: exiting now`. wrangler 4.135.0 accepts the compatibility date
  `2026-09-19`.
- **The deploy is successful.** Method: `CLOUDFLARE_ACCOUNT_ID=... npx wrangler deploy`.
  The output shows `Uploaded 1 of 1 asset`, `Uploaded recall-demo-frontend` and
  `Deployed recall-demo-frontend triggers ... recall.samneet.com (custom domain)`. The
  version ID is `1bbcebe2-297a-47de-b744-a8a4f41755bc`.
- **`https://recall.samneet.com/` gives HTTP 200 from outside the network.** Method:
  `curl -i https://recall.samneet.com/`. The result is `HTTP/2 200` with
  `content-type: text/html` and `server: cloudflare`. The body has
  `<title>Recall Demo — AI Pre-Visit Intake Assistant</title>`. Item 1c is complete.
- **The custom domain is available immediately.** Method: a loop with a five second
  interval. The first attempt gave HTTP 200. A Worker custom domain does not have the
  20 second delay of a tunnel restart.
- **The wildcard record `*.samneet.com` is not changed.** Method:
  `curl https://nonexistent-test.samneet.com/` gives HTTP 522, which is the start state
  in `../task-01-infra/todo.md`. `curl https://recall.samneet.com/` gives HTTP 200 at the
  same time. The custom domain makes a more specific record, and only that hostname
  changed.
- **`not_found_handling: "404-page"` operates.** Method:
  `curl https://recall.samneet.com/no-such-page` gives HTTP 404.
- **A browser on `https://recall.samneet.com` reads `/health` on the backend.** Method: a
  headless Chromium loaded the live page. The `access-control-allow-origin` header in the
  response is `https://recall.samneet.com` and `access-control-allow-credentials` is
  `true`. The status text on the page becomes
  `The backend answers. /health gives {"status":"ok"}`. The browser console has no error.
  This closes the last done criterion of item 1d.
- **The backend CORS preflight operates over the live URL.** Method:
  `curl -i -X OPTIONS -H 'Origin: https://recall.samneet.com'
  -H 'Access-Control-Request-Method: GET'
  https://recall-api.ss-ubuntu-01.net/health`. The result is HTTP 200 with
  `access-control-allow-methods: GET, POST, OPTIONS` and
  `access-control-max-age: 600`.
- **`node_modules/` and `.wrangler/` are ignored.** Method: `git check-ignore -v` gives
  `.gitignore:12:node_modules/` and `.gitignore:13:.wrangler/`.

## Corrections

- **Wrong:** The session started to read the wrangler OAuth token file to find which of
  the six accounts owns `samneet.com`. **Correct:** Ask Sam. He knows his accounts. An
  investigation for a fact that the user holds wastes tokens and time. Sam added this
  rule to `CLAUDE.md`: "If a question arises, ask it. Do not attempt to reason through a
  question that can most likely be answered by the user."
- **Wrong:** Session 02 says an origin that is not in the list gives HTTP 400.
  **Correct:** This is true for an `OPTIONS` preflight, which Starlette refuses with
  HTTP 400. A simple `GET` with a bad `Origin` header gives HTTP 200 with no
  `access-control-allow-origin` header. The browser then stops the page from reading the
  body. Both results are correct CORS behavior. Method:
  `curl -i -H 'Origin: https://evil.example.com'
  https://recall-api.ss-ubuntu-01.net/health`.
- **Wrong:** The session sent two Bash commands with different `cd` targets in one
  parallel block. The working directory is shared, so the second command ran in the wrong
  directory and gave `no such file or directory`. **Correct:** Give each parallel command
  an absolute path, or send the commands one after the other. Do not use `cd` in parallel
  commands.

## Open items

- [ ] Commit and push the changes of this session. Owner: Sam.
- [ ] The `Upgrade` and `Connection` headers in
      `~/docker/nginx-proxy/conf.d/recall-api.ss-ubuntu-01.net.conf`. Owner: Sam. Task 4
      needs them for the real-time transcript.
- [ ] `backend/.env` on the homelab server. Owner: Sam. Task 2 needs the API keys.
- [ ] The four open questions in [`../API_CONTRACT.md`](../API_CONTRACT.md). Owner: the
      task 2 session. The `recall-ai` MCP server is authorized and can answer them.

## Next session starts here

Section 1 is complete. Start task 2, the backend skeleton, in
[`../TASKS.md`](../TASKS.md).

1. Change `backend/app/config.py` from plain module constants to a `pydantic-settings`
   `BaseSettings` class. Add the `pydantic-settings` dependency. The import in
   `app/main.py` does not change. Session 02 made this decision. Do not decide it again.
2. Make the SQLite schema: the sessions table with id, meeting_url, status, transcript
   log and summary.
3. Answer the four open questions in [`../API_CONTRACT.md`](../API_CONTRACT.md) with the
   `recall-ai` MCP server.

The workspace supports bot schema v1.11 only. Write v1.11 payloads. Do not copy a v1
example from an old document.

Do not change `frontend/` in the same turn as a `backend/` task.
