"""Which measurement to make next, and what it would buy.

THE QUESTION THIS ANSWERS
-------------------------
`sensitivity.py` says which constants the answer rests on. Identifiability
says which of them a given set of measurements can recover at all. Neither
tells a researcher what to do on Monday, because both take the experiment as
given and rank things inside it.

The question left over is the one that costs money: of the things this
system could be measured for, which one, measured next, recovers the
unknowns fastest? That is a question about the EXPERIMENT rather than about
the model, and it is the last step of the loop the rest of this package
opens.

RANKED BY INFORMATION ONLY -- READ THIS BEFORE ACTING ON THE RANKING
--------------------------------------------------------------------
Nothing in this module knows what a measurement costs, whether the assay
exists, whether the antibody works, whether the equipment is booked, or how
long any of it takes. A settling time can come out top here and still take
three weeks at the bench while the steady state it beat takes an afternoon.

This module ranks the INFORMATION CONTENT of an observation and nothing
else. The researcher's constraints are not in the model, and a ranking that
pretended otherwise would be worse than no ranking, because it would look
like advice. `DesignReport.summary()` repeats this, deliberately, every
time it is printed.

WHY THE GEOMETRY, AND WHY IT IS REPORTED RATHER THAN SCORED
-----------------------------------------------------------
Each observation has a log-sensitivity vector: one component per target
parameter, each the fractional change in the observation per fractional
change in that parameter. Two facts follow, and they are the whole method.

An observation whose vector is PARALLEL to one already measured adds
nothing. Measuring the steady state of dX/dt = ks - kd*X twice tells you
ks/kd twice. The second measurement tightens the number you have; it does
not tell you a new one.

An observation whose vector is ORTHOGONAL to everything measured so far adds
a whole new direction. The settling time of that same model is 1/kd, whose
vector (0, -1) is 45 degrees off the steady state's (+1, -1). It is that
angle -- not the size of the sensitivity -- that breaks the ks/kd
degeneracy, and after it both constants are recoverable separately.

So the quantity ranked is the length of the part of a candidate's
sensitivity vector that is perpendicular to the span of what has already
been measured. It is reported as an angle, a length and a named combination
of parameters, because "observation B scores 0.71" tells a reader nothing
they can check. "Its vector sits 45 degrees off everything you have, and the
0.71 of it that is new pins the combination `ks +1%, kd +1%`, which your
current measurements cannot see" is checkable by hand, and on this model it
is checkable against the closed-form answer.

WHY THE LENGTH AND NOT ONLY THE ANGLE
-------------------------------------
An observation can be exactly orthogonal to everything and still be useless:
if its whole sensitivity vector has length 1e-9, it raises the matrix rank
on paper and would need an assay nine digits deep to do it in a lab. Ranking
by the angle alone would put that observation first. Ranking by the length
of the new component keeps the two facts multiplied together, which is what
"how much would this actually buy" means. Both are reported; only the length
is ranked on.

THIS WORKS ONLY BECAUSE THE VECTORS ARE DIMENSIONLESS
-----------------------------------------------------
Projecting one sensitivity vector onto another requires their components to
be comparable, and absolute derivatives are not: d(settling time)/d(kcat) is
in seconds per (1/s) and d(settling time)/d(Km) is in seconds per mM, and
their inner product is not a number with a meaning. `sensitivity.py` already
computes the LOGARITHMIC sensitivity for exactly this reason, and every
inner product taken here is between dimensionless vectors. An earlier
version of this reasoning that used absolute derivatives would have produced
a ranking that changed when somebody switched from mM to uM.

THE NOISE FLOOR IS INHERITED, NOT INVENTED
------------------------------------------
Each row comes with the floor `sensitivity.analyse` reports for it -- 4e-10
for a steady state, 5e-5 for anything read off the finite-difference
Jacobian. A residual whose length is under that floor is the arithmetic's
own rounding, projected, and calling it a new direction would manufacture an
experiment out of round-off. `measurement_floor` turns the rows involved
into that bound, by the same derivation `identifiability.py` uses for its
singular-value threshold, so the two modules cannot disagree about what
counts as zero.

WHAT IS NOT HERE
----------------
The amplitude of an oscillation. For a system ringing down to a stable
state, the amplitude is set by how far you displaced it, not by the rate
constants, so it is not a function of the parameters at all and a
sensitivity of it would be a sensitivity of the disturbance. For a sustained
limit cycle the amplitude IS parameter-determined, but computing it needs a
time course integrated onto the cycle, and this module has no MEASURED
accuracy for that number -- and without one it cannot tell a real
sensitivity from the integrator's tolerance. Both cases are reported as
declined candidates naming which of the two applies, rather than silently
omitted. See `_amplitude_decline`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, Iterator, List, Mapping, Optional, Sequence, Tuple

try:
    from .sensitivity import (
        MACHINE_PRECISION, SOLVER_PRECISION, Quantity, SensitivityUnavailable,
        analyse, resolution_for, settling_time, steady_state_of,
        _anchor, _continue_from, _the_one_stable_point,
    )
except ImportError:  # pragma: no cover - flat import
    from sensitivity import (  # type: ignore[no-redef]
        MACHINE_PRECISION, SOLVER_PRECISION, Quantity, SensitivityUnavailable,
        analyse, resolution_for, settling_time, steady_state_of,
        _anchor, _continue_from, _the_one_stable_point,
    )

# The three underscore-prefixed imports are deliberate and are the reason
# this comment exists. `_the_one_stable_point` carries the multistability
# REFUSAL -- two stable states means a derivative describes the choice
# between them -- and `_anchor` / `_continue_from` carry the guarantee that
# both halves of a central difference are about one branch. Re-implementing
# them here would fork a refusal, and a refusal that exists in two copies
# eventually exists in one and a half. The period quantity below needs
# exactly the same contract as `settling_time`, so it uses exactly the same
# machinery.


#: The smallest fraction of the largest weight a parameter must carry before
#: a described direction names it. A JUDGEMENT about readability, not about
#: arithmetic: a twelve-constant cascade produces directions with a long
#: tail of components at 1e-4 of the leader, and printing all of them buries
#: the two that matter. The count of what was dropped is always printed, so
#: nothing disappears silently.
DIRECTION_FLOOR = 0.01


class NoInformativeMeasurement(RuntimeError):
    """No available observation would tell the reader anything new.

    Distinct from a failure. This is a finding: every observation this module
    can construct already lies in the span of what has been measured, so the
    remaining unknowns are not reachable by measuring the same system harder.
    """


class DesignError(ValueError):
    """The design question itself was malformed."""


# ---------------------------------------------------------------------------
# What can be observed
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Observation:
    """One thing a researcher could go and measure on this system."""

    #: Stable identity, so `already_measured` can be given as strings and a
    #: report can be compared against a previous one.
    key: str
    description: str
    #: How to read the number off the model. A `sensitivity.Quantity`, so it
    #: carries its own accuracy and its own branch-following contract.
    quantity: Quantity
    #: What is actually done at the bench, in one line. Method only -- no
    #: instrument, no duration, no cost, because this module does not model
    #: any of those and stating one would imply it did.
    protocol: str = ""


@dataclass(frozen=True)
class DeclinedObservation:
    """Something a reader would expect to be offered, and why it is not.

    Carried rather than omitted. A candidate list with no amplitude in it
    looks like an oversight; a candidate list that says WHY there is no
    amplitude is a statement about the model.
    """

    key: str
    reason: str


@dataclass(frozen=True)
class Candidates:
    """What can be measured, and what was considered and declined.

    Iterates over the offered observations, so `for obs in
    candidate_observations(net)` reads the way it should, while `.declined`
    stays reachable for a report that wants to say what is missing.
    """

    observations: Tuple[Observation, ...]
    declined: Tuple[DeclinedObservation, ...] = ()
    #: What the steady-state search found, in one line. Reported because
    #: whether a period is on the list is a consequence of it.
    finding: str = ""

    def __iter__(self) -> Iterator[Observation]:
        return iter(self.observations)

    def __len__(self) -> int:
        return len(self.observations)

    def __getitem__(self, index: int) -> Observation:
        return self.observations[index]

    def by_key(self, key: str) -> Observation:
        for observation in self.observations:
            if observation.key == key:
                return observation
        raise DesignError(
            f"no observation {key!r} here. Available: "
            f"{', '.join(o.key for o in self.observations) or 'none'}."
        )


def candidate_observations(network: Any) -> Candidates:
    """The things a researcher could actually measure on this model.

    Every species' steady-state concentration, the settling time, and -- when
    the linearisation says the approach rings rather than creeps -- the
    period of that ringing.

    The list depends on what the model DOES, which is why this runs the
    steady-state search rather than offering a fixed menu: a period is not a
    measurable property of a system that does not oscillate, and offering one
    would send somebody to look for a frequency that is not there.

    Refuses nothing. When the search finds no usable state, the observations
    that need one are declined WITH the search's own reason, so the caller
    gets an empty menu that explains itself rather than an exception in the
    middle of building a list.
    """
    observations: List[Observation] = []
    declined: List[DeclinedObservation] = []

    try:
        point = _the_one_stable_point(network)
    except SensitivityUnavailable as exc:
        reason = str(exc)
        return Candidates(
            observations=(),
            declined=tuple(
                [
                    DeclinedObservation(f"steady_state:{s.id}", reason)
                    for s in network.species
                ]
                + [
                    DeclinedObservation("settling_time", reason),
                    DeclinedObservation("oscillation_period", reason),
                    DeclinedObservation(
                        "oscillation_amplitude",
                        "no single stable state was available, so which of "
                        "the two amplitude cases applies could not even be "
                        "decided: " + reason,
                    ),
                ]
            ),
            finding="no unique stable steady state at these values",
        )

    for species in network.species:
        observations.append(
            Observation(
                key=f"steady_state:{species.id}",
                description=f"the steady-state concentration of {species.id}",
                quantity=steady_state_of(species.id),
                protocol=(
                    f"let the system run until it stops changing, then assay "
                    f"{species.id}"
                ),
            )
        )

    observations.append(
        Observation(
            key="settling_time",
            description="the time the system takes to settle",
            quantity=settling_time(),
            protocol=(
                "displace the system and follow it back to rest; the settling "
                "time is the slowest relaxation in that return"
            ),
        )
    )

    oscillatory = _oscillatory_modes(point)
    if oscillatory:
        observations.append(
            Observation(
                key="oscillation_period",
                description="the period of the oscillation",
                quantity=oscillation_period(),
                protocol=(
                    "displace the system and time successive peaks of the "
                    "return; the period is the peak-to-peak interval"
                ),
            )
        )
    else:
        declined.append(
            DeclinedObservation(
                "oscillation_period",
                "no eigenvalue at this state has an imaginary part, so the "
                "approach to steady state does not oscillate and there is no "
                "period to measure. This is a statement about the "
                "linearisation at this state, not about every state the "
                "model can reach.",
            )
        )

    declined.append(_amplitude_decline(point, oscillatory))

    return Candidates(
        observations=tuple(observations),
        declined=tuple(declined),
        finding=(
            f"one stable steady state, {point.classification}"
            + (
                f", with {len(oscillatory)} oscillatory mode(s)"
                if oscillatory
                else ", with no oscillatory mode"
            )
        ),
    )


def _amplitude_decline(point: Any, oscillatory: Sequence[complex]) -> DeclinedObservation:
    """Why the amplitude is not on the menu, in whichever of two ways applies.

    Both are real reasons and they are not the same reason, so they are not
    given the same sentence.
    """
    if not oscillatory:
        return DeclinedObservation(
            "oscillation_amplitude",
            "there is no oscillation at this state to have an amplitude.",
        )
    return DeclinedObservation(
        "oscillation_amplitude",
        "the state is a stable focus, so the system RINGS DOWN rather than "
        "sustaining an oscillation, and the amplitude of that ringing is set "
        "by how far you displaced the system rather than by any rate "
        "constant. A sensitivity of it would be a sensitivity of your own "
        "disturbance. The parameter-determined parts of the same experiment "
        "are the period and the settling time, and both are offered. A "
        "sustained limit cycle would have a parameter-determined amplitude, "
        "but reading it needs a time course integrated onto the cycle and "
        "this module has no measured accuracy for that number -- without one "
        "it cannot separate a real sensitivity from the integrator's "
        "tolerance, so it declines rather than guessing.",
    )


def _oscillatory_modes(point: Any) -> Tuple[complex, ...]:
    marginal = _marginal_eigenvalue()
    return tuple(
        value for value in point.eigenvalues if abs(value.imag) > marginal
    )


def _marginal_eigenvalue() -> float:
    try:
        from .analysis import MARGINAL_EIGENVALUE
    except ImportError:  # pragma: no cover - flat import
        from analysis import MARGINAL_EIGENVALUE  # type: ignore[no-redef]
    return float(MARGINAL_EIGENVALUE)


def oscillation_period() -> Quantity:
    """The period of the oscillation the linearisation predicts.

    2 pi / |Im lambda|, for the oscillatory mode with the LARGEST real part
    -- the one that decays slowest and therefore the one still visible when
    the others have gone. `FixedPoint.describe` reports the SHORTEST period
    instead; that is a different summary statistic for a different purpose
    (it bounds the timestep a plot needs) and the divergence is deliberate.
    An experiment timing peak to peak sees the surviving mode.

    Accurate to `SOLVER_PRECISION` for the same reason the settling time is:
    it comes from an eigenvalue of a finite-difference Jacobian, and
    differentiating it as though it were exact is the mistake recorded in
    `sensitivity.py`'s module docstring.
    """

    def evaluate(network: Any) -> Tuple[float, Any]:
        point = _the_one_stable_point(network)
        return period_of(point), _anchor(network, point)

    def follow(network: Any, anchor: Sequence[float]) -> float:
        return period_of(_continue_from(network, anchor))

    return Quantity(
        evaluate=evaluate,
        follow=follow,
        precision=SOLVER_PRECISION,
        name="oscillation period",
    )


def period_of(point: Any) -> float:
    modes = _oscillatory_modes(point)
    if not modes:
        raise SensitivityUnavailable(
            "no eigenvalue at this state has an imaginary part, so the "
            "linearisation predicts no oscillation and there is no period to "
            "differentiate"
        )
    surviving = max(modes, key=lambda value: value.real)
    return 2.0 * math.pi / abs(surviving.imag)


# ---------------------------------------------------------------------------
# Directions in parameter space
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Direction:
    """A combination of parameters, as a direction in log-parameter space.

    A unit vector whose components are fractional changes: weights of
    (+1, +1) on (ks, kd) mean "multiply both by the same factor", which is
    exactly the move a steady state of ks/kd cannot see.
    """

    weights: Mapping[str, float]

    def describe(self) -> str:
        if not self.weights:
            return "no direction (there are no target parameters)"
        scale = max(abs(w) for w in self.weights.values()) or 1.0
        ordered = sorted(
            self.weights.items(), key=lambda kv: abs(kv[1]), reverse=True
        )
        named = [
            f"{name} {value / scale:+.3g}%"
            for name, value in ordered
            if abs(value) / scale >= DIRECTION_FLOOR
        ]
        dropped = len(ordered) - len(named)
        text = ", ".join(named)
        if dropped:
            text += (
                f" ({dropped} further parameter(s) enter at under "
                f"{DIRECTION_FLOOR:.0%} of the largest weight)"
            )
        return text


def unit_direction(vector: Sequence[float]) -> Tuple[float, ...]:
    """Unit vector, signed so its largest component is positive.

    The sign is arbitrary -- a direction and its negative are the same
    direction -- and fixing it makes two descriptions of the same direction
    read the same, which is what lets a reader see that the combination an
    observation pins IS the combination that was blind.
    """
    length = _norm(vector)
    if length == 0.0:
        return tuple(0.0 for _ in vector)
    scaled = [value / length for value in vector]
    largest = max(range(len(scaled)), key=lambda i: abs(scaled[i]))
    if scaled[largest] < 0:
        scaled = [-value for value in scaled]
    return tuple(scaled)


def measurement_floor(resolutions: Sequence[float], columns: int) -> float:
    """The longest residual that could still be exactly zero.

    sqrt(k * sum_i eps_i^2) over the k parameters and the rows involved. Each
    entry of row i is uncertain by at most that row's noise floor; the
    Frobenius norm bounds the spectral norm of the resulting perturbation;
    Weyl's inequality turns that into a bound on how far the length of any
    residual can have moved. Nothing in it is tuned -- every number comes
    from a quantity's declared accuracy and from the shape of the matrix.

    THE SAME DERIVATION `identifiability.singular_value_threshold` USES, and
    written out here rather than imported from it. A floor that was borrowed
    when that module happened to be importable and computed differently when
    it was not would give the same question two answers in two checkouts,
    which for a result meant to be citable is worse than either answer.
    `_cross_check` compares the two modules' rows when both are present; the
    threshold is not fetched at run time.
    """
    if columns < 1:
        raise DesignError(
            "a floor over no parameters is a floor on nothing. Pass the "
            "constants the measurement is meant to identify."
        )
    total = math.fsum(float(value) * float(value) for value in resolutions)
    if not (math.isfinite(total) and total > 0.0):
        raise DesignError(
            f"the row resolutions {list(resolutions)!r} do not give a "
            f"positive finite floor. A floor of zero would claim the "
            f"arithmetic is exact, and every residual would count as a new "
            f"direction."
        )
    return math.sqrt(columns * total)


def _dot(a: Sequence[float], b: Sequence[float]) -> float:
    return math.fsum(x * y for x, y in zip(a, b))


def _norm(vector: Sequence[float]) -> float:
    return math.sqrt(math.fsum(value * value for value in vector))


def residual_after(vector: Sequence[float], basis: Sequence[Sequence[float]]) -> List[float]:
    """The part of `vector` perpendicular to an orthonormal `basis`.

    Two passes. One pass of Gram-Schmidt leaves a residual contaminated by
    the rounding of the projection itself, which for nearly-parallel vectors
    is the whole answer -- and nearly-parallel is precisely the case this
    module has to get right, because it is what "adds nothing" looks like.
    Re-orthogonalising once is the standard fix and costs one more pass over
    a matrix with at most a few dozen entries.
    """
    residual = list(vector)
    for _ in range(2):
        for row in basis:
            weight = _dot(residual, row)
            residual = [r - weight * b for r, b in zip(residual, row)]
    return residual


def orthonormal_span(
    vectors: Sequence[Sequence[float]], floor: float
) -> Tuple[Tuple[float, ...], ...]:
    """An orthonormal basis for the span, dropping directions under `floor`.

    `floor` is the inherited noise floor, not a numerical epsilon. A row
    whose residual is shorter than it contributes nothing that can be told
    from the arithmetic's own rounding, and admitting it would report a rank
    the data does not support.
    """
    basis: List[Tuple[float, ...]] = []
    for vector in vectors:
        residual = residual_after(vector, basis)
        length = _norm(residual)
        if length > floor:
            basis.append(tuple(value / length for value in residual))
    return tuple(basis)


def blind_directions(
    basis: Sequence[Sequence[float]], names: Sequence[str], floor: float
) -> Tuple[Direction, ...]:
    """Directions in parameter space that `basis` does not span.

    The null space of the measurement matrix: the combinations of parameters
    that can be changed without moving anything measured. These are the
    unidentifiable directions, and naming them is more useful than counting
    them -- "you cannot separate ks from kd" is actionable, "the rank
    deficiency is 1" is not.
    """
    directions: List[Direction] = []
    working = list(basis)
    for index in range(len(names)):
        axis = [1.0 if i == index else 0.0 for i in range(len(names))]
        residual = residual_after(axis, working)
        length = _norm(residual)
        if length > floor:
            unit = tuple(value / length for value in residual)
            working.append(unit)
            directions.append(Direction(dict(zip(names, unit_direction(unit)))))
    return tuple(directions)


# ---------------------------------------------------------------------------
# The sensitivity rows
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SensitivityRow:
    """One observation's log-sensitivity vector over the target parameters."""

    observation: Observation
    parameters: Tuple[str, ...]
    vector: Tuple[float, ...]
    #: The noise floor that applied to this row, from the quantity's own
    #: declared accuracy. Carried per row because a steady state's floor and
    #: a settling time's differ by five orders of magnitude.
    resolution: float
    #: Parameters `sensitivity.analyse` could not differentiate, with the
    #: reason. Their component is zero in `vector`, which is a placeholder
    #: and not a measurement -- see `DesignReport.summary`.
    skipped: Mapping[str, str] = field(default_factory=dict)

    @property
    def length(self) -> float:
        return _norm(self.vector)


def sensitivity_rows(
    network: Any,
    observations: Sequence[Observation],
    parameters: Sequence[str],
) -> Tuple[Tuple[SensitivityRow, ...], Dict[str, str]]:
    """(rows, unavailable). One row per observation that could be computed.

    An observation that refuses -- no stable state, a species that is not in
    the model, a branch that will not continue -- is recorded in
    `unavailable` with its own reason rather than aborting the report. One
    unmeasurable candidate is a fact about that candidate; killing the whole
    ranking over it would lose the other nine.
    """
    rows: List[SensitivityRow] = []
    unavailable: Dict[str, str] = {}
    for observation in observations:
        try:
            report = analyse(
                network,
                observation.quantity,
                quantity_name=observation.description,
                parameters=list(parameters),
            )
        except SensitivityUnavailable as exc:
            unavailable[observation.key] = str(exc)
            continue
        except Exception as exc:  # noqa: BLE001 - one bad candidate, not a bad report
            unavailable[observation.key] = f"could not be computed: {exc}"
            continue

        found = {s.parameter: s.relative for s in report.sensitivities}
        rows.append(
            SensitivityRow(
                observation=observation,
                parameters=tuple(parameters),
                vector=tuple(found.get(name, 0.0) for name in parameters),
                resolution=report.resolution,
                skipped=dict(report.skipped),
            )
        )
    return tuple(rows), unavailable


def _cross_check(
    network: Any,
    observations: Sequence[Observation],
    parameters: Sequence[str],
    rows: Sequence[SensitivityRow],
) -> str:
    """Compare our rows against `identifiability.sensitivity_matrix`, if it is there.

    LAZY AND GUARDED ON PURPOSE. `Terium/compose/identifiability.py` was
    written alongside this module, so the import is inside the function and
    every failure -- the module missing, the call not matching, the shape
    disagreeing -- is recorded as a note rather than raised. Both modules
    build the same object from `sensitivity.analyse`, and two modules that
    are supposed to agree should be able to say whether they do.

    The rows built above are the definition of record either way. This
    function never returns them and never substitutes for them, so a change
    on the other side cannot move a single ranking; it can only fail to
    produce a cross-check, which the note then says.

    THE TWO DISAGREE ABOUT ONE THING ON PURPOSE, and it is not an error:
    `sensitivity_matrix` REFUSES when a parameter's value is zero or an
    observation cannot be evaluated, because a missing row or column silently
    lowers the rank it reports. This module records those and carries on,
    because a menu of ten candidate experiments should not be withheld
    because one of them is unmeasurable. When that happens the cross-check
    does not run and says so.
    """
    try:
        from .identifiability import sensitivity_matrix  # type: ignore
    except ImportError:
        try:
            from identifiability import sensitivity_matrix  # type: ignore[no-redef]
        except ImportError:
            return (
                "cross-check against identifiability.sensitivity_matrix: not "
                "run, that module is not importable here. The rows used are "
                "this module's own and are unaffected."
            )

    try:
        other = sensitivity_matrix(
            network,
            [observation.quantity for observation in observations],
            list(parameters),
        )
        theirs = [list(map(float, row)) for row in getattr(other, "rows", other)]
    except Exception as exc:  # noqa: BLE001 - a cross-check is not a dependency
        return (
            f"cross-check against identifiability.sensitivity_matrix: not "
            f"run ({type(exc).__name__}: {exc}). That module refuses where "
            f"this one records and carries on, so this is expected whenever "
            f"a candidate is unmeasurable or a parameter's value is zero. "
            f"The rows used are this module's own and are unaffected."
        )

    ours = [list(row.vector) for row in rows]
    if len(theirs) != len(ours):
        return (
            f"cross-check against identifiability.sensitivity_matrix: it "
            f"returned {len(theirs)} row(s) where this module built "
            f"{len(ours)}. Not comparable, so not compared."
        )
    worst = 0.0
    for mine, other_row in zip(ours, theirs):
        if len(mine) != len(other_row):
            return (
                "cross-check against identifiability.sensitivity_matrix: row "
                "widths disagree, so not compared."
            )
        worst = max(
            [worst] + [abs(a - b) for a, b in zip(mine, other_row)]
        )
    return (
        f"cross-check against identifiability.sensitivity_matrix: agreed to "
        f"{worst:.2g} at worst."
    )


# ---------------------------------------------------------------------------
# The ranking
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class InformationGain:
    """What one candidate observation would add to what is already measured."""

    observation: Observation
    parameters: Tuple[str, ...]
    #: This observation's log-sensitivity vector.
    sensitivity: Tuple[float, ...]
    #: Length of the part of it perpendicular to the span of what is already
    #: measured. THE RANKED QUANTITY.
    novelty: float
    #: novelty / |sensitivity| -- the sine of the angle to that span. 1 is
    #: exactly orthogonal, 0 exactly parallel. Reported but not ranked on;
    #: see the module docstring.
    independence: float
    angle_degrees: float
    rank_before: int
    rank_after: int
    #: The floor `novelty` had to clear: `measurement_floor` over this row's
    #: resolution and those of the rows already measured. Carried on the row
    #: rather than looked up, because a candidate read off an eigenvalue and
    #: one read off a steady state are judged five orders of magnitude apart.
    floor: float
    #: The parameter combination this observation would newly pin. `None`
    #: when it adds nothing, because there is then no direction to name.
    pins: Optional[Direction]
    skipped: Mapping[str, str] = field(default_factory=dict)

    @property
    def informative(self) -> bool:
        return self.novelty > self.floor

    def describe(self) -> str:
        if not self.informative:
            return (
                f"{self.observation.key}: adds nothing. Its sensitivity "
                f"vector lies in the span of what you have already measured, "
                f"to within this run's floor of {self.floor:.1g} -- the new "
                f"component is {self.novelty:.2g} long. Measuring it would "
                f"tighten numbers you already have and would pin no "
                f"combination you cannot already see."
            )
        pinned = self.pins.describe() if self.pins is not None else "a new direction"
        return (
            f"{self.observation.key}: its sensitivity vector sits "
            f"{self.angle_degrees:.1f} degrees from the span of what you have "
            f"measured, so {self.novelty:.3g} of its length "
            f"({self.independence:.0%} of it) is a direction nothing measured "
            f"so far can see. Rank {self.rank_before} -> {self.rank_after}; "
            f"it pins the combination {pinned}."
        )


@dataclass(frozen=True)
class DesignReport:
    """Every candidate observation, ranked by what it would newly pin."""

    parameters: Tuple[str, ...]
    already_measured: Tuple[str, ...]
    gains: Tuple[InformationGain, ...]
    #: Directions in parameter space the current measurements cannot see.
    blind: Tuple[Direction, ...]
    rank_before: int
    #: Candidates considered and not offered, with the reason.
    declined: Tuple[DeclinedObservation, ...] = ()
    #: Candidates whose quantity could not be computed on this model.
    unavailable: Mapping[str, str] = field(default_factory=dict)
    notes: Tuple[str, ...] = ()

    @property
    def ranked(self) -> Tuple[InformationGain, ...]:
        return tuple(sorted(self.gains, key=lambda g: g.novelty, reverse=True))

    @property
    def informative(self) -> Tuple[InformationGain, ...]:
        return tuple(g for g in self.ranked if g.informative)

    @property
    def best(self) -> Optional[InformationGain]:
        informative = self.informative
        return informative[0] if informative else None

    @property
    def identified(self) -> bool:
        """True when the measurements already taken pin every parameter."""
        return not self.blind

    def summary(self) -> str:
        lines = [
            f"Next measurement, for {len(self.parameters)} target "
            f"parameter(s), given "
            + (
                f"{len(self.already_measured)} already measured "
                f"({', '.join(self.already_measured)})"
                if self.already_measured
                else "nothing measured yet"
            )
            + f". Rank of what you have: {self.rank_before} of "
            f"{len(self.parameters)}."
        ]

        if self.blind:
            lines.append(
                f"{len(self.blind)} parameter combination(s) are invisible to "
                "the measurements taken so far: "
                + "; ".join(d.describe() for d in self.blind)
                + ". Those are the degeneracies a next measurement has to "
                "break."
            )
        else:
            lines.append(
                "Nothing is degenerate: the measurements already taken move "
                "with every target parameter independently, so a further "
                "measurement can only tighten what you have, not pin "
                "something new."
            )

        informative = self.informative
        if informative:
            lines.append("Ranked by how much new direction each one adds:")
            for gain in informative:
                lines.append("  - " + gain.describe())
        uninformative = [g for g in self.ranked if not g.informative]
        if uninformative:
            lines.append(
                f"{len(uninformative)} observation(s) add nothing new: "
                + ", ".join(g.observation.key for g in uninformative)
                + ". Their sensitivity vectors already lie in the span of "
                "what you have measured, so they repeat information rather "
                "than adding it."
            )
        if not self.gains:
            lines.append(
                "No candidate observation could be evaluated at all, so this "
                "is not a finding that nothing would help -- nothing was "
                "measured."
            )

        if self.declined:
            lines.append(
                "Considered and not offered: "
                + "; ".join(f"{d.key} ({d.reason})" for d in self.declined)
            )
        if self.unavailable:
            lines.append(
                "Could not be computed on this model: "
                + "; ".join(f"{k} ({v})" for k, v in self.unavailable.items())
            )

        skipped = sorted(
            {name for gain in self.gains for name in gain.skipped}
        )
        if skipped:
            lines.append(
                f"{len(skipped)} parameter(s) were skipped in at least one "
                f"observation ({', '.join(skipped)}) and carry a zero "
                f"component there. That zero is a placeholder, not a measured "
                f"insensitivity, and it makes the observation look LESS "
                f"informative about those parameters than it may be."
            )

        lines.extend(self.notes)

        lines.append(
            "RANKED BY INFORMATION ONLY. Cost, feasibility, assay "
            "availability and how long a measurement takes are not modelled "
            "here and were not considered. The observation at the top of this "
            "list may take three weeks while the one below it takes an "
            "afternoon; nothing here knows that. Weigh this ranking against "
            "your own constraints -- it is one input to that decision and not "
            "the decision."
        )
        lines.append(
            "Local: every sensitivity here describes the model AT the values "
            "it currently holds, and the placeholders among those values are "
            "what put it there."
        )
        return " ".join(lines)


def rank_observations(
    network: Any,
    parameters: Optional[Sequence[str]] = None,
    *,
    already_measured: Sequence[Any] = (),
    candidates: Optional[Sequence[Observation]] = None,
) -> DesignReport:
    """Rank each candidate observation by how much identifiability it adds.

    `parameters` are the constants you are trying to recover. Defaults to
    every parameter in the network, which is the right default only when
    every one of them is unknown -- a caller holding a `ComposedModel` should
    pass `[q.parameter_id for q in model.resolvable]` instead, because a
    concentration or a Hill exponent is a choice rather than something a
    measurement recovers and including it invents a degeneracy that is not
    there.

    `already_measured` may be observation keys or `Observation` objects.

    The number ranked on is the length of each candidate's sensitivity vector
    perpendicular to the span of the already-measured ones. See the module
    docstring for why that, and for what this ranking deliberately does not
    know.
    """
    names = list(parameters) if parameters is not None else [
        p.id for p in network.parameters
    ]
    if not names:
        raise DesignError(
            "no target parameters, so there is nothing for a measurement to "
            "identify. Pass the constants you are trying to recover -- for a "
            "composed model, the ids of `model.resolvable`."
        )
    known = {p.id for p in network.parameters}
    unknown = [name for name in names if name not in known]
    if unknown:
        raise DesignError(
            f"{unknown} are not parameters of this network. It has: "
            f"{', '.join(sorted(known))}."
        )

    available = candidates if candidates is not None else candidate_observations(network)
    declined = tuple(getattr(available, "declined", ()))
    offered = list(available)
    by_key = {observation.key: observation for observation in offered}

    measured: List[Observation] = []
    for entry in already_measured:
        if isinstance(entry, Observation):
            measured.append(entry)
            continue
        if entry not in by_key:
            raise DesignError(
                f"{entry!r} was given as already measured, but it is not an "
                f"observation of this model. Available: "
                f"{', '.join(sorted(by_key)) or 'none'}. Pass an Observation "
                f"directly if you measured something this module does not "
                f"construct."
            )
        measured.append(by_key[entry])

    candidate_rows, unavailable = sensitivity_rows(network, offered, names)

    # An already-measured observation is usually also a candidate, and
    # differentiating it twice doubles the cost of the whole report for no
    # new number. Reuse the row when the key matches; compute only the
    # observations that were passed in from outside the candidate list.
    computed = {row.observation.key: row for row in candidate_rows}
    outside = [o for o in measured if o.key not in computed]
    extra_rows, extra_unavailable = sensitivity_rows(network, outside, names)
    for key, reason in extra_unavailable.items():
        unavailable.setdefault(key, reason)
    computed.update({row.observation.key: row for row in extra_rows})
    measured_rows = [computed[o.key] for o in measured if o.key in computed]

    # With nothing measured the span is empty and the floor cannot come from
    # its rows, so it falls back to the floor of an exact quantity. Nothing
    # is ever dropped from an empty span, so this only sets the scale for the
    # blind directions, where a unit axis clears any of these by ten orders.
    measured_resolutions = [r.resolution for r in measured_rows] or [
        resolution_for(MACHINE_PRECISION)
    ]
    span_floor = measurement_floor(measured_resolutions, len(names))
    basis = orthonormal_span([r.vector for r in measured_rows], span_floor)
    rank_before = len(basis)
    blind = blind_directions(basis, names, span_floor)

    gains: List[InformationGain] = []
    for row in candidate_rows:
        floor = measurement_floor(
            [row.resolution, *measured_resolutions], len(names)
        )
        residual = residual_after(row.vector, basis)
        novelty = _norm(residual)
        length = row.length
        independence = novelty / length if length > 0 else 0.0
        # Clamped because a residual can exceed its own vector's length by a
        # few ulps, and asin of 1.0000000001 is a ValueError rather than 90
        # degrees.
        angle = math.degrees(math.asin(min(1.0, max(0.0, independence))))
        informative = novelty > floor
        gains.append(
            InformationGain(
                observation=row.observation,
                parameters=tuple(names),
                sensitivity=row.vector,
                novelty=novelty,
                independence=independence,
                angle_degrees=angle,
                rank_before=rank_before,
                rank_after=rank_before + (1 if informative else 0),
                floor=floor,
                pins=(
                    Direction(dict(zip(names, unit_direction(residual))))
                    if informative
                    else None
                ),
                skipped=row.skipped,
            )
        )

    notes = [
        _cross_check(network, offered, names, candidate_rows),
        getattr(available, "finding", "") or "",
    ]
    # A MEASUREMENT THE CALLER HAS AND THIS MODULE CANNOT REPRODUCE.
    #
    # Its row is missing, so it is not in the span and the rank is computed
    # without it. Saying "rank 1" under a header that says "2 already
    # measured" would be two numbers that contradict each other with no
    # sentence between them, and the reader would reasonably believe the
    # bigger one.
    unreproduced = [o.key for o in measured if o.key not in computed]
    if unreproduced:
        notes.insert(
            0,
            f"{len(unreproduced)} observation(s) you have measured could not "
            f"be evaluated on this model ({', '.join(unreproduced)}), so they "
            f"are not in the span and contributed nothing to the rank above. "
            f"That rank is a LOWER bound on what you know -- it is what could "
            f"be checked here, not all you have.",
        )

    return DesignReport(
        parameters=tuple(names),
        already_measured=tuple(o.key for o in measured),
        gains=tuple(gains),
        blind=blind,
        rank_before=rank_before,
        declined=declined,
        unavailable=unavailable,
        notes=tuple(note for note in notes if note),
    )


def best_next_measurement(
    network: Any,
    already_measured: Sequence[Any] = (),
    parameters: Optional[Sequence[str]] = None,
    *,
    candidates: Optional[Sequence[Observation]] = None,
) -> InformationGain:
    """The single observation that most reduces the unidentifiable subspace.

    Raises `NoInformativeMeasurement` when no observation would add anything,
    rather than returning the least useless one. "Measure this, it will not
    help" is not an answer, and a ranking that always names a winner cannot
    tell the reader the interesting case: that the remaining unknowns are not
    reachable by measuring this system harder, and the EXPERIMENT has to
    change.
    """
    report = rank_observations(
        network,
        parameters,
        already_measured=already_measured,
        candidates=candidates,
    )
    best = report.best
    if best is not None:
        return best

    if not report.gains:
        raise NoInformativeMeasurement(
            "no candidate observation could be evaluated on this model, so "
            "nothing can be ranked -- which is not a finding that nothing "
            "would help. "
            + (
                "Reason(s): "
                + "; ".join(f"{k} ({v})" for k, v in report.unavailable.items())
                + ". "
                if report.unavailable
                else ""
            )
            + "Fix what makes the observations uncomputable -- most often no "
            "stable steady state at these values -- and ask again."
        )

    if report.identified:
        raise NoInformativeMeasurement(
            f"every one of the {len(report.parameters)} target parameter(s) "
            f"is already pinned by the {len(report.already_measured)} "
            f"measurement(s) taken: {', '.join(report.already_measured)}. "
            f"There is no unidentifiable subspace left to reduce, so no "
            f"measurement can raise the rank. A further measurement would "
            f"tighten the numbers you have, which is a question about "
            f"precision rather than about identifiability and is not what "
            f"this module ranks."
        )

    raise NoInformativeMeasurement(
        f"none of the {len(report.gains)} available observation(s) would add "
        f"anything: every one of their sensitivity vectors already lies in "
        f"the span of what has been measured, to within this run's noise "
        f"floor. The combination(s) still invisible are "
        + "; ".join(d.describe() for d in report.blind)
        + ", and no observation this module can construct moves along them. "
        "Measuring the same system again will not break that degeneracy -- "
        "change the EXPERIMENT (a different initial condition, a "
        "perturbation, a knockout, a labelled tracer) or accept the "
        "combination as the thing this system actually determines and stop "
        "reporting its factors separately."
    )


__all__ = [
    "DIRECTION_FLOOR",
    "Candidates",
    "DeclinedObservation",
    "DesignError",
    "DesignReport",
    "Direction",
    "InformationGain",
    "NoInformativeMeasurement",
    "Observation",
    "SensitivityRow",
    "best_next_measurement",
    "blind_directions",
    "candidate_observations",
    "measurement_floor",
    "orthonormal_span",
    "oscillation_period",
    "period_of",
    "rank_observations",
    "residual_after",
    "sensitivity_rows",
    "unit_direction",
]
