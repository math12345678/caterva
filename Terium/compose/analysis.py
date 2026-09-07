"""Steady states, stability, and whether a switch actually switches.

WHY A TRAJECTORY IS NOT AN ANSWER
---------------------------------
Terrium can integrate a composed model and draw a curve. For most of the
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
#: MEASURED, not chosen for tidiness. At 4 the symmetric toggle switch
#: found one of its two stable states and reported "one stable state ... the
#: system settles to the same place from anywhere it can reach" -- a
#: confidently wrong answer about the single property the model exists to
#: show. At 8 it finds both, and 16 and 32 find nothing further.
#:
#: Set to 8 rather than to the largest number tried: more starts cost a root
#: find each and bought nothing here, and a default that is slow for no
#: measured benefit gets turned down by the first person in a hurry.
#:
#: This does not make the search exhaustive and nothing here claims it is.
#: See `StabilityReport.at_least_bistable` for what the evidence supports.
DEFAULT_STARTS_PER_SPECIES = 8

STABLE = "stable"
UNSTABLE = "unstable"
SADDLE = "saddle"
MARGINAL = "marginal"
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

        if self.at_least_bistable:
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
        # A zero eigenvalue usually means a conservation law: the dynamics
        # do not move along that direction at all. That is not marginality
        # in the bifurcation sense, so it is worth distinguishing -- but
        # doing so needs the conservation laws, which `analyse` has and this
        # function does not. It reports what it can see.
        others = [real for real in reals if abs(real) > MARGINAL_EIGENVALUE]
        if others and all(real < 0 for real in others):
            return OSCILLATORY_STABLE if oscillatory else STABLE
        if others and all(real > 0 for real in others):
            return OSCILLATORY_UNSTABLE if oscillatory else UNSTABLE
        return MARGINAL

    if all(real < 0 for real in reals):
        return OSCILLATORY_STABLE if oscillatory else STABLE
    if all(real > 0 for real in reals):
        return OSCILLATORY_UNSTABLE if oscillatory else UNSTABLE
    return SADDLE


# ---------------------------------------------------------------------------
# The search
# ---------------------------------------------------------------------------


def analyse(
    network: Any,
    *,
    starts_per_species: int = DEFAULT_STARTS_PER_SPECIES,
    max_starts: int = 64,
    seed: int = 0,
) -> StabilityReport:
    """Find what steady states a multistart root find converges to.

    Deterministic: the starting points are generated from `seed` by a local
    linear congruential sequence rather than from the global random module,
    so two runs of the same model give the same report. A stability analysis
    that changed between runs would be unciteable.
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

    scale = [max(abs(s.initial), 1.0) for s in network.species]
    starts = _starting_points(
        len(species), scale, starts_per_species, max_starts, seed
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
        if not math.isfinite(residual) or residual > RESIDUAL_TOLERANCE:
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
    """
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
    "STABLE", "UNSTABLE", "SADDLE", "MARGINAL",
    "OSCILLATORY_STABLE", "OSCILLATORY_UNSTABLE",
    "RESIDUAL_TOLERANCE", "STATE_DISTINCT_TOLERANCE", "MARGINAL_EIGENVALUE",
    "JACOBIAN_STEP", "DEFAULT_STARTS_PER_SPECIES",
]
