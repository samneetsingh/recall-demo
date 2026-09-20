# TASKS

Ordered checklist. Work top to bottom. Do not skip to voice mode before chat mode
works end to end.

## 1. Infra first

- [ ] Cloudflare Tunnel running on the homelab server.
- [ ] `recall-api.ss-ubuntu-01.net` resolves and hits a placeholder FastAPI route.
- [ ] `recall.samneet.com` resolves via Cloudflare Workers, serves a placeholder page.
- [ ] CORS configured on the backend for the frontend origin.

## 2. Backend skeleton

- [ ] Poetry project initialized, FastAPI running.
- [ ] SQLite schema: sessions table (id, meeting_url, status, transcript log, summary).
- [ ] `config.py` migrated from plain constants to `pydantic-settings`
      (adds the `pydantic-settings` dependency).
- [ ] Recall API key stored as an environment variable, never committed.
- [ ] Endpoint: create session (takes a meeting URL, creates a Recall bot).
- [ ] Endpoint: get session status.
- [ ] Endpoint: get session summary.
- [ ] Webhook endpoint(s) for Recall bot status events, verified against Recall's
      signature.

## 3. Mock intake engine

- [ ] LiteLLM wired up.
- [ ] Intake prompt written: question sequence, branching behavior.
- [ ] Summary prompt written: structured fields listed in SPEC.md.
- [ ] Engine tested standalone (no Recall involved yet) with a scripted conversation.

## 4. Mode boundary (build before chat mode)

- [ ] `handle_incoming_turn` / `send_outgoing_turn` defined as the interface
      between the state machine and the meeting platform. See
      `IMPLEMENTATION.md`.
- [ ] State machine, conversation log, `engine/intake.py`, `engine/summary.py`
      written only in terms of this interface, no chat-specific code above it.

## 5. Chat mode (must work)

- [ ] `handle_incoming_turn` implemented for chat: parses an incoming chat
      message event into patient text.
- [ ] `send_outgoing_turn` implemented for chat: posts the engine's next
      question as a chat message.
- [ ] Full loop tested against a real Google Meet call, start to summary.

## 6. Voice mode (stretch, added alongside chat mode, not a rewrite of it)

- [ ] OpenAI TTS wired up on the backend.
- [ ] `send_outgoing_turn` implemented for voice: calls TTS, sends output audio
      through Recall.
- [ ] Backend subscribes to real-time transcript.
- [ ] Silence-gap turn-taking logic implemented.
- [ ] `handle_incoming_turn` implemented for voice: turns a transcript-gap
      signal into patient text.
- [ ] Full loop tested against a real Google Meet call, start to summary.
- [ ] Chat mode still works unchanged (it should not need to be touched to add
      this).

## 7. Frontend

- [ ] Meeting URL input, submits to backend.
- [ ] Status display, polls backend.
- [ ] Summary display once complete.

## 8. Deploy for real

- [ ] Backend deployed on the homelab server, tunnel live.
- [ ] Frontend deployed to Workers.
- [ ] Full flow tested against the live URLs, not localhost.

## 9. Docs pass

- [ ] README finished: links at top, narrative, setup instructions, limitations.
- [ ] ARCHITECTURE.md finished.
- [ ] API_REFERENCE.md finished (your own backend endpoints).
- [ ] Repo pushed to github.com/samneetsingh/recall-demo.

## If time runs out

Cut voice mode, not chat mode. Cut deploy polish, not the working loop. The
"Limitations & Next Steps" section in the README is where you say what you cut and
why — that is a legitimate part of the deliverable, not a failure to hide.
