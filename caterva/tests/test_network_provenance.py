"""Refusal must survive the model becoming open-ended.

Generality is easy and worthless on its own. The reason Caterva is not a
thin SBML wrapper is that it refuses to run a model containing a number
nobody sourced, and the danger in making models arbitrary is that the
refusal quietly stops applying.

It would stop applying in a specific, silent way. On the TypeScript side
provenance entries exist only for keys present in
``DOMAIN_DEFAULTS[domain].parameters``, so a parameter the catalogue never
heard of has no entry -- and a key with no entry is not judged. **Absence
reads as consent.** These tests pin the inversion: for a network, absence
is refusal, and the quantities to judge come from the model itself.
"""

from __future__ import annotations

import pytest

from caterva.continuous.networks import mm_network, sir_network
from caterva.core.data_structures import ModelBuildError
from caterva.core.network import Parameter, Reaction, ReactionNetwork, Species
from caterva.core.network_provenance import (
    BLOCKED_ORIGINS,
    QuantitySource,
    compile_with_provenance,
    provenance_report,
    unsourced_quantities,
)

BRENDA = "BRENDA ref 641068, EC 2.7.1.1, Homo sapiens"


def _fully_sourced(network) -> dict:
    """Every quantity supplied by the user. The honest baseline."""
    return {
        q: QuantitySource(origin="user", note="supplied in this test")
        for q in network.quantity_ids()
    }


def test_a_fully_sourced_network_compiles() -> None:
    network = mm_network(2.0, 5.0, 10.0)
    antimony = compile_with_provenance(network, _fully_sourced(network))
    assert "model michaelis_menten" in antimony


def test_a_quantity_with_no_source_is_refused() -> None:
    """The case a closed catalogue could not see.

    `Km` simply has no entry. Under the per-domain scheme that made it
    invisible to the rule; here it is the reason the model will not run.
    """
    network = mm_network(2.0, 5.0, 10.0)
    sources = _fully_sourced(network)
    del sources["Km"]

    with pytest.raises(ModelBuildError) as raised:
        compile_with_provenance(network, sources)
    assert "Km" in str(raised.value)
    assert "no source recorded" in str(raised.value)


def test_species_initials_are_judged_too_not_only_parameters() -> None:
    """An initial amount is a number like any other.

    `S = 10 mM` is as much an experimental claim as a Km, and a system that
    policed rate constants while waving through initial conditions would be
    checking the half of the model that is easier to check.
    """
    network = mm_network(2.0, 5.0, 10.0)
    sources = _fully_sourced(network)
    del sources["S"]

    with pytest.raises(ModelBuildError) as raised:
        compile_with_provenance(network, sources)
    assert "S" in str(raised.value)


@pytest.mark.parametrize("origin", ["llm", "default"])
def test_blocked_origins_are_refused(origin: str) -> None:
    """The same pair `unverifiedOriginKeys` blocks, enforced in the engine.

    The origins are NAMED here, not read from `BLOCKED_ORIGINS`. A first
    version parametrised over that set and was vacuous: deleting `llm` from
    it deleted the test case rather than failing it, so the check could not
    catch the one change it exists to catch. A test that derives its cases
    from the thing under test asks that thing whether it agrees with itself.
    """
    network = mm_network(2.0, 5.0, 10.0)
    sources = _fully_sourced(network)
    sources["Vmax"] = QuantitySource(origin=origin)

    with pytest.raises(ModelBuildError) as raised:
        compile_with_provenance(network, sources)
    assert "Vmax" in str(raised.value)
    assert origin in str(raised.value)


def test_the_blocked_set_is_exactly_the_pair_the_hard_rule_blocks() -> None:
    """Pinned by name, so widening or narrowing it is a deliberate edit.

    `unverifiedOriginKeys` in provenance.ts blocks `llm` and `default`. Two
    enforcers of one rule that disagree about its content are two rules.
    """
    assert BLOCKED_ORIGINS == {"llm", "default"}


def test_resolved_without_a_citation_is_refused() -> None:
    """A resolved value with nothing to check is asserted, not resolved.

    This repository has found seven of its own citations fabricated or
    pointing at the wrong paper. An origin that claims literature backing
    while naming no literature is the same defect with the evidence field
    left blank.
    """
    network = mm_network(2.0, 5.0, 10.0)
    sources = _fully_sourced(network)
    sources["Km"] = QuantitySource(origin="resolved", citation="   ")

    with pytest.raises(ModelBuildError) as raised:
        compile_with_provenance(network, sources)
    assert "names no citation" in str(raised.value)


def test_resolved_with_a_citation_is_accepted() -> None:
    """The refusals must not be a check that refuses everything."""
    network = mm_network(2.0, 5.0, 10.0)
    sources = _fully_sourced(network)
    sources["Km"] = QuantitySource(origin="resolved", citation=BRENDA)
    assert "model michaelis_menten" in compile_with_provenance(network, sources)


def test_an_unknown_origin_is_refused_rather_than_ignored() -> None:
    """A vocabulary drift between the two enforcers must not pass silently."""
    network = mm_network(2.0, 5.0, 10.0)
    sources = _fully_sourced(network)
    sources["Km"] = QuantitySource(origin="literature")  # not one of the four

    with pytest.raises(ModelBuildError) as raised:
        compile_with_provenance(network, sources)
    assert "unknown origin" in str(raised.value)


def test_a_source_for_a_quantity_the_model_lacks_is_reported() -> None:
    """Usually a rename that landed in one place and not the other.

    Not silently ignored: a value attached to nothing is a value the reader
    believes is backing something.
    """
    network = mm_network(2.0, 5.0, 10.0)
    sources = _fully_sourced(network)
    sources["Ki"] = QuantitySource(origin="user")

    problems = unsourced_quantities(network, sources)
    assert any("Ki" in p and "does not contain" in p for p in problems)


def test_every_problem_is_reported_at_once() -> None:
    """A caller assembling a model wants the whole list.

    Reporting the first failure turns one fix into a sequence of them, and
    a person fixing a model one error at a time stops reading the errors.
    """
    network = sir_network(0.5761, 0.1835, 999.0, 1.0, 0.0)
    problems = unsourced_quantities(network, {})
    # S, I, R, beta, gamma_rate, N -- all six, not just the first.
    assert len(problems) == len(network.quantity_ids()) == 6


def test_the_judged_set_comes_from_the_model_not_from_a_list() -> None:
    """The property that makes this work for a system nobody anticipated.

    A network invented here, matching no domain in the catalogue, is still
    fully judged -- and every one of its quantities is named.
    """
    invented = ReactionNetwork(
        name="something_nobody_wrote_a_builder_for",
        species=(Species("A", 1.0), Species("B", 0.0), Species("C", 0.0)),
        parameters=(Parameter("k_fwd", 0.3), Parameter("k_cat", 1.7)),
        reactions=(
            Reaction("R1", {"A": 1}, {"B": 1}, "k_fwd * A"),
            Reaction("R2", {"B": 1}, {"C": 2}, "k_cat * B"),
        ),
    )
    problems = unsourced_quantities(invented, {})
    named = {p.split(":")[0] for p in problems}
    assert named == {"A", "B", "C", "k_fwd", "k_cat"}


def test_the_report_shows_its_working() -> None:
    network = mm_network(2.0, 5.0, 10.0)
    sources = _fully_sourced(network)
    sources["Km"] = QuantitySource(origin="resolved", citation=BRENDA)

    report = provenance_report(network, sources)
    assert list(report) == list(network.quantity_ids())  # declaration order
    assert report["Km"]["origin"] == "resolved"
    assert report["Km"]["citation"] == BRENDA
    assert report["Vmax"]["origin"] == "user"


def test_a_structurally_invalid_network_is_refused_before_provenance() -> None:
    """Order matters: a model that cannot be built is not a provenance
    problem, and reporting it as one would send the reader to the wrong
    place."""
    broken = ReactionNetwork(
        name="broken",
        species=(Species("S", 1.0),),
        parameters=(Parameter("k", 1.0),),
        reactions=(Reaction("J0", {"S": 1}, {}, "k * MISSING"),),
    )
    with pytest.raises(ModelBuildError) as raised:
        compile_with_provenance(
            broken,
            {
                "S": QuantitySource(origin="user"),
                "k": QuantitySource(origin="user"),
            },
        )
    assert "MISSING" in str(raised.value)
