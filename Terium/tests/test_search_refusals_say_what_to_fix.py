"""A search that could not run says what to fix, never "run the search".

Found 2026-09-25 with the inputs a new user gets wrong: an EC number
BRENDA does not have (9.9.9.9) printed a raw HTTP 404 and a verdict saying
"none has been run -- run the literature search"; an incomplete EC number
(2.7.1) was looked up in UniProt as an enzyme NAME; a typo'd substrate
("glucoze") read as "nothing found in BRENDA" while BRENDA held D-glucose.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any, Dict, Optional, Tuple

from Terium.agents.adapters import to_parameter_source
from Terium.compose.verdict import _provenance_concerns


@dataclass
class Refused:
    measured: Dict[str, Any] = field(default_factory=dict)
    unmeasured: Tuple[str, ...] = ("reaction_kcat", "reaction_Km")
    not_found: Dict[str, str] = field(default_factory=dict)
    subject: str = "9.9.9.9"
    search_refused: Optional[str] = "BRENDA has no enzyme 9.9.9.9. Check the EC number"
    resolvable: Tuple[Any, ...] = ()

    @property
    def searched(self) -> bool:
        return False


def test_the_refusal_is_the_remedy() -> None:
    concerns, note = _provenance_concerns(Refused())
    assert "could not run" in concerns[0].detail
    assert concerns[0].remedy.startswith("BRENDA has no enzyme 9.9.9.9")
    assert "run the literature search" not in concerns[0].remedy
    assert "could not run" in note


def test_without_a_refusal_the_old_wording_stands() -> None:
    concerns, _ = _provenance_concerns(Refused(search_refused=None))
    assert "none has been run" in concerns[0].detail


def test_a_misspelt_substrate_lists_what_brenda_has() -> None:
    result = SimpleNamespace(
        found=False, source="not_found",
        cross_species_organisms_available=[],
        substrates_available=["D-glucose", "D-fructose", "D-mannose"],
    )
    source, reason = to_parameter_source("Km", result)
    assert source is None
    assert "D-glucose" in reason and "--substrate" in reason


def test_no_list_means_no_hint() -> None:
    result = SimpleNamespace(
        found=False, source="not_found",
        cross_species_organisms_available=[], substrates_available=[],
    )
    _, reason = to_parameter_source("Km", result)
    assert "--substrate" not in reason


def test_an_incomplete_ec_number_is_named_as_one() -> None:
    from Terium.compose.__main__ import _search_the_literature
    from Terium.compose.pipeline import compose

    model = compose("Michaelis Menten", subject="2.7.1")
    args = SimpleNamespace(subject="2.7.1", organism="Homo sapiens",
                           substrate="glucose")
    _, note, refused = _search_the_literature(model, args)
    assert refused
    assert "incomplete EC number" in note and "2.7.1.1" in note
