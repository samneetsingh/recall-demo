# FLOW — the request path, point to point

Written in ASD-STE100 Simplified Technical English.

This document shows what the code does today, not what it will do. A part that is not
built is marked. Read [`ARCHITECTURE.md`](ARCHITECTURE.md) for the design intent and
this file for the path of one request.

## Read this first

Sections 1 to 5, 5a, 7 and 8 of [`TASKS.md`](TASKS.md) are complete. A live Google
Meet call proved the full path on 2026-09-20: the bot joined, it interviewed a patient
in the chat, and `GET /sessions/{id}/summary` gave the eight fields.

**Voice mode is built. It has no live call yet.** Section 6 made
`app/tts/openai_tts.py`, `app/modes/voice.py`, the `voice_buffers` table and the
transcript wire. The assistant speaks each question with OpenAI TTS and Recall's output
audio endpoint, and a silence in the transcript ends each patient turn. Flow D gives the
path. A signed `transcript.data` against the container made one turn from three
utterances. **A Google Meet call is the one step that is open.**

**The page calls the backend now.** Section 7 made `frontend/public/index.html`: a
meeting URL goes in, the page polls the status, and the eight fields come on the page at
the end. It is on `recall.samneet.com`. Part 8 says what it reads.

**The webhook drives the engine now.** Section 5 made `modes/chat.py`, put it in the
`MODES` registry, and added the two calls that were absent: `loop.start_intake` when the
bot starts to record, and `loop.run_turn` for each chat message. A real Google Meet call
thus gives a bot that joins, sends a pinned notice, asks its questions in the chat, and
writes the summary at the end.

**To drive a full intake now, with no Recall:**

```
cd backend && poetry run python scripts/intake_console.py
```

It puts a terminal mode in the same registry that chat mode uses, and it runs the real
state machine, the real database and the real model. You are the patient. It does not
test the Recall wiring. The engine and the prompts are mode-neutral, so this covers
voice mode as well: only the two ends of the turn boundary differ, and the tests hold
those. The `Dockerfile` copies `app` only, so the script is not in the image.

## 1. The parts

```mermaid
flowchart LR
    U[Patient and user] -->|"paste a Meet URL"| F["Frontend<br/>recall.samneet.com<br/>Cloudflare Worker"]
    F -->|"POST /sessions, GET /sessions/id"| B["Backend<br/>recall-api.ss-ubuntu-01.net<br/>FastAPI in Docker"]
    B -->|"create bot"| R["Recall.ai<br/>us-west-2"]
    R -->|"bot.* and realtime events<br/>POST /webhooks/recall"| B
    R -->|"the bot joins"| M["Google Meet call"]
    U --- M
    B -->|"ask_model"| O["OpenAI<br/>gpt-4o-mini"]
    B --- D[("SQLite<br/>one row per session<br/>named volume")]
```

## 2. The state. It is all in the database

The state of a session is one row in `sessions`, its rows in `turns`, and, for voice
mode, its row in `voice_buffers`. **No state is in the process.** There is no global
variable, no cache and no queue. Each request reads the database and writes the
database, so a restart of the container loses no turn. Voice mode adds one wake-up
thread, and it holds a session id and nothing more; see the end of this part.

| Column | Who writes it | What it is |
|---|---|---|
| `id` | `create_session` | The session id. The frontend holds it |
| `meeting_url` | `create_session` | The Google Meet URL |
| `mode` | `create_session` | `chat` or `voice`. It selects the implementation of the turn boundary |
| `status` | the routes, the webhook, the engine | The state machine of part 7 |
| `error_reason` | the same | A short text that the frontend shows |
| `bot_id` | `POST /sessions` | The Recall bot. The webhook maps an event back to a session with it |
| `summary` | `set_summary` | The eight fields, or `NULL` |
| `created_at`, `updated_at` | each write | Time |
| `last_event_at` | `apply_bot_event` | The time of the newest bot event that this session applied. It makes the webhook order-independent |

The conversation log is **not** in this row. It is the `turns` table:

| Column | What it is |
|---|---|
| `id` | The rowid. It gives the order, and it always goes up |
| `session_id` | The session |
| `role` | `bot` or `patient` |
| `text` | The words |
| `event_id` | The Svix message id for a chat turn, `voice-<buffer id>` for a voice turn, or `NULL` for a bot turn. `UNIQUE(session_id, event_id)` makes a repeated delivery change nothing |
| `created_at` | Time |

The insert holds the rules of the conversation. A turn goes in only if the session
exists, its `event_id` is new, **and its role is not the role of the last turn**. The
log thus always alternates, and it cannot be otherwise.

**Voice mode adds a third table, `voice_buffers`.** One `transcript.data` event is one
finalized utterance, and **one utterance is not a turn**: a patient answers in parts.
The parts wait here until a silence ends the turn.

| Column | What it is |
|---|---|
| `id` | The rowid. It is the `event_id` of the turn that this buffer becomes, as `voice-<id>` |
| `session_id` | The session |
| `text` | The parts of one answer, joined with a space |
| `last_part_at` | The time of the newest part, to the microsecond. The silence is measured from it |
| `flushed_at` | `NULL` while the patient speaks. A time when the buffer became a turn |
| `created_at` | Time |

`CREATE UNIQUE INDEX voice_buffers_open ON voice_buffers(session_id) WHERE flushed_at IS
NULL` is a **partial** index, and it is what makes one open buffer for one session. A
part is one `INSERT ... ON CONFLICT ... DO UPDATE`, so two handlers cannot lose a part.
The flush is one `UPDATE ... WHERE flushed_at IS NULL AND last_part_at <= ?`, so **two
wake-ups give one turn**. This is the rule of `apply_bot_event`, applied again.

**The timer is not state.** A `threading.Timer` wakes the process after
`VOICE_TURN_GAP_SECONDS`, and it carries no words: it carries a session id. The words
and the time are in the database, so a restart of the container loses the wake-up and
not the answer. An early wake-up is never cancelled, because an early wake-up finds
`last_part_at` too new and claims nothing.

## 3. What a turn is

**A turn is one message from each party: a question and its answer.** It is not one
message. Three rows in `turns` are one turn and a question that waits:

| `id` | `role` | `text` |
|---|---|---|
| 1 | `bot` | Hello, I am the intake assistant. What brings you in? |
| 2 | `patient` | I get bad headaches. |
| 3 | `bot` | When did they start, and how long does one last? |

**The turn count is calculated, it is not stored.**
`intake.turn_count(log)` is `len(log) // 2`. No column and no variable holds a counter.

- A counter and a log can disagree. Then you must decide which one is true.
- The log is written one time, by one function, `append_turn`.
- A question that has no answer yet is not a turn, so it does not use the budget.
- The engine is thus a pure function of the log: give it the same log and it does the
  same thing. This is why the test can drive it with no database and no network.

**The limit.** `INTAKE_MAX_TURNS` is 6, so the intake is 6 questions and 6 answers, and
12 rows. `next_turn()` counts the log **before** it calls the model. At 6 it gives the
complete signal and makes no call. The prompt also tells the model that it has 6
questions, but that is a request and not a guarantee. The count is the guarantee.

**The conversation is half-duplex.** One full patient message goes in, the assistant
answers it, and only then does the next message go in. A message that arrives before the
answer is refused by the insert, not queued. `docs/SPEC.md` gives this rule for voice
mode, where a pause in the transcript ends the patient turn; chat mode is the same rule
with the message as the unit.

This is why `len(log) // 2` is exact and not approximate: the log cannot hold two
messages from one party in sequence. A patient who sends three messages for one question
still gets 6 questions.

**What a refused message costs.** Its text is not in the log. It is in the container log,
in the line `session <id> refused a turn`. A patient who sends the answer in two parts
loses the second part.

**The engine does not know the mode.** It gets `list[{role, text}]` and gives back a
string or the complete signal. A turn from a chat message and a turn from a transcript
are the same object at this level.

## 4. Flow A — make a session. This operates today

```mermaid
sequenceDiagram
    participant F as Frontend
    participant S as routes/sessions.py
    participant DB as SQLite
    participant RC as recall/client.py
    participant R as Recall.ai

    F->>S: POST /sessions {meeting_url, mode}
    S->>DB: create_session() → status creating_bot
    S->>RC: create_bot(url, session_id, mode)
    RC->>R: POST /api/v1/bot/ (schema v1.11)
    alt Recall answers
        R-->>RC: {"id": bot_id}
        RC-->>S: bot_id
        S->>DB: set_bot_id(), set_status(waiting_for_bot)
        S-->>F: 201 {session_id, status: waiting_for_bot}
    else Recall refuses
        RC-->>S: RecallError
        S->>DB: set_status(error, reason)
        S-->>F: 201 {session_id, status: error}
    end
```

A failed bot gives HTTP 201 and not HTTP 500. The row exists, so the frontend reads the
reason from its poll.

## 5. Flow B — a bot status event. This operates today

```mermaid
sequenceDiagram
    participant R as Recall.ai
    participant W as routes/webhooks.py
    participant E as recall/events.py
    participant DB as SQLite

    R->>W: POST /webhooks/recall (svix headers)
    W->>E: verify_and_parse(raw bytes, headers)
    alt bad signature
        E-->>W: SignatureError
        W-->>R: 401
    else good
        E-->>W: RecallEvent(name, bot_id, sub_code, event_at)
        W-->>R: 200 {"ok": true}
        Note over W: The work runs after the answer.<br/>Recall has a 15 second timeout.
        W->>DB: get_session_by_bot_id(bot_id)
        W->>DB: apply_bot_event(id, status, reason, event_at)
        Note over DB: One UPDATE. It applies the event only if<br/>event_at > last_event_at and status is not complete.
        opt the UPDATE changed the row and the new status is in_progress
            W->>W: send_notice(CONSENT_NOTICE), then loop.start_intake() — flow C
        end
    end
```

`apply_bot_event` gives False for an event that is not newer, so a repeated
`bot.in_call_recording` does not start the intake two times.

The order of arrival does not decide. The time in the event decides. See
[`session-logs/06-event-ordering.md`](session-logs/06-event-ordering.md).

## 6. Flow C — one intake turn. This operates

```mermaid
sequenceDiagram
    participant R as Recall.ai
    participant W as routes/webhooks.py
    participant MO as modes/chat.py
    participant L as engine/loop.py
    participant I as engine/intake.py
    participant DB as SQLite
    participant O as OpenAI

    R->>W: participant_events.chat_message
    W->>MO: handle_incoming_turn(session_id, event) → patient text
    Note over MO: It gives None for the bot's own message,<br/>for an empty text and for another shape.<br/>The route then stops.
    W->>L: run_turn(session_id, text, event.message_id)
    L->>DB: get_session() — refuse if status is not in_progress
    L->>DB: append_turn(patient, text, event_id)
    Note over DB: One INSERT. It refuses a repeated event_id<br/>and a role that does not alternate.<br/>Either gives None, and the loop stops.
    L->>DB: get_turns(session_id)
    L->>I: next_turn(log)
    alt turn_count >= 6
        I-->>L: complete. No call to the model
    else
        I->>O: ask_model(intake prompt, log, strict schema)
        O-->>I: {"action": "ask"|"complete", "question": ...}
        I-->>L: NextTurn(question) or complete
    end
    alt a question
        L->>MO: send_outgoing_turn(session_id, question)
        MO->>R: POST /api/v1/bot/{id}/send_chat_message/
        Note over MO: One message for each 500 characters.<br/>A RecallError becomes a ModeError, and<br/>loop.py puts the session in error.
        L->>DB: append_turn(bot, question)
        Note over L: Send first, then log. A question that<br/>the patient never got is not in the log.
    else complete
        L->>O: make_summary(log) — the second prompt
        O-->>L: the eight fields
        L->>DB: set_summary(), then set_status(complete)
        Note over L: The summary is written first. The frontend<br/>reads the status and then asks for the summary.
    end
    W->>MO: send_outgoing_turn(CLOSING_MESSAGE) if the status is now complete
    Note over W: The closing line is not a turn, so it is<br/>not in the log. loop.py does not send it.
    W->>W: wait BOT_LEAVE_DELAY_SECONDS
    W->>R: POST /api/v1/bot/{id}/leave_call/
    Note over W,R: The bot takes itself out of the call.<br/>Irreversible. A failure is a log line only.
```

**The first question.** `bot.in_call_recording` calls `_start_chat_intake`. That sends
the pinned consent notice with `send_notice`, and then calls `loop.start_intake`, which
is the same path as a turn with no patient message at the start of it. The notice and
the question thus go out in order, from one process. The create-bot hook
`chat.on_bot_join` did this before, and Recall sent the notice after the first question
in the live call of session 09.

**Two messages of the bot are not turns:** the pinned notice and the closing line. A
question that goes out in two parts is one turn and one row. The log holds what the engine said,
one row for each question.

**The bot leaves at the end.** `_finish_intake` says the closing line, waits
`BOT_LEAVE_DELAY_SECONDS` (3 seconds), and then calls `leave_call`. The wait is the
point: Recall answers HTTP 200 when it **accepts** the message, and the bot has still to
type it into the meeting, so a leave with no wait can cut the line. The leave is
irreversible, and a failure is a log line only, because the summary is already written.
The leave is **not** on the mode boundary: it is one HTTP call to Recall and it is the
same for chat and for voice. A session in `error` keeps its bot, because an error
usually means that the bot takes no command. The event that the leave makes,
`bot.call_ended`, changes nothing: `apply_bot_event` has `AND status != 'complete'`.

## 6a. Flow D — one voice turn. This operates, with no live call yet

Flow C is chat mode. Voice mode is the same flow below `loop.run_turn`: the same state
machine, the same engine, the same summary and the same leave. **The difference is at
the two ends**, and this diagram gives only those ends.

```mermaid
sequenceDiagram
    participant R as Recall.ai
    participant W as routes/webhooks.py
    participant MO as modes/voice.py
    participant DB as SQLite
    participant T as tts/openai_tts.py
    participant L as engine/loop.py

    Note over R,W: The patient speaks. One answer is several utterances.
    loop for each transcript.data
        R->>W: transcript.data (a finalized utterance)
        W-->>R: 200 {"ok": true}
        W->>MO: handle_incoming_turn(session_id, event) → None
        Note over MO: The words are at data.data.words[].text.<br/>The bot's own speech gives None.
        MO->>DB: add_voice_part() — one upsert on the open buffer
        W->>DB: open_voice_buffer()
        opt a buffer is open
            W->>W: threading.Timer(VOICE_TURN_GAP_SECONDS, flush_voice_turn)
        end
    end

    Note over W: The patient stops. The newest wake-up fires.
    W->>MO: handle_incoming_turn(session_id, VoiceTurnGap) → the whole answer
    MO->>DB: claim_voice_buffer(now - gap)
    Note over DB: One UPDATE. It gives the row only if<br/>flushed_at IS NULL and no part came after<br/>the gap. An early wake-up gets nothing.
    MO-->>W: the text, and gap.event_id = "voice-<buffer id>"
    W->>L: run_turn(session_id, text, gap.event_id)
    Note over L: From here the path is flow C, with no change.
    L->>MO: send_outgoing_turn(session_id, question)
    MO->>T: speak(question)
    T-->>MO: mp3 bytes
    MO->>R: POST /api/v1/bot/{id}/output_audio/ {"kind": "mp3", "b64_data": ...}
    Note over MO,R: A TTSError and a RecallError each become<br/>a ModeError, and loop.py puts the session in error.
```

**One utterance is not a turn.** Recall says that an utterance often arrives word by
word. `handle_incoming_turn` thus gives `None` for each `transcript.data`, and the
answer comes from the wake-up that follows the last part.

**The wake-up is a thread and not a sleep.** Recall sends the webhooks in sequence, and
a wait on the transcript path would delay each later utterance. `time.sleep` is on the
completion path only, between the closing line and the leave, and it runs one time.

**Each part arms its own wake-up, and none is cancelled.** Three parts arm three
wake-ups. The first two find `last_part_at` newer than `now - gap` and claim nothing.
The third one claims the row, and a fourth wake-up for the same buffer finds
`flushed_at` set. **Two wake-ups cannot make two turns.**

**The `event_id` is the buffer rowid, not a Svix message id.** A voice turn is made of
many events, so no one message names it. One buffer row becomes one turn, and the claim
gives a row one time, so `voice-<id>` gives the same repeat protection that the Svix id
gives a chat turn.

**The consent notice is spoken, not pinned.** `CONSENT_NOTICES` is keyed by the mode:
the chat text ends "Please answer in the chat" and the voice text ends "Please answer
out loud". `send_notice` is the same method on both modes, and the notice is not a turn
in either one.

**A chat message in a voice session is not a turn, and a transcript in a chat session
opens no buffer.** One `realtime_endpoints` list carries both events to each bot, so
each mode receives the events of the other. Each one gives `None` for them. Sam selected
this: one session has one mode.

## 7. The status machine

```mermaid
stateDiagram-v2
    [*] --> creating_bot: POST /sessions
    creating_bot --> waiting_for_bot: the bot id came back
    creating_bot --> error: RecallError
    waiting_for_bot --> in_progress: bot.in_call_recording
    waiting_for_bot --> error: bot.fatal, permission denied
    in_progress --> complete: the complete signal, summary written
    in_progress --> error: LLMError, ModeError, bot.call_ended
    complete --> [*]
    error --> [*]
```

`complete` is terminal in the SQL itself: `apply_bot_event` has `AND status != 'complete'`
in the same statement as the write.

## 8. What the frontend reads

`frontend/public/index.html` is one page of plain HTML and JS. It is on
`recall.samneet.com`, and it operates against the live backend. **Three routes and
nothing else.**

| Route | When | Gives |
|---|---|---|
| `POST /sessions` | one time, on submit | `session_id` and `status`. The body is `{meeting_url, mode}`, and the mode is a control |
| `GET /sessions/{id}` | every 2.5 seconds | `status`, `mode`, `error_reason`, `summary` |
| `GET /sessions/{id}/summary` | one time, after `complete` | The eight fields |

**The page renders from the poll only.** The status in the answer to `POST /sessions`
is not used: a Recall failure also gives HTTP 201, with the status `error` and no
reason, and only the poll has the reason. One source of truth cannot disagree with
itself.

**The session id is in the URL query string**, `?session=<id>`, with
`history.replaceState`. A reload keeps the session, and a link continues one. It is not
in `localStorage`: `IMPLEMENTATION.md` gives this rule for a demo that has one session.

**The poll stops for two conditions only:** the status is `complete` or `error`, which
are the terminal states of part 7, or the route gives HTTP 404, which says that no
session has this id. **A failed request does not stop the poll.** The backend is on a
home server behind a tunnel, so the page shows a warning, keeps the last known status,
and sends the next request at the usual time.

**The mode is a control, and the page reads it back from the poll.** The form has a
chat/voice selector, and `POST /sessions` carries what it holds.

**One text is not the same for the two modes: how the patient must answer.** A chat
patient answers in the meeting chat and a voice patient answers out loud. The page takes
that text from `body.mode` of the **poll**, and never from the control. A reload keeps
the session id only, so the control is back at its default while the session continues;
the backend owns the mode, and the page must not hold a second copy of it. This is the
same rule that makes the page render from the poll and not from the answer to
`POST /sessions`: one source of truth cannot disagree with itself.

`GET /sessions/{id}` thus gives `mode`, which it did not before section 7a. A poll with
no `mode`, which is what a backend of an older version gives, falls back to the chat
text.

**What the page does not read.** There is no route for the `turns` table, so the page
does not show the conversation. A chat patient reads the questions in the meeting chat,
where the bot sends them. **A voice patient sees nothing at all**: the questions are
audio, so the page gives no sign that the bot heard an answer. A turns view needs a
backend route first, and it is the one part of voice mode that the page cannot show
today.

**Three texts of the backend go on the page without a change:**

| Text | Where it comes from | Why it is not changed |
|---|---|---|
| `error_reason` | the session row | It is the only text that says why the bot did not join. `IMPLEMENTATION.md` gives this rule |
| `not discussed` | a summary field that the intake did not cover | The intake asks a small number of questions, so this is usual and it is not a fault. The page makes it muted and does not hide it |
| `RED FLAG:` | the start of `associated_symptoms` | The page gives it the alert color. The words are the words that the model wrote |

An HTTP 500 from `GET /sessions/{id}/summary` also goes on the page. The backend calls
that a fault of its own, and the page does not hide a fault of the backend.

## 9. What is not built, and what is weak

**Not built.**

- **A live Google Meet call in voice mode.** The code operates and no call proved it.
  The procedure is at the end of [`session-logs/11-voice-mode.md`](session-logs/11-voice-mode.md).
  Owner: Sam.
- **A mode control on the page.** `frontend/public/index.html` sends the mode `chat` as
  a constant, so a voice session starts with curl. This is section 7a of
  [`TASKS.md`](TASKS.md). Sam selected it.
- Prompt tuning. Section 8a. Four live calls show that the model stops with questions
  unused, and that the first question introduces the assistant a second time.

**Repaired by task 6.**

- ~~Voice mode: `tts/openai_tts.py`, the transcript parser, and the silence-gap timer.~~
  Built. `transcript.data` drives the buffer now.
- ~~`MODES` has `chat` and not `voice`.~~ It has both.

**Repaired by task 4. Kept here so the reason is not lost.**

1. ~~`append_turn` is a read and then a write, so two handlers can lose a turn.~~ It is
   one `INSERT` now. A threaded test in `test_session_store.py` keeps it that way: with
   the task 3 code, the two threads give one row and not two.
2. ~~A turn has no idempotency.~~ `UNIQUE(session_id, event_id)` and `INSERT OR IGNORE`.
   A repeated delivery gives `None` and the loop stops.
3. ~~Two turns of one session can run the engine at the same time.~~ The insert refuses
   a role that does not alternate, so a second patient message cannot go in before the
   assistant has answered the first. One message in, one question out.

**Repaired by task 5.**

4. ~~The wire from `routes/webhooks.py` to `loop.run_turn` and `loop.start_intake`.~~
5. ~~`modes/chat.py`, and its one entry in `MODES`.~~

**Weak. These are faults, not plans.**

1. **A refused patient message is lost.** The half-duplex rule refuses it and the text
   stays in the container log only. A patient who sends an answer in two parts loses the
   second part. A queue would keep it, and a queue is state that can disagree with the
   log.
2. **A turn that fails has no retry.** If the handler that owns the newest turn stops,
   the conversation waits and nothing acts. The turns table makes this visible — the
   last turn has the role `patient` and it is old — and no code reads it.
3. **A patient who stops answering keeps the session in `in_progress` forever.** Only
   `bot.call_ended` ends it.
4. **The echo filter is the bot name.** A message whose sender name is
   `RECALL_BOT_NAME` is not a patient turn. The payload has no "this is the bot" field,
   so a patient who uses the same name in the call is not heard. The name is also
   `null` for some platforms, and a `null` name counts as a patient.
5. **A real-time retry is not proved to keep its `webhook-id`.** The repeat protection
   of a chat turn is that header. Svix keeps the id for a dashboard event, and Recall
   retries a real-time message with its own policy: 60 attempts, one each second. If the
   id changes, a retry makes a second turn.

6. **Two sessions can hold one bot id.** `get_session_by_bot_id` is
   `SELECT * FROM sessions WHERE bot_id = ?`, with no order and no limit, so it gives an
   arbitrary row. Recall gives a new bot for each session, so the application cannot make
   this condition. A test can: session 09 sent a chat event for the bot of the live call
   of session 05, and the webhook applied it to the session of session 05, which was
   `error`. The log line `session <id> is error, no turn` is what this looks like.

**Weak, and specific to voice mode.**

7. **A pause in the middle of a sentence ends the turn.** The signal is a silence of
   `VOICE_TURN_GAP_SECONDS` (2.5) and nothing more. A patient who thinks for three
   seconds sends half an answer to the engine, and the second half is refused by the
   half-duplex insert. `participant_events.speech_off` is the other signal, and it has
   its own fault: it arrives before the last `transcript.data`, which has a delay of 1
   to 3 seconds. `SPEC.md` gives the pause, and a live call must tune the value.
8. **Each participant who is not the bot is the patient.** The echo filter compares the
   speaker name with `RECALL_BOT_NAME`, as chat mode does. A second person in the call
   thus speaks into the same buffer. `SPEC.md` has one patient.
9. **Recall says not to do this.** The document `bot-real-time-transcription` says to
   use output media with a voice-to-voice model for a conversational agent, and not the
   real-time transcript. This build keeps the `SPEC.md` design on purpose: half duplex,
   no interruption handling, and a pause as the turn signal. Output media is mutually
   exclusive with the output audio endpoint, it always sends video, and full duplex is
   out of scope. The trade-off is the delay: the transcript has 1 to 3 seconds, the
   silence adds 2.5, and the TTS call adds its own.
10. **A wake-up that the container loses stops the conversation.** The words are in the
    database and the wake-up is not. A restart between the last utterance and the gap
    thus leaves an open buffer that nothing claims, and the patient waits. The next
    utterance arms a new wake-up and the answer comes back, one turn late.

All of these are next steps for the README, not faults of the store.
