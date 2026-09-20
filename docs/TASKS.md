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
      The dashboard webhook endpoint is made and active, `ep_3JZumFBubz7xBTnyeUonK4U1MfH`,
      and live `bot.*` events have arrived on it.

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
      `None` for a message whose sender name is the bot name, for an empty
      text, and for a payload shape that it does not know. The payload has no
      self or bot marker, so the sender name is the only test available. The
      live call of session 09 then showed that Google Meet sends no event for a
      message that the bot sent, so this filter did not operate. It stays,
      because another platform can be different. See `task-05-chat-mode/todo.md`.
- [x] `send_outgoing_turn` implemented for chat: posts the engine's next
      question with `POST /api/v1/bot/{id}/send_chat_message/`. A question of
      more than 500 characters goes out in two messages, because Google Meet
      refuses a longer one. A `RecallError` becomes a `ModeError`, so a send
      that failed puts the session in `error` and is not silent.
- [x] The wire: `routes/webhooks.py` calls `loop.start_intake` when the bot
      starts to record, and `loop.run_turn` for each chat message, with the
      Svix message id as the `event_id`.
- [x] The greeting: **the backend sends the consent notice of `SPEC.md` itself**,
      with `send_chat_message` and `pin`, immediately before the first question.
      The create-bot hook `chat.on_bot_join` did this up to session 09 and was
      removed: Recall sends that message, so its time is not under the control of
      the backend, and in the live call the first question went out before the
      notice. Google Meet keeps a pinned message visible for a participant who
      joins later. **The pin needs continuous chat off in the call.**
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
- [x] **A session in `error` also leaves the call.** Changed after this item was first
      written: the usual error is a failed model call, and the bot itself is in good
      health, so it takes the command. The patient must not have to remove a bot that
      stopped. The error path says its own last line first, which tells the patient that
      a technical problem stopped the intake.
- [x] Proved in a live Google Meet call, 2026-09-20. Bot
      `193f426d-ba66-4cdc-ba6a-3ac67b642f2e`: the closing line went out at 09:21:17.393,
      Recall logged `bot_received_leave_call` at 09:21:20.686, and
      `POST /leave_call/` gave HTTP 200. The gap is 3.293 seconds, which is the 3.0
      second wait and 0.29 seconds of overhead. Sam saw the closing line in the chat
      before the bot left, so the delay is long enough.

## 5b. Hardening of the live paths

Done in the last session before the submission. No new dependency and no new route.

- [x] `POST /sessions` refuses a mode that has no implementation. It tests the `MODES`
      registry and gives HTTP 400 with `the mode <x> has no implementation`, **before**
      the session row and before the bot. A bot costs money and joins a real meeting.
- [x] `bot.call_ended` branches on its sub-code. A normal end gives `complete` with no
      reason, and a fault, an unknown or an absent sub-code gives `error` with the raw
      `call_ended:<sub_code>`. The list of normal sub-codes is never treated as the whole
      set of the values Recall can send.
- [x] `error` is terminal, the same as `complete`. A later bot event cannot take a
      session out of `error` and cannot erase its reason. `apply_bot_event` holds the
      rule in one conditional `UPDATE`.
- [x] Zero data retention. `recording_config` sends `"retention": null` and no video key.
      Chat mode subscribes to `participant_events.chat_message` only and names no
      transcript provider.
- [x] `automatic_leave` is set and not left to the defaults.
      `everyone_left_timeout` is `{"timeout": 120}`, because the default 2 seconds is less
      than a Meet tab reload and the bot cannot come back. `noone_joined_timeout` is 300.
- [x] `leave_call` retries one time after a transient failure: a network fault, HTTP 429
      or an HTTP 5xx. It does not retry an HTTP 400, 401 or 404.
- [ ] **A partial summary for a call that ended early.** Scoped and cut for time. A call
      that ends before the last question now reaches `complete` with no summary, and
      `GET /sessions/{id}/summary` then gives HTTP 500. The README and `API_REFERENCE.md`
      state the gap.

## 6. Voice mode (a stretch goal, unfinished, on the branch `feat/voice-mode`)

**This section is not on `main`.** `main` ships chat mode only, and `POST /sessions`
with the mode `voice` gives HTTP 400 there. The work below is on the branch
`feat/voice-mode`. It is built and tested against the container, and **it is not proved
in a live Google Meet call**, so it was not merged. See
`../session-logs/11-voice-mode.md` on that branch.

- [x] OpenAI TTS wired up on the backend. (branch)
- [x] `send_outgoing_turn` implemented for voice: calls TTS, sends output audio
      through Recall. A voice bot needs an `automatic_audio_output` configuration
      with a short silent mp3, or the output-audio endpoint gives HTTP 400. (branch)
- [x] Backend subscribes to real-time transcript. (branch)
- [x] Silence-gap turn-taking logic implemented. The parts of one spoken answer wait
      in a `voice_buffers` table, and a gap of 2.5 seconds ends the turn. (branch)
- [x] `handle_incoming_turn` implemented for voice: turns a transcript-gap
      signal into patient text. (branch)
- [ ] **Full loop tested against a real Google Meet call, start to summary. Not done.**
      This is the reason the branch is not on `main`.
- [x] Chat mode still works unchanged. `git diff` on `app/modes/chat.py` and on the
      four engine modules gives no line. (branch)

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

- [x] Backend deployed on the homelab server, tunnel live. Sam deployed at the end of
      session 09, and session 10 ran two live calls against it.
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
- [x] **The order of the first two messages. Repaired.** The pinned notice came from
      Recall, through the create-bot hook, so its time was not under the control of the
      backend: in session 09 the question went out 1.74 seconds after the join and the
      notice came after it. The hook is removed and the backend sends both, in order.
      This was a code choice and not a prompt. See `../session-logs/09-chat-mode.md`.
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

Done in the last session before the submission, after a review of each document against
the code.

- [x] README finished: links at top, narrative, setup instructions, limitations.
- [x] ARCHITECTURE.md finished.
- [x] API_REFERENCE.md finished (your own backend endpoints). The 400 for a mode with no
      implementation, the `bot.call_ended` branch, the terminal `error`, the leave on the
      error path, and the corrected recipe for a new mode.
- [x] API_CONTRACT.md reconciled. The top half now agrees with the answers below it, the
      dashboard webhook endpoint is marked closed, and the echo claim is corrected against
      the live call of session 09.
- [x] TASKS.md reconciled with the code and the branches. This file.
- [ ] Repo pushed to github.com/samneetsingh/recall-demo. Owner: Sam.

## If time runs out

Cut voice mode, not chat mode. Cut deploy polish, not the working loop. The
"Limitations & Next Steps" section in the README is where you say what you cut and
why. That is a legitimate part of the deliverable, not a failure to hide.

**This is what happened.** Voice mode is on the branch `feat/voice-mode` and it is not
merged, because no live call proved it. Chat mode works end to end on `main`.
