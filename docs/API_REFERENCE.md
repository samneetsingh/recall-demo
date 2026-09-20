# API Reference — Backend

This is the backend's own API, for anyone extending this demo. For the Recall.ai
endpoints this backend calls internally, see [`API_CONTRACT.md`](API_CONTRACT.md).

Base URL: `https://recall-api.ss-ubuntu-01.net`

## POST /sessions

Start a new intake session for a meeting.

Request body:
```json
{
  "meeting_url": "https://meet.google.com/xxx-xxxx-xxx",
  "mode": "chat"
}
```

`mode` is `"chat"` or `"voice"`. Both operate.

- **`chat`**: the assistant asks its questions as meeting chat messages, and the patient
  types the answers. The consent notice is pinned.
- **`voice`**: the assistant speaks its questions with OpenAI TTS, through Recall's
  output audio endpoint, and it listens to the real-time transcript. The consent notice
  is spoken. The bot of a voice session carries an `automatic_audio_output`
  configuration, which the output audio endpoint needs.

**The page has a control for this** since section 7a of `TASKS.md`. A session can also
start with curl:

```bash
curl -X POST https://recall-api.ss-ubuntu-01.net/sessions \
  -H 'content-type: application/json' \
  -d '{"meeting_url": "https://meet.google.com/xxx-xxxx-xxx", "mode": "voice"}'
```

The route makes the session row, then makes the Recall bot.

Response: HTTP 201.
```json
{
  "session_id": "abc123",
  "status": "waiting_for_bot"
}
```

A bot that Recall refuses does not fail the request. The session row exists, so the
result is HTTP 201 with the status `error`. Read the text of the failure from
`GET /sessions/{session_id}`. The route does not give HTTP 500 for a Recall failure.

## GET /sessions/{session_id}

Poll for session status.

Response:
```json
{
  "session_id": "abc123",
  "status": "in_progress",
  "mode": "chat",
  "summary": null,
  "error_reason": null
}
```

`status` values: `creating_bot`, `waiting_for_bot`, `in_progress`, `complete`, `error`.

`mode` is `chat` or `voice`, as `POST /sessions` set it. The page reads it to choose
one text: a chat patient answers in the meeting chat and a voice patient answers out
loud. It is here and not held by the page because a reload keeps the session id only,
and the backend owns the mode.

`error_reason` is a short text with the status `error`, and `null` with each other
status. The frontend shows this text to the user. See `IMPLEMENTATION.md`.

## GET /sessions/{session_id}/summary

Get the structured summary once the session is complete. Returns 404 until `status`
is `complete`.

The eight fields are always present. A field that the intake did not cover holds the
text `not discussed`: the intake asks a small number of questions, so this is usual and
it is not a fault. A red-flag feature that the patient reported comes at the start of
`associated_symptoms` after the text `RED FLAG:`.

The result is HTTP 500 if a session is `complete` and has no summary. The engine writes
the summary before it writes the status, so this is a fault of the backend and the route
does not hide it with an empty object.

Response:
```json
{
  "chief_complaint": "string",
  "onset_duration": "string",
  "location_character": "string",
  "severity": "string",
  "triggers": "string",
  "associated_symptoms": "string",
  "prior_treatments": "string",
  "notes": "string"
}
```

## POST /webhooks/recall

Internal endpoint. Receives bot status, chat, and transcript events from Recall.ai.
Not meant to be called directly.

Each request must carry the headers `webhook-id`, `webhook-timestamp` and
`webhook-signature`. The route verifies the signature against the workspace
verification secret before it reads the body. A bad signature gives HTTP 401, and a
body that is not an event gives HTTP 400. An empty `RECALL_WEBHOOK_SECRET` refuses
every request.

A verified request gives HTTP 200 and `{"ok": true}` immediately. The work runs after
the response, because Recall sends the events in sequence and has a 15 second timeout.

**What the events do.** `bot.in_call_recording` starts the intake: the assistant gives
the consent notice and then asks its first question. Chat mode pins the notice as a chat
message, and voice mode speaks it; the text differs in its last sentence, which says
where to answer.

**A `participant_events.chat_message` is one patient turn in a chat session.** The
backend reads the text, runs the engine, and sends the next question into the meeting
chat.

**A `transcript.data` is one utterance in a voice session, and one utterance is not a
turn.** A patient answers in parts, and Recall warns that an utterance often arrives
word by word. The backend puts each part in the `voice_buffers` table and waits for a
silence of `VOICE_TURN_GAP_SECONDS` (2.5). The silence ends the turn, the whole answer
goes to the engine one time, and the next question goes out as audio: OpenAI TTS makes
an mp3 and `POST /api/v1/bot/{id}/output_audio/` plays it. The wake-up is a thread,
because Recall sends the webhooks in sequence and a wait would delay each later
utterance.

**One session has one mode.** A chat message in a voice session is not a turn, and a
transcript utterance in a chat session opens no buffer. One `realtime_endpoints` list
carries both events to each bot, so each mode receives the events of the other and gives
nothing for them.

**The end of an intake is the same for both modes.** When the engine ends the intake,
the backend writes the summary, sends one closing message, waits
`BOT_LEAVE_DELAY_SECONDS`, and then takes the bot out of the call with
`POST /api/v1/bot/{id}/leave_call/`. The patient thus does not have to remove the bot.
The leave is irreversible, and a failed leave is a log line: the summary is written and
the status stays `complete`. A session in `error` keeps its bot, because an error usually
means that the bot takes no command.

**The bot does not answer itself.** The bot receives its own chat messages back, and it
plays its own audio into the meeting, so Recall can transcribe it back. A message or an
utterance whose speaker name is the bot name is not a turn.

The map from a bot event to `status`:

| Event | `status` | `error_reason` |
|---|---|---|
| `bot.joining_call`, `bot.in_waiting_room`, `bot.in_call_not_recording`, `bot.recording_permission_allowed` | `waiting_for_bot` | `null` |
| `bot.in_call_recording` | `in_progress` | `null` |
| `bot.recording_permission_denied`, `bot.fatal` | `error` | the `sub_code` |
| `bot.call_ended` before the intake is complete | `error` | `call_ended:<sub_code>` |
| `bot.call_ended` after the intake is complete | no change | no change |
| `bot.done` | no change | no change |

A status that is `complete` does not change. An event name that the backend does not
know gives HTTP 200 and makes no change. The `sub_code` is a plain string, not an enum:
Recall adds values without a notice.

**A repeated event does not change the result.** Svix delivers at least one time. A
chat message carries the Svix message id into the `turns` table, where
`UNIQUE(session_id, event_id)` refuses the second copy. The patient thus gets one
question for one message, and a retry adds no turn.

**A voice turn uses the buffer rowid, `voice-<id>`, and not a Svix message id.** A voice
turn is made of many events, so no one message names it. One buffer row becomes one
turn: the flush is one conditional UPDATE, so a second wake-up and a repeated utterance
each add no turn.

**The conversation is half-duplex.** One full patient message goes in, the assistant
answers it, and only then does the next message go in. A message that arrives before
the answer is refused and it is not queued, so a patient who sends an answer in two
parts loses the second part. This is the rule that `SPEC.md` gives for voice mode, with
the chat message as the unit in place of a pause.

**The order of the events does not change the result.** Webhook delivery is at-least-once
and has no order, and Recall was seen to send `bot.in_waiting_room` before
`bot.joining_call`. The backend uses the time of the event, `data.data.updated_at`, and
not the time it arrived. An event that is not newer than the last one that the session
applied gives HTTP 200 and makes no change. A duplicate event thus changes nothing. An
event with no time is applied, because a true event must not be lost.

## Extending this

To add a new interaction mode, add a value to `mode`, write a class with
`handle_incoming_turn`, `send_outgoing_turn` and `send_notice` in `backend/app/modes/`,
put it in the `MODES` registry of `app/modes/base.py`, give it a text in
`CONSENT_NOTICES`, and keep the session status machine the same. `app/modes/chat.py` and
`app/modes/voice.py` are the two examples: chat mode is one event in and one message
out, and voice mode buffers many events into one turn. The frontend only depends on
`status` and `summary`, not on how a mode is implemented.

Neither mode changed `app/engine/`. `git diff --stat -- backend/app/engine/` gave no
line in section 5 and again in section 6, which is the test of the boundary.
