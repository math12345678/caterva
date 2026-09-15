"""Checking the compose module's own conclusions against each other.

WHY THIS EXISTS
---------------
`compose/` now reaches several of the same facts by routes that share no
code, and nothing compares them.

`analysis.py` finds a steady state by driving a root finder over rate laws
it compiles itself, with Python's `eval`. `simulate.py` reaches the same
state by integrating the same model through Antimony, SBML and
libRoadRunner -- a different reading of the same rate-law strings, and a
different arithmetic. `core/network.py` derives conservation laws exactly,
over `Fraction`, from the stoichiometry; the integrator has never been told
they exist. `analysis.py` predicts a settling time from the eigenvalues of a
finite-difference Jacobian; the trajectory takes however long it takes.
`sensitivity.py` takes a derivative with a step of six parts in a million;
the same derivative can be had by re-solving twenty percent away.
`units.py` decides whether a rate law balances, from declarations that no
other module reads.

Where two routes to one fact disagree, one of them is wrong and neither
knows it. Each module reports its own answer with its own caveats and
stops. This module is the comparison nobody was making.

WHY A CROSS-CHECK IS WORTH MORE HERE THAN A TEST
------------------------------------------------
A test pins a known model to a known answer, and catches the regression it
was written for. These checks compare two answers to each other, so they
need no known answer -- which is the whole point, because the population of
models this package serves is the one that was never in a catalogue. A
grammar that composes an eleven-step cascade produces a model nobody has
ever looked at, and the only thing available to check it against is
Terrium's other opinion of it.

NAMING WHICH ANSWER TO DOUBT IS THE PRODUCT
--------------------------------------------
"The root finder and the integrator disagree" is a fact and is not yet
useful: the reader has two modules and no reason to open one before the
other. Every finding here carries a `doubt` -- which answer is more likely
wrong, and the argument -- and three of the checks compute a discriminator
rather than guessing:

  * The fixed-point check re-evaluates the analysis module's own rate
    equations at the state before blaming anybody. A state that is not a
    root THERE was never a steady state, whatever produced it. A state that
    is a root and still drifts under the integrator means the two modules
    are not integrating the same equations, which is a different bug in a
    different place.

  * The sensitivity check recomputes its coarse secant over a span four
    times narrower. A secant that walks toward the fine derivative as the
    span shrinks is measuring curvature -- both numbers are right, about
    different things. One that does not is disagreeing about the slope
    itself, and then the fine difference, the one dividing by a step of
    6e-6, is the number exposed to the quantity's own noise.

  * The settling check asks whether the trajectory arrived at that fixed
    point at all before comparing timescales, because "the linearisation is
    slow" and "the system went somewhere else" are not the same finding.

WHAT A CLEAN REPORT DOES NOT MEAN
---------------------------------
That the model is right. Every check here compares Terrium against
Terrium. Two routes can be wrong together: they share the rate laws, the
stoichiometry and the parameter values, and a motif whose rate law says
something biology does not is reproduced faithfully by all of them. This
finds INCONSISTENCY, which is strictly smaller than error, and there is
deliberately no `report.valid` for a caller to read as the larger thing.

Nor does a check that did not run count as one that passed. A model with no
stable steady state has no fixed point to check; an installation without
libRoadRunner has no trajectory; a model whose rate laws do not balance
dimensionally is refused a trajectory by `simulate.run`, on purpose. All of
those come back `unchecked`, with the reason, and `ValidationReport` counts
them separately -- a report that asked nothing must not read like a report
that found nothing wrong.

THE TOLERANCES ARE JUDGEMENTS AND ARE NAMED
-------------------------------------------
Every threshold in this module is a constant with an argument attached,
because a cross-check is only as honest as its tolerance. Set them tight
and the report cries wolf on ordinary integrator noise until somebody stops
reading it; set them loose and it agrees with everything. Both failures
produce a report that looks like evidence, which is why each number here
says what it is protecting against and what it would miss.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from typing import Any, List, Mapping, Optional, Sequence, Tuple

# ---------------------------------------------------------------------------
# Vocabulary
# ---------------------------------------------------------------------------

#: The two routes gave the same answer, within the stated tolerance.
AGREE = "agree"

#: The two routes cannot both be right. One of the modules is wrong and the
#: finding says which is the better bet.
CONTRADICTION = "contradiction"

#: The two routes differ and the difference has a defensible reading that is
#: not a bug -- a linearisation describing the tail of an approach the
#: trajectory never entered, a secant measuring curvature. Real information,
#: reported as such rather than raised as an alarm or swallowed as noise.
DIVERGENCE = "divergence"

#: The check did not run. Never an agreement: the question was not asked.
UNCHECKED = "unchecked"

SEVERITIES = (AGREE, CONTRADICTION, DIVERGENCE, UNCHECKED)

#: Names of the checks, so a caller can select or filter without matching
#: prose that will be reworded.
CHECK_FIXED_POINT = "fixed point"
CHECK_CONSERVATION = "conservation"
CHECK_SETTLING = "settling time"
CHECK_SENSITIVITY = "sensitivity"
CHECK_DIMENSIONS = "dimensions"

CHECKS = (
    CHECK_DIMENSIONS,
    CHECK_CONSERVATION,
    CHECK_FIXED_POINT,
    CHECK_SETTLING,
    CHECK_SENSITIVITY,
)


# ---------------------------------------------------------------------------
# Tolerances, each with the argument for it
# ---------------------------------------------------------------------------

#: How far the state may move, as a fraction of the state's own magnitude,
#: while still counting as "did not move".
#:
#: A JUDGEMENT bounded from below by the integrator, not by a measurement.
#: libRoadRunner's default relative tolerance is around 1e-6, so a
#: trajectory sitting on a fixed point may wander at roughly that size for
#: reasons that are nobody's mistake. A factor of a hundred above it leaves
#: ordinary solver noise alone while still catching the failure this check
#: is for -- a state the root finder is confident about and the integrator
#: walks away from, which moves by order one.
#:
#: Measured on first-order turnover, where the root finder lands on x = 10
#: and the integrator holds it for forty time units: the drift is 1.8e-16
#: relative, twelve orders below this threshold. That measurement is
#: deliberately NOT used as the tolerance. One model's drift is not a bound
#: on another's, and a stiff nine-species system has no reason to hold its
#: state as tightly as a single exponential does.
FIXED_POINT_DRIFT_TOLERANCE = 1e-4

#: How many settling times to integrate for when checking that a fixed point
#: does not move. Long enough that a slow inconsistency has time to show;
#: there is no upper cost to running longer at a STABLE point, because the
#: dynamics there pull round-off back rather than amplifying it.
DRIFT_WINDOW_MULTIPLES = 4.0

#: The "within" in "how long the trajectory takes to get within a stated
#: tolerance of the steady state", as a fraction of the INITIAL deviation.
#:
#: Relative to the initial deviation rather than to the state, because the
#: question is how long the approach takes, and a system that starts close
#: to its steady state should not be credited with having settled instantly.
#: One twentieth is three time constants for a single exponential, which is
#: the textbook reading of "settled" and is far enough down the decay that
#: the slowest mode is the one still visible.
SETTLING_FRACTION = 0.05

#: How many predicted settling times to integrate for when measuring the
#: observed one. `SETTLING_FRACTION` is reached at ln(20) = 3.0 settling
#: times if the prediction is right, so eight leaves room to MEASURE a
#: system up to 2.6 times slower than predicted instead of truncating it and
#: reporting an unreached tolerance.
SETTLING_WINDOW_MULTIPLES = 8.0

#: Points in the trajectories these checks integrate.
#:
#: Higher than `simulate.DEFAULT_POINTS` because these are read
#: quantitatively rather than plotted: the crossing time is interpolated
#: between two grid points, and 401 over eight settling times puts them a
#: fiftieth of a settling time apart.
DEFAULT_POINTS = 401

#: How far apart the observed and predicted settling times may be, as a
#: ratio either way, before the difference is reported.
#:
#: A FACTOR, not a percentage, because the two numbers are not measuring
#: quite the same thing and cannot be expected to agree closely. The
#: prediction is the asymptotic rate of the slowest eigen-direction. The
#: measurement is when the whole state got small, and it comes out lower
#: whenever the initial displacement puts little weight on that direction --
#: legitimately, and by an amount that depends on the initial condition
#: rather than on any module being wrong. Two is loose enough to leave that
#: alone and tight enough that the failure worth catching -- a window
#: derived from the eigenvalues that cuts the approach off, or a fixed point
#: the trajectory is not going to -- is out of range by much more.
SETTLING_TOLERANCE_FACTOR = 2.0

#: The fractional parameter change the coarse sensitivity uses.
#:
#: Sixteen thousand times the fine difference's step, which is the point:
#: two estimates separated by that much cannot share a rounding error, a
#: cancellation, or a mis-declared precision. Ten percent is also about the
#: smallest change in a rate constant anyone would call a real change, so
#: the coarse number answers a question a reader recognises.
COARSE_SPAN = 0.1

#: The factor the span is narrowed by for the discriminator. Four, so the
#: curvature term -- which falls as the square of the span -- drops
#: sixteenfold, which is a large enough move to see against the agreement
#: threshold.
COARSE_REFINEMENT = 4.0

#: How far the coarse and fine sensitivities may differ, relatively, before
#: the difference is reported. Coarse on purpose: this check exists to catch
#: sign errors and gross scaling mistakes, which is what finite-difference
#: bugs look like, and a tight threshold here would fire on the curvature
#: that a ten percent span legitimately picks up.
SENSITIVITY_AGREEMENT = 0.25

#: How many stable states the fixed-point check examines.
#:
#: `analysis.analyse` does not promise to have found them all and this does
#: not either. The cap is there because each state costs an integration and
#: a model with many is usually a model whose search is confused; checking
#: three and saying how many were found is more honest than checking all of
#: an unbounded list and implying the list was complete.
MAX_STATES_CHECKED = 3


class ValidationError(RuntimeError):
    """A check could not be set up, as distinct from a check that failed."""


# ---------------------------------------------------------------------------
# What a check returns
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Finding:
    """One comparison between two of the package's answers.

    `doubt` is the reason this class exists. A finding that says two modules
    disagree and stops has handed the reader a bisection to perform; a
    finding that names the more likely suspect and the argument for it has
    handed them a place to start. It is required on anything that is not an
    agreement, and the constructor enforces that rather than trusting
    everyone who ever adds a check to remember.
    """

    check: str
    severity: str
    #: What was compared: a species, a conservation law, a parameter, a
    #: reaction. Carried separately from `detail` so a caller can group.
    subject: str
    #: What was measured, in words, including the numbers.
    detail: str
    #: Which module's answer to doubt first, and why. Empty only for an
    #: agreement.
    doubt: str = ""
    #: The numbers behind the verdict, so a reader can redo the arithmetic
    #: rather than trust the sentence.
    measured: Mapping[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.severity not in SEVERITIES:
            raise ValidationError(
                f"severity {self.severity!r} is not one of {SEVERITIES}. "
                f"Severity decides whether a caller must act, so an unknown "
                f"one has no defined meaning."
            )
        if self.severity in (CONTRADICTION, DIVERGENCE) and not self.doubt:
            raise ValidationError(
                f"the {self.check!r} check reported a {self.severity} about "
                f"{self.subject!r} without saying which answer to doubt. "
                f"Naming the suspect is the useful half of a cross-check: "
                f"without it the reader has two modules and no reason to "
                f"open one before the other."
            )
        if self.severity == UNCHECKED and not self.detail:
            raise ValidationError(
                f"the {self.check!r} check reported {self.subject!r} as "
                f"unchecked without saying why. An unexplained gap reads as "
                f"a pass."
            )

    @property
    def agreed(self) -> bool:
        return self.severity == AGREE

    def describe(self) -> str:
        head = f"[{self.severity}] {self.check} / {self.subject}: {self.detail}"
        return head if not self.doubt else f"{head} DOUBT: {self.doubt}"


@dataclass(frozen=True)
class ValidationReport:
    """Every cross-check that ran on one model, and what it found."""

    model: str
    findings: Tuple[Finding, ...]

    @property
    def contradictions(self) -> Tuple[Finding, ...]:
        return tuple(f for f in self.findings if f.severity == CONTRADICTION)

    @property
    def divergences(self) -> Tuple[Finding, ...]:
        return tuple(f for f in self.findings if f.severity == DIVERGENCE)

    @property
    def unchecked(self) -> Tuple[Finding, ...]:
        return tuple(f for f in self.findings if f.severity == UNCHECKED)

    @property
    def agreements(self) -> Tuple[Finding, ...]:
        return tuple(f for f in self.findings if f.severity == AGREE)

    def checks_run(self) -> Tuple[str, ...]:
        """Which checks produced at least one non-`unchecked` finding.

        Deliberately not "which checks were requested". A caller deciding
        how much a clean report is worth needs to know what was actually
        asked, and the difference between the two lists is the answer.
        """
        return tuple(
            name for name in CHECKS
            if any(f.check == name and f.severity != UNCHECKED
                   for f in self.findings)
        )

    def summary(self) -> str:
        lines = [
            f"Cross-checked {self.model}: "
            f"{len(self.agreements)} agreement(s), "
            f"{len(self.contradictions)} contradiction(s), "
            f"{len(self.divergences)} divergence(s), "
            f"{len(self.unchecked)} check(s) that did not run."
        ]

        if self.contradictions:
            lines.append(
                "CONTRADICTIONS -- two routes to the same fact that cannot "
                "both be right:"
            )
            for finding in self.contradictions:
                lines.append("  - " + finding.describe())

        if self.divergences:
            lines.append(
                "DIVERGENCES -- differences with a reading that is not a "
                "bug, reported because the reading is itself information:"
            )
            for finding in self.divergences:
                lines.append("  - " + finding.describe())

        if self.unchecked:
            lines.append(
                f"{len(self.unchecked)} check(s) did not run, which is not "
                f"the same as passing: "
                + "; ".join(f"{f.check} ({f.detail})" for f in self.unchecked)
                + "."
            )

        ran = self.checks_run()
        lines.append(
            f"{len(ran)} of {len(CHECKS)} checks produced a result "
            + (f"({', '.join(ran)}). " if ran else ". ")
            + "Every one of them compares Terrium against Terrium. Agreement "
            "means the package is self-consistent here, not that the model "
            "is right: the routes share the rate laws, the stoichiometry and "
            "the parameter values, so a mechanism written down wrongly is "
            "reproduced faithfully by all of them."
        )
        return " ".join(lines)


# ---------------------------------------------------------------------------
# Shared plumbing
# ---------------------------------------------------------------------------


def _analysis():
    try:
        from . import analysis  # type: ignore
    except ImportError:  # pragma: no cover - flat import
        import analysis  # type: ignore[no-redef]
    return analysis


def _simulate():
    try:
        from . import simulate  # type: ignore
    except ImportError:  # pragma: no cover - flat import
        import simulate  # type: ignore[no-redef]
    return simulate


def _sensitivity():
    try:
        from . import sensitivity  # type: ignore
    except ImportError:  # pragma: no cover - flat import
        import sensitivity  # type: ignore[no-redef]
    return sensitivity


def residual_at(network: Any, state: Mapping[str, float]) -> float:
    """The largest |dx/dt| at `state`, from the analysis module's own RHS.

    The discriminator the fixed-point check turns on, and the reason it can
    name a suspect instead of reporting a disagreement. This is one
    evaluation of each declared rate law -- no iteration, no tolerance, no
    solver -- so a large value here is a statement about the STATE and not
    about anybody's numerics.
    """
    analysis = _analysis()
    rhs, species = analysis.derivative_function(network)
    missing = [name for name in species if name not in state]
    if missing:
        raise ValidationError(
            f"the state is missing {', '.join(missing)}, which this network "
            f"has. Padding it with zeros would evaluate the rate laws at a "
            f"point nobody asked about and report the residual as though it "
            f"were the caller's."
        )
    values = [float(state[name]) for name in species]
    derivatives = rhs(values)
    return max(abs(value) for value in derivatives) if derivatives else 0.0


def state_scale(state: Mapping[str, float]) -> float:
    """The magnitude to measure a movement of this state against.

    ONE scale for the whole state, not one per species. A cascade's enzymes
    sit at 1e-3 and its substrates at 1, and dividing each species' drift by
    its own value would make a 1e-9 wobble on an enzyme look like a larger
    failure than a 1e-4 move of the substrate it is acting on. The question
    is whether the STATE moved, and the state's own magnitude is the
    yardstick for that.
    """
    values = [abs(float(v)) for v in state.values()]
    return max(max(values) if values else 0.0, 1e-12)


def _model_at(model: Any, state: Mapping[str, float]) -> Any:
    """The same model, started at `state`.

    Rebuilds the network's species rather than the composition's, because
    the composition's initial amounts are the SCENARIO the caller chose and
    a validator has no business editing them. Only the copy handed to the
    integrator moves.
    """
    network = model.network
    return replace(
        model,
        network=replace(
            network,
            species=tuple(
                replace(s, initial=float(state[s.id])) if s.id in state else s
                for s in network.species
            ),
        ),
    )


def _deviation(
    columns: Mapping[str, Sequence[float]],
    state: Mapping[str, float],
    index: int,
) -> float:
    """Euclidean distance from `state` at one point of a trajectory."""
    total = 0.0
    for name, target in state.items():
        if name not in columns:
            continue
        total += (float(columns[name][index]) - float(target)) ** 2
    return math.sqrt(total)


# ---------------------------------------------------------------------------
# Check 1: is the root finder's steady state a steady state of the integrator?
# ---------------------------------------------------------------------------


def fixed_point_verdict(
    residual: float, drift: float, scale: float
) -> Tuple[str, str, str]:
    """`(severity, detail, doubt)` for one fixed-point comparison.

    SPLIT OUT SO IT CAN BE DRIVEN DIRECTLY. The interesting half of this
    check is the attribution, and the attribution's second branch -- a state
    that IS a root and drifts anyway -- needs the two modules to disagree
    about what the ODE is, which no model in the library does. Left inside
    the check it would be a paragraph nobody could ever see run. Here it is
    a function with two numbers going in, and the tests drive both branches.
    """
    analysis = _analysis()
    relative = drift / scale

    if relative <= FIXED_POINT_DRIFT_TOLERANCE:
        return (
            AGREE,
            f"the state does not move: the trajectory stays within "
            f"{relative:.2e} of it, against a tolerance of "
            f"{FIXED_POINT_DRIFT_TOLERANCE:g}. The root finder and the "
            f"integrator agree about where this system rests, having reached "
            f"it by different arithmetic over different compilations of the "
            f"same rate laws.",
            "",
        )

    if residual > analysis.RESIDUAL_TOLERANCE:
        return (
            CONTRADICTION,
            f"the trajectory leaves this state by {relative:.3g} of the "
            f"state's own magnitude, and the state was never a steady state "
            f"to begin with: the analysis module's own rate equations give "
            f"|dx/dt| = {residual:.3g} here, against its convergence "
            f"threshold of {analysis.RESIDUAL_TOLERANCE:g}. The integrator "
            f"is behaving correctly by moving.",
            "whatever produced this state, not the integrator. The residual "
            "is one evaluation of the declared rate laws -- no solver, no "
            "tolerance -- so it settles the question on its own. If the "
            "state came from `analysis.analyse`, that is a defect in the "
            "search, which filters on exactly this residual and cannot "
            "return a point that fails it. The likelier innocent "
            "explanation is that the state is being reused against a "
            "network whose parameters have since changed.",
        )

    return (
        CONTRADICTION,
        f"the analysis module's rate equations are satisfied here to "
        f"|dx/dt| = {residual:.3g}, and the integrator still moves the state "
        f"by {relative:.3g} of its own magnitude. Both cannot be describing "
        f"the same system of equations.",
        "the path through the integrator, before the root find. The "
        "residual is a direct evaluation of the declared rate laws at this "
        "state -- one arithmetic expression per reaction, nothing iterative "
        "-- while the trajectory passes through `compile_to_antimony`, "
        "libantimony, SBML and an adaptive stiff solver with tolerances of "
        "its own. The specific failure to look for is the two readings of "
        "one rate-law string disagreeing: `analysis.derivative_function` "
        "already has to translate `^` to `**` because Python would read it "
        "as exclusive-or, and the base of `log` is another place two "
        "readers of the same text can mean different things. A rate law "
        "using either is the first thing to check. If the laws read the "
        "same both ways, the remaining suspect is the integrator's "
        "tolerance on a stiff system -- which the conservation check will "
        "usually have caught as well.",
    )


def fixed_point_findings(
    model: Any,
    *,
    states: Optional[Sequence[Mapping[str, float]]] = None,
    report: Any = None,
    points: int = DEFAULT_POINTS,
    window: Optional[float] = None,
    max_states: int = MAX_STATES_CHECKED,
    starts_per_species: Optional[int] = None,
) -> Tuple[Finding, ...]:
    """Integrate from each steady state and see whether it stays there.

    ONLY STABLE STATES, and that is not timidity. At an unstable fixed point
    or a saddle the integrator is SUPPOSED to leave: the round-off it starts
    with grows along the unstable direction, and a correct solver run from a
    correct state would drift away every time. Reporting that would be a
    false alarm by construction, and a check that fires on correct behaviour
    stops being read. Pass the state explicitly through `states` to check
    one anyway, which is what the tests do.

    `states` also lets a caller hand over a state the search did not
    produce. That is the deliberate-break entry point, and it is a real use
    besides: a state read out of somebody else's paper is exactly the thing
    worth asking this question about.

    `report` accepts a `StabilityReport` the caller already has, because a
    multistart search is the expensive part of everything in this package
    and `validate` needs the same one for two checks. Running it twice would
    cost double and, worse, let the two checks disagree about which search
    they were talking about.
    """
    analysis = _analysis()
    simulate = _simulate()
    findings: List[Finding] = []

    chosen: List[Mapping[str, float]]
    timescale: Optional[float] = None
    if states is not None:
        chosen = [dict(state) for state in states]
    else:
        try:
            if report is None:
                report = (
                    analysis.analyse(model.network)
                    if starts_per_species is None
                    else analysis.analyse(
                        model.network, starts_per_species=starts_per_species
                    )
                )
        except Exception as exc:  # noqa: BLE001 - a failed search is not a failure
            return (
                Finding(
                    check=CHECK_FIXED_POINT,
                    severity=UNCHECKED,
                    subject=model.network.name,
                    detail=(
                        f"the steady-state search did not run, so there is "
                        f"no state to integrate from: {exc}"
                    ),
                ),
            )
        stable = report.stable_points
        if not stable:
            return (
                Finding(
                    check=CHECK_FIXED_POINT,
                    severity=UNCHECKED,
                    subject=model.network.name,
                    detail=(
                        f"no stable steady state was found from "
                        f"{report.starts_tried} starting points, so there is "
                        f"nothing to check the integrator against. An "
                        f"unstable state is not a substitute: a correct "
                        f"integrator leaves one, so drift there would be "
                        f"evidence of nothing"
                    ),
                ),
            )
        chosen = [dict(point.state) for point in stable[:max_states]]
        timescales = [
            p.slowest_timescale for p in stable[:max_states]
            if p.slowest_timescale is not None
        ]
        timescale = max(timescales) if timescales else None
        if len(stable) > max_states:
            findings.append(
                Finding(
                    check=CHECK_FIXED_POINT,
                    severity=UNCHECKED,
                    subject=f"{len(stable) - max_states} further state(s)",
                    detail=(
                        f"{len(stable)} stable states were found and "
                        f"{max_states} were checked, which is what "
                        f"MAX_STATES_CHECKED says. The rest were not "
                        f"examined"
                    ),
                )
            )

    end = window
    if end is None:
        end = (
            DRIFT_WINDOW_MULTIPLES * timescale
            if timescale is not None
            else simulate.FALLBACK_END
        )

    for state in chosen:
        subject = ", ".join(
            f"{name}={value:.4g}" for name, value in sorted(state.items())
        )
        try:
            residual = residual_at(model.network, state)
        except Exception as exc:  # noqa: BLE001
            findings.append(
                Finding(
                    check=CHECK_FIXED_POINT,
                    severity=UNCHECKED,
                    subject=subject,
                    detail=f"the rate equations could not be evaluated: {exc}",
                )
            )
            continue

        try:
            trajectory = _simulate().run(
                _model_at(model, state), end=end, points=points
            )
        except Exception as exc:  # noqa: BLE001 - includes SimulationRefused
            findings.append(
                Finding(
                    check=CHECK_FIXED_POINT,
                    severity=UNCHECKED,
                    subject=subject,
                    detail=(
                        f"the model could not be integrated from this state, "
                        f"so the root finder's answer has nothing to be "
                        f"compared against: {exc}"
                    ),
                )
            )
            continue

        drift = 0.0
        for name, target in state.items():
            column = trajectory.columns.get(name)
            if column is None:
                continue
            drift = max(drift, max(abs(float(v) - float(target)) for v in column))

        scale = state_scale(state)
        severity, detail, doubt = fixed_point_verdict(residual, drift, scale)
        findings.append(
            Finding(
                check=CHECK_FIXED_POINT,
                severity=severity,
                subject=subject,
                detail=detail + f" (integrated to t={end:.4g}.)",
                doubt=doubt,
                measured={
                    "residual": residual,
                    "drift": drift,
                    "scale": scale,
                    "relative_drift": drift / scale,
                    "end": float(end),
                },
            )
        )

    return tuple(findings)


# ---------------------------------------------------------------------------
# Check 2: do the derived conservation laws survive the integration?
# ---------------------------------------------------------------------------


def conservation_findings(
    network: Any, columns: Mapping[str, Sequence[float]]
) -> Tuple[Finding, ...]:
    """Turn `simulate.check_invariants` into findings that name a suspect.

    The measurement is `simulate.py`'s and is not repeated here: it already
    walks each derived law along the trajectory and records the worst drift
    against a stated tolerance. What this adds is the attribution, which
    `simulate.py` states in prose on the failing case and cannot state at
    all on the one case where the law rather than the trajectory is the
    thing to doubt.
    """
    simulate = _simulate()
    checks = simulate.check_invariants(network, columns)
    if not checks:
        return (
            Finding(
                check=CHECK_CONSERVATION,
                severity=UNCHECKED,
                subject=getattr(network, "name", "this network"),
                detail=(
                    "no conservation law could be checked along this "
                    "trajectory. Either the stoichiometry has none -- which "
                    "is a real property of an open system and not a gap -- "
                    "or the trajectory did not carry the species the laws "
                    "are over"
                ),
            ),
        )

    # The one circumstance in which the LAW is the thing to doubt.
    # `stoichiometry_matrix` gives a column to every reaction and every rate
    # rule, so a species those two can change is accounted for. An
    # ASSIGNMENT rule is not a column: it overwrites its target every step,
    # and a "law" over a species written that way is a claim the dynamics
    # never agreed to.
    assigned = {
        getattr(rule, "target", None)
        for rule in getattr(network, "assignment_rules", ())
    }

    findings: List[Finding] = []
    for check in checks:
        scale = max(abs(check.initial), 1e-12)
        relative = check.worst_drift / scale
        if check.held:
            findings.append(
                Finding(
                    check=CHECK_CONSERVATION,
                    severity=AGREE,
                    subject=check.law,
                    detail=(
                        f"held to {relative:.2e} over the run, against a "
                        f"tolerance of "
                        f"{simulate.CONSERVATION_DRIFT_TOLERANCE:g}. The "
                        f"integrator does not know this law exists -- it is "
                        f"the left null space of the stoichiometry over "
                        f"rationals -- so this is an independent check and "
                        f"not a restatement."
                    ),
                    measured={
                        "initial": check.initial,
                        "final": check.final,
                        "worst_drift": check.worst_drift,
                        "relative": relative,
                    },
                )
            )
            continue

        touched = sorted(
            name for name in assigned
            if name and name in check.law.split()
        )
        if touched:
            doubt = (
                f"the LAW, not the integration, in this one case. "
                f"{', '.join(touched)} appear(s) in this law and is written "
                f"by an assignment rule. `stoichiometry_matrix` gives a "
                f"column to every reaction and every rate rule, so those are "
                f"accounted for; an assignment rule overwrites its target "
                f"every step and is not a column, so a conservation derived "
                f"over that species is a claim the dynamics never agreed to. "
                f"Check whether the law should exist before checking the "
                f"solver."
            )
        else:
            doubt = (
                "the integration. This law is exact: it is computed over "
                "`Fraction` from the stoichiometry, with no floating point "
                "and no tolerance anywhere in it, so there is no arithmetic "
                "in it to be wrong. The trajectory is the approximation. "
                "The usual causes are a stiff system integrated with too "
                "loose a relative tolerance, or an output grid so coarse "
                "that the solver is taking steps nobody is looking at. Note "
                "what this rules out: the trajectory is wrong by at least "
                "this much, and the plot of it looks entirely normal."
            )

        findings.append(
            Finding(
                check=CHECK_CONSERVATION,
                severity=CONTRADICTION,
                subject=check.law,
                detail=check.describe(),
                doubt=doubt,
                measured={
                    "initial": check.initial,
                    "final": check.final,
                    "worst_drift": check.worst_drift,
                    "relative": relative,
                },
            )
        )
    return tuple(findings)


# ---------------------------------------------------------------------------
# Check 3: does the trajectory settle as fast as the eigenvalues predict?
# ---------------------------------------------------------------------------


def observed_timescale(
    times: Sequence[float],
    columns: Mapping[str, Sequence[float]],
    state: Mapping[str, float],
    *,
    fraction: float = SETTLING_FRACTION,
) -> Optional[float]:
    """The time constant the trajectory actually approached `state` with.

    Measures when the deviation from `state` first falls to `fraction` of
    what it started at, then DIVIDES BY ln(1/fraction) so the answer is
    comparable with an eigenvalue's reciprocal. Skipping that division is
    the obvious way to write this check wrong: a system whose settling time
    is 10 takes 30 to fall to a twentieth, and comparing 30 against 10 would
    report every correct model as three times slower than predicted.

    The crossing is interpolated in the LOGARITHM of the deviation, which is
    exact for the exponential decay the comparison assumes and removes the
    output grid from the answer -- otherwise the measurement would be
    quantised at the sampling interval and would move when a caller changed
    `points`.

    `None` when the trajectory never gets that close, which is a result and
    not an error: the caller has to distinguish "slower than predicted" from
    "went somewhere else", and both arrive here as `None`.
    """
    if not (0.0 < fraction < 1.0):
        raise ValidationError(
            f"the settling fraction must be strictly between 0 and 1, not "
            f"{fraction!r}. It is the share of the INITIAL deviation the "
            f"trajectory has to fall to, so 1 is satisfied at t=0 and 0 is "
            f"never satisfied at all."
        )
    length = len(times)
    if length < 2:
        return None

    start = _deviation(columns, state, 0)
    if start <= 0.0:
        raise ValidationError(
            "the trajectory starts exactly at the steady state, so there is "
            "no approach to time. Start the model somewhere else, or ask "
            "the fixed-point check instead -- 'does it stay?' is the "
            "question that has an answer here."
        )

    target = fraction * start
    for index in range(1, length):
        here = _deviation(columns, state, index)
        if here > target:
            continue
        before = _deviation(columns, state, index - 1)
        t_before, t_here = float(times[index - 1]), float(times[index])
        if here <= 0.0 or before <= target:
            crossing = t_here
        else:
            span = math.log(before) - math.log(here)
            crossing = t_before + (t_here - t_before) * (
                (math.log(before) - math.log(target)) / span
            )
        return crossing / math.log(1.0 / fraction)
    return None


def settling_verdict(
    observed: Optional[float],
    predicted: float,
    *,
    final_deviation: float,
    initial_deviation: float,
    window: float,
) -> Tuple[str, str, str]:
    """`(severity, detail, doubt)` for one settling-time comparison.

    Split out for the same reason as `fixed_point_verdict`: the branch that
    matters most -- the trajectory going somewhere else entirely -- needs a
    model whose search and whose integrator disagree about the destination,
    and the tests drive it here instead of trying to build one.
    """
    if observed is None:
        if final_deviation >= initial_deviation:
            return (
                CONTRADICTION,
                f"the trajectory did not approach this state at all: it "
                f"starts {initial_deviation:.3g} away and ends "
                f"{final_deviation:.3g} away after t={window:.4g}. The "
                f"eigenvalues at this point say it is stable.",
                "the classification, before the integration. A stable point "
                "attracts everything near it, so a trajectory that leaves is "
                "either starting outside its basin -- in which case the "
                "search and the integrator are describing two different "
                "attractors and `analysis.analyse` has more states than it "
                "reported -- or the Jacobian's eigenvalues are wrong about "
                "this point. Check whether the state the trajectory does "
                "reach appears in the stability report; if it does not, the "
                "search missed it, and the multistart depth is the thing to "
                "raise.",
            )
        return (
            DIVERGENCE,
            f"the trajectory is still {final_deviation / initial_deviation:.3g} "
            f"of its initial deviation away after t={window:.4g}, which is "
            f"{window / predicted:.3g} times the predicted settling time of "
            f"{predicted:.4g}, so no settling time could be measured. It is "
            f"approaching, and more slowly than the linearisation says.",
            "the linearisation as a description of THIS approach, not the "
            "eigenvalue arithmetic. An eigenvalue is a statement about the "
            "neighbourhood of the fixed point, and a trajectory that spends "
            "its time far away is not governed by it. The consequence worth "
            "acting on is in `simulate.choose_window`, which multiplies this "
            "same settling time by SETTLING_MULTIPLES to pick a plot window: "
            "on this model that window cuts the approach off, and the curve "
            "will look as though it had finished.",
        )

    ratio = observed / predicted
    if 1.0 / SETTLING_TOLERANCE_FACTOR <= ratio <= SETTLING_TOLERANCE_FACTOR:
        return (
            AGREE,
            f"the trajectory settles with a time constant of "
            f"{observed:.4g} against the {predicted:.4g} the Jacobian's "
            f"slowest eigenvalue predicts, a ratio of {ratio:.3g}. The "
            f"linearisation is describing the approach the integrator "
            f"actually takes.",
            "",
        )

    if ratio > SETTLING_TOLERANCE_FACTOR:
        return (
            DIVERGENCE,
            f"the trajectory settles with a time constant of "
            f"{observed:.4g}, {ratio:.3g} times the {predicted:.4g} "
            f"predicted from the Jacobian's slowest eigenvalue.",
            "the linearisation, as a description of this approach. The "
            "eigenvalue is a local statement and the trajectory is not "
            "local: it starts far from the fixed point, where the "
            "linearisation does not hold, and the nonlinear part of the "
            "journey is slower. Nothing here says the eigenvalue is wrong "
            "about the tail. It does say that a plot window derived from it "
            "-- which is what `simulate.choose_window` does -- is too short "
            "for this model by about this factor.",
        )

    return (
        DIVERGENCE,
        f"the trajectory settles with a time constant of {observed:.4g}, "
        f"only {ratio:.3g} of the {predicted:.4g} predicted from the "
        f"Jacobian's slowest eigenvalue -- it arrives sooner than the "
        f"linearisation says it should.",
        "the comparison rather than either module. The slowest eigenvalue "
        "governs the TAIL of the approach, and this trajectory reached the "
        "tolerance before that tail became visible, which happens whenever "
        "the initial displacement puts little weight on the slow "
        "eigendirection. The prediction is still right about how the last "
        "of the deviation decays; there was simply not enough of it left to "
        "see. A window derived from the eigenvalue is generous here, which "
        "is the harmless direction to be wrong in. Worth a second look only "
        "if it is much smaller than a factor of a few, which would suggest "
        "the eigenvalue belongs to a direction the dynamics barely use.",
    )


def settling_findings(
    model: Any,
    *,
    point: Any = None,
    points: int = DEFAULT_POINTS,
    window: Optional[float] = None,
    starts_per_species: Optional[int] = None,
) -> Tuple[Finding, ...]:
    """Compare the predicted settling time with the measured one.

    Integrates from the model's DECLARED initial condition, because that is
    the trajectory a reader will actually be shown and the window
    `simulate.choose_window` derives from the same eigenvalue is the window
    it will be shown in. Starting from an artificial small perturbation
    would make the linearisation true by construction and check nothing.
    """
    analysis = _analysis()
    simulate = _simulate()

    if point is None:
        try:
            report = (
                analysis.analyse(model.network)
                if starts_per_species is None
                else analysis.analyse(
                    model.network, starts_per_species=starts_per_species
                )
            )
        except Exception as exc:  # noqa: BLE001
            return (
                Finding(
                    check=CHECK_SETTLING,
                    severity=UNCHECKED,
                    subject=model.network.name,
                    detail=f"the steady-state search did not run: {exc}",
                ),
            )
        stable = report.stable_points
        if len(stable) != 1:
            return (
                Finding(
                    check=CHECK_SETTLING,
                    severity=UNCHECKED,
                    subject=model.network.name,
                    detail=(
                        f"{len(stable)} stable state(s) were found from "
                        f"{report.starts_tried} starting points, and this "
                        f"check needs exactly one: with none there is no "
                        f"settling time to predict, and with several there "
                        f"is no way to know which one the trajectory is "
                        f"heading for without assuming the answer"
                    ),
                ),
            )
        point = stable[0]

    predicted = point.slowest_timescale
    subject = ", ".join(
        f"{name}={value:.4g}" for name, value in sorted(point.state.items())
    )
    if predicted is None:
        return (
            Finding(
                check=CHECK_SETTLING,
                severity=UNCHECKED,
                subject=subject,
                detail=(
                    "every eigenvalue at this state is marginal, so the "
                    "linearisation predicts no settling time and there is "
                    "nothing to compare a measurement with"
                ),
            ),
        )

    end = window if window is not None else SETTLING_WINDOW_MULTIPLES * predicted
    try:
        trajectory = simulate.run(model, end=end, points=points)
    except Exception as exc:  # noqa: BLE001
        return (
            Finding(
                check=CHECK_SETTLING,
                severity=UNCHECKED,
                subject=subject,
                detail=f"the model could not be integrated: {exc}",
            ),
        )

    return settling_findings_from(
        trajectory.times, trajectory.columns, point.state, predicted, window=end
    )


def settling_findings_from(
    times: Sequence[float],
    columns: Mapping[str, Sequence[float]],
    state: Mapping[str, float],
    predicted: float,
    *,
    window: Optional[float] = None,
    fraction: float = SETTLING_FRACTION,
) -> Tuple[Finding, ...]:
    """The comparison, over a trajectory the caller already has.

    Separated from `settling_findings` so the same arithmetic serves a
    caller who integrated once and wants several questions asked of the one
    trajectory -- which is what `validate` does -- and so a test can hand
    over a trajectory whose answer is known in closed form.
    """
    subject = ", ".join(f"{k}={v:.4g}" for k, v in sorted(state.items()))
    end = float(window) if window is not None else float(times[-1])

    # A species with no column would drop out of the deviation norm
    # silently, making the trajectory look closer to the fixed point than
    # it is and the settling time shorter than it is. Refused rather than
    # skipped: a distance measured over some of the coordinates is not a
    # distance.
    absent = [name for name in state if name not in columns]
    if absent:
        return (
            Finding(
                check=CHECK_SETTLING,
                severity=UNCHECKED,
                subject=subject,
                detail=(
                    f"the trajectory carries no column for "
                    f"{', '.join(sorted(absent))}, so the distance to the "
                    f"steady state can only be measured over some of the "
                    f"coordinates. That is not a distance, and a settling "
                    f"time read off it would be too short"
                ),
            ),
        )

    initial = _deviation(columns, state, 0)
    if initial <= 0.0:
        return (
            Finding(
                check=CHECK_SETTLING,
                severity=UNCHECKED,
                subject=subject,
                detail=(
                    "the trajectory starts at the steady state, so there is "
                    "no approach to measure. That is not a failure of the "
                    "prediction; it is the wrong trajectory to ask"
                ),
            ),
        )
    final = _deviation(columns, state, len(times) - 1)
    observed = observed_timescale(times, columns, state, fraction=fraction)

    severity, detail, doubt = settling_verdict(
        observed,
        predicted,
        final_deviation=final,
        initial_deviation=initial,
        window=end,
    )
    return (
        Finding(
            check=CHECK_SETTLING,
            severity=severity,
            subject=subject,
            detail=detail,
            doubt=doubt,
            measured={
                "predicted": float(predicted),
                "observed": float(observed) if observed is not None else float("nan"),
                "initial_deviation": initial,
                "final_deviation": final,
                "window": end,
            },
        ),
    )


# ---------------------------------------------------------------------------
# Check 4: does the fine sensitivity survive a coarse re-solve?
# ---------------------------------------------------------------------------


def sensitivity_verdict(
    fine: float,
    coarse: float,
    refined: float,
    *,
    floor: float,
    span: float,
) -> Tuple[str, str, str]:
    """`(severity, detail, doubt)` for one parameter's two sensitivities.

    THE DISCRIMINATOR IS `refined`. A secant over a finite span is the
    derivative plus a curvature term that falls as the span squared, so
    narrowing the span by `COARSE_REFINEMENT` should cut the gap sixteenfold
    if curvature is all that separates the two numbers. A refined secant
    that walks toward the fine derivative is therefore measuring curvature,
    and both numbers are right about different things. One that does not
    move is disagreeing about the slope itself, and then the fine difference
    -- which divides by a step of a few parts in a million -- is the one
    exposed to the quantity's own noise.
    """
    gap = abs(fine - coarse)
    largest = max(abs(fine), abs(coarse))
    allowed = max(floor, SENSITIVITY_AGREEMENT * largest)

    if largest < floor:
        # A WEAK AGREEMENT, SAID SO. Two numbers below the floor agree
        # because neither of them is being told apart from zero, and
        # reporting that with the same sentence as two independent
        # estimates landing on 1.0 would flatter it. The commonest cause is
        # a conservation law fixing the quantity, which `sensitivity.py`
        # diagnoses by name in `conservation_pinning`; the second is
        # saturation. Either way the finding here is an absence of
        # influence, not a confirmed value.
        return (
            AGREE,
            f"S = {fine:+.4g} locally and {coarse:+.4g} over {span:.0%}, "
            f"both under {floor:.2g} -- the size `sensitivity.py` itself "
            f"declines to send anyone to the bench for. They agree, and the "
            f"agreement is weak: neither number is being told apart from "
            f"zero, so this says neither route found influence rather than "
            f"that the two found the same influence.",
            "",
        )

    if gap <= allowed:
        return (
            AGREE,
            f"S = {fine:+.4g} from a step of a few parts in a million, and "
            f"{coarse:+.4g} from re-solving {span:.0%} away. Two estimates "
            f"that cannot share a rounding error agree to {gap:.2g}.",
            "",
        )

    refined_gap = abs(fine - refined)
    converging = refined_gap <= 0.5 * gap
    opposite_signs = fine * coarse < 0

    if converging:
        return (
            DIVERGENCE,
            f"S = {fine:+.4g} locally and {coarse:+.4g} over {span:.0%}, a "
            f"gap of {gap:.3g}. Narrowing the span to "
            f"{span / COARSE_REFINEMENT:.1%} moves the coarse estimate to "
            f"{refined:+.4g}, closing the gap to {refined_gap:.3g}: the "
            f"difference is curvature, not disagreement.",
            "neither number, and the reading of the fine one. Both are "
            "right about different questions: the local derivative is the "
            f"slope AT these values and the coarse secant is the average "
            f"slope across a {span:.0%} change. `sensitivity.py` already "
            "says its ranking is local; this is that caveat with a size "
            "attached. If the reader intends to move this constant by that "
            "much -- which is less than the spread of published values for "
            "most enzyme constants -- the coarse number is the one that "
            "describes what they would see.",
        )

    if opposite_signs:
        return (
            CONTRADICTION,
            f"S = {fine:+.4g} locally and {coarse:+.4g} over {span:.0%} -- "
            f"OPPOSITE SIGNS. Narrowing the span to "
            f"{span / COARSE_REFINEMENT:.1%} gives {refined:+.4g}, which "
            f"does not move toward the local value, so this is not "
            f"curvature.",
            "the fine difference. It is the estimate exposed to "
            "cancellation: it divides a difference of a few parts in a "
            "million by a step of the same size, so a quantity whose own "
            "accuracy is worse than its declared `precision` returns noise "
            "with an arbitrary sign -- exactly the defect "
            "`sensitivity.SOLVER_PRECISION` exists for, where a settling "
            "time accurate to 1e-8 differentiated with a 1e-6 step reported "
            "0.004 for a true zero. Check the quantity's declared precision "
            "first. The alternative, if the fine value survives that, is a "
            f"response that turns over inside the {span:.0%} span, which "
            "would make the coarse secant the misleading one -- but a "
            "turning point would also have moved the refined estimate, and "
            "it did not.",
        )

    return (
        CONTRADICTION,
        f"S = {fine:+.4g} locally and {coarse:+.4g} over {span:.0%}, a gap "
        f"of {gap:.3g} against an allowance of {allowed:.3g}. Narrowing the "
        f"span to {span / COARSE_REFINEMENT:.1%} gives {refined:+.4g}, "
        f"which does not close the gap, so the two are disagreeing about "
        f"the slope rather than about where it is measured.",
        "the fine difference. Curvature is the innocent explanation for a "
        "gap this size and the refinement has ruled it out: a secant whose "
        "error is curvature shrinks by sixteen when the span shrinks by "
        "four, and this one did not shrink. What is left is the fine "
        "estimate's own arithmetic -- a step too small for the quantity's "
        "true accuracy, or a `precision` declared finer than the quantity "
        "delivers. The coarse estimate re-solves at parameter values "
        f"{span:.0%} apart, where no rounding error is large enough to "
        "matter, which is why it is the one to trust about the magnitude.",
    )


def sensitivity_findings(
    network: Any,
    quantity: Any,
    *,
    parameters: Optional[Sequence[str]] = None,
    unmeasured: Sequence[str] = (),
    span: float = COARSE_SPAN,
    fine: Any = None,
) -> Tuple[Finding, ...]:
    """Check `sensitivity.analyse` against itself at a very different step.

    The coarse estimate is the SAME routine with `step=span`, not a second
    implementation. That is deliberate: a reimplementation would test this
    module's arithmetic against `sensitivity.py`'s, and what is worth
    testing is the STEP -- whether an answer that needs a difference of a
    few parts in a million survives being asked over a change of ten
    percent. Sharing the code makes the step the only difference between
    the two numbers, which is what lets the disagreement be attributed.

    `fine` accepts a report the caller already has, so the expensive half is
    not recomputed -- and so a test can hand over one that has been broken
    on purpose, which is the only honest way to watch this check fail.
    """
    sensitivity = _sensitivity()

    try:
        if fine is None:
            fine = sensitivity.analyse(
                network, quantity, parameters=parameters, unmeasured=unmeasured
            )
        coarse = sensitivity.analyse(
            network, quantity, parameters=parameters, unmeasured=unmeasured,
            step=span,
        )
        refined = sensitivity.analyse(
            network, quantity, parameters=parameters, unmeasured=unmeasured,
            step=span / COARSE_REFINEMENT,
        )
    except Exception as exc:  # noqa: BLE001 - includes SensitivityUnavailable
        return (
            Finding(
                check=CHECK_SENSITIVITY,
                severity=UNCHECKED,
                subject=getattr(quantity, "name", "the quantity"),
                detail=(
                    f"the sensitivity could not be computed, so there is "
                    f"nothing to cross-check: {exc}"
                ),
            ),
        )

    coarse_by_name = {s.parameter: s for s in coarse.sensitivities}
    refined_by_name = {s.parameter: s for s in refined.sensitivities}

    findings: List[Finding] = []
    for row in fine.sensitivities:
        other = coarse_by_name.get(row.parameter)
        narrow = refined_by_name.get(row.parameter)
        if other is None or narrow is None:
            findings.append(
                Finding(
                    check=CHECK_SENSITIVITY,
                    severity=UNCHECKED,
                    subject=row.parameter,
                    detail=(
                        f"the local sensitivity is {row.relative:+.4g}, and "
                        f"re-solving {span:.0%} away did not produce a value "
                        f"to compare it with: "
                        + (
                            coarse.skipped.get(row.parameter)
                            or refined.skipped.get(row.parameter)
                            or "the parameter was not evaluated"
                        )
                    ),
                )
            )
            continue

        # The floor below which this check declines to have an opinion.
        #
        # `row.resolution` is where the fine difference stops being able to
        # tell a sensitivity from its own rounding. `NEGLIGIBLE_INFLUENCE`
        # is `sensitivity.py`'s own judgement about biochemistry: below
        # |S| = 0.01 a constant wrong by half moves the answer by under a
        # percent. Taking the larger of the two makes this check blind to
        # disagreements -- including sign disagreements -- among numbers the
        # ranking already declines to act on. That is a real gap and it is
        # chosen rather than overlooked: a check that fired on the sign of a
        # 1e-8 sensitivity would produce findings nobody can use, on every
        # saturated model in the library, and the report would stop being
        # read before it reached the one that mattered.
        floor = max(row.resolution, sensitivity.NEGLIGIBLE_INFLUENCE)
        severity, detail, doubt = sensitivity_verdict(
            row.relative,
            other.relative,
            narrow.relative,
            floor=floor,
            span=span,
        )
        findings.append(
            Finding(
                check=CHECK_SENSITIVITY,
                severity=severity,
                subject=row.parameter,
                detail=detail,
                doubt=doubt,
                measured={
                    "fine": row.relative,
                    "coarse": other.relative,
                    "refined": narrow.relative,
                    "floor": floor,
                    "span": span,
                },
            )
        )

    if not findings:
        return (
            Finding(
                check=CHECK_SENSITIVITY,
                severity=UNCHECKED,
                subject=fine.quantity,
                detail=(
                    f"no parameter produced a sensitivity to cross-check. "
                    f"{len(fine.skipped)} were skipped by the fine "
                    f"difference"
                    + (
                        ": " + "; ".join(
                            f"{k} ({v})" for k, v in fine.skipped.items()
                        )
                        if fine.skipped
                        else ""
                    )
                ),
            ),
        )
    return tuple(findings)


# ---------------------------------------------------------------------------
# Check 5: does every rate law in the network balance dimensionally?
# ---------------------------------------------------------------------------


def dimension_findings(composition: Any) -> Tuple[Finding, ...]:
    """Every rate law whose units do not balance, with a suspect named.

    The measurement is `builder.Composition.unit_findings`, which is where
    it belongs -- the units are declared per motif and the network has
    forgotten which motif each parameter came from. What this adds is the
    attribution, and the attribution is the awkward part: the two things
    that could be wrong sit side by side in the same motif and the check
    cannot tell them apart.
    """
    try:
        examined, findings = composition.unit_check()
    except Exception as exc:  # noqa: BLE001
        return (
            Finding(
                check=CHECK_DIMENSIONS,
                severity=UNCHECKED,
                subject=getattr(composition, "name", "this composition"),
                detail=f"the dimensional check did not run: {exc}",
            ),
        )

    if not examined:
        # AGREE here would be a cross-check reporting agreement between
        # itself and nothing. UNCHECKED is the same answer this function
        # already gives when the check raises, and for the same reason.
        return (
            Finding(
                check=CHECK_DIMENSIONS,
                severity=UNCHECKED,
                subject=getattr(composition, "name", "this composition"),
                detail=(
                    "no rate law was examined -- this composition declares "
                    "none, so the dimensional check had nothing to run "
                    "against and agreement would mean nothing"
                ),
            ),
        )

    if not findings:
        return (
            Finding(
                check=CHECK_DIMENSIONS,
                severity=AGREE,
                subject=getattr(composition, "name", "this composition"),
                detail=(
                    f"all {examined} rate laws evaluate to an amount per "
                    "volume per time, in the unit the composition declares, "
                    "with the "
                    "units its motifs declare for their own constants. "
                    "Dimensions and SCALE both: mM and uM have the same "
                    "dimensions and differ by a thousand, so a check that "
                    "looked only at dimensions would pass a model that is "
                    "wrong by that factor."
                ),
            ),
        )

    out: List[Finding] = []
    for finding in findings:
        severity_word = getattr(finding, "severity", "blocking")
        out.append(
            Finding(
                check=CHECK_DIMENSIONS,
                severity=CONTRADICTION,
                subject=getattr(finding, "where", "a rate law"),
                detail=f"[{severity_word}] {finding.detail}",
                doubt=(
                    "the motif, and this check cannot say which half of it. "
                    "Two declarations disagree and both are the motif "
                    "author's: the `unit` string on a `MotifParameter` and "
                    "the `rate_law` on the `ReactionTemplate` that uses it. "
                    "A kcat written as `1/s` in a law that needs "
                    "`1/(mM*s)`, and a law missing the concentration that "
                    "would make `1/s` right, produce the same finding. "
                    + (
                        "For a scale mismatch there is a third suspect: the "
                        "composition's `concentration_unit`, which every "
                        "species is measured in, against a constant "
                        "declared with a different prefix. "
                        if severity_word == "scale"
                        else ""
                    )
                    + "What is NOT in doubt is the numbers: unit strings are "
                    "declarations that no rate law reads, so the model will "
                    "integrate and produce a smooth curve either way, wrong "
                    "by whatever the mistake introduced."
                ),
            )
        )
    return tuple(out)


# ---------------------------------------------------------------------------
# All of them, over one model
# ---------------------------------------------------------------------------


def validate(
    model: Any,
    *,
    species: Optional[str] = None,
    parameters: Optional[Sequence[str]] = None,
    points: int = DEFAULT_POINTS,
    max_states: int = MAX_STATES_CHECKED,
    starts_per_species: Optional[int] = None,
) -> ValidationReport:
    """Run every cross-check that this model supports.

    Takes a `ComposedModel` because two of the checks need a trajectory and
    `simulate.run` needs one -- it reads the composition's dimensional
    findings before it will integrate anything, which is a refusal this
    module depends on rather than works around. The individual checks each
    take the smallest thing they need (a network, a composition, a
    trajectory), so a caller holding only one of those can still ask the
    questions that apply to it.

    `species` names the quantity the sensitivity cross-check differentiates.
    There is no default and none is guessed: picking a species would pick
    which of the model's conclusions gets checked, silently, and a reader
    would have no way to tell which one that was. With no species named the
    sensitivity check reports itself unchecked and says this.

    Order is cheapest first, and it matters: a dimensional contradiction
    makes `simulate.run` refuse, so the integration checks come back
    unchecked with the refusal as their reason. That chain is the intended
    behaviour -- integrating a model whose units do not balance produces a
    curve that is wrong by an unknown factor and looks normal.
    """
    analysis = _analysis()
    simulate = _simulate()

    findings: List[Finding] = []
    composition = getattr(getattr(model, "recognition", None), "composition", None)
    if composition is None:
        findings.append(
            Finding(
                check=CHECK_DIMENSIONS,
                severity=UNCHECKED,
                subject=model.network.name,
                detail=(
                    "this model carries no composition, so the units its "
                    "motifs declared are not available. The network alone "
                    "does not record them"
                ),
            )
        )
    else:
        findings.extend(dimension_findings(composition))

    # One steady-state search, shared by the two checks that need it.
    report = None
    try:
        report = (
            analysis.analyse(model.network)
            if starts_per_species is None
            else analysis.analyse(
                model.network, starts_per_species=starts_per_species
            )
        )
    except Exception as exc:  # noqa: BLE001
        for name in (CHECK_FIXED_POINT, CHECK_SETTLING):
            findings.append(
                Finding(
                    check=name,
                    severity=UNCHECKED,
                    subject=model.network.name,
                    detail=f"the steady-state search did not run: {exc}",
                )
            )

    stable = report.stable_points if report is not None else ()

    # One trajectory from the declared initial condition, shared by the
    # conservation and settling checks. Integrating twice would double the
    # cost and, worse, let the two checks disagree about which run they were
    # talking about.
    predicted = (
        stable[0].slowest_timescale if len(stable) == 1 else None
    )
    end = (
        SETTLING_WINDOW_MULTIPLES * predicted
        if predicted is not None
        else simulate.FALLBACK_END
    )
    trajectory = None
    try:
        trajectory = simulate.run(model, end=end, points=points)
    except Exception as exc:  # noqa: BLE001
        findings.append(
            Finding(
                check=CHECK_CONSERVATION,
                severity=UNCHECKED,
                subject=model.network.name,
                detail=(
                    f"the model could not be integrated, so the derived "
                    f"conservation laws have no trajectory to be checked "
                    f"along: {exc}"
                ),
            )
        )
        if report is not None:
            findings.append(
                Finding(
                    check=CHECK_SETTLING,
                    severity=UNCHECKED,
                    subject=model.network.name,
                    detail=f"the model could not be integrated: {exc}",
                )
            )

    if trajectory is not None:
        findings.extend(conservation_findings(model.network, trajectory.columns))

    if report is not None:
        findings.extend(
            fixed_point_findings(
                model,
                report=report,
                points=points,
                max_states=max_states,
                starts_per_species=starts_per_species,
            )
        )

        if trajectory is not None:
            if len(stable) != 1:
                findings.append(
                    Finding(
                        check=CHECK_SETTLING,
                        severity=UNCHECKED,
                        subject=model.network.name,
                        detail=(
                            f"{len(stable)} stable state(s) were found and "
                            f"this check needs exactly one: with none there "
                            f"is no settling time to predict, and with "
                            f"several there is no way to know which one this "
                            f"trajectory is heading for without assuming the "
                            f"answer"
                        ),
                    )
                )
            elif predicted is None:
                findings.append(
                    Finding(
                        check=CHECK_SETTLING,
                        severity=UNCHECKED,
                        subject=model.network.name,
                        detail=(
                            "every eigenvalue at the steady state is "
                            "marginal, so the linearisation predicts no "
                            "settling time"
                        ),
                    )
                )
            else:
                findings.extend(
                    settling_findings_from(
                        trajectory.times,
                        trajectory.columns,
                        stable[0].state,
                        predicted,
                        window=end,
                    )
                )

    if species is None:
        findings.append(
            Finding(
                check=CHECK_SENSITIVITY,
                severity=UNCHECKED,
                subject=model.network.name,
                detail=(
                    "no quantity was named. A sensitivity cross-check needs "
                    "a scalar to differentiate, and choosing one here would "
                    "choose which of this model's conclusions gets checked "
                    "without saying so. Pass `species=`"
                ),
            )
        )
    else:
        sensitivity = _sensitivity()
        findings.extend(
            sensitivity_findings(
                model.network,
                sensitivity.steady_state_of(species),
                parameters=parameters,
                unmeasured=tuple(
                    q.parameter_id for q in getattr(model, "resolvable", ())
                ),
            )
        )

    return ValidationReport(model=model.network.name, findings=tuple(findings))


__all__ = [
    "Finding", "ValidationReport", "ValidationError",
    "validate",
    "fixed_point_findings", "fixed_point_verdict",
    "conservation_findings",
    "settling_findings", "settling_findings_from", "settling_verdict",
    "observed_timescale",
    "sensitivity_findings", "sensitivity_verdict",
    "dimension_findings",
    "residual_at", "state_scale",
    "AGREE", "CONTRADICTION", "DIVERGENCE", "UNCHECKED", "SEVERITIES",
    "CHECK_FIXED_POINT", "CHECK_CONSERVATION", "CHECK_SETTLING",
    "CHECK_SENSITIVITY", "CHECK_DIMENSIONS", "CHECKS",
    "FIXED_POINT_DRIFT_TOLERANCE", "DRIFT_WINDOW_MULTIPLES",
    "SETTLING_FRACTION", "SETTLING_WINDOW_MULTIPLES",
    "SETTLING_TOLERANCE_FACTOR", "COARSE_SPAN", "COARSE_REFINEMENT",
    "SENSITIVITY_AGREEMENT", "MAX_STATES_CHECKED", "DEFAULT_POINTS",
]
