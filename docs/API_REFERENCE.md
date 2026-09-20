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

`mode` is `"chat"` or `"voice"`.

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
  "summary": null,
  "error_reason": null
}
```

`status` values: `creating_bot`, `waiting_for_bot`, `in_progress`, `complete`, `error`.

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

**What the events do.** `bot.in_call_recording` starts the intake: the assistant sends
a pinned consent notice and then asks its first question. A `participant_events.chat_message` is one patient turn: the backend
reads the text, runs the engine, and sends the next question into the meeting chat. When
the engine ends the intake, the backend writes the summary and then sends one closing
message. `transcript.data` gets a log line only until section 6 of `TASKS.md`.

**The bot does not answer itself.** The bot receives its own chat messages back. A
message whose sender name is the bot name is not a turn.

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
`handle_incoming_turn` and `send_outgoing_turn` in `backend/app/modes/`, put it in the
`MODES` registry of `app/modes/base.py`, and keep the session status machine the same.
`app/modes/chat.py` is the example. The frontend only depends on `status` and `summary`,
not on how a mode is implemented.
