# TASKS

Ordered checklist. Work top to bottom. Do not skip to voice mode before chat mode
works end to end.

## 1. Infra first

- [x] Cloudflare Tunnel running on the homelab server.
- [x] `recall-api.ss-ubuntu-01.net` resolves and hits a placeholder FastAPI route.
- [x] `recall.samneet.com` resolves via Cloudflare Workers, serves a placeholder page.
- [x] CORS configured on the backend for the frontend origin.

## 2. Backend skeleton

- [x] Poetry project initialized, FastAPI running.
- [x] SQLite schema: sessions table (id, meeting_url, status, transcript log, summary).
      Also `mode`, `error_reason`, `bot_id`, `created_at`, `updated_at`. See
      `task-02-backend-skeleton/todo.md` for the reason for each one.
- [x] `config.py` migrated from plain constants to `pydantic-settings`
      (adds the `pydantic-settings` dependency).
- [x] Recall API key stored as an environment variable, never committed.
      `backend/.env` is not on the homelab server yet. Owner: Sam.
- [x] Endpoint: create session (takes a meeting URL, creates a Recall bot).
- [x] Endpoint: get session status.
- [x] Endpoint: get session summary. The route, the 404 rule and a real summary
      from the engine. `STUB_SUMMARY` is gone. A session that is `complete` with
      no summary gives HTTP 500, which is a fault that the route does not hide.
- [x] Webhook endpoint(s) for Recall bot status events, verified against Recall's
      signature. `POST /webhooks/recall` verifies with the workspace secret, then maps
      the bot events to the session status. See `task-02-recall-connection/todo.md`.
      Sam must still make the dashboard webhook endpoint, so no live event has arrived.

## 3. Mock intake engine

- [x] LLM wired up. The `openai` SDK, not LiteLLM: the workspace has one provider,
      so the SDK is one package and not a large tree. `app/engine/llm.py` is the
      only module that imports it. See `task-03-intake-engine/todo.md`.
- [x] Intake prompt written: an action envelope, a branch on the last answer, and
      the turn limit `INTAKE_MAX_TURNS` (6). The engine applies the limit, not the
      model.
- [x] Summary prompt written: a second call with its own prompt, the eight fields
      of SPEC.md, and a red-flag rule.
- [x] Engine tested standalone (no Recall involved yet) with a scripted
      conversation. `tests/test_engine_loop.py`. No network in any test.

## 4. Mode boundary (build before chat mode)

- [x] `handle_incoming_turn` / `send_outgoing_turn` defined as the interface
      between the state machine and the meeting platform. See
      `IMPLEMENTATION.md`. The protocol is `app/modes/base.py`, and the registry
      is empty until section 5.
- [x] State machine, conversation log, `engine/intake.py`, `engine/summary.py`
      written only in terms of this interface, no chat-specific code above it.
      A test reads the engine modules and refuses the words chat and voice.

## 4a. The turns table (before chat mode)

- [x] The conversation log moved from the `sessions.transcript` JSON column to its own
      `turns` table. An `INSERT` cannot lose a turn, which a read and then a write can.
      Migrations 3, 4 and 5: make the table, copy the JSON into rows, drop the column.
- [x] A turn is one message from each party. `turn_count(log)` is `len(log) // 2`.
- [x] `UNIQUE(session_id, event_id)` with `INSERT OR IGNORE` makes a repeated delivery
      change nothing. `RecallEvent.message_id` carries the Svix message id.
- [x] The conversation is half-duplex. The insert refuses a turn whose role is the role
      of the last turn, so one full patient message goes in, the assistant answers it,
      and only then does the next message go in. The log always alternates.
- [x] `engine/intake.py` and `engine/summary.py` did not change. See
      `task-04-turns-table/todo.md`.

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

## 8a. Prompt tuning (an optimization, near the end)

Do this after the loop works end to end, not before. The prompts operate and they are
not tuned. `backend/app/engine/prompts.py` holds all of the text, so this task changes
one file.

- [ ] Make a small evaluation: more than one scripted patient, the same prompts, and a
      look at each summary. Sam has a synthetic suite from an earlier project that ran
      the same intake against other models. Use its shape.
- [ ] The model sometimes gives the action `complete` with one question left, although
      rule 9 says to use each question. The engine guarantees a maximum of 6 turns and
      not a minimum.
- [ ] The red-flag rule is sensitive. Session 07 saw both faults in one session: the
      model invented "the worst headache of my life" from "really bad headaches", and
      then, after the first repair, it reported no red flag for a patient who gave
      three. Each change to rule 5 needs both a patient with a red flag and a patient
      with none.
- [ ] A question must be 500 characters or less. Google Meet refuses a longer chat
      message. Nothing applies this limit today.
- [ ] Try a larger model against the same patients, and compare. `OPENAI_MODEL` is a
      setting, so this needs no code change.
- [ ] Tune `INTAKE_MAX_TURNS`. It is 6 for a short demonstration.

## 9. Docs pass

- [ ] README finished: links at top, narrative, setup instructions, limitations.
- [ ] ARCHITECTURE.md finished.
- [ ] API_REFERENCE.md finished (your own backend endpoints).
- [ ] Repo pushed to github.com/samneetsingh/recall-demo.

## If time runs out

Cut voice mode, not chat mode. Cut deploy polish, not the working loop. The
"Limitations & Next Steps" section in the README is where you say what you cut and
why — that is a legitimate part of the deliverable, not a failure to hide.
