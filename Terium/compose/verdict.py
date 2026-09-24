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


def _dimensional_concerns(
    model: Any,
) -> Tuple[List[Concern], Optional[str], Optional[str]]:
    """(concerns, what was consulted, or why it could not be).

    A rate law whose sides disagree is wrong, not unvalidated. It
    integrates perfectly well and is wrong by whatever factor the mistake
    introduced, which is why this is BROKEN rather than a note.

    THREE RETURNS, NOT ONE. The first version returned a bare list and
    swallowed every exception into an empty one, with a comment saying the
    check not running was "reported elsewhere". It was not; the caller
    wrote `consulted["units"] = "balanced"` over the empty list, so a
    check that RAISED was printed as a check that passed. And it read
    `unit_findings()`, which is also empty when a composition declares no
    rate law at all -- "balanced" over zero laws. Either way the page said
    the units were fine about a check that had examined nothing.

    Now: a raise is UNAVAILABLE with the reason; zero laws examined is
    UNAVAILABLE with that reason; and "balanced" is said only with the
    count of laws it is balanced across.
    """
    try:
        examined, findings = model.recognition.composition.unit_check()
    except Exception as exc:  # noqa: BLE001
        return [], None, f"{type(exc).__name__}: {exc}"

    if not examined:
        return [], None, (
            "this composition declares no rate law, so there is nothing "
            "whose dimensions could balance or fail to"
        )

    concerns = [
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
    note = (
        f"all {examined} rate law(s) balance" if not concerns
        else f"{len(concerns)} problem(s) across {examined} rate law(s)"
    )
    return concerns, note, None


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
    # "every number physically possible" is true of a model whose numbers
    # were never looked at, which is the one case a reader cannot tell from
    # the outside. So coverage leads, and the clean phrasing is reserved
    # for a check that actually ran.
    if report.examined_nothing:
        note = (
            "no number was examined -- no parameter carried a unit this "
            "module recognises, so this is silence, not approval"
        )
    elif report.findings:
        note = (
            f"{len(report.errors)} impossible, {len(report.questions)} "
            f"unusual, of {len(report.checked)} examined"
        )
    else:
        note = f"all {len(report.checked)} numbers examined are possible"
    if report.unchecked:
        note += f", {len(report.unchecked)} unchecked"
    return concerns, note


def _concentration_unit_of(model: Any) -> Optional[str]:
    """The unit the model's species amounts are in, from the model itself.

    NOT ASSUMED. A state of {"X": 1.0} is 1 M, 1 mM or 1 nM depending on
    the composition, and those differ by a factor of a billion -- so a
    bound compared against the wrong one is the unit slip this package
    exists to catch, made while checking for unit slips. The composition
    declares one concentration unit for the whole model; when there is no
    composition to ask, this returns None and the caller reports the
    check as unavailable rather than guessing.
    """
    composition = getattr(
        getattr(model, "recognition", None), "composition", None
    )
    unit = getattr(composition, "concentration_unit", None)
    return str(unit) if unit else None


def _protein_species_of(model: Any) -> Tuple[str, ...]:
    """Which species the composition wires as enzymes or regulators.

    The protein bound -- five millimolar -- is right for those and wrong
    by a factor of twenty for a metabolite. A model with no composition
    to ask gets an empty set, which sends every species to the weaker
    solute bound: the conservative direction.
    """
    composition = getattr(
        getattr(model, "recognition", None), "composition", None
    )
    if composition is None or not hasattr(composition, "protein_species"):
        return ()
    return tuple(sorted(composition.protein_species()))


def _prediction_concerns(
    stability: Any, *, unit: str, proteins: Sequence[str] = (),
) -> Tuple[List[Concern], str]:
    """What the model PREDICTS, against what a cell can hold.

    Separate from `_scale_concerns` because it asks a different question.
    That one checks the numbers the model was GIVEN; this checks the
    numbers it PRODUCES, and a model can pass the first and fail the
    second -- each parameter plausible, their combination not. Checking
    the inputs cannot catch that, by construction.

    Runs off the stability report the caller already computed, so it costs
    nothing beyond the comparison.
    """
    try:
        from .predictions import UNEXAMINED, check_steady_states
    except ImportError:  # pragma: no cover - flat import
        from predictions import (  # type: ignore[no-redef]
            UNEXAMINED, check_steady_states,
        )

    reports = check_steady_states(stability, unit=unit, proteins=proteins)
    concerns: List[Concern] = []
    for report in reports:
        if report.already_flagged_nonphysical:
            # `analysis` keeps negative roots on purpose -- they are a real
            # property of the equations -- and already labels them. Raising
            # each one again here as a BROKEN concern would fill the page
            # with the same fact in different words: a root finder over a
            # competitive-inhibition model returns twenty-odd points and
            # several are non-physical by construction.
            continue
        concerns += [
            Concern(
                source="predictions",
                severity=BROKEN,
                detail=f"{report.subject}: {excess.describe()}",
                remedy=(
                    "the parameters behind this are each plausible and "
                    "their combination is not -- the ratio that sets this "
                    "steady state is what to look at, not any one constant"
                ),
            )
            for excess in report.impossible
        ]

    judged = [r for r in reports if not r.already_flagged_nonphysical]
    skipped = len(reports) - len(judged)
    examined = sum(len(r.examined) for r in judged)
    impossible = sum(len(r.impossible) for r in judged)
    questionable = sum(len(r.questionable) for r in judged)

    if not judged:
        return concerns, (
            f"{len(reports)} steady state(s) found and every one was "
            f"already marked non-physical by the analysis, so this check "
            f"had nothing left of its own to say"
        )

    aside = (
        f" ({skipped} already non-physical, not re-counted here)"
        if skipped else ""
    )
    if all(r.verdict == UNEXAMINED for r in judged):
        note = (
            f"{len(judged)} steady state(s) found, none examined -- no "
            f"species carried a concentration unit this module recognises, "
            f"so this is silence and not approval{aside}"
        )
    elif impossible:
        note = (
            f"{impossible} species cannot exist at the amount predicted, "
            f"across {len(judged)} steady state(s){aside}"
        )
    elif questionable:
        note = (
            f"all {examined} predicted amounts are possible; "
            f"{questionable} sit below one molecule per cell, where the "
            f"deterministic model stops applying{aside}"
        )
    else:
        note = (
            f"all {examined} predicted amounts across {len(judged)} steady "
            f"state(s) are amounts a cell could hold{aside}"
        )
    return concerns, note


def _grounding(model: Any) -> Tuple[int, int, bool]:
    """(measured, unmeasured, whether the model carries provenance at all).

    THE ONLY WAY TO KNOW WHETHER A CONSTANT WAS MEASURED IS TO ASK THE
    PROVENANCE. The verdict used to ask `structure_only` instead, which
    means "no subject was named" -- and so typing an enzyme's name into the
    query, with no search run and every constant still the library's
    placeholder, flipped the page to GROUNDED: "grounded in measured
    constants, with the provenance to show it". Nothing had been measured.
    The provenance note said "constants resolved". This is the single
    claim the package exists never to make, made at the top of the page by
    the module whose job is to say what the evidence supports.

    A `ProvenancedModel` (from `export.provenance_of`) carries `measured`
    and `placeholders`. A bare `ComposedModel` carries neither, and a model
    with no provenance has had nothing resolved, whatever its query said.
    """
    measured = getattr(model, "measured", None)
    placeholders = getattr(model, "placeholders", None)
    if measured is None or placeholders is None:
        resolvable = list(getattr(model, "resolvable", ()))
        return 0, len(resolvable), False
    try:
        return len(measured), len(placeholders), True
    except TypeError:
        resolvable = list(getattr(model, "resolvable", ()))
        return 0, len(resolvable), False


def _influence_is_informative(influence: Any) -> Optional[bool]:
    """Does the influence ranking single anything out? None = no ranking.

    WHY THE VERDICT HAS TO ASK
    --------------------------
    The provenance concern's remedy used to end "start with the top of its
    influence ranking" unconditionally. On a saturated model that advice
    contradicts the same report's own provenance section, which says "No
    constant here clears |S| = 0.01, so measuring any single one of them
    would not move this answer" -- the reader is told to act on a ranking
    the document has just called uninformative, in the one line labelled
    "Do this next".

    This is the same defect `_settling_ranking` was written for (a ranking
    pinned to zero by a conservation law) in its other form: there the
    ranking was empty because the question was asked of the wrong quantity,
    here because the mechanism is running flat out. Both were advice
    pointing at nothing.
    """
    if influence is None:
        return None
    try:
        from .sensitivity import NEGLIGIBLE_INFLUENCE
    except ImportError:  # pragma: no cover - flat import
        from sensitivity import NEGLIGIBLE_INFLUENCE  # type: ignore[no-redef]
    entries = getattr(influence, "sensitivities", None)
    if not entries:
        return None
    return any(abs(getattr(e, "relative", 0.0)) >= NEGLIGIBLE_INFLUENCE for e in entries)


def _provenance_concerns(
    model: Any, influence: Any = None,
) -> Tuple[List[Concern], str]:
    """Placeholders are not a fault. They are a limit on the question.

    This is the commonest state of a composed model and the report must not
    scold the reader for it -- but it must say plainly that the conclusions
    are about the mechanism rather than about their system.
    """
    measured, unmeasured, has_provenance = _grounding(model)
    subject = getattr(model, "subject", None)

    if unmeasured == 0 and measured > 0:
        return [], f"all {measured} constant(s) measured, with provenance"
    if unmeasured == 0 and measured == 0:
        return [], "nothing to resolve"

    if measured:
        detail = (
            f"{measured} constant(s) measured and {unmeasured} still the "
            f"motif library's illustrative values"
        )
        note = f"{measured} measured, {unmeasured} unmeasured"
    elif subject and not has_provenance:
        # THE CASE THAT USED TO READ AS GROUNDED. A subject was named, so a
        # search could be run -- and has not been. Say exactly that.
        detail = (
            f"all {unmeasured} rate constant(s) are the motif library's "
            f"illustrative values. {subject!r} was named, so a literature "
            f"search is possible, but none has been run and no value here "
            f"comes from one"
        )
        note = (
            f"{unmeasured} constant(s) unmeasured -- {subject!r} named, "
            f"no search run"
        )
    elif subject:
        detail = (
            f"all {unmeasured} rate constant(s) are still placeholders: "
            f"the search for {subject!r} found nothing it could use"
        )
        note = f"{unmeasured} constant(s) unmeasured after searching"
    else:
        detail = (
            f"all {unmeasured} rate constant(s) are the motif library's "
            f"illustrative values, because no enzyme was named"
        )
        note = f"{unmeasured} constant(s) unmeasured"

    source = (
        f"run the literature search for {subject!r}, or supply the "
        f"constants the provenance table lists"
        if subject else
        "name the enzyme, or supply the constants the provenance table lists"
    )
    informative = _influence_is_informative(influence)
    if informative is True:
        remedy = f"{source} -- start with the top of its influence ranking"
    elif informative is False:
        # Saying "start with the top of the ranking" here would contradict
        # the provenance section, which has just reported that nothing in
        # the ranking clears the noise. Ground the model first: the ranking
        # is computed AT the placeholder values, and it is those values that
        # put the model where nothing moves it.
        remedy = (
            f"{source} -- not in the influence ranking's order, which at "
            f"these values singles nothing out: every constant is below the "
            f"threshold because the placeholders have the mechanism running "
            f"flat out. Ground it first and the ranking becomes meaningful"
        )
    else:
        remedy = f"{source} (no influence ranking was computed for this model)"
    return (
        [Concern(source="provenance", severity=STRUCTURAL,
                 detail=detail, remedy=remedy)],
        note,
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
    # Counted over ALL fixed points, not just the physical ones. A line of
    # equilibria is established by every point the search landed on it,
    # and most of the line usually lies outside the physical region --
    # two enzymes competing for one substrate put 18 of 19 points at
    # negative product. The physical count says how much of the line the
    # cell can occupy; the total says the line is there.
    continuum = [
        p for p in getattr(stability, "fixed_points", ())
        if getattr(p, "classification", "") == "continuum"
    ]
    continuum_physical = [p for p in continuum if getattr(p, "physical", True)]

    if not getattr(stability, "fixed_points", ()):
        return (
            "no steady state was found from "
            f"{getattr(stability, 'starts_tried', '?')} starting points -- an "
            "open system runs forever rather than settling, so every "
            "steady-state question below is the wrong question for it"
        )
    if continuum and not stable:
        # A LINE OF EQUILIBRIA, NOT A SWITCH. Every point found is
        # attracting in all directions but one, and along that one the
        # dynamics do not move. The system reaches the line and stops;
        # WHERE on the line is set by the transient. Two enzymes competing
        # for one substrate produce it -- once the substrate is gone, any
        # split of product is an equilibrium -- and before `CONTINUUM`
        # existed as a classification this page read "19 stable states
        # were found, which is what a switch looks like". It is not what a
        # switch looks like; a switch has discrete attractors with
        # repellors between them.
        #
        # THE COUNT IS NOT THE FINDING. How many points the search lands on
        # a line is an artefact of where the starts fell -- one run found
        # 23 here and another 19 -- so it is stated as a count of samples,
        # not as a number of states.
        return (
            f"a LINE of equilibria was found ({len(continuum)} points on it, "
            f"{len(continuum_physical)} physically reachable), none of them "
            f"an attractor on its own -- the system reaches the line and "
            f"stops, and where on it is decided by the transient rather than "
            f"by the constants. That is not a switch, and 'which state' has "
            f"no answer here; a time course from your actual starting "
            f"amounts does"
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
    influence: Optional[Any] = None,
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

    unit_concerns, unit_note, unit_failure = _dimensional_concerns(model)
    concerns += unit_concerns
    if unit_failure is not None:
        unavailable["units"] = unit_failure
    else:
        consulted["units"] = unit_note or "consulted"

    try:
        scale_concerns, scale_note = _scale_concerns(model)
        concerns += scale_concerns
        consulted["scale"] = scale_note
    except Exception as exc:  # noqa: BLE001
        unavailable["scale"] = f"{type(exc).__name__}: {exc}"

    prediction_unit = _concentration_unit_of(model)
    if stability is None:
        unavailable["predictions"] = (
            "no stability report was passed, so there is no predicted "
            "steady state to check"
        )
    elif prediction_unit is None:
        # Guessing mM here would compare a bound in molar against numbers
        # that might be anything. UNAVAILABLE is the honest state.
        unavailable["predictions"] = (
            "this model declares no concentration unit, so a predicted "
            "amount cannot be compared against what a cell can hold "
            "without assuming one"
        )
    else:
        try:
            prediction_concerns, prediction_note = _prediction_concerns(
                stability, unit=prediction_unit,
                proteins=_protein_species_of(model),
            )
            concerns += prediction_concerns
            consulted["predictions"] = prediction_note
        except Exception as exc:  # noqa: BLE001
            unavailable["predictions"] = f"{type(exc).__name__}: {exc}"

    provenance_concerns, provenance_note = _provenance_concerns(model, influence)
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
        unavailable["validate"] = (
            "not run -- pass --validate (or `validation=`) for the "
            "cross-module consistency check"
        )
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
        unavailable["robustness"] = (
            "not run -- pass --robustness (or `robustness=`) to resample "
            "the placeholders"
        )
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

    # GROUNDED IS EARNED BY PROVENANCE, NOT BY NAMING A SUBJECT. This
    # used to read `structure_only`, so a query that named an enzyme --
    # with no search run and every constant a placeholder -- was graded
    # "grounded in measured constants, with the provenance to show it".
    measured, unmeasured, _ = _grounding(model)
    grounded = unmeasured == 0 and measured > 0

    if any(c.severity == BROKEN for c in concerns):
        verdict = BROKEN
    elif not grounded:
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
