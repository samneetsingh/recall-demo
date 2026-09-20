# API_CONTRACT — Recall.ai

Internal reference for the Recall.ai endpoints, webhooks, and event payloads this
project uses. Check this before writing a Recall API call, and update it if the real
behavior differs from what is written here.

Docs root: https://docs.recall.ai

## Auth

All requests use `Authorization: Token $RECALL_API_KEY`. Store the key as an
environment variable on the backend. Never in the frontend, never in a log line.

## Create a bot

`POST /api/v1/bot/`

Minimum body:
```json
{
  "meeting_url": "https://meet.google.com/xxx-xxxx-xxx",
  "bot_name": "FIRY Intake Assistant"
}
```

A bot is single-use and maps to one meeting. Bot ID comes back in the response; store
it against the session in SQLite.

## Chat messages (Mode 1)

**Send.** `POST /api/v1/bot/{id}/send_chat_message/` with the body
`{"to": "everyone", "message": "..."}`. Google Meet takes the recipient `everyone`
only, and it refuses a message of more than 500 characters. `app/modes/chat.py` cuts a
longer message into parts.

**Pin a message.** The send endpoint takes `"pin": true`. A pinned message stays
visible for a participant who joins later. **The pin needs continuous chat disabled in
the call.** If it is on, the message goes out and the pin does not.

**The create-bot `chat` hooks. This build does not use them.** The body takes a `chat`
object with `on_bot_join` and `on_participant_join`, and `on_bot_join` sent the consent
notice up to session 09. Recall sends that message, so its time is not under the control
of the backend: in the live call the first question went out 1.74 seconds after the join
and the notice came after it. The backend sends the notice itself now, with the send
endpoint and `pin`, immediately before the first question.

**Receive.** The real-time endpoint of the create-bot request, with the event
`participant_events.chat_message`. The true shape, from the document
`real-time-event-payloads`:

```json
{
  "event": "participant_events.chat_message",
  "data": {
    "data": {
      "participant": { "id": 100, "name": "Samneet Singh", "is_host": true,
                       "platform": "desktop", "extra_data": {}, "email": null },
      "timestamp": { "absolute": "2026-09-20T05:48:18.360372Z", "relative": 76.8 },
      "data": { "text": "I get bad headaches", "to": "everyone" }
    },
    "realtime_endpoint": { "id": "...", "metadata": {} },
    "participant_events": { "id": "...", "metadata": {} },
    "recording": { "id": "...", "metadata": {} },
    "bot": { "id": "...", "metadata": {} }
  }
}
```

The text is at `data.data.data.text` and the sender is at
`data.data.participant.name`. **The payload has no field that says "the bot sent this".**
The bot receives its own messages back, so the backend compares the sender name with
`RECALL_BOT_NAME`.

**A real-time event is not a dashboard event.** It goes directly to the URL of the
create-bot request, it is not in the Webhooks console, and Recall retries it up to 60
times, one each second. The signature is the same workspace secret.

## Real-time transcript (Mode 2)

- Set the transcription provider to Recall's own transcription when creating the bot.
- Subscribe to real-time transcript events (webhook or WebSocket, confirm which one
  this build uses once implemented).
- Use gaps in new transcript text as the turn-taking signal: after N seconds with no
  new transcript, treat the patient's turn as done and pass it to the engine.

## Output audio (Mode 2)

- See "Output Speech/Audio from the Bot" in the docs.
- Backend generates audio with OpenAI TTS, then sends it to Recall's output-audio
  endpoint/stream so the bot plays it into the meeting.
- Confirm expected audio format/encoding in the docs before wiring this up; do not
  assume it matches OpenAI TTS's default output format.

## Bot status webhooks

- Subscribe to bot status change events (joining, in_call, done, error states).
- Use these to update session status for the frontend to poll (e.g. "waiting,"
  "bot joined," "interview in progress," "complete," "error").

## Webhook verification

- Recall signs webhook/callback requests. Verify signatures on the backend before
  trusting payloads. See "Verifying webhooks, websockets and callback requests."

## Answers to the open questions

Session 04 answered these questions with the `recall-ai` MCP server, which reads the
live Recall.ai documentation. The workspace is `Sandbox`, and it supports bot schema
v1.11 only.

### [x] The delivery mechanism of the real-time transcript: webhook or WebSocket

Recall supplies both. You select the mechanism in the Create Bot request, in
`recording_config.realtime_endpoints[].type`, which is `webhook` or `websocket`. The
event `transcript.data` is necessary for a real-time transcript. Two fields are
necessary together: `recording_config.transcript.provider` and
`recording_config.realtime_endpoints`. If one is absent, no transcript event comes.

```json
"recording_config": {
  "transcript": {
    "provider": {
      "recallai_streaming": { "mode": "prioritize_low_latency", "language_code": "en" }
    }
  },
  "realtime_endpoints": [
    { "type": "webhook", "url": "https://.../webhooks/recall", "events": ["transcript.data"] }
  ]
}
```

**This build uses the webhook type.** The backend is behind nginx, and the nginx
configuration does not pass the `Upgrade` and `Connection` headers at this time. A
webhook needs no change to nginx. The two types give the same payload.

More facts:

- The mode `prioritize_low_latency` gives a lower delay. The default is
  `prioritize_accuracy`, which uses an asynchronous model and has more delay.
- The event `transcript.partial_data` gives the words before the utterance is complete.
  The turn-taking logic of mode 2 does not need it. `transcript.data` is sufficient.
- The events `participant_events.speech_on` and `participant_events.speech_off` are a
  better turn-taking signal than a timer. Look at them if the silence timer is not good.
- Recall sends the webhooks in sequence. A slow handler delays the next event. The
  handler must answer 2xx immediately and do the work after that.
- A failure of the transcription gives a `transcript.failed` event on the **dashboard**
  webhook endpoint, not on the real-time endpoint. The two configurations are different
  and their event sets do not intersect.

Method: `recall-ai` MCP, `get_doc` for `bot-real-time-transcription`.

### [x] The audio format for the output audio

**mp3, as a base64 string.** The body of `POST /api/v1/bot/{id}/output_audio/` is:

```json
{ "kind": "mp3", "b64_data": "<the base64 mp3>" }
```

`kind` accepts `mp3` only. OpenAI TTS gives mp3 by default, so no conversion of the
format is necessary. The backend must only encode the bytes to base64.

**One condition is important:** the Output Audio endpoint operates only if the bot was
made with an `automatic_audio_output` configuration. Recall tells you to put a short
silent mp3 in that configuration if you do not want automatic audio. Put this in the
Create Bot request of mode 2.

Do not use the Output Media feature for this demo. It is the other method to make a bot
speak: it streams a web page that you control into the meeting, with the camera or the
screen share. It is more powerful, but it is mutually exclusive with
`automatic_audio_output` and with the Output Audio endpoint, and it always sends video.

Method: `recall-ai` MCP, `get_doc` for `output-audio-in-meetings` and `stream-media`.

### [x] Chat messages: webhook events or polling

**Webhook events. No polling is necessary.** Chat messages come through the same
real-time endpoint configuration as the transcript. Put the event
`participant_events.chat_message` in `recording_config.realtime_endpoints[].events` in
the Create Bot request.

```json
"recording_config": {
  "realtime_endpoints": [
    { "type": "webhook", "url": "https://.../webhooks/recall", "events": ["participant_events.chat_message"] }
  ]
}
```

Google Meet has full support, with no limitation. Recall also keeps all chat messages
for a download after the call, at
`recordings[i].media_shortcuts.participant_events.data.participant_events_download_url`.
The demo does not need this, because it reads the messages during the call.

To receive chat messages without a recording, add `"participant_events": {}` and
`"retention": null` to `recording_config`.

Method: `recall-ai` MCP, `get_doc` for `receiving-chat-messages`.

### [x] The bot sub-codes to handle for the error states

A `sub_code` comes with a bot status change event, in `data.data.sub_code`. The
dashboard webhook endpoint receives these events, with this shape:

```json
{
  "event": "bot.fatal",
  "data": { "data": { "code": "fatal", "sub_code": "meeting_link_invalid", "updated_at": "..." },
            "bot": { "id": "...", "metadata": {} } }
}
```

The events are `bot.joining_call`, `bot.in_waiting_room`, `bot.in_call_not_recording`,
`bot.recording_permission_allowed`, `bot.recording_permission_denied`,
`bot.in_call_recording`, `bot.call_ended`, `bot.done` and `bot.fatal`. A `sub_code`
comes with `bot.fatal`, `bot.call_ended` and `bot.recording_permission_denied` (Zoom).

**Important rule: do not make the `sub_code` an enum.** Recall adds values without a
notice. The backend must write the value into the `error_reason` column and show it. A
value that the code does not know must not stop the application.

These sub-codes are the applicable ones for a Google Meet demo. Each one makes the
session status `error`:

| Sub code | Meaning |
|---|---|
| `meeting_link_invalid` | The meeting does not exist, or the link is bad. The most frequent error of the demo |
| `meeting_link_expired` | The link is not valid now |
| `meeting_not_found` | No meeting is at the link |
| `meeting_not_started` | The meeting did not start |
| `meeting_requires_sign_in` | Only a user with an account can join. The bot has no Google account |
| `google_meet_knocking_disabled` | The host settings do not let the bot ask to join |
| `google_meet_bot_blocked` | The meeting does not permit the bot |
| `google_meet_organisation_restricted` | The call permits only members of the organization of the host |
| `google_meet_video_error` | A Google Meet video error stopped the join |
| `google_meet_meeting_room_not_ready` | The meeting room was not ready |
| `google_meet_internal_error` | An internal problem of Google Meet |
| `bot_errored` | An unexpected error in the bot |
| `failed_to_launch_in_time` | A problem of the Recall infrastructure |

These `bot.call_ended` sub-codes are normal, not an error. Do not make the status
`error` for them:

| Sub code | Meaning |
|---|---|
| `call_ended_by_host` | The host ended the call |
| `bot_kicked_from_call` | The host removed the bot |
| `timeout_exceeded_everyone_left` | The other participants left |
| `timeout_exceeded_noone_joined` | No person joined |
| `call_ended_by_platform_waiting_room_timeout` | The Google Meet waiting room timeout is 10 minutes |
| `timeout_exceeded_silence_detected` | Recall thinks that only bots are in the call |

A demo that ends before the intake is complete must make the status `complete` or
`error` with the sub-code as the reason. The frontend polls, and it must not wait for a
session that has no bot in the call.

Method: `recall-ai` MCP, `get_doc` for `sub-codes` and `bot-status-change-events`.

## The region

**The workspace uses `us-west-2`, the pay-as-you-go region.** Sam gave this answer in
session 05. The host is `https://us-west-2.recall.ai`, and the setting is
`RECALL_API_BASE`. The API key is specific to the region: a key from another region
gives HTTP 401 with the code `authentication_failed`, and the text of the answer names
the four regions.

## Webhook verification: how this build does it

The scheme is HMAC-SHA256 over `webhook-id.webhook-timestamp.raw_body`. The key is the
base64 body of the `whsec_...` secret. The signature header holds one or more
`v1,<base64>` entries, because a secret rotation keeps the old secret active for 24
hours.

**This build uses the `svix` package.** Sam decided this in session 05.

- `svix.webhooks.Webhook.verify` reads `webhook-id` or `svix-id`, and the same for the
  timestamp and the signature. Recall sends the `webhook-*` names, so no header change
  is necessary.
- `svix` 2.5.0 gives `None` from `verify`. It calls `standardwebhooks` with
  `json_parse=False`, so the caller must parse the body itself, after the check.
- `standardwebhooks` refuses a timestamp that is more than 5 minutes old or 5 minutes in
  the future. No extra check is necessary.
- The headers come only after a workspace verification secret exists. Without the secret,
  Recall sends no `webhook-*` header and no request can be verified.

Method: `recall-ai` MCP, `get_doc` for `authenticating-requests-from-recallai`, and the
installed source of `svix` and `standardwebhooks`.

## Webhook configuration: an open item

`list_webhook_endpoints` on the `Sandbox` workspace gives an empty list. **No dashboard
webhook endpoint exists at this time.** The bot status events have no destination. Make
the endpoint in the Recall dashboard before the task that receives the events. This is a
manual task for a human, in the dashboard.

Two different configurations send events, and this demo uses both:

| Configuration | Where you make it | Events it sends |
|---|---|---|
| The dashboard webhook | The Recall dashboard, one time | `bot.*` status changes, `transcript.done`, `transcript.failed` |
| `recording_config.realtime_endpoints` | In each Create Bot request | `transcript.data`, `participant_events.chat_message` |

Both can point at the same URL, `POST /webhooks/recall`. The event sets do not
intersect. `dashboard_uses_workspace_verification_secret` is true for this workspace, so
one verification secret verifies the requests of both.

Method: `recall-ai` MCP, `list_webhook_endpoints` and `get_info`.
