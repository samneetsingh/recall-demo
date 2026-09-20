# Recall Demo: AI Pre-Visit Intake Assistant

A demo built on the Recall.ai Meeting Bot API. A bot joins a Google Meet call and runs a
patient intake interview, the way a headache or neurology clinic runs a pre-visit
questionnaire. At the end it writes a structured clinical summary.

**Try it:** https://recall.samneet.com
**Backend API:** https://recall-api.ss-ubuntu-01.net

## Why this demo

I am the founding engineer at FIRY AI, a clinical AI platform for headache and neurological care. I build conversational intake and triage systems as my day job. This demo reuses that shape of problem, structured and adaptive patient interviews, on top of Recall's API. The intake logic here is a prompted general-purpose LLM, not FIRY's real clinical engine.

The use case fits two scenarios:

- A patient gives intake details before a scheduled visit, so the visit starts with the context already collected.
- A standalone triage flow, to route or prioritize care before a clinician sees the patient.

## How it works

1. Open the page and paste a Google Meet URL.
2. A bot joins the call. Its name is "Headache Assistant" (`RECALL_BOT_NAME`).
3. The bot pins a consent notice in the meeting chat, then asks its questions there. Each
   follow-up adapts to the last answer. The limit is six questions.
4. The bot says a closing line, leaves the call, and the page shows the eight summary
   fields.

The intake runs in **chat mode**. The bot sends each question as a meeting chat message,
and reads the patient answers from `participant_events.chat_message` on a real-time
webhook.

**Voice mode is a stretch goal that I did not finish.** It is not on `main`, and it is not
demonstrable. The `MODES` registry has one entry, `chat`, and `POST /sessions` with the
mode `voice` gives HTTP 400 and makes no bot. The unfinished work (OpenAI TTS output audio
and a transcript turn boundary) is on the branch `feat/voice-mode`.

## See the intake with no Recall account and no call

```bash
cd backend
poetry install
OPENAI_API_KEY=sk-... poetry run python scripts/intake_console.py
```

The script puts a terminal implementation in the same `MODES` registry that chat mode
uses. It runs the real state machine, the real database and the real model, and you are
the patient. It does not exercise the Recall wiring. Each run writes its database to a new
temporary directory.

## Documentation

| File | What it is |
|---|---|
| [`docs/FLOW.md`](docs/FLOW.md) | **Start here.** What the code does today, point to point: the state, one turn, the status machine, and the known faults |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | The pieces, the two Recall event channels, and why the deploy is split |
| [`docs/API_CONTRACT.md`](docs/API_CONTRACT.md) | The Recall endpoints and events this build uses, with the Recall doc consulted for each answer |
| [`docs/API_REFERENCE.md`](docs/API_REFERENCE.md) | The backend's own HTTP API |

## Run it yourself

Python 3.13 or newer is necessary (`backend/pyproject.toml`). The frontend needs Node.

```bash
cd backend
cp .env.example .env        # put your keys in it
poetry install
poetry run pytest           # 296 tests. No keys and no network necessary
docker compose -f deploy/docker-compose.yml up -d --build
```

Three environment variables are necessary. `backend/.env.example` lists them, and the
optional ones:

| Variable | Why |
|---|---|
| `RECALL_API_KEY` | The create-bot call and the chat calls |
| `OPENAI_API_KEY` | The intake engine and the summary |
| `RECALL_WEBHOOK_SECRET` | The workspace verification secret. **An empty value refuses every webhook.** The bot then joins the call and never asks a question |

**Docker is the path that works.** `DB_PATH` defaults to `/app/data/recall_demo.sqlite3`,
the named volume in the container. `poetry run uvicorn app.main:app` on a laptop makes
that directory at startup and crashes with `PermissionError`. For a local process, set
`DB_PATH=./data/recall_demo.sqlite3` in `.env`.

A full call also needs two things that are not in this repo:

- **A public URL that Recall can reach.** Recall pushes its events to `PUBLIC_BASE_URL`.
  A backend on localhost gets none of them. Put a tunnel in front of it (cloudflared,
  ngrok) and set `PUBLIC_BASE_URL` to the tunnel URL.
- **A dashboard webhook endpoint**, made by hand in the Recall dashboard, with its
  workspace verification secret in `RECALL_WEBHOOK_SECRET`. Without it, the `bot.*` status
  events have no destination. See [`docs/API_CONTRACT.md`](docs/API_CONTRACT.md).

The frontend holds the backend URL as a constant (`const API` in
`frontend/public/index.html`). `npx wrangler dev` thus serves a local page that calls the
deployed backend. Change that constant to call your own.

## Limitations and next steps

### Faults I know about

[`docs/FLOW.md`](docs/FLOW.md) gives the mechanism of each one.

1. **A call that ends early gives no summary.** `bot.call_ended` with a normal sub-code
   (the patient hangs up, or the host ends the call) makes the status `complete`. If the
   intake did not reach its end, the row has no summary, so
   `GET /sessions/{id}/summary` gives HTTP 500. `backend/app/engine/summary.py` takes any
   log and gives the eight fields, so the fix is to call it on that path before the status
   goes to `complete`. I scoped this and then cut it for time.
2. **A refused patient message is lost.** The conversation is half-duplex: one message in,
   one question out. A message that arrives before the answer is refused by the `turns`
   insert, and its text stays in the container log. A patient who sends an answer in two
   parts loses the second part.
3. **A turn that fails has no retry.** If the handler that owns the newest turn stops, the
   conversation waits and nothing acts. The `turns` table makes this visible (the last row
   has the role `patient`, and it is old) and no code reads it.
4. **A patient who stops answering keeps the session `in_progress` forever.** Only
   `bot.call_ended` ends it.
5. **The echo filter is the bot name.** A chat message whose sender name is
   `RECALL_BOT_NAME` is not a patient turn. The payload has no "this is the bot" field, and
   a `null` sender name counts as a patient.
6. **A real-time retry is not proved to keep its `webhook-id`.** That header is the repeat
   protection of a chat turn. Svix keeps the id for a dashboard event, and Recall retries a
   real-time message with its own policy. If the id changes, a retry makes a second turn.
7. **Two sessions can hold one bot id.** `get_session_by_bot_id` has no order and no limit,
   so it gives an arbitrary row. Recall gives a new bot for each session, so the
   application cannot make this condition, but a test did.

### Out of scope for this demo

- **Not HIPAA compliant.** A real clinical version must be. Not attempted here. The bot
  does ask Recall for zero data retention (`"retention": null`), so Recall keeps no audio,
  no video and no transcript.
- **Google Meet only.** Zoom and Microsoft Teams each need more setup on Recall's side
  (Zoom needs an app in the Zoom Marketplace).
- **Mock intake logic.** A prompted general-purpose model, written for this repo.
- **No authentication.** One session at a time, and no accounts.

Next steps in order: the partial summary, voice mode from `feat/voice-mode`, the faults
above, then HIPAA-track infrastructure and accounts.
