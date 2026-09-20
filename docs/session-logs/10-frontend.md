# 10 — The frontend

Written in ASD-STE100 Simplified Technical English.

- **Date:** 2026-09-20
- **Task:** Section 7 of [`../TASKS.md`](../TASKS.md). See
  [`../task-07-frontend/todo.md`](../task-07-frontend/todo.md)
- **Result:** complete — the page is built, deployed and proved in a live Google Meet
  call from `recall.samneet.com`. The call also closed the two backend items that
  session 09 left open.

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
