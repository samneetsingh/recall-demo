# Recall Demo — AI Pre-Visit Intake Assistant

A demo built on the Recall.ai Meeting Bot API. A bot joins a video call and conducts a
patient intake interview, the way a headache or neurology clinic would run a pre-visit
questionnaire. It ends the call with a structured clinical summary.

**Try it:** https://recall.samneet.com
**Backend API:** https://recall-api.ss-ubuntu-01.net

## Why this demo

I am the founding engineer at FIRY AI, a clinical AI platform for headache and neurological
care. I build conversational intake and triage systems as my day job. This demo reuses that shape of problem — structured, adaptive patient interviews — on top of Recall's API, mocked
with a general-purpose LLM instead of FIRY's real logic.

The use case fits two scenarios:
- A patient fills in intake details before a scheduled doctor visit, so the visit
  starts with context already gathered.
- A standalone triage flow, helping route or prioritize care before a human sees the
  patient.

## How it works

1. Open the app, paste a Google Meet URL.
2. A bot named "FIRY Intake Assistant" joins the call.
3. The bot asks intake questions and adapts follow-ups based on your answers.
4. When the interview ends, a structured summary appears on the page.

Two interaction modes:
- **Chat** — the bot asks questions and reads answers over meeting chat.
- **Voice** — the bot speaks its questions with text-to-speech, and listens to the
  live transcript for your reply.

Both modes exist on purpose. Voice is the more natural interaction. Chat is a real
fallback for noisy environments or accessibility, not just a backup plan.

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for how the pieces fit together, and
[`docs/API_REFERENCE.md`](docs/API_REFERENCE.md) for the backend's own API, if you want
to extend this.

## Setup and running locally

```bash
# Backend
cd backend
poetry install
poetry run uvicorn app.main:app --reload

# Frontend
cd frontend
npm install
npx wrangler dev
```

Environment variables needed (backend): `RECALL_API_KEY`, `OPENAI_API_KEY`.

## Limitations and next steps

This is a demo, not a production system. Known gaps, left as-is on purpose given the
timeline:

- **Not HIPAA compliant.** A real clinical version of this would need to be. Not
  attempted here.
- **Half-duplex voice only.** The bot does not handle interruptions or crosstalk. It
  waits for a pause in the transcript to treat a turn as finished. The pause is 2.5
  seconds, and a patient who thinks for longer sends half an answer.
- **Voice mode uses the real-time transcript, and Recall says not to.** Recall's own
  guide points a conversational agent at Output Media with a voice-to-voice model
  instead. This build keeps the transcript on purpose: Output Media always sends video,
  it is mutually exclusive with the output-audio endpoint this bot speaks through, and
  full duplex is out of scope. The cost is the delay — 1 to 3 seconds for the
  transcript, 2.5 for the pause, and the text-to-speech call on top. A production voice
  agent would take Recall's route.
- **Google Meet only.** Zoom and Microsoft Teams both need extra setup on Recall's
  side (Zoom needs an app registered in the Zoom Marketplace) that was not worth the
  time for a demo.
- **Mock intake logic**, not FIRY's real clinical engine. Prompted to behave similarly,
  built from scratch for this repo.
- **No authentication.** Single-session demo, no accounts.

Given more time, the next steps in order would be: full duplex voice, HIPAA-track
infrastructure, Zoom/Teams support, and multi-session/account handling.
