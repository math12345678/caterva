"""The catalogue, rebuilt as data.

Every model `model_building.py` emits from a hand-written function is
constructed here as a `ReactionNetwork` instead. Nothing new is modelled:
these are the same systems with the same constants, expressed through the IR
so that the IR has to be adequate rather than merely plausible.

That is the point of this module. A general representation is easy to
believe in and easy to get subtly wrong, and the cheapest way to find out is
to make it reproduce work that already exists and is already tested.
`caterva/tests/test_network_equivalence.py` integrates the hand-written
builder and the compiled network side by side and requires the trajectories
to agree exactly -- measured, they agree to 0.0, not to a tolerance.

WHAT THIS BUYS
--------------
The builders stay. They are not deprecated by this and nothing here asks a
caller to stop using them; `simulate_michaelis_menten` is a better API for
Michaelis-Menten than assembling a network by hand, and it should remain.

What changes is that they stop being the ONLY way to reach the engine. A
system nobody wrote a builder for is now expressible, and arrives with the
same three guarantees the catalogue had: its rate laws are checked against
its own declarations, its quantities are enumerable so the provenance rule
can be applied to them, and its conservation laws are derived from its
stoichiometry rather than asserted by whoever wrote the test.

A NOTE ON THE TWO SHAPES
------------------------
Four of these are reaction networks and three are rate-rule systems, and
that split is not incidental. Michaelis-Menten and the compartmental models
are naturally transformations between pools. Lotka-Volterra's predation
term, Tyson's relaxation oscillator and the repressilator's Hill functions
are not sums of mass-action reactions and are written in the literature as
differential equations, so they are represented as rate rules here.

An IR that handled only reactions would have covered four of seven and left
the interesting three behind -- which is how a general abstraction ends up
general only over the easy cases.
"""

from __future__ import annotations


def _package_path_missing(exc: ModuleNotFoundError) -> bool:
    """See caterva/core/import_mode.py. Inlined deliberately: this
    guards the import machinery itself, so it cannot import a
    helper to do its job."""
    name = getattr(exc, "name", None)
    return bool(name) and (name == "caterva" or name.startswith("caterva."))


try:
    from caterva.core.network import (
        AssignmentRule,
        Parameter,
        RateRule,
        Reaction,
        ReactionNetwork,
        Species,
    )
except ModuleNotFoundError as _exc:  # flat mode: caterva/ on sys.path
    if not _package_path_missing(_exc):
        # A missing THIRD-PARTY dependency. Flat mode cannot fix it, and
        # retrying replaces the real reason with a confusing
        # 'No module named core'. See caterva/core/import_mode.py.
        raise
    from core.network import (  # type: ignore[no-redef]
        AssignmentRule,
        Parameter,
        RateRule,
        Reaction,
        ReactionNetwork,
        Species,
    )


def mm_network(
    km: float, vmax: float, s0: float, name: str = "michaelis_menten"
) -> ReactionNetwork:
    """Irreversible single-substrate Michaelis-Menten: S -> P.

    Derived conservation law: S + P. The substrate is not destroyed, it
    becomes product -- which is exactly what the hand-written test for this
    domain asserts, and here it falls out of the stoichiometry.
    """
    return ReactionNetwork(
        name=name,
        species=(Species("S", s0), Species("P", 0.0)),
        parameters=(Parameter("Vmax", vmax), Parameter("Km", km)),
        reactions=(
            Reaction("J0", {"S": 1}, {"P": 1}, "Vmax * S / (Km + S)"),
        ),
    )


def mm_competitive_network(
    km: float,
    vmax: float,
    ki: float,
    s0: float,
    i: float,
    name: str = "mm_competitive_inhibition",
) -> ReactionNetwork:
    """Michaelis-Menten with a competitive inhibitor.

    `I` is a parameter, not a species: the inhibitor is not consumed, and
    the hand-written builder holds it fixed too. Modelling it as a species
    would let it appear in a conservation law it has no business in.
    """
    return ReactionNetwork(
        name=name,
        species=(Species("S", s0), Species("P", 0.0)),
        parameters=(
            Parameter("Vmax", vmax),
            Parameter("Km", km),
            Parameter("Ki", ki),
            Parameter("I", i),
        ),
        reactions=(
            Reaction(
                "J0", {"S": 1}, {"P": 1}, "Vmax * S / (Km * (1 + I / Ki) + S)"
            ),
        ),
    )


__all__ = [
    "mm_network",
    "mm_competitive_network",
]
