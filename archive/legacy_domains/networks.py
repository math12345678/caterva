
# ---- from caterva/continuous/networks.py ----

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


