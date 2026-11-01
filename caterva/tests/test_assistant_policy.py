"""Questions refused before any model is asked: no payload is built and nothing is sent."""
from __future__ import annotations

import pytest

from caterva.assistant.policy import screen_question

REFUSED = [
    ("What dose of gossypol should I take?", "clinical"),
    ("Is this safe for a patient?", "clinical"),
    ("Could this treat diabetes?", "clinical"),
    ("is it toxic", "clinical"),
    ("What is the Km of lactate dehydrogenase?", "knowledge"),
    ("what is the kcat for hexokinase in yeast", "knowledge"),
    ("Tell me the Ki of gossypol for LDH", "knowledge"),
    ("What are the Vmax values of pyruvate kinase?", "knowledge"),
    ("Run the simulation again with Km = 1", "action"),
    ("delete this run", "action"),
    ("set kcat to 50", "action"),
    ("Please change the Km", "action"),
    ("", "empty"),
    ("   ", "empty"),
    ("x" * 500, "too_long"),
]

ALLOWED = [
    "Why is kcat a placeholder?",
    "Which row did the Km come from?",
    "What is the Km in this run?",
    "What is the Km of this result and where did it come from?",
    "Why does the verdict say structural?",
    "What does the second concern mean?",
    "Which constants are measured here?",
    "How many starting points were tried?",
]


@pytest.mark.parametrize("question,code", REFUSED)
def test_these_are_refused_with_a_reason(question, code):
    refusal = screen_question(question)
    assert refusal is not None and refusal.code == code
    assert refusal.message and "--" not in refusal.message and "—" not in refusal.message


@pytest.mark.parametrize("question", ALLOWED)
def test_questions_about_this_run_pass_the_screen(question):
    assert screen_question(question) is None


def test_the_knowledge_refusal_points_to_the_cited_lookup():
    assert "Constants" in screen_question("What is the Km of hexokinase?").message
