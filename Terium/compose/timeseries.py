"""What a trajectory actually shows.

THE QUESTION THIS ANSWERS
-------------------------
`simulate.py` produces a time course and nothing reads it. The trajectory
knows its own final state and whether the conservation laws survived, and
those are the two questions it was built to answer -- neither of which is
the question a researcher looking at the curve is asking.

Somebody looking at an oscillation wants the period and the amplitude.
Somebody looking at a pulse wants the peak, when it arrived, and whether the
signal came back down. Somebody looking at a step wants how fast it rose,
whether it overshot, and when it stopped moving. Those are the readings, and
until this module there was no way to take any of them except by eye off a
plot -- which is exactly how a slow decay gets reported as a very long
period.

TWO METHODS FOR THE PERIOD, AND THE DISAGREEMENT IS THE POINT
-------------------------------------------------------------
The period is measured twice, by two methods that share nothing below the
samples:

    zero crossings    the times the signal crosses its own mean going
                      upward, interpolated between the bracketing samples.
                      A LOCAL reading: it looks at two samples at a time and
                      knows nothing about the rest of the record.
    autocorrelation   the lag at which the whole record best matches a
                      shifted copy of itself. A GLOBAL reading: every sample
                      contributes to every lag.

For one clean frequency they agree. They stop agreeing when the signal has
two frequencies, when it is drifting, or when noise adds crossings that are
not cycles -- and in each of those cases "the period" was not a well-posed
question in the first place. So both numbers are reported and a disagreement
above `AGREEMENT_TOLERANCE` is FLAGGED rather than averaged away.

Measured, so that the flag means something. On a pure sine the two differ by
at most 0.03%; on the repressilator's limit cycle by 7e-7; on a decaying
sine, and on the repressilator including its approach to the limit cycle, by
0.1%. A tolerance of 5% is therefore two orders of magnitude clear of every
clean case measured, which is the property a flag needs: it fires on
something about the signal, not on the estimators arguing with each other.

`Oscillation.period` -- a single number -- exists and REFUSES when the two
disagree. A consumer that wants one number gets one exactly when there is
one to give.

WHY THE AUTOCORRELATION IS NORMALISED PER LAG
---------------------------------------------
The textbook estimator divides the lagged sum of products by the record
length (biased) or by the overlap length (unbiased). Both move the peak, and
this was measured rather than argued. Worst relative error in the recovered
period of a pure sine, over 72 combinations of 10 and 40 samples per period,
3.2 to 10.2 cycles, and six phases:

    global mean, divided by (n - k)   textbook unbiased    0.66%
    global mean, divided by n         textbook biased      1.34%
    per-lag Pearson                   shipped              0.23%

and over the shortest records this module accepts, 3.2 cycles, 0.55% / 1.34%
/ 0.19%.

The cause is the NORMALISATION and not the mean. Dividing by a fixed length
leaves each r(k) carrying whatever the overlap's own scale happens to be:
the biased form tapers as the overlap shrinks and drags the peak toward
shorter lags, the unbiased form's variance grows with lag and pushes it the
other way. Dividing instead by the two overlaps' own root sums of squares
removes the effect from both directions -- every lag is then a correlation
between two windows rather than a sum that has to be compared against sums
of different lengths.

The per-lag MEAN is kept because that is what makes each value a correlation
between the two windows rather than a correlation with the record's overall
level -- and it is kept honestly: swapping it for one global mean, with the
per-lag normalisation left in place, moves the worst case from 0.221% to
0.233%. It earns its place by definition, not by accuracy, and saying so is
the difference between a reason and a story that fits. A mutation that
replaces it with one global mean comes back NOT CAUGHT by the tests below,
correctly: on this signal the two agree to a part in ten thousand, and a
test manufactured to fail on it would be pinning a difference that is not
there.

`TestWhyTheAutocorrelationIsNormalisedPerLag` drives the textbook estimator
against the shipped one so this stays a measurement.

WHAT IS A SAMPLE AND WHAT IS AN ESTIMATE
-----------------------------------------
Two conventions live here on purpose, because the questions differ.

`Adaptation.peak` and the extreme behind `StepResponse.overshoot` are the
largest SAMPLE. They answer "how high did this go", and a peak interpolated
above every value the integrator produced would be a number the model never
attained. Consequence, stated: a smooth peak sampled N times per feature is
missed low by up to 1 - cos(pi/N), which is 7.6% at this module's sampling
floor of 8 and is the reason that floor is where it is.

`Oscillation.amplitude_by_extrema` is an ESTIMATE of the continuous signal's
turning point, from a parabola through the sample and its two neighbours.
Here the question is "what is the amplitude of the underlying oscillation",
for which the samples are evidence rather than the answer. Measured at the
sampling floor over seventeen phases: sample extrema come in up to 7.61% low
-- which is 1 - cos(pi/8) to three figures, so the bound above is not a
rule of thumb -- and the parabola up to 2.54%. The second number is reported
and this paragraph is why.

NYQUIST, AND WHY IT DESERVES ITS OWN REFUSAL
---------------------------------------------
A period shorter than two sample intervals is not measured, it is aliased:
the frequency that comes back is the true one folded about the sampling
frequency, and it is a property of `points=` rather than of the model. Worse
-- and this is the reason for a refusal rather than a caveat -- an aliased
signal does not look broken. Sampling a period of 1.0 every 0.7 gives an
apparent period of 2.33, and BOTH methods here report it: 2.333 by crossings
and 2.279 by autocorrelation, which agree to 2.4% and are both wrong by a
factor of 2.3. Agreement does not detect aliasing. Only counting samples per
period does, so that is what is checked, and below the floor this module
declines to report a number at all.

The check is not the theorem, and saying so is the difference between a
guard and a superstition. Nyquist bounds the TRUE frequency, and the true
frequency is exactly the thing not available here. What the samples give is
the APPARENT period, and that cannot come out below about two sample
intervals however fast the signal really is -- an upward crossing needs a
sample under the mean and a sample over it, so every crossing interval costs
two samples. The aliased example above measures 3.33 samples per period
while the true signal has 1.43. So this refusal does not detect a fold; it
detects being near the floor, which is the only circumstance in which a fold
is possible, and it says which of the two it is claiming.

WHY THREE CYCLES
----------------
See `MINIMUM_CYCLES`. One cycle is a feature, not a period. Two cycles give
one interval -- a single measurement, with nothing to compare it against,
and a transient bump followed by a second bump produces the same number.
Three give two intervals and three peaks, which is the fewest from which
"the interval repeats" and "the envelope is or is not shrinking" are both
readings rather than assertions.

WHAT THIS MODULE DOES NOT CLAIM
-------------------------------
That a period measured here is the model's period. It is the period of THIS
trajectory, over THIS window, at THESE illustrative constants; run from
another starting point inside the same basin the limit cycle is the same,
but nothing here establishes that the trajectory is on a limit cycle at all.
`Damping` is the closest this gets, and it reports a measured per-cycle
ratio rather than a claim about the attractor.

Nor does it claim a stimulus. `adaptation` reads the baseline off the first
sample of the window unless told otherwise, which assumes the run starts
before whatever provokes the response. When that is wrong every number it
returns is measured against the wrong reference, so the baseline it used is
reported alongside the answer.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, List, Mapping, Optional, Sequence, Tuple

# ---------------------------------------------------------------------------
# How much signal there has to be before a reading means anything
# ---------------------------------------------------------------------------

#: Complete cycles required before a period is reported.
#:
#: A JUDGEMENT, and the number is stated so it can be argued with.
#:
#:   1 cycle  -- the window holds one feature. Its width is not a period;
#:               nothing in the data says it repeats.
#:   2 cycles -- two up-crossings bracket ONE interval. That is a single
#:               measurement with no second measurement to compare it
#:               against, and a transient bump followed by an unrelated
#:               second bump yields exactly the same number.
#:   3 cycles -- four up-crossings, so three intervals and three peaks. The
#:               interval can be compared with itself (hence
#:               `Oscillation.crossing_spread`) and the envelope has
#:               successive values (hence `Damping`).
#:
#: Three is therefore the smallest count at which BOTH things this module
#: says about an oscillation -- its period, and whether it is sustained --
#: are measurements rather than extrapolations. Below it the module refuses.
MINIMUM_CYCLES = 3

#: Two samples per period: Nyquist, a fact rather than a judgement. Below it
#: the frequency recovered is the true one folded about the sampling
#: frequency.
#:
#: QUOTED IN THE REFUSAL AND NOT USED AS A THRESHOLD, on purpose. The bound
#: is on the TRUE frequency, and what is measurable here is the apparent
#: one, which cannot fall much below two samples whatever the signal does --
#: an upward crossing costs a sample below the mean and a sample above it.
#: Testing the apparent count against 2 would be a check that almost never
#: fires and would imply, when it did not, that no fold had occurred.
#: `MINIMUM_SAMPLES_PER_PERIOD` is the threshold; this is the fact the
#: threshold exists to respect, and the refusal states both.
NYQUIST_SAMPLES_PER_PERIOD = 2.0

#: Samples per period this module insists on. A JUDGEMENT sitting above the
#: fact above, for the same reason `sensitivity.py` keeps its noise floor
#: separate from its act-on threshold: "cannot be represented" and "can be
#: represented too poorly to report" are different claims.
#:
#: At N samples per period the nearest sample to a smooth peak is up to
#: pi/N out of phase with it, so a peak read off samples is low by up to
#: 1 - cos(pi/N): 29% at N = 4, 7.6% at N = 8, 1.2% at N = 20. Eight is
#: where that worst case falls under a tenth. MEASURED at exactly that
#: floor, over seventeen phases: sample extrema 7.61% low, matching the
#: bound to three figures, and the parabolic refinement
#: `Oscillation.amplitude_by_extrema` uses 2.54%.
MINIMUM_SAMPLES_PER_PERIOD = 8.0

#: Relative gap between the two period estimates above which they are called
#: disagreeing. MEASURED against the clean cases -- pure sine 0.03%,
#: repressilator limit cycle 7e-7, decaying sine 0.1% -- so a flag here is a
#: statement about the signal rather than about the estimators. See the
#: module docstring.
AGREEMENT_TOLERANCE = 0.05

#: Fractional change per cycle in the envelope below which an oscillation is
#: called sustained. A JUDGEMENT: 2% per cycle is under what a reader would
#: call a trend and over anything the integrator contributes.
SUSTAINED_BAND = 0.02

#: The per-cycle envelope change a genuinely sustained oscillation comes back
#: with here. MEASURED: the repressilator on its limit cycle (Hill
#: coefficient 4, five cycles after the transient) gives 1.1e-5, so 1e-4 is
#: an order of magnitude clear of it.
#:
#: NOT the same number as `SUSTAINED_BAND` and not used to classify. It is
#: what lets `Damping.describe` distinguish "indistinguishable from a limit
#: cycle at this integrator's accuracy" from "drifting, measurably, by less
#: than a reader would call a trend" -- two different findings that a single
#: threshold would print with one word.
ENVELOPE_RESOLUTION = 1e-4

#: Relative spread in the sample spacing above which the samples are not
#: treated as evenly spaced. MEASURED: a 3001-point roadrunner run through
#: `simulate.run` comes back at 5.7e-13, so 1e-6 is six orders of magnitude
#: of headroom and still tight enough that a genuinely adaptive grid fails
#: it.
#:
#: This matters because the autocorrelation is computed on a LAG INDEX, and
#: a lag index is only a time when the spacing is constant. On an uneven
#: grid the lag peak would be at a position with no time attached to it, and
#: multiplying it by a mean dt would produce a confident wrong period.
UNIFORM_SAMPLING_TOLERANCE = 1e-6

# ---------------------------------------------------------------------------
# Step-response conventions. There are several in use and a number quoted
# without its convention is not a number.
# ---------------------------------------------------------------------------

#: Rise time is measured between these fractions of the total change.
#:
#: NOT 0 to 100%: an exponential approach never reaches its final value, so
#: the 100% crossing does not exist and a 0-100% rise time is infinite for
#: the commonest response there is. 10-90% is the standard convention and is
#: finite -- for a first-order system it is exactly tau * ln(9).
RISE_LOW_FRACTION = 0.1
RISE_HIGH_FRACTION = 0.9

#: Settling band, as a fraction of the total change. The settling time is the
#: first moment after which the signal STAYS inside it -- the last exit, not
#: the first entry, which for an overshooting response are different times
#: and only the first is a settling time. For a first-order system the 2%
#: band gives exactly tau * ln(50).
SETTLING_BAND = 0.02

#: The tail of the window used to ask whether the run finished. A tenth is a
#: judgement: long enough to see slow drift, short enough not to include the
#: transient it is trying to exclude.
TAIL_FRACTION = 0.1

#: Variation, relative to the signal's own magnitude, below which the signal
#: is treated as not varying at all. Under this the "peak" is the
#: integrator's own rounding and an adaptation fraction would be that
#: rounding divided by itself.
#:
#: RELATIVE AND NOT ABSOLUTE, which was a defect before it was a constant. A
#: species held at 1e-3 by construction has a mean that is not exactly 1e-3
#: once 401 samples have been summed and divided, so its variance comes back
#: at about 1e-38 rather than at zero. Testing for exactly zero called that
#: an oscillation and went on to look for its period.
EXCURSION_FLOOR = 1e-9

# ---------------------------------------------------------------------------
# Verdicts
# ---------------------------------------------------------------------------

SUSTAINED = "sustained"
DECAYING = "decaying"
GROWING = "growing"

DAMPING_VERDICTS = (SUSTAINED, DECAYING, GROWING)

RISING = "rising"
FALLING = "falling"


class TimeSeriesRefused(RuntimeError):
    """A reading was not taken, and the reason is the message.

    Every one of these names a property of the DATA -- too few cycles, too
    few samples per cycle, a signal that never crosses its own mean, a step
    that is not a step -- and says what to do instead. None of them is an
    internal error, and none should be caught and turned into a default: a
    period defaulted to zero is a worse outcome than no period.
    """


def _numpy() -> Any:
    try:
        # Imported here rather than at module scope, as analysis.py and
        # reduction.py do: structure, dimensions and conservation laws are
        # all available without numpy, and only these readings need it.
        import numpy as np
    except ImportError as exc:  # pragma: no cover - dependency is pinned
        raise TimeSeriesRefused(
            "reading a trajectory needs numpy, which is pinned in "
            f"requirements.txt but is not importable here: {exc}. This is a "
            "statement about the environment, not about the trajectory."
        ) from exc
    return np


# ---------------------------------------------------------------------------
# What a reading can be taken from
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Series:
    """A time course from somewhere other than this package's integrator.

    `simulate.Trajectory` already has this shape -- `times` and `columns` --
    so every function here takes either, and the structural contract is those
    two attributes and nothing else.

    DELIBERATELY NOT A `Trajectory`. A Trajectory carries conservation checks
    and a window basis, and `Trajectory.sound` is True when no law was
    checked. Wrapping measured data, or an array written down to check the
    arithmetic against an analytic answer, in a Trajectory would have it
    report that an integration it never underwent came out sound. The point
    of this class is to be readable by the same functions while claiming
    none of that.
    """

    times: Tuple[float, ...]
    columns: Mapping[str, Tuple[float, ...]]

    @classmethod
    def of(
        cls, times: Sequence[float], values: Sequence[float], name: str = "signal"
    ) -> "Series":
        if len(times) != len(values):
            raise TimeSeriesRefused(
                f"{len(times)} time(s) and {len(values)} value(s): a series "
                f"needs one value per time, and padding either would invent "
                f"data."
            )
        return cls(
            times=tuple(float(t) for t in times),
            columns={name: tuple(float(v) for v in values)},
        )


def read(
    source: Any, species: str, *, after: Optional[float] = None
) -> Tuple[Tuple[float, ...], Tuple[float, ...]]:
    """One column of a trajectory, optionally from a stated time onward.

    `after` EXISTS BECAUSE A TRANSIENT IS NOT THE ATTRACTOR. The
    repressilator reaches its limit cycle over the first two cycles, and a
    period averaged across the approach and the limit cycle is the period of
    neither: measured over the whole window the two methods here differ by
    0.1%, and after the transient by 7e-7. Averaging them would have been an
    answer; saying which part of the run was read is a measurement.
    """
    times = getattr(source, "times", None)
    columns = getattr(source, "columns", None)
    if times is None or columns is None:
        raise TimeSeriesRefused(
            f"{type(source).__name__} carries no `times`/`columns`, so there "
            f"is nothing to read. Pass a `simulate.Trajectory`, or wrap your "
            f"own data with `Series.of(times, values)`."
        )
    if species not in columns:
        raise TimeSeriesRefused(
            f"no series named {species!r} here. Available: "
            f"{', '.join(sorted(columns)) or 'none'}."
        )

    column = columns[species]
    if len(column) != len(times):
        # `zip` would truncate to the shorter of the two and every reading
        # below would then be taken over a window that silently ended early.
        raise TimeSeriesRefused(
            f"{species} has {len(column)} value(s) against {len(times)} "
            f"time(s). Reading the shorter of the two would take every "
            f"measurement below over a window that quietly ended early."
        )
    pairs = list(zip(times, column))
    if after is not None:
        kept = [(t, v) for t, v in pairs if t >= after]
        if not kept:
            raise TimeSeriesRefused(
                f"no sample at or after t={after:g}; the run ends at "
                f"t={float(times[-1]) if len(times) else float('nan'):g}. "
                f"Nothing was read rather than the window silently becoming "
                f"the whole run."
            )
        pairs = kept
    return (
        tuple(float(t) for t, _ in pairs),
        tuple(float(v) for _, v in pairs),
    )


# ---------------------------------------------------------------------------
# Primitives
# ---------------------------------------------------------------------------


def sample_spacing(times: Sequence[float]) -> float:
    """The one sample interval, refusing when there is not one.

    See `UNIFORM_SAMPLING_TOLERANCE` for why an uneven grid is refused rather
    than averaged.
    """
    np = _numpy()
    if len(times) < 2:
        raise TimeSeriesRefused(
            f"{len(times)} sample(s): a time course needs at least two before "
            f"anything can be said about how it changes."
        )
    diffs = np.diff(np.asarray(times, dtype=float))
    if float(diffs.min()) <= 0.0:
        raise TimeSeriesRefused(
            "the times do not increase. Every reading here assumes the "
            "samples are in order, and sorting them silently would hide "
            "whatever produced the ordering."
        )
    mean = float(diffs.mean())
    spread = float(diffs.max() - diffs.min()) / mean
    if spread > UNIFORM_SAMPLING_TOLERANCE:
        raise TimeSeriesRefused(
            f"the samples are not evenly spaced: the interval varies by "
            f"{spread:.2g} of its mean, against a tolerance of "
            f"{UNIFORM_SAMPLING_TOLERANCE:g}. The autocorrelation is computed "
            f"on a lag index, and a lag index is only a time when the spacing "
            f"is constant -- on this grid the lag of best match has no time "
            f"attached to it, and multiplying it by a mean interval would "
            f"produce a confident wrong period. Resample onto an even grid, "
            f"or ask `simulate.run` for the trajectory, which produces one."
        )
    return mean


def mean_crossings(
    times: Sequence[float], values: Sequence[float]
) -> Tuple[float, ...]:
    """Times the signal crosses its own mean going upward, interpolated.

    UPWARD ONLY, so successive crossings are one full cycle apart rather than
    half. Counting both directions would halve the reported period for any
    waveform that is not symmetric about its mean, which is most of them --
    a relaxation oscillator spends most of a cycle low.

    The crossing time is where the straight line between the two bracketing
    samples meets the mean. That is an INTERPOLATION and it is the reason the
    period comes out exact on a synthetic sine rather than quantised to the
    sample grid; on a signal that curves sharply between samples it is worth
    what a straight line is worth, which is why the sampling floor exists.
    """
    np = _numpy()
    series = np.asarray(values, dtype=float)
    grid = np.asarray(times, dtype=float)
    centred = series - series.mean()

    out: List[float] = []
    for index in range(centred.size - 1):
        low = float(centred[index])
        high = float(centred[index + 1])
        # Strictly below then at-or-above. A sample sitting exactly on the
        # mean is counted once, at that sample, rather than once on the way
        # in and once on the way out.
        if low < 0.0 <= high:
            fraction = -low / (high - low)
            out.append(
                float(grid[index])
                + fraction * float(grid[index + 1] - grid[index])
            )
    return tuple(out)


def autocorrelation(values: Sequence[float], *, max_lag: Optional[int] = None) -> Any:
    """Correlation of the record with a copy of itself shifted by each lag.

    A PEARSON CORRELATION PER LAG: each overlap has its own mean and its own
    scale removed, so r(0) = 1 and every r(k) is on the same footing. The
    textbook estimators normalise by a fixed length instead -- by n, which
    tapers as the overlap shrinks, or by n - k, whose variance grows with
    lag -- and both measurably move the peak at the record lengths this
    module works with. The numbers are in the module docstring; the short
    version is 0.66% and 1.34% against 0.23%, on a signal whose period is
    written in its own definition.

    Lags run to half the record by default. Beyond that the overlap is under
    half the samples and the correlation is dominated by whichever few points
    still overlap; a peak found there says more about the record's ends than
    about its period.
    """
    np = _numpy()
    series = np.asarray(values, dtype=float)
    count = series.size
    if max_lag is None:
        max_lag = count // 2
    max_lag = int(min(max_lag, count - 2))
    if max_lag < 1:
        raise TimeSeriesRefused(
            f"{count} sample(s) leave no usable lag: the autocorrelation "
            f"needs a record long enough to overlap itself."
        )

    out = np.empty(max_lag + 1, dtype=float)
    for lag in range(max_lag + 1):
        left = series[: count - lag]
        right = series[lag:]
        left = left - left.mean()
        right = right - right.mean()
        # `np.sum(a * b)` rather than `a @ b`. The two compute the same
        # number, but the matmul goes through BLAS, and BLAS on macOS
        # Accelerate sets the divide-by-zero and overflow flags from inside
        # its own vectorised kernels on arrays this size. numpy attributes
        # those flags to the caller, so every run printed RuntimeWarnings
        # about arithmetic this function never performed -- and a suite that
        # turns warnings into errors would have failed on them. A warning
        # that is not about the data teaches a reader to ignore warnings.
        scale = math.sqrt(
            float(np.sum(left * left)) * float(np.sum(right * right))
        )
        out[lag] = float(np.sum(left * right)) / scale if scale > 0.0 else 0.0
    return out


def _first_repeat_lag(correlation: Any) -> Tuple[int, float]:
    """(lag index, sub-sample offset) of the first repeat in the record.

    The FIRST local maximum after the correlation has gone negative, not the
    largest. The largest is a trap: a record holding five cycles correlates
    with itself at one period, two periods and three, and which of those
    comes out highest is decided by the record's ends. Taking the global
    maximum on the repressilator reported 227.6 for a period of 75.8 -- three
    periods, confidently, with no sign that anything was wrong.

    The offset refines the peak by fitting a parabola through the lag and its
    neighbours, which is what makes the period sub-sample rather than
    quantised to the grid.
    """
    count = int(correlation.size) - 1
    negative = next(
        (lag for lag in range(1, count + 1) if float(correlation[lag]) < 0.0), None
    )
    if negative is None:
        raise TimeSeriesRefused(
            f"the signal never decorrelates from itself within the "
            f"{count} usable lag(s) -- its autocorrelation stays positive all "
            f"the way to half the record. That is what a monotone approach or "
            f"a drifting baseline looks like, and it is also what an "
            f"oscillation looks like when the window holds less than one "
            f"cycle of it. Run longer and ask again."
        )

    for lag in range(negative + 1, count):
        before = float(correlation[lag - 1])
        here = float(correlation[lag])
        after = float(correlation[lag + 1])
        if here >= before and here > after:
            # Detected with >=, refined only where >. Same rule and same
            # reason as `turning_points`: through a plateau the parabola's
            # vertex sits a full half-sample away and the lag it returns is
            # not a lag the correlation ever took. Where both neighbours are
            # strictly lower the vertex is inside half a sample by
            # construction -- with u = here - before and v = here - after
            # both positive it lands at (u - v) / (2 * (u + v)) -- so no
            # clamp is needed and none is written, because a guard that
            # cannot fire teaches a reader that it can.
            if here <= before:
                return lag, 0.0
            curvature = before - 2.0 * here + after
            return lag, 0.5 * (before - after) / curvature

    raise TimeSeriesRefused(
        f"the signal decorrelates and never correlates again within the "
        f"{count} usable lag(s), so there is no repeat to measure. A single "
        f"excursion does this; so does an oscillation whose window holds one "
        f"cycle and a bit."
    )


@dataclass(frozen=True)
class TurningPoint:
    """One local extremum, as a sample and as an estimate of the real one."""

    index: int
    #: The sample's own time and value. What the integrator actually
    #: produced.
    sample_time: float
    sample_value: float
    #: The vertex of the parabola through this sample and its neighbours.
    #: An ESTIMATE of where the continuous signal turns -- see the module
    #: docstring on which readings use which.
    time: float
    value: float


def turning_points(
    times: Sequence[float], values: Sequence[float], *, maxima: bool = True
) -> Tuple[TurningPoint, ...]:
    """Interior local maxima (or minima), sample and refined.

    A point qualifies when it is at least as extreme as the sample before and
    strictly more extreme than the one after. The asymmetry is deliberate: on
    a plateau of equal samples it selects the last one exactly once, rather
    than every sample of the plateau or none of them.

    THE PARABOLA IS FITTED ONLY WHERE IT IS ENTITLED TO BE, which is where
    both neighbours are STRICTLY lower. On a plateau it is not: the three
    points are (h, h, lower), the vertex of the parabola through them sits a
    full half-sample to the left, and the value it returns is h + one eighth
    of the drop -- a peak above every sample the signal ever took. On a
    square wave that is a 25% overstatement of the amplitude, which is the
    module inventing a number, so the plateau keeps its sample value.

    Where both neighbours are strictly lower the refinement is bounded and
    is worth taking. Writing u = here - before and v = here - after, both
    positive, the vertex sits at 0.5*(u - v)/(u + v) samples, which is
    inside half a sample by construction, and the refined value is
    here + (u - v)^2 / (8 * (u + v)) -- above the sample, as the continuous
    peak of a smooth signal is, and by an amount that goes to zero as the
    sampling becomes symmetric about the peak.

    Endpoints are never turning points. The first and last samples are where
    a window was cut, and a cut is not a feature of the signal.
    """
    np = _numpy()
    series = np.asarray(values, dtype=float)
    grid = np.asarray(times, dtype=float)

    out: List[TurningPoint] = []
    for index in range(1, series.size - 1):
        before = float(series[index - 1])
        here = float(series[index])
        after = float(series[index + 1])
        if maxima:
            qualifies = here >= before and here > after
        else:
            qualifies = here <= before and here < after
        if not qualifies:
            continue

        strict = (
            (here > before and here > after)
            if maxima
            else (here < before and here < after)
        )
        if strict:
            curvature = before - 2.0 * here + after
            offset = 0.5 * (before - after) / curvature
            value = here - 0.25 * (before - after) * offset
        else:
            offset = 0.0
            value = here
        spacing = float(grid[index + 1] - grid[index])
        out.append(
            TurningPoint(
                index=index,
                sample_time=float(grid[index]),
                sample_value=here,
                time=float(grid[index]) + offset * spacing,
                value=value,
            )
        )
    return tuple(out)


def _level_crossing(
    times: Sequence[float], values: Sequence[float], level: float
) -> Optional[float]:
    """The first time the signal reaches `level`, interpolated, or None."""
    for index in range(len(values) - 1):
        low = float(values[index])
        high = float(values[index + 1])
        if (low < level <= high) or (low > level >= high):
            if high == low:
                return float(times[index])
            fraction = (level - low) / (high - low)
            return float(times[index]) + fraction * float(
                times[index + 1] - times[index]
            )
    return None


# ---------------------------------------------------------------------------
# Damping
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Damping:
    """Whether successive excursions are shrinking, holding or growing."""

    verdict: str
    #: Fractional change in the envelope per cycle. 1.0 holds, 0.9 loses a
    #: tenth of its swing each cycle, 1.1 gains a tenth.
    per_cycle_ratio: float
    #: The same thing as a rate, per unit time, which is what compares
    #: against an eigenvalue.
    rate: float
    #: Peak-to-trough excursions the fit rests on. Two is the fewest that can
    #: give a ratio at all, and a verdict from two is one comparison.
    excursions: int
    #: The excursions themselves, first and last, so the reader can see the
    #: size of what is being called a trend.
    first_excursion: float
    last_excursion: float

    @property
    def sustained(self) -> bool:
        return self.verdict == SUSTAINED

    def describe(self) -> str:
        drift = abs(self.per_cycle_ratio - 1.0)
        if self.verdict == SUSTAINED and drift < ENVELOPE_RESOLUTION:
            return (
                f"sustained: the envelope changes by {drift:.1g} per cycle "
                f"over {self.excursions} excursion(s), which is at or below "
                f"the {ENVELOPE_RESOLUTION:g} a numerically integrated limit "
                f"cycle comes back with here -- indistinguishable from "
                f"constant at this integrator's accuracy"
            )
        if self.verdict == SUSTAINED:
            return (
                f"sustained: the envelope drifts by {drift:.2g} per cycle "
                f"over {self.excursions} excursion(s). That drift is real and "
                f"was measured -- it is above the {ENVELOPE_RESOLUTION:g} "
                f"floor -- and it is under the {SUSTAINED_BAND:g} per cycle "
                f"this module calls a trend"
            )
        direction = "loses" if self.verdict == DECAYING else "gains"
        return (
            f"{self.verdict}: each cycle {direction} "
            f"{abs(1.0 - self.per_cycle_ratio) * 100:.3g}% of its swing "
            f"(ratio {self.per_cycle_ratio:.4g} per cycle, rate "
            f"{self.rate:+.3g} per unit time), from {self.first_excursion:.4g} "
            f"to {self.last_excursion:.4g} over {self.excursions} excursion(s)"
        )


def _excursions(
    times: Sequence[float], values: Sequence[float]
) -> Tuple[Tuple[float, float], ...]:
    """(time, half peak-to-trough) for each peak with a trough after it.

    HALF THE PEAK-TO-TROUGH SWING, NOT THE PEAK ABOVE A MEAN. The two differ
    exactly when the baseline moves, and a baseline that moves is the case
    that matters: an oscillation of constant amplitude riding a rising
    baseline has peaks that climb every cycle, and measuring peak height
    above the window mean would report it as growing. The peak-to-trough
    swing cancels any offset that is slowly varying compared with a cycle,
    so it answers the question that was asked.
    """
    peaks = turning_points(times, values, maxima=True)
    troughs = turning_points(times, values, maxima=False)
    if not peaks or not troughs:
        return ()

    out: List[Tuple[float, float]] = []
    for peak in peaks:
        following = next((t for t in troughs if t.index > peak.index), None)
        if following is None:
            continue
        swing = (peak.value - following.value) / 2.0
        if swing > 0.0:
            out.append((peak.time, swing))
    return tuple(out)


def _damping_from(
    times: Sequence[float], values: Sequence[float], period: float
) -> Damping:
    np = _numpy()
    pairs = _excursions(times, values)
    if len(pairs) < 2:
        raise TimeSeriesRefused(
            f"{len(pairs)} complete peak-to-trough excursion(s) in this "
            f"window. Damping is a comparison between successive swings, so "
            f"it needs at least two of them -- with one there is a swing and "
            f"no trend, and with none there is not even a swing. Run for at "
            f"least {MINIMUM_CYCLES} cycles, which is what `oscillation` "
            f"insists on for the same reason."
        )

    stamps = np.asarray([t for t, _ in pairs], dtype=float)
    swings = np.asarray([s for _, s in pairs], dtype=float)
    # A straight line through the LOGARITHM of the envelope, because a
    # damped oscillation's envelope is an exponential and its logarithm is
    # the straight line whose slope is the damping rate. Fitting the
    # envelope itself would return a rate whose meaning changes with the
    # amplitude it was measured at.
    slope = float(np.polyfit(stamps, np.log(swings), 1)[0])
    ratio = math.exp(slope * period)

    if abs(ratio - 1.0) <= SUSTAINED_BAND:
        verdict = SUSTAINED
    elif ratio < 1.0:
        verdict = DECAYING
    else:
        verdict = GROWING

    return Damping(
        verdict=verdict,
        per_cycle_ratio=ratio,
        rate=slope,
        excursions=len(pairs),
        first_excursion=float(swings[0]),
        last_excursion=float(swings[-1]),
    )


def damping(
    source: Any,
    species: str,
    *,
    after: Optional[float] = None,
    period: Optional[float] = None,
) -> Damping:
    """Sustained, decaying or growing, from the envelope of the peaks.

    `period` converts the fitted rate into a per-cycle ratio, which is the
    readable form. Left out, it is taken from the mean spacing of the peaks
    themselves -- which is a period measured by a third method, and is used
    here only to express a rate, never reported as the period.
    """
    times, values = read(source, species, after=after)
    if period is None:
        peaks = turning_points(times, values, maxima=True)
        if len(peaks) < 2:
            raise TimeSeriesRefused(
                f"{len(peaks)} peak(s) in this window, so there is no peak "
                f"spacing to use as a cycle length and no `period` was given. "
                f"Pass one, or run long enough for at least two peaks."
            )
        period = (peaks[-1].time - peaks[0].time) / (len(peaks) - 1)
    return _damping_from(times, values, float(period))


# ---------------------------------------------------------------------------
# Oscillation
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Oscillation:
    """A period and an amplitude, each measured twice, and the disagreement."""

    species: str
    window: Tuple[float, float]
    #: Mean of the intervals between successive upward crossings of the
    #: signal's own mean.
    period_by_crossings: float
    #: Lag of the first repeat in the autocorrelation, refined by a parabola.
    period_by_autocorrelation: float
    #: Half the (mean refined peak less mean refined trough). An estimate of
    #: the continuous signal's swing -- see the module docstring.
    amplitude_by_extrema: float
    #: sqrt(2 * variance), which is the amplitude of a sine with this
    #: variance. A second route to the same quantity that uses every sample
    #: rather than the turning points, so it is unaffected by how well the
    #: grid happens to land on a peak -- and it reads high on a waveform
    #: with broad peaks and low on a spiky one, which is information about
    #: the SHAPE rather than an error.
    amplitude_by_variance: float
    mean: float
    #: Upward crossings found, and the spread of the intervals between them
    #: as a fraction of their mean. A clean oscillation has a spread near
    #: zero; a large one means the crossings are not evenly spaced, which no
    #: single period describes.
    crossings: int
    crossing_spread: float
    samples_per_period: float
    #: `None` when the envelope gave fewer than two complete excursions to
    #: compare -- reported as absent rather than guessed at.
    damping: Optional[Damping] = None

    @property
    def cycles(self) -> float:
        span = self.window[1] - self.window[0]
        return span / self.period_by_crossings

    @property
    def disagreement(self) -> float:
        """Relative gap between the two periods, against their mean."""
        mean = (self.period_by_crossings + self.period_by_autocorrelation) / 2.0
        if mean == 0.0:
            return float("inf")
        return abs(
            self.period_by_crossings - self.period_by_autocorrelation
        ) / mean

    @property
    def methods_agree(self) -> bool:
        return self.disagreement <= AGREEMENT_TOLERANCE

    @property
    def period(self) -> float:
        """One number, available exactly when there is one number to give.

        REFUSES rather than averaging. Two estimators that share nothing
        below the samples disagreeing by more than `AGREEMENT_TOLERANCE`
        means the record does not have a single period, and the mean of two
        descriptions of a thing that is not there describes it no better.
        The caller that wants to see both anyway already can.
        """
        if not self.methods_agree:
            raise TimeSeriesRefused(
                f"the two methods disagree by {self.disagreement:.1%} on "
                f"{self.species}: {self.period_by_crossings:.6g} by crossings "
                f"of the mean, {self.period_by_autocorrelation:.6g} by "
                f"autocorrelation, against a tolerance of "
                f"{AGREEMENT_TOLERANCE:.0%}. They share nothing below the "
                f"samples -- one is local and one is global -- so a gap this "
                f"size is a property of the signal, not of the arithmetic: "
                f"two frequencies, a drifting baseline, or crossings that are "
                f"not cycles. There is no single period here to return. Read "
                f"`period_by_crossings` and `period_by_autocorrelation` and "
                f"decide which question you are asking."
            )
        return (self.period_by_crossings + self.period_by_autocorrelation) / 2.0

    @property
    def shape_ratio(self) -> float:
        """Variance amplitude over extremum amplitude. 1 for a sine.

        Not a quality score. A square wave gives sqrt(2) = 1.41 and a
        triangle sqrt(2/3) = 0.82, both exactly right for what they are. It
        says how the signal distributes its time between its extremes, which
        is the one thing a period and an amplitude together cannot say.
        """
        if self.amplitude_by_extrema == 0.0:
            return float("inf")
        return self.amplitude_by_variance / self.amplitude_by_extrema

    def summary(self) -> str:
        lines = [
            f"{self.species} over t={self.window[0]:.4g}..{self.window[1]:.4g} "
            f"holds {self.cycles:.2f} cycles at "
            f"{self.samples_per_period:.1f} samples per period."
        ]
        if self.methods_agree:
            lines.append(
                f"Period {self.period:.6g}: {self.period_by_crossings:.6g} by "
                f"upward crossings of the mean ({self.mean:.4g}), "
                f"{self.period_by_autocorrelation:.6g} by autocorrelation. "
                f"The two agree to {self.disagreement:.2g}, and they share "
                f"nothing below the samples, so the agreement is evidence "
                f"rather than arithmetic."
            )
        else:
            lines.append(
                f"**The two methods disagree.** "
                f"{self.period_by_crossings:.6g} by upward crossings of the "
                f"mean, {self.period_by_autocorrelation:.6g} by "
                f"autocorrelation -- a gap of {self.disagreement:.1%} against "
                f"a tolerance of {AGREEMENT_TOLERANCE:.0%}. That is a finding "
                f"about the signal: it does not have one period. No single "
                f"number is reported for it."
            )
        lines.append(
            f"Amplitude {self.amplitude_by_extrema:.4g} from the turning "
            f"points, {self.amplitude_by_variance:.4g} from the variance "
            f"(ratio {self.shape_ratio:.3g}; a sine gives 1, a square wave "
            f"1.41, a triangle 0.82 -- this is waveform shape, not error)."
        )
        lines.append(
            f"The intervals between crossings vary by "
            f"{self.crossing_spread:.2g} of their mean over "
            f"{self.crossings} crossing(s)."
        )
        if self.damping is not None:
            lines.append("Envelope: " + self.damping.describe() + ".")
        else:
            lines.append(
                "The envelope gave fewer than two complete peak-to-trough "
                "excursions, so whether this is sustained was not judged -- "
                "which is not the same as it being sustained."
            )
        lines.append(
            "This is the period of THIS trajectory over THIS window at these "
            "constants. Nothing here establishes that the trajectory is on a "
            "limit cycle, only what it did while it was watched."
        )
        return " ".join(lines)


def oscillation(
    source: Any, species: str, *, after: Optional[float] = None
) -> Oscillation:
    """Period and amplitude, by two methods, with the refusals that matter.

    The order of the checks is the order in which a failure invalidates what
    follows. Aliasing comes first because under it every later number is a
    property of the sampling grid; the cycle count comes next because under
    it the numbers may be right and are not yet evidence.
    """
    np = _numpy()
    times, values = read(source, species, after=after)

    floor = int(MINIMUM_CYCLES * MINIMUM_SAMPLES_PER_PERIOD)
    if len(times) < floor:
        raise TimeSeriesRefused(
            f"{len(times)} sample(s) in this window. {MINIMUM_CYCLES} cycles "
            f"at {MINIMUM_SAMPLES_PER_PERIOD:g} samples per period is "
            f"{floor}, and those two numbers are the least this module will "
            f"report a period from -- see MINIMUM_CYCLES and "
            f"MINIMUM_SAMPLES_PER_PERIOD. Ask `simulate.run` for more points, "
            f"a longer window, or both."
        )

    spacing = sample_spacing(times)
    series = np.asarray(values, dtype=float)
    centred = series - series.mean()
    variance = float(np.mean(centred * centred))
    scale = max(float(np.abs(series).max()), 1.0)
    if math.sqrt(variance) <= EXCURSION_FLOOR * scale:
        raise TimeSeriesRefused(
            f"{species} does not change over this window: its variation is "
            f"{math.sqrt(variance):.3g} against a magnitude of {scale:.3g}, "
            f"which is the integrator's own rounding rather than a signal. It "
            f"has no period and no amplitude. A species that is constant by "
            f"construction -- an enzyme that appears only as a modifier -- "
            f"reaches this, and so does a model that had already settled "
            f"before the window started."
        )

    crossings = mean_crossings(times, values)
    if len(crossings) < 2:
        raise TimeSeriesRefused(
            f"{species} crosses its own mean upward {len(crossings)} time(s) "
            f"in t={times[0]:.6g}..{times[-1]:.6g}, so there is not one "
            f"complete cycle to measure, let alone {MINIMUM_CYCLES}. Two "
            f"different things look like this and this window cannot tell "
            f"them apart: a signal that does not oscillate -- a monotone "
            f"approach to a steady state crosses its mean once and never "
            f"again -- and an oscillation whose period is longer than the "
            f"window. Run longer and ask again; if the period is the "
            f"settling time's order, `analysis.py` gives that without "
            f"integrating."
        )

    intervals = np.diff(np.asarray(crossings, dtype=float))
    by_crossings = float(intervals.mean())
    spread = float(intervals.max() - intervals.min()) / by_crossings

    samples_per_period = by_crossings / spacing
    if samples_per_period < MINIMUM_SAMPLES_PER_PERIOD:
        wanted = int(
            math.ceil(
                MINIMUM_SAMPLES_PER_PERIOD
                * (times[-1] - times[0])
                / by_crossings
            )
        ) + 1
        peak_error = 1.0 - math.cos(math.pi / max(samples_per_period, 1.0))
        raise TimeSeriesRefused(
            f"{species} appears to repeat every {by_crossings:.6g}, which is "
            f"{samples_per_period:.2f} sample intervals of {spacing:.6g} -- "
            f"below the {MINIMUM_SAMPLES_PER_PERIOD:g} per period this module "
            f"will report from. At this spacing a reported period would be a "
            f"property of the sampling grid rather than of the model, and "
            f"every peak is read low by up to {peak_error * 100:.0f}%. "
            f"This is ALIASING and it is why the check counts samples instead "
            f"of trusting the answer: Nyquist "
            f"({NYQUIST_SAMPLES_PER_PERIOD:g} samples per period) is a bound "
            f"on the TRUE frequency, and the apparent one measured here "
            f"cannot establish it. A signal faster than the grid folds into a "
            f"slower apparent one that looks perfectly well sampled -- a "
            f"period of 1.0 sampled every 0.7 comes back as 2.333 by "
            f"crossings and 2.279 by autocorrelation, two methods agreeing "
            f"with each other and both wrong by a factor of 2.3. Agreement "
            f"cannot detect the fold; only counting can, and near the floor "
            f"the count is the only warning there is. Re-run over the same "
            f"window with points >= {wanted}, or shorten the window at the "
            f"same point count -- and note that {wanted} is computed from the "
            f"APPARENT period and is therefore a LOWER bound: if this signal "
            f"is folded, the true frequency needs more again, and the way to "
            f"find out is to keep raising the count until the answer stops "
            f"moving."
        )

    complete = len(crossings) - 1
    if complete < MINIMUM_CYCLES:
        raise TimeSeriesRefused(
            f"{species} completes {complete} cycle(s) in "
            f"t={times[0]:.6g}..{times[-1]:.6g}. {MINIMUM_CYCLES} is the "
            f"fewest this module reports a period from: with "
            f"{complete} there {'is' if complete == 1 else 'are'} "
            f"{complete} interval(s) between crossings, which is a single "
            f"measurement with nothing to compare it against -- a transient "
            f"bump followed by an unrelated second bump gives the same "
            f"number. What is available from this window is an "
            f"EXTRAPOLATION, not a measurement. On the intervals seen so far "
            f"the repeat is about {by_crossings:.6g}, so re-run to end >= "
            f"{times[0] + (MINIMUM_CYCLES + 1) * by_crossings:.6g}."
        )

    lag, offset = _first_repeat_lag(autocorrelation(values))
    by_autocorrelation = (lag + offset) * spacing

    # THE MEAN OF THE PEAKS AND THE MEAN OF THE TROUGHS, not the single
    # largest sample less the single smallest. The extremes of a record are
    # one sample's worth of evidence each and any noise in the run lands on
    # exactly those two; averaging over the cycles the window actually holds
    # uses all of them.
    #
    # No empty-list fallback, because there is no case for one to serve.
    # Four upward crossings of the mean have been established above, and
    # between consecutive upward crossings the signal rises above its mean
    # and returns below it, so it attains a maximum strictly inside that
    # stretch -- and the last sample attaining it satisfies the rule
    # `turning_points` uses. The same argument gives a minimum between each
    # downward crossing and the next upward one. A fallback nobody can reach
    # is a claim nobody can check.
    peaks = turning_points(times, values, maxima=True)
    troughs = turning_points(times, values, maxima=False)
    amplitude_by_extrema = (
        float(np.mean([p.value for p in peaks]))
        - float(np.mean([t.value for t in troughs]))
    ) / 2.0

    try:
        envelope = _damping_from(times, values, by_crossings)
    except TimeSeriesRefused:
        # Reported as absent, not as sustained. A window that produced a
        # period but not two complete excursions has said nothing about
        # whether the swing is holding, and a default of "sustained" would
        # be the module answering a question it did not measure.
        envelope = None

    return Oscillation(
        species=species,
        window=(float(times[0]), float(times[-1])),
        period_by_crossings=by_crossings,
        period_by_autocorrelation=by_autocorrelation,
        amplitude_by_extrema=amplitude_by_extrema,
        amplitude_by_variance=math.sqrt(2.0 * variance),
        mean=float(series.mean()),
        crossings=len(crossings),
        crossing_spread=spread,
        samples_per_period=samples_per_period,
        damping=envelope,
    )


# ---------------------------------------------------------------------------
# Adaptation
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Adaptation:
    """A pulse: how far it went, when, and how much of it came back."""

    species: str
    window: Tuple[float, float]
    #: Where the excursion is measured from. The first sample of the window
    #: unless the caller said otherwise, which ASSUMES the run starts before
    #: whatever provokes the response. Reported because if that is wrong,
    #: every number here is measured against the wrong reference.
    baseline: float
    baseline_is_assumed: bool
    #: The largest SAMPLE, and its time. Not interpolated -- see the module
    #: docstring on why a peak above every sample would be an invention.
    peak: float
    time_to_peak: float
    final: float
    direction: str
    #: Whether the run was still moving at the end. When it is, `recovered`
    #: is where the signal had got to, not where it is going.
    settled: bool
    tail_movement: float

    @property
    def excursion(self) -> float:
        """Peak displacement from the baseline, signed by `direction`."""
        return abs(self.peak - self.baseline)

    @property
    def recovered(self) -> float:
        """Fraction of the excursion given back by the end of the window.

        1.0 IS PERFECT ADAPTATION: the signal returned to the baseline it
        started from. 0.0 is no adaptation: it is still at its peak. Above
        1.0 it went past the baseline the other way, which is real and has a
        name -- undershoot -- and is not clipped away here.

        A FRACTION AND NOT A BOOLEAN, deliberately. "Adapts" is a matter of
        degree: a system returning 97% of its excursion and one returning 55%
        are doing different things, and a threshold anywhere between them
        would be this module inventing a biological claim. Nothing here calls
        a system adapted; it reports how much came back and the reader
        decides what that is worth.

        MEASURED FROM THE BASELINE, NOT FROM ZERO. `final / peak` is the
        other reading of "the fraction of the peak it returns to" and it is
        the wrong one: a signal resting at 5, peaking at 10 and returning
        exactly to 5 has adapted perfectly and `final / peak` calls it 0.5.
        Where zero happens to be is not a property of the response.
        """
        if self.excursion <= 0.0:
            return float("nan")
        return (self.peak - self.final) / (self.peak - self.baseline)

    @property
    def residual(self) -> float:
        """Fraction of the excursion still held. 1 - `recovered`."""
        return 1.0 - self.recovered

    def describe(self) -> str:
        recovered = self.recovered
        if recovered >= 0.99:
            reading = "returns essentially all of it"
        elif recovered >= 0.5:
            reading = "returns most of it"
        elif recovered >= 0.1:
            reading = "returns a little of it"
        else:
            reading = "does not come back"
        return (
            f"{self.species} {self.direction} to {self.peak:.6g} at "
            f"t={self.time_to_peak:.6g}, an excursion of {self.excursion:.6g} "
            f"from a baseline of {self.baseline:.6g}, and by "
            f"t={self.window[1]:.6g} it {reading}: {recovered:.4g} of the "
            f"excursion recovered, {self.residual:.4g} still held"
        )

    def summary(self) -> str:
        lines = [self.describe() + "."]
        lines.append(
            "1.0 would be perfect adaptation -- a return to the pre-stimulus "
            "baseline. This is reported as a fraction and not as a verdict: "
            "adaptation is a matter of degree and any threshold between 0.55 "
            "and 0.97 would be this module inventing a biological claim."
        )
        if self.baseline_is_assumed:
            lines.append(
                f"The baseline is the first sample of the window "
                f"({self.baseline:.6g}), which assumes the run starts before "
                f"whatever provokes the response. If the stimulus was already "
                f"on at t={self.window[0]:.6g}, every number above is measured "
                f"against the wrong reference -- pass `baseline=` to say so."
            )
        if not self.settled:
            lines.append(
                f"**The run ended while the signal was still moving**: over "
                f"the last {TAIL_FRACTION:.0%} of the window it changed by "
                f"{self.tail_movement:.3g}, which is "
                f"{self.tail_movement / self.excursion:.1%} of the excursion "
                f"and above the {SETTLING_BAND:.0%} that counts as settled. "
                f"The fraction above is where the signal had reached, not "
                f"where it is going -- the value it is heading for is not in "
                f"this trajectory. Integrate further before reading it as "
                f"the adaptation of the mechanism."
            )
        return " ".join(lines)


def adaptation(
    source: Any,
    species: str,
    *,
    after: Optional[float] = None,
    baseline: Optional[float] = None,
) -> Adaptation:
    """Peak, time to peak, and how much of the excursion came back."""
    np = _numpy()
    times, values = read(source, species, after=after)
    if len(times) < 3:
        raise TimeSeriesRefused(
            f"{len(times)} sample(s): a pulse needs a before, a peak and an "
            f"after, and this window cannot hold all three."
        )

    series = np.asarray(values, dtype=float)
    assumed = baseline is None
    start = float(series[0]) if assumed else float(baseline)

    displacement = series - start
    index = int(np.argmax(np.abs(displacement)))
    peak = float(series[index])
    excursion = abs(peak - start)

    scale = max(abs(start), abs(peak), float(np.abs(series).max()))
    if excursion <= EXCURSION_FLOOR * max(scale, 1.0):
        raise TimeSeriesRefused(
            f"{species} never leaves its baseline of {start:.6g} by more than "
            f"{excursion:.3g} over t={times[0]:.6g}..{times[-1]:.6g}. There is "
            f"no peak to adapt from, and an adaptation fraction here would be "
            f"the integrator's own noise divided by itself. If a stimulus was "
            f"meant to arrive in this window, nothing in the model responded "
            f"to it."
        )

    # The last tenth of the window, which always contains the final sample,
    # so there is no empty case to guard.
    span = float(times[-1] - times[0])
    tail_from = float(times[-1]) - TAIL_FRACTION * span
    tail = series[np.asarray(times, dtype=float) >= tail_from]
    movement = float(tail.max() - tail.min())

    return Adaptation(
        species=species,
        window=(float(times[0]), float(times[-1])),
        baseline=start,
        baseline_is_assumed=assumed,
        peak=peak,
        time_to_peak=float(times[index]),
        final=float(series[-1]),
        direction=RISING if peak >= start else FALLING,
        settled=movement <= SETTLING_BAND * excursion,
        tail_movement=movement,
    )


# ---------------------------------------------------------------------------
# Step response
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StepResponse:
    """How fast it got there, whether it went past, and when it stopped."""

    species: str
    window: Tuple[float, float]
    initial: float
    final: float
    #: Time between the 10% and 90% crossings of the total change. `None`
    #: when the signal never reaches 90% inside the window, which is a
    #: statement about the window and not a rise time of infinity.
    rise_time: Optional[float]
    #: First time after which the signal stays inside `SETTLING_BAND` of the
    #: final value. The LAST exit from the band, not the first entry.
    settling_time: Optional[float]
    #: (extreme - final) / (final - initial), positive in both directions.
    #: Zero for a monotone approach.
    overshoot: float
    peak: float
    time_to_peak: float
    direction: str
    settled: bool
    tail_movement: float

    @property
    def change(self) -> float:
        return self.final - self.initial

    def summary(self) -> str:
        lines = [
            f"{self.species} steps from {self.initial:.6g} to "
            f"{self.final:.6g} ({self.direction}) over "
            f"t={self.window[0]:.4g}..{self.window[1]:.4g}."
        ]
        if self.rise_time is not None:
            lines.append(
                f"Rise time {self.rise_time:.6g}, measured "
                f"{RISE_LOW_FRACTION:.0%} to {RISE_HIGH_FRACTION:.0%} of the "
                f"change -- not 0 to 100%, which does not exist for an "
                f"exponential approach."
            )
        else:
            lines.append(
                f"No rise time: the signal never reaches "
                f"{RISE_HIGH_FRACTION:.0%} of its change inside this window."
            )
        if self.overshoot > 0.0:
            lines.append(
                f"Overshoot {self.overshoot:.4g} "
                f"({self.overshoot * 100:.3g}% of the step), peaking at "
                f"{self.peak:.6g} at t={self.time_to_peak:.6g}. The peak is "
                f"the largest sample, so it is a lower bound on a peak the "
                f"grid may have stepped over."
            )
        else:
            lines.append(
                "No overshoot: the signal does not pass its final value."
            )
        if self.settling_time is not None:
            lines.append(
                f"Settled at t={self.settling_time:.6g}: the moment after "
                f"which it never again leaves the {SETTLING_BAND:.0%} band "
                f"around the final value. The LAST exit, not the first "
                f"entry -- for a response that rings, those are different "
                f"times and only this one is a settling time."
            )
        else:
            lines.append(
                f"It never leaves the {SETTLING_BAND:.0%} band, so the "
                f"settling time is at or before the first sample."
            )
        if not self.settled:
            lines.append(
                f"**The run ended while the signal was still moving**: over "
                f"the last {TAIL_FRACTION:.0%} of the window it changed by "
                f"{self.tail_movement:.3g}. Every number above is measured "
                f"against the last sample standing in for a final value that "
                f"is not in this trajectory."
            )
        return " ".join(lines)


def step_response(
    source: Any, species: str, *, after: Optional[float] = None
) -> StepResponse:
    """Rise time, settling time and overshoot, against stated conventions.

    Refuses when the signal ends where it started. A step response is
    measured as a fraction of the change, and with no change every fraction
    is zero over zero -- the numbers would not be small, they would be
    undefined. A signal that leaves its starting value and returns is a
    PULSE, and `adaptation` is the reading it wants.
    """
    np = _numpy()
    times, values = read(source, species, after=after)
    if len(times) < 3:
        raise TimeSeriesRefused(
            f"{len(times)} sample(s): a step response needs a before, a "
            f"transition and an after."
        )

    series = np.asarray(values, dtype=float)
    initial = float(series[0])
    final = float(series[-1])
    change = final - initial

    span = float(series.max() - series.min())
    # WHAT COUNTS AS "NO STEP", AND WHERE THE NUMBER COMES FROM.
    #
    # Not "the change is zero": the perfectly adapting pulse ends 4.5e-5
    # above where it began, which is not zero and is not a step either, and
    # an absolute floor let it through to produce a settling band of 9e-7
    # and an overshoot of 15000%.
    #
    # The threshold is derived from `SETTLING_BAND` rather than invented. If
    # the signal's total excursion exceeds its net change by more than
    # 1 / SETTLING_BAND = 50 times, then its peak sits more than fifty
    # settling bands away from the final value: that is not a step that
    # overshot, it is an excursion that returned, and the reading it wants
    # is `adaptation`.
    if span <= 0.0 or abs(change) < SETTLING_BAND * span:
        raise TimeSeriesRefused(
            f"{species} ends at {final:.6g}, effectively where it started "
            f"({initial:.6g}): a net change of {change:.3g} against a total "
            f"excursion of {span:.3g}, so the signal moves "
            f"{span / abs(change) if change else float('inf'):.4g} times "
            f"further than it nets. There is no step to characterise here. "
            f"Rise time, overshoot and settling time are all fractions of the "
            f"change, and at this ratio the 'overshoot' would be "
            f"{span / abs(change) * 100 if change else float('inf'):.0f}% -- "
            f"which is not a step that overshot, it is an excursion that came "
            f"back. Ask `adaptation`, which measures exactly that return. If "
            f"the signal never moved at all, nothing in the model responded "
            f"to whatever was supposed to provoke it."
        )

    rising = change > 0.0
    low_level = initial + RISE_LOW_FRACTION * change
    high_level = initial + RISE_HIGH_FRACTION * change
    low_time = _level_crossing(times, values, low_level)
    high_time = _level_crossing(times, values, high_level)
    rise = (
        high_time - low_time
        if low_time is not None and high_time is not None
        else None
    )

    extreme_index = int(np.argmax(series) if rising else np.argmin(series))
    extreme = float(series[extreme_index])
    # ONE EXPRESSION FOR BOTH DIRECTIONS. This was written as a conditional
    # -- (extreme - final)/change when rising, (final - extreme)/-change when
    # falling -- until a mutation deleted the falling branch and came back
    # NOT CAUGHT. Inspecting it showed the mutation was right and the code
    # was redundant: the two expressions are the same number, because
    # negating both the numerator and the denominator changes nothing. The
    # sign of `change` already carries the direction.
    overshoot = max(0.0, (extreme - final) / change)

    band = SETTLING_BAND * abs(change)
    distance = np.abs(series - final)
    outside = np.nonzero(distance > band)[0]
    settling: Optional[float] = None
    if outside.size:
        last = int(outside[-1])
        if last + 1 < series.size:
            here = float(distance[last])
            nxt = float(distance[last + 1])
            fraction = (here - band) / (here - nxt) if here != nxt else 0.0
            settling = float(times[last]) + fraction * float(
                times[last + 1] - times[last]
            )
        else:
            # Still outside the band at the last sample. There is no settling
            # time in this window, and the `settled` flag below says so.
            settling = None

    grid = np.asarray(times, dtype=float)
    tail_from = float(times[-1]) - TAIL_FRACTION * (
        float(times[-1]) - float(times[0])
    )
    tail = series[grid >= tail_from]
    movement = float(tail.max() - tail.min())

    return StepResponse(
        species=species,
        window=(float(times[0]), float(times[-1])),
        initial=initial,
        final=final,
        rise_time=rise,
        settling_time=settling,
        overshoot=overshoot,
        peak=extreme,
        time_to_peak=float(times[extreme_index]),
        direction=RISING if rising else FALLING,
        settled=movement <= band,
        tail_movement=movement,
    )



# ---------------------------------------------------------------------------
# Depletion: the reading `assumptions.py` tells the reader to take
# ---------------------------------------------------------------------------
#
# `assumptions._substrate_not_exhausted` is structural, on purpose -- it can
# see that a substrate is consumed and never replenished, which is what a
# closed batch assay IS, and it returns UNDECIDED because whether the
# saturable law still applies depends entirely on the window simulated. Its
# message ends "simulate and check whether S is still well above its Km at
# the end", which is correct advice and was not a callable thing.
#
# It also carried the threshold for that check -- DEPLETION_FRACTION, ten
# percent, documented as a judgement -- in a module that never simulates and
# never read it. A documented, exported threshold that nothing applies reads
# as a rule in force. It lives here now, where a trajectory exists.

#: Below this fraction of its starting amount, a pool has been CONSUMED
#: rather than merely drawn down, and any law that assumed a roughly
#: constant pool has stopped describing the system.
#:
#: A JUDGEMENT, and the reason it is one: at a tenth remaining, the
#: denominator of every saturable rate law in the model is wrong by an
#: order of magnitude, and it is wrong fastest exactly where the curve is
#: most interesting. Ten percent is not derived from anything -- it is the
#: point past which the approximation is not worth defending.
DEPLETION_FRACTION = 0.1


@dataclass(frozen=True)
class Depletion:
    """How much of a pool is left, and whether that is still a pool.

    Deliberately reports the FRACTION alongside the verdict, because the
    verdict is a judgement against `DEPLETION_FRACTION` and the fraction is
    a measurement. A reader who disagrees with the threshold can use the
    number; a reader who only got a boolean cannot.
    """

    species: str
    initial: float
    final: float
    #: `final / initial`, or None when `initial` is zero -- a pool that
    #: started empty has not been depleted, it was never there, and
    #: dividing to find out would invent a ratio.
    remaining_fraction: Optional[float]
    #: The first time the series fell below the threshold, interpolated,
    #: or None if it never did.
    crossed_at: Optional[float]
    threshold: float

    @property
    def depleted(self) -> bool:
        """Below the threshold at the END of the window.

        Not "ever went below": a pool that dips and is replenished has not
        been consumed, and reporting it as depleted would call a
        regenerating system a spent one.
        """
        return (
            self.remaining_fraction is not None
            and self.remaining_fraction < self.threshold
        )

    @property
    def undecidable(self) -> bool:
        """Started at zero, so there is no fraction to take."""
        return self.remaining_fraction is None

    def describe(self) -> str:
        if self.undecidable:
            return (
                f"{self.species} started at zero, so there is no fraction "
                f"remaining to report -- it was not depleted, it was never "
                f"there"
            )
        percent = 100.0 * (self.remaining_fraction or 0.0)
        if self.depleted:
            when = (
                f", first crossing at t={self.crossed_at:g}"
                if self.crossed_at is not None else ""
            )
            return (
                f"{self.species} ended at {percent:.3g}% of its starting "
                f"amount{when}. Below {100.0 * self.threshold:g}% any "
                f"saturable law reading it is wrong by an order of "
                f"magnitude in its denominator"
            )
        return (
            f"{self.species} ended at {percent:.3g}% of its starting "
            f"amount, above the {100.0 * self.threshold:g}% below which a "
            f"pool stops behaving like one"
        )


def depletion(
    source: Any,
    species: str,
    *,
    threshold: float = DEPLETION_FRACTION,
    after: Optional[float] = None,
) -> Depletion:
    """Whether a pool was consumed over the window, and by how much.

    THE READING `assumptions.py` ASKS FOR. That module can tell you a
    substrate is consumed and never replenished; only a trajectory can tell
    you whether that mattered over the window you ran.

    Takes the threshold as an argument with the module default, so a reader
    who thinks a tenth is the wrong line can move it without editing this
    file -- and so a test can drive both sides of it.
    """
    if not 0.0 < threshold < 1.0:
        raise TimeSeriesRefused(
            f"threshold={threshold!r} is not a fraction between 0 and 1. A "
            f"threshold of 0 can never be crossed and one of 1 or more is "
            f"crossed by every pool that is consumed at all, so neither "
            f"states anything about this trajectory."
        )

    times, values = read(source, species, after=after)
    if not values:
        raise TimeSeriesRefused(
            f"{species} has no samples over this window, so there is no "
            f"starting amount to take a fraction of."
        )

    initial, final = float(values[0]), float(values[-1])
    if initial == 0.0:
        return Depletion(
            species=species, initial=initial, final=final,
            remaining_fraction=None, crossed_at=None, threshold=threshold,
        )

    fraction = final / initial
    level = threshold * initial
    # `_level_crossing` interpolates and already takes crossings in either
    # direction, which matters here: the sample grid is the integrator's,
    # not the chemistry's, so reporting the first sample BELOW the line as
    # the crossing time would be off by up to one step.
    crossed = _level_crossing(times, values, level)
    return Depletion(
        species=species, initial=initial, final=final,
        remaining_fraction=fraction, crossed_at=crossed, threshold=threshold,
    )


__all__ = [
    "Adaptation", "Damping", "Depletion", "Oscillation", "Series",
    "StepResponse",
    "TimeSeriesRefused", "TurningPoint",
    "adaptation", "autocorrelation", "damping", "depletion",
    "mean_crossings",
    "oscillation", "read", "sample_spacing", "step_response",
    "turning_points",
    "AGREEMENT_TOLERANCE", "DAMPING_VERDICTS", "DECAYING",
    "DEPLETION_FRACTION", "ENVELOPE_RESOLUTION",
    "EXCURSION_FLOOR", "FALLING", "GROWING", "MINIMUM_CYCLES",
    "MINIMUM_SAMPLES_PER_PERIOD", "NYQUIST_SAMPLES_PER_PERIOD",
    "RISE_HIGH_FRACTION", "RISE_LOW_FRACTION", "RISING", "SETTLING_BAND",
    "SUSTAINED", "SUSTAINED_BAND", "TAIL_FRACTION",
    "UNIFORM_SAMPLING_TOLERANCE",
]
