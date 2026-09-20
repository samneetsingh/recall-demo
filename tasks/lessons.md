# Lessons

Written in ASD-STE100 Simplified Technical English. Read this at the start of a session.
Add a pattern after each correction from Sam.

## Ask a question with the question tool. Do not bury it in prose

**Date:** 2026-09-19. **Session:** 05.

**What happened:** I put an approval request and four decisions in a long message. Sam
had to read an essay to find the questions.

**The rule:** A question goes in the `AskUserQuestion` tool, with the options. Prose
before it is two sentences maximum. A decision that Sam must make is never a paragraph
in a summary.

**Why:** Sam answers a question with options in seconds. He does not read an essay to
find the question in it.

**How to apply:** Before you send a message, look for a question mark or a request for
an answer. If there is one, move it into the tool.

## A mocked test does not prove a prompt. Call the real model

**Date:** 2026-09-20. **Session:** 07.

**What happened:** The intake engine had 68 tests and all of them passed. One call to
the real `gpt-4o-mini` then found three faults in the prompts in 3 minutes: the model
stopped with a question unused, it called nausea a red flag, and it made "the worst
headache of my life" from "really bad headaches". The fix for the third fault made the
opposite fault, and only a second live patient showed it.

**The rule:** After you write or change a prompt, run it against the real model with a
scripted conversation. Write the script by hand, outside `pytest`. Use more than one
patient: one with the feature and one without it.

**Why:** A mock gives the answer that the test writer expected. A schema test proves the
shape of an answer and says nothing about its quality. A prompt is not code, and a test
of it that never calls a model proves nothing.

**How to apply:** The tests stay free of the network. The live check is a script in the
scratchpad that a person runs and reads. Put what it showed in the session log, because
the next session cannot see the output.

## A test that was offline can go online when you wire a route

**Date:** 2026-09-20. **Session:** 09.

**What happened:** The webhook route got the call to the intake loop. The tests of that
route were written when the route only wrote a log line, so they had no fake model and
no fake Recall. The first run after the wire sent a real request to `api.openai.com`.
The tests still "passed" the earlier sessions, so nothing said that the rule was broken.

**The rule:** After you connect a route to a service, run the full suite with each
socket refused. A test file that was offline because its route did nothing is not
offline after the route does something.

**Why:** The no-network rule is a property of the whole suite, not of one test file. A
route is where the rule breaks, because a route gains callers and the tests of it do
not change at the same time.

**How to apply:** A pytest plugin that makes `socket.socket.connect`,
`socket.socket.connect_ex` and `socket.create_connection` raise is 10 lines. Keep it in
the scratchpad and run `poetry run pytest -p block_network` after each change to a
route. Put the result in the session log.
