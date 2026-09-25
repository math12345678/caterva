"""Plain Michaelis-Menten must build, in the words people actually use.

Found 2026-09-24 by trying queries nobody had scripted: "Michaelis Menten",
"michaelis-menten kinetics", "simple enzyme kinetics" and "an enzyme
converting substrate to product" were all refused, while the only enzyme
phrasing that worked was the one the docs used. The motif existed; no rule
reached it.
"""
from __future__ import annotations

import pytest

from Terium.compose.grammar import recognise


@pytest.mark.parametrize("query", [
    "Michaelis Menten",
    "Michaelis-Menten",
    "michaelis-menten kinetics",
    "simple enzyme kinetics",
    "an enzyme converting substrate to product",
    "a single enzyme",
    "an enzyme-catalysed reaction",
    "one catalytic step",
])
def test_plain_enzyme_phrasings_build_michaelis_menten(query: str) -> None:
    assert recognise(query).rule == "michaelis_menten"


@pytest.mark.parametrize("query, rule", [
    # More structure in the words must still reach the rule written for it.
    ("Michaelis-Menten with a competitive inhibitor", "competitive_inhibition"),
    ("reversible michaelis-menten", "reversible_catalysis"),
    ("3 step enzyme cascade", "enzyme_cascade"),
])
def test_a_more_specific_shape_still_wins(query: str, rule: str) -> None:
    assert recognise(query).rule == rule


def test_the_model_asks_the_literature_for_kcat_and_km() -> None:
    from Terium.compose.pipeline import compose

    model = compose("Michaelis Menten", subject="1.1.1.1")
    wanted = {q.parameter_id for q in model.resolvable}
    assert wanted == {"reaction_kcat", "reaction_Km"}
