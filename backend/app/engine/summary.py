"""The summary engine.

It takes the full conversation log and gives the eight fields of the summary.
It is a second call with its own prompt, so a session that stops early can still
give a summary of the part that is complete.
"""

from __future__ import annotations

from app.engine import prompts
from app.engine.llm import ask_model, to_messages


def make_summary(log: list[dict[str, str]]) -> dict[str, str]:
    """Give the eight summary fields for a conversation log."""
    answer = ask_model(
        prompts.SUMMARY_SYSTEM,
        to_messages(log),
        prompts.SUMMARY_SCHEMA,
        "intake_summary",
    )
    return {
        field: str(answer.get(field) or "").strip() or prompts.NOT_DISCUSSED
        for field in prompts.SUMMARY_FIELDS
    }
