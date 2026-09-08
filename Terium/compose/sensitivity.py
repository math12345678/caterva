"""Which of the unmeasured constants the answer actually rests on.

THE QUESTION THIS ANSWERS
-------------------------
A three-tier cascade has twelve rate constants and none of them is measured
until somebody names an enzyme. "Go and measure twelve things" is not
advice. "Three of these twelve control the answer and the other nine barely
move it" is, and it is the difference between a model that tells a
researcher what to do next and one that tells them they have a lot of work.

Sensitivity is what turns the gap list into a priority list.

RELATIVE, NOT ABSOLUTE
----------------------
The quantity computed is the logarithmic sensitivity

    S = (dy/dp) * (p/y)

-- the fractional change in the answer per fractional change in the
parameter. Absolute derivatives are not comparable across parameters
measured in different units: dV/d(kcat) is in mM per (1/s) and dV/d(Km) is
in mM per mM, and ranking them against each other is meaningless. The
relative form is dimensionless and IS comparable, which is the whole point
of producing a ranking.

WHAT IT DOES NOT CLAIM
----------------------
That a low-sensitivity parameter does not matter. Sensitivity is local: it
describes the model at the point it was evaluated, and a parameter with
sensitivity 0.01 at the current values can dominate two decades away. The
report says where it was evaluated and does not generalise past it.

Nor does it rank a parameter's IMPORTANCE. A constant with high sensitivity
and a well-known literature value is not a priority; one with modest
sensitivity that nobody has ever measured is. Sensitivity is one of the two
inputs to that judgement and this module computes only that one.

THE STEP IS SET BY THE QUANTITY'S ACCURACY, NOT BY THE FLOAT'S
--------------------------------------------------------------
The first version of this module used one fixed step for everything, on the
usual rule of thumb about machine epsilon. That rule assumes the function
being differentiated is accurate to machine epsilon. Neither of the
quantities here is.

Measured, on dX/dt = ks - kd*X, where both answers are known exactly:

    steady state (= ks/kd)   worst relative error   1.8e-16
    settling time (= 1/kd)   worst relative error   1.0e-08

The steady state is a root solved to a 1e-14 residual on a rate law that
evaluates exactly, so it lands at machine precision. The settling time comes
from an eigenvalue of a FINITE-DIFFERENCE Jacobian, so it carries that
approximation's error -- eight orders of magnitude worse. Differentiating it
with a step of 1e-6 divided a 1e-8 error by a 1e-6 step and reported 0.004
as the sensitivity of a parameter whose true sensitivity is exactly zero.

So the step comes from the quantity. For a central difference the error is
(h^2 / 6) * |third derivative| + eps_f * |f| / h, which is smallest near
h = cbrt(eps_f) and leaves a smallest trustworthy sensitivity of about
eps_f ** (2/3). Both follow from one declared number, `Quantity.precision`;
a plain callable that declares nothing is assumed to be exact.

A CONSEQUENCE WORTH STATING: THE FLOOR MOVES WITH THE QUANTITY
--------------------------------------------------------------
The noise floor cannot be one constant either. At machine precision it is
4e-10; for the settling time it is 5e-5, five orders of magnitude coarser. A
single threshold would either call real settling-time sensitivities noise or
dress settling-time noise up as signal. `SensitivityReport.resolution`
carries the floor that actually applied and the summary prints it, because a
floor means nothing without saying a floor on what.

TWO THRESHOLDS, BECAUSE THERE ARE TWO QUESTIONS
-----------------------------------------------
Deriving that floor exposed a conflation the first version had. It had one
threshold at 1e-6 called NEGLIGIBLE, and a saturated cascade reported eight
constants as having "no measurable influence". With the floor put where the
arithmetic actually is -- 4e-10 -- all eight turned out to have influence of
about 1e-8: entirely real, two orders of magnitude clear of the noise, and
still not worth anyone's week at the bench.

Both facts are worth reporting and they are not the same fact:

    unresolvable   |S| < resolution           the arithmetic cannot tell
                                              this from its own rounding
    negligible     |S| < NEGLIGIBLE_INFLUENCE real, measured, and too
                                              small to act on

The first is about floating point and moves with the quantity. The second is
a judgement about biochemistry and does not. Reporting a real 1e-8 as "no
measurable influence" overstates what was found; reporting it without saying
it is too small to chase understates what the reader should do. The summary
says both, separately.

The same number decides `dominant`. |S| = 1 is the commonest exact answer
there is -- every first-order rate constant has it -- and the arithmetic
lands on either side of 1.0 by a few parts in 1e11. Comparing with `>=` made
the classification of the most ordinary case in biochemistry a coin flip on
the last digit, so the comparison is made with the resolution as slack.

WHAT THE MULTISTABILITY REFUSAL IS AND IS NOT
---------------------------------------------
`steady_state_of` refuses when the search finds more than one stable state,
because a derivative through a choice between attractors describes the
choice. That refusal is only as good as the search, and this is measured,
not assumed. Stable states found, by starting points per species:

    toggle switch         4 -> 1 (WRONG, it is bistable)   8 -> 2
    two-enzyme competition   8 -> 1 (WRONG)               16 -> 2

The first row is why these quantities no longer search below the analysis
module's measured default. The second is why the report says a single stable
state is a search result rather than a proof: at the default depth a real
five-species model still reports one state when it has two, and no number of
starting points turns "did not find another" into "there is not another".
"""

from __future__ import annotations

import math
import sys
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

#: Relative accuracy of a quantity that evaluates in floating point with no
#: iteration behind it. The floor nothing can beat.
MACHINE_PRECISION = sys.float_info.epsilon

#: Relative accuracy of a quantity read off an eigenvalue of the analysis
#: module's finite-difference Jacobian. MEASURED, not assumed: the settling
#: time of dX/dt = ks - kd*X is exactly 1/kd, and over a sweep of ks the
#: computed value was wrong by at most 1.0e-8 relative. Rounded up to a
#: round number because the measurement is one model's, and a precision
#: claimed finer than it was measured is the error this constant exists to
#: prevent.
SOLVER_PRECISION = 1e-8

#: How many times the theoretical noise floor a sensitivity must clear
#: before it is believed. eps_f ** (2/3) is where the two error terms
#: balance for a TYPICAL third derivative, not a bound on either: the
#: measured steady-state error came in at 1.4x it. A safety factor of ten
#: costs four significant figures nobody reads and buys the difference
#: between a floor and a wish.
SAFETY = 10.0


def step_for(precision: float) -> float:
    """The fractional step a central difference should take.

    Balances truncation, which grows as h^2, against cancellation, which
    grows as eps_f / h. A RELATIVE step, because these parameters span
    decades and one absolute step cannot serve a kcat of 1e4 and a Km of
    1e-3 at once.
    """
    return float(precision) ** (1.0 / 3.0)


def resolution_for(precision: float) -> float:
    """The smallest |S| worth reporting for a quantity of this accuracy.

    Below this the central difference is returning the quantity's own error
    divided by the step. Printing it as a sensitivity invites a reader to
    believe a number that is entirely method.
    """
    return SAFETY * float(precision) ** (2.0 / 3.0)


#: The default step, for a quantity that declares no precision.
RELATIVE_STEP = step_for(MACHINE_PRECISION)

#: The default floor. Note this is the floor for an EXACT quantity; the one
#: that actually applied to a given result is `SensitivityReport.resolution`,
#: and for the settling time it is five orders of magnitude coarser.
NEGLIGIBLE = resolution_for(MACHINE_PRECISION)

#: A sensitivity at or above this is called dominant in the summary. A
#: JUDGEMENT: |S| = 1 means the answer moves proportionally with the
#: parameter, which is the natural place to draw the line, and anything
#: above it amplifies. Compared against with the resolution as slack -- see
#: the module docstring on why an exact 1 must not be a coin flip.
DOMINANT = 1.0

#: Below this |S| the influence is real but too small to act on. A
#: JUDGEMENT ABOUT BIOCHEMISTRY, and not the same claim as `resolution`.
#:
#: Enzyme constants are rarely known to better than +/-20%, so at |S| = 0.01
#: even a parameter that is wrong by half moves the answer by half a
#: percent -- well under the uncertainty the model's own structure carries,
#: and far under anything an assay would resolve. Telling a researcher to go
#: and measure that constant would be sending them to the bench for a digit
#: nobody could see.
#:
#: Kept separate from `resolution` because they answer different questions
#: and conflating them cost this module a real finding. With one threshold
#: at 1e-6, a saturated cascade reported eight constants as having "no
#: measurable influence"; the truth is that their influence is about 1e-8,
#: which is entirely real, sits far above the arithmetic's own floor, and is
#: still not worth a week of anyone's time. "Cannot be told from rounding"
#: and "too small to act on" are different facts and must not share a word.
NEGLIGIBLE_INFLUENCE = 0.01


class SensitivityUnavailable(RuntimeError):
    """The quantity of interest could not be computed at the base point."""


@dataclass(frozen=True)
class Sensitivity:
    """How much one answer moves when one parameter moves."""

    parameter: str
    value: float
    relative: float
    #: The absolute derivative, kept because a reader checking the
    #: arithmetic needs it and because it is the only form with units.
    absolute: float
    #: The noise floor that applied to THIS number, from the quantity's own
    #: precision. Carried on the row rather than looked up from a module
    #: constant so that a row cannot be judged by a threshold belonging to a
    #: different quantity.
    resolution: float = NEGLIGIBLE

    @property
    def unresolvable(self) -> bool:
        """Below the arithmetic's own floor. Says nothing about biology.

        The number returned here is the quantity's error divided by the
        step. It is not a small sensitivity; it is not a sensitivity.
        """
        return abs(self.relative) < self.resolution

    @property
    def negligible(self) -> bool:
        """Too small to act on -- a judgement, and a different one.

        A sensitivity can be far above `resolution` and still be here: the
        saturated cascade's upstream constants sit at about 1e-8, which is
        real, measurable, and not worth anybody's week.
        """
        return abs(self.relative) < NEGLIGIBLE_INFLUENCE

    @property
    def dominant(self) -> bool:
        # With the resolution as slack: an exact 1 lands on either side of
        # 1.0 by a few parts in 1e11, and every first-order rate constant
        # has an exact 1.
        return abs(self.relative) >= DOMINANT - self.resolution

    def describe(self) -> str:
        if self.unresolvable:
            return (
                f"{self.parameter}: below this run's noise floor of "
                f"{self.resolution:.1g} -- the arithmetic cannot tell its "
                f"influence from its own rounding, which is not the same as "
                f"having none"
            )
        if self.negligible:
            return (
                f"{self.parameter}: S = {self.relative:+.2g}, negligible -- "
                f"real, but a constant wrong by half would move the answer "
                f"by {abs(self.relative) * 50:.2g}%, under anything an assay "
                f"would resolve"
            )
        direction = "raises" if self.relative > 0 else "lowers"
        return (
            f"{self.parameter}: S = {self.relative:+.3g} "
            f"(a 1% increase {direction} the answer by "
            f"{abs(self.relative):.2g}%)"
        )


@dataclass(frozen=True)
class SensitivityReport:
    quantity: str
    base_value: float
    sensitivities: Tuple[Sensitivity, ...]
    #: Parameters that could not be evaluated, with the reason.
    skipped: Mapping[str, str] = field(default_factory=dict)
    #: Which of the parameters have no measured value behind them.
    unmeasured: Tuple[str, ...] = ()
    #: The smallest |S| this run could tell apart from its own arithmetic.
    resolution: float = NEGLIGIBLE
    #: The fractional step taken. Reported because it and the resolution are
    #: the two numbers a reader needs to reproduce any row here.
    step: float = RELATIVE_STEP

    @property
    def ranked(self) -> Tuple[Sensitivity, ...]:
        return tuple(
            sorted(self.sensitivities, key=lambda s: abs(s.relative), reverse=True)
        )

    @property
    def dominant(self) -> Tuple[Sensitivity, ...]:
        return tuple(s for s in self.ranked if s.dominant)

    def priorities(self) -> Tuple[Sensitivity, ...]:
        """Unmeasured parameters, most influential first.

        The actionable list: of the constants nobody has measured, these are
        the ones the answer depends on. A researcher deciding what to do at
        the bench reads this and nothing else.
        """
        unmeasured = set(self.unmeasured)
        return tuple(s for s in self.ranked if s.parameter in unmeasured)

    def summary(self) -> str:
        lines = [
            f"Sensitivity of {self.quantity} (= {self.base_value:.6g}) to "
            f"{len(self.sensitivities)} parameter(s), as fractional change "
            f"per fractional change."
        ]

        ranked = [s for s in self.ranked if not s.negligible]
        if ranked:
            lines.append("Ranked:")
            for entry in ranked:
                lines.append("  - " + entry.describe())
        negligible = [
            s for s in self.sensitivities if s.negligible and not s.unresolvable
        ]
        if negligible:
            lines.append(
                f"{len(negligible)} parameter(s) influence the answer too "
                f"little to act on (|S| < {NEGLIGIBLE_INFLUENCE:g}): "
                + ", ".join(s.parameter for s in negligible)
                + ". Their influence is real and was measured; at that size "
                "a constant wrong by half moves the answer by under a "
                "percent, which is below what the model's own structure is "
                "worth."
            )

        unresolvable = [s for s in self.sensitivities if s.unresolvable]
        if unresolvable:
            lines.append(
                f"{len(unresolvable)} parameter(s) came back below this "
                f"run's noise floor of {self.resolution:.1g}: "
                + ", ".join(s.parameter for s in unresolvable)
                + ". That is a statement about the arithmetic, not about "
                "biology -- the influence could not be told from rounding, "
                "which is not the same as having none."
            )

        priorities = [s for s in self.priorities() if not s.negligible]
        if priorities:
            lines.append(
                "Of the constants nobody has measured, the answer depends "
                "most on: "
                + ", ".join(s.parameter for s in priorities[:5])
                + ". Measuring those first buys more than measuring the "
                "others, which is a different statement from saying the "
                "others do not matter."
            )
        elif self.unmeasured:
            # NOT silence. An empty priority list is a finding: at these
            # values the answer does not rest on any unmeasured constant, so
            # measuring is not what would improve it. Omitting the paragraph
            # would read as "the ranking had nothing to say", which is the
            # opposite of what was found.
            lines.append(
                f"None of the {len(self.unmeasured)} unmeasured constant(s) "
                f"influences this answer by |S| >= {NEGLIGIBLE_INFLUENCE:g} "
                f"at these values, so measuring any one of them would not "
                f"move it. That is a property of where the model currently "
                f"sits -- a saturated mechanism is insensitive to almost "
                f"everything upstream of the saturation -- and not a "
                f"licence to leave the constants unmeasured, because it is "
                f"the placeholders themselves that put the model here."
            )

        if self.skipped:
            lines.append(
                f"{len(self.skipped)} parameter(s) were skipped: "
                + "; ".join(f"{k} ({v})" for k, v in self.skipped.items())
                + "."
            )

        lines.append(
            "Local: these describe the model AT the values it currently "
            "holds. A parameter with a small sensitivity here can dominate "
            "two decades away, and nothing here says otherwise."
        )
        return " ".join(lines)


def analyse(
    network: Any,
    quantity: Callable[[Any], float],
    *,
    quantity_name: Optional[str] = None,
    parameters: Optional[Sequence[str]] = None,
    unmeasured: Sequence[str] = (),
    step: Optional[float] = None,
    precision: Optional[float] = None,
) -> SensitivityReport:
    """Relative sensitivity of `quantity(network)` to each parameter.

    `quantity` is a callable rather than a name so this can rank against
    anything the caller cares about -- a steady-state concentration, a
    settling time, the amplitude of an oscillation. A fixed vocabulary of
    supported outputs would be a list to keep in sync with what people
    actually ask.

    A `Quantity` brings its own accuracy, and the step and the noise floor
    follow from it. A plain callable is taken to be exact, which is the
    optimistic assumption -- but it is the caller's own function, `precision`
    overrides it, and the alternative is silently differentiating everything
    as though it were the worst case.
    """
    precision = float(
        precision
        if precision is not None
        else getattr(quantity, "precision", MACHINE_PRECISION)
    )
    if not (0.0 < precision < 1.0):
        raise ValueError(
            f"precision must be a relative accuracy strictly between 0 and "
            f"1, not {precision!r}. It is the fractional error in the "
            f"quantity, not an absolute tolerance."
        )
    step = float(step) if step is not None else step_for(precision)
    resolution = resolution_for(precision)
    if quantity_name is None:
        quantity_name = getattr(quantity, "name", None) or "the quantity of interest"

    names = list(parameters) if parameters is not None else [
        p.id for p in network.parameters
    ]
    known = {p.id: float(p.value) for p in network.parameters}
    unknown = [name for name in names if name not in known]
    if unknown:
        raise KeyError(
            f"{unknown} are not parameters of this network. It has: "
            f"{', '.join(sorted(known))}."
        )

    try:
        if isinstance(quantity, Quantity):
            base_value, anchor = quantity.evaluate(network)
            base = float(base_value)
        else:
            base, anchor = float(quantity(network)), None
    except Exception as exc:  # noqa: BLE001
        raise SensitivityUnavailable(
            f"the quantity could not be computed at the base point, so "
            f"there is nothing to differentiate: {exc}"
        ) from exc

    # Every perturbed evaluation continues from the base state, so both
    # halves of a central difference are provably about one branch. A
    # quantity with no anchor is simply re-evaluated.
    if isinstance(quantity, Quantity) and quantity.follow is not None and anchor is not None:
        follow = quantity.follow

        def at(net: Any) -> float:
            return float(follow(net, anchor))
    else:
        def at(net: Any) -> float:
            return float(quantity(net))
    if not math.isfinite(base):
        raise SensitivityUnavailable(
            f"the quantity is {base} at the base point"
        )

    results: List[Sensitivity] = []
    skipped: Dict[str, str] = {}

    for name in names:
        value = known[name]
        if value == 0.0:
            # A relative step around zero is zero. An absolute step would
            # work and would answer a different question -- the RELATIVE
            # sensitivity is undefined at p = 0, because the fractional
            # change in the parameter is undefined.
            skipped[name] = "its value is zero, so a fractional change in it is undefined"
            continue

        h = abs(value) * step
        try:
            up = at(_with(network, name, value + h))
            down = at(_with(network, name, value - h))
        except Exception as exc:  # noqa: BLE001
            skipped[name] = f"could not be evaluated when perturbed: {exc}"
            continue
        if not (math.isfinite(up) and math.isfinite(down)):
            skipped[name] = "the quantity is not finite when this parameter is perturbed"
            continue

        derivative = (up - down) / (2 * h)
        relative = derivative * value / base if base != 0 else float("inf")
        if not math.isfinite(relative):
            skipped[name] = "the base value is zero, so a relative sensitivity is undefined"
            continue

        results.append(
            Sensitivity(
                parameter=name, value=value,
                relative=relative, absolute=derivative,
                resolution=resolution,
            )
        )

    return SensitivityReport(
        quantity=quantity_name,
        base_value=base,
        sensitivities=tuple(results),
        skipped=skipped,
        unmeasured=tuple(unmeasured),
        resolution=resolution,
        step=step,
    )


def _with(network: Any, parameter: str, value: float) -> Any:
    from dataclasses import replace

    return replace(
        network,
        parameters=tuple(
            replace(p, value=float(value)) if p.id == parameter else p
            for p in network.parameters
        ),
    )


# ---------------------------------------------------------------------------
# Ready-made quantities
# ---------------------------------------------------------------------------

#: Starting points per species for the steady-state search behind these
#: quantities. MEASURED. The analysis module's own default is 8, and these
#: quantities previously passed 4 to be quick, which cost the refusal below
#: its meaning: at 4 the toggle switch reports ONE stable state when it has
#: two, so a derivative would have been taken straight through a bistable
#: system without a word. At 8 the toggle is right and the five-species
#: competition model is still wrong; at 16 both are right.
#:
#: 16 is therefore a measured floor for the models in the library, not a
#: proof for models outside it. Nothing here can turn "did not find another"
#: into "there is not another", which is why `steady_state_of` reports the
#: depth it searched instead of implying a guarantee.
STARTS_PER_SPECIES = 16


@dataclass(frozen=True)
class Quantity:
    """A scalar read off a model, how accurately it is known, and where.

    THE ACCURACY. `analyse` sets its step and its noise floor from
    `precision`, so a quantity computed through an iterative solver is
    differentiated differently from one computed exactly -- see the module
    docstring for the measurement that forced this.

    THE ANCHOR, which is a correctness matter and not only a speed one.
    `evaluate` returns the value together with the state it was read at, and
    `follow` recomputes the value from that state after a parameter has
    moved a fraction of a percent. Without it every perturbed evaluation
    repeats the whole global multistart search, and a global search does not
    promise to return the same branch twice: the difference quotient would
    then be the gap between two different steady states divided by a tiny
    step, which is not a derivative of anything. Anchoring makes the two
    evaluations of a central difference provably about one branch.

    It is also what makes this affordable. Ranking twelve constants costs
    twenty-five evaluations; at 16 starting points per species on a
    six-species cascade the unanchored version ran thousands of global
    solves and did not finish.
    """

    #: (network) -> (value, anchor). The anchor is opaque to `analyse` and
    #: is only ever handed back to `follow`.
    evaluate: Callable[[Any], Tuple[float, Any]]
    #: (network, anchor) -> value, continuing from the anchor. `None` for a
    #: quantity with no branch to follow, which is then simply re-evaluated.
    follow: Optional[Callable[[Any, Any], float]]
    #: Relative accuracy. See MACHINE_PRECISION / SOLVER_PRECISION.
    precision: float
    name: str

    def __call__(self, network: Any) -> float:
        return self.evaluate(network)[0]


def steady_state_of(species: str) -> "Quantity":
    """A species' concentration at the stable steady state.

    Raises when there is no unique stable state, rather than picking one:
    differentiating through a choice between two attractors produces a
    number that describes the choice rather than the model.

    Exact to machine precision. The root is solved to a 1e-14 residual on a
    rate law that evaluates in floating point with nothing iterative in it,
    and the measurement in the module docstring confirms it: 1.8e-16 against
    the analytic ks/kd.
    """
    def evaluate(network: Any) -> Tuple[float, Any]:
        point = _the_one_stable_point(network)
        return _read(point, species), _anchor(network, point)

    def follow(network: Any, anchor: Sequence[float]) -> float:
        return _read(_continue_from(network, anchor), species)

    return Quantity(
        evaluate=evaluate,
        follow=follow,
        precision=MACHINE_PRECISION,
        name=f"steady-state {species}",
    )


def settling_time() -> "Quantity":
    """How long the system takes to reach its steady state.

    Accurate to `SOLVER_PRECISION`, not to machine precision, and that is
    not a detail: the value is 1 / |smallest eigenvalue real part| of a
    Jacobian the analysis module builds by finite differences, so it
    inherits that approximation's error. Measured at 1.0e-8 against the
    analytic 1/kd, eight orders of magnitude short of the steady state's.
    Differentiating it as though it were exact is what produced a
    sensitivity of 0.004 for a parameter the settling time does not depend
    on at all.
    """
    def evaluate(network: Any) -> Tuple[float, Any]:
        point = _the_one_stable_point(network)
        return _timescale(point), _anchor(network, point)

    def follow(network: Any, anchor: Sequence[float]) -> float:
        return _timescale(_continue_from(network, anchor))

    return Quantity(
        evaluate=evaluate,
        follow=follow,
        precision=SOLVER_PRECISION,
        name="settling time",
    )


# -- the search, and the continuation from it -------------------------------


def _stability_module() -> Any:
    try:
        from . import analysis  # type: ignore
    except ImportError:  # pragma: no cover - flat import
        import analysis  # type: ignore[no-redef]
    return analysis


def _the_one_stable_point(network: Any) -> Any:
    """The unique stable steady state, or a refusal naming the ambiguity.

    The global search, at the depth `STARTS_PER_SPECIES` documents. This is
    where the refusal lives, so it runs once per report -- at the base point
    -- and the perturbed evaluations continue from what it found.
    """
    report = _stability_module().analyse(
        network, starts_per_species=STARTS_PER_SPECIES
    )
    stable = report.stable_points
    if not stable:
        raise SensitivityUnavailable(
            f"no stable steady state at these values, from "
            f"{report.starts_tried} starting points, so there is no "
            f"steady-state quantity to differentiate"
        )
    if len(stable) > 1:
        # Two possibilities, and the message must not pick one.
        #
        # Genuine multistability -- a toggle switch -- where the states are
        # separated by a saddle and the system rests in one of them. Or a
        # CONTINUUM: the competition model consumes its substrate
        # completely, after which both rates are zero and every split of the
        # products summing to the conserved total is a fixed point. The
        # second is not a choice between attractors at all; it is a line of
        # them, and which point is reached is decided by the transient
        # rather than by the equations at rest.
        #
        # Either way a derivative is undefined, and calling the second one
        # "attractors" would describe the wrong thing.
        raise SensitivityUnavailable(
            f"{len(stable)} stable states at these values, so a "
            f"steady-state derivative is undefined. This is either "
            f"genuine multistability -- states separated by a saddle -- "
            f"or a continuum, which is what a model that consumes its "
            f"substrate completely has: once the rates are zero every "
            f"split of the products is a fixed point, and which one is "
            f"reached is decided by the transient rather than by the "
            f"equations at rest. Ask for a time course instead."
        )
    return stable[0]


def _anchor(network: Any, point: Any) -> Tuple[float, ...]:
    """A fixed point as a starting vector, in the network's species order.

    Ordered by the network rather than by the state mapping, because
    `analysis.analyse` reads its starts positionally and a dictionary that
    happened to iterate differently would place each concentration on the
    wrong species -- a solve that converges to a confident wrong answer.
    """
    return tuple(float(point.state[s.id]) for s in network.species)


def _continue_from(network: Any, anchor: Sequence[float]) -> Any:
    """The same branch, after the parameters moved a fraction of a percent.

    A LOCAL solve from one starting point, not a global search. Both halves
    of a central difference are then provably about the branch the base
    point was on -- a global search makes no such promise, and the quotient
    of two different steady states over a tiny step is not a derivative.

    Refuses rather than falling back to a global search when the local solve
    does not converge. A fallback would silently turn the one case this
    function exists to prevent -- landing on another branch -- back on, and
    at exactly the moment it is most likely: the continuation failing is
    itself evidence the branch is doing something interesting.

    THE ANCHOR WINS BY POSITION, WHICH IS WORTH KNOWING. `analysis.analyse`
    tries `extra_starts` before any generated ones and `found` is built in
    start order, so the anchor's root is `fixed_points[0]` whenever it
    converges. That makes the zero here a statement of intent rather than
    the only thing holding the branch: adding global starts back alongside
    the anchor would waste time without changing the answer. Found by a
    mutation that did exactly that and came back NOT CAUGHT -- correctly,
    because it changed nothing. The mutation that does break this removes
    the anchor, and is the one recorded against ADR 0175.
    """
    report = _stability_module().analyse(
        network, starts_per_species=0, extra_starts=[list(anchor)]
    )
    points = report.fixed_points
    if not points:
        raise SensitivityUnavailable(
            "the steady state could not be continued after a parameter was "
            "perturbed by a fraction of a percent. Either the branch ends "
            "near these values -- a fold -- or the solve is struggling; "
            "either way a derivative here would not describe a branch. Try "
            "a sweep, which is built to cross folds."
        )
    return points[0]


def _read(point: Any, species: str) -> float:
    if species not in point.state:
        raise SensitivityUnavailable(
            f"no species {species!r} in this model. It has: "
            f"{', '.join(sorted(point.state))}."
        )
    return float(point.state[species])


def _timescale(point: Any) -> float:
    value = point.slowest_timescale
    if value is None:
        raise SensitivityUnavailable(
            "every eigenvalue at this state is marginal, so no settling "
            "time is defined -- the linearisation says nothing about how "
            "fast the system approaches"
        )
    return float(value)


def rank_unmeasured(model: Any, species: str) -> SensitivityReport:
    """The actionable report: which unmeasured constant to go and measure.

    Takes a `ComposedModel` so the unmeasured set comes from the model's own
    account of what it could not resolve, rather than from the caller
    guessing.
    """
    return analyse(
        model.network,
        steady_state_of(species),
        unmeasured=tuple(q.parameter_id for q in model.resolvable),
    )


__all__ = [
    "Quantity", "Sensitivity", "SensitivityReport", "SensitivityUnavailable",
    "analyse", "steady_state_of", "settling_time", "rank_unmeasured",
    "step_for", "resolution_for",
    "MACHINE_PRECISION", "SOLVER_PRECISION", "SAFETY",
    "RELATIVE_STEP", "NEGLIGIBLE", "NEGLIGIBLE_INFLUENCE", "DOMINANT",
    "STARTS_PER_SPECIES",
]
