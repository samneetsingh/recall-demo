# 01 — Task 1 infra plan

Written in ASD-STE100 Simplified Technical English.

- **Date:** 2026-09-19
- **Task:** Section 1 of [`../TASKS.md`](../TASKS.md), infra
- **Result:** partial — the plan is complete, the build is not started

## Summary

The session read the repository and found no application code. The session checked the
two subdomains from outside the network and found that neither one serves a page. The
session then wrote the plan for task 1. No application code was written.

## Files changed

| File | Change | Reason |
|---|---|---|
| `docs/task-01-infra/todo.md` | new | The procedure for task 1 |
| `docs/session-logs/TEMPLATE.md` | edit | Removed two incorrect lines at the end of the file |
| `docs/session-logs/01-task-1-infra-plan.md` | new | This log |

## Decisions

- **The deploy files stay in `backend/` and `frontend/`.** There is no top-level
  `infra/` directory. `CLAUDE.md` requires the two sides to stay separate.
- **The placeholder application is the real `app/main.py`.** Task 2 adds routers to the
  same file. A temporary file makes more work later.
- **The Worker uses static assets only.** It has no `main` entrypoint and no build
  step. The placeholder page has no server-side logic.
- **The Compose project name is `recall-api`.** This name makes the network
  `recall-api_default`. The external nginx stack needs this network.
- **The container name is `recall-api`.** The nginx stack finds the container by this
  name.
- **nginx and the tunnel stay outside this repository.** These parts are already
  operational. This task supplies only the container and the Worker.
- **CORS uses an exact list of origins.** The `*` character is not permitted.
- **The documentation uses ASD-STE100.** `todo.md` holds tasks only. Decisions go in a
  session log.

## Verified facts

- **A static-only Worker deploys with no `main` entrypoint.** Method:
  `npx wrangler deploy --dry-run` on a `wrangler.jsonc` with an `assets` block only.
- **The Compose key `name: recall-api` makes the network `recall-api_default`.**
  Method: `docker compose config`.
- **`recall-api.ss-ubuntu-01.net` gives NXDOMAIN.** Method:
  `dig @1.1.1.1 recall-api.ss-ubuntu-01.net A`.
- **The zone `ss-ubuntu-01.net` is live on the Cloudflare name servers.** Method:
  `dig +short ss-ubuntu-01.net NS`.
- **`recall.samneet.com` gives HTTP 522.** Method:
  `curl -sSI https://recall.samneet.com/`.
- **A proxied wildcard record covers all subdomains of `samneet.com`.** Method:
  `dig @1.1.1.1 +short <random-name>.samneet.com A` gives the same two IP addresses as
  `recall.samneet.com`. A request to the random subdomain also gives HTTP 522.
- **Local tool versions:** wrangler 4.85.0, node v25.9.0, docker 29.3.1, Docker Compose
  v5.1.0, poetry 2.3.3, python 3.13.1. Method: `<tool> --version`.

## Open items

- [ ] The tunnel configuration for `recall-api.ss-ubuntu-01.net`. Owner: Sam.
- [ ] All commands on the homelab server. Owner: Sam. This session had no SSH access to
      the server.
- [ ] Approval for `wrangler deploy`. Owner: Sam. The command changes a live domain.
- [ ] Authorization for the `recall-ai` MCP server. Owner: Sam. This server can answer
      the four open questions in [`../API_CONTRACT.md`](../API_CONTRACT.md).
- [ ] The file `.mcp.json` is not in git. Owner: Sam. It holds no credentials.

## Next session starts here

Build the backend container. Follow the backend procedure in
[`../task-01-infra/todo.md`](../task-01-infra/todo.md).

1. Make `backend/pyproject.toml` with Poetry. Add `fastapi` and `uvicorn[standard]`.
2. Make `backend/app/main.py` with a `GET /health` route and a `GET /` route.
3. Make `backend/Dockerfile` and `backend/.dockerignore`.
4. Make `backend/deploy/docker-compose.yml` with the project name `recall-api` and the
   container name `recall-api`.
5. Make `backend/.env.example` with the names of the environment variables.
6. Start the container on the local machine. The `/health` route must give HTTP 200.

Do not change `frontend/` in the same turn as a `backend/` task.
