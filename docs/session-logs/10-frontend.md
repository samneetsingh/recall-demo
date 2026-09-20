# 10 — The frontend

Written in ASD-STE100 Simplified Technical English.

- **Date:** 2026-09-20
- **Task:** Section 7 of [`../TASKS.md`](../TASKS.md), then section 5a. See
  [`../task-07-frontend/todo.md`](../task-07-frontend/todo.md) and
  [`../task-05a-bot-leave/todo.md`](../task-05a-bot-leave/todo.md)
- **Result:** complete for section 7 — the page is built, deployed and proved in a live
  Google Meet call from `recall.samneet.com`. The call also closed the two backend items
  that session 09 left open. Part 2 added section 5a, which takes the bot out of the
  call at the end of an intake; it needs a live call to prove.

## Summary

The backend ran the full intake and no page called it. This session made
`frontend/public/index.html`: a meeting URL goes in, the page polls the status, and the
eight fields come on the page at the end. It is one file of plain HTML and JS, with no
framework, no build step and no new package. `backend/` did not change.

## Files changed

| File | Change | Reason |
|---|---|---|
| `frontend/public/index.html` | edit | The form, the poll, the summary and the error. The `/health` check of task 1d is out |
| `docs/task-07-frontend/todo.md` | new | The plan of this session |
| `docs/TASKS.md` | edit | Section 7, and two items of section 8 |
| `docs/FLOW.md` | edit | The header, and part 8 |
| `docs/session-logs/09-chat-mode.md` | edit | Two open items that this call closed |
| `docs/session-logs/10-frontend.md` | new | This log |

**`backend/` did not change.** Method: `git diff --stat -- backend/` gives no line.
`package.json`, `package-lock.json` and `wrangler.jsonc` did not change.
**This session added no package.**

## Decisions

- **Plain HTML and JS, one file.** Sam selected it. The page is a form, a status line
  and eight fields. A framework adds a package and a build step, and
  `wrangler.jsonc` would then point at a build output and not at `public/`. The
  capability is the same.
- **The page renders from the poll only.** The status in the answer to `POST /sessions`
  is not used. A Recall failure also gives HTTP 201, with the status `error` and **no
  reason**, and only `GET /sessions/{id}` has the reason. Two sources can disagree, and
  one cannot.
- **The session id is in the URL query string.** Sam selected it.
  `history.replaceState` writes `?session=<id>`, so a reload keeps the session and a
  link continues one. `../IMPLEMENTATION.md` permits the URL or memory, and not
  `localStorage`.
- **The instruction is the headline, and the status word is secondary.** Sam selected
  it. `waiting_for_bot` says "Admit the bot to your Google Meet call", with the elapsed
  time below it. The user must act, and the word `waiting_for_bot` does not say that.
- **A failed poll does not stop the poll, and HTTP 404 does.** The backend is on a home
  server behind a Cloudflare Tunnel, so a short interruption must not end the session on
  the page. HTTP 404 is different: the id is not in the database, and more requests
  cannot change that.
- **A `setTimeout` chain, and not `setInterval`.** The next request goes out 2.5 seconds
  after the last answer. `setInterval` sends a second request while the first one waits,
  and the backend is behind a tunnel where a slow answer is usual.
- **The mode is a constant in the code and not a control.** Voice mode is section 6 and
  it has no implementation, so a session with the mode `voice` goes to `error`. A
  control that makes an error on each use is worse than no control.
- **The conversation is not on the page.** Sam selected it. The backend has no route for
  the `turns` table, and a route is backend work that does not go in a frontend session.
  The patient reads the questions in the Meet chat, where the bot sends them.
- **Three texts of the backend go on the page with no change:** `error_reason`,
  `not discussed` and `RED FLAG:`. The page gives them a color and never other words.
  `error_reason` is the only text that says why a bot did not join, and a friendly text
  in place of it loses the one fact that the user needs.
- **`textContent`, and never `innerHTML`.** The summary holds words that a patient typed
  and a model wrote.
- **The elapsed time counts from the page and not from the session.** The answer to
  `GET /sessions/{id}` has no `created_at`, so the page cannot know when the session
  started. The words on the page say "on this page", because a number with the wrong
  origin is worse than no number.
- **The three states were proved with a stub, and the render code was not changed for
  it.** A copy of the page in the scratchpad has one different line, the `API` constant.
  No live session holds a `RED FLAG:` value or stays in `waiting_for_bot` on demand.

## Verified facts

- **`npm run check` passes.** Method: `CLOUDFLARE_ACCOUNT_ID=f25beb959f46731f346dedc78c224cf1 npm run check`
  in `frontend/`. It reads 1 file from `public/`. The account id is necessary, because
  the OAuth token has six accounts. See [`03-frontend-worker.md`](03-frontend-worker.md).
- **`backend/` did not change.** Method: `git diff --stat -- backend/` gives no line.
- **The `complete` state renders against the live backend.** Method: `npm run dev`, then
  `http://localhost:8787/?session=ac7fe64a52114045acb4180f241ad88b` in a real browser.
  The eight fields render, `prior_treatments` and `notes` are muted because they hold
  `not discussed`, and the browser gives no console error.
- **The `waiting_for_bot` state renders, and the clock goes up.** Method: a stub in the
  scratchpad. The headline is "Admit the bot to your Google Meet call", and the meta
  line went `0 s` → `5 s` → `2 min 7 s`.
- **The `error` state shows the true reason of the backend.** Method: `POST /sessions`
  from the deployed form with `https://example.com/not-a-meeting`. The answer was HTTP
  201, and the poll then gave the status `error` with
  `recall http 400: {"meeting_url":["The meeting_url is malformed, or for an unsupported platform."]}`.
  **This is a real Recall refusal and not a stub.** It made the session
  `7ab008128fbb41a99accffa616cf5f5e`, which is a junk row with no bot.
- **A bad URL shows the answer of FastAPI.** Method: the text `banana` in the form. The
  page shows `HTTP 422 — {"detail":[{"type":"url_parsing",...}]}`, the form stays, the
  button comes back, and the URL query string does not change.
- **An HTTP 500 on the summary is not hidden.** Method: the stub, with a session that is
  `complete` and has no summary. The page shows
  `HTTP 500 — {"detail": "the session is complete and has no summary"}`.
- **HTTP 404 on the poll stops the poll.** Method: the stub, with an id that it does not
  know. The page says "No session has this id." and the requests stop.
- **A backend that stops does not end the session on the page.** Method: the stub was
  stopped while the page polled. The page kept the status `waiting_for_bot`, showed
  "The backend does not answer. The page tries again.", and the request count went from
  13 to 16 in 6 seconds. The stub was started again, and the warning went away with no
  reload.
- **A reload keeps the session.** Method: a reload of
  `?session=7ab008128fbb41a99accffa616cf5f5e`. The same reason came back on the page.
  `New session` then cleared the query string and gave the form back.
- **The `RED FLAG:` mark and the `not discussed` mark are correct.** Method: the stub,
  with a summary whose `associated_symptoms` starts with `RED FLAG:`. That field gets
  the alert color, the text does not change, and `prior_treatments` is muted.
- **The page has no sideways scroll at 390 px, and dark mode is correct.** Method: a
  browser at 390 × 844, and `prefers-color-scheme: dark` at 760 px.
- **The CORS behavior did not change.** `backend/` has no change, so it cannot. Each
  check above ran from `http://localhost:8787` or from `https://recall.samneet.com`
  against the live backend, and each one passed.
- **The deploy is live.** Method: `npm run deploy`. Version
  `c2219c53-0508-4f92-9777-b61007307f0c` on `recall.samneet.com`. The live URL serves
  the form, the text "This page is a placeholder" is gone, and `/health` is not in the
  page.
- **The full loop operates from the deployed page.** Method: `recall.samneet.com` with
  `https://meet.google.com/dix-ufgb-ojb`. It made the session
  `ae72c30fdd8b40fb987a03ea24cfe7e4` and the bot
  `a311030c-e52c-4a38-9f02-30a78826e46b`. The page showed `waiting_for_bot` at 08:56,
  `in_progress` at 08:56:19 when Sam admitted the bot, and `complete` with the eight
  fields at 09:00:00. **No console error and no page error in the whole call.**

### The two backend items of session 09

- **The consent notice comes before the first question. This is proved on the server.**
  Method: `get_bot_logs` for `a311030c-e52c-4a38-9f02-30a78826e46b`. The notice went out
  at `08:56:18.327` with `"pin": true`, and the first question at `08:56:20.437`. The
  difference is 2.11 seconds, and the order is correct. Session 09 had the opposite
  order, from the create-bot hook.
- **`pin` is the correct field name of the send endpoint.** Method: the same log gives
  the body `{"to": "everyone", "message": ..., "pin": true}` and the answer HTTP 200,
  **and Sam saw the notice pinned in the Meet chat.** The HTTP 200 alone is not the
  proof: an API that ignores a key that it does not know also gives 200. The pin in the
  interface is the proof.

### What the call showed about the prompts

These are data for section 8a. This session changed no prompt.

- **The model stopped after 4 questions of 6.** `get_bot_logs` gives 4 questions and the
  closing line. Session 09 stopped after 5. `triggers`, `prior_treatments` and `notes`
  thus came back `not discussed`, which is three of the eight fields.
- **The first question introduces the assistant a second time.** The notice says "I am
  an AI intake assistant, not a physician", and the first question then said "Hello! I
  am the intake assistant, and I collect history before your visit." This is the same
  fault that session 09 recorded, and it is still open.

## Corrections

- **Wrong:** a Playwright wait for `#poll-warning[hidden]` proves that the warning went
  away. **Correct:** that selector can never match, because the default state of
  `waitForSelector` is "visible" and a hidden element is not visible. A wait on the
  property, `element.hidden === true`, is the correct test. The first two runs of the
  recovery check failed for this reason, and the page was correct in each one.
- **Wrong:** `(python3 stub.py &)` in a tool call keeps the server after the call ends.
  **Correct:** the process dies with the shell of the call. The check then showed
  "The backend does not answer" and I read it as a fault of the page. A background
  process must start as a background task, not with `&` in a one-shot shell.
- **Wrong:** the page can show how long a session has run. **Correct:**
  `GET /sessions/{id}` gives no `created_at`, so the page can only count from when it
  opened. The words on the page say "on this page" for this reason.

## Open items

- [ ] Commit the changes of this session. The working tree holds
      `frontend/public/index.html`, the plan, and the documents. The deployed page is
      **in front of** the commit, because Sam asked for the deploy first. Owner: Sam.
- [ ] Delete the junk session `7ab008128fbb41a99accffa616cf5f5e` if a clean database
      matters for the demonstration. It has the status `error` and no bot. Owner: Sam.
- [ ] Section 8a has one more data point: the model stopped after 4 questions of 6 in
      this call, and 5 of 6 in session 09. Owner: a later session.
- [ ] The six weak points of [`../FLOW.md`](../FLOW.md) part 9 go in the README as
      limitations. Owner: the docs pass of section 9.
- [ ] **Is the `webhook-id` of a real-time retry the same each time?** Still open. This
      call gave no failed delivery, so no retry occurred. Owner: section 6, or a call
      where a delivery fails.
- [ ] Starlette says that `httpx` with `TestClient` is deprecated. Owner: the next
      session that touches the tests.

## Next session starts here

Section 6 of [`../TASKS.md`](../TASKS.md), voice mode, or section 8a, prompt tuning.
Section 7 needs nothing more.

**If section 6:** the frontend needs no change for it. The page reads `status` and
`summary` only, and it never learns the mode. Follow the four steps at the end of
[`09-chat-mode.md`](09-chat-mode.md).

**If section 8a:** the live calls of sessions 09 and 10 give the evidence. The model
stopped early in each one, and the first question introduces the assistant a second
time. `backend/app/engine/prompts.py` holds all of the text.


---

# Part 2 — The bot leaves the call (section 5a)

Sam asked at the end of the session: can the bot leave, so the patient does not have to
remove it? This part is `backend/` only, and it went in after the frontend commit
`1f8bbb5`.

## Files changed, part 2

| File | Change | Reason |
|---|---|---|
| `backend/app/config.py` | edit | `BOT_LEAVE_DELAY_SECONDS`, 3.0 |
| `backend/app/recall/client.py` | edit | `leave_call(bot_id)` |
| `backend/app/routes/webhooks.py` | edit | `_send_closing_message` is `_finish_intake`. `_leave_call` |
| `backend/tests/test_recall_client.py` | edit | 6 tests of the leave call |
| `backend/tests/test_routes_webhooks.py` | edit | 9 tests of the wire, and `leave_call` in the `offline` fixture |
| `docs/API_CONTRACT.md` | edit | The leave endpoint, and the automatic-leave defaults |
| `docs/API_REFERENCE.md` | edit | What the backend does at the end of an intake |
| `docs/FLOW.md` | edit | Flow C, and the note under it |
| `docs/TASKS.md` | edit | Section 5a |
| `docs/task-05a-bot-leave/todo.md` | new | The plan |

**`app/engine/` and `app/modes/` did not change.** `frontend/` did not change.
**This part added no package.**

## Decisions, part 2

- **The leave is not on the mode boundary.** `send_notice` went on the boundary in
  section 5, because how a notice reaches the patient is mode-specific: chat pins a
  message and voice will speak it. A leave is not mode-specific. It is one HTTP call to
  Recall, and voice mode makes the same call, so `app/modes/` did not change and section
  6 gets the behavior at no cost.
- **`routes/webhooks.py` calls `recall/client.py` directly.** `../../CLAUDE.md` permits
  a route to call into `engine/`, `recall/` or `db/`, and `routes/sessions.py` already
  calls `create_bot` in the same manner. The leave is not part of the conversation, so
  it is not in `engine/loop.py`, which is the same rule that keeps the closing line out
  of it.
- **A wait of 3 seconds between the line and the leave.** Sam selected it against no
  wait. Recall answers HTTP 200 when it **accepts** a message, and the bot has still to
  type it into the meeting. A leave with no wait can cut the closing line, which is the
  same class of race as the notice-and-pin fault of session 09. The value is a setting,
  so a live call can tune it with no code change.
- **A session in `error` keeps its bot.** Sam selected it. An error usually means that
  the bot takes no command, so the leave would fail in the same manner. The
  `everyone_left_timeout` of 2 seconds still removes the bot when the patient goes.
- **A failed leave is a log line.** The summary is written and the status is `complete`.
  A bot that stays in the call is untidy, and it costs no data. A failed leave must
  never change a complete session.

## Verified facts, part 2

- **`POST /api/v1/bot/{id}/leave_call/` is the endpoint, and it is irreversible.**
  Method: `get_doc` for `bot_leave_call_create`. No request body, HTTP 200 with the bot
  object or HTTP 400 with no body, 300 requests each minute for one workspace.
- **Recall has no endpoint that ends a meeting for all participants.** The bot joins as
  an ordinary participant, and Google Meet gives that action to the host only.
- **The bot already left 2 seconds after the patient.** Method: `get_doc` for
  `automatic-leaving-behavior`. `everyone_left_timeout` has the default 2 seconds. This
  task is thus not a repair of a bot that stays for ever: it makes the bot leave **at
  the end of the intake, while the patient is still there**. The other timeouts are
  3600 seconds, so a patient who keeps the call open sees a silent bot for one hour.
- **The 265 tests pass.** Method: `poetry run pytest -q` in `backend/`. Part 1 of this
  session had 250, and section 5a added 15.
- **No test uses the network.** Method: the plugin of lesson 3, then
  `poetry run pytest -q -p block_network`. The result is 265 passed. **`leave_call` went
  into the `offline` fixture of `test_routes_webhooks.py` before the route called it**,
  which is the fault that lesson 3 records from session 09.
- **The leave is load-bearing in the tests.** Method: remove `_leave_call(session)` from
  `_finish_intake`, then run the suite. Three tests fail. Restore it, and 265 pass.
- **The order of the closing line and the leave is load-bearing.** Method: move
  `_leave_call(session)` above the `send_outgoing_turn` of the closing line, then run
  the suite. `test_the_closing_line_goes_out_before_the_leave` fails and nothing else
  does, so that test holds the rule by itself.
- **`app/engine/` and `app/modes/` did not change.** Method:
  `git diff --stat -- backend/app/engine/ backend/app/modes/` gives no line.

## Corrections, part 2

- **Wrong:** the bot sits in the call for ever after the intake, so a leave repairs a
  bot that never goes. **Correct:** `everyone_left_timeout` already removes it 2 seconds
  after the patient leaves. The true gain is the time **before** that: a bot that goes
  when the intake ends, and not one that waits, silent, for the patient to act.

## The live call, part 2

Sam deployed and ran two calls. The first one, bot `3fedba10`, still had the old code:
the closing line went out at 09:05:28 and **no `leave_call` request is in the bot logs**.
The second one, bot `193f426d-ba66-4cdc-ba6a-3ac67b642f2e`, has the leave.

- **The bot leaves the call by itself.** Method: `get_bot_logs`. The closing line went
  out at `09:21:17.393`. Recall then wrote `Received a /leave_call request from your
  server`, with the sub code `bot_received_leave_call`, at `09:21:20.686`, and
  `POST /api/v1/bot/{id}/leave_call/ -> 200` at `09:21:20.732`.
- **The delay is long enough.** The gap between the closing line and the leave is
  **3.293 seconds**: the 3.0 second wait of `BOT_LEAVE_DELAY_SECONDS` and 0.29 seconds
  of overhead. Sam saw the closing line in the Meet chat before the bot left, which is
  the part that the log cannot show. `BOT_LEAVE_DELAY_SECONDS` does not need a change.
- **Recall writes its own log line for the leave.** The sub code is
  `bot_received_leave_call`. A later session can use it to find a leave in the logs.
- **The notice still comes first.** The notice went out at `09:20:49.171` with
  `"pin": true`, and the first question at `09:20:50.760`. The difference is 1.59
  seconds.
- **The page still shows the summary after the bot leaves.** Method:
  `GET /sessions/a54e4fea974642ac843f88fc2583a912` gives `complete` with the eight
  fields. The page stops its poll at `complete`, so the bot that goes changes nothing
  on it.

**A fault that a first deploy can make.** The first call proved that a deploy which
does not rebuild the image gives a backend that answers each request correctly and does
not have the new code. The closing line went out and the leave did not, and the two are
three lines apart in one function. The test is
`docker exec recall-api python -c "from app.recall import client; print(hasattr(client, 'leave_call'))"`,
which reads the code that **runs** and not the code that is checked out.

## What the calls show about the prompts

Section 8a, with four live calls now. This session changed no prompt.

| Call | Questions of 6 | Fields that say `not discussed` |
|---|---|---|
| Session 09, bot `2277e43d` | 5 | 2 |
| Bot `a311030c` | 4 | 2 |
| Bot `3fedba10` | 5 | 2 |
| Bot `193f426d` | **3** | **3** of 8 |

**The model never used its 6 questions, and the last call used 3.** The engine
guarantees a maximum and not a minimum, so an early stop costs data: `triggers`,
`prior_treatments` and `notes` came back `not discussed` in the last call. The first
question also introduces the assistant a second time in each call, after the notice
already did it. Both are open items of section 8a.

## Open items, part 2

- [x] Commit part 2. Sam committed it as `1c4b794`, after the live call. The
      documents of this part came after the commit.
- [ ] Section 8a is more urgent than it was. The early stop got worse, not better, and
      3 questions of 6 gives a summary where 3 of the 8 fields hold no data.
      Owner: a later session.
