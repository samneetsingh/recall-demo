# Task 7 — The frontend: todo

Written in ASD-STE100 Simplified Technical English.

## Scope

The backend runs the full intake. A live Google Meet call proved it on 2026-09-20: the
bot joined, it sent a pinned notice, it interviewed a patient in the chat, and it wrote
the summary. **No page calls any of it.** `recall.samneet.com` serves a placeholder that
calls `GET /health` one time.

This task makes the page. Section 7 of [`../TASKS.md`](../TASKS.md). **`frontend/` only.**

## The gap

1. `public/index.html` has no form, no poll and no summary. It says "This page is a
   placeholder."
2. Its last 20 lines call `GET /health`. That was the proof of item 1d, and the comment
   in the file says that task 7 removes it.

## Answers from Sam

| Question | Answer |
|---|---|
| Plain HTML and JS, or a framework | **Plain HTML and JS.** One file, `public/index.html`. No new dependency and no build step |
| The session id | **In the URL query string.** `?session=<id>`, with `history.replaceState`. A reload keeps the session. Not `localStorage` |
| The wait for the bot | **An instruction and the elapsed time.** "Admit the bot to your Google Meet call" is the first line. The status word is secondary |
| The conversation | **No.** The status and the summary only. A turns route is backend work, and it is not in this session |
| The deploy | **Yes, after Sam sees the result.** `npm run check` first, then Sam gives the word, then `npm run deploy` |
| A live Google Meet call | **Yes, at the end of this session.** Each other item is proved first |

## Verified before the plan

Method: `curl` against the live backend, and a read of `app/routes/sessions.py`.

- **The backend has three public routes.** `POST /sessions`, `GET /sessions/{id}` and
  `GET /sessions/{id}/summary`, plus `GET /health` and `POST /webhooks/recall`. **There
  is no route for the turns.** This is why the conversation is not on the page.
- **The path has no slash at the end.** The route is `APIRouter(prefix="/sessions")`
  with the path `""`, so the URL is `/sessions` exactly. A slash at the end gives an
  HTTP 307 to a different URL, and a redirect makes a second CORS test.
- **The test data for the complete state is live.**
  `GET /sessions/ac7fe64a52114045acb4180f241ad88b` gives HTTP 200, the status
  `complete`, and the eight fields. Two of them hold `not discussed`, which the document
  says is usual.
- **CORS operates for the development origin.** `GET /health` with the header
  `Origin: http://localhost:8787` gives `access-control-allow-origin:
  http://localhost:8787`. `wrangler dev` uses that port.
- **A bad URL does not fail the request.** `POST /sessions` gives HTTP 201 with the
  status `error` if Recall refuses the bot. The reason is only in the answer to
  `GET /sessions/{id}`, so the page must read it from the poll and not from the POST.
- **The summary of the live call has no red flag.** `associated_symptoms` is "nausea, no
  red flag was reported." A red flag comes at the start of that field after the text
  `RED FLAG:`, so a stub gives the only test of that mark.

## New dependencies

**None.** `fetch`, `history.replaceState` and `URLSearchParams` are in each browser that
Workers serves. `package.json` keeps `wrangler` as its one development dependency.

## Files

```
frontend/
  public/
    index.html    edit  The form, the poll, the summary and the error. The /health check goes out
docs/
  task-07-frontend/todo.md      new   This plan
  TASKS.md                      edit  Section 7
  FLOW.md                       edit  Part 8, what the frontend reads
  session-logs/10-frontend.md   new   The log of this session
```

**`backend/` does not change.** `git diff --stat -- backend/` must give no line at the
end of this session. `package.json`, `package-lock.json` and `wrangler.jsonc` do not
change: the page is one static file, and `wrangler` serves `public/` today.

## Procedure — the form

- [x] A `<form>` with one text input for the meeting URL and one submit button. The
      input has `type="url"`, `required` and a `placeholder` that shows a Meet URL.
- [x] Submit sends `POST {API}/sessions` with `Content-Type: application/json` and the
      body `{"meeting_url": <the input>, "mode": "chat"}`.
- [x] **The mode is a constant in the code, not a control.** Voice mode is section 6 and
      it has no implementation. A session with the mode `voice` goes to `error`. Write
      the reason in a comment.
- [x] The button is disabled while the request is in operation, so two clicks do not make
      two sessions and two bots.
- [x] A result that is not HTTP 201 shows the text of the answer near the form, and the
      form stays. A `HttpUrl` that FastAPI refuses gives HTTP 422, and the user must see
      why.
- [x] A network failure shows the error text near the form. The form stays.
- [x] HTTP 201 gives `{session_id, status}`. The page keeps the id, puts
      `?session=<id>` in the URL with `history.replaceState`, hides the form, and starts
      the poll.
- [x] **The status of the POST is not used to render.** The page renders from the poll
      only, because a Recall failure gives HTTP 201 with the status `error` and no
      reason. One source of truth is less code and no disagreement.

## Procedure — the poll

- [x] On load, read `?session` with `URLSearchParams`. If there is an id, hide the form
      and start the poll. If there is none, show the form.
- [x] `GET {API}/sessions/{id}` every 2500 milliseconds. Use a chain of `setTimeout`,
      and not `setInterval`: a slow answer must not make two requests at the same time.
- [x] The poll stops when the status is `complete` or `error`. It does not stop for
      `creating_bot`, `waiting_for_bot` or `in_progress`.
- [x] **A failed poll does not stop the poll.** A network failure or an HTTP 5xx shows a
      short line that says that the backend does not answer, and the next request goes
      out at the usual time. The backend is on a home server through a tunnel, so a short
      interruption must not end the session on the page.
- [x] **HTTP 404 stops the poll.** The id is not in the database. The page says that no
      session has this id, and it gives a way back to the form. An old link in a browser
      makes this condition.
- [x] Count the time from the first poll and show it in seconds. `waiting_for_bot` can
      continue for a minute, and a number shows that the page is not dead.

## Procedure — the four status states

Each state gives a headline, a short text, and the status word with the elapsed time. The
headline says what the user must do, because the status word does not.

- [x] `creating_bot` — "The bot starts." / "The backend asks Recall for a bot."
- [x] `waiting_for_bot` — **"Admit the bot to your Google Meet call."** / "The bot waits
      at the door. Let it in to start the intake." This is the state that needs an
      action from the user, so it is the strongest line on the page.
- [x] `in_progress` — "The intake is in operation." / "Answer the questions of the bot in
      the meeting chat. The summary comes to this page at the end."
- [x] `complete` — "The intake is complete." The summary card comes below it.
- [x] A status word that the page does not know shows the word as it is. Do not fail. The
      backend can add a status, and an unknown word is better than an empty page.
- [x] The status region has `aria-live="polite"`, so a change is announced.

## Procedure — the summary

- [x] The status `complete` calls `GET {API}/sessions/{id}/summary` one time, and renders
      the eight fields: `chief_complaint`, `onset_duration`, `location_character`,
      `severity`, `triggers`, `associated_symptoms`, `prior_treatments` and `notes`.
- [x] The order and the labels are from `../SPEC.md`: Chief complaint, Onset and
      duration, Location and character, Severity, Triggers, Associated symptoms, Prior
      treatments, Notes.
- [x] The fields render from a list of `[key, label]` pairs. A field that the answer does
      not hold renders as empty, and the page does not fail.
- [x] **`not discussed` is not an error.** The document says that the intake asks a small
      number of questions, so this text is usual. Show it in the muted color, and do not
      hide the field and do not add a warning.
- [x] **The red flag.** A value of `associated_symptoms` that starts with `RED FLAG:`
      gets the alert color. **The text does not change.** The prefix is what the backend
      wrote, and it stays on the page.
- [x] A summary request that fails shows the failure. The route gives HTTP 500 if a
      session is `complete` and has no summary, which the document calls a fault of the
      backend. Do not hide it.
- [x] The text of a field goes in the page with `textContent`, and never with `innerHTML`.
      The summary holds words that a patient typed and a model wrote.

## Procedure — the error state

- [x] The status `error` shows `error_reason` **as it is**. Do not replace it with a
      friendly text and do not hide it. It is the only text that says why the bot did not
      join. `../IMPLEMENTATION.md` gives this rule.
- [x] The reason goes in a monospace element, because it holds a value such as
      `recall http 400: {"code":"cannot_command_unstarted_bot"}`.
- [x] A short line above the reason says that the session stopped. The reason is not
      changed by that line.
- [x] `error_reason` that is `null` with the status `error` shows that no reason was
      given. Do not show an empty box.

## Procedure — back to the form

- [x] A "New session" control clears `?session` from the URL, stops the poll, and shows
      the form. A user who ends one intake must not edit the URL by hand to start
      another.

## Procedure — remove the /health check

- [x] Delete the last script block of `public/index.html` and the "Backend connection"
      card. The comment in the file says that task 7 replaces this section.
- [x] Keep the `API` constant. The new code uses the same value,
      `https://recall-api.ss-ubuntu-01.net`.
- [x] Keep the style block, the colors, the dark mode and the layout. They operate, and
      this task adds to them and does not make them again.

## Procedure — the checks

The page has no test framework, and this task adds none. The proof is a run.

- [x] `npm run check` in `frontend/` passes. It is `wrangler deploy --dry-run`, and it
      needs `CLOUDFLARE_ACCOUNT_ID=f25beb959f46731f346dedc78c224cf1`, because the OAuth
      token has six accounts. See `../session-logs/03-frontend-worker.md`.
- [x] **The complete state, with no call.** `npm run dev`, then open
      `http://localhost:8787/?session=ac7fe64a52114045acb4180f241ad88b`. The page must
      show the eight fields of the live call. This is a real answer from the live
      backend through a real browser, so it proves the poll, the summary request and
      CORS in one run.
- [x] **The three states, with a stub.** A small server in the scratchpad gives a fixed
      answer for `GET /sessions/{id}` and `GET /sessions/{id}/summary`, with the CORS
      headers. A copy of `index.html` in the scratchpad points `API` at it. This gives
      `waiting_for_bot`, `error` with a reason, and a summary with a `RED FLAG:` value,
      which no live session has. **The copy is throwaway.** Only the one constant is
      different, so the render code that runs is the code that ships.
- [x] **A real error session.** `POST /sessions` on the live backend with a URL that is
      not a Meet call. The answer is HTTP 201 with the status `error`, and the poll then
      shows the true reason from Recall. This makes one junk row in the database and no
      bot.
- [x] **CORS did not change.** `backend/` has no change in this session, so it cannot
      change. The run from `http://localhost:8787` is the proof that the list still holds
      that origin.
- [x] **The live call.** Sam starts a Google Meet call. The page takes the URL, the bot
      joins, Sam admits it, the page shows `waiting_for_bot` and then `in_progress`, Sam
      answers in the chat, and the eight fields come to the page. Sam must disable
      continuous chat in the call, or the notice is not pinned.
- [x] **Two open backend items get an answer in that call.** Is `pin` the correct field
      name of the send endpoint, and does the notice now come before the first question?
      Read the Meet chat and `get_bot_logs`, and write the answer in the session log.
      These need a call and no code.

## Out of scope

- **Any change to `backend/`.** If the page needs a route that does not exist, stop and
  ask. That is a backend task, and it does not go in this turn.
- **Voice mode.** Section 6. The page sends the mode `chat`.
- **Prompt tuning.** Section 8a. Three faults of the live call are already written
  there, and a fourth is visible on the page: `prior_treatments` holds `not discussed`.
  The page shows the text and does not repair the prompt.
- **A turns view.** It needs a backend route.
- **A commit or a push.** Sam does that, or he asks for it.

## At the end of the session

- [x] Check the completed boxes in this file.
- [x] Mark the items of section 7 in `../TASKS.md` that now pass.
- [x] Update part 8 of `../FLOW.md`, which says what the frontend reads.
- [x] Copy `../session-logs/TEMPLATE.md` to `../session-logs/10-frontend.md` and fill it
      in.
