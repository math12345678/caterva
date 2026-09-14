"""One page, above the dossier: what is known, and how well.

WHY A LAYER ABOVE THE REPORT
-----------------------------
`report.py` assembles everything the compose package can say about a model
into one document, and it is thorough. Thoroughness is the problem. A reader
opening six pages of structure, invariants, dimensions, provenance, steady
states, sensitivities, sweeps and time courses has to decide for themselves
which parts are load-bearing, and the decision that matters is not in any one
section: it is whether the model is worth using at all, and for what.

That judgement needs several sections at once. A bistability claim means one
thing when the constants are measured and another when they are the library's
illustrative values. A sharp EC50 means one thing when the model's numbers
are physically possible and another when a Km is tighter than avidin-biotin.
A sensitivity ranking means nothing when the steady state it ranks against is
pinned by a conservation law.

So this reads the other modules' reports and produces the paragraph a
researcher actually needs: what this model can be used for, what it cannot,
and which single thing would most improve it.

WHAT IT REFUSES TO DO
---------------------
Produce a score. There is no number that summarises "is this model any good",
and inventing one would be the most quotable thing in the package and the
least defensible -- a reader would cite the 7.3 and never read the sentence
under it.

It produces a GRADE over a small, named set of verdicts, each of which maps to
a concrete statement about what the model supports. The grades are ordered but
the ordering is a convenience for sorting, not a measurement.

It also refuses to average. A model that is structurally sound and numerically
absurd is not "medium" -- it is a model with a specific, nameable problem, and
the whole value of the page is naming it. The worst finding sets the verdict,
and the finding is reported rather than folded in.

THE ONE CLAIM IT MAKES THAT NOTHING ELSE DOES
----------------------------------------------
That the pieces AGREE. `validate.py` cross-checks them; this reports the
result where a reader will see it. Two independent routes to the same fact
disagreeing is the most informative thing this package can find about itself,
and burying it in a subsection would waste it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

# ---------------------------------------------------------------------------
# Verdicts
# ---------------------------------------------------------------------------

#: The model is wrong, not merely unvalidated. A dimensional mismatch, a
#: physically impossible constant, a conservation law violated during
#: integration. Nothing downstream is worth reading.
BROKEN = "broken"

#: The structure is sound and the numbers are placeholders. This is the
#: NORMAL state of a composed model and is not a criticism: it supports
#: questions about the mechanism's shape and no questions about a real
#: system. Most models this package builds are here and should be.
STRUCTURAL = "structural"

#: Grounded in measured constants, with the provenance to show it.
GROUNDED = "grounded"

#: Grounded, and its conclusions survive the uncertainty in those
#: measurements. The strongest thing this package can say.
ROBUST = "robust"

#: Ordered worst-first, which is the order a reader should meet them in.
VERDICTS = (BROKEN, STRUCTURAL, GROUNDED, ROBUST)

#: What each verdict licenses, in the reader's own terms. Kept beside the
#: constants because a verdict without its licence is a label, and labels
#: get quoted.
LICENCE = {
    BROKEN: (
        "Nothing. A specific thing is wrong and is named below; fix that "
        "before reading any other number in this report."
    ),
    STRUCTURAL: (
        "Questions about the MECHANISM: can this shape oscillate, can it "
        "switch, which constants would matter if you measured them. Not "
        "questions about any particular enzyme or cell, because the "
        "constants are the library's illustrative values."
    ),
    GROUNDED: (
        "Questions about the system whose constants these are, AT the "
        "conditions those constants were measured at. Not questions about "
        "other conditions, other organisms, or other enzyme concentrations "
        "unless the report says those were checked."
    ),
    ROBUST: (
        "The same questions as GROUNDED, plus the knowledge that the "
        "conclusion named below survived the measured uncertainty rather "
        "than sitting on one particular set of values."
    ),
}


class VerdictError(RuntimeError):
    """A verdict could not be formed, as distinct from being unfavourable."""


@dataclass(frozen=True)
class Concern:
    """One thing wrong, or one thing missing, and what it costs."""

    #: Which module found it, so a reader can go and read that section.
    source: str
    #: BROKEN for something wrong; the others for something absent.
    severity: str
    detail: str
    #: What to do about it, concretely. A concern with no action is a
    #: complaint.
    remedy: str = ""

    def describe(self) -> str:
        text = f"[{self.source}] {self.detail}"
        return f"{text} -- {self.remedy}" if self.remedy else text


@dataclass(frozen=True)
class Verdict:
    """What this model is good for, and the single thing that would help."""

    verdict: str
    concerns: Tuple[Concern, ...]
    #: The conclusion the robustness run was about, when one was made.
    conclusion: Optional[str] = None
    #: What the mechanism DOES, from the steady-state search. The one line
    #: that differs between two models, and the reason this page is worth
    #: reading rather than merely true -- see `behaviour_of`.
    behaviour: Optional[str] = None
    #: Module name -> one-line summary of what it found. Reported so the
    #: page can say what it actually looked at, rather than implying it
    #: looked at everything.
    consulted: Mapping[str, str] = field(default_factory=dict)
    #: Modules that could not run, with the reason. Silence about a check
    #: that did not run reads as a check that passed.
    unavailable: Mapping[str, str] = field(default_factory=dict)

    @property
    def blocking(self) -> Tuple[Concern, ...]:
        return tuple(c for c in self.concerns if c.severity == BROKEN)

    @property
    def usable(self) -> bool:
        """Whether any downstream number is worth reading.

        Deliberately not called `valid`, and deliberately not a score: this
        answers one question, which is whether to keep reading.
        """
        return self.verdict != BROKEN

    def next_step(self) -> Optional[str]:
        """The single highest-value thing to do next.

        ONE, not a list. A report that ends with nine suggestions has
        prioritised nothing, and the reader picks the easiest rather than
        the most valuable. The first concern is the worst one, because the
        concerns are built worst-first.
        """
        for concern in self.concerns:
            if concern.remedy:
                return concern.remedy
        return None

    def summary(self) -> str:
        lines = [
            f"VERDICT: {self.verdict.upper()}",
            "",
            f"What this supports: {LICENCE[self.verdict]}",
        ]

        if self.behaviour:
            lines.append("")
            lines.append(f"What this model does: {self.behaviour}")

        if self.conclusion:
            lines.append("")
            lines.append(f"The conclusion tested: {self.conclusion}")

        if self.concerns:
            lines.append("")
            lines.append(
                f"{len(self.concerns)} concern(s), worst first:"
            )
            for concern in self.concerns:
                lines.append("  - " + concern.describe())

        step = self.next_step()
        if step:
            lines.append("")
            lines.append(f"Do this next: {step}")

        if self.consulted:
            lines.append("")
            lines.append(
                "Checked: "
                + "; ".join(f"{k} ({v})" for k, v in sorted(self.consulted.items()))
                + "."
            )

        if self.unavailable:
            lines.append("")
            lines.append(
                f"{len(self.unavailable)} check(s) did NOT run: "
                + "; ".join(
                    f"{k} ({v})" for k, v in sorted(self.unavailable.items())
                )
                + ". Those are unexamined, not passed."
            )

        lines.append("")
        lines.append(
            "This page is a reading of the sections below, not a measurement "
            "of its own. There is deliberately no score: the worst finding "
            "sets the verdict and is named, because a model that is "
            "structurally sound and numerically absurd is not 'medium' -- it "
            "has one specific problem, and naming it is the point."
        )
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Forming the verdict
# ---------------------------------------------------------------------------


def _dimensional_concerns(model: Any) -> List[Concern]:
    """A rate law whose sides disagree is wrong, not unvalidated.

    It integrates perfectly well and is wrong by whatever factor the
    mistake introduced, which is why this is BROKEN rather than a note.
    """
    try:
        findings = list(model.recognition.composition.unit_findings())
    except Exception:  # noqa: BLE001 - the check not running is reported elsewhere
        return []
    return [
        Concern(
            source="units",
            severity=BROKEN,
            detail=f"{finding.severity} in {finding.where}: {finding.detail}",
            remedy=(
                "fix the rate law -- a dimensional mismatch integrates "
                "cleanly and is wrong by whatever factor it introduced"
            ),
        )
        for finding in findings
    ]


def _scale_concerns(model: Any) -> Tuple[List[Concern], str]:
    try:
        from .scale import check_model
    except ImportError:  # pragma: no cover - flat import
        from scale import check_model  # type: ignore[no-redef]

    report = check_model(model)
    concerns = [
        Concern(
            source="scale",
            severity=BROKEN,
            detail=finding.describe(),
            remedy=(
                "check the units on this constant -- a factor of a thousand "
                "is dimensionally invisible and this is what it looks like"
            ),
        )
        for finding in report.errors
    ]
    note = (
        f"{len(report.errors)} impossible, {len(report.questions)} unusual"
        if report.findings else "every number physically possible"
    )
    if report.unchecked:
        note += f", {len(report.unchecked)} unchecked"
    return concerns, note


def _provenance_concerns(model: Any) -> Tuple[List[Concern], str]:
    """Placeholders are not a fault. They are a limit on the question.

    This is the commonest state of a composed model and the report must not
    scold the reader for it -- but it must say plainly that the conclusions
    are about the mechanism rather than about their system.
    """
    resolvable = list(getattr(model, "resolvable", ()))
    if not getattr(model, "structure_only", False):
        return [], "constants resolved"
    if not resolvable:
        return [], "nothing left to resolve"
    return (
        [Concern(
            source="provenance",
            severity=STRUCTURAL,
            detail=(
                f"all {len(resolvable)} rate constant(s) are the motif "
                f"library's illustrative values, because no enzyme was named"
            ),
            remedy=(
                f"name the enzyme, or supply the constants the provenance "
                f"table lists -- start with the top of its influence ranking"
            ),
        )],
        f"{len(resolvable)} constant(s) unmeasured",
    )


def behaviour_of(stability: Any) -> Optional[str]:
    """What this mechanism DOES, in one clause.

    WHY THE VERDICT NEEDS THIS AT ALL. Swept across the eleven models the
    composer builds, this page returned an identical verdict for every one
    of them: STRUCTURAL, one concern, the same next step. True of all
    eleven, and useless -- it said the same thing about a toggle switch and
    about an open system that has no steady state whatsoever.

    The package already knew they were different. `analysis.analyse`
    reports 2 stable states for the toggle, 0 for the open system, and an
    oscillatory pair for the repressilator. The verdict simply never asked.

    A summary that cannot tell two models apart is not summarising them, so
    the defining behaviour goes at the top where a reader meets it first.
    Phrased as what the SEARCH found, never as what the system is --
    `analysis.py` reports "at least two stable states were found" and this
    must not upgrade that to "this system is bistable" on the way past.
    """
    if stability is None:
        return None
    stable = getattr(stability, "stable_points", ())
    physical = getattr(stability, "physical_points", ())
    oscillatory = [p for p in physical if getattr(p, "oscillatory", False)]

    if not getattr(stability, "fixed_points", ()):
        return (
            "no steady state was found from "
            f"{getattr(stability, 'starts_tried', '?')} starting points -- an "
            "open system runs forever rather than settling, so every "
            "steady-state question below is the wrong question for it"
        )
    if len(stable) > 1:
        return (
            f"{len(stable)} stable states were found, which is what a switch "
            f"looks like -- and which of them is reached depends on where the "
            f"system started, not on the constants alone"
        )
    if oscillatory and any(
        v.real > 0 for p in oscillatory for v in getattr(p, "eigenvalues", ())
    ):
        return (
            "an unstable spiral was found, which is what a sustained "
            "oscillation looks like in a linearisation"
        )
    if len(stable) == 1:
        settled = stable[0]
        if getattr(settled, "oscillatory", False):
            # A STABLE SPIRAL, which is not the same as a sustained
            # oscillation and not the same as a monotonic approach either.
            # The repressilator lands here at the library's default
            # constants: it rings and settles rather than oscillating
            # forever, which is a real property of those constants and the
            # single most interesting thing this page can say about it.
            # Reporting only "one stable state" threw that away.
            return (
                "one stable state was found, and the approach to it SPIRALS "
                "-- a damped oscillation that rings and settles, which is "
                "not a sustained one. A mechanism built to oscillate is "
                "telling you these particular constants do not make it"
            )
        return (
            "one stable state was found, and the search did not find another "
            "-- which is not the same as there being none"
        )
    return (
        f"{len(getattr(stability, 'fixed_points', ()))} fixed point(s) were "
        f"found and none of them is stable"
    )


def form(
    model: Any,
    *,
    stability: Optional[Any] = None,
    robustness: Optional[Any] = None,
    validation: Optional[Any] = None,
    conclusion_name: Optional[str] = None,
) -> Verdict:
    """Read the other modules' reports and say what the model supports.

    Takes already-computed reports rather than running them, because each is
    expensive and the caller -- `report.dossier` -- has usually run them
    already. Passing `None` means that check did not run, which is recorded
    as UNAVAILABLE rather than treated as a pass: silence about a check that
    did not run reads as a check that passed, and that is the failure this
    whole package is built against.
    """
    concerns: List[Concern] = []
    consulted: Dict[str, str] = {}
    unavailable: Dict[str, str] = {}

    concerns += _dimensional_concerns(model)
    consulted["units"] = (
        "balanced" if not concerns else f"{len(concerns)} problem(s)"
    )

    try:
        scale_concerns, scale_note = _scale_concerns(model)
        concerns += scale_concerns
        consulted["scale"] = scale_note
    except Exception as exc:  # noqa: BLE001
        unavailable["scale"] = f"{type(exc).__name__}: {exc}"

    provenance_concerns, provenance_note = _provenance_concerns(model)
    concerns += provenance_concerns
    consulted["provenance"] = provenance_note

    try:
        from .assumptions import check as check_assumptions
    except ImportError:  # pragma: no cover - flat import
        from assumptions import check as check_assumptions  # type: ignore[no-redef]
    try:
        stated = check_assumptions(model)
        concerns += [
            Concern(
                source="assumptions",
                severity=BROKEN,
                detail=finding.describe(),
                remedy=(
                    "the rate law still integrates -- it is describing "
                    "something other than what the motif claims, so either "
                    "narrow the window or use a motif whose assumption holds"
                ),
            )
            for finding in stated.violated
        ]
        consulted["assumptions"] = (
            f"{len(stated.violated)} violated, {len(stated.undecided)} undecided"
            if stated.findings else "none checkable"
        )
    except Exception as exc:  # noqa: BLE001
        unavailable["assumptions"] = f"{type(exc).__name__}: {exc}"

    if validation is None:
        unavailable["validate"] = "not run"
    else:
        failures = [
            f for f in getattr(validation, "findings", ())
            if getattr(f, "severity", "") in ("error", BROKEN)
        ]
        concerns += [
            Concern(
                source="validate",
                severity=BROKEN,
                detail=str(getattr(f, "detail", f)),
                remedy=(
                    "two independent routes to the same fact disagree, so "
                    "one of them is wrong -- this is the most informative "
                    "thing the package can find about itself"
                ),
            )
            for f in failures
        ]
        consulted["validate"] = (
            "cross-checks agree" if not failures
            else f"{len(failures)} disagreement(s)"
        )

    if stability is None:
        unavailable["stability"] = "not run, so this page cannot say what the model does"
    else:
        consulted["stability"] = (
            f"{len(getattr(stability, 'stable_points', ()))} stable state(s) "
            f"from {getattr(stability, 'starts_tried', '?')} starting points"
        )

    if robustness is None:
        unavailable["robustness"] = "not run"
    else:
        fraction = getattr(robustness, "fraction", None)
        if fraction is None:
            consulted["robustness"] = "no sample could be evaluated"
        else:
            consulted["robustness"] = (
                f"{robustness.held_count}/{len(robustness.evaluated)} samples"
            )

    # WORST FIRST, and no averaging. A model that is structurally sound and
    # numerically absurd has one specific problem, and the page exists to
    # name it rather than to blend it into a middling grade.
    concerns.sort(key=lambda c: VERDICTS.index(c.severity))

    if any(c.severity == BROKEN for c in concerns):
        verdict = BROKEN
    elif getattr(model, "structure_only", False):
        verdict = STRUCTURAL
    elif robustness is not None and getattr(robustness, "fraction", None) == 1.0:
        verdict = ROBUST
    else:
        verdict = GROUNDED

    return Verdict(
        verdict=verdict,
        behaviour=behaviour_of(stability),
        concerns=tuple(concerns),
        conclusion=(
            conclusion_name
            or getattr(robustness, "conclusion", None)
        ),
        consulted=consulted,
        unavailable=unavailable,
    )


__all__ = [
    "BROKEN", "STRUCTURAL", "GROUNDED", "ROBUST", "VERDICTS", "LICENCE",
    "Concern", "Verdict", "VerdictError", "form", "behaviour_of",
]
