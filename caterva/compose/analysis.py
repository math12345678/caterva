"""Steady states, stability, and whether a switch actually switches.

WHY A TRAJECTORY IS NOT AN ANSWER
---------------------------------
Caterva can integrate a composed model and draw a curve. For most of the
questions these models are built to answer, that curve is the wrong output.

"Is this toggle switch bistable?" is not answered by one trajectory -- a
bistable system reached from one starting point looks exactly like a
monostable one, and the second stable state is invisible unless you go and
look for it. "How much does this cascade amplify?" is a property of the
steady state, not of the transient. "Does this oscillate?" is decided by the
eigenvalues of the Jacobian, and reading it off a plot means guessing
whether a slow decay is a decay or a very long period.

So this computes what the questions actually ask for: the fixed points, the
Jacobian at each, its eigenvalues, and the classification that follows.

WHAT IS NUMERICAL AND WHAT IS EXACT
-----------------------------------
The stoichiometry and the conservation laws are exact -- they come from
`ReactionNetwork`, over `Fraction`, and this does not recompute them.
Everything here is numerical: a root find from many starting points, a
finite-difference Jacobian, an eigenvalue decomposition.

That difference is reported rather than blurred. A steady state found by a
solver is a state the solver converged to, and the report says so, with its
residual. Presenting a numerical root with the same confidence as a derived
conservation law would be exactly the flattening of evidence this codebase
spends its time undoing.

WHAT IT REFUSES TO CONCLUDE
---------------------------
That it found ALL the fixed points. A multistart root find can only report
what it converged to; the absence of a third state is not evidence there
isn't one, and `states_found` is never called `all_states`. `bistability`
reports "at least two stable states were found", never "this system is
bistable and has exactly two".
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

#: Below this, a residual counts as a converged root.
#:
#: A JUDGEMENT with a reason: species concentrations here are order 1 in
#: whatever unit the model uses, and rates are order 1 per second, so a
#: residual of 1e-9 is nine orders below the quantities involved. Stated as
#: a constant so it can be argued with rather than buried in a comparison.
RESIDUAL_TOLERANCE = 1e-9

#: Two states closer than this in every coordinate are the same state found
#: twice. Root finders from nearby starts converge to slightly different
#: floating-point answers, and reporting those as distinct fixed points
#: would turn one stable state into a dozen.
STATE_DISTINCT_TOLERANCE = 1e-6

#: The engine's own words about the count of points on a line of equilibria. A
#: page that prints "N found from M starts" for such a model must print this
#: beside it: the count is where the starts fell, not a fact about the model.
CONTINUUM_COUNT_CAVEAT = (
    "How many points land on the line is an artefact of where the starts fell, not a property of the model."
)

#: An eigenvalue whose real part is within this of zero is not called stable
#: OR unstable. At a bifurcation the linearisation decides nothing, and
#: rounding a marginal eigenvalue to one side is how a model gets reported
#: as a switch that is actually sitting on the boundary of being one.
MARGINAL_EIGENVALUE = 1e-8

#: Relative step for the finite-difference Jacobian. The usual sqrt(machine
#: epsilon) compromise: smaller loses accuracy to cancellation, larger to
#: truncation.
JACOBIAN_STEP = 1.4901161193847656e-08  # sqrt(2^-52)

#: How many starting points a multistart search uses per species.
#:
#: MEASURED, and re-measured when the measurement changed. The first
#: version of this note said the toggle switch found one of its two stable
#: states at 4 and both at 8. That was true when the search was anchored
#: at order 1 for every model; since `_search_scale` anchors it where the
#: model's concentrations actually are, the toggle finds both at 4.
#:
#: The current table, every model the composer builds, stable states found
#: (and, for the one model on a line of equilibria, points on the line):
#:
#:     depth                      4      8     16     32
#:     ten models with attractors    identical at every depth
#:     two-enzyme competition     0/11   0/19   0/27   0/27
#:
#: Nothing changes from 4 upward except how many points land on the
#: continuum, which is not a property of the model. `sensitivity.py` used
#: to justify a deeper search of its own -- 16 -- by that model reporting
#: "1 stable state at 8 and 2 at 16". Those were continuum points; neither
#: was a stable state, and once they were classified correctly the only
#: evidence for 16 disappeared with them.
#:
#: 8 is kept rather than dropped to 4 because the library is not the
#: world: a user's model with narrower basins gets a margin, at the cost
#: of a root find per extra start. It is not raised to 16 because nothing
#: measured asks for it, and a default that is slow for no measured
#: benefit gets turned down by the first person in a hurry. A caller who
#: needs more passes `starts_per_species`, which every consumer of this
#: module now threads through.
#:
#: `test_the_library_is_depth_independent_from_four` holds this table live,
#: so the next time the search changes the note cannot go stale quietly.
#:
#: This does not make the search exhaustive and nothing here claims it is.
#: See `StabilityReport.at_least_bistable` for what the evidence supports.
DEFAULT_STARTS_PER_SPECIES = 8

STABLE = "stable"
UNSTABLE = "unstable"
SADDLE = "saddle"
MARGINAL = "marginal"
#: One point on a LINE of equilibria: attracting in every direction but
#: one, and along that one the dynamics do not move at all. The system
#: reaches the line and stops; WHERE on the line is decided by the
#: transient, not by the equations at rest.
#:
#: Not `stable`, because it is not an attractor -- a nudge along the line
#: is never undone. Not `marginal`, because that word sends a reader to a
#: bifurcation diagram and this is not a bifurcation; it is a degenerate
#: family that exists at every parameter value. Two enzymes competing for
#: one substrate produce it: once the substrate is gone, every split of
#: product is an equilibrium.
CONTINUUM = "continuum"
OSCILLATORY_STABLE = "stable spiral"
OSCILLATORY_UNSTABLE = "unstable spiral"


class AnalysisError(RuntimeError):
    """The analysis could not be performed, as distinct from finding nothing."""


@dataclass(frozen=True)
class FixedPoint:
    """One steady state, and what the linearisation says about it."""

    #: species id -> concentration
    state: Mapping[str, float]
    #: Largest absolute time derivative at this point. A converged root has
    #: a small one; it is carried rather than discarded so a reader can see
    #: HOW converged, instead of trusting a boolean.
    residual: float
    eigenvalues: Tuple[complex, ...]
    classification: str
    #: True when any species is negative by more than rounding. Kept rather
    #: than filtered, because a negative fixed point is a real property of
    #: the equations and hiding it makes the positive ones look like the
    #: whole story.
    physical: bool = True

    @property
    def stable(self) -> bool:
        return self.classification in (STABLE, OSCILLATORY_STABLE)

    @property
    def oscillatory(self) -> bool:
        return any(abs(value.imag) > MARGINAL_EIGENVALUE for value in self.eigenvalues)

    @property
    def slowest_timescale(self) -> Optional[float]:
        """1 / |smallest non-zero real part|, in the model's time unit.

        How long the system takes to settle, which is what a researcher
        choosing a simulation window actually needs. `None` when every
        eigenvalue is marginal, where no timescale is defined.
        """
        rates = [
            abs(value.real) for value in self.eigenvalues
            if abs(value.real) > MARGINAL_EIGENVALUE
        ]
        return 1.0 / min(rates) if rates else None

    def describe(self) -> str:
        coordinates = ", ".join(
            f"{name}={value:.4g}" for name, value in sorted(self.state.items())
        )
        parts = [f"{self.classification} at {coordinates}"]
        if self.oscillatory:
            periods = [
                2 * math.pi / abs(value.imag)
                for value in self.eigenvalues
                if abs(value.imag) > MARGINAL_EIGENVALUE
            ]
            parts.append(f"period ~{min(periods):.3g} time units")
        timescale = self.slowest_timescale
        if timescale is not None:
            parts.append(f"settles over ~{timescale:.3g} time units")
        if not self.physical:
            parts.append("NEGATIVE concentrations -- not physically reachable")
        return "; ".join(parts)


@dataclass(frozen=True)
class StabilityReport:
    """Every fixed point the search converged to, and what follows."""

    fixed_points: Tuple[FixedPoint, ...]
    #: How many starting points were tried. Reported because the meaning of
    #: "found two states" depends entirely on how hard it looked.
    starts_tried: int
    species: Tuple[str, ...]
    notes: Tuple[str, ...] = ()

    @property
    def physical_points(self) -> Tuple[FixedPoint, ...]:
        return tuple(point for point in self.fixed_points if point.physical)

    @property
    def stable_points(self) -> Tuple[FixedPoint, ...]:
        return tuple(p for p in self.physical_points if p.stable)

    @property
    def at_least_bistable(self) -> bool:
        """Two or more physically reachable stable states were FOUND.

        Deliberately not `is_bistable`. A multistart search reports what it
        converged to; it cannot prove there is no third state, and it cannot
        prove there is no second one it missed. The name says what the
        evidence supports.
        """
        return len(self.stable_points) >= 2

    @property
    def any_oscillatory(self) -> bool:
        return any(p.oscillatory for p in self.physical_points)

    @property
    def continuum_points(self) -> Tuple[FixedPoint, ...]:
        """Every point the search landed on a line of equilibria.

        Over ALL fixed points, not the physical ones: the line is
        established by every point on it, and most of a line usually lies
        outside the physical region. Two enzymes competing for one
        substrate put 18 of 19 points at negative product.
        """
        return tuple(p for p in self.fixed_points if p.classification == CONTINUUM)

    @property
    def on_a_continuum(self) -> bool:
        """The search found a line of equilibria and no isolated attractor.

        Deliberately conjunctive. A model can have a continuum AND a
        genuine stable state elsewhere in its state space; that is a
        stranger object than either alone and is not summarised by this
        flag. This is the plain case, and the one the library produces.
        """
        return bool(self.continuum_points) and not self.stable_points

    def summary(self) -> str:
        if not self.fixed_points:
            return (
                f"No steady state was found from {self.starts_tried} starting "
                f"points. That is not proof there is none -- a root find "
                f"reports where it converged. A system that oscillates "
                f"forever has an unstable fixed point the solver may step "
                f"away from, and one with a source and no sink has no steady "
                f"state at all."
            )

        lines = [
            f"{len(self.physical_points)} steady state(s) found from "
            f"{self.starts_tried} starting points"
            + (
                f" ({len(self.fixed_points) - len(self.physical_points)} more "
                f"at negative concentrations, which the equations have and "
                f"the system cannot reach)"
                if len(self.fixed_points) > len(self.physical_points)
                else ""
            )
            + ":"
        ]
        for point in self.physical_points:
            lines.append("  - " + point.describe())

        if self.on_a_continuum:
            physical = [p for p in self.continuum_points if p.physical]
            lines.append(
                f"A LINE of equilibria: {len(self.continuum_points)} point(s) "
                f"were found on it, {len(physical)} physically reachable, and "
                f"none is an attractor on its own -- each is attracting in "
                f"every direction but one, and along that one the dynamics "
                f"do not move. The system reaches the line and stops; where "
                f"on it is decided by the transient, not by the constants. "
                f"This is NOT a switch. A switch has discrete states with "
                f"repellors between them; here every point on the line is "
                f"an equilibrium and 'which state' has no answer -- a time "
                f"course from your actual starting amounts does. "
                + CONTINUUM_COUNT_CAVEAT
            )
        elif self.at_least_bistable:
            lines.append(
                f"At least {len(self.stable_points)} stable states were "
                f"found, so this system can rest in more than one place: it "
                f"switches. Which one it reaches depends on where it starts, "
                f"which is why a single trajectory cannot show this."
            )
        elif len(self.stable_points) == 1 and len(self.physical_points) > 1:
            lines.append(
                "One stable state and one or more unstable ones: the system "
                "settles to the same place from anywhere it can reach."
            )

        if self.any_oscillatory:
            lines.append(
                "Complex eigenvalues: the approach to steady state is "
                "oscillatory rather than monotone. A sustained oscillation "
                "needs an UNSTABLE spiral, which is listed above if present."
            )

        lines.extend(self.notes)
        lines.append(
            "These are numerical results from a root find, not derived "
            "facts. The conservation laws this model reports ARE derived; "
            "these are what a solver converged to, with the residuals shown."
        )
        return " ".join(lines)


# ---------------------------------------------------------------------------
# Building the right-hand side from a network
# ---------------------------------------------------------------------------


def derivative_function(
    network: Any,
) -> Tuple[Callable[[Sequence[float]], List[float]], Tuple[str, ...]]:
    """`(f, species_order)` where `f(x)` is dx/dt for the network.

    Compiled from the stoichiometry and the rate laws rather than from any
    simulator, so the analysis needs no libRoadRunner and agrees with the
    model as declared. Rate laws are evaluated with a restricted builtins
    map -- they have already been validated by `ReactionNetwork`, and this
    adds the second lock rather than trusting the first.
    """
    species_order = tuple(s.id for s in network.species)
    index_of = {name: position for position, name in enumerate(species_order)}
    parameters = {p.id: float(p.value) for p in network.parameters}

    compiled: List[Tuple[Any, Dict[str, int]]] = []
    for reaction in network.reactions:
        net: Dict[str, int] = {}
        for name, count in reaction.reactants.items():
            net[name] = net.get(name, 0) - int(count)
        for name, count in reaction.products.items():
            net[name] = net.get(name, 0) + int(count)
        expression = _compile_rate_law(reaction.rate_law, reaction.id)
        compiled.append((expression, {k: v for k, v in net.items() if v}))

    # RATE RULES ARE DYNAMICS TOO, AND WERE BEING DROPPED.
    #
    # `core.network.RateRule` exists because Lotka-Volterra, Tyson's
    # cell-cycle oscillator and the catalogue's repressilator are written
    # as X' = expression rather than as reactions -- its own docstring says
    # an IR without them "would quietly leave the interesting three
    # behind". This function built the right-hand side from reactions
    # alone, so on any such model it returned zero for every rate-ruled
    # species, `analyse` found fixed points of the wrong system, and
    # reported them with residuals near zero. The simulator honoured the
    # rules; the analysis did not; and nothing compared the two.
    #
    # A rate rule contributes its whole expression to its target's
    # derivative, coefficient one. The IR forbids a species being both
    # rate-ruled and in a reaction, so there is no double counting.
    for rule in getattr(network, "rate_rules", ()):
        target = getattr(rule, "target", None)
        if target in index_of:
            expression = _compile_rate_law(
                getattr(rule, "expression", ""), f"rate rule for {target}",
            )
            compiled.append((expression, {target: 1}))

    # Assignment rules are derived quantities, not state: recomputed from
    # the current environment before any rate is evaluated, in declaration
    # order so one may use another. An assigned name that is also a species
    # has no dynamics of its own, which the IR's `problems` already forbids.
    assignments: List[Tuple[str, Any]] = [
        (
            getattr(rule, "target", ""),
            _compile_rate_law(
                getattr(rule, "expression", ""),
                f"assignment rule for {getattr(rule, 'target', '')}",
            ),
        )
        for rule in getattr(network, "assignment_rules", ())
        if getattr(rule, "target", None)
    ]

    safe_builtins: Dict[str, Any] = {
        "abs": abs, "min": min, "max": max, "pow": pow,
        "exp": math.exp, "ln": math.log, "log": math.log,
        "log10": math.log10, "sqrt": math.sqrt,
        "sin": math.sin, "cos": math.cos, "tan": math.tan,
    }

    def rhs(state: Sequence[float]) -> List[float]:
        environment = dict(parameters)
        for name, position in index_of.items():
            environment[name] = float(state[position])
        for target, expression in assignments:
            try:
                environment[target] = float(eval(
                    expression, {"__builtins__": {}},
                    {**safe_builtins, **environment},
                ))
            except ZeroDivisionError:
                environment[target] = float("inf")
        derivatives = [0.0] * len(species_order)
        for expression, net in compiled:
            try:
                rate = eval(expression, {"__builtins__": {}}, {**safe_builtins, **environment})
            except ZeroDivisionError:
                # A rate law dividing by zero at this point. Reported as a
                # non-finite derivative rather than crashing the search:
                # the solver should step away from it, not the analysis.
                rate = float("inf")
            for name, coefficient in net.items():
                derivatives[index_of[name]] += coefficient * float(rate)
        return derivatives

    return rhs, species_order


def _compile_rate_law(rate_law: str, reaction_id: str):
    """Compile a validated rate law, translating `^` to Python's `**`.

    Antimony and SBML use `^` for exponentiation; Python uses it for XOR.
    A model written with `^` and evaluated in Python without this
    translation computes something entirely different and does not error --
    `2^3` is 1, not 8 -- which is a silent wrong answer of exactly the kind
    this module exists to avoid producing.
    """
    translated = rate_law.replace("^", "**")
    try:
        return compile(translated, f"<rate law {reaction_id}>", "eval")
    except SyntaxError as exc:
        raise AnalysisError(
            f"reaction {reaction_id!r} has a rate law this analysis cannot "
            f"compile: {rate_law!r} ({exc})"
        ) from exc


# ---------------------------------------------------------------------------
# Jacobian and classification
# ---------------------------------------------------------------------------


def jacobian(
    rhs: Callable[[Sequence[float]], List[float]],
    state: Sequence[float],
    step: float = JACOBIAN_STEP,
) -> List[List[float]]:
    """Finite-difference Jacobian, by central differences.

    Central rather than forward: the truncation error is O(h^2) rather than
    O(h), which matters here because the eigenvalues near a bifurcation are
    small and a forward difference's first-order error can move one across
    zero -- turning a stable state into an unstable one in the report.
    """
    n = len(state)
    base = list(state)
    matrix: List[List[float]] = []

    for column in range(n):
        magnitude = max(abs(base[column]), 1.0)
        h = step * magnitude

        forward = list(base)
        forward[column] += h
        backward = list(base)
        backward[column] -= h

        plus = rhs(forward)
        minus = rhs(backward)
        matrix.append([(plus[row] - minus[row]) / (2 * h) for row in range(n)])

    # Built column by column above; transpose to the conventional
    # J[i][j] = d(f_i)/d(x_j).
    return [[matrix[column][row] for column in range(n)] for row in range(n)]


def classify(eigenvalues: Sequence[complex]) -> str:
    """Name the fixed point from its eigenvalues.

    `marginal` is a real answer, not a failure to decide. At a bifurcation
    the linearisation decides nothing, and rounding a near-zero eigenvalue
    to one side reports a system as a switch when it is sitting exactly on
    the boundary of being one.
    """
    if not eigenvalues:
        return MARGINAL

    reals = [value.real for value in eigenvalues]
    oscillatory = any(abs(value.imag) > MARGINAL_EIGENVALUE for value in eigenvalues)

    if any(abs(real) <= MARGINAL_EIGENVALUE for real in reals):
        # A ZERO THAT REACHES HERE IS REAL.
        #
        # The first version of this branch ignored the zero and classified
        # on the remaining eigenvalues, reasoning that a zero "usually means
        # a conservation law". Both callers -- `analyse` and
        # `continuation` -- strip exactly as many structural zeros as there
        # are conservation laws BEFORE calling this, so by the time a zero
        # arrives it is not a law. It is a direction the dynamics do not
        # restore along: the point sits on a LINE of equilibria, and which
        # point on the line the system reaches is decided by the transient.
        #
        # Two enzymes competing for one substrate is the plain case. Once
        # substrate is exhausted, every split of product between them is an
        # equilibrium. The old branch called nineteen points on that line
        # "stable", and the verdict page turned nineteen stable states into
        # "this system switches". It does not switch. A switch has discrete
        # attractors with repellors between them; this has a continuum.
        #
        # So a remaining zero is CONTINUUM when every other direction is
        # attracting -- the line is reached and then not left -- and
        # MARGINAL otherwise, which is the bifurcation reading the docstring
        # above describes. The distinction is worth a constant of its own
        # because a reader asked to interpret "marginal" reaches for a
        # bifurcation diagram, and this is not that.
        others = [real for real in reals if abs(real) > MARGINAL_EIGENVALUE]
        if others and all(real < 0 for real in others):
            return CONTINUUM
        return MARGINAL

    if all(real < 0 for real in reals):
        return OSCILLATORY_STABLE if oscillatory else STABLE
    if all(real > 0 for real in reals):
        return OSCILLATORY_UNSTABLE if oscillatory else UNSTABLE
    return SADDLE


# ---------------------------------------------------------------------------
# The search
# ---------------------------------------------------------------------------


#: Units `core.network.Parameter` may carry that denote a concentration.
#:
#: Duplicated from `scale._TO_MOLAR`'s keys rather than imported, so the
#: root finder does not depend on the physical-bounds module to decide
#: where to look. `test_the_concentration_units_have_not_drifted` holds the
#: two lists together.
_CONCENTRATION_UNITS = frozenset({"M", "mM", "uM", "µM", "nM", "pM"})


def _search_scale(network: Any) -> List[float]:
    """The magnitude each species' concentration actually lives at.

    THE BUG THIS REPLACES. This was `max(abs(s.initial), 1.0)` per species,
    and the floor of 1.0 is the whole problem: for any model whose
    concentrations sit below one in its own unit, the multistart looked
    at order 1 and the fixed points were orders of magnitude below that.

    A toggle switch scaled to realistic transcription-factor
    concentrations -- around a micromolar, which in the library's mM is
    1e-3 -- returned ONE fixed point and no stable states. The same model
    at the library's default values returns three points and two stable
    ones. The mathematics is identical: scaling every synthesis rate and
    every affinity by the same factor scales the steady states by that
    factor and changes nothing else. Only the search moved.

    That is the concentration range real regulatory biology occupies, and
    the failure was silent: not a refusal, a confident "no stable state
    was found from N starting points".

    ONE SCALE FOR THE WHOLE MODEL, NOT ONE PER SPECIES.

    The first version of this fix used each species' OWN initial amount,
    and a test caught it: in the library toggle switch geneB starts at 0.1
    and settles at 1.995, so a search anchored at 0.1 never reached the
    state. An initial amount is where a species STARTS. It is not an
    estimate of where it ends up, and treating it as one is a worse error
    than the floor it replaced -- the old `max(initial, 1.0)` at least
    bracketed both states by accident.

    So every species is searched at the same magnitude: the largest
    concentration the model states anywhere. Starts are spread over
    decades around it, and overshooting costs far less than undershooting
    -- undershooting is the failure this whole function exists to fix.

    WHAT COUNTS AS THE MODEL STATING A CONCENTRATION

    Species initial amounts, and concentration-valued PARAMETERS: a Km, a
    Kd, a half-repression constant. Those set the scale of whatever
    species sits beside them in a rate law -- a Hill term is
    `K^n / (K^n + R^n)`, so R matters exactly where it is comparable to K.
    This is what `core.network.Parameter` carrying a unit is FOR; without
    it the network cannot say which of its constants are concentrations.

    WHEN THE PARAMETERS SAY NOTHING, THE FLOOR OF ONE STAYS. A network
    built by hand with unitless constants gives no concentration evidence
    beyond its starting amounts -- and a starting amount is where a species
    STARTS, which this function's own history shows is a poor guide to
    where it settles. The second version of this dropped the floor for
    every network, and a hand-built switch starting at X = 0.1 with its
    stable state at X = 3.2 lost that state at shallow depth: the search
    was anchored at 0.1 and only a third of its starts fell in the basin.
    So the floor is dropped only when a declared concentration -- a Km, a
    Kd, a half-repression constant -- gives a real reason to; otherwise
    order unity is the honest default for a model that has said nothing.
    """
    initials: List[float] = [
        abs(float(getattr(s, "initial", 0.0))) for s in network.species
    ]

    declared: List[float] = []
    for parameter in getattr(network, "parameters", ()):
        unit = str(getattr(parameter, "unit", "") or "").strip()
        value = abs(float(getattr(parameter, "value", 0.0)))
        if unit in _CONCENTRATION_UNITS and value > 0.0:
            declared.append(value)

    positive_initials = [value for value in initials if value > 0.0]
    if declared:
        # A declared concentration is evidence about scale; the floor goes.
        magnitude = max(declared + positive_initials)
    else:
        # Only starting amounts, which are not: keep the floor.
        magnitude = max(positive_initials + [1.0])
    return [magnitude] * len(network.species)


def analyse(
    network: Any,
    *,
    starts_per_species: int = DEFAULT_STARTS_PER_SPECIES,
    max_starts: int = 64,
    seed: int = 0,
    extra_starts: Sequence[Sequence[float]] = (),
) -> StabilityReport:
    """Find what steady states a multistart root find converges to.

    Deterministic: the starting points are generated from `seed` by a local
    linear congruential sequence rather than from the global random module,
    so two runs of the same model give the same report. A stability analysis
    that changed between runs would be unciteable.

    `extra_starts` are tried BEFORE the generated ones, in the order given.
    They exist for continuation: a caller that already knows where a fixed
    point sits -- because it is walking a parameter a fraction of a percent
    at a time -- can hand that state over instead of making the search
    rediscover it from scratch. With `starts_per_species=0` they are the
    only starts, which turns a global search into a local one and is the
    difference between following a branch and re-deciding which branch to be
    on at every step. See `compose/sensitivity.py`, which needs the former
    and was getting the latter.

    A start of the wrong length is a caller error and is refused rather than
    padded: silently reshaping a state would produce a converged answer to a
    question nobody asked.
    """
    try:
        import numpy as np
        from scipy.optimize import least_squares
    except ImportError as exc:  # pragma: no cover - dependency is pinned
        raise AnalysisError(
            "steady-state analysis needs numpy and scipy, which are in "
            f"requirements.txt but not importable here: {exc}"
        ) from exc

    rhs, species = derivative_function(network)
    if not species:
        raise AnalysisError("a network with no species has no state to solve for")

    # THE CONSERVATION LAWS CHANGE THE QUESTION.
    #
    # A network with conservation laws does not have isolated steady states:
    # it has one per LEAF of the foliation the laws define. A three-tier
    # cascade conserves total protein in each tier, so every choice of those
    # totals has its own steady state, and an unconstrained multistart finds
    # a different leaf from every start.
    #
    # The first version of this reported nine such points as "at least 9
    # stable states were found, so this system switches". They are one
    # steady state seen from nine different initial conditions. Multistability
    # means several stable states on the SAME leaf, and only a constrained
    # solve can tell the difference.
    laws = _conservation_matrix(network, species)

    scale = _search_scale(network)
    for start in extra_starts:
        if len(start) != len(species):
            raise AnalysisError(
                f"an explicit starting point has {len(start)} coordinates "
                f"but this network has {len(species)} species "
                f"({', '.join(species)}). A start of the wrong length is not "
                f"padded, because the solve would converge and answer a "
                f"different question."
            )
    starts = [[float(v) for v in start] for start in extra_starts]
    starts += _starting_points(
        len(species), scale, starts_per_species, max_starts, seed
    )
    if not starts:
        raise AnalysisError(
            "no starting points: starts_per_species is 0 and no "
            "extra_starts were given, so the search would look nowhere and "
            "report no steady states. That would read as 'this model has "
            "none', which is a different claim entirely."
        )

    # Every start is projected onto the leaf of the DECLARED initial
    # condition, so all of them are asking the same question.
    declared = [float(s.initial) for s in network.species]
    totals = [sum(row[i] * declared[i] for i in range(len(species))) for row in laws]

    def residual_system(x):
        """Rate equations AND conservation constraints, all of them.

        APPENDED, not substituted. The first version replaced the last
        `len(laws)` rate equations with the constraints, on the reasoning
        that the rate equations are linearly dependent by exactly that many.
        They are -- but the dependent rows are not the last ones, and
        picking by position threw away equations the system needed. The
        three-tier cascade went from nine wrong answers to none at all.

        Appending makes the system overdetermined and consistent, which
        `least_squares` solves and `fsolve` (square systems only) cannot.
        Nothing is discarded and no row is privileged by its position.
        """
        values = list(rhs(x))
        for row, total in zip(laws, totals):
            values.append(sum(row[i] * x[i] for i in range(len(x))) - total)
        return values

    # THE CONVERGENCE BAR IS RELATIVE TO THE MODEL'S OWN FLUXES.
    #
    # `RESIDUAL_TOLERANCE` is 1e-9 and was compared against the residual
    # as an absolute number. On a model at nanomolar concentrations with
    # rates to match, every flux is around 1e-7 and a residual of 5e-10 is
    # not a converged root -- it is a point a few percent away from one,
    # with everything small. A two-stage expression model returned THREE
    # "stable states" that were one state, found imprecisely from three
    # starts, each passing the absolute bar. The search-scale fix exposed
    # this: the search used to start far above such a model and never
    # reached the flat region where the bar was too easy.
    #
    # So the bar is 1e-9 of the largest flux the model shows across the
    # starting points, which are spread over four decades around its scale
    # and so include points well away from equilibrium. A model whose
    # every flux is zero at every start has no dynamics to converge, and
    # for it the absolute bar is kept rather than dividing by nothing.
    #
    # PROBED AWAY FROM EQUILIBRIUM, NOT ONLY AT THE STARTS. A caller
    # passing one explicit start placed AT the root -- which is what a
    # local solve is -- would otherwise measure the reference flux at the
    # root itself, get something near machine precision, and set a bar a
    # million times tighter than any solver can meet. Two of this file's
    # own tests did exactly that and found nothing. So the probes at the
    # search scale, and at a decade either side of it, are always included:
    # a model that is at equilibrium at all three has no dynamics to speak
    # of, and the absolute bar is kept for it.
    probes = list(starts)
    for factor in (0.1, 1.0, 10.0):
        probes.append([factor * value for value in scale])
    reference_flux = 0.0
    for probe in probes:
        try:
            rates = rhs(probe)
        except Exception:  # noqa: BLE001 - a probe that raises is not a scale
            continue
        largest = max((abs(v) for v in rates if math.isfinite(v)), default=0.0)
        reference_flux = max(reference_flux, largest)
    residual_bar = (
        RESIDUAL_TOLERANCE * reference_flux if reference_flux > 0.0
        else RESIDUAL_TOLERANCE
    )

    found: List[FixedPoint] = []
    for start in starts:
        try:
            outcome = least_squares(
                residual_system, start, xtol=1e-14, ftol=1e-14, gtol=1e-14,
            )
        except Exception:  # noqa: BLE001 - a failed start is not a failed run
            continue
        if not outcome.success:
            continue
        solution = outcome.x
        # Measured on the true dynamics, not on the augmented system: the
        # conservation rows are satisfied by construction and including them
        # would flatter the residual.
        residual = max(abs(value) for value in rhs(solution))
        if not math.isfinite(residual) or residual > residual_bar:
            continue
        state = {name: float(value) for name, value in zip(species, solution)}
        if _already_found(state, found):
            continue

        matrix = jacobian(rhs, list(solution))
        try:
            eigenvalues = tuple(complex(v) for v in np.linalg.eigvals(np.array(matrix)))
        except Exception:  # noqa: BLE001
            continue

        # Drop exactly as many near-zero eigenvalues as there are
        # conservation laws. Each law contributes a structural zero -- the
        # dynamics do not move along a conserved direction -- and leaving
        # them in makes every conserved system read as `marginal`, which
        # says nothing about whether the state is an attractor ON its leaf.
        if laws:
            ordered = sorted(eigenvalues, key=lambda v: abs(v))
            structural = [v for v in ordered[:len(laws)] if abs(v) <= 1e-6]
            for value in structural:
                remaining = list(eigenvalues)
                remaining.remove(value)
                eigenvalues = tuple(remaining)

        found.append(
            FixedPoint(
                state=state,
                residual=residual,
                eigenvalues=eigenvalues,
                classification=classify(eigenvalues),
                physical=all(value > -STATE_DISTINCT_TOLERANCE for value in state.values()),
            )
        )

    notes: List[str] = []
    zero_eigen = [
        point for point in found
        if any(abs(v.real) <= MARGINAL_EIGENVALUE and abs(v.imag) <= MARGINAL_EIGENVALUE
               for v in point.eigenvalues)
    ]
    if zero_eigen:
        laws = _conservation_law_count(network)
        if laws:
            notes.append(
                f"Some eigenvalues are zero, which is expected here: this "
                f"network has {laws} conservation law(s), and the dynamics do "
                f"not move along a conserved direction at all. That is a "
                f"structural zero rather than a marginal stability."
            )

    return StabilityReport(
        fixed_points=tuple(found),
        starts_tried=len(starts),
        species=species,
        notes=tuple(notes),
    )


def _conservation_matrix(network: Any, species: Sequence[str]) -> List[List[float]]:
    """Conservation laws as rows over the species order.

    Taken from `ReactionNetwork`, which computes them EXACTLY over
    `Fraction` from the stoichiometry. Converted to float only here, at the
    boundary with a numerical solver, so the exact result stays the
    authority and this is visibly the approximation of it.
    """
    try:
        laws = network.conservation_laws()
    except Exception:  # noqa: BLE001 - a network that cannot report them
        return []
    rows: List[List[float]] = []
    for law in laws:
        rows.append([float(law.get(name, 0)) for name in species])
    return rows


def _conservation_law_count(network: Any) -> int:
    try:
        return len(network.conservation_laws())
    except Exception:  # noqa: BLE001 - the count is a courtesy, not a result
        return 0


def _already_found(state: Mapping[str, float], found: Sequence[FixedPoint]) -> bool:
    for point in found:
        if all(
            abs(state[name] - point.state[name])
            <= STATE_DISTINCT_TOLERANCE * max(1.0, abs(point.state[name]))
            for name in state
        ):
            return True
    return False


def _starting_points(
    dimension: int,
    scale: Sequence[float],
    per_species: int,
    maximum: int,
    seed: int,
) -> List[List[float]]:
    """Deterministic spread of starting points across the state space.

    A local linear congruential generator rather than `random`, so the
    report does not depend on global interpreter state that another module
    may have seeded. Numerical results that move between runs cannot be
    cited.

    `per_species <= 0` generates nothing, for a caller supplying its own
    starts. The floor of four otherwise is there so that asking for a search
    always gets one; it must not override a caller that asked for no search
    at all, because four arbitrary points added to a continuation step would
    let it jump to a branch the caller was deliberately not on.
    """
    if per_species <= 0:
        return []
    count = min(maximum, max(4, per_species * dimension))
    state = (seed * 6364136223846793005 + 1442695040888963407) & ((1 << 64) - 1)
    points: List[List[float]] = []

    # The origin and the declared initial condition are always tried: the
    # first is where many of these systems have a trivial state, and the
    # second is where the researcher said they were starting.
    points.append([0.0] * dimension)
    points.append([float(value) for value in scale])

    while len(points) < count:
        coordinates: List[float] = []
        for index in range(dimension):
            state = (state * 6364136223846793005 + 1442695040888963407) & ((1 << 64) - 1)
            fraction = ((state >> 11) & ((1 << 53) - 1)) / float(1 << 53)
            # LOGARITHMIC over four decades, not linear over three-fold.
            #
            # The linear version spanned 0.05 to 3 times the declared
            # concentration and missed both stable states of a toggle
            # switch, which sit near ten times it -- the whole point of a
            # switch being that the two states are far apart. A switch whose
            # states the search cannot reach is reported as monostable,
            # which is a confidently wrong answer about the one property the
            # model was built to show.
            exponent = -2.0 + 4.0 * fraction
            coordinates.append(scale[index] * (10.0 ** exponent))
        points.append(coordinates)
    return points


__all__ = [
    "FixedPoint", "StabilityReport", "AnalysisError",
    "analyse", "classify", "jacobian", "derivative_function",
    "STABLE", "UNSTABLE", "SADDLE", "MARGINAL", "CONTINUUM",
    "OSCILLATORY_STABLE", "OSCILLATORY_UNSTABLE",
    "RESIDUAL_TOLERANCE", "STATE_DISTINCT_TOLERANCE", "CONTINUUM_COUNT_CAVEAT", "MARGINAL_EIGENVALUE",
    "JACOBIAN_STEP", "DEFAULT_STARTS_PER_SPECIES",
]
