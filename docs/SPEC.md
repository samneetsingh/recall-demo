# SPEC

Internal design doc. This is the source of truth for what to build. If a build decision
is not in here, add it here before you build it.

## Purpose

Show a real use case for the Recall.ai Meeting Bot API: an AI assistant that joins a
video call as a participant, conducts a pre-visit patient intake, and hands back a
structured clinical summary.

## Users

Two possible framings, both valid:
- A patient, before a scheduled doctor visit. The bot collects intake data ahead of time
  so the visit starts with context already gathered.
- A standalone triage flow. A patient talks to the bot first, and the summary helps
  route or prioritize care.

## What the bot does

1. Joins a meeting when given a Google Meet URL.
2. Introduces itself as an AI intake assistant.
3. Asks a sequence of intake questions, adjusting follow-ups based on answers.
4. Ends the interview once it has enough information.
5. Produces a structured summary and makes it available to the user.

## Interaction modes

### Mode 1: Chat (build first, must work)

The bot sends its questions as chat messages in the meeting. The patient replies in
chat. The bot reads chat messages in real time, sends the reply to the engine, and
sends the next question back as chat.

### Mode 2: Voice (stretch goal)

The bot speaks its questions using OpenAI TTS, played into the meeting as bot audio.
The bot listens to the real-time transcript. It waits for a pause in new transcript
text (a few seconds of silence) before treating the patient's turn as finished. This
is half-duplex: no interruption handling, no crosstalk handling. Full duplex voice is
out of scope for this build.

Chat mode stays in the app even after voice mode works. It is a legitimate fallback,
useful in noisy environments or for accessibility, not just a backup plan.

## The mock intake engine

- Powered by an LLM through LiteLLM. Not the real FIRY AI logic.
- Prompted to run a headache/neurology-style intake: chief complaint, onset, duration,
  location, character of pain, severity, triggers, associated symptoms, prior
  treatments tried.
- Can branch: a follow-up question can depend on a prior answer (e.g. "sharp pain"
  leads to a different follow-up than "dull pain").
- At the end, the same LLM is prompted with the full conversation to produce a
  structured summary.

### Summary shape

Structured, not free text. Suggested fields:
- Chief complaint
- Onset and duration
- Location and character of pain
- Severity (patient-reported)
- Triggers
- Associated symptoms
- Prior treatments tried
- Free-text notes for anything that doesn't fit a field

## What is explicitly out of scope

- Real FIRY AI logic or prompts.
- HIPAA-related controls of any kind. Note as a next step, not a build task.
- Zoom or Microsoft Teams support. Google Meet only.
- Full duplex voice, interruption handling.
- Any authentication or user accounts. This is a single-session demo.
- Disclaimers beyond identifying the bot as an AI intake assistant, not a physician.

## Data flow, short version

1. User pastes a Google Meet URL into the frontend.
2. Frontend calls the backend to create a session.
3. Backend calls Recall to create a bot for that meeting URL.
4. Bot joins. Recall sends events to the backend (chat messages or real-time
   transcript, depending on mode).
5. Backend runs the engine, gets the next question, sends it back through Recall
   (chat message or TTS audio).
6. Repeat until the engine signals the intake is complete.
7. Backend generates the summary and stores it.
8. Frontend polls the backend for status, shows the summary once ready.
