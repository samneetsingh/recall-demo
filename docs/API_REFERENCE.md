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

Response: HTTP 201.
```json
{
  "session_id": "abc123",
  "status": "creating_bot"
}
```

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
Verified against Recall's webhook signature. Not meant to be called directly.

## Extending this

To add a new interaction mode, add a value to `mode`, implement the matching input/
output handling in `backend/engine/`, and keep the session status machine the same —
the frontend only depends on `status` and `summary`, not on how a mode is implemented.
