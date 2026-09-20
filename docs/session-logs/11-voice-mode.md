# 11 — Voice mode

Written in ASD-STE100 Simplified Technical English.

- **Date:** 2026-09-20
- **Task:** Section 6 of [`../TASKS.md`](../TASKS.md). See
  [`../task-06-voice-mode/todo.md`](../task-06-voice-mode/todo.md)
- **Result:** partial — voice mode is built, tested and proved against the container.
  **A live Google Meet call is the one step that is open**, because no person was awake
  to admit the bot. The procedure for that call is at the end of this log.

## Summary

The assistant speaks now. This session made `app/tts/openai_tts.py`, `app/modes/voice.py`
and the `voice_buffers` table, added `send_output_audio` to the Recall client, put the
`automatic_audio_output` configuration on a voice bot, and connected `transcript.data`
to the intake loop. **One transcript utterance is not a turn:** the parts of one answer
wait in the database, and a silence of 2.5 seconds ends the turn. The tests went from
265 to 348. Chat mode and the four engine modules are byte for byte the same.

## Files changed

| File | Change | Reason |
|---|---|---|
| `backend/app/tts/__init__.py` | new | The package |
| `backend/app/tts/openai_tts.py` | new | `speak(text) -> mp3 bytes`. The one module that knows about TTS |
| `backend/app/modes/voice.py` | new | `VoiceMode`, `VoiceTurnGap`, `utterance_text`, the echo filter |
| `backend/app/modes/base.py` | edit | The `voice` entry in `MODES`, `CONSENT_NOTICE_VOICE`, `CONSENT_NOTICES` |
| `backend/app/db/models.py` | edit | Migration 6: `voice_buffers` and its partial unique index |
| `backend/app/db/session_store.py` | edit | `_now` gives microseconds, `add_voice_part`, `claim_voice_buffer`, `open_voice_buffer` |
| `backend/app/recall/client.py` | edit | `send_output_audio`, `SILENT_MP3_B64`, the mode in `build_request_body` |
| `backend/app/routes/webhooks.py` | edit | `_mode_of`, `_start_intake`, `_run_voice_turn`, `_arm_voice_flush`, `flush_voice_turn` |
| `backend/app/config.py` | edit | `OPENAI_TTS_MODEL`, `_VOICE`, `_INSTRUCTIONS`, `VOICE_TURN_GAP_SECONDS` |
| `backend/tests/test_tts_openai.py` | new | 16 tests of the TTS call |
| `backend/tests/test_modes_voice.py` | new | 28 tests of the parse, the buffer, the gap and the sends |
| `backend/tests/conftest.py` | edit | `transcript_payload`, the true shape of the event |
| `backend/tests/test_routes_webhooks.py` | edit | 87 tests. The voice fakes in `offline`, and the voice wire |
| `backend/tests/test_recall_client.py` | edit | 38 tests. The audio send and the voice body |
| `backend/tests/test_session_store.py` | edit | 30 tests. The buffer, and two claims at the same time |
| `backend/tests/test_db_migrations.py` | edit | 10 tests. The new table in a new file and in an old file |
| `backend/tests/test_engine_loop.py` | edit | `voice` has an implementation now, so the test takes it out |
| `docs/TASKS.md` | edit | Section 6, and the new section 7a |
| `docs/FLOW.md` | edit | The header, part 2, flow D, part 9 |
| `docs/API_CONTRACT.md` | edit | The two Mode 2 sections |
| `docs/API_REFERENCE.md` | edit | A voice session, and the transcript events |
| `README.md` | edit | One limitation: Recall says not to use the transcript for an agent |
| `docs/task-06-voice-mode/todo.md` | new | The plan of this session |
| `docs/session-logs/11-voice-mode.md` | new | This log |

**`frontend/`, `app/engine/` and `app/modes/chat.py` did not change.**
`pyproject.toml` and `poetry.lock` did not change. **This session added no package.**

## Decisions

Sam answered six questions at the start of this session. The first six items are his.

- **The turn-taking state is a new table and a debounce timer.** Sam selected it against
  a table with no timer and against `participant_events.speech_off`. The parts and the
  time of the newest part are in `voice_buffers`, and a `threading.Timer` of
  `VOICE_TURN_GAP_SECONDS` wakes the process. **The state is in SQLite and the timer is
  only a wake-up**, so a restart of the container loses the wake-up and not the answer.
  A table with no timer deadlocks: the last utterance of an answer never flushes,
  because nothing else arrives. `speech_off` arrives before the last `transcript.data`,
  which has a delay of 1 to 3 seconds, so it cuts the end of an answer.
- **The `event_id` of a voice turn is `voice-<buffer rowid>`.** Sam selected it. A voice
  turn is made of many events, so the Svix id of one part is the wrong value: a retry of
  that part after the flush opens a new buffer and would make a second turn. One buffer
  row becomes one turn, and the claim gives a row one time.
- **Two constants for the consent notice, and a dict keyed by the mode.** Sam selected
  it. `CONSENT_NOTICE` did not change one character and `CONSENT_NOTICE_VOICE` ends
  "Please answer out loud." `CONSENT_NOTICES` sits next to `MODES`, so the route has no
  test of the mode in it.
- **`gpt-4o-mini-tts`, voice `alloy`, `response_format` `mp3`.** Sam selected it. It is
  the one model of the three that takes an `instructions` text, which gives the tone:
  "Speak in a calm, clear and unhurried voice." `tts-1` has a lower delay and no
  instructions, and `tts-1-hd` costs more than a meeting call can carry.
- **A voice session starts with curl for now.** Sam selected it. The page sends the mode
  `chat` as a constant, and this session must not touch `frontend/`. The mode control on
  the page is the new section 7a of `../TASKS.md`.
- **A chat message in a voice session is not a turn.** Sam selected it. One session has
  one mode. The cost is that a patient who types in a voice call gets no answer, and the
  container log is the one place that says so.

These decisions are mine. Sam was asleep.

- **The gap wake-up is an event, `VoiceTurnGap`.** `handle_incoming_turn` gives `None`
  for each `transcript.data` part and gives the whole answer for a gap. The protocol
  thus keeps one entry point, and `engine/loop.py` keeps its one caller: the route. The
  other shape, a second method on the mode, puts the flush outside the protocol.
- **`VoiceTurnGap` carries the `event_id` back to the route.** The protocol gives
  `str | None`, and the route needs the id of the buffer that flushed. The mode writes
  `gap.event_id`, and the route reads it. The gap object is voice-specific and the route
  makes it in the voice path only.
- **The route arms the wake-up, and only if a buffer is open.** A chat session receives
  `transcript.data` as well, because one `realtime_endpoints` list carries both events.
  `open_voice_buffer` gives `None` for a chat session, for the bot's own speech and for
  an empty utterance, so no thread starts for any of them. This is one cheap read, and
  it needs no mode name in the route.
- **A wake-up is never cancelled.** Three parts arm three wake-ups. The first two find
  `last_part_at` newer than `now - gap` and claim nothing. Cancellation needs a
  reference to a timer, which is state in the process, and the condition in the UPDATE
  gives the same result with no state.
- **`_is_the_bot` is written a second time in `voice.py`.** `app/modes/chat.py` must not
  change, so the function cannot move to `base.py`, and an import of a private name from
  `chat.py` would make voice mode depend on chat mode. Four lines are cheaper than that
  coupling. **The echo filter matters more here than in chat:** the live call of session
  09 showed that Google Meet does not send a chat event for the bot's own message, but
  the bot plays its audio into the meeting and Recall transcribes the meeting.
- **`_mode_of(session)` replaced three copies of the `get_mode` guard** in
  `routes/webhooks.py`. `_start_chat_intake` is `_start_intake` now, because the notice
  is no longer chat-specific. Chat behavior did not change, and the chat tests prove it.
- **`_now()` gives microseconds, and there is no second time function.** The voice
  buffer measures a silence of a few seconds and compares `last_part_at` in SQL, which
  a time to the second cannot do. The first version of this added `_now_precise()` next
  to `_now()`; **Sam refused it in the review and he was correct.** Nothing stops `_now`
  from widening: `created_at` and `updated_at` are written and never parsed or compared,
  no route gives them out, and `last_event_at`, which **is** compared, never came from
  `_now` — it comes from `_event_time` in `app/recall/events.py`, which has used
  microseconds since session 06. Two functions that differ only in precision are two
  functions that a later session must choose between, and it will sometimes choose the
  wrong one. The change also repairs a test that could not fail:
  `test_the_same_event_two_times_changes_the_session_one_time` compares `updated_at`
  before and after a repeated event, and at a precision of one second the two writes
  gave the same text, so the test passed with the guard of `apply_bot_event` removed.
- **The silent mp3 is a constant in the source, not a file.** It is 288 bytes and 384
  base64 characters. A file needs a path in the image, a read at start, and a failure
  path for a file that is absent.
- **No split for a long question.** The 500 character limit is a Google Meet chat rule.
  A long text makes a long audio clip and nothing refuses it.
- **`VOICE_TURN_GAP_SECONDS` is 2.5.** `SPEC.md` gives 2 to 3. It is a setting, so a
  live call tunes it with no code change.
- **No wait between the spoken notice and the first question, and this is a risk.**
  In chat mode the two messages go out about 2 seconds apart and Google Meet shows
  both. In voice mode they are **two audio clips**, and the notice is about 15 seconds
  of speech. Recall does not say what the output audio endpoint does with a second clip
  that arrives while the first one plays: it can queue it, or it can cut the first one.
  If it cuts, **the patient hears a consent disclaimer that stops in the middle**. I did
  not add a wait, because the mechanism is a guess until a call shows it, and an
  untested sleep on the join path is complexity that `../../CLAUDE.md` pushes back on.
  **This is the first item to watch in the live call**, and the remedy is one constant.
  See the procedure below.
- **There is no terminal driver for voice mode.** One was written in this session, in
  the shape of `intake_console.py`, and Sam removed it in review. He was correct: what
  it uniquely covered was the timing of the wake-up, which is plumbing and belongs in
  the suite, and everything else in it repeated `intake_console.py`, because the engine,
  the prompts and the summary are mode-neutral. A later session must not add it back.
  The turn-taking is proved by the tests and by the container check below.

## Verified facts

- **The 348 tests pass.** Method: `poetry run pytest -q` in `backend/`. Session 10 left
  265. The new files are `test_tts_openai.py` (16) and `test_modes_voice.py` (28), and
  `test_routes_webhooks.py` went from 71 to 87.
- **No test uses the network.** Method: the plugin of lesson 3 in the scratchpad, then
  `PYTHONPATH=<scratchpad> poetry run pytest -q -p block_network`. **The result is 348
  passed.** The voice fakes went into the `offline` fixture of
  `tests/test_routes_webhooks.py` **before** the route called them, which is the fault
  that lesson 3 records from session 09.
- **The forbidden files did not change.** Method:
  `git diff --stat -- backend/app/engine/ backend/app/modes/chat.py frontend/` gives no
  line.
- **The `transcript.data` payload shape is confirmed, not guessed.** Method: the
  `recall-ai` MCP. `get_doc` for `real-time-event-payloads` renders the payload from a
  component and gives no field names, so `get_doc` for `agent-quickstarts` gave the same
  schema as text. The words are at `data.data.words[]`, each with `text`,
  `start_timestamp.relative` and `end_timestamp.relative`, and the speaker is at
  `data.data.participant.name`. **There is no sentence field and no absolute time.**
- **The output audio endpoint needs `automatic_audio_output`.** Method: `get_doc` for
  `output-audio-in-meetings`. Recall says to put a short silent mp3 in that
  configuration if you do not want automatic audio.
- **The silent mp3 is valid.** Method:
  `ffmpeg -f lavfi -i anullsrc=r=8000:cl=mono -t 0.1 -c:a libmp3lame -b:a 8k -write_xing 0 -id3v2_version 0`,
  then `ffprobe` gives `format_name=mp3, duration=0.288`. A test decodes the constant and
  reads the 11 frame-sync bits.
- **SQLite takes an upsert on a partial unique index, with RETURNING.** Method: a probe
  before the plan. This machine has 3.53.2 and **the container has 3.46.1**, and
  migration 6 ran in the container. Upsert needs 3.24 and RETURNING needs 3.35.
- **The new tests are load-bearing.** Method: break the behavior, run the suite, restore.
  Ten breaks, ten failures:

  | The break | The tests that failed |
  |---|---|
  | The echo filter of voice mode | `test_the_bot_does_not_hear_itself` |
  | The buffer: one utterance becomes one turn | **15 tests**, in `test_modes_voice.py` and `test_routes_webhooks.py` |
  | The silence condition of the claim | `test_a_gap_that_is_too_early_gives_nothing` |
  | The claim closes the buffer one time | **4 tests**, including `test_two_claims_at_the_same_time_give_one_turn` |
  | The `event_id` of a voice turn | `test_the_event_id_of_a_voice_turn_is_the_buffer_id` |
  | `automatic_audio_output` on a voice bot | `test_a_voice_body_carries_the_automatic_audio_output` |
  | The voice consent notice | `test_the_voice_notice_is_spoken_and_not_pinned` |
  | The open-buffer guard of the route | `test_the_bot_does_not_answer_itself`, `test_a_transcript_in_a_chat_session_arms_nothing` |
  | The mp3 format of the TTS call | `test_the_request_has_the_model_the_voice_and_the_format` |
  | The audio send after the TTS call | `test_send_outgoing_turn_speaks_and_plays` |

- **A signed `transcript.data` against the container makes one turn from three
  utterances.** Method: a script in the container, the method of session 09. It made a
  voice session with a bot id that Recall does not know, then posted three signed
  utterances to `http://localhost:8000/webhooks/recall`. Each one gave HTTP 200
  `{"ok":true}`. The buffer went `(1, 'I get')` → `(1, 'I get bad headaches')`, and after
  the gap the turns table held **one** patient row:
  `voice-1 | I get bad headaches most mornings`. The container log then gives, in order:

  ```
  app.modes.voice: session ... ended a turn, buffer 1
  httpx2: POST https://api.openai.com/v1/chat/completions "HTTP/1.1 200 OK"
  app.engine.llm: model gpt-4o-mini answered for intake_turn
  httpx2: POST https://api.openai.com/v1/audio/speech "HTTP/1.1 200 OK"
  app.tts.openai_tts: tts gpt-4o-mini-tts made 86400 bytes for 81 characters
  httpx: POST https://us-west-2.recall.ai/api/v1/bot/bot-voice-check-.../output_audio/ "HTTP/1.1 404 Not Found"
  app.engine.loop: session ... failed: recall http 404: {"detail":"Not found."}
  ```

  **This proves six things in one run:** the signature and the parse operate on the
  server, three utterances make one turn, the silence timer fires in the container, the
  real model answers, **the real OpenAI TTS call gives real mp3 bytes with
  `gpt-4o-mini-tts` and the `instructions` parameter**, and a failed audio send is not
  silent. The HTTP 404 is the expected end: that bot id is invented.
- **The container builds and becomes healthy.** Method:
  `docker compose -f deploy/docker-compose.yml up -d --build` in `backend/`, then
  `docker inspect --format '{{.State.Health.Status}}' recall-api`. The result is
  `Up 8 seconds (healthy)`.
- **The code that runs in the container is the new code.** Method:
  `docker exec -w /app -e PYTHONPATH=/app recall-api python -c ...`. It gives
  `modes: ['chat', 'voice']`, the two notice texts, `send_output_audio: True`,
  `tts.speak: True`, `migrations: 6`, `voice body has audio: True` and
  `chat body has audio: False`. This reads the code that **runs**, which is the check
  that session 10 added after a deploy that did not rebuild.
- **The bot already subscribes to the transcript.** Method: read `_recording_config()`
  and `tests/test_recall_client.py::test_body_has_the_v111_shape`. It sets
  `transcript.provider.recallai_streaming` with `mode: prioritize_low_latency` and
  `language_code: en`, and `realtime_endpoints` lists `transcript.data` next to
  `participant_events.chat_message`. **This was built in section 2 and it was not built
  again.**

## Corrections

- **Wrong:** a table with no timer, flushed by the next event after the gap, is a
  simpler option of the same class. **Correct:** it deadlocks. The last utterance of an
  answer never flushes, because the patient then waits for the bot and nothing else
  arrives. The bot would answer one turn late, and a patient who stops talking would
  wait for ever. The cost belongs with the option, and the question to Sam said so.
- **Wrong:** `handle_incoming_turn` can give the text of a transcript utterance and let
  the route decide. **Correct:** an utterance often arrives word by word, so the mode
  must give `None` for each one. A test proves it: make the mode give the text, and 15
  tests fail.
- **Wrong:** the route can arm a wake-up for each `transcript.data`. **Correct:** a chat
  session receives those events as well, and the bot hears itself. The route reads
  `open_voice_buffer` first, so a thread starts only for a real part.
- **Wrong:** `docker exec recall-api python /tmp/check.py` finds the `app` package.
  **Correct:** the working directory of `docker exec` is not `/app` for a copied script,
  and `PYTHONPATH` is not set. The check needs
  `docker exec -w /app -e PYTHONPATH=/app`.
- **Wrong:** voice mode needs its own terminal driver, in the shape of
  `intake_console.py`. **Correct:** it does not, and the one written in this session was
  removed in review. Sam named the reason: it proved plumbing, and plumbing is a unit
  test. The engine, the prompts and the summary are mode-neutral, so `intake_console.py`
  already covers everything in it except the timing of the wake-up.
- **Wrong (a document, not the code):** the `turns` table in `../FLOW.md` part 2 had its
  `created_at` row below the paragraph that follows the table. Repaired in this session.
- **Wrong:** the voice buffer needs a second time function, `_now_precise()`, because
  `_now()` gives seconds. **Correct:** `_now()` widens to microseconds and
  `_now_precise` does not exist. Sam found this in the review. Nothing depended on the
  narrower format, and the two functions would have been a choice for each later session
  to make and to get wrong. See the decision above for the full reason.

## Open items

- [ ] **The live Google Meet call in voice mode.** Owner: Sam. The procedure is below.
- [ ] Deploy to the homelab server. Owner: Sam. The image needs a rebuild, not a
      restart. The check is
      `docker exec -w /app -e PYTHONPATH=/app recall-api python -c "from app.modes.base import MODES; print(sorted(MODES))"`.
- [ ] Commit this session. The working tree holds the code, the plan and the documents.
      Owner: Sam. **This session made no commit and no push.**
- [ ] **Section 7a: the mode control on the page.** Owner: a later session.
- [ ] **Section 8a is still the most urgent item.** The voice console run stopped after
      4 questions of 6, and `triggers`, `prior_treatments` and `notes` came back
      `not discussed`. The first question also introduced the assistant a second time,
      after the spoken notice already did. This is the fifth run that shows both faults.
- [ ] **Is the `webhook-id` of a real-time retry the same each time?** Still open for
      chat mode. **Voice mode does not depend on the answer**, because a voice turn uses
      the buffer rowid and not the Svix id.
- [ ] Is 2.5 seconds the correct gap? Only a live call answers this. See the procedure.
- [ ] The weak points of [`../FLOW.md`](../FLOW.md) part 9 go in the README as
      limitations. Owner: the docs pass of section 9. Items 7 to 10 are new.
- [ ] Starlette says that `httpx` with `TestClient` is deprecated. 348 tests pass with
      the warning only. Owner: the next session that touches the tests.
- [ ] The local development container holds a junk session from the check above. It is
      not the homelab database. Owner: nobody, unless a clean database matters.

## Next session starts here

**The live Google Meet call in voice mode. Sam runs it.** Nothing else in section 6 is
open. Do this before section 7a and before section 8a.

### Before the call

1. **Deploy the new code and prove that it runs.** A restart is not sufficient: the
   image must be rebuilt. This is the fault that session 10 found.

   ```bash
   cd backend
   docker compose -f deploy/docker-compose.yml up -d --build
   docker inspect --format '{{.State.Health.Status}}' recall-api
   docker exec -w /app -e PYTHONPATH=/app recall-api python -c \
     "from app.modes.base import MODES; from app.recall import client; \
      print(sorted(MODES), hasattr(client, 'send_output_audio'))"
   ```

   The last line must give `['chat', 'voice'] True`. If it gives `['chat'] False`, the
   container runs the old image.

2. **Open a Google Meet call** and keep the tab open. Turn your microphone on.
   The pin is not used in voice mode, so continuous chat does not matter this time.

3. **Watch the container log in a second terminal:**

   ```bash
   docker logs -f recall-api
   ```

### Start the session

The page sends the mode `chat` as a constant, so a voice session needs curl:

```bash
curl -sS -X POST https://recall-api.ss-ubuntu-01.net/sessions \
  -H 'content-type: application/json' \
  -d '{"meeting_url": "https://meet.google.com/xxx-xxxx-xxx", "mode": "voice"}'
```

It gives `{"session_id": "...", "status": "waiting_for_bot"}`. **Keep the session id.**
A status of `error` means that Recall refused the bot; read the reason with
`curl -sS https://recall-api.ss-ubuntu-01.net/sessions/<session_id>`.

### In the call

1. **Admit the bot.** Google Meet asks.
2. **Listen.** The bot must **speak** the consent notice, and it must end with "Please
   answer out loud". It must not write in the chat.
3. **The bot then speaks its first question.**
4. **Answer out loud, in parts, with short pauses.** For example: "I get" … "really bad
   headaches" … "about twice a week". **Then stop and wait.** The bot must answer about
   3 to 5 seconds after your last word: 1 to 3 seconds for the transcript, plus the 2.5
   second silence, plus the TTS call.
5. Answer each question the same way, to the end of the intake.
6. **At the end** the bot must speak the closing line and then leave the call by itself.

### What proves that voice mode operates

| What to watch | The result that passes |
|---|---|
| **The consent notice, to its end** | It is **spoken complete**, and it ends "Please answer out loud". **It must not stop in the middle.** See the risk below |
| The consent notice | Spoken, and not written in the chat |
| An answer in three parts | **One** question comes back, not three |
| The delay | The bot answers 3 to 5 seconds after your last word |
| The container log | `app.modes.voice: session ... ended a turn, buffer N` one time for each answer |
| The container log | `app.tts.openai_tts: tts gpt-4o-mini-tts made N bytes` for each question |
| The bot logs at Recall | `POST /api/v1/bot/{id}/output_audio/ -> 200` for each question |
| The end | The closing line is spoken, then the bot leaves |
| `GET /sessions/{id}` | `complete`, with the eight fields |
| The turns table | The rows alternate, and each patient row holds the **whole** answer |

### If something is wrong

- **The consent notice stops in the middle, and the first question starts.** This is the
  one fault that I could not test without a call. The notice and the first question are
  two audio clips that go out about 2 seconds apart, and the notice is about 15 seconds
  of speech. Recall does not say if the output audio endpoint queues a second clip or
  cuts the first one. **The remedy is a short wait between them.** Add a setting next to
  `BOT_LEAVE_DELAY_SECONDS`, for example `NOTICE_AUDIO_SECONDS`, and make
  `_start_intake` in `app/routes/webhooks.py` wait that time after `send_notice` and
  before `loop.start_intake`. The handler runs after the answer to Recall, so the wait
  costs nothing in the request; this is the same shape as `_leave_call`. A better answer
  is to wait for the length of the clip, which the mp3 gives. **Do not make this change
  before the call shows the fault.**
- **The bot says nothing at all, and the log gives `recall http 400`.** The create-bot
  body had no `automatic_audio_output`. Check the body:
  `docker exec -w /app -e PYTHONPATH=/app recall-api python -c "from app.recall import client; print('automatic_audio_output' in client.build_request_body('u','s','voice'))"`.
- **The bot cuts you off in the middle of an answer.** The gap is too short. Raise
  `VOICE_TURN_GAP_SECONDS` in `backend/.env` to 3.5 and restart. This is the value that
  no test can tune.
- **The bot answers its own question.** The echo filter did not hold. Look in the log
  for `session ... heard itself, no part`. If that line is absent and a bot question is
  in the turns table as a patient row, the speaker name of the bot in the transcript is
  not `RECALL_BOT_NAME`. Read the true name with
  `get_bot_logs` and compare.
- **The bot never answers.** Look for `ended a turn, buffer N` in the log. If it is
  absent, no `transcript.data` arrived: check `get_bot_logs` for a transcript failure,
  and the dashboard webhook for a `transcript.failed` event.
- **The bot answers one turn late.** That is the wake-up that the container lost. See
  `../FLOW.md` part 9, item 10.

**Write what the call showed in this log, under a new part.** The questions that are
open and that only a call answers:

1. **Does the output audio endpoint queue a second clip, or cut the first one?** This
   decides whether the notice needs a wait before the first question.
2. **Is 2.5 seconds the correct silence gap?** Too short cuts an answer in two, and too
   long makes the bot slow.
3. **Does the bot hear itself in the transcript?** Chat mode did not need its echo
   filter in the live call of session 09. Voice mode probably does, because the bot
   plays audio into the meeting that Recall transcribes.
4. **What is the true delay** from the last word of the patient to the first sound of
   the bot?
