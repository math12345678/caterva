"""Sweep a parameter and find where the system's behaviour changes.

THE QUESTION A STABILITY ANALYSIS AT ONE POINT CANNOT ANSWER
------------------------------------------------------------
`analysis.py` says what a model does at the parameters it currently has.
The question a modeller actually has is the next one: at what value of the
Hill coefficient does this toggle switch become bistable? How much
cooperativity does the repressilator need before it oscillates? Where does
this cascade stop being graded and start being a switch?

Those are questions about a FAMILY of models, and they are answered by
sweeping one parameter and watching the fixed points appear, disappear, and
change stability. The values at which that happens are the bifurcations, and
they are usually the only numbers in the whole analysis a paper reports.

WHAT IS DETECTED AND WHAT IS NAMED
----------------------------------
Detected: a change in the NUMBER of stable states, a change in the
classification of a state that persists, and an eigenvalue crossing the
imaginary axis.

Named, cautiously: a fold (states appearing or vanishing in pairs) and a
Hopf (a complex pair crossing into instability, which is where sustained
oscillation begins). These are named only when the numerical evidence fits
the definition; anything else is reported as "the behaviour changed here"
without a label, because a bifurcation misnamed is worse than one merely
located -- a reader who is told "Hopf" will look for a limit cycle.

WHAT IT WILL NOT DO
-------------------
It will not continue a branch. Proper numerical continuation follows a
solution family through turning points using a predictor-corrector on an
augmented system, which is a different and much larger piece of machinery
(AUTO, MatCont). This resolves the sweep by re-solving from scratch at each
step, which finds what a researcher would find by re-running the model and
misses branches that only exist between sample points. The resolution is
reported so that limitation is visible rather than implied.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

try:
    from .analysis import (
        MARGINAL_EIGENVALUE, FixedPoint, StabilityReport, analyse,
    )
except ImportError:  # pragma: no cover - flat import
    from analysis import (  # type: ignore[no-redef]
        MARGINAL_EIGENVALUE, FixedPoint, StabilityReport, analyse,
    )

#: Default number of parameter values in a sweep. A compromise stated
#: rather than hidden: each step is a full multistart root find, so this is
#: the cost knob, and 25 resolves a fold to about 4% of the swept range.
DEFAULT_STEPS = 25

#: Two fixed points across adjacent parameter values are "the same state
#: continued" when every coordinate is within this RELATIVE distance.
#:
#: Loose on purpose. A state moves as the parameter moves, and a threshold
#: tight enough to be certain would report every step as a new state
#: appearing and the old one vanishing -- a bifurcation at every sample.
CONTINUATION_TOLERANCE = 0.5

FOLD = "fold"
HOPF = "Hopf"
UNNAMED = "behaviour change"


@dataclass(frozen=True)
class SweepPoint:
    """What the model does at one parameter value."""

    value: float
    report: StabilityReport

    @property
    def stable_count(self) -> int:
        return len(self.report.stable_points)

    @property
    def total_count(self) -> int:
        return len(self.report.physical_points)

    @property
    def oscillatory(self) -> bool:
        return self.report.any_oscillatory

    @property
    def unstable_spiral(self) -> bool:
        """An unstable focus, which is where sustained oscillation lives."""
        return any(
            p.oscillatory and not p.stable for p in self.report.physical_points
        )

    @property
    def behaviour(self) -> str:
        """What the model DOES here, as a label -- not just how many attractors.

        `stable_count` alone cannot tell a sustained oscillation from an
        open system that runs away: both have zero stable states. The
        repressilator's whole interesting range -- where it oscillates --
        was being labelled "no steady state", which is false (there is
        one, an unstable spiral) and points the reader at the wrong
        diagnosis. A line of equilibria is a third zero-stable case with
        its own meaning.
        """
        if self.stable_count == 0 and self.unstable_spiral:
            return "sustained oscillation"
        if getattr(self.report, "on_a_continuum", False):
            return "a line of equilibria"
        if self.total_count == 0:
            return "no steady state"
        if self.stable_count == 0:
            return "no stable state"
        if self.stable_count == 1:
            return "one stable state"
        return f"{self.stable_count} stable states"


@dataclass(frozen=True)
class Bifurcation:
    """A parameter interval across which the behaviour changed."""

    parameter: str
    #: The change happened BETWEEN these two sampled values. Reported as an
    #: interval rather than a point, because a sweep locates it no more
    #: precisely than its own step -- and quoting a midpoint as "the"
    #: bifurcation value would claim a precision the method does not have.
    below: float
    above: float
    kind: str
    detail: str

    @property
    def bracket(self) -> Tuple[float, float]:
        return (self.below, self.above)

    def describe(self) -> str:
        return (
            f"{self.kind} between {self.parameter}={self.below:.6g} and "
            f"{self.parameter}={self.above:.6g}: {self.detail}"
        )


@dataclass(frozen=True)
class SweepReport:
    parameter: str
    points: Tuple[SweepPoint, ...]
    bifurcations: Tuple[Bifurcation, ...]
    #: Parameter values where the root find returned nothing. Kept because
    #: a gap in the sweep is not evidence of a bifurcation and must not be
    #: read as one.
    barren: Tuple[float, ...] = ()

    @property
    def resolution(self) -> Optional[float]:
        if len(self.points) < 2:
            return None
        return abs(self.points[-1].value - self.points[0].value) / (
            len(self.points) - 1
        )

    def behaviours(self) -> Tuple[Tuple[float, float, str], ...]:
        """(from, to, behaviour label) for each stretch where it holds.

        The richer sibling of `regions`, which groups by stable-state
        count alone and so cannot tell "oscillates" from "runs away" --
        both are zero. `regions` is kept for callers that want the count;
        the summary reads this one.
        """
        if not self.points:
            return ()
        out: List[Tuple[float, float, str]] = []
        start = self.points[0]
        current = start.behaviour
        for point in self.points[1:]:
            if point.behaviour != current:
                out.append((start.value, point.value, current))
                start, current = point, point.behaviour
        out.append((start.value, self.points[-1].value, current))
        return tuple(out)

    def regions(self) -> Tuple[Tuple[float, float, int], ...]:
        """(from, to, stable-state count) for each stretch of constant behaviour."""
        if not self.points:
            return ()
        out: List[Tuple[float, float, int]] = []
        start = self.points[0]
        current = start.stable_count
        for point in self.points[1:]:
            if point.stable_count != current:
                out.append((start.value, point.value, current))
                start, current = point, point.stable_count
        out.append((start.value, self.points[-1].value, current))
        return tuple(out)

    def summary(self) -> str:
        if not self.points:
            return f"No parameter values were swept for {self.parameter}."

        lines = [
            f"Swept {self.parameter} from {self.points[0].value:.6g} to "
            f"{self.points[-1].value:.6g} in {len(self.points)} steps"
            + (f" (resolution {self.resolution:.3g})" if self.resolution else "")
            + "."
        ]

        for start, end, word in self.behaviours():
            lines.append(f"{self.parameter} {start:.4g} to {end:.4g}: {word}.")

        if self.bifurcations:
            lines.append("Behaviour changes:")
            for bifurcation in self.bifurcations:
                lines.append("  - " + bifurcation.describe())
        elif len({count for _, _, count in self.regions()}) > 1:
            # The regions above already show the count changing. Saying "no
            # change was seen" here as well would make the report contradict
            # itself in consecutive sentences, which it did.
            lines.append(
                "The number of stable states changes across this range, but "
                "no single interval could be classified -- most often "
                "because the root find returned nothing on one side of the "
                "transition. The regions above locate it; nothing is named."
            )
        else:
            lines.append(
                "No change in the number or stability of steady states was "
                "seen across this range. That is a statement about the "
                "values sampled, not about the range: a change entirely "
                "between two samples is invisible to a sweep."
            )

        if self.barren:
            lines.append(
                f"The root find returned nothing at {len(self.barren)} "
                f"value(s) ({', '.join(f'{v:.4g}' for v in self.barren[:5])}"
                + ("..." if len(self.barren) > 5 else "")
                + "). A gap is not a bifurcation and is not counted as one."
            )

        lines.append(
            "Located by re-solving at each step, not by numerical "
            "continuation: a branch that exists only between two samples is "
            "not found, and every interval above is bracketed at the sweep's "
            "own resolution rather than refined."
        )
        return " ".join(lines)


def _same_state(left: FixedPoint, right: FixedPoint) -> bool:
    """Is `right` the continuation of `left` at the next parameter value?"""
    for name, value in left.state.items():
        other = right.state.get(name)
        if other is None:
            return False
        scale = max(abs(value), abs(other), 1e-12)
        if abs(value - other) / scale > CONTINUATION_TOLERANCE:
            return False
    return True


def _classify_change(before: SweepPoint, after: SweepPoint) -> Optional[Bifurcation]:
    """Name the change between two adjacent samples, or return None.

    Conservative by construction. A label is attached only when the
    numerical evidence matches the definition; a change that does not fit
    one is reported as UNNAMED rather than guessed at, because a reader told
    "Hopf" will go looking for a limit cycle.
    """
    if not before.report.physical_points or not after.report.physical_points:
        # One side found nothing. That is a gap in the sweep, not evidence
        # of a bifurcation, and calling it one would manufacture a result
        # out of a solver failure.
        return None

    stable_change = after.stable_count - before.stable_count
    total_change = after.total_count - before.total_count

    # A Hopf: a state that persists, keeps complex eigenvalues, and crosses
    # from stable to unstable. The state count does not change.
    if total_change == 0:
        for old in before.report.physical_points:
            for new in after.report.physical_points:
                if not _same_state(old, new):
                    continue
                if old.oscillatory and new.oscillatory and old.stable != new.stable:
                    direction = (
                        "loses stability" if old.stable else "regains stability"
                    )
                    return Bifurcation(
                        parameter="", below=before.value, above=after.value,
                        kind=HOPF,
                        detail=(
                            f"a spiral {direction} while remaining the only "
                            f"state of its kind -- a complex eigenvalue pair "
                            f"crosses the imaginary axis. Sustained "
                            f"oscillation begins on the unstable side; this "
                            f"sweep does not compute the limit cycle's "
                            f"amplitude."
                        ),
                    )

    # A fold: states appear or vanish in pairs, one stable and one not.
    if total_change != 0 and abs(total_change) >= 2 and stable_change != 0:
        appearing = total_change > 0
        return Bifurcation(
            parameter="", below=before.value, above=after.value, kind=FOLD,
            detail=(
                f"{abs(total_change)} steady states "
                f"{'appear' if appearing else 'vanish'} together, "
                f"{abs(stable_change)} of them stable. States arriving in "
                f"pairs is the signature of a fold: a stable state and the "
                f"saddle bounding its basin are created or destroyed at the "
                f"same value."
            ),
        )

    if stable_change != 0 or total_change != 0:
        return Bifurcation(
            parameter="", below=before.value, above=after.value, kind=UNNAMED,
            detail=(
                f"the steady states went from {before.total_count} "
                f"({before.stable_count} stable) to {after.total_count} "
                f"({after.stable_count} stable). The numerical evidence does "
                f"not match a fold or a Hopf, so nothing is named -- it may "
                f"also be the root find reaching a state at one value and "
                f"not the other."
            ),
        )
    return None


def sweep(
    network: Any,
    parameter: str,
    values: Sequence[float],
    *,
    starts_per_species: int = 8,
    seed: int = 0,
) -> SweepReport:
    """Re-analyse the model at each value of one parameter.

    The network is rebuilt for every value rather than mutated, so a sweep
    cannot leave the caller's model altered -- a real hazard when the object
    is a frozen dataclass whose `replace` returns a copy that is easy to
    forget to use.
    """
    from dataclasses import replace

    known = {p.id for p in network.parameters}
    if parameter not in known:
        raise KeyError(
            f"{parameter!r} is not a parameter of this network. It has: "
            f"{', '.join(sorted(known))}."
        )

    points: List[SweepPoint] = []
    barren: List[float] = []

    for value in values:
        altered = replace(
            network,
            parameters=tuple(
                replace(p, value=float(value)) if p.id == parameter else p
                for p in network.parameters
            ),
        )
        report = analyse(
            altered, starts_per_species=starts_per_species, seed=seed
        )
        points.append(SweepPoint(value=float(value), report=report))
        if not report.physical_points:
            barren.append(float(value))

    # Compare each sample to the next one that FOUND something, not simply
    # to its neighbour.
    #
    # A barren sample -- where the root find converged to nothing -- used to
    # blind the detector on both sides of itself, because each comparison
    # had one empty side and returned None. The toggle switch became
    # bistable across exactly such a gap, and the report listed regions with
    # different stable-state counts while simultaneously announcing that no
    # change had been seen. Bridging the gap fixes the contradiction; the
    # bracket then spans it, which is honest about how well it is located.
    solved = [point for point in points if point.report.physical_points]

    bifurcations: List[Bifurcation] = []
    for before, after in zip(solved, solved[1:]):
        change = _classify_change(before, after)
        if change is not None:
            spanned = any(
                before.value < gap < after.value for gap in barren
            )
            bifurcations.append(
                Bifurcation(
                    parameter=parameter, below=change.below, above=change.above,
                    kind=change.kind,
                    detail=change.detail + (
                        " The bracket spans a value where the root find "
                        "returned nothing, so it is wider than the sweep's "
                        "own resolution."
                        if spanned else ""
                    ),
                )
            )

    return SweepReport(
        parameter=parameter,
        points=tuple(points),
        bifurcations=tuple(bifurcations),
        barren=tuple(barren),
    )


def linear_values(low: float, high: float, steps: int = DEFAULT_STEPS) -> List[float]:
    if steps < 2:
        raise ValueError("a sweep of fewer than two values is not a sweep")
    span = (high - low) / (steps - 1)
    return [low + span * index for index in range(steps)]


def logarithmic_values(
    low: float, high: float, steps: int = DEFAULT_STEPS
) -> List[float]:
    """Log-spaced values, for a parameter whose effect is multiplicative.

    Rate constants and dissociation constants span decades, and a linear
    sweep from 0.1 to 100 spends nine tenths of its samples above 10 -- so
    it resolves the uninteresting end finely and the interesting end not at
    all.
    """
    if low <= 0 or high <= 0:
        raise ValueError(
            "a logarithmic sweep needs positive endpoints; use "
            "linear_values for a range that includes zero"
        )
    if steps < 2:
        raise ValueError("a sweep of fewer than two values is not a sweep")
    log_low, log_high = math.log10(low), math.log10(high)
    span = (log_high - log_low) / (steps - 1)
    return [10.0 ** (log_low + span * index) for index in range(steps)]


__all__ = [
    "Bifurcation", "SweepPoint", "SweepReport", "sweep",
    "linear_values", "logarithmic_values",
    "FOLD", "HOPF", "UNNAMED", "DEFAULT_STEPS", "CONTINUATION_TOLERANCE",
]
