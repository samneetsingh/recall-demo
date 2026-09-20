# Task 6 — Voice mode: todo

Written in ASD-STE100 Simplified Technical English.

## Scope

Section 6 of [`../TASKS.md`](../TASKS.md). The assistant speaks its questions into the
Google Meet call and listens to the real-time transcript. Voice mode is a **second**
implementation of the turn boundary, next to `app/modes/chat.py`.

**`backend/` only.** The frontend does not change. **Chat mode does not change**, and
the four engine modules do not change.

## Answers from Sam

| Question | Answer |
|---|---|
| Where the turn-taking state lives | **A new table and a debounce timer.** The parts and the time of the last part are in SQLite. Each `transcript.data` schedules a wake-up at now + N seconds, and the flush is one conditional UPDATE |
| The `event_id` of a voice turn | **The buffer rowid.** `voice-<id of the buffer row that flushed>` |
| The consent notice for voice | **Two constants and a dict** keyed by the mode, next to `MODES`. The chat text does not change one character |
| The TTS model and voice | **`gpt-4o-mini-tts`, voice `alloy`, `response_format` `mp3`**, with an `instructions` string for a calm tone |
| Can a voice session be started | **Curl for now.** Add "7a. The mode control on the page" to `../TASKS.md` for a later session |
| A chat message in a voice session | **Ignore it.** One session has one mode |

## Verified before the plan

Method: the `recall-ai` MCP against the live documents, and a probe of SQLite.

- **The `transcript.data` payload.** `get_doc` for `agent-quickstarts`, which renders the
  schema that the `real-time-event-payloads` page holds in a component:

  ```
  data.data.words[]           {text, start_timestamp:{relative}, end_timestamp:{relative}|null}
  data.data.language_code
  data.data.participant       {id, name, is_host, platform, extra_data, email}
  data.transcript.id  data.recording.id  data.bot.id
  ```

  **The text is at `data.data.words[].text`, and the speaker is at
  `data.data.participant.name`.** There is no sentence field: the words must be joined.
  A `transcript.data` event is one **finalized utterance**, not one turn.
- **The output audio endpoint.** `get_doc` for `output-audio-in-meetings`.
  `POST /api/v1/bot/{id}/output_audio/` with `{"kind": "mp3", "b64_data": "<base64>"}`.
  `kind` takes `mp3` only. **The endpoint operates only if the bot was made with an
  `automatic_audio_output` configuration.** Recall says to put a short silent mp3 there.
- **Output Media is the other method, and this build does not use it.** It streams a web
  page into the call, it always sends video, and it is mutually exclusive with
  `automatic_audio_output` and the output audio endpoint.
- **Recall says not to use the real-time transcript for a conversational agent**, and to
  use output media with a voice-to-voice model. `../SPEC.md` scopes this build to half
  duplex with a pause as the turn signal. Keep the `SPEC.md` approach, and write the
  trade-off in the README limitations.
- **The bot already subscribes to the transcript.** `_recording_config()` in
  `app/recall/client.py` sets `transcript.provider.recallai_streaming` with
  `mode: prioritize_low_latency` and `language_code: en`, and `realtime_endpoints`
  already lists `transcript.data`. The TASKS.md item is **already true**.
- **Webhook delivery is serial.** A slow handler delays each later event. The route
  answers HTTP 200 first and works in a `BackgroundTask`. **No blocking sleep goes on
  the transcript path.**
- **`transcript.failed` arrives at the dashboard endpoint**, not at the real-time
  endpoint. Do not put it in `realtime_endpoints`.
- **SQLite takes an upsert on a partial unique index, with RETURNING.** Method: a probe
  with `poetry run python`. `sqlite3.sqlite_version` is 3.53.2 on this machine. Upsert
  needs 3.24 and RETURNING needs 3.35, so the container image is new enough.
- **A silent mp3 of 288 bytes is sufficient.** Method:
  `ffmpeg -f lavfi -i anullsrc=r=8000:cl=mono -t 0.1 -c:a libmp3lame -b:a 8k -write_xing 0 -id3v2_version 0`,
  then `ffprobe` gives `format_name=mp3`. Base64 gives 384 characters, so the value is a
  constant in the source and not a file.

## New dependencies

**None.** The `openai` SDK (3.16.2) has `client.audio.speech.create`, `httpx` sends the
Recall request, and `base64` and `threading` are in the standard library.

## Decisions

- **The state is in SQLite and the timer is only a wake-up.** The `voice_buffers` table
  holds the words and the time of the last part. A `threading.Timer` wakes at
  `VOICE_TURN_GAP_SECONDS`, and the flush is one conditional UPDATE
  (`flushed_at IS NULL AND last_part_at <= now - gap`). A restart of the container loses
  the wake-up and not the words. **Two wake-ups cannot make two turns**, because the
  UPDATE gives one row one time. This is the rule of `apply_bot_event`, applied again.
- **A wake-up is not cancelled.** An earlier wake-up that fires after a newer part
  arrived finds `last_part_at` too new and claims nothing. No timer holds a reference to
  another timer, and no code cancels one.
- **The gap wake-up is an event.** `handle_incoming_turn` gives `None` for each
  `transcript.data` part and gives the **full answer** for a `VoiceTurnGap` object. The
  protocol thus keeps one entry point, and `engine/loop.py` keeps its one caller: the
  route.
- **`VoiceTurnGap` carries the `event_id` back.** The protocol gives `str | None`, and
  the route needs the id of the buffer that flushed. The mode writes
  `voice-<buffer id>` on the gap object, and the route reads it. The gap object is
  voice-specific and the route makes it in the voice path only.
- **The route arms the wake-up, and only if a buffer is open.** A chat session also
  receives `transcript.data`, because one `realtime_endpoints` list carries both events.
  `open_voice_buffer` gives `None` for a chat session, for the bot's own speech and for
  an empty utterance, so no thread starts for any of them.
- **The echo filter is necessary for voice, and it was not for chat.** The bot plays its
  own audio into the meeting, so Recall can transcribe it back. A `transcript.data`
  whose `participant.name` is `RECALL_BOT_NAME` is not a patient turn.
- **`_is_the_bot` is written a second time in `voice.py`.** `app/modes/chat.py` must not
  change, so the function cannot move to `base.py`. An import of a private name from
  `chat.py` would make voice mode depend on chat mode, which is the one thing the
  boundary prevents. Four lines are cheaper than that coupling.
- **A `TTSError` becomes a `ModeError`.** `engine/loop.py` catches `ModeError` and puts
  the session in `error`. This is the rule that session 09 made for `RecallError`.
- **No split for a long question.** The 500 character limit is a Google Meet chat rule.
  A long text makes a long audio clip and nothing refuses it.
- **No wait between the spoken notice and the first question.** They are two audio
  clips, and Recall does not say what the endpoint does with a second clip that arrives
  while the first one plays. An untested sleep on the join path is a guess. This is the
  first item of the live call procedure, and the remedy is one constant.
- **`automatic_audio_output` goes in the body of a voice bot only.** The chat body does
  not change, and a test holds that rule.

## Files

```
backend/
  app/
    config.py                   edit  OPENAI_TTS_*, VOICE_TURN_GAP_SECONDS
    tts/__init__.py             new
    tts/openai_tts.py           new   speak(text) -> mp3 bytes
    db/models.py                edit  Migration 6: the voice_buffers table
    db/session_store.py         edit  add_voice_part, claim_voice_buffer, open_voice_buffer
    recall/client.py            edit  send_output_audio, the mode in the body, SILENT_MP3_B64
    modes/voice.py              new   VoiceMode, VoiceTurnGap, utterance_text
    modes/base.py               edit  The voice entry in MODES, CONSENT_NOTICES
    routes/webhooks.py          edit  _run_voice_turn, flush_voice_turn, _arm_voice_flush, _mode_of
  tests/
    conftest.py                 edit  transcript_payload
    test_tts_openai.py          new
    test_modes_voice.py         new
    test_session_store.py       edit  The buffer
    test_db_migrations.py       edit  The new table
    test_recall_client.py       edit  send_output_audio, the voice body
    test_routes_webhooks.py     edit  The voice fakes in `offline` FIRST, then the wire
    test_engine_loop.py         edit  "no implementation" needs a mode that has none
  README.md                     edit  One limitation: Recall says not to do this
docs/
  TASKS.md                      edit  Section 6, and the new section 7a
  FLOW.md                       edit  The header, part 2, flow D, part 9
  API_CONTRACT.md               edit  The two Mode 2 sections
  API_REFERENCE.md              edit  A voice session, and the transcript events
  task-06-voice-mode/todo.md    new   This file
  session-logs/11-voice-mode.md new
```

**`app/engine/intake.py`, `summary.py`, `prompts.py` and `loop.py` get no change.**
**`app/modes/chat.py` gets no change.** `frontend/` gets no change.

## Procedure — the TTS module

- [x] `app/tts/__init__.py` and `app/tts/openai_tts.py`.
- [x] `TTSError`, its own class. It is the one failure that this module gives.
- [x] `speak(text: str) -> bytes`. It is the only function, and this module is the only
      one that knows about TTS, as `app/engine/llm.py` is the only one that makes the
      OpenAI client for the engine.
- [x] No API key raises before a request.
- [x] `response_format="mp3"` is explicit. The default is mp3 and a default can change.
- [x] `instructions` goes in only if `OPENAI_TTS_INSTRUCTIONS` is not empty. `tts-1` and
      `tts-1-hd` refuse that parameter.
- [x] An `openai.OpenAIError` becomes a `TTSError`, and the text holds no API key.
- [x] An empty answer raises. Silence in the meeting looks like a hang to the patient.

## Procedure — the Recall call

- [x] `send_output_audio(bot_id: str, audio: bytes) -> None` in `app/recall/client.py`,
      through the shared `_post`.
- [x] The body is `{"kind": "mp3", "b64_data": base64.b64encode(audio).decode("ascii")}`.
- [x] A log line with the byte count. The base64 text never goes in the log.
- [x] `SILENT_MP3_B64`: 384 characters, with a comment that says what makes it necessary.
- [x] `build_request_body(meeting_url, session_id, mode="chat")` takes the mode, and
      `create_bot` gives it. A voice body has `automatic_audio_output.in_call_recording`
      with the silent mp3 and no `replay_on_participant_join`.
- [x] The chat body does not change. A test holds that rule.

## Procedure — the table

- [x] Migration 6 in `app/db/models.py`. It makes `voice_buffers` and one **partial
      unique index**, `voice_buffers(session_id) WHERE flushed_at IS NULL`. The index is
      what makes one open buffer for one session.
- [x] `add_voice_part(session_id, text) -> int | None`. One statement: an INSERT with
      `ON CONFLICT(session_id) WHERE flushed_at IS NULL DO UPDATE`, which appends the
      words, moves `last_part_at`, and gives the row id with `RETURNING`.
- [x] `claim_voice_buffer(session_id, not_after) -> tuple[int, str] | None`. One
      statement: `UPDATE ... SET flushed_at = ? WHERE flushed_at IS NULL AND
      last_part_at <= ? RETURNING id, text`. The second call gives `None`.
- [x] `open_voice_buffer(session_id) -> tuple[int, str] | None`, a read. The route uses
      it to decide if a wake-up is necessary.
- [x] The times use microseconds. **`_now()` widens; there is no second time
      function.** A time to the second cannot see a gap of 2.5 seconds, and nothing
      depended on the narrower format: `created_at` and `updated_at` are written and
      never compared, and `last_event_at` never came from `_now()`.

## Procedure — the mode

- [x] `app/modes/voice.py`: `TRANSCRIPT_EVENT`, `VoiceTurnGap`, `utterance_text`,
      `VoiceMode`.
- [x] `utterance_text(payload)` joins `data.data.words[].text` with one space and
      normalizes the spaces. A shape that it does not know gives an empty text.
- [x] `handle_incoming_turn`:
  - a `VoiceTurnGap` claims the buffer and gives the whole answer, or `None`;
  - a `transcript.data` from a person adds a part and gives `None`;
  - the bot's own speech, an empty utterance, a chat message, and a shape that it does
    not know each give `None` and never an exception.
- [x] `send_outgoing_turn`: TTS, then the output audio.
- [x] `send_notice`: the same path. The notice is spoken, not pinned.
- [x] A session with no `bot_id`, an empty text, a `TTSError` and a `RecallError` each
      give a `ModeError`.
- [x] `app/modes/base.py`: `MODES["voice"] = VoiceMode()`, `CONSENT_NOTICE_VOICE`, and
      `CONSENT_NOTICES: dict[Mode, str]`.

## Procedure — the wire

- [x] `routes/webhooks.py` sends `transcript.data` to `_run_voice_turn`, which today
      writes a log line and returns.
- [x] `_mode_of(session)` holds the `get_mode` guard one time. `_start_chat_intake`,
      `_run_chat_turn`, `_run_voice_turn` and `flush_voice_turn` each use it.
- [x] `_run_voice_turn(event)`: the mode buffers the utterance, then the route arms a
      wake-up **if a buffer is open**.
- [x] `_arm_voice_flush(session_id)`: a `threading.Timer` with `daemon=True`. **It does
      not block the webhook path.**
- [x] `flush_voice_turn(session_id)` is public, because the tests call it directly and
      the wake-up thread calls it by name: it makes the `VoiceTurnGap`, gets the text, calls
      `loop.run_turn(session_id, text, gap.event_id)`, and then `_finish_intake` if the
      session was not complete before the turn. This is the shape of `_run_chat_turn`.
- [x] `_start_chat_intake` gives the notice of the mode: `CONSENT_NOTICES[session.mode]`.

## Procedure — the tests

The tests use no network. Each Recall call is an `httpx.MockTransport`, each TTS call is
a fake, and each model call is a patched `ask_model`.

- [x] **The voice fakes go in the `offline` fixture of `tests/test_routes_webhooks.py`
      BEFORE the route calls them.** That fixture is the reason the suite stays offline.
      This is lesson 3 of `../../tasks/lessons.md`.
- [x] `tests/test_tts_openai.py`: the model, the voice, the format, the instructions, the
      bytes, no key, an `OpenAIError`, the redaction, an empty answer.
- [x] `tests/test_modes_voice.py`: the parse, the echo filter, the buffer, the gap, a
      repeated gap, the two sends, and each failure that becomes a `ModeError`.
- [x] `tests/test_session_store.py`: one open buffer, the append, the claim, a claim with
      a newer part, a second claim, and two threads that claim at the same time.
- [x] `tests/test_recall_client.py`: `send_output_audio`, the voice body, the chat body.
- [x] `tests/test_routes_webhooks.py`: a transcript part makes no turn; three parts and a
      gap make one turn with the whole answer; the `event_id` is `voice-<id>`; a gap with
      a newer part makes no turn; a second gap makes no second turn; the question is
      spoken; the closing line is spoken and the bot leaves; a chat message in a voice
      session makes no turn.
- [x] `tests/test_engine_loop.py`: `voice` has an implementation now, so
      `test_a_mode_with_no_implementation_puts_the_session_in_error` takes the entry out
      of the registry with `monkeypatch.delitem`.
- [x] `tests/test_db_migrations.py`: the new table is in a new file and in an old file.

## Procedure — the proof

- [x] The full suite passes.
- [x] **No test uses the network.** The plugin of lesson 3, then
      `poetry run pytest -q -p block_network`. The count goes in the session log.
- [x] **The new tests are load-bearing.** Break each new behavior on purpose, run the
      suite, and record which tests failed.
- [x] **The turn-taking is proved with no Recall and no network.** The tests do it:
      three utterances and a wake-up give one turn that holds the whole answer. A
      terminal driver for voice is **not** the way to prove this, and one written in
      this session was removed in review. Its only unique coverage was the timing of the
      wake-up, which belongs in the suite, and the rest of it repeated
      `intake_console.py`, because the engine and the prompts are mode-neutral.
- [x] **A signed `transcript.data` event against the container gives HTTP 200 and the
      expected turn.** The method of session 09 and session 10.
- [x] The container builds and becomes healthy.
- [x] `git diff --stat -- backend/app/engine/ backend/app/modes/chat.py frontend/` gives
      no line.
- [ ] **A live Google Meet call.** Sam runs it. The procedure is at the end of
      `../session-logs/11-voice-mode.md`.

## Out of scope

- **Output Media, a voice-to-voice model, interruption handling, crosstalk handling and
  full duplex.** `../SPEC.md` puts each one out of scope.
- **`transcript.partial_data`.** `transcript.data` is sufficient for a pause signal.
- **Prompt tuning.** That is section 8a.
- **A change to `frontend/`**, to chat mode or to the four engine modules.
- **A commit or a push.**

## At the end

- [x] Check the completed boxes in this file.
- [x] Mark the items of section 6 of `../TASKS.md` that pass. The live call stays open.
- [x] `../FLOW.md`: the header, part 2, flow D, and part 9.
- [x] `../API_CONTRACT.md`: the two Mode 2 sections that say "confirm which one this
      build uses once implemented".
- [x] `../API_REFERENCE.md`: a voice session, and the transcript events at the route.
- [x] `../session-logs/11-voice-mode.md`, with the live call procedure at the end.
