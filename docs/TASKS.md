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

## 4. Chat mode (must work)

- [ ] Backend receives chat messages from the bot via Recall.
- [ ] Backend sends the engine's next question back as a chat message.
- [ ] Full loop tested against a real Google Meet call, start to summary.

## 5. Voice mode (stretch)

- [ ] OpenAI TTS wired up on the backend.
- [ ] Backend sends bot's question as audio through Recall's output-audio path.
- [ ] Backend subscribes to real-time transcript.
- [ ] Silence-gap turn-taking logic implemented.
- [ ] Full loop tested against a real Google Meet call, start to summary.
- [ ] Chat mode still works after this (did not get broken or removed).

## 6. Frontend

- [ ] Meeting URL input, submits to backend.
- [ ] Status display, polls backend.
- [ ] Summary display once complete.

## 7. Deploy for real

- [ ] Backend deployed on the homelab server, tunnel live.
- [ ] Frontend deployed to Workers.
- [ ] Full flow tested against the live URLs, not localhost.

## 8. Docs pass

- [ ] README finished: links at top, narrative, setup instructions, limitations.
- [ ] ARCHITECTURE.md finished.
- [ ] API_REFERENCE.md finished (your own backend endpoints).
- [ ] Repo pushed to github.com/samneetsingh/recall-demo.

## If time runs out

Cut voice mode, not chat mode. Cut deploy polish, not the working loop. The
"Limitations & Next Steps" section in the README is where you say what you cut and
why — that is a legitimate part of the deliverable, not a failure to hide.
