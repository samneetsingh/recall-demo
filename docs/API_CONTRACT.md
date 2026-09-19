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

- Send: see "Sending Chat Messages" in the docs. Backend posts the bot's next question
  as a chat message in the meeting.
- Receive: see "Receiving Chat Messages." Comes through as a webhook or real-time
  event. Backend reads the patient's reply from here.

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

## Open questions to confirm while building

- [ ] Exact real-time transcript delivery mechanism: webhook vs WebSocket.
- [ ] Exact audio format Recall expects for output audio.
- [ ] Whether chat messages arrive as webhook events or need to be polled.
- [ ] Bot sub-codes to handle for error states (see "Bot Sub Codes" in the docs).
