"""Estimating a constant from data, and the uncertainty that estimate carries.

WHAT COMES OUT OF HERE IS NOT A LITERATURE VALUE
------------------------------------------------
Every other module in this package asks the literature for a constant and
refuses when nobody has measured it. This one is the other door: the caller
measured something themselves -- a time course, a plateau, a response at
several inputs -- and wants the constants that best reproduce it.

A number produced here is evidence from the caller's own dataset, and its
provenance is "fitted to N observations, under these conditions, ASSUMING
THIS MODEL". That is a different kind of claim from a measured kcat, and it
is a weaker one: it is conditional on a model the fit cannot check. A fitted
12.4 and a measured 12.4 print identically, so every report here says which
it is. Nothing in this module may be recorded as literature-backed.

WHY AN OBSERVATION CANNOT EXIST WITHOUT AN ERROR BAR
----------------------------------------------------
`Observation` refuses to be constructed without an uncertainty, and that
refusal is the load-bearing decision in the module.

Weighted least squares needs the weights. Without them there are two
choices and both fabricate. Weighting everything equally declares that a
0.01 mM reading and a 100 mM reading are equally precise, which hands every
parameter to whichever measurement happens to be the largest number in the
file. Inventing a plausible sigma -- 5% of the value, say -- puts a number
nobody measured directly into the confidence interval, where it is
indistinguishable from the data.

There is a third reason, and it is the one that decides it: everything this
module reports is expressed in units of the stated errors. The chi-squared
statement asks whether the residual is the size the error bars predicted.
The confidence intervals are the widths those error bars imply. A dataset
without them has no scale in which "the fit is good" means anything at all,
so the fit would produce numbers and no way to judge them.

If the uncertainty is genuinely unknown, that is a fact about the
experiment, and the answer is to state the replicate spread or the
instrument's precision -- not to let this module choose one.

WHY THE FIT IS DONE IN LOG PARAMETER SPACE
------------------------------------------
Three reasons, in increasing order of importance.

Rate constants are positive. In linear space nothing stops the optimiser
proposing kd = -0.3, which is not a slow reaction, it is not a reaction; the
integrator then either fails or returns a growing exponential and the
optimiser reads that as information. In log space the positivity is
structural rather than a bound that the search can sit on.

They span decades. One trust-region step cannot serve a kcat of 1e4 and a Km
of 1e-3 at once, and a step that suits one wastes every iteration on the
other. In log space a step is a FACTOR and means the same thing for both.

And it is how these constants are actually uncertain. Nobody knows a kcat
"to within 0.4 per second"; they know it to within a factor of two. A
confidence interval that comes out multiplicative -- 12.4, within a factor
of 1.8 -- is in the form a reader can compare with a paper, and it cannot
contain a negative rate, which a symmetric linear interval on a
poorly-determined constant routinely does.

The rank test below depends on this too. Both the rows (divided by the
measurement error) and the columns (log parameters) of the Jacobian are
dimensionless, so its singular values are comparable with one another. On an
unscaled Jacobian, one column is in mM per (1/s) and another in mM per mM,
and the condition number is a statement about the choice of units.

THE REFUSAL THIS MODULE EXISTS FOR
-----------------------------------
A fit returning numbers for parameters the data cannot determine is the most
dangerous output here, because those numbers look exactly like the ones the
data DO determine: same decimals, same interval, same confident tone. The
degeneracy is invisible in the output and visible in the arithmetic, so it
is checked in the arithmetic.

Two checks, and they answer different questions.

COUNTING. Fewer distinct measurement situations than parameters cannot
determine them, whatever the data say. Replicates are not a second
situation: measuring the same quantity twice under the same condition
shrinks one error bar, it does not add a second shape for the model to
match. So the count is of distinct (quantity, condition) pairs, and it is a
necessary condition -- passing it proves nothing.

RANK. At the optimum, the singular values of the weighted Jacobian say
whether any direction in log-parameter space leaves every prediction
unchanged. If one does, the data are silent about where along it the truth
lies, and the fit's position along it was decided by the starting point. The
refusal NAMES the direction as a multiplicative pattern -- "multiply ks by c
and kd by c and nothing changes" -- and names the combinations that ARE
determined, which is the useful half: an experiment measuring only a steady
state does not fail to measure anything, it measures ks/kd exactly and
nothing else.

WHAT THE RANK TEST IS NOT
-------------------------
It is local, first-order, and numerical. Local: it describes the model at
the optimum, and a parameter can be identifiable there and not two decades
away. First-order: it cannot see a second, distant optimum that fits equally
well, which is a global identifiability question. Numerical: the Jacobian is
a finite difference, so a direction whose singular value sits near the
differencing floor is indistinguishable from one that is exactly flat, and
`RANK_TOLERANCE` is where that line is drawn.

`compose/identifiability.py` is the structural question -- whether the model
COULD determine these parameters from perfect, noiseless data. It is imported
lazily and its absence costs this module nothing.

WHY THE COVARIANCE IS NOT RESCALED BY THE RESIDUAL
--------------------------------------------------
The common convention multiplies (J^T J)^-1 by chi-squared over the degrees
of freedom. That is right when the error bars are known only up to a common
factor and the fit is being asked to estimate it. Here the error bars are
REQUIRED and are the experiment's own, so rescaling would discard the one
thing the experiment supplied.

It would also do something worse. A model that fits badly has a large
reduced chi-squared, so rescaling WIDENS its intervals -- and a wide interval
reads as caution when what it actually encodes is that the model is wrong.
The failure would be hidden inside the number that is supposed to report it.

So the intervals mean: IF this model is right and IF the stated errors are
right, this is the range. The chi-squared line in the summary is the test of
the second IF, and it is reported separately rather than folded in.

WHAT A GOOD FIT IS NOT EVIDENCE OF
----------------------------------
That the model is right. A residual consistent with the stated errors says
these parameters reproduce these data to within their own noise. So would
several other models, and a model with enough parameters reproduces anything.
The summary says this in as many words, every time, including when the fit
is excellent -- especially then.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

#: Relative accuracy claimed for a prediction -- a steady state solved to a
#: residual tolerance, or an ODE integrated at tight tolerances.
#:
#: A CONSERVATIVE STATEMENT, not a measurement of any particular model. The
#: steady-state solve converges to about 1e-14 and the integrator is asked
#: for 1e-10, so 1e-9 claims less than either. It is used for exactly two
#: things -- the finite-difference step and the rank floor that follows from
#: it -- and in both a pessimistic claim costs precision while an optimistic
#: one invents it.
PREDICTION_PRECISION = 1e-9

#: The step used to differentiate the residuals with respect to log p.
#:
#: ABSOLUTE in log space, which is the point: exp(LOG_STEP) is a fixed
#: FACTOR, so the same step is right for a constant of 1e4 and one of 1e-3.
#: A relative step on the logarithm would be meaningless -- a parameter at
#: 1.0 has log 0, and a relative step around zero is zero.
#:
#: cbrt(precision) is where a central difference's truncation error (h^2)
#: meets its cancellation error (precision / h), the same balance
#: `compose/sensitivity.py` derives at greater length.
LOG_STEP = PREDICTION_PRECISION ** (1.0 / 3.0)

#: A singular value below this fraction of the largest is called
#: unconstrained.
#:
#: DERIVED, not chosen for roundness. A central difference on a quantity
#: accurate to `PREDICTION_PRECISION` leaves each Jacobian entry with a
#: relative error of about precision / LOG_STEP = precision^(2/3), so a
#: direction whose singular value is smaller than that cannot be told from
#: the differencing error. The factor of ten on top is deliberate slack in
#: the direction of refusing: calling a real direction unconstrained costs
#: the caller an experiment they might not have needed, and calling a flat
#: direction constrained produces a confident number about nothing.
RANK_TOLERANCE = 10.0 * PREDICTION_PRECISION ** (2.0 / 3.0)

#: Above this absolute correlation between two fitted parameters, the report
#: says so. A JUDGEMENT. At 0.99 the two are very nearly one measurement:
#: the rank test passes, the intervals are honest, and the pair still cannot
#: be moved independently by anything the data saw. Reporting it is the
#: difference between "identifiable" and "identifiable by a margin worth
#: relying on".
STRONG_CORRELATION = 0.99

#: Confidence level for the reported intervals.
DEFAULT_LEVEL = 0.95

#: Tail probability at which the residual is called inconsistent with the
#: stated errors, in EITHER direction.
#:
#: A JUDGEMENT, set at one tail in a hundred rather than one in twenty so
#: that an ordinary dataset does not get called inconsistent once every
#: twenty fits. Both tails are reported and they mean different things: too
#: large a residual says the model or the error bars are wrong; too small a
#: residual says the error bars are overstated, or the observations are not
#: independent of one another.
CONSISTENCY_TAIL = 0.01


class FitRefused(RuntimeError):
    """The fit was not performed, or its result was not fit to report."""


class Underdetermined(FitRefused):
    """The data cannot determine these parameters, and here is what they can.

    Carries the finding as data as well as prose: `unconstrained` holds the
    directions in log-parameter space that leave every prediction unchanged,
    and `determined` holds the combinations the data DO fix. A caller that
    wants to redesign the experiment needs the second list more than the
    first.
    """

    def __init__(
        self,
        message: str,
        unconstrained: Sequence["Direction"] = (),
        determined: Sequence["Direction"] = (),
    ) -> None:
        super().__init__(message)
        self.unconstrained: Tuple["Direction", ...] = tuple(unconstrained)
        self.determined: Tuple["Direction", ...] = tuple(determined)


@dataclass(frozen=True)
class Condition:
    """What was set in the experiment, and when it was read.

    A condition is the part of an observation that is not the number: which
    knobs were turned away from the model's declared state, and at what time
    the reading was taken.

    `time is None` means the reading is a steady state -- the assay ran long
    enough that nothing was still changing. That is a claim about the
    experiment, not a default: a plateau on a plot is not a steady state
    unless the plateau outlasted the system's own settling time, and
    `compose/analysis.py` reports that timescale.

    `parameters` and `initials` are OVERRIDES. Anything not named keeps the
    value the network declares, so a set of conditions differing in one
    inducer concentration says so by naming one species each.
    """

    name: str
    parameters: Mapping[str, float] = field(default_factory=dict)
    initials: Mapping[str, float] = field(default_factory=dict)
    time: Optional[float] = None
    description: str = ""

    def __post_init__(self) -> None:
        if not str(self.name).strip():
            raise ValueError(
                "a condition must be named. The name is what a reader sees "
                "next to a residual, and 'condition 3' with nothing else "
                "recorded is how a dataset becomes unreproducible."
            )
        object.__setattr__(
            self, "parameters",
            {str(k): _finite(v, f"condition {self.name!r} parameter {k!r}")
             for k, v in dict(self.parameters).items()},
        )
        object.__setattr__(
            self, "initials",
            {str(k): _finite(v, f"condition {self.name!r} initial {k!r}")
             for k, v in dict(self.initials).items()},
        )
        if self.time is not None:
            time = _finite(self.time, f"condition {self.name!r} time")
            if time < 0.0:
                raise ValueError(
                    f"condition {self.name!r} has time {time}, which is "
                    f"before the experiment started. Time here is measured "
                    f"from the stated initial condition."
                )
            object.__setattr__(self, "time", time)

    @property
    def at_steady_state(self) -> bool:
        return self.time is None

    @property
    def key(self) -> Tuple[Any, ...]:
        """Content identity: what was actually set, ignoring the name.

        Two conditions with the same key produce the same prediction from
        any model, so they are the same measurement situation however they
        are labelled -- which is what the independence count has to know.
        """
        return (
            tuple(sorted(self.parameters.items())),
            tuple(sorted(self.initials.items())),
            self.time,
        )

    def describe(self) -> str:
        parts: List[str] = []
        if self.parameters:
            parts.append(
                ", ".join(f"{k}={v:g}" for k, v in sorted(self.parameters.items()))
            )
        if self.initials:
            parts.append(
                ", ".join(f"{k}(0)={v:g}" for k, v in sorted(self.initials.items()))
            )
        parts.append(
            "at steady state" if self.at_steady_state else f"at t={self.time:g}"
        )
        return f"{self.name} ({'; '.join(parts)})"


@dataclass(frozen=True)
class Observation:
    """One measured number, with the error bar that makes it usable.

    `uncertainty` is the standard deviation of the measurement, in the same
    units as `value`, and it is REQUIRED. See the module docstring for why
    refusing beats every available way of supplying one.

    `quantity` names what was measured -- a species of the model, for the
    predictor this module ships. `condition` says under what.
    """

    quantity: str
    condition: Condition
    value: float
    uncertainty: float
    note: str = ""

    def __post_init__(self) -> None:
        if not str(self.quantity).strip():
            raise ValueError("an observation must say what was measured")
        if not isinstance(self.condition, Condition):
            raise TypeError(
                f"observation of {self.quantity!r} has condition "
                f"{self.condition!r}, which is not a Condition. The condition "
                f"is what makes two readings comparable or not, so it is not "
                f"inferred from a string."
            )
        object.__setattr__(
            self, "value",
            _finite(self.value, f"observation of {self.quantity!r}"),
        )

        uncertainty = self.uncertainty
        if uncertainty is None or isinstance(uncertainty, bool):
            raise ValueError(_no_uncertainty(self.quantity, uncertainty))
        try:
            uncertainty = float(uncertainty)
        except (TypeError, ValueError):
            raise ValueError(_no_uncertainty(self.quantity, self.uncertainty)) from None
        if not math.isfinite(uncertainty) or uncertainty <= 0.0:
            raise ValueError(_no_uncertainty(self.quantity, uncertainty))
        object.__setattr__(self, "uncertainty", uncertainty)

    @property
    def key(self) -> Tuple[Any, ...]:
        """(what was measured, under what). Two observations sharing this
        are replicates of one another."""
        return (self.quantity, self.condition.key)

    def describe(self) -> str:
        return (
            f"{self.quantity} = {self.value:.6g} +/- {self.uncertainty:.3g} "
            f"[{self.condition.describe()}]"
        )


def _no_uncertainty(quantity: str, given: Any) -> str:
    return (
        f"the observation of {quantity!r} has uncertainty {given!r}. An "
        f"uncertainty is required and must be a positive, finite standard "
        f"deviation in the same units as the value. This module will not "
        f"choose one: the weights of a weighted fit, the chi-squared "
        f"statement and every confidence interval are all expressed in units "
        f"of the stated errors, so an invented sigma would appear in the "
        f"answer as though it had been measured. State the standard "
        f"deviation of your replicates; with a single reading, state the "
        f"instrument's precision; if neither is known, that is a fact about "
        f"the experiment and this fit cannot stand in for it."
    )


def _finite(value: Any, what: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{what} is {value!r}, which is not a number") from None
    if not math.isfinite(number):
        raise ValueError(f"{what} is {number}, which is not a finite number")
    return number


@dataclass(frozen=True)
class Direction:
    """A multiplicative pattern across the parameters.

    A direction in log-parameter space: exponents e mean the move
    p_i -> p_i * c^(e_i). Normalised so the largest |exponent| is 1 and the
    first substantial one is positive, because the direction and its
    negative are the same pattern and a sign that flips between runs would
    make two identical findings read as different ones.

    `singular_value` is how strongly the data constrain this pattern,
    relative to `largest` -- the best-determined direction in the same fit.
    A ratio near zero is a combination the data are silent about.
    """

    exponents: Mapping[str, float]
    singular_value: float
    largest: float

    @property
    def relative_strength(self) -> float:
        return self.singular_value / self.largest if self.largest > 0 else 0.0

    def monomial(self) -> str:
        """The combination as a product, e.g. `ks / kd`."""
        top: List[str] = []
        bottom: List[str] = []
        for name, exponent in self.exponents.items():
            if abs(exponent) < 0.05:
                continue
            magnitude = abs(exponent)
            term = name if abs(magnitude - 1.0) < 0.05 else f"{name}^{magnitude:.2g}"
            (top if exponent > 0 else bottom).append(term)
        if not top and not bottom:
            return "(no parameter contributes measurably)"
        numerator = " * ".join(top) if top else "1"
        return numerator + (" / " + " * ".join(bottom) if bottom else "")

    def as_moves(self) -> str:
        """The same pattern as an instruction, e.g. "multiply ks by c"."""
        moves: List[str] = []
        for name, exponent in self.exponents.items():
            if abs(exponent) < 0.05:
                continue
            if abs(exponent - 1.0) < 0.05:
                moves.append(f"multiply {name} by c")
            elif abs(exponent + 1.0) < 0.05:
                moves.append(f"divide {name} by c")
            else:
                moves.append(f"multiply {name} by c^{exponent:.2g}")
        small = [n for n, e in self.exponents.items() if abs(e) < 0.05]
        text = ", ".join(moves)
        if small:
            text += f" (leaving {', '.join(small)} alone)"
        return text


@dataclass(frozen=True)
class FittedParameter:
    """One estimate, with the interval the stated errors imply.

    The interval is MULTIPLICATIVE -- value / fold to value * fold -- because
    the fit is in log space and that is the shape the uncertainty actually
    has. A symmetric linear interval on a constant known to a factor of three
    would run to a negative rate.
    """

    name: str
    value: float
    #: Standard error of log(value). The natural unit here: a log standard
    #: error of 0.1 is "about 10%", whatever the parameter's magnitude.
    log_standard_error: float
    low: float
    high: float
    level: float
    #: Where the fit started. Kept because a non-convex problem's answer can
    #: depend on it, and because the starting value is usually the library's
    #: illustrative placeholder rather than anything measured.
    start: float

    @property
    def fold(self) -> float:
        """The interval as a factor: value / fold .. value * fold."""
        return math.exp(self.log_standard_error * _z_for(self.level))

    @property
    def moved_by(self) -> float:
        """How far the fit moved this parameter from where it started, as a
        factor. A parameter that did not move is one the data said nothing
        about, or one that started at the answer, and the two look alike."""
        return self.value / self.start if self.start > 0 else float("inf")

    def describe(self) -> str:
        return (
            f"{self.name} = {self.value:.6g} "
            f"({self.level:.0%} interval {self.low:.4g} to {self.high:.4g}, "
            f"a factor of {self.fold:.3g}; started at {self.start:.4g})"
        )


@dataclass(frozen=True)
class FitReport:
    """What the fit found, and everything needed to judge it."""

    parameters: Tuple[FittedParameter, ...]
    observations: Tuple[Observation, ...]
    #: What the model says at the fitted parameters, one per observation.
    predictions: Tuple[float, ...]
    #: (prediction - measurement) / uncertainty. In units of the stated
    #: error, which is the only scale in which a residual means anything.
    residuals: Tuple[float, ...]
    #: The network carrying the fitted values, ready to simulate. Its
    #: parameters are FITTED, and nothing downstream should treat them
    #: otherwise.
    network: Any
    level: float
    #: Directions in log-parameter space, best-determined first.
    directions: Tuple[Direction, ...]
    #: (a, b) -> correlation between the estimates of a and b.
    correlations: Mapping[Tuple[str, str], float]
    notes: Tuple[str, ...] = ()
    #: What the structural identifiability module said, when it is present.
    structural: Optional[str] = None

    @property
    def chi_squared(self) -> float:
        return float(sum(r * r for r in self.residuals))

    @property
    def degrees_of_freedom(self) -> int:
        return len(self.observations) - len(self.parameters)

    @property
    def reduced_chi_squared(self) -> Optional[float]:
        dof = self.degrees_of_freedom
        return self.chi_squared / dof if dof > 0 else None

    @property
    def p_value(self) -> Optional[float]:
        """P(chi-squared >= the one observed), under this model and the
        stated errors. `None` when there are no degrees of freedom to
        spend."""
        dof = self.degrees_of_freedom
        if dof <= 0:
            return None
        return chi_squared_tail(self.chi_squared, dof)

    @property
    def consistent(self) -> Optional[bool]:
        """Whether the residual is the size the stated errors predict.

        `None` when the question cannot be asked -- with no degrees of
        freedom the residual is zero by construction. NOT a verdict on the
        model: consistency means these data do not contradict it.
        """
        p = self.p_value
        if p is None:
            return None
        return CONSISTENCY_TAIL <= p <= 1.0 - CONSISTENCY_TAIL

    @property
    def condition_number(self) -> float:
        """Best-determined direction over worst-determined.

        Dimensionless, because the Jacobian's rows are divided by the
        measurement errors and its columns are logarithms. On an unscaled
        Jacobian this number is a statement about the units.
        """
        if not self.directions:
            return float("inf")
        worst = self.directions[-1].singular_value
        return self.directions[0].singular_value / worst if worst > 0 else float("inf")

    @property
    def worst_residual(self) -> Optional[Observation]:
        if not self.observations:
            return None
        index = max(
            range(len(self.residuals)), key=lambda i: abs(self.residuals[i])
        )
        return self.observations[index]

    def value_of(self, parameter: str) -> float:
        for entry in self.parameters:
            if entry.name == parameter:
                return entry.value
        raise KeyError(
            f"{parameter!r} was not fitted. This report holds: "
            f"{', '.join(p.name for p in self.parameters)}."
        )

    def correlation(self, first: str, second: str) -> float:
        if first == second:
            return 1.0
        return float(
            self.correlations.get((first, second))
            or self.correlations.get((second, first))
            or 0.0
        )

    def strong_correlations(self) -> Tuple[Tuple[str, str, float], ...]:
        return tuple(
            (a, b, value)
            for (a, b), value in sorted(self.correlations.items())
            if abs(value) >= STRONG_CORRELATION
        )

    def summary(self) -> str:
        conditions = {o.condition.key for o in self.observations}
        lines = [
            f"Fitted {len(self.parameters)} parameter(s) to "
            f"{len(self.observations)} observation(s) across "
            f"{len(conditions)} distinct condition(s), by weighted least "
            f"squares in log parameter space."
        ]

        lines.append("Estimates:")
        for entry in self.parameters:
            lines.append("  - " + entry.describe())
        lines.append(
            f"The intervals are multiplicative because the fit is: the "
            f"uncertainty on a rate constant is a factor, not an offset, and "
            f"a symmetric linear interval on a poorly determined one runs to "
            f"a negative rate. They assume THIS model and the stated "
            f"measurement errors, and they are not widened when the fit is "
            f"poor -- a wide interval would then read as caution when what it "
            f"encoded was that the model is wrong."
        )

        lines.append(self._residual_sentence())

        if len(self.directions) > 1:
            best, worst = self.directions[0], self.directions[-1]
            lines.append(
                f"The data pin `{best.monomial()}` most strongly and "
                f"`{worst.monomial()}` least, by a factor of "
                f"{self.condition_number:.3g}. Nothing here is unconstrained "
                f"-- that would have been refused rather than reported -- but "
                f"the weakest direction is where another experiment would buy "
                f"the most."
            )

        for a, b, value in self.strong_correlations():
            lines.append(
                f"{a} and {b} are correlated at {value:+.4g}: the data very "
                f"nearly measure one combination of them rather than two. The "
                f"intervals above are still honest, and either constant can "
                f"move a long way if the other follows it."
            )

        # ALWAYS said, whether or not the structural module is installed.
        # Its answer is appended to this caveat and never replaces it: the
        # limits of the check this module performed are this module's to
        # state, and a reader who saw only another module's summary would
        # not know which question had been answered.
        lines.append(
            "The identifiability check performed here is LOCAL: a rank test "
            "on the Jacobian at this optimum. It cannot see a second, distant "
            "set of parameters that would fit these data equally well, which "
            "is structural identifiability -- a property of the equations "
            "rather than of this dataset, and the question "
            "`compose/identifiability.py` exists to ask."
        )
        if self.structural:
            lines.append(self.structural)

        lines.extend(self.notes)

        lines.append(
            "A fit this good is NOT evidence that the model is right. It says "
            "these parameters reproduce these data to within the errors the "
            "data carry. Other models would too, and a model with enough "
            "constants reproduces anything; choosing between models needs a "
            "comparison this module does not perform."
        )
        lines.append(
            "These values are FITTED, not literature values. Their provenance "
            "is this dataset and this model, they are conditional on both, "
            "and they must not be recorded as though somebody had measured "
            "the constant itself."
        )
        return " ".join(lines)

    def _residual_sentence(self) -> str:
        chi = self.chi_squared
        dof = self.degrees_of_freedom
        if dof <= 0:
            return (
                f"Residual: chi-squared = {chi:.4g} with {dof} degrees of "
                f"freedom. There are as many parameters as observations, so "
                f"the residual can be driven to zero by construction and says "
                f"nothing at all about whether the model fits. Only an "
                f"observation the fit did not have to match can test that."
            )

        p = self.p_value
        head = (
            f"Residual: chi-squared = {chi:.4g} on {dof} degrees of freedom "
            f"({self.reduced_chi_squared:.3g} per degree of freedom"
            + (f", p = {p:.3g}" if p is not None else "")
            + ")."
        )
        if p is None:
            return head + (
                " The tail probability could not be computed, so this is the "
                "raw residual and not a consistency statement."
            )
        if p < CONSISTENCY_TAIL:
            return head + (
                f" The residuals are LARGER than the stated measurement "
                f"errors -- about {math.sqrt(self.reduced_chi_squared):.3g} "
                f"times larger in scale. Either this model is missing "
                f"something these data contain, or the error bars are "
                f"understated. The estimates below are still the best "
                f"available for this model, and the intervals below are "
                f"narrower than the disagreement warrants."
            )
        if p > 1.0 - CONSISTENCY_TAIL:
            return head + (
                " The fit is CLOSER to the data than the stated errors say it "
                "should be able to get. That usually means the error bars are "
                "overstated, or that the observations are not independent of "
                "one another -- replicates of one reading entered as separate "
                "measurements, say. It is not evidence of a better fit."
            )
        return head + (
            " The residuals are the size the stated measurement errors "
            "predict, so these data do not contradict this model at these "
            "parameters."
        )


# ---------------------------------------------------------------------------
# The fit
# ---------------------------------------------------------------------------


def fit(
    network: Any,
    observations: Sequence[Observation],
    parameters: Sequence[str],
    *,
    predict: Optional[Callable[[Any, Sequence[Observation]], Sequence[float]]] = None,
    start: Optional[Mapping[str, float]] = None,
    level: float = DEFAULT_LEVEL,
    rank_tolerance: float = RANK_TOLERANCE,
    max_evaluations: int = 2000,
) -> FitReport:
    """Weighted least squares for `parameters`, in log space.

    Minimises the sum of squares of (prediction - measurement) / uncertainty
    over log of each parameter. The weighting is what makes observations of
    different magnitudes comparable, and it is why the uncertainty is
    required rather than defaulted.

    `predict` maps (network, observations) to one number per observation, in
    order. The default reads the named species out of the model -- at the
    steady state reached from the condition's initial state, or at the
    condition's time. A caller measuring something else (a ratio, a slope, a
    fluorescence proportional to a species) supplies their own and owns the
    vocabulary of `Observation.quantity`; nothing here second-guesses it.

    `start` overrides where the search begins. The default is the network's
    current values, which for a composed model are the library's ILLUSTRATIVE
    placeholders -- a starting point, not information. The report records
    where each parameter started because a non-convex problem's answer can
    depend on it.

    Refuses, rather than returning numbers, when the observations cannot
    determine the parameters. See `Underdetermined`.
    """
    try:
        import numpy as np
        from scipy.optimize import least_squares
    except ImportError as exc:  # pragma: no cover - dependency is pinned
        raise FitRefused(
            "fitting needs numpy and scipy, which are in requirements.txt "
            f"but not importable here: {exc}"
        ) from exc

    observations = tuple(observations)
    names = list(parameters)
    _check_inputs(network, observations, names, predict is None)

    if not (0.0 < level < 1.0):
        raise ValueError(
            f"level must be a probability strictly between 0 and 1, not "
            f"{level!r}. It is the confidence level of the intervals, so 95 "
            f"is not 0.95."
        )

    declared = {p.id: float(p.value) for p in network.parameters}
    start_values: Dict[str, float] = {}
    for name in names:
        value = float(dict(start or {}).get(name, declared[name]))
        if not (math.isfinite(value) and value > 0.0):
            raise FitRefused(
                f"{name} starts at {value:g}, and a fit in log space cannot "
                f"start there: log of a non-positive number is undefined. A "
                f"rate constant of zero is not a small rate constant, it is "
                f"the statement that the reaction does not happen, which is a "
                f"structural claim about the model rather than a value to "
                f"estimate. Give a positive starting guess through `start`."
            )
        start_values[name] = value

    _refuse_if_too_few(observations, names)

    predictor = predict if predict is not None else predict_states
    theta0 = [math.log(start_values[name]) for name in names]

    def residuals(theta: Sequence[float]) -> List[float]:
        values = {name: math.exp(t) for name, t in zip(names, theta)}
        moved = _with_parameters(network, values)
        try:
            predicted = list(predictor(moved, observations))
        except FitRefused:
            raise
        except Exception as exc:  # noqa: BLE001
            raise FitRefused(
                f"the model could not be evaluated at "
                + ", ".join(f"{k}={v:.6g}" for k, v in values.items())
                + f": {exc}. This is not treated as a bad fit and given a "
                f"large residual -- that would tell the optimiser this region "
                f"is wrong for a reason nobody established, when what "
                f"happened is that a solver failed."
            ) from exc
        if len(predicted) != len(observations):
            raise FitRefused(
                f"the predictor returned {len(predicted)} value(s) for "
                f"{len(observations)} observation(s). The contract is one "
                f"prediction per observation, in order; a mismatch would pair "
                f"measurements with predictions of other things."
            )
        return [
            (float(p) - o.value) / o.uncertainty
            for p, o in zip(predicted, observations)
        ]

    outcome = least_squares(
        residuals, theta0, method="trf",
        xtol=1e-12, ftol=1e-12, gtol=1e-12, max_nfev=max_evaluations,
    )
    if not outcome.success:
        raise FitRefused(
            f"the optimiser stopped without converging (status "
            f"{outcome.status}: {outcome.message.strip()}). The values it "
            f"holds are where it stopped, not a minimum, and their "
            f"confidence intervals would be curvature measured at a point "
            f"that is not the answer. Try a different starting point, or "
            f"fewer parameters."
        )

    theta = [float(v) for v in outcome.x]
    fitted = {name: math.exp(t) for name, t in zip(names, theta)}
    jacobian = _log_jacobian(residuals, theta)

    matrix = np.array(jacobian, dtype=float)
    if not np.all(np.isfinite(matrix)):
        raise FitRefused(
            "the Jacobian at the optimum has non-finite entries, so neither "
            "the identifiability check nor the confidence intervals can be "
            "computed. The estimates without them would be numbers with no "
            "stated uncertainty, which is what this module exists not to "
            "produce."
        )

    _basis, singular, right = np.linalg.svd(matrix, full_matrices=False)
    largest = float(singular[0]) if singular.size else 0.0
    directions = tuple(
        _direction(names, right[i], float(singular[i]), largest)
        for i in range(len(singular))
    )

    _refuse_if_rank_deficient(directions, largest, rank_tolerance, len(names))

    covariance = right.T @ np.diag(1.0 / (singular ** 2)) @ right
    errors = [float(math.sqrt(max(covariance[i][i], 0.0))) for i in range(len(names))]
    z = _z_for(level)

    estimates = tuple(
        FittedParameter(
            name=name,
            value=fitted[name],
            log_standard_error=errors[index],
            low=fitted[name] * math.exp(-z * errors[index]),
            high=fitted[name] * math.exp(z * errors[index]),
            level=level,
            start=start_values[name],
        )
        for index, name in enumerate(names)
    )

    correlations: Dict[Tuple[str, str], float] = {}
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            denominator = errors[i] * errors[j]
            if denominator > 0:
                correlations[(names[i], names[j])] = float(
                    covariance[i][j] / denominator
                )

    # Evaluated once more at the answer, rather than reconstructed from the
    # optimiser's last residual: the last residual belongs to whatever point
    # the search happened to try last, which is near the optimum and is not
    # it.
    fitted_network = _with_parameters(network, fitted)
    predicted = [float(v) for v in predictor(fitted_network, observations)]
    final = [
        (p - o.value) / o.uncertainty for p, o in zip(predicted, observations)
    ]

    return FitReport(
        parameters=estimates,
        observations=observations,
        predictions=tuple(predicted),
        residuals=tuple(final),
        network=fitted_network,
        level=level,
        directions=directions,
        correlations=correlations,
        notes=(),
        structural=structural_note(network, names, observations, predictor),
    )


# ---------------------------------------------------------------------------
# The checks that decide whether there is a fit to report
# ---------------------------------------------------------------------------


def _check_inputs(
    network: Any,
    observations: Sequence[Observation],
    names: Sequence[str],
    default_predictor: bool,
) -> None:
    """Everything that can be refused before anything is computed."""
    if not observations:
        raise FitRefused(
            "there is nothing to fit against: no observations were given. An "
            "empty dataset does not produce a weakly constrained estimate, it "
            "produces the starting guess with an interval invented from "
            "nothing."
        )
    for entry in observations:
        if not isinstance(entry, Observation):
            raise TypeError(
                f"{entry!r} is not an Observation. Observations are "
                f"constructed rather than inferred from tuples because that "
                f"is where the uncertainty is required, and a tuple would let "
                f"one through without."
            )

    if not names:
        raise FitRefused(
            "no parameters were named, so there is nothing to estimate. A fit "
            "over no parameters is not a fit of everything, it is a residual."
        )
    if len(set(names)) != len(names):
        repeated = sorted({n for n in names if list(names).count(n) > 1})
        raise FitRefused(
            f"{repeated} appear(s) more than once in the parameter list. The "
            f"same constant fitted twice makes the Jacobian rank deficient by "
            f"construction, which would be reported as the model's problem."
        )

    known = {p.id for p in network.parameters}
    unknown = [name for name in names if name not in known]
    if unknown:
        raise KeyError(
            f"{unknown} are not parameters of this network. It has: "
            f"{', '.join(sorted(known))}."
        )

    by_name: Dict[str, Condition] = {}
    for entry in observations:
        existing = by_name.setdefault(entry.condition.name, entry.condition)
        if existing.key != entry.condition.key:
            raise FitRefused(
                f"two different conditions are both called "
                f"{entry.condition.name!r}: {existing.describe()} and "
                f"{entry.condition.describe()}. A condition's name is what a "
                f"reader matches observations by, so one name for two setups "
                f"would report a disagreement between experiments as scatter "
                f"within one."
            )

    if default_predictor:
        species = {s.id for s in network.species}
        missing = sorted({o.quantity for o in observations if o.quantity not in species})
        if missing:
            raise FitRefused(
                f"nothing in this model is called {missing}. The predictor "
                f"used here reads species concentrations, and this model's "
                f"species are: {', '.join(sorted(species))}. If the "
                f"measurement is of something else -- a ratio, a rate, a "
                f"fluorescence proportional to a species -- pass a `predict` "
                f"function that computes it, rather than renaming the "
                f"measurement until it matches."
            )


def _refuse_if_too_few(observations: Sequence[Observation], names: Sequence[str]) -> None:
    """The counting check: distinct measurement situations against parameters.

    Replicates are deliberately not counted. Measuring the same quantity
    twice under the same condition shrinks the error bar on ONE number; it
    does not give the model a second shape to match, and no number of
    repeats of a single reading can separate two constants that only appear
    together in it.

    Necessary, not sufficient. Passing this proves nothing -- two distinct
    conditions can produce the same prediction, which is exactly what a
    steady state does under two different starting amounts -- and that is
    what the rank test is for.
    """
    situations = {o.key for o in observations}
    if len(situations) >= len(names):
        return
    quantities = sorted({o.quantity for o in observations})
    conditions = sorted({o.condition.name for o in observations})
    raise Underdetermined(
        f"{len(situations)} distinct measurement situation(s) cannot "
        f"determine {len(names)} parameter(s) ({', '.join(names)}). The "
        f"dataset holds {len(observations)} observation(s) of "
        f"{quantities} across condition(s) {conditions}, which is "
        f"{len(situations)} distinct (quantity, condition) pair(s); the rest "
        f"are replicates. Replicates shrink the error bar on one number and "
        f"do not add a second shape for the model to match, so they cannot "
        f"separate constants that appear together in that one number. Measure "
        f"another quantity, or the same one under a condition that moves one "
        f"of these parameters and not the others."
    )


def _refuse_if_rank_deficient(
    directions: Sequence[Direction],
    largest: float,
    tolerance: float,
    count: int,
) -> None:
    """The rank test at the optimum, and the refusal it produces.

    A direction whose singular value is negligible against the largest is
    one along which every prediction is unchanged to first order. The fit
    still returns a position along it, and that position came from the
    starting guess. Reporting it would be indistinguishable, in the output,
    from reporting a measurement.
    """
    if largest <= 0.0:
        raise Underdetermined(
            "no parameter changes any prediction at the optimum: the "
            "Jacobian is identically zero. Either these observations are of "
            "quantities this model fixes structurally -- a conserved total "
            "does not depend on any rate constant -- or the parameters named "
            "do not appear in the rate laws that produce them. Nothing here "
            "can be estimated from these data."
        )

    if len(directions) < count:
        # Fewer singular values than parameters means the Jacobian has more
        # columns than rows: some directions are not merely weak, they were
        # never seen. The counting check refuses this first, so reaching here
        # means a predictor returned fewer numbers than there are
        # observations, or a caller called this helper directly.
        raise Underdetermined(
            f"the Jacobian has only {len(directions)} direction(s) for "
            f"{count} parameter(s), so at least "
            f"{count - len(directions)} of them cannot be constrained by "
            f"these data at all -- not weakly, but not at all.",
            unconstrained=(),
            determined=tuple(directions),
        )

    weak = [d for d in directions if d.relative_strength < tolerance]
    if not weak:
        return

    determined = [d for d in directions if d.relative_strength >= tolerance]
    lines = [
        f"these {count} parameter(s) are not all determined by these data: "
        f"{len(weak)} direction(s) in log-parameter space leave every "
        f"prediction unchanged."
    ]
    for entry in weak:
        lines.append(
            f"Unconstrained: {entry.as_moves()} -- the combination "
            f"`{entry.monomial()}`, which the data pin "
            f"{entry.relative_strength:.2g} times as strongly as the "
            f"best-determined direction, i.e. not at all."
        )
    if determined:
        lines.append(
            "What these observations DO determine: "
            + ", ".join(f"`{d.monomial()}`" for d in determined)
            + ". That is a real result and worth reporting as one -- an "
              "experiment measuring only a plateau has not failed to measure "
              "anything, it has measured a ratio exactly and the individual "
              "constants not at all."
        )
    lines.append(
        "The estimates are withheld rather than reported with wide intervals, "
        "because a number produced along an unconstrained direction was set "
        "by the starting guess and prints identically to one the data fixed. "
        "Add an observation that separates the parameters -- a reading taken "
        "while the system is still changing constrains rates that a settled "
        "one cannot, and a condition that moves one constant without moving "
        "the other splits any pair -- or fit the determined combination "
        "instead of its factors."
    )
    raise Underdetermined(
        " ".join(lines), unconstrained=weak, determined=determined,
    )


def _direction(
    names: Sequence[str],
    vector: Sequence[float],
    singular_value: float,
    largest: float,
) -> Direction:
    """One right singular vector, normalised so it reads as a pattern.

    Scaled so the largest exponent is 1, and signed so the first substantial
    exponent is positive. A direction and its negative are the same pattern
    -- multiplying by c or by 1/c -- and a sign that flips between runs would
    make one finding read as two.
    """
    components = [float(v) for v in vector]
    peak = max((abs(v) for v in components), default=0.0)
    if peak > 0:
        components = [v / peak for v in components]
    for value in components:
        if abs(value) >= 0.05:
            if value < 0:
                components = [-v for v in components]
            break
    return Direction(
        exponents={name: value for name, value in zip(names, components)},
        singular_value=singular_value,
        largest=largest,
    )


def _log_jacobian(
    residuals: Callable[[Sequence[float]], Sequence[float]],
    theta: Sequence[float],
) -> List[List[float]]:
    """d(weighted residual) / d(log parameter), by central differences.

    Recomputed rather than taken from the optimiser's own Jacobian, which is
    a one-sided difference accumulated during the search. The covariance is
    the inverse of this matrix's curvature, so a first-order error in it is
    a first-order error in every confidence interval -- and the interval is
    the half of the answer that says how much to trust the other half.
    """
    columns: List[List[float]] = []
    for index in range(len(theta)):
        up = list(theta)
        up[index] += LOG_STEP
        down = list(theta)
        down[index] -= LOG_STEP
        ahead = list(residuals(up))
        behind = list(residuals(down))
        columns.append(
            [(a - b) / (2.0 * LOG_STEP) for a, b in zip(ahead, behind)]
        )
    rows = len(columns[0]) if columns else 0
    return [[columns[j][i] for j in range(len(columns))] for i in range(rows)]


# ---------------------------------------------------------------------------
# Predictions
# ---------------------------------------------------------------------------

#: Integration tolerances for a predicted time point.
#:
#: Tighter than a run made to be plotted, and for a reason that only applies
#: here: the fit DIFFERENTIATES this prediction. Integrator noise divided by
#: the finite-difference step lands directly in the Jacobian, and from there
#: in the rank test and the confidence intervals. `PREDICTION_PRECISION` is
#: the claim these tolerances have to support.
INTEGRATION_RTOL = 1e-10
INTEGRATION_ATOL = 1e-12


def predict_states(
    network: Any, observations: Sequence[Observation]
) -> Tuple[float, ...]:
    """The default predictor: species concentrations, one per observation.

    Two kinds of reading, decided by the condition:

    A TIME POINT is integrated from the condition's initial state. Every
    observation sharing an initial state and a parameter override is
    integrated ONCE, over all their times together, which is both faster and
    more consistent than integrating each separately -- two runs to
    neighbouring times with adaptive steps do not agree to the last digit,
    and a fit differentiating them would see the disagreement as signal.

    A STEADY STATE is a local solve continued from the condition's initial
    state, not a global search. That is the right question: the assay started
    somewhere and settled, so where it settles from THAT start is what was
    measured. In a model with several stable states, a global search would be
    answering a different question -- which state exists -- and picking among
    them by solver order.

    It does not require the state it finds to be stable. An unstable steady
    state is not something an assay sits at, so a model doing that is being
    asked the wrong question, but that is a judgement about the experiment
    and it is not made silently here at every optimiser step.
    """
    grouped: Dict[Tuple[Any, ...], List[Tuple[int, Observation]]] = {}
    for index, entry in enumerate(observations):
        setup = (
            tuple(sorted(entry.condition.parameters.items())),
            tuple(sorted(entry.condition.initials.items())),
        )
        grouped.setdefault(setup, []).append((index, entry))

    out: List[Optional[float]] = [None] * len(observations)
    for members in grouped.values():
        network_here = _with_condition(network, members[0][1].condition)
        times = sorted(
            {e.condition.time for _, e in members if e.condition.time is not None}
        )
        at_time = _integrate(network_here, times) if times else {}
        settled = (
            _settle(network_here)
            if any(e.condition.at_steady_state for _, e in members)
            else {}
        )
        for index, entry in members:
            state = settled if entry.condition.at_steady_state else at_time[entry.condition.time]
            if entry.quantity not in state:
                raise FitRefused(
                    f"the model produced no value for {entry.quantity!r}. It "
                    f"has: {', '.join(sorted(state))}."
                )
            out[index] = float(state[entry.quantity])

    # Explicitly, rather than by filtering the Nones out: a filter would
    # return a SHORTER tuple, which pairs every later measurement with
    # another one's prediction and fits happily to the wrong data.
    missing = [i for i, value in enumerate(out) if value is None]
    if missing:
        raise FitRefused(
            f"no prediction was produced for observation(s) {missing}, so the "
            f"remaining ones cannot be paired with their measurements."
        )
    return tuple(float(value) for value in out)


def _integrate(network: Any, times: Sequence[float]) -> Dict[float, Dict[str, float]]:
    """The state at each of `times`, from the network's declared initials."""
    try:
        from scipy.integrate import solve_ivp
    except ImportError as exc:  # pragma: no cover - dependency is pinned
        raise FitRefused(
            f"a time-point observation needs scipy's integrator: {exc}"
        ) from exc

    rhs, order = _derivative(network)
    initial = [float(s.initial) for s in network.species]
    if not times:
        return {}
    horizon = max(times)
    if horizon <= 0.0:
        # Every reading is at t=0, which is the initial condition and needs
        # no integrator. Not a degenerate case to guard against: a t=0
        # reading is how a dataset states what it started from.
        return {time: dict(zip(order, initial)) for time in times}

    outcome = solve_ivp(
        lambda _t, y: rhs(y),
        (0.0, horizon),
        initial,
        t_eval=list(times),
        rtol=INTEGRATION_RTOL,
        atol=INTEGRATION_ATOL,
        method="LSODA",
    )
    if not outcome.success:
        raise FitRefused(
            f"the integration to t={horizon:g} failed ({outcome.message}), so "
            f"there is no prediction to compare with the measurement at that "
            f"time. A failed integration is not a poor fit and is not given a "
            f"residual."
        )
    return {
        float(time): {
            name: float(outcome.y[row][column]) for row, name in enumerate(order)
        }
        for column, time in enumerate(times)
    }


def _settle(network: Any) -> Dict[str, float]:
    """Where the declared initial state settles, by local continuation."""
    try:
        from .analysis import analyse as analyse_stability
    except ImportError:  # pragma: no cover - flat import
        from analysis import analyse as analyse_stability  # type: ignore[no-redef]

    start = [float(s.initial) for s in network.species]
    report = analyse_stability(network, starts_per_species=0, extra_starts=[start])
    if not report.fixed_points:
        raise FitRefused(
            "the system does not settle from the condition's initial state: "
            "no steady state was found by continuing from it. A model that "
            "does not settle has no plateau to compare a plateau measurement "
            "with -- it may oscillate, or grow without bound -- and the "
            "measurement should be entered at the time it was taken instead."
        )
    return {name: float(value) for name, value in report.fixed_points[0].state.items()}


def _derivative(network: Any):
    try:
        from .analysis import derivative_function
    except ImportError:  # pragma: no cover - flat import
        from analysis import derivative_function  # type: ignore[no-redef]
    return derivative_function(network)


def _with_parameters(network: Any, values: Mapping[str, float]) -> Any:
    return replace(
        network,
        parameters=tuple(
            replace(p, value=float(values[p.id])) if p.id in values else p
            for p in network.parameters
        ),
    )


def _with_condition(network: Any, condition: Condition) -> Any:
    """The network as the experiment set it up.

    Anything the condition does not name keeps the model's declared value,
    so a set of conditions differing in one inducer says so by naming one
    species each. An override of something that does not exist is refused
    rather than ignored: a typo would otherwise become a condition that
    silently equals the control, and the fit would report that the inducer
    does nothing.
    """
    known_parameters = {p.id for p in network.parameters}
    unknown = sorted(set(condition.parameters) - known_parameters)
    if unknown:
        raise FitRefused(
            f"condition {condition.name!r} sets {unknown}, which this model "
            f"has no parameter for. Its parameters are: "
            f"{', '.join(sorted(known_parameters))}."
        )
    known_species = {s.id for s in network.species}
    unknown = sorted(set(condition.initials) - known_species)
    if unknown:
        raise FitRefused(
            f"condition {condition.name!r} sets the initial amount of "
            f"{unknown}, which this model has no species for. Its species "
            f"are: {', '.join(sorted(known_species))}."
        )

    moved = _with_parameters(network, dict(condition.parameters))
    if not condition.initials:
        return moved
    return replace(
        moved,
        species=tuple(
            replace(s, initial=float(condition.initials[s.id]))
            if s.id in condition.initials else s
            for s in moved.species
        ),
    )


# ---------------------------------------------------------------------------
# The two statistics, computed rather than tabulated
# ---------------------------------------------------------------------------


def _z_for(level: float) -> float:
    """The two-sided normal quantile for a confidence level.

    Computed from the stdlib's inverse normal CDF rather than written down
    as 1.96, so the number in the report follows from the level in the call
    and a caller asking for 99% gets 99%.

    NORMAL AND NOT STUDENT'S t, deliberately. The t distribution is what to
    use when the measurement error was ESTIMATED from the residuals of this
    same fit, which is exactly what this module refuses to do -- the errors
    are the experiment's own and are required as input. With the variance
    known, the quantile is the normal one.
    """
    from statistics import NormalDist

    return NormalDist().inv_cdf(1.0 - (1.0 - level) / 2.0)


def chi_squared_tail(chi_squared: float, degrees_of_freedom: int) -> Optional[float]:
    """P(X >= chi_squared) for X with this many degrees of freedom.

    The regularised upper incomplete gamma Q(k/2, x/2), by the standard
    series and continued fraction. Computed here rather than imported from
    `scipy.stats` because this is the only thing in the module that would
    need that import, and because the result is checkable against closed
    forms: for two degrees of freedom Q is exactly exp(-x/2), and for four
    it is exp(-x/2) * (1 + x/2).
    """
    if degrees_of_freedom <= 0:
        return None
    if not math.isfinite(chi_squared) or chi_squared < 0:
        return None
    return _upper_gamma(degrees_of_freedom / 2.0, chi_squared / 2.0)


def _upper_gamma(a: float, x: float, iterations: int = 500) -> Optional[float]:
    """Regularised upper incomplete gamma Q(a, x), or None if it did not
    converge.

    `None` rather than a number when the iteration runs out: a p-value is
    used to decide whether a fit is consistent with its error bars, and a
    silently unconverged one would decide it wrongly.
    """
    if x <= 0.0:
        return 1.0
    if x < a + 1.0:
        # Series for the LOWER incomplete gamma; Q = 1 - P.
        term = 1.0 / a
        total = term
        denominator = a
        for _ in range(iterations):
            denominator += 1.0
            term *= x / denominator
            total += term
            if abs(term) < abs(total) * 1e-16:
                return 1.0 - total * math.exp(-x + a * math.log(x) - math.lgamma(a))
        return None

    # Continued fraction for Q directly, by the modified Lentz method.
    tiny = 1e-300
    b = x + 1.0 - a
    c = 1.0 / tiny
    d = 1.0 / b if b != 0 else 1.0 / tiny
    h = d
    for index in range(1, iterations + 1):
        numerator = -index * (index - a)
        b += 2.0
        d = numerator * d + b
        if abs(d) < tiny:
            d = tiny
        c = b + numerator / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 1e-16:
            return h * math.exp(-x + a * math.log(x) - math.lgamma(a))
    return None


# ---------------------------------------------------------------------------
# The structural question, which this module does not answer
# ---------------------------------------------------------------------------


def structural_note(
    network: Any,
    parameters: Sequence[str],
    observations: Sequence[Any] = (),
    predictor: Optional[Callable[..., Sequence[float]]] = None,
) -> Optional[str]:
    """What `compose/identifiability.py` says, if it is installed.

    IT HAD NEVER ONCE RUN. `identifiability.analyse(network, quantities,
    *, parameters=...)` takes the OBSERVABLES as its second argument and
    the parameters by keyword; this called it as `entry(network,
    parameters)`, so every parameter name was handed over as an observable,
    the module raised, and every FitReport carried "the structural
    identifiability check did not run". True, and the wrong reason -- the
    check was fine, the call was not -- and a capability that nothing can
    reach is not a capability (ADR 0090).

    The structural question is "could THESE observations determine THESE
    parameters from perfect data?", so the observations go in as what they
    are: one callable per observation, the model's prediction for it as a
    function of the network. `observations` and `predictor` are what `fit`
    already has in hand at the point it asks.

    IMPORTED LAZILY AND CALLED DEFENSIVELY, for a reason beyond the usual
    one about optional dependencies. This module does not own that module's
    contract. Printing another module's answer as though this one had
    established it is how a report ends up asserting something nothing
    checked, so the note is ATTRIBUTED -- it says which module said it -- and
    anything unexpected produces no note at all rather than a guess.

    The distinction it adds is real and this module cannot make it. The rank
    test here is local and numerical: it asks whether these data, at this
    optimum, pin these parameters. Structural identifiability asks whether
    the model COULD determine them from perfect, noiseless data, which is a
    property of the equations and holds or fails before any experiment is
    done.
    """
    module = None
    for attempt in ("Terium.compose.identifiability", "compose.identifiability",
                    "identifiability"):
        try:
            module = __import__(attempt, fromlist=["*"])
            break
        except ImportError:
            continue
    if module is None:
        return None

    entry = None
    for candidate in ("analyse", "analyze", "assess", "check"):
        function = getattr(module, candidate, None)
        if callable(function):
            entry = function
            break
    if entry is None:
        return (
            "`compose/identifiability.py` is present but exposes no function "
            "this module recognises (it looked for `analyse`, `analyze`, "
            "`assess`, `check`), so the structural question -- whether this "
            "model could determine these constants from perfect data -- was "
            "not asked. The rank test performed here is local and numerical "
            "and is not a substitute for it."
        )

    if not observations or predictor is None:
        return (
            "The structural identifiability check was not asked: it needs "
            "the observations the fit was made against, and none were "
            "handed to it. The rank test above is local and numerical and "
            "is not a substitute."
        )

    quantities = [
        (lambda net, _obs=observation: float(predictor(net, [_obs])[0]))
        for observation in observations
    ]
    names = [
        getattr(o, "species", None) or f"observation {i + 1}"
        for i, o in enumerate(observations)
    ]
    try:
        result = entry(
            network, quantities, parameters=list(parameters),
            quantity_names=names,
        )
    except Exception as exc:  # noqa: BLE001 - another module's failure is not this one's answer
        return (
            f"The structural identifiability check did not run "
            f"({type(exc).__name__}: {exc}), so what is reported here is the "
            f"local rank test only: these data pin these parameters AT this "
            f"optimum, which is a weaker statement than the model being able "
            f"to determine them at all."
        )

    text = None
    summary = getattr(result, "summary", None)
    if callable(summary):
        try:
            text = str(summary())
        except Exception:  # noqa: BLE001
            text = None
    if text is None:
        text = str(result)
    text = " ".join(text.split())
    if not text:
        return None
    if len(text) > 600:
        text = text[:597] + "..."
    return f"`compose/identifiability.py` reports: {text}"


__all__ = [
    "Condition", "Observation", "Direction", "FittedParameter", "FitReport",
    "FitRefused", "Underdetermined",
    "fit", "predict_states", "structural_note", "chi_squared_tail",
    "PREDICTION_PRECISION", "LOG_STEP", "RANK_TOLERANCE",
    "STRONG_CORRELATION", "DEFAULT_LEVEL", "CONSISTENCY_TAIL",
    "INTEGRATION_RTOL", "INTEGRATION_ATOL",
]
