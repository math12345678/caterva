"""Whether what the model PREDICTS is physically possible.

THE GAP THIS FILLS
------------------
`compose/scale.py` checks every number that goes IN: a kcat against
characterised turnover numbers, a Km against measured affinities, an
association rate against the diffusion limit. It never looks at what comes
OUT.

A model can pass every one of those checks and predict something that
cannot happen. Each parameter is individually plausible; their combination
is not. A synthesis rate of 1 mM/s with a degradation rate of 1e-5 /s is
two ordinary numbers whose steady state is 100 M -- twenty thousand times
the entire protein content of a cell.

Nothing caught that, because nothing was looking. `analysis.FixedPoint`
carries a flag called `physical`, which sounds like this check and is not:
it means "no species is negative". A fixed point at 100 M is `physical`.

WHAT IT CHECKS AND WHY EACH ONE
--------------------------------
Three readings, and they are genuinely different questions:

  * A STEADY STATE above the cell's total protein content is a model that
    predicts more of one species than the cell contains of all protein
    together. That is an ERROR: it is a statement about the world that is
    false, not a parameter outside a measured range.

  * A TRANSIENT can be impossible while the steady state is fine. A system
    that overshoots to 50 M on its way to a sensible 1 uM has passed
    through a state that cannot exist, and a steady-state check sees
    nothing wrong. This is the reading that catches a stiff model with a
    badly-scaled initial condition, which is the commonest way a composed
    model goes wrong in a teaching setting.

  * A steady state BELOW one molecule per cell is not an error and must not
    be reported as one. It is the statement that the deterministic model
    has stopped applying -- you cannot have 0.3 of a molecule -- and the
    answer is a stochastic simulation, not a smaller number. That is a
    QUESTION with a specific next step, and `compose/stochastic.py` is it.

WHAT IT DOES NOT DO
-------------------
It does not decide whether the model is RIGHT. Every bound here is a
property of cells, not of this model's biology: a prediction inside them is
not thereby correct, it has merely not been ruled out on grounds of
capacity. A model can predict a perfectly possible concentration of the
wrong species at the wrong time.

It also does not check anything for a model whose species are not
concentrations. The bounds are molar, and a dimensionless or per-cell-count
state is reported UNEXAMINED rather than compared against a limit that does
not apply to it -- which would be the unit slip this package exists to
catch, committed while checking for unit slips.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

try:
    from .scale import (
        ERROR, LIBRARY_CONCENTRATION_UNIT, ONE_MOLECULE_PER_BACTERIUM_MOLAR,
        QUESTION, TOTAL_CELLULAR_PROTEIN_MOLAR, _as_molar,
    )
except ImportError:  # pragma: no cover - flat import
    from scale import (  # type: ignore[no-redef]
        ERROR, LIBRARY_CONCENTRATION_UNIT, ONE_MOLECULE_PER_BACTERIUM_MOLAR,
        QUESTION, TOTAL_CELLULAR_PROTEIN_MOLAR, _as_molar,
    )


class PredictionRefused(RuntimeError):
    """The prediction check could not be set up, as distinct from failing."""


#: Verdict for a state this module could not compare against anything.
#: A THIRD STATE, kept apart from "possible" and "impossible" for the
#: reason it is kept apart everywhere else in this package: a state whose
#: unit is not molar has not been found possible, and reporting it as such
#: would be the module approving what it never read.
UNEXAMINED = "unexamined"

#: How negative a predicted amount must be before it is a NEGATIVE amount
#: rather than a zero the root finder reached from below.
#:
#: A root finder converging on a species at zero lands at -7e-43 as readily
#: as at +7e-43, and the first sweep of this module across the library
#: reported one of those as "the integrator stepped past zero" -- true, and
#: useless, and exactly the cry-wolf failure ADR 0028 names. A check that
#: fires on every model with an absent species stops being read.
#:
#: The value is `analysis.STATE_DISTINCT_TOLERANCE`, which is what that
#: module already uses to decide `FixedPoint.physical`, and it is applied
#: in the STATED unit for the same reason it is there. Duplicated rather
#: than imported so this module stays free of the analysis stack, with
#: `test_the_two_tolerances_have_not_drifted` holding them together.
NEGATIVE_TOLERANCE = 1e-6

POSSIBLE = "possible"
IMPOSSIBLE = "impossible"
QUESTIONABLE = "questionable"

VERDICTS = (IMPOSSIBLE, QUESTIONABLE, POSSIBLE, UNEXAMINED)


@dataclass(frozen=True)
class Excess:
    """One species predicted outside what a cell can hold."""

    species: str
    #: The predicted value, in the unit it was stated in.
    value: float
    unit: str
    #: The same value in molar, so the comparison is checkable by hand.
    molar: Optional[float]
    severity: str
    against: str
    detail: str
    #: When this was reached, for a trajectory. None for a steady state,
    #: which is by definition not at a time.
    at_time: Optional[float] = None

    def describe(self) -> str:
        where = f" at t={self.at_time:g}" if self.at_time is not None else ""
        molar = f" ({self.molar:.3g} M)" if self.molar is not None else ""
        return (
            f"{self.species} = {self.value:.4g} {self.unit}{molar}{where}: "
            f"{self.detail} -- against {self.against}"
        )


@dataclass(frozen=True)
class PredictionReport:
    """What a predicted state or trajectory would require of a cell."""

    #: What was read: "steady state", "trajectory", or a caller's label.
    subject: str
    findings: Tuple[Excess, ...] = ()
    #: Species compared against a bound. The other half of the coverage
    #: distinction `scale.ScaleReport` draws: without it, a report with no
    #: findings cannot say whether everything was possible or nothing was
    #: examined.
    examined: Tuple[str, ...] = ()
    #: species -> why it was not compared. A state in a unit this module
    #: does not recognise is UNEXAMINED, never assumed to be molar.
    unexamined: Mapping[str, str] = field(default_factory=dict)
    #: True when `analysis` had ALREADY marked this fixed point
    #: non-physical -- it has a negative coordinate and that module keeps
    #: it deliberately, because a negative root is a real property of the
    #: equations and hiding it makes the positive ones look like the whole
    #: story.
    #:
    #: Carried so a caller can avoid announcing as a new discovery
    #: something the analysis above it already said. A root finder over a
    #: competitive-inhibition model returns nineteen fixed points and most
    #: of them are non-physical; reporting each as a fresh impossibility
    #: is the wall of findings ADR 0028 warns about.
    already_flagged_nonphysical: bool = False

    @property
    def impossible(self) -> Tuple[Excess, ...]:
        return tuple(f for f in self.findings if f.severity == ERROR)

    @property
    def questionable(self) -> Tuple[Excess, ...]:
        return tuple(f for f in self.findings if f.severity == QUESTION)

    @property
    def examined_nothing(self) -> bool:
        """No species reached a bound, for any reason.

        DELIBERATELY NOT `not examined and not unexamined`. That was the
        first version and it was wrong in the case that matters most: a
        state whose every species was SKIPPED has a non-empty `unexamined`,
        so the conjunction was False, so `verdict` fell through to
        POSSIBLE. A report reading "0 examined, 1 skipped" then called the
        state possible, which is this module approving what it never read
        -- the exact failure it was written to prevent, committed inside
        it. Nothing examined is nothing examined, whatever the reason.
        """
        return not self.examined

    @property
    def verdict(self) -> str:
        if self.examined_nothing:
            return UNEXAMINED
        if self.impossible:
            return IMPOSSIBLE
        if self.questionable:
            return QUESTIONABLE
        return POSSIBLE

    @property
    def coverage(self) -> str:
        if self.examined_nothing:
            # WHY nothing was examined is the useful half. "nothing was
            # examined" alone invites the reader to assume the state was
            # empty, when the commoner cause is a unit this module does
            # not recognise -- which is a fixable thing and a different
            # conversation.
            if self.unexamined:
                return (
                    f"nothing was examined; {len(self.unexamined)} species "
                    "skipped for want of a concentration unit"
                )
            return "nothing was examined, and nothing was skipped either"
        if not self.unexamined:
            return f"{len(self.examined)} examined, none skipped"
        return (
            f"{len(self.examined)} examined, {len(self.unexamined)} skipped "
            "for want of a concentration unit"
        )

    def summary(self) -> str:
        lines: List[str] = []
        if self.examined_nothing:
            lines.append(
                f"NOTHING WAS EXAMINED in {self.subject}. No species carried "
                f"a concentration unit this module recognises, so there is "
                f"no verdict here -- only an absence of one."
            )
            return "\n".join(lines)

        if self.impossible:
            lines.append(
                f"{len(self.impossible)} species in {self.subject} cannot "
                f"exist at the predicted amount:"
            )
            lines += ["  - " + f.describe() for f in self.impossible]
        if self.questionable:
            lines.append(
                f"{len(self.questionable)} species in {self.subject} sit "
                f"where the deterministic model stops applying. Not an "
                f"error: a concentration below one molecule per cell is a "
                f"statement that molecule counts matter, and the answer is "
                f"a stochastic run rather than a different number."
            )
            lines += ["  - " + f.describe() for f in self.questionable]
        if not self.findings:
            lines.append(
                f"All {len(self.examined)} species in {self.subject} are at "
                f"amounts a cell could hold. That is a capacity check and "
                f"not a claim the model is right."
            )
        if self.unexamined:
            lines.append(
                f"{len(self.unexamined)} species were NOT examined: "
                + "; ".join(
                    f"{k} ({v})" for k, v in sorted(self.unexamined.items())
                )
                + ". Silence about those is absence of examination."
            )
        return "\n".join(lines)


def _one_species(
    name: str, value: float, unit: str, at_time: Optional[float] = None
) -> Tuple[Optional[Excess], bool]:
    """(finding or None, whether it was examined at all)."""
    if not math.isfinite(value):
        return Excess(
            species=name, value=value, unit=unit, molar=None, severity=ERROR,
            against="the finite numbers",
            detail=(
                "not a finite predicted amount, which means the integration "
                "diverged or divided by zero rather than that the model "
                "predicts something large"
            ),
            at_time=at_time,
        ), True

    molar = _as_molar(value, unit)
    if molar is None:
        return None, False

    if value < -NEGATIVE_TOLERANCE:
        return Excess(
            species=name, value=value, unit=unit, molar=molar, severity=ERROR,
            against="zero, below which a concentration does not exist",
            detail=(
                "a negative predicted amount. Either the integrator stepped "
                "past zero on a species that empties, or a rate law is "
                "producing what it should consume"
            ),
            at_time=at_time,
        ), True

    if molar > TOTAL_CELLULAR_PROTEIN_MOLAR:
        factor = molar / TOTAL_CELLULAR_PROTEIN_MOLAR
        return Excess(
            species=name, value=value, unit=unit, molar=molar, severity=ERROR,
            against=(
                f"total cellular protein, ~{TOTAL_CELLULAR_PROTEIN_MOLAR:g} M"
            ),
            detail=(
                f"{factor:.3g}x more of this one species than the cell "
                f"contains of all protein together. Each parameter behind "
                f"this may be plausible on its own; their combination is "
                f"not, which is why checking the inputs did not catch it"
            ),
            at_time=at_time,
        ), True

    if value < 0.0:
        # Between -NEGATIVE_TOLERANCE and zero: a root finder's zero.
        # Examined and found fine, NOT reported -- and deliberately not
        # passed to the sub-molecular check below either, which would
        # otherwise flag every absent species in every model.
        return None, True

    if 0.0 < molar < ONE_MOLECULE_PER_BACTERIUM_MOLAR:
        molecules = molar / ONE_MOLECULE_PER_BACTERIUM_MOLAR
        return Excess(
            species=name, value=value, unit=unit, molar=molar,
            severity=QUESTION,
            against=(
                f"one molecule per cell, ~{ONE_MOLECULE_PER_BACTERIUM_MOLAR:g} M"
            ),
            detail=(
                f"about {molecules:.3g} molecules in an E. coli-sized "
                f"volume. NOT an error and not a small number to be "
                f"rounded: a fraction of a molecule means the "
                f"deterministic model has stopped applying, and the answer "
                f"is compose/stochastic.py rather than a different value"
            ),
            at_time=at_time,
        ), True

    return None, True


def check_state(
    state: Mapping[str, float],
    *,
    unit: str = LIBRARY_CONCENTRATION_UNIT,
    subject: str = "this state",
) -> PredictionReport:
    """Every species in one predicted state, against what a cell can hold.

    `unit` is the concentration unit the state is in. It is a REQUIRED
    piece of context with a library default rather than something guessed
    from the numbers: a state of {"X": 1.0} is 1 M, 1 mM or 1 nM depending
    on the model, and those differ by a factor of a billion. Guessing would
    be the unit slip this package exists to catch.
    """
    if not isinstance(state, Mapping):
        raise PredictionRefused(
            f"a state is a mapping of species id to concentration; got "
            f"{type(state).__name__}. `analysis.FixedPoint.state` has this "
            f"shape, as does a column-wise slice of a trajectory."
        )

    findings: List[Excess] = []
    examined: List[str] = []
    unexamined: Dict[str, str] = {}

    for name in sorted(state):
        finding, was_examined = _one_species(name, float(state[name]), unit)
        if was_examined:
            examined.append(name)
            if finding is not None:
                findings.append(finding)
        else:
            unexamined[name] = (
                f"unit {unit!r} is not a concentration this module "
                f"recognises, so there is no bound to compare against"
            )

    return PredictionReport(
        subject=subject,
        findings=tuple(findings),
        examined=tuple(examined),
        unexamined=unexamined,
    )


def check_steady_states(
    stability: Any,
    *,
    unit: str = LIBRARY_CONCENTRATION_UNIT,
) -> Tuple[PredictionReport, ...]:
    """One report per fixed point the analysis found.

    Returns a report PER POINT rather than one merged report, because the
    points are alternatives and merging them would produce a verdict about
    no single state the system can be in. A bistable switch with one
    possible branch and one impossible one is a real and interesting
    result, and a merged report would call the whole model impossible.
    """
    points = getattr(stability, "fixed_points", None)
    if points is None:
        raise PredictionRefused(
            f"{type(stability).__name__} carries no `fixed_points`. Pass an "
            f"`analysis.StabilityReport`, or call `check_state` with a "
            f"mapping directly."
        )
    if not points:
        raise PredictionRefused(
            "no fixed point was found, so there is no predicted steady "
            "state to check. That is a finding about the model -- an open "
            "system runs forever -- and it belongs to the analysis that "
            "searched, not to this module."
        )

    reports: List[PredictionReport] = []
    for index, point in enumerate(points):
        flagged = not getattr(point, "physical", True)
        suffix = (
            " (already non-physical per the analysis)" if flagged else ""
        )
        base = check_state(
            getattr(point, "state", {}) or {},
            unit=unit,
            subject=f"steady state {index + 1} of {len(points)}{suffix}",
        )
        reports.append(PredictionReport(
            subject=base.subject,
            findings=base.findings,
            examined=base.examined,
            unexamined=base.unexamined,
            already_flagged_nonphysical=flagged,
        ))
    return tuple(reports)


def check_trajectory(
    source: Any,
    *,
    unit: str = LIBRARY_CONCENTRATION_UNIT,
    subject: str = "this trajectory",
) -> PredictionReport:
    """The whole run, not just where it ended.

    A TRANSIENT CAN BE IMPOSSIBLE WHILE THE STEADY STATE IS FINE, and that
    is the case this reading exists for. A system that overshoots to 50 M
    on its way to a sensible 1 uM has passed through a state that cannot
    exist; a steady-state check sees nothing wrong, and the curve a student
    plots looks like a spike they will try to interpret.

    Reports each species ONCE, at its most extreme sample, rather than once
    per sample above the line. A thousand-step trajectory that sits above
    the bound throughout would otherwise produce a thousand findings that
    say the same thing, which is the cry-wolf failure ADR 0028 names.
    """
    times = getattr(source, "times", None)
    columns = getattr(source, "columns", None)
    if times is None or columns is None:
        raise PredictionRefused(
            f"{type(source).__name__} carries no `times`/`columns`, so there "
            f"is nothing to read. Pass a `simulate.Trajectory` or a "
            f"`timeseries.Series`."
        )
    if not columns:
        raise PredictionRefused(
            "this trajectory has no species columns, so there is nothing to "
            "check. A report over no species would be clean and mean "
            "nothing."
        )

    findings: List[Excess] = []
    examined: List[str] = []
    unexamined: Dict[str, str] = {}

    for name in sorted(columns):
        values = columns[name]
        if len(values) != len(times):
            raise PredictionRefused(
                f"{name} has {len(values)} value(s) against {len(times)} "
                f"time(s). Reading the shorter of the two would check a "
                f"window that silently ended early."
            )
        if not values:
            unexamined[name] = "no samples in this window"
            continue

        # The extreme in BOTH directions: a species can be impossible for
        # being too large and, separately, for having gone negative, and
        # reporting only the maximum would miss an integrator that stepped
        # below zero before recovering.
        worst: Optional[Excess] = None
        for candidate_index in _extreme_indices(values):
            finding, was_examined = _one_species(
                name, float(values[candidate_index]), unit,
                at_time=float(times[candidate_index]),
            )
            if not was_examined:
                unexamined[name] = (
                    f"unit {unit!r} is not a concentration this module "
                    f"recognises, so there is no bound to compare against"
                )
                worst = None
                break
            if name not in examined:
                examined.append(name)
            if finding is not None and (
                worst is None or _rank(finding) > _rank(worst)
            ):
                worst = finding
        if worst is not None:
            findings.append(worst)

    return PredictionReport(
        subject=subject,
        findings=tuple(findings),
        examined=tuple(examined),
        unexamined=unexamined,
    )


def _extreme_indices(values: Sequence[float]) -> Tuple[int, ...]:
    """Indices of the largest and smallest sample, and any non-finite one.

    Non-finite first: a NaN anywhere is the most informative thing in the
    record, and `max`/`min` over a list containing one are not defined in
    a useful way.
    """
    for index, value in enumerate(values):
        if not math.isfinite(float(value)):
            return (index,)
    highest = max(range(len(values)), key=lambda i: float(values[i]))
    lowest = min(range(len(values)), key=lambda i: float(values[i]))
    return (highest, lowest) if highest != lowest else (highest,)


def _rank(finding: Excess) -> int:
    """ERROR outranks QUESTION, so the worse of two extremes is kept."""
    return 2 if finding.severity == ERROR else 1


__all__ = [
    "Excess", "PredictionRefused", "PredictionReport",
    "check_state", "check_steady_states", "check_trajectory",
    "IMPOSSIBLE", "POSSIBLE", "QUESTIONABLE", "UNEXAMINED", "VERDICTS",
    "NEGATIVE_TOLERANCE",
]
