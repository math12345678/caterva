"""The verdict must read a search's results, not only a ProvenancedModel's.

Reported 2026-09-24 by running the checklist: for rabbit LDH the table said
"3 of 3 constant(s) came from the literature", each with a BRENDA ref, and
the verdict at the top of the same page said "all 3 rate constant(s) are
the motif library's illustrative values ... none has been run". The verdict
only recognised provenance on objects with a `placeholders` attribute; a
`ComposedModel` after `with_measured` carries a mapping instead.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Tuple

from Terium.compose.verdict import _grounding, _provenance_concerns


@dataclass
class Searched:
    """The shape of a ComposedModel after `with_measured`: no `placeholders`."""

    measured: Dict[str, Any]
    unmeasured: Tuple[str, ...]
    subject: str = "1.1.1.27"
    not_found: Dict[str, str] = field(default_factory=dict)
    resolvable: Tuple[Any, ...] = ()

    @property
    def searched(self) -> bool:
        return bool(self.measured) or bool(self.not_found)


def test_a_fully_sourced_model_counts_as_measured() -> None:
    model = Searched(measured={"Km": 1, "Ki": 2, "kcat": 3}, unmeasured=())
    assert _grounding(model) == (3, 0, True)
    concerns, note = _provenance_concerns(model)
    assert concerns == []
    assert "3 constant(s) measured" in note


def test_a_partial_result_is_not_called_unsearched() -> None:
    model = Searched(measured={"Km": 1, "Ki": 2}, unmeasured=("kcat",))
    concerns, note = _provenance_concerns(model)
    assert "2 measured, 1 unmeasured" == note
    assert "none has been run" not in concerns[0].detail


def test_a_search_that_found_nothing_says_it_searched() -> None:
    model = Searched(measured={}, unmeasured=("Km", "Ki", "kcat"),
                     not_found={"Km": "no value in the organism requested"})
    concerns, _ = _provenance_concerns(model)
    assert "found nothing it could use" in concerns[0].detail
    assert "--organism" in concerns[0].remedy
