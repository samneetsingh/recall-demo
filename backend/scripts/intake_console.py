"""Drive a full intake in the terminal. No Recall, no Meet call, no webhook.

Run it from `backend/`:

    poetry run python scripts/intake_console.py

It uses the real state machine, the real database and the real model. You are
the patient. `ConsoleMode` is a third implementation of the same protocol that
chat mode and voice mode will implement, so this exercises the turn boundary
and not a copy of it.

Each run gets a new database file in a temporary directory.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

# `app.config` reads the environment at its import, so this must come first.
os.environ.setdefault(
    "DB_PATH",
    str(Path(tempfile.mkdtemp(prefix="intake-console-")) / "console.sqlite3"),
)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings  # noqa: E402  The import must follow the lines above.
from app.db import session_store  # noqa: E402
from app.engine import loop  # noqa: E402
from app.engine.intake import turn_count  # noqa: E402
from app.modes.base import MODES  # noqa: E402

CONSOLE_URL = "https://meet.google.com/console-driver"


class ConsoleMode:
    """The turn boundary, implemented for a terminal."""

    def handle_incoming_turn(self, session_id: str, raw_event: object) -> str | None:
        return str(raw_event).strip() or None

    def send_outgoing_turn(self, session_id: str, text: str) -> None:
        print(f"\n  ASSISTANT  {text}")
        # Google Meet refuses a chat message of more than 500 characters.
        if len(text) > 500:
            print(f"  [warning] {len(text)} characters. Google Meet permits 500.")


def _report(session_id: str) -> int:
    """Print the result. Give the exit code."""
    session = session_store.get_session(session_id)
    log = session_store.get_turns(session_id)
    print(f"\n{'-' * 70}")
    print(f"status {session.status if session else 'gone'}, {turn_count(log)} turns, {len(log)} rows")

    if session is None:
        return 1
    if session.status == "error":
        print(f"reason: {session.error_reason}")
        return 1
    if session.summary:
        print("\nsummary")
        print(json.dumps(session.summary, indent=2))
    return 0


def main() -> int:
    if not settings.OPENAI_API_KEY:
        print("no OPENAI_API_KEY. Put one in backend/.env")
        return 1

    # Chat mode does not exist until section 5 of docs/TASKS.md. The registry
    # is how a mode arrives, so the driver uses the same door.
    MODES["chat"] = ConsoleMode()

    session_store.init_db()
    session = session_store.create_session(CONSOLE_URL)
    session_store.set_status(session.id, "in_progress")

    print(f"session {session.id}")
    print(f"model {settings.OPENAI_MODEL}, limit {settings.INTAKE_MAX_TURNS} turns")
    print("Answer as the patient. Ctrl-C stops.")
    print("-" * 70)

    loop.start_intake(session.id)

    while True:
        current = session_store.get_session(session.id)
        if current is None or current.status != "in_progress":
            break
        try:
            answer = input("\n  PATIENT    ")
        except (EOFError, KeyboardInterrupt):
            print("\nstopped")
            return _report(session.id)
        turns = turn_count(session_store.get_turns(session.id))
        loop.run_turn(session.id, answer, event_id=f"console-{turns}")

    return _report(session.id)


if __name__ == "__main__":
    raise SystemExit(main())
