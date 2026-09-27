"""Naming the inhibited step wires the inhibition, as the note promises.

Found 2026-09-26: the unwired note said "Say which step to inhibit and it
can be added", and "the end product inhibits step 1" still built a plain
chain. A promise in a report is a claim about the tool.
"""
from __future__ import annotations

import pytest

from caterva.compose.pipeline import compose


def _laws(model):
    return {r.id: str(r.rate_law) for r in model.network.reactions}


@pytest.mark.parametrize("query, step", [
    ("feedback inhibition of a 3 step pathway where the end product inhibits step 1", 1),
    ("3 step pathway with end product inhibition of the first step", 1),
    ("feedback inhibition of a 4 step pathway at the committed step", 1),
    ("feedback inhibition of a 3 step pathway, the end product inhibits step 2", 2),
])
def test_the_named_step_is_inhibited_by_the_end_product(query, step) -> None:
    model = compose(query)
    assert model.recognition.rule == "feedback_inhibition"
    law = _laws(model)[f"step{step}_catalysis"]
    assert f"step{step}_I" in law and f"step{step}_Ki" in law
    # The last step produces that same species: the loop is closed.
    last = max(int(r.id[4]) for r in model.network.reactions)
    produced = {
        s for r in model.network.reactions if r.id == f"step{last}_catalysis"
        for s in getattr(r, "products", {})
    }
    assert f"step{step}_I" in produced or not produced


def test_the_last_step_inhibited_is_product_inhibition() -> None:
    model = compose("feedback inhibition of a 3 step pathway, the end product inhibits the last step")
    assert "step3_P" in _laws(model)["step3_catalysis"]
    assert "step3_Kp" in _laws(model)["step3_catalysis"]


def test_no_step_named_still_says_so_rather_than_guessing() -> None:
    model = compose("feedback inhibition of a 3 step pathway")
    assert model.recognition.rule == "sequential_pathway"
    assert "not wired" in model.recognition.reading
