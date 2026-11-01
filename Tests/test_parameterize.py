"""Whole-model parameterization: resolve everything, then judge the set.

The case worth testing is not the one that fails loudly. It is the one
where every quantity resolved, every citation is real, and the model is
still wrong because the values were measured in different organisms under
different conditions. That is what `usable` distinguishes from `complete`,
and it is the distinction this file exists to pin.
"""

from __future__ import annotations

import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from model_compatibility import ParameterSource  # noqa: E402
from parameterize import (  # noqa: E402
    ParameterRequest,
    Resolution,
    parameterize,
    requests_for_network,
)

HUMAN = "Homo sapiens"
ECOLI = "Escherichia coli"


def _resolver(table):
    """A resolver built from a fixed table, recording what it was asked."""
    asked = []

    def resolve(request: ParameterRequest) -> Resolution:
        asked.append(request.quantity)
        entry = table.get(request.quantity)
        if entry is None:
            return Resolution(request=request, reason="no entry in BRENDA")
        return Resolution(request=request, source=entry)

    resolve.asked = asked  # type: ignore[attr-defined]
    return resolve


CLEAN = {
    "km": ParameterSource("km", 6.0, "mM", organism=HUMAN, ph=7.4,
                          temperature_c=37.0, buffer="HEPES"),
    "kcat": ParameterSource("kcat", 118.0, "1/s", organism=HUMAN, ph=7.4,
                            temperature_c=37.0, buffer="HEPES"),
}

SCAVENGED = {
    "km": ParameterSource("km", 6.0, "mM", organism=HUMAN, ph=7.4,
                          temperature_c=37.0, buffer="HEPES"),
    "kcat": ParameterSource("kcat", 118.0, "1/s", organism=ECOLI, ph=6.0,
                            temperature_c=25.0, buffer="phosphate",
                            cross_species=True),
}


def test_a_clean_model_is_complete_and_usable() -> None:
    report = parameterize(
        [ParameterRequest("km"), ParameterRequest("kcat")], _resolver(CLEAN)
    )
    assert report.complete
    assert report.usable
    assert "can be simulated as it stands" in report.summary()


def test_the_case_that_looks_most_like_success() -> None:
    """Complete, every citation real, and not usable.

    This is the failure a researcher would ship. Every parameter resolved;
    nothing is missing; each value has a genuine BRENDA entry. The model
    still describes no enzyme, because km is human at pH 7.4 / 37 C and
    kcat is E. coli at pH 6.0 / 25 C.
    """
    report = parameterize(
        [ParameterRequest("km"), ParameterRequest("kcat")],
        _resolver(SCAVENGED),
    )
    assert report.complete, "both values were found"
    assert not report.usable, "and the set does not hold together"
    kinds = {f.kind for f in report.compatibility.findings}
    assert "organism_mismatch" in kinds
    assert "temperature_mismatch" in kinds
    assert "most resembles success" in report.summary()


def test_a_gap_is_named_with_the_resolver_s_own_reason() -> None:
    report = parameterize(
        [ParameterRequest("km"), ParameterRequest("ki")], _resolver(CLEAN)
    )
    assert not report.complete
    assert [r.request.quantity for r in report.missing] == ["ki"]
    # The resolver's words, not a paraphrase: "no BRENDA entry" and
    # "found, in a rabbit" are different facts to act on.
    assert "no entry in BRENDA" in report.summary()
    assert "does not fill them in" in report.summary()


def test_it_asks_for_every_quantity_before_judging_any() -> None:
    """Order is the interesting failure.

    Judging compatibility incrementally would report a coherent model on
    partial data -- true of the first value and meaningless about the
    model. This pins that assessment happens once, after everything.
    """
    resolve = _resolver(SCAVENGED)
    report = parameterize(
        [ParameterRequest("km"), ParameterRequest("kcat")], resolve
    )
    assert resolve.asked == ["km", "kcat"]
    # The finding spans both quantities, which is only possible if both
    # had returned before the judgement ran.
    mismatch = next(
        f for f in report.compatibility.findings
        if f.kind == "temperature_mismatch"
    )
    assert set(mismatch.quantities) == {"km", "kcat"}


def test_nothing_resolving_is_reported_rather_than_crashing() -> None:
    report = parameterize([ParameterRequest("km")], _resolver({}))
    assert not report.complete
    # Vacuously coherent -- there is nothing to be incompatible with -- and
    # `usable` must still be False, because the model has no parameters.
    assert report.compatibility.coherent
    assert not report.usable


class TestRequestsForNetwork:
    def test_it_builds_requests_from_a_model_s_own_quantity_list(self) -> None:
        # Pairs with ReactionNetwork.quantity_ids(), so a constructed model
        # needs nobody to re-type what it requires.
        requests = requests_for_network(
            ["S", "P", "Vmax", "Km"], subject="hexokinase", organism=HUMAN
        )
        assert [r.quantity for r in requests] == ["S", "P", "Vmax", "Km"]
        assert all(r.subject == "hexokinase" for r in requests)
        assert all(r.organism == HUMAN for r in requests)

    def test_skip_leaves_out_what_the_caller_already_has(self) -> None:
        # Scenario choices and the user's own bench values: no literature
        # search could supply them and asking would waste a lookup.
        requests = requests_for_network(
            ["S", "P", "Vmax", "Km", "end"], skip=["S", "P", "end"]
        )
        assert [r.quantity for r in requests] == ["Vmax", "Km"]
