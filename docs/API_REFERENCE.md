# API Reference: Backend

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

**`mode` is `"chat"`. Voice mode has no implementation on `main`.** The route tests the
mode against the `MODES` registry of `backend/app/modes/base.py` first. A mode with no
implementation gives HTTP 400 with the detail `the mode <x> has no implementation`. The
test comes before the session row and before the Recall bot, because a bot costs money
and joins a real meeting. `{"mode": "voice"}` on `main` thus gives HTTP 400 and makes
nothing. The branch `feat/voice-mode` holds the voice work.

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
status. The frontend shows this text to the user.

## GET /sessions/{session_id}/summary

Get the structured summary once the session is complete. Returns 404 until `status`
is `complete`.

The eight fields are always present. A field that the intake did not cover holds the
text `not discussed`: the intake asks a small number of questions, so this is usual and
it is not a fault. A red-flag feature that the patient reported comes at the start of
`associated_symptoms` after the text `RED FLAG:`.

**The result is HTTP 500 if a session is `complete` and has no summary.** Two different
paths reach that state:

- A fault of the backend. `engine/loop.py` writes the summary before it writes the
  status, so a complete intake always has one.
- **A call that ended early.** `bot.call_ended` with a normal sub-code makes the status
  `complete`, and an intake that stopped before its last question has no summary. The
  patient who leaves the call in the middle of the intake is the usual cause.

The second path is a known gap. A partial summary, made from the turns that exist, was
scoped and cut for time. The route does not hide either path with an empty object.

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

Internal endpoint. Receives bot status and chat events from Recall.ai. Not meant to be
called directly.

Each request must carry the headers `webhook-id`, `webhook-timestamp` and
`webhook-signature`. The route verifies the signature against the workspace
verification secret before it reads the body. A bad signature gives HTTP 401, and a
body that is not an event gives HTTP 400. An empty `RECALL_WEBHOOK_SECRET` refuses
every request.

A verified request gives HTTP 200 and `{"ok": true}` immediately. The work runs after
the response, because Recall sends the events in sequence and has a 15 second timeout.

**What the events do.** `bot.in_call_recording` starts the intake: the assistant sends a
pinned consent notice and then asks its first question. A
`participant_events.chat_message` is one patient turn: the backend reads the text, runs
the engine, and sends the next question into the meeting chat. When the intake ends, the
backend writes the summary, sends one closing message, waits `BOT_LEAVE_DELAY_SECONDS`,
and then takes the bot out of the call with `POST /api/v1/bot/{id}/leave_call/`. The
patient thus does not have to remove the bot.

**The bot leaves on the error path too.** A session that goes to `error` gets a different
last line, which says that a technical problem stopped the intake. The bot then leaves in
the same manner. The usual error is a failed model call, and the bot itself is in good
health, so it takes the leave command. The leave is irreversible. A failed leave is a log
line only: the summary, the status and the reason do not change. The client retries a
leave one time after a transient failure.

**Chat mode reads no transcript.** The create-bot request of a chat session subscribes to
`participant_events.chat_message` only, and it names no transcript provider, so no
`transcript.data` event arrives. The route keeps a rule for the event: one that does
arrive gives a log line and makes no change to the session.

**The bot does not answer itself.** The `participant_events.chat_message` payload has no
field that says the bot sent the message, so the backend compares the sender name with
`RECALL_BOT_NAME`. A message from that name is not a turn. A live Google Meet call in
session 09 showed that Meet sends no event for a message that the bot sent, so the filter
did not operate one time in that call. Keep it: the payload gives no marker, the Recall
document does not promise this behavior, and another platform can be different.

The map from a bot event to `status`:

| Event | `status` | `error_reason` |
|---|---|---|
| `bot.joining_call`, `bot.in_waiting_room`, `bot.in_call_not_recording`, `bot.recording_permission_allowed` | `waiting_for_bot` | `null` |
| `bot.in_call_recording` | `in_progress` | `null` |
| `bot.recording_permission_denied`, `bot.fatal` | `error` | the `sub_code` |
| `bot.call_ended` with a normal sub-code | `complete` | `null` |
| `bot.call_ended` with a fault, an unknown or an absent sub-code | `error` | `call_ended:<sub_code>` |
| `bot.done` | no change | no change |

`API_CONTRACT.md` holds the list of the normal sub-codes. The `sub_code` is a plain
string and not an enum: Recall adds values without a notice. A value that the list does
not hold makes the status `error` and keeps its raw value as the reason, so a new
sub-code cannot stop the application. An absent sub-code gives the reason
`call_ended:unknown`.

A call that ends before the last question thus reaches `complete` with no summary. See
the gap in `GET /sessions/{session_id}/summary`.

**`complete` and `error` are both terminal.** A session in one of them does not change
again. A later bot event cannot take a session out of `error`, and it cannot erase the
reason. An event name that the backend does not know gives HTTP 200 and makes no change.

**A repeated event does not change the result.** Svix delivers at least one time. A
chat message carries the Svix message id into the `turns` table, where
`UNIQUE(session_id, event_id)` refuses the second copy. The patient thus gets one
question for one message, and a retry adds no turn.

**The conversation is half-duplex.** One full patient message goes in, the assistant
answers it, and only then does the next message go in. A message that arrives before
the answer is refused and it is not queued, so a patient who sends an answer in two
parts loses the second part.

**The order of the events does not change the result.** Webhook delivery is at-least-once
and has no order, and Recall was seen to send `bot.in_waiting_room` before
`bot.joining_call`. The backend uses the time of the event, `data.data.updated_at`, and
not the time it arrived. An event that is not newer than the last one that the session
applied gives HTTP 200 and makes no change. A duplicate event thus changes nothing. An
event with no time is applied, because a true event must not be lost.

## Extending this

To add a new interaction mode:

1. Add the value to `Mode` in `backend/app/db/models.py`.
2. Write a class in `backend/app/modes/` with the **three** methods of the `TurnMode`
   protocol in `app/modes/base.py`: `handle_incoming_turn`, `send_outgoing_turn` and
   `send_notice`. `app/modes/chat.py` is the example.
3. Put the class in the `MODES` registry of `app/modes/base.py`. `POST /sessions` reads
   that registry, so the new mode stops giving HTTP 400.
4. **Extend the dispatch of `backend/app/routes/webhooks.py`.** The registry alone is not
   sufficient. `_dispatch_event` sends one event name to the intake loop, the
   chat-specific `CHAT_EVENT`, and it writes a log line for each other real-time event. A
   registered mode whose turns arrive on a different event gets no turn until this
   dispatch knows that event.

The session status machine does not change, and the frontend depends on `status` and
`summary` only.

Voice mode is not a drop-in addition. It also needs a transcript provider and the event
`transcript.data` in the create-bot request, a turn boundary that joins the parts of one
spoken answer, and an output path for the audio. See the branch `feat/voice-mode`.
