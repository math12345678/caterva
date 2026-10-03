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

from caterva.agents.adapters import to_parameter_source
from caterva.compose.verdict import _provenance_concerns


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
    from caterva.compose.__main__ import _search_the_literature
    from caterva.compose.pipeline import compose

    model = compose("Michaelis Menten", subject="2.7.1")
    args = SimpleNamespace(subject="2.7.1", organism="Homo sapiens",
                           substrate="glucose")
    _, note, refused = _search_the_literature(model, args)
    assert refused
    assert "incomplete EC number" in note and "2.7.1.1" in note


def test_a_gene_circuit_is_not_told_to_name_an_enzyme() -> None:
    from caterva.compose.pipeline import compose

    concerns, _ = _provenance_concerns(compose("two genes repressing each other"))
    assert "name the enzyme" not in concerns[0].remedy
    # Why an enzyme does not apply is said once, in the detail; the remedy
    # does not then tell the reader the thing it asked for is pointless.
    assert "not kept in an enzyme database" in concerns[0].detail
    assert "would not find" not in concerns[0].remedy
    assert "enzyme database" not in concerns[0].remedy
    assert "no enzyme was named" not in concerns[0].detail


def test_an_enzyme_shape_still_is() -> None:
    from caterva.compose.pipeline import compose

    concerns, _ = _provenance_concerns(compose("Michaelis Menten"))
    assert concerns[0].remedy.startswith("name the enzyme")


def test_a_toggle_switch_says_why_no_enzyme_applies_once_and_does_not_contradict_itself() -> None:
    """The verdict said "because no enzyme was named" and then that naming one
    would not find anything. A mechanism with no enzyme step says why an enzyme
    does not apply in one place, and its remedy is the one thing left to do."""
    from caterva.compose.pipeline import compose
    from caterva.compose.report import dossier

    model = compose("a toggle switch")
    concerns, note = _provenance_concerns(model)
    detail, remedy = concerns[0].detail, concerns[0].remedy
    assert "no enzyme step" in detail and "not kept in an enzyme database" in detail
    assert "no enzyme was named" not in detail
    assert "name the enzyme" not in remedy and "naming an enzyme" not in remedy
    assert remedy.startswith("supply the constants the provenance table lists")
    text = "\n".join(str(part) for part in (detail, remedy))
    assert text.count("enzyme database") == 1
    report = dossier("a toggle switch", analyse_stability=False, simulate=False, rank_unmeasured=False)
    markdown = report.markdown()
    assert "because no enzyme was named" not in markdown
    assert "no enzyme step" in markdown
