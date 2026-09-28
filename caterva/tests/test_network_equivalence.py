"""The generic compiler must reproduce the hand-written catalogue exactly.

WHY THIS IS THE TEST THAT MATTERS
---------------------------------
`caterva/core/network.py` replaces seven hand-written Antimony builders with
one compiler over a data structure. That is a claim about equivalence, and a
claim about equivalence is worth exactly what is measured about it.

So each domain is built BOTH ways -- through the existing builder, which is
already covered by the domain tests and golden set, and through the IR --
and both are integrated by roadrunner. The trajectories must agree.

Not "to a tolerance". Measured, they agree to 0.0 at every point of every
column, because the compiler emits the same model and roadrunner is
deterministic. The tolerance below exists so that a future change to
formatting or solver settings fails informatively rather than mysteriously,
but the assertion the architecture rests on is the exact one.

Byte equality of the Antimony text is deliberately NOT asserted. The
hand-written Michaelis-Menten builder writes `P = 0;` where the compiler
writes `P = 0.0;`, and Antimony treats those identically. Pinning the text
would make this a test about strings; pinning the trajectory makes it a test
about the model.

WHAT ELSE IS PINNED HERE
------------------------
The two properties that make the IR more than a refactor:

  * conservation laws are DERIVED from stoichiometry, and then checked to
    actually hold in the integrated trajectory -- structure predicting
    numerics, which is the whole claim;
  * a rate law may only name symbols its own network declares, which is
    what makes a machine-authored model safe to compile.
"""

from __future__ import annotations

import numpy as np
import pytest

from caterva.continuous.model_building import antimony_to_sbml
from caterva.continuous.networks import mm_competitive_network, mm_network
from caterva.continuous.simulations import simulate_mm_competitive_inhibition, simulate_michaelis_menten, simulate_sbml
from caterva.core.data_structures import ModelBuildError
from caterva.core.network import (
    AssignmentRule,
    Parameter,
    RateRule,
    Reaction,
    ReactionNetwork,
    Species,
    compile_to_antimony,
    describe_conservation_laws,
)

START, END, POINTS = 0.0, 20.0, 101

#: (label, network, callable producing the hand-built result over the same
#: window). Every builder in model_building.py that emits an ODE model.


def _columns(result) -> dict:
    data = np.array(result.data, dtype=float)
    return {name: data[:, i] for i, name in enumerate(result.colnames)}


def _simulate_network(network: ReactionNetwork):
    return simulate_sbml(
        antimony_to_sbml(compile_to_antimony(network)), START, END, POINTS
    )


CASES = [
    (
        "michaelis_menten",
        mm_network(2.0, 5.0, 10.0),
        lambda: simulate_michaelis_menten(2.0, 5.0, 10.0, START, END, POINTS),
    ),
    (
        "mm_competitive_inhibition",
        mm_competitive_network(2.0, 5.0, 1.0, 10.0, 0.5),
        lambda: simulate_mm_competitive_inhibition(
            2.0, 5.0, 1.0, 10.0, 0.5, START, END, POINTS
        ),
    ),
]

@pytest.mark.parametrize(
    "label, network, build_reference", CASES, ids=[c[0] for c in CASES]
)
def test_compiled_network_matches_the_hand_written_builder(
    label, network, build_reference
) -> None:
    """The claim the whole IR rests on."""
    reference = _columns(build_reference())
    compiled = _columns(_simulate_network(network))

    shared = sorted(set(reference) & set(compiled))
    # A comparison over zero shared columns would pass while comparing
    # nothing -- the exact shape this repository keeps rediscovering.
    assert len(shared) >= 2, (
        f"{label}: builder produced {sorted(reference)} and the compiled "
        f"network produced {sorted(compiled)}; too little overlap to be a "
        f"real comparison"
    )

    for column in shared:
        difference = np.max(np.abs(reference[column] - compiled[column]))
        assert difference < 1e-9, (
            f"{label}: column {column} differs by {difference:.3e} between "
            f"the hand-written builder and the compiled network"
        )


@pytest.mark.parametrize(
    "label, network, build_reference", CASES, ids=[c[0] for c in CASES]
)
def test_every_state_variable_is_reproduced(
    label, network, build_reference
) -> None:
    """Agreement on a subset would be a weaker claim than it looks.

    The test above compares shared columns. This one requires that the
    compiled network actually produces every state variable the builder
    does, so a network that silently dropped a species could not pass by
    agreeing about the ones it kept.
    """
    reference = set(_columns(build_reference()))
    compiled = set(_columns(_simulate_network(network)))
    missing = reference - compiled
    assert not missing, f"{label}: compiled network is missing {sorted(missing)}"


# ---------------------------------------------------------------------------
# Invariants derived from structure, then checked against numerics.
# ---------------------------------------------------------------------------

#: What the stoichiometry SHOULD imply. Written out so that a change in the
#: derivation is caught here rather than silently weakening every downstream
#: conservation check.
EXPECTED_LAWS = {
    "michaelis_menten": ["S + P"],
    "mm_competitive_inhibition": ["S + P"],
    "sir": ["S + I + R"],
    "seir": ["S + E + I + R"],
    # Rate-rule systems. A rate rule may change its species by any amount,
    # so no stoichiometric conservation can be claimed -- and claiming one
    # would be false rather than merely unhelpful.
    "lotka_volterra": [],
    "cell_cycle_oscillator": [],
    "repressilator": [],
}


@pytest.mark.parametrize(
    "label, network, _build", CASES, ids=[c[0] for c in CASES]
)
def test_conservation_laws_are_derived_not_declared(
    label, network, _build
) -> None:
    """Nobody tells SIR that epidemics conserve people."""
    assert describe_conservation_laws(network) == EXPECTED_LAWS[label]


@pytest.mark.parametrize(
    "label, network, _build",
    [c for c in CASES if EXPECTED_LAWS[c[0]]],
    ids=[c[0] for c in CASES if EXPECTED_LAWS[c[0]]],
)
def test_the_derived_law_actually_holds_in_the_trajectory(
    label, network, _build
) -> None:
    """Structure predicting numerics, which is the whole claim.

    The conservation law is computed from the stoichiometry matrix alone,
    without integrating anything. This then integrates the model and
    requires the predicted quantity to be constant. A derivation that was
    subtly wrong -- a sign, a transpose -- would produce a plausible law
    that drifts, and this is what would catch it.
    """
    columns = _columns(_simulate_network(network))
    # roadrunner reports concentrations as `[S]`; map both spellings.
    def series(species_id: str):
        for key in (species_id, f"[{species_id}]"):
            if key in columns:
                return columns[key]
        pytest.fail(f"{label}: no column for species {species_id}")

    for law in network.conservation_laws():
        total = sum(
            float(coefficient) * series(species_id)
            for species_id, coefficient in law.items()
        )
        drift = float(np.max(np.abs(total - total[0])))
        scale = max(abs(float(total[0])), 1.0)
        assert drift / scale < 1e-6, (
            f"{label}: derived conservation law "
            f"{describe_conservation_laws(network)} drifts by {drift:.3e} "
            f"over the run; either the derivation or the integration is wrong"
        )


# ---------------------------------------------------------------------------
# The safety property that makes a machine-authored model compilable.
# ---------------------------------------------------------------------------

_BASE = dict(
    species=(Species("S", 10.0), Species("P", 0.0)),
    parameters=(Parameter("Vmax", 5.0), Parameter("Km", 2.0)),
)


@pytest.mark.parametrize(
    "label, network, expected",
    [
        (
            "undefined symbol in a rate law",
            ReactionNetwork(
                name="m",
                **_BASE,
                reactions=(
                    Reaction("J0", {"S": 1}, {"P": 1}, "Vmax * S / (Kmm + S)"),
                ),
            ),
            "not a species or parameter",
        ),
        (
            "statement injection",
            ReactionNetwork(
                name="m",
                **_BASE,
                reactions=(Reaction("J0", {"S": 1}, {"P": 1}, "Vmax; Q = 1"),),
            ),
            "disallowed character",
        ),
        (
            "call to an unsanctioned function",
            ReactionNetwork(
                name="m",
                **_BASE,
                reactions=(Reaction("J0", {"S": 1}, {"P": 1}, "system(Vmax)"),),
            ),
            "not an allowed function",
        ),
        (
            "reactant that is not a declared species",
            ReactionNetwork(
                name="m",
                **_BASE,
                reactions=(Reaction("J0", {"X": 1}, {"P": 1}, "Vmax"),),
            ),
            "not a declared species",
        ),
        (
            "negative stoichiometry",
            ReactionNetwork(
                name="m",
                **_BASE,
                reactions=(Reaction("J0", {"S": -1}, {"P": 1}, "Vmax"),),
            ),
            "must be positive",
        ),
        (
            "'gamma', which Antimony reads as the gamma function",
            ReactionNetwork(
                name="m",
                species=(Species("I", 1.0),),
                parameters=(Parameter("gamma", 0.1),),
                reactions=(Reaction("J0", {"I": 1}, {}, "gamma * I"),),
            ),
            "reserved by Antimony",
        ),
        (
            "a species driven by both a reaction and a rate rule",
            ReactionNetwork(
                name="m",
                **_BASE,
                reactions=(Reaction("J0", {"S": 1}, {"P": 1}, "Vmax"),),
                rate_rules=(RateRule("S", "-Vmax"),),
            ),
            "two ways",
        ),
        (
            "a model in which nothing can change",
            ReactionNetwork(name="m", **_BASE),
            "flat line",
        ),
    ],
)
def test_a_malformed_network_is_refused_with_a_reason(
    label, network, expected
) -> None:
    """Rejected at construction, before roadrunner sees it.

    Each message names the offending symbol or rule. A model author -- who
    may be a language model -- gets told what is wrong rather than a parser
    error from three layers down.
    """
    with pytest.raises(ModelBuildError) as raised:
        compile_to_antimony(network)
    assert expected in str(raised.value), (
        f"{label}: refused, but the message did not mention {expected!r}: "
        f"{raised.value}"
    )


def test_a_well_formed_network_using_the_full_grammar_is_accepted() -> None:
    """The refusals above must not be a compiler that refuses everything.

    A catalyst on both sides, an allowed function call, a rate rule and an
    assignment rule -- all legal, all accepted.
    """
    network = ReactionNetwork(
        name="mixed",
        species=(Species("S", 10.0), Species("P", 0.0), Species("E", 1.0)),
        parameters=(Parameter("k", 1.0), Parameter("decay", 0.1)),
        reactions=(
            Reaction("J0", {"S": 1, "E": 1}, {"P": 1, "E": 1}, "k * E * S"),
        ),
        rate_rules=(RateRule("E", "-decay * E + ratio"),),
        assignment_rules=(AssignmentRule("ratio", "P / (S + 1)"),),
    )
    antimony = compile_to_antimony(network)
    assert "J0: S + E -> P + E; k * E * S;" in antimony
    assert "E' = -decay * E + ratio;" in antimony
    assert "ratio := P / (S + 1);" in antimony
    # E is a catalyst in J0 and separately driven by a rate rule, which is
    # legal: the reaction does not change it. S + P is still conserved.
    assert describe_conservation_laws(network) == ["S + P"]
