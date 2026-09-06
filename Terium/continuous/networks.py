"""The catalogue, rebuilt as data.

Every model `model_building.py` emits from a hand-written function is
constructed here as a `ReactionNetwork` instead. Nothing new is modelled:
these are the same systems with the same constants, expressed through the IR
so that the IR has to be adequate rather than merely plausible.

That is the point of this module. A general representation is easy to
believe in and easy to get subtly wrong, and the cheapest way to find out is
to make it reproduce work that already exists and is already tested.
`Terium/tests/test_network_equivalence.py` integrates the hand-written
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
    """See Terium/core/import_mode.py. Inlined deliberately: this
    guards the import machinery itself, so it cannot import a
    helper to do its job."""
    name = getattr(exc, "name", None)
    return bool(name) and (name == "Terium" or name.startswith("Terium."))


try:
    from Terium.core.network import (
        AssignmentRule,
        Parameter,
        RateRule,
        Reaction,
        ReactionNetwork,
        Species,
    )
except ModuleNotFoundError as _exc:  # flat mode: Terium/ on sys.path
    if not _package_path_missing(_exc):
        # A missing THIRD-PARTY dependency. Flat mode cannot fix it, and
        # retrying replaces the real reason with a confusing
        # 'No module named core'. See Terium/core/import_mode.py.
        raise
    from core.network import (  # type: ignore[no-redef]
        AssignmentRule,
        Parameter,
        RateRule,
        Reaction,
        ReactionNetwork,
        Species,
    )

try:
    from Terium.continuous.model_building import (
        GAMMA_PARAM,
        REPRESSILATOR_ALPHA,
        REPRESSILATOR_ALPHA0,
        REPRESSILATOR_BETA,
        REPRESSILATOR_N,
        TYSON_K4,
        TYSON_K4PRIME,
        TYSON_K6,
        TYSON_KAPPA,
    )
except ModuleNotFoundError as _exc:
    if not _package_path_missing(_exc):
        raise
    from continuous.model_building import (  # type: ignore[no-redef]
        GAMMA_PARAM,
        REPRESSILATOR_ALPHA,
        REPRESSILATOR_ALPHA0,
        REPRESSILATOR_BETA,
        REPRESSILATOR_N,
        TYSON_K4,
        TYSON_K4PRIME,
        TYSON_K6,
        TYSON_KAPPA,
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


def sir_network(
    beta: float,
    gamma: float,
    s0: float,
    i0: float,
    r0_recovered: float = 0.0,
    name: str = "sir",
) -> ReactionNetwork:
    """Frequency-dependent SIR: dS/dt = -beta*S*I/N.

    Derived conservation law: S + I + R. Nobody tells this model that
    epidemics conserve people; it follows from every reaction moving one
    individual from one compartment to another.

    The recovery-rate parameter is emitted as `gamma_rate` because Antimony
    resolves the bare name `gamma` to the gamma FUNCTION. The IR rejects
    `gamma` as an identifier for that reason, so this cannot be got wrong
    silently the way it once was.
    """
    n = s0 + i0 + r0_recovered
    return ReactionNetwork(
        name=name,
        species=(
            Species("S", s0),
            Species("I", i0),
            Species("R", r0_recovered),
        ),
        parameters=(
            Parameter("beta", beta),
            Parameter(GAMMA_PARAM, gamma),
            Parameter("N", n),
        ),
        reactions=(
            Reaction("J0", {"S": 1}, {"I": 1}, "beta * S * I / N"),
            Reaction("J1", {"I": 1}, {"R": 1}, f"{GAMMA_PARAM} * I"),
        ),
    )


def seir_network(
    beta: float,
    sigma: float,
    gamma: float,
    s0: float,
    e0: float,
    i0: float,
    r0_recovered: float = 0.0,
    name: str = "seir",
) -> ReactionNetwork:
    """SEIR with an explicit latent compartment.

    Derived conservation law: S + E + I + R.
    """
    n = s0 + e0 + i0 + r0_recovered
    return ReactionNetwork(
        name=name,
        species=(
            Species("S", s0),
            Species("E", e0),
            Species("I", i0),
            Species("R", r0_recovered),
        ),
        parameters=(
            Parameter("beta", beta),
            Parameter("sigma", sigma),
            Parameter(GAMMA_PARAM, gamma),
            Parameter("N", n),
        ),
        reactions=(
            Reaction("J0", {"S": 1}, {"E": 1}, "beta * S * I / N"),
            Reaction("J1", {"E": 1}, {"I": 1}, "sigma * E"),
            Reaction("J2", {"I": 1}, {"R": 1}, f"{GAMMA_PARAM} * I"),
        ),
    )


def lotka_volterra_network(
    alpha: float,
    beta: float,
    gamma: float,
    delta: float,
    p0: float,
    v0: float,
    name: str = "lotka_volterra",
) -> ReactionNetwork:
    """Predator-prey, as the two differential equations the model is.

    Written with rate rules rather than reactions. Prey growth `alpha * P`
    is not a transformation of anything into prey, and predation converts
    prey into predators at a different rate than it removes them
    (`beta != gamma`), so this is not a stoichiometric system. Forcing it
    into reactions would misstate the model.

    Consequently it has NO derived conservation law, and that is correct:
    predator-prey populations are not conserved. `conservation_laws`
    returns an empty list because a rate rule can change its species by any
    amount, which is represented honestly in the stoichiometry matrix
    rather than assumed away.
    """
    return ReactionNetwork(
        name=name,
        species=(Species("P", p0), Species("V", v0)),
        parameters=(
            Parameter("alpha", alpha),
            Parameter("beta", beta),
            Parameter(GAMMA_PARAM, gamma),
            Parameter("delta", delta),
        ),
        rate_rules=(
            RateRule("P", "alpha * P - beta * P * V"),
            RateRule("V", f"{GAMMA_PARAM} * P * V - delta * V"),
        ),
    )


def cell_cycle_oscillator_network(
    name: str = "cell_cycle_oscillator",
) -> ReactionNetwork:
    """Tyson (1991) two-variable cdc2-cyclin relaxation oscillator.

    No caller-supplied parameters, matching the builder: the constants are
    the literature's own oscillatory set. Uses both rule kinds -- `alpha`
    is a derived constant and `cyclin_fraction` is a reported output, and
    neither is state.
    """
    return ReactionNetwork(
        name=name,
        species=(Species("u", 0.0), Species("v", 0.0)),
        parameters=(
            Parameter("kappa", TYSON_KAPPA),
            Parameter("k6", TYSON_K6),
            Parameter("k4", TYSON_K4),
            Parameter("k4prime", TYSON_K4PRIME),
        ),
        rate_rules=(
            RateRule("u", "k4 * (v - u) * (alpha + u^2) - k6 * u"),
            RateRule("v", "kappa - k6 * u"),
        ),
        assignment_rules=(
            AssignmentRule("alpha", "k4prime / k4"),
            AssignmentRule("cyclin_fraction", "v - u"),
        ),
    )


def repressilator_network(name: str = "repressilator") -> ReactionNetwork:
    """Elowitz & Leibler (2000) synthetic oscillator: three genes, cyclic
    repression.

    Six rate rules in the paper's p.337 dimensionless form. The Hill terms
    `alpha / (1 + p^n)` are why this is a rate-rule system: repression is
    not a reaction that consumes the repressor.
    """
    return ReactionNetwork(
        name=name,
        species=(
            Species("m1", 0.0),
            Species("m2", 0.0),
            Species("m3", 0.0),
            Species("p1", 1.0),
            Species("p2", 2.0),
            Species("p3", 3.0),
        ),
        parameters=(
            Parameter("alpha", REPRESSILATOR_ALPHA),
            Parameter("alpha0", REPRESSILATOR_ALPHA0),
            Parameter("beta", REPRESSILATOR_BETA),
            Parameter("n", REPRESSILATOR_N),
        ),
        rate_rules=(
            RateRule("m1", "-m1 + alpha / (1 + p3^n) + alpha0"),
            RateRule("m2", "-m2 + alpha / (1 + p1^n) + alpha0"),
            RateRule("m3", "-m3 + alpha / (1 + p2^n) + alpha0"),
            RateRule("p1", "-beta * (p1 - m1)"),
            RateRule("p2", "-beta * (p2 - m2)"),
            RateRule("p3", "-beta * (p3 - m3)"),
        ),
    )


__all__ = [
    "mm_network",
    "mm_competitive_network",
    "sir_network",
    "seir_network",
    "lotka_volterra_network",
    "cell_cycle_oscillator_network",
    "repressilator_network",
]
