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
      `IMPLEMENTATION.md`. The protocol is `app/modes/base.py`. Section 5 put
      `chat` in the registry, and section 6 puts `voice` next to it.
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

- [x] `handle_incoming_turn` implemented for chat: parses an incoming
      `participant_events.chat_message` event into patient text. It gives
      `None` for the bot's own message, which the bot receives back, for an
      empty text, and for a payload shape that it does not know. See
      `task-05-chat-mode/todo.md`.
- [x] `send_outgoing_turn` implemented for chat: posts the engine's next
      question with `POST /api/v1/bot/{id}/send_chat_message/`. A question of
      more than 500 characters goes out in two messages, because Google Meet
      refuses a longer one. A `RecallError` becomes a `ModeError`, so a send
      that failed puts the session in `error` and is not silent.
- [x] The wire: `routes/webhooks.py` calls `loop.start_intake` when the bot
      starts to record, and `loop.run_turn` for each chat message, with the
      Svix message id as the `event_id`.
- [x] The greeting: the create-bot hook `chat.on_bot_join` sends the consent
      notice of `SPEC.md` and pins it. Google Meet keeps a pinned message
      visible for a participant who joins later. **The pin needs continuous
      chat off in the call.**
- [x] The closing line: the bot says that the intake is complete when the
      summary is written. It is not a turn, so it is not in the log.
- [x] `engine/intake.py`, `summary.py`, `prompts.py` and `loop.py` did not
      change. `git diff` on `app/engine/` gives no line.
- [x] Full loop tested against a real Google Meet call, start to summary. Session
      09: the bot joined, asked 5 questions in the chat, and
      `GET /sessions/{id}/summary` gave the eight fields on the live URL.

## 5a. The bot leaves when the intake is complete

Found in session 10. The bot said the closing line and then waited in the call, silent,
until the patient removed it. See `task-05a-bot-leave/todo.md`.

- [x] `leave_call(bot_id)` in `app/recall/client.py`.
      `POST /api/v1/bot/{id}/leave_call/` with no body. It is **irreversible**.
- [x] The wire: `_finish_intake` in `routes/webhooks.py` says the closing line, waits
      `BOT_LEAVE_DELAY_SECONDS`, and then takes the bot out of the call. Recall accepts
      the message before the bot has typed it into the meeting, so a leave with no wait
      can cut the line.
- [x] The leave is **not** on the mode boundary. It is one HTTP call and it is the same
      for chat and for voice, so `app/modes/` did not change and section 6 gets it free.
- [x] A failed leave is a log line. The summary is written and the status is `complete`.
- [x] A session in `error` keeps its bot. An error usually means that the bot takes no
      command, so the leave would fail in the same manner.
- [ ] Proved in a live Google Meet call: the closing line arrives, and the bot then
      leaves by itself. **The delay is the one value that a test cannot prove.**

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

One page of plain HTML and JS, `frontend/public/index.html`. No framework, no build
step and no new dependency. See `task-07-frontend/todo.md`.

- [x] Meeting URL input, submits to backend. `POST /sessions` with the mode `chat`.
      The session id goes in the URL query string, so a reload keeps the session.
- [x] Status display, polls backend. `GET /sessions/{id}` every 2.5 seconds, with a
      `setTimeout` chain, until the status is `complete` or `error`. Each status gives
      an instruction: `waiting_for_bot` says to admit the bot to the call, with the
      elapsed time. A failed poll does not stop the poll, and HTTP 404 does.
- [x] Summary display once complete. The eight fields of `GET /sessions/{id}/summary`.
      `not discussed` is muted, and a value that starts with `RED FLAG:` is in the
      alert color. The text is never changed.
- [x] The error path. The status `error` shows `error_reason` as it is, in monospace.
      Proved with a real Recall refusal on the live backend.
- [x] The `/health` check of item 1d is out of `public/index.html`.

## 8. Deploy for real

- [ ] Backend deployed on the homelab server, tunnel live.
- [x] Frontend deployed to Workers. Version `c2219c53-0508-4f92-9777-b61007307f0c`
      on `recall.samneet.com`, 2026-09-20.
- [x] Full flow tested against the live URLs, not localhost. 2026-09-20:
      `recall.samneet.com` made session `ae72c30fdd8b40fb987a03ea24cfe7e4`, the bot
      joined, the intake ran in the chat, and the eight fields came on the page.

## 8a. Prompt tuning (an optimization, near the end)

Do this after the loop works end to end, not before. The prompts operate and they are
not tuned. `backend/app/engine/prompts.py` holds all of the text, so this task changes
one file.

- [ ] Make a small evaluation: more than one scripted patient, the same prompts, and a
      look at each summary. Sam has a synthetic suite from an earlier project that ran
      the same intake against other models. Use its shape.
- [ ] **The order of the first two messages.** The pinned notice comes from Recall,
      through the create-bot hook, and the first question comes from this backend. In
      session 09 the question went out 1.74 seconds after the join and the notice came
      after it. This is a code choice and not a prompt, so it is not part of this
      section. See `../session-logs/09-chat-mode.md`.
- [ ] **The first question introduces the assistant a second time.** The pinned
      notice says "I am an AI intake assistant, not a physician", and the live call of
      session 09 then gave "Hello, I'm the intake assistant. Can you tell me about your
      headache?". The notice does the introduction, so the first question must ask only.
      Rule 1 of the intake prompt tells the model to introduce itself; remove that and
      keep the question.
- [ ] The model sometimes gives the action `complete` with one question left, although
      rule 9 says to use each question. The engine guarantees a maximum of 6 turns and
      not a minimum. The live call of session 09 stopped after 5 turns, and it never
      asked about prior treatments, so `prior_treatments` came back `not discussed`.
      That field is one of the eight of `SPEC.md`, so an early stop costs data.
- [ ] The red-flag rule is sensitive. Session 07 saw both faults in one session: the
      model invented "the worst headache of my life" from "really bad headaches", and
      then, after the first repair, it reported no red flag for a patient who gave
      three. Each change to rule 5 needs both a patient with a red flag and a patient
      with none.
- [ ] A question must be 500 characters or less. Google Meet refuses a longer chat
      message. Section 5 cuts a long question into two messages, which operates but
      reads badly. Make the prompt give a question that fits in one message.
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
