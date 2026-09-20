# Task 3 — The mock intake engine: todo

Written in ASD-STE100 Simplified Technical English.

## Scope

Section 3 of [`../TASKS.md`](../TASKS.md), the mock intake engine, and section 4, the
mode boundary. Sam put the two sections in one session, which agrees with step 2 of the
build order in `CLAUDE.md`.

The engine takes the conversation log and gives the next question, or a signal that the
intake is complete. A second prompt then makes the eight fields of
[`../SPEC.md`](../SPEC.md) from the same log. The engine takes plain text in and gives
plain text out. It must never know if a turn came from chat or from a transcript.

This task makes no Recall call and no webhook. Section 5 adds the chat implementation.

## Answers from Sam

- **The `openai` SDK, not LiteLLM and not plain `httpx`.** LiteLLM is in the stack list
  in `CLAUDE.md`, but the workspace has no `ANTHROPIC_API_KEY`, so a provider change has
  no use in this build. `CLAUDE.md` and the README must get this correction.
- **The model is `gpt-4o-mini`.** The value is `OPENAI_MODEL` in `config.py`, so a demo
  can change it in `.env` with no code change.
- **Build the engine and the mode boundary.** Section 3 and section 4, not section 5.
- **The intake uses an action envelope, and the LLM branches.** Sam gave the prompt
  framework of a synthetic test suite that he made. The model answers with one JSON
  object: an action to ask, or a terminal action. The framework stays. See the changes
  below.
- **The limit is 6 questions.** A short demo. The value is `INTAKE_MAX_TURNS` in
  `config.py`.
- **The summary has the eight fields of `SPEC.md` only.** No diagnosis and no ranked
  candidates. The summary uses a different prompt from the intake.

### The changes to the framework of Sam

1. **The terminal action is `complete`, not `diagnose`.** `SPEC.md` makes this bot a
   pre-visit intake assistant and not a physician, and the summary shape in `SPEC.md`
   has no diagnosis. The model thus gives `{"action": "complete"}` and no more.
2. **The summary is a second call with a different prompt.** `SPEC.md` says this. It
   also keeps `summary.py` usable alone: a call that stops early can still give a
   summary of the part of the intake that is complete.
3. **The engine counts the turns, the model does not.** A model goes past a limit that a
   prompt gives it. The engine counts the bot turns in the log, and at the limit it
   gives the terminal result and makes **no** LLM call. The `turn` field stays in the
   schema because it helps the model, but no code reads it. This is also what makes the
   test deterministic.
4. **The JSON schema is strict, not a request in the prose.** The `openai` SDK has
   `response_format` with a JSON schema. The API then refuses a shape that does not
   agree, so "no Markdown and no backticks" is a guarantee. The prose rule stays in the
   prompt as well.
5. **The persona is an AI intake assistant.** Not "a compassionate telehealth
   clinician". `SPEC.md` permits one disclaimer only: the bot is an AI intake assistant
   and not a physician.
6. **The red-flag line stays.** It makes the demo look real. The answers go in
   `associated_symptoms` and in `notes`.

## New dependencies

- **`openai`.** Sam approved it. One package. Its tree is `httpx`, `pydantic`,
  `typing-extensions`, `anyio`, `distro`, `jiter` and `sniffio`. The image has each of
  these, except `distro` and `jiter`, which are small.
- Nothing else. The tests use `pytest` and `monkeypatch`, which the repo has.

## Files

```
backend/
  app/
    engine/
      __init__.py           new   The package doc line
      prompts.py            new   All prompt text and the two JSON schemas
      llm.py                new   The OpenAI call. chat_json(), LLMError, to_messages()
      intake.py             new   next_turn(log) -> NextTurn
      summary.py            new   make_summary(log) -> the eight fields
      loop.py               new   start_intake(), run_turn(). The state machine
    modes/
      __init__.py           new   The package doc line
      base.py               new   The TurnMode protocol and the registry
    config.py               edit  OPENAI_MODEL, OPENAI_TIMEOUT_SECONDS, INTAKE_MAX_TURNS
    routes/
      sessions.py           edit  Remove STUB_SUMMARY
  tests/
    test_engine_prompts.py  new   The templates and the field names
    test_engine_llm.py      new   The request shape and the errors
    test_engine_intake.py   new   A scripted conversation. The turn limit
    test_engine_summary.py  new   The eight fields. A field with no answer
    test_engine_loop.py     new   The full intake through a fake mode
    test_routes_sessions.py edit  The stub is gone
  pyproject.toml            edit  openai
  poetry.lock               edit  poetry lock
  .env.example              edit  The new values
docs/
  API_REFERENCE.md          edit  The summary is real. A field with no answer
  TASKS.md                  edit  Mark section 3 and section 4
  task-03-intake-engine/todo.md      new
  session-logs/07-intake-engine.md   new
CLAUDE.md                   edit  The stack line says the openai SDK, not LiteLLM
```

`frontend/`, the `Dockerfile` and the compose file do not change. The `Dockerfile`
copies the full `app` directory, so a new module needs no change to it.

## Procedure — the prompts

- [x] Make `app/engine/prompts.py`. **All** prompt text is in this file. No prompt text
      in `intake.py`, in `summary.py` or in `llm.py`.
- [x] `INTAKE_SYSTEM` is a `string.Template` with `$max_turns`. It holds the persona,
      the rules and the topics. The topics are in the order of priority, because 6
      questions cannot cover 8 topics: chief complaint, onset and duration, location and
      character, severity, triggers, associated symptoms and red flags, prior treatments.
- [x] The prompt says that the first turn introduces the bot as an AI intake assistant
      and asks the first question in the same message.
- [x] `INTAKE_SCHEMA` is the JSON schema of the answer:
      `{"action": "ask" | "complete", "turn": integer, "question": string,
      "notes": string}`. Strict mode needs each key in `required` and
      `additionalProperties: false`, so `question` and `notes` are empty text for the
      action `complete`.
- [x] `SUMMARY_SYSTEM` is a different prompt. It makes the eight fields from the log. It
      says: use the words of the patient, do not invent, and write `not discussed` in a
      field that the intake did not cover. With 6 questions some fields have no answer,
      and an empty field looks like a fault in the frontend.
- [x] `SUMMARY_SCHEMA` has the eight fields of `SPEC.md`, each a string, each required.
- [x] `SUMMARY_FIELDS` is the tuple of the eight names. `summary.py` and the tests read
      it, so the list exists one time.

## Procedure — the LLM call

- [x] Make `app/engine/llm.py`. It is the only module that imports `openai`.
- [x] `LLMError` is the exception. It carries a short text for the `error_reason` column.
- [x] `chat_json(system, messages, schema, schema_name) -> dict`. It calls the chat
      completions endpoint with `response_format` of the type `json_schema` and
      `strict: true`, and it gives the parsed object.
- [x] Make the client in the function, not at the import. An import that needs the key
      breaks each test that does not have one. `app/recall/client.py` opens its client
      per call for the same reason, so the two modules have the same shape.
- [x] A missing `OPENAI_API_KEY`, a network failure, an HTTP failure and a body that is
      not JSON each raise `LLMError`. Put the key out of the text of the error, the same
      as `_redact()` in `app/recall/client.py`.
- [x] `to_messages(log)` changes the conversation log into the message list: the role
      `bot` becomes `assistant`, and the role `patient` becomes `user`. This is the one
      place that makes the change.

## Procedure — the intake

- [x] Make `app/engine/intake.py`. `next_turn(log) -> NextTurn`.
- [x] `NextTurn` is a frozen dataclass: `question: str | None` and `complete: bool`. The
      question is `None` when `complete` is `True`.
- [x] Count the turns with the role `bot` in the log. If the count is
      `INTAKE_MAX_TURNS` or more, give `NextTurn(None, True)` and **make no LLM call**.
- [x] If the count is less than the limit, call `chat_json` with `INTAKE_SYSTEM` and the
      messages. The action `complete` gives `NextTurn(None, True)`. The action `ask`
      gives `NextTurn(question, False)`.
- [x] An empty `question` with the action `ask` raises `LLMError`. A question that is
      empty text stops the intake with no message in the meeting, which looks like a
      hang.
- [x] `intake.py` has no prompt text and no `openai` import.

## Procedure — the summary

- [x] Make `app/engine/summary.py`. `make_summary(log) -> dict[str, str]`.
- [x] Call `chat_json` with `SUMMARY_SYSTEM` and `SUMMARY_SCHEMA`.
- [x] Give each of the eight fields, in the order of `SUMMARY_FIELDS`. A field that the
      model did not give becomes `not discussed`. Strict mode makes this improbable, but
      the frontend must never get a key that is absent.
- [x] `summary.py` has no prompt text and no `openai` import.

## Procedure — the mode boundary

- [x] Make `app/modes/base.py` with the `TurnMode` protocol:

```
handle_incoming_turn(session_id, raw_event) -> str | None
send_outgoing_turn(session_id, text) -> None
```

- [x] The protocol is the exact pair of names in [`../IMPLEMENTATION.md`](../IMPLEMENTATION.md).
- [x] `MODES: dict[Mode, TurnMode]` is the registry, and it is **empty** in this session.
      `get_mode(mode)` raises a clear error for a mode that has no implementation.
      Section 5 puts `chat` in the registry, and section 6 puts `voice` in it. Nothing
      above the boundary changes at that time.
- [x] `handle_incoming_turn` gives `None` for an event that is not a patient turn. Voice
      mode needs this: a transcript part that is not the end of a turn gives no text.

## Procedure — the state machine

- [x] Make `app/engine/loop.py`. It is mode-agnostic. It names no mode, and it holds no
      chat word and no voice word.
- [x] `start_intake(session_id)`: get the first question from the engine, send it with
      `send_outgoing_turn`, and put it in the log. Section 5 calls this when the status
      becomes `in_progress`.
- [x] `run_turn(session_id, patient_text)`: put the patient text in the log, call
      `next_turn`, and then:
      - a question: send it, put it in the log, and keep the status `in_progress`;
      - complete: call `make_summary`, write the summary, and **then** set the status
        `complete`.
- [x] **The summary is written before the status.** The frontend reads the status and
      then asks for the summary. The opposite order gives a window in which a complete
      session has no summary.
- [x] An `LLMError` sets the status `error` with a short reason. The route pattern of
      `RecallError` in `routes/sessions.py` is the same.
- [x] A session that is not `in_progress` takes no turn. A chat message after the intake
      is complete must not start the engine again.

## Procedure — the route and the stub

- [x] Remove `STUB_SUMMARY` from `app/routes/sessions.py`. The comment above it goes
      with it.
- [x] `get_summary` gives `session.summary`. The 404 rule before `complete` does not
      change.
- [x] A status that is `complete` with no summary gives HTTP 500 with a short text. This
      is a fault of the backend, and `loop.py` makes it impossible. Do not hide it with
      an empty object.

## Procedure — the configuration

- [x] Add `OPENAI_MODEL: str = "gpt-4o-mini"`, `OPENAI_TIMEOUT_SECONDS: float = 30.0`
      and `INTAKE_MAX_TURNS: int = 6` to `app/config.py`.
- [x] Do not remove the three CORS aliases at the end of the file. `app/main.py` imports
      by those names.
- [x] Put the new values in `.env.example`, with a `#` and the default.
- [x] `poetry add openai`, then `poetry lock`.

## Procedure — the tests

- [x] **No test makes a network call.** Each test of `intake.py`, `summary.py` and
      `loop.py` replaces `chat_json` with a function that gives a value from a script.
- [x] `test_engine_llm.py` uses the real `openai` SDK with a `httpx.MockTransport`
      client. The SDK takes an `http_client`, so the test uses the true code path. This
      is the `_transport()` pattern of `tests/test_recall_client.py`.
- [x] `test_engine_llm.py`: the request has the model, the strict schema and the
      messages in order. An HTTP 500, a timeout, a body that is not JSON and an absent
      key each give `LLMError`. The text of an error has no API key in it.
- [x] `test_engine_intake.py`: an empty log gives the first question; a script of
      answers gives one question per turn; the action `complete` ends the intake; the
      limit of 6 ends the intake **with no call to the LLM**; an empty question raises.
- [x] `test_engine_summary.py`: the result has the eight keys of `SUMMARY_FIELDS`; a
      field that the model did not give becomes `not discussed`; an `LLMError` goes up.
- [x] `test_engine_loop.py` is the standalone proof: a fake mode collects the outgoing
      text, a scripted patient answers, and the intake runs from the first question to
      the summary. Prove the status is `complete`, the log has the full conversation,
      the summary has the eight fields, and the outgoing text went through the fake mode
      only. No Recall, no webhook and no network.
- [x] `test_engine_loop.py`: an `LLMError` sets the status `error` and the reason.
- [x] `test_engine_loop.py`: a turn on a session that is `complete` changes nothing.
- [x] `test_engine_prompts.py`: `$max_turns` substitutes; the summary prompt names the
      eight fields; the two schemas are strict and their `required` list is complete.
- [x] `test_routes_sessions.py`: remove the import of `STUB_SUMMARY` and its test. Add:
      `complete` with a summary gives the summary; `complete` with no summary gives 500.
- [x] Each of the 112 tests that exist now must pass. Only the stub test changes.

## Proof

- [x] `poetry run pytest` in `backend/` passes. The count is more than 112.
- [x] The engine runs standalone against a scripted conversation, with the LLM mocked.
      `test_engine_loop.py` is this proof. Give the number of turns and the summary in
      the session log.
- [x] Prove that the turn limit is the engine and not the prompt. Method: a fake
      `chat_json` that always gives the action `ask`. The intake must stop at 6.
- [x] `docker compose -f deploy/docker-compose.yml up -d --build` in `backend/`, then a
      loop on `docker inspect --format '{{.State.Health.Status}}' recall-api` gives
      `healthy`. Do not read the value in the same second as the start.
- [x] `GET /health` gives HTTP 200, and the CORS behavior does not change. Method:
      `docker exec recall-api curl -i ...`. Use `curl -i`, not `curl -I`.
- [x] The image has the `openai` package. Method: `docker exec recall-api python -c
      "import openai"`.
- [x] The database keeps its rows through the build. The schema does not change in this
      task, so `PRAGMA user_version` stays at 2.
- [x] One real call to the OpenAI API by hand, with a scripted patient. Sam approved
      it. It is not part of `pytest`. **It found three faults in the prompts that no
      mocked test can find.** See the session log.

## Done criteria

- [x] The engine gives the next question from a log, and it signals complete.
- [x] The summary has the eight fields of `SPEC.md`.
- [x] `STUB_SUMMARY` is gone.
- [x] The intake stops at 6 questions, and the engine makes that decision.
- [x] No module above the mode boundary names chat or voice.
- [x] The tests pass with no network, and the container is healthy.
- [x] `../session-logs/07-intake-engine.md` is complete.

## Out of scope

- The chat send and the chat receive logic. That is section 5.
- The TTS code and the output audio. That is section 6.
- A change to `frontend/`.
- A change to the database schema. The engine uses the columns that exist.
- A deploy to the homelab server. Ask Sam first.
- A commit and a push.

## What changed against the plan

- **The `openai` SDK uses `httpx2`, not `httpx`.** `openai` 3.16.2 takes an
  `httpx2.Client` for `http_client`, so the image now has two HTTP client packages:
  `httpx` for `app/recall/client.py` and `httpx2` for the SDK. The test of `llm.py`
  uses `httpx2.MockTransport`, not the `httpx.MockTransport` of
  `tests/test_recall_client.py`. The pattern is the same, the package is not.
- **`NextTurn.complete` is a property, not a second field.** The plan gave the
  dataclass two fields. Two fields can disagree, and a question with `complete: True`
  would be a fault that no type can refuse. One field holds the state, and `complete`
  reads it. The API that the plan named does not change.
- **The intake prompt is built by a function, `prompts.intake_system(max_turns)`.** The
  prompt holds the JSON shapes, so it has literal braces and it cannot be an f-string.
  It is a `Template` with two placeholders, `$max_turns` and `$red_flags`, and the
  function does the substitution. All prompt assembly thus stays in `prompts.py`.
- **`RED_FLAGS` is one constant that both prompts use.** The plan put the red-flag list
  in the intake prompt only. The summary prompt needs the same list, or the two prompts
  do not agree on what a red flag is.
- **The live check found three faults in the prompts.** This was the optional step. It
  was not optional in effect: no mocked test can find any of the three. See the session
  log.
- **`test_engine_prompts.py` reads the source of the other engine modules.** The plan
  did not name this test. `CLAUDE.md` makes "all prompt text in `prompts.py`" a rule,
  and a rule with no test is a comment. The same test refuses the words chat and voice
  in the engine, which is the rule of section 4.
- **`docs/SPEC.md` and `docs/ARCHITECTURE.md` changed as well.** The plan named
  `CLAUDE.md` only. `SPEC.md` says that a build decision goes in it before the build, and
  three of its lines named LiteLLM.
