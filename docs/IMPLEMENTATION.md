# Implementation Plan

Bridges SPEC.md and ARCHITECTURE.md to actual code. Describes modules, the session
state machine, and the decision points a build session needs, without writing the
code itself. Read this before starting a Claude Code session on backend work.

## Backend module layout

```
backend/
  app/
    main.py              FastAPI app, route registration
    routes/
      sessions.py        POST /sessions, GET /sessions/{id}, GET /sessions/{id}/summary
      webhooks.py         POST /webhooks/recall
    engine/
      intake.py           Question generation, branching logic
      summary.py          Final summary generation
      prompts.py           All prompt text lives here, not inline in other files
    recall/
      client.py            Thin wrapper over Recall's HTTP API (create bot, send
                            chat, send audio, etc.)
      events.py             Parses incoming webhook/event payloads into internal
                             types
    tts/
      openai_tts.py         Wraps OpenAI TTS calls
    db/
      models.py             SQLite schema (sessions table)
      session_store.py      Read/write helpers, no raw SQL outside this file
    config.py               Env vars: RECALL_API_KEY, OPENAI_API_KEY, DB path
```

Rule: `routes/` files stay thin. A route handler reads the request, calls into
`engine/`, `recall/`, or `db/`, and returns a response. No business logic in the
route handler itself.

## Mode boundary: build this first, before either mode

Chat is built first, but the code must not be chat-specific underneath. Split the
system into two layers from the start:

- **Mode-agnostic** (build once, both modes use it unchanged): the state machine,
  the conversation log, `engine/intake.py`, `engine/summary.py`. These only ever
  handle plain text in, plain text out. They must never know whether a turn came
  from chat or a transcript.
- **Mode-specific** (one implementation per mode, same shape): how a patient turn
  arrives, and how a bot turn goes out. Chat mode implements this with chat
  messages. Voice mode will implement the same interface with transcript chunks
  and TTS/output audio.

Name the two functions at this boundary mode-neutrally from the start, even while
only chat exists:

```
handle_incoming_turn(session_id, raw_event) -> patient_text
send_outgoing_turn(session_id, text) -> None
```

Chat mode's version of `handle_incoming_turn` parses a chat message event. Voice
mode's version will parse a transcript-gap signal instead. Same for
`send_outgoing_turn`: chat mode posts a chat message, voice mode will call TTS and
send output audio. Nothing above this boundary changes when voice is added later.

This makes voice mode an addition, not a rewrite: a second implementation of
`handle_incoming_turn`/`send_outgoing_turn`, selected by the session's `mode`
field, sitting next to the first.

## Session state machine

A session moves through these states, stored on the session row:

```
creating_bot -> waiting_for_bot -> in_progress -> complete
                                 \-> error
```

- `creating_bot`: backend has called Recall's create-bot endpoint, response not
  back yet.
- `waiting_for_bot`: bot created, waiting for the "bot joined call" webhook event.
- `in_progress`: bot is in the call, intake question/answer loop is running.
- `complete`: engine signaled the intake is done, summary has been generated and
  stored.
- `error`: something failed (bot couldn't join, Recall error, engine error).
  Store a short reason string alongside this state for debugging.

The frontend only ever reads this `status` field plus `summary`. It does not need to
know about chat vs. voice mode internally, that is a backend concern.

## The question/answer loop, in detail

This is the same shape for both chat and voice. It is written entirely in terms of
`handle_incoming_turn` and `send_outgoing_turn` from the mode boundary above, so it
never changes when voice mode is added.

1. An incoming event arrives, tagged with the session id. `handle_incoming_turn`
   (the mode-specific implementation) turns it into plain patient text.
2. Backend looks up the session, appends the patient text to the stored
   conversation log.
3. Backend calls `engine/intake.py` with the full conversation so far.
4. The engine returns one of two things:
   - The next question to ask, as text.
   - A signal that the intake is complete.
5. If a next question came back: call `send_outgoing_turn` (the mode-specific
   implementation) with the text, append it to the conversation log, stay in
   `in_progress`.
6. If complete: call `engine/summary.py` with the full conversation log, store the
   result, set status to `complete`.

Keep the conversation log as a simple ordered list of `{role, text}` entries in the
session row (JSON column or separate table, either is fine for SQLite at this
scale). Both the intake engine and the summary engine read from this same log, so
there is one source of truth for "what has been said so far."

## Turn-taking in voice mode

Voice mode needs one additional piece: deciding when the patient has finished
speaking. Implementation approach:

- On each incoming transcript chunk, reset a timer.
- If no new transcript arrives for N seconds (start with 2-3, tune by testing),
  treat the buffered transcript since the bot's last question as the patient's
  full answer, and run step 2 above.
- Do not try to detect interruptions or handle the bot being talked over. Out of
  scope, noted in SPEC.md and the README limitations section.

## Webhook handling

- `routes/webhooks.py` receives all Recall events at one endpoint.
- `recall/events.py` is responsible for verifying the signature and turning the
  raw payload into a typed internal event (bot status change, chat message
  received, transcript chunk received).
- The route handler dispatches based on event type: bot status events update
  session `status`; chat/transcript events feed into the question/answer loop
  described above.

## Frontend implementation notes

- Single page. No routing library needed.
- On submit: POST to `/sessions`, store the returned `session_id` (in memory or
  the URL query string, not localStorage, this is a single-use demo).
- Poll `GET /sessions/{id}` every 2-3 seconds while status is not `complete` or
  `error`.
- On `complete`: call `GET /sessions/{id}/summary`, render the structured fields.
- On `error`: show the stored reason string plainly, do not hide it.

## Suggested build order within this plan

Matches `TASKS.md`, restated at the module level:

1. `db/`, `config.py`, `routes/sessions.py` returning stubbed data, no Recall
   calls yet. Confirms the frontend/backend wiring works.
2. `recall/client.py` create-bot call, `routes/webhooks.py` receiving real bot
   status events. Confirms the Recall connection works.
3. `engine/intake.py` and `engine/summary.py`, tested standalone against a
   scripted conversation, no Recall involved.
4. Wire chat mode: `recall/events.py` chat parsing, sending chat messages back
   out. Full loop, real Google Meet call.
5. Wire voice mode: `tts/openai_tts.py`, transcript parsing, silence-gap timer.
6. Deploy, then a full pass on `README.md` and the rest of `docs/`.
