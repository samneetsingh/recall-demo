# CLAUDE.md

This file gives Claude Code context for the `recall-demo` repo. Read this first, every session.

## What this project is

A demo app for the Recall.ai technical interview. It shows a real use case for the Recall
Meeting Bot API: an AI pre-visit intake assistant that joins a video call, interviews a
patient the way a headache/neurology intake would, and produces a structured clinical
summary at the end.

The demo is not the real FIRY AI system. The intake logic is a mock, built with an LLM
through LiteLLM. Do not port real FIRY code into this repo.

## Repo layout

```
recall-demo/
  backend/     FastAPI app, Poetry-managed. Bot logic, Recall webhooks, LLM calls, SQLite.
  frontend/    Static site on Cloudflare Workers. Calls the backend API. No bot logic here.
  docs/        SPEC.md, ARCHITECTURE.md, API_CONTRACT.md, API_REFERENCE.md, TASKS.md
  README.md
  CLAUDE.md
```

Keep `backend/` and `frontend/` fully separate. No shared imports. They deploy to
different places and can fail independently.

## Stack

- Backend: FastAPI, Poetry, SQLite, LiteLLM (for the mock intake engine), Recall.ai
  Python SDK or plain HTTP calls, OpenAI TTS.
- Frontend: plain HTML/JS (or minimal framework), Cloudflare Workers, calls the backend
  over HTTPS.
- Transcription: Recall.ai's own transcription provider.
- Deploy targets:
  - Frontend: `recall.samneet.com` (Cloudflare Workers)
  - Backend: `recall-api.ss-ubuntu-01.net` (homelab, via Cloudflare Tunnel)

## Build order (do not skip ahead)

1. Get both subdomains resolving with a placeholder response, end to end.
2. Build the state machine, conversation log, and intake/summary engine behind a
   mode-neutral interface (`handle_incoming_turn` / `send_outgoing_turn` — see
   `docs/IMPLEMENTATION.md`). Nothing above this interface should know about chat
   or voice specifically.
3. Implement that interface for **chat** (send/receive chat messages through the
   bot). This must fully work before touching voice.
4. Add a second implementation of the interface for voice (real-time transcript +
   OpenAI TTS output audio). This is an addition, not a rewrite of step 3 — chat
   mode keeps working unchanged.
5. Deploy both sides for real.
6. Docs and README pass.

## Conventions

- Don't add a new dependency without flagging it first.
- Don't touch `frontend/` while working a `backend/` task, or vice versa, in the same turn.
- Keep the mock intake logic in one clearly named module (e.g. `backend/engine/`), not
  scattered across route handlers.
- SQLite is fine for this demo. No migrations framework needed, keep the schema small.
- No HIPAA-related controls in this build. Note it as a next step in the README, not
  something to implement now.

## What "done" looks like

A user can open `recall.samneet.com`, paste a Google Meet URL, have the bot join, go
through a chat-based (and ideally voice) intake, and see a structured summary appear on
the page when it's done.
