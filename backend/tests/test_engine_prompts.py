"""Tests of the prompt module.

CLAUDE.md says that all prompt text is in `prompts.py`. The last test holds that
rule: it reads the other engine modules and refuses a long string literal.
"""

import ast
from pathlib import Path

import pytest

from app.engine import prompts

# The modules that must hold no prompt text and no mode word.
ENGINE_MODULES = ("intake.py", "summary.py", "loop.py")

# A string literal longer than this in a module that is not `prompts.py` is
# prompt text that moved out of place.
MAX_LITERAL = 80


def _module_source(name: str) -> str:
    return (Path(__file__).parent.parent / "app" / "engine" / name).read_text()


def _docstring_ids(tree: ast.Module) -> set[int]:
    """Give the id() of each docstring node, which is not prompt text."""
    ids = set()
    for node in ast.walk(tree):
        if not isinstance(
            node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef
        ):
            continue
        first = node.body[0] if node.body else None
        if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
            ids.add(id(first.value))
    return ids


def test_the_intake_prompt_takes_the_turn_limit() -> None:
    text = prompts.intake_system(6)

    assert "6 questions" in text
    # `substitute` raises for a placeholder that the builder does not give.
    assert "$" not in text


def test_the_intake_prompt_refuses_a_diagnosis() -> None:
    text = prompts.intake_system(6)

    assert "not a physician" in text
    assert "Do not give a diagnosis" in text


def test_the_intake_prompt_says_to_use_each_question() -> None:
    # The live check showed a model that stopped with a question unused and
    # left a field empty.
    assert "Use each of your questions" in prompts.intake_system(6)


def test_the_two_prompts_have_the_same_red_flags() -> None:
    # A red flag in the intake must be a red flag in the summary.
    assert prompts.RED_FLAGS in prompts.intake_system(6)
    assert prompts.RED_FLAGS in prompts.SUMMARY_SYSTEM


def test_the_summary_prompt_refuses_an_invented_red_flag() -> None:
    # The live check showed a model that made "the worst headache of my life"
    # from "really bad headaches". This is the worst failure of this demo.
    text = prompts.SUMMARY_SYSTEM

    assert "Do not make a red flag from words that are only near to one" in text
    assert "no red flag was reported" in text
    assert "do\n   not make the words of the patient stronger" in text


def test_the_summary_prompt_asks_for_a_red_flag_that_the_patient_gave() -> None:
    # The first fix made the opposite fault: a patient gave three red flags and
    # the summary said that there were none.
    text = prompts.SUMMARY_SYSTEM

    assert "RED FLAG:" in text
    assert "Do not leave one out" in text


def test_the_summary_prompt_keeps_the_empty_words_out_of_a_full_field() -> None:
    # The live check showed a model that put the words inside an answer.
    assert "Never put these words in a field that has an answer" in prompts.SUMMARY_SYSTEM


def test_the_summary_prompt_refuses_a_red_flag_that_is_not_one() -> None:
    # The live check showed a model that called nausea a red flag.
    assert "They are not red flags" in prompts.SUMMARY_SYSTEM


def test_the_summary_prompt_names_each_field() -> None:
    for field in prompts.SUMMARY_FIELDS:
        assert field in prompts.SUMMARY_SYSTEM


def test_the_summary_prompt_gives_the_words_for_a_field_with_no_answer() -> None:
    assert prompts.NOT_DISCUSSED in prompts.SUMMARY_SYSTEM


def test_the_two_prompts_are_not_the_same() -> None:
    assert prompts.intake_system(6) != prompts.SUMMARY_SYSTEM


@pytest.mark.parametrize("schema", [prompts.INTAKE_SCHEMA, prompts.SUMMARY_SCHEMA])
def test_each_schema_can_be_strict(schema: dict) -> None:
    # Strict mode needs each property in `required`, and no other property.
    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(schema["properties"])


def test_the_summary_schema_has_the_eight_fields() -> None:
    assert len(prompts.SUMMARY_FIELDS) == 8
    assert tuple(prompts.SUMMARY_SCHEMA["properties"]) == prompts.SUMMARY_FIELDS


def test_the_intake_schema_has_the_two_actions() -> None:
    assert prompts.INTAKE_SCHEMA["properties"]["action"]["enum"] == ["ask", "complete"]


@pytest.mark.parametrize("name", ENGINE_MODULES)
def test_no_prompt_text_is_in_another_module(name: str) -> None:
    tree = ast.parse(_module_source(name))
    docstrings = _docstring_ids(tree)

    long_literals = [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
        and len(node.value) > MAX_LITERAL
    ]

    assert long_literals == []


@pytest.mark.parametrize("name", ("prompts.py", *ENGINE_MODULES))
@pytest.mark.parametrize("word", ("chat", "voice"))
def test_the_engine_names_no_mode(name: str, word: str) -> None:
    # The engine must operate for each mode. `llm.py` is not here, because the
    # OpenAI endpoint itself is named "chat completions".
    assert word not in _module_source(name).lower()
