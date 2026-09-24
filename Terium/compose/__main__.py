"""`python -m Terium.compose "three step phosphorylation cascade"`.

A capability nobody can reach is not a capability (ADR 0090). The
compositional builder is reachable from the API runner and from Python;
this is the surface a researcher at a terminal actually uses, and it needs
no server, no key and no network.

WHY EVERY ANALYSIS IS A FLAG ON ONE COMMAND
-------------------------------------------
`compose/` grew seventeen modules that nothing outside the test suite ever
called. Each of them answers a question a researcher asks out loud -- is
this number physical, does the conclusion survive the placeholders, is a
quasi-steady-state argument licensed here, which constant could a fit even
recover, what should I measure next -- and each of them was reachable only
by writing Python against an undocumented signature. That is a library, not
a tool, and the difference is exactly ADR 0090's subject.

They are flags on the existing command rather than subcommands of their own
because every one of them is a question ABOUT A MODEL, and the model comes
from the same sentence either way. `terium crnt --model ...` would require a
model file to exist first; `python -m Terium.compose "..." --crnt` asks the
question in the form the researcher already has it.

WHAT A REFUSAL DOES HERE, WHICH IS THE POINT OF THE DESIGN
----------------------------------------------------------
Most of these modules refuse more often than they answer, and they are
right to: a timescale separation that is not there, a deficiency theorem
whose hypotheses do not hold, an SSA on a rate law that has no propensity.
A refusal is a finding about the model, so it is printed IN the report,
under the heading of the section it belongs to, and the remaining sections
still run.

The alternative -- abort on the first refusal -- would mean a model with
Michaelis-Menten kinetics could never be asked anything, because `--crnt`
and `--stochastic` both decline it on the same true fact. One module
declining is not the report failing.

Each section prints under its own heading whether it answered or declined,
so a reader can tell "this was asked and the answer is no" from "this was
never asked", which is the distinction `ScaleReport.unchecked` and
`ValidationReport.unchecked` both exist to preserve.

EXIT CODES
----------
    0   everything asked for was produced
    2   the question was not well formed -- no description, an unknown
        flag, a combination with no meaning. argparse's own code, kept.
    3   a REFUSAL with information in it: the shape was not recognised, or
        an analysis declined and said why. The report is still on stdout.
    1   a crash. Nothing here converts one into a 3: a module raising
        something it does not declare is a bug in that module, and a CLI
        that quietly reported it as a refusal would hide it.

A run with none of the analysis flags exits exactly as it did before this
file grew: the dossier's own internal failures are notes inside the report
and do not move the exit code.

WHAT THIS DOES NOT CLAIM
------------------------
That the sections agree with each other. They deliberately do not share a
steady-state search: `--reduction`, `--design` and `--validate` each run
their own, because each needs a different guarantee about it, and a shared
one would silently answer one module's question with another's state.
`--validate` is the module whose job IS cross-checking them, and it is the
only place in this file where agreement is asserted.

Nor does any flag here supply a number. Every constant in the model is
still the motif library's illustrative placeholder until an enzyme is
named, and the sections say so where it changes what they mean.
"""

from __future__ import annotations

from dataclasses import replace

import argparse
import sys
from typing import Any, Callable, List, Optional, Sequence, Tuple

#: `--robustness` given with no sample count. argparse cannot use `None`
#: for both "flag absent" and "flag present, number unstated", and the
#: number that fills in is `robustness.DEFAULT_SAMPLES` -- which lives in
#: that module with the arithmetic that chose it, and is not restated here.
SAMPLES_UNSTATED = -1

#: The SSA seed when the caller does not give one. ADR 0005 requires the
#: seed to be explicit; a CLI still has to have an answer when nobody types
#: one, so the default is named here and PRINTED in the output rather than
#: left implicit -- an unreproducible trajectory is the failure the ADR is
#: about, and a stated default is reproducible.
DEFAULT_SEED = 0

#: The export formats, in the order the help lists them.
EXPORT_FORMATS = ("sbml", "antimony", "csv", "methods")

#: Flags that add a section to the report. Named as a set because
#: `--export` has to refuse to run alongside any of them -- see
#: `_check_combination`.
ANALYSIS_FLAGS = (
    "scale", "robustness", "crnt", "reduction", "identifiability",
    "design", "validate", "knockout", "overexpress", "screen", "stochastic",
)


def build_parser(prog: str = "python -m Terium.compose") -> argparse.ArgumentParser:
    """`prog` is how the caller is invoked: the module form from a checkout,
    `terium-compose` from the wheel's console script, `terrium compose` from
    the app folder's one executable. The examples follow it, so `--help`
    never shows a command the user cannot type (ADR 0177)."""
    parser = argparse.ArgumentParser(
        prog=prog,
        description=(
            "Build a mechanistic model from a description of its mechanism. "
            "Recognises shapes -- a cascade, a toggle switch, competition "
            "for a substrate -- deterministically, with no language model."
        ),
        epilog=(
            "Examples:\n"
            f"  {prog} 'three step phosphorylation cascade'\n"
            f"  {prog} 'a toggle switch between two repressors' --sweep geneA_n\n"
            f"  {prog} 'three step phosphorylation cascade' --rank-against tier2_Xp\n"
            f"  {prog} 'reversible binding of a ligand to a receptor' --crnt --scale\n"
            f"  {prog} 'two enzymes competing for the same substrate' --screen\n"
            f"  {prog} 'reversible binding of a ligand to a receptor' --export sbml > model.xml\n"
            f"  {prog} --shapes\n"
            "\n"
            "Exit codes: 0 produced everything asked for, 2 the question was "
            "not well formed, 3 something refused and said why (the report "
            "is still printed), 1 a crash.\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("description", nargs="?",
                        help="the mechanism to build")
    parser.add_argument("--subject",
                        help="the enzyme these constants belong to: an EC number "
                             "(1.1.1.27) searches the literature; a name is "
                             "resolved through UniProt and refused if it means "
                             "more than one enzyme")
    parser.add_argument("--organism",
                        help="the organism the constants should belong to, e.g. "
                             "'Homo sapiens'. Only used when --subject names one")
    parser.add_argument("--substrate",
                        help="the substrate a Km or Ki belongs to. A motif knows "
                             "it needs a Km; it cannot know what the Km is FOR, "
                             "and BRENDA's km and ki tables cannot be read "
                             "without it")
    parser.add_argument("--shapes", action="store_true",
                        help="list every shape this can build, and exit")
    parser.add_argument("--antimony", action="store_true",
                        help="emit Antimony source instead of a report")
    parser.add_argument("--no-analysis", action="store_true",
                        help="skip the steady-state analysis (much faster)")
    parser.add_argument("--no-simulate", action="store_true",
                        help="skip the time course")
    parser.add_argument("--no-ranking", action="store_true",
                        help=("skip the influence ranking of the unmeasured "
                              "constants (it re-solves the steady state twice "
                              "per constant)"))
    parser.add_argument("--rank-against", metavar="SPECIES",
                        help=("rank influence on this species instead of the "
                              "one the last motif declares it produces. Also "
                              "the readout for --knockout/--overexpress/"
                              "--screen and the quantity --validate "
                              "cross-checks, so one document does not talk "
                              "about two different answers"))
    parser.add_argument("--sweep", action="append", default=[], metavar="PARAM",
                        help="sweep this parameter and report bifurcations; repeatable")
    parser.add_argument("--sweep-from", type=float, default=0.1)
    parser.add_argument("--sweep-to", type=float, default=10.0)
    parser.add_argument("--sweep-steps", type=int, default=15)

    analyses = parser.add_argument_group(
        "analyses",
        "Each adds a section to the report. A section that refuses prints "
        "the refusal under its own heading and the rest of the report still "
        "runs; the exit code becomes 3 so a script can tell.",
    )
    analyses.add_argument(
        "--scale", action="store_true",
        help=("is every number physically possible -- against the diffusion "
              "limit, the tightest measured Kd, one molecule per bacterium"),
    )
    analyses.add_argument(
        "--predictions", action="store_true",
        help=("is what the model PREDICTS physically possible -- a steady "
              "state or transient above the cell's total protein content, "
              "or below one molecule. Different from --scale, which checks "
              "the numbers going in: each can pass while the other fails"),
    )
    analyses.add_argument(
        "--robustness", nargs="?", type=int, const=SAMPLES_UNSTATED,
        default=None, metavar="N",
        help=("does the conclusion survive resampling the placeholders. N "
              "samples, each a full steady-state search, so lower it for a "
              "large model"),
    )
    analyses.add_argument(
        "--crnt", action="store_true",
        help=("deficiency theory: complexes, linkage classes, deficiency and "
              "what the theorems do and do not say. Structural -- it reads "
              "no parameter value at all"),
    )
    analyses.add_argument(
        "--reduction", action="store_true",
        help=("is a quasi-steady-state approximation licensed by a gap in "
              "the timescales, and what it would cost"),
    )
    analyses.add_argument(
        "--identifiability", action="store_true",
        help=("which constants a fit could actually recover, as distinct "
              "from which ones move the answer"),
    )
    analyses.add_argument(
        "--design", action="store_true",
        help="which measurement to make next, and what it would newly pin",
    )
    analyses.add_argument(
        "--validate", action="store_true",
        help=("cross-check Terrium against Terrium: steady state against "
              "trajectory, sensitivity against a finite difference"),
    )
    analyses.add_argument(
        "--knockout", action="append", default=[], metavar="SPECIES",
        help="remove this species and report the fold change; repeatable",
    )
    analyses.add_argument(
        "--overexpress", action="append", default=[], metavar="SPECIES",
        help="raise this species and report the fold change; repeatable",
    )
    analyses.add_argument(
        "--screen", action="store_true",
        help="knock out every species in turn and rank the effects",
    )
    analyses.add_argument(
        "--stochastic", type=float, default=None, metavar="LITRES",
        help=("exact Gillespie SSA in a compartment of this volume, in "
              "LITRES (an E. coli cell is about 1e-15). Refuses a rate law "
              "that is not mass action, because it has no propensity"),
    )
    analyses.add_argument(
        "--stochastic-end", type=float, default=None, metavar="SECONDS",
        help=("SSA horizon. Default: the same window the deterministic time "
              "course uses, derived from the settling time"),
    )
    analyses.add_argument(
        "--stochastic-seed", type=int, default=None, metavar="SEED",
        help=(f"RNG seed for the SSA (ADR 0005); default {DEFAULT_SEED}. "
              f"Reported in the output, because a trajectory whose seed is "
              f"not stated cannot be reproduced"),
    )

    exports = parser.add_argument_group(
        "export",
        "Writes one artefact to stdout and nothing else, so the output can "
        "be redirected straight into a file.",
    )
    exports.add_argument(
        "--export", choices=EXPORT_FORMATS, default=None, metavar="FORMAT",
        help=("one of: " + " | ".join(EXPORT_FORMATS) + ". Every number "
              "carries its origin -- measured, placeholder or chosen"),
    )
    return parser


# ---------------------------------------------------------------------------
# Sections
# ---------------------------------------------------------------------------


class Sections:
    """The analysis sections, printed as they are produced.

    PRINTED AS THEY GO rather than assembled and printed at the end. A
    module that crashes -- as distinct from refusing -- takes the process
    with it, and a reader who has already paid for four steady-state
    searches should keep those four.

    Refusals are counted rather than collected into a summary block. The
    reason belongs beside the heading it qualifies, which is the rule the
    dossier already follows for its own caveats; a list of refusals at the
    bottom would separate each one from the thing it is about.
    """

    def __init__(self, stream: Any = None) -> None:
        self.stream = sys.stdout if stream is None else stream
        self.refused: List[str] = []

    def write(self, title: str, body: str) -> None:
        print(f"\n## {title}\n", file=self.stream)
        print(body, file=self.stream)

    def refusal(self, title: str, reason: str) -> str:
        """Record a refusal and return the paragraph that reports it.

        Returns the text rather than printing it so a section with several
        parts -- `--crnt` asks three questions -- can splice one declined
        part into a body whose other parts answered.
        """
        self.refused.append(title)
        return f"**Refused.** {reason}"

    def attempt(
        self,
        title: str,
        refusals: Tuple[type, ...],
        produce: Callable[[], str],
    ) -> None:
        """Print `produce()` under `title`, or the refusal it raised.

        `refusals` is the tuple of exception types that module DECLARES as
        refusals. Anything else propagates, because a module raising
        something it does not declare is a bug, and catching it here would
        report the bug as a considered decline.

        Returns nothing. An earlier version returned whether it answered and
        no caller read it: the section is already in the report either way,
        and `self.refused` is what decides the exit code.
        """
        try:
            body = produce()
        except refusals as exc:  # noqa: B902 - the module's own refusal types
            self.write(title, self.refusal(title, str(exc)))
            return
        self.write(title, body)


def _answer_species(model: Any, named: Optional[str]) -> Optional[str]:
    """The species the perturbation sections use as a readout.

    The SAME rule the influence ranking uses, deliberately. A document whose
    ranking is about `tier3_Xp` and whose knockout screen is about
    `tier1_X` is a document about two different questions wearing one
    heading, and a reader has no way to notice.

    `None` when no motif declares a product or a complex -- see
    `report._default_target`, which argues at length for refusing there
    rather than falling back to an arbitrary species. The caller turns that
    into a refusal naming `--rank-against`.
    """
    if named:
        return named
    from Terium.compose.report import _default_target

    return _default_target(model)


def _concentration_unit(model: Any) -> str:
    """The unit the model's own composition writes its amounts in.

    Read off the composition rather than assumed, for the reason
    `scale.units_from_model` documents: `core.network.Parameter` has an id
    and a value and NO unit, so the network alone cannot say whether a 1.0
    is a millimolar or a molar -- and the conversion to molecule counts is
    wrong by a thousand if that is guessed.
    """
    from Terium.compose.scale import LIBRARY_CONCENTRATION_UNIT

    composition = getattr(getattr(model, "recognition", None), "composition", None)
    return str(
        getattr(composition, "concentration_unit", None)
        or LIBRARY_CONCENTRATION_UNIT
    )


def _scale_section(sections: Sections, model: Any) -> None:
    from Terium.compose.scale import ScaleError, check_model

    def produce() -> str:
        report = check_model(model)
        return (
            report.summary()
            + "\n\nThe units came from the motifs that declared them. "
            "`core.network.Parameter` carries the unit through, so a "
            "COMPOSED network describes itself; a network built outside "
            "the composer carries none, and every parameter in it is "
            "reported unchecked rather than assumed to be a "
            "concentration. See `scale.units_from_model`."
        )

    sections.attempt("Physical scale", (ScaleError,), produce)


def _predictions_section(sections: Sections, model: Any) -> None:
    """What the model produces, against what a cell can hold.

    A SEPARATE SECTION FROM "Physical scale", NOT AN EXTENSION OF IT. That
    one reads the numbers the model was given; this reads the numbers it
    produces. A model passes one and fails the other routinely -- every
    parameter inside its measured range, their ratio predicting more of one
    species than the cell contains of all protein together -- and folding
    them together would let a reader think one clean section covered both.
    """
    from Terium.compose.analysis import analyse
    from Terium.compose.predictions import (
        PredictionRefused, check_steady_states, check_trajectory,
    )

    def produce() -> str:
        parts: list[str] = []
        composition = model.recognition.composition
        proteins = tuple(sorted(composition.protein_species()))

        stability = analyse(model.network)
        for report in check_steady_states(stability, proteins=proteins):
            parts.append(report.summary())

        # The transient is the reading that earns this section: a run can
        # pass through an impossible state and settle somewhere fine, and
        # the steady-state check above sees nothing.
        try:
            from Terium.compose.simulate import run

            parts.append("")
            parts.append(check_trajectory(
                run(model), subject="the simulated run", proteins=proteins,
            ).summary())
        except Exception as exc:  # noqa: BLE001
            parts.append("")
            parts.append(
                f"The transient was NOT checked: {type(exc).__name__}: {exc}. "
                f"The steady states above still stand; a run that never "
                f"happened has not been found possible."
            )

        parts.append("")
        parts.append(
            "These are bounds on what a cell can hold, not on whether the "
            "model is right. A prediction inside them has not been shown "
            "correct; it has not been ruled out on grounds of capacity."
        )
        return "\n".join(parts)

    sections.attempt("Predicted amounts", (PredictionRefused,), produce)


def _crnt_section(sections: Sections, model: Any) -> None:
    """Deficiency theory, in the order the facts build on each other.

    Three questions, refused independently. The counts are checkable by
    hand from the reaction table above; the two theorems are not, and a
    reader who disagrees with a verdict should be able to find out where
    the disagreement starts. That is `crnt.describe`'s own argument and
    this section keeps its order.
    """
    from Terium.compose.crnt import (
        StructuralRefusal, deficiency_one_verdict, deficiency_zero_verdict,
        describe,
    )

    title = "Reaction network structure"
    network = model.network

    def produce() -> str:
        parts = [
            describe(network),
            "",
            "Nothing above reads a parameter value. Deficiency is a "
            "property of the wiring, so it holds for EVERY choice of "
            "positive rate constants -- including the placeholders this "
            "model is carrying.",
        ]
        for name, verdict in (
            ("Deficiency Zero Theorem", deficiency_zero_verdict),
            ("Deficiency One Theorem", deficiency_one_verdict),
        ):
            parts.append("")
            try:
                parts.append(verdict(network).summary())
            except StructuralRefusal as exc:
                parts.append(f"{name}: " + sections.refusal(title, str(exc)))
        return "\n".join(parts)

    sections.attempt(title, (StructuralRefusal,), produce)


def _reduction_section(sections: Sections, model: Any) -> None:
    from Terium.compose.reduction import (
        ReductionRefused, candidates_for_elimination, timescale_separation,
        validity_report,
    )
    from Terium.compose.sensitivity import SensitivityUnavailable

    def produce() -> str:
        separation = timescale_separation(model.network)
        candidates = candidates_for_elimination(
            model.network, separation=separation
        )
        parts = [separation.summary(), ""]
        for candidate in candidates:
            parts.append(f"- {candidate.describe()}")
        parts.append("")
        parts.append(validity_report(separation, candidates).summary())
        return "\n".join(parts)

    sections.attempt(
        "Timescale separation",
        (ReductionRefused, SensitivityUnavailable),
        produce,
    )


def _identifiability_section(sections: Sections, model: Any) -> None:
    """Which constants a fit could recover, not which ones matter.

    The observations offered are every species' steady state plus the
    settling time -- the same menu `design.candidate_observations` builds,
    minus the oscillation period, which exists only for a model that rings
    and is this module's business only through that menu.

    The PARAMETERS asked about are the model's `resolvable` set and not
    every parameter in the network. A concentration is a choice, not a
    measurement (rule 2 of this package): including one would invent a
    degeneracy between a rate constant and a starting amount that no
    experiment is trying to break.
    """
    from Terium.compose.identifiability import IdentifiabilityUnavailable, analyse
    from Terium.compose.sensitivity import (
        SensitivityUnavailable, settling_time, steady_state_of,
    )

    title = "Identifiability"

    def produce() -> str:
        targets = [q.parameter_id for q in model.resolvable]
        if not targets:
            raise IdentifiabilityUnavailable(
                "this model has no constant the literature could supply, so "
                "there is nothing for a measurement to identify. Every "
                "number in it is a starting amount or a cooperativity, and "
                "both are yours to choose rather than things an experiment "
                "recovers."
            )
        quantities = [steady_state_of(s.id) for s in model.network.species]
        names = [f"steady state of {s.id}" for s in model.network.species]
        quantities.append(settling_time())
        names.append("settling time")
        report = analyse(
            model.network, quantities,
            parameters=targets, quantity_names=names,
        )
        return (
            report.summary()
            + "\n\nAsked about the "
            + f"{len(targets)} constant(s) the literature could supply, not "
            "about the starting amounts. A concentration is a choice rather "
            "than something a measurement recovers, and including one would "
            "invent a degeneracy nobody is trying to break."
        )

    sections.attempt(
        title, (IdentifiabilityUnavailable, SensitivityUnavailable), produce
    )


def _design_section(sections: Sections, model: Any) -> None:
    from Terium.compose.design import (
        DesignError, NoInformativeMeasurement, rank_observations,
    )
    from Terium.compose.sensitivity import SensitivityUnavailable

    def produce() -> str:
        targets = [q.parameter_id for q in model.resolvable]
        if not targets:
            raise DesignError(
                "this model has no constant the literature could supply, so "
                "no measurement has anything to identify. Ranking "
                "measurements against the starting amounts would rank them "
                "against numbers you already know, because you chose them."
            )
        return rank_observations(model.network, targets).summary()

    sections.attempt(
        "What to measure next",
        (DesignError, NoInformativeMeasurement, SensitivityUnavailable),
        produce,
    )


def _robustness_assessment(model: Any, samples: int) -> Tuple[Any, str]:
    """(the RobustnessReport, the conclusion's name), or a refusal.

    THE COMPUTATION, SEPARATED FROM THE PRINTING, so it can run BEFORE the
    dossier and be handed to the verdict page. The dossier used to print a
    verdict saying "robustness: not run" and then this section ran
    underneath it -- one report whose headline contradicted its body. Now
    `main` computes this first, the verdict reads it, and the section
    prints the same object rather than computing a second time.

    WHICH CONCLUSION IS NOT CHOSEN BY THIS FILE. It is read off the
    steady-state analysis: a model the search found two stable states in
    is asked whether it stays bistable, and one it found exactly one in is
    asked whether it stays monostable. Picking a fixed conclusion would
    report a monostable model as 0% robust, which is a true number
    answering a question nobody asked.

    THE CONCLUSION AND ITS RESAMPLING USE ONE SEARCH DEPTH. They did not:
    this chose from `analyse`'s default and `robustness` judged every draw
    at a deeper one, so the printed percentage was partly a measure of two
    searches disagreeing and the conclusion could be FALSE at the centre
    of the box being sampled. One depth, by reference, everywhere.
    """
    from Terium.compose.analysis import analyse
    from Terium.compose.robustness import (
        DEFAULT_SAMPLES, RobustnessError, assess_model, default_search_depth,
        is_bistable, is_monostable, oscillates,
    )

    depth = default_search_depth()
    report = analyse(model.network, starts_per_species=depth)
    stable = report.stable_points
    if len(stable) > 1:
        conclusion, name = (
            is_bistable(starts_per_species=depth),
            "at least two stable states",
        )
    elif len(stable) == 1:
        conclusion, name = (
            is_monostable(starts_per_species=depth),
            "exactly one stable state",
        )
    elif report.any_oscillatory:
        conclusion, name = (
            oscillates(starts_per_species=depth), "sustained oscillation",
        )
    elif getattr(report, "on_a_continuum", False):
        # A line of equilibria is a real finding and there IS a conclusion
        # to resample: "the system has no isolated attractor". But that
        # conclusion is structural -- it follows from the substrate being
        # consumed and nothing replenishing it -- and resampling rate
        # constants cannot move it. The honest answer is to say what the
        # finding is and why a fraction would be 100% by construction,
        # rather than print the 100%.
        points = len(getattr(report, "continuum_points", ()))
        raise RobustnessError(
            f"the steady-state search found a LINE of equilibria "
            f"({points} points on it) and no isolated attractor. That "
            f"is a structural property -- the substrate is consumed and "
            f"nothing replenishes it, so once the rates reach zero every "
            f"split of the products is an equilibrium -- and resampling "
            f"rate constants cannot change it. A robustness fraction "
            f"here would be 100% by construction and would say nothing. "
            f"Ask for a time course from your actual starting amounts "
            f"instead; where on the line the system stops is the "
            f"question this model actually poses."
        )
    else:
        raise RobustnessError(
            f"the steady-state search found no stable state and no "
            f"unstable spiral from {report.starts_tried} starting "
            f"points, so there is no conclusion to resample. "
            f"Robustness is a question about a finding, and this model "
            f"has not produced one to ask about."
        )
    count = DEFAULT_SAMPLES if samples == SAMPLES_UNSTATED else samples
    assessment = assess_model(
        model, conclusion, conclusion_name=name, samples=count,
        starts_per_species=depth,
    )
    return assessment, name


def _robustness_section(
    sections: Sections, model: Any, samples: int,
    precomputed: Optional[Tuple[Any, str]] = None,
) -> None:
    """Does the conclusion survive resampling the placeholders.

    Prints `precomputed` when `main` already ran the assessment for the
    verdict page; computes it only when called without one.
    """
    from Terium.compose.analysis import AnalysisError
    from Terium.compose.robustness import RobustnessError

    title = "Robustness to the placeholders"

    def produce() -> str:
        assessment, name = (
            precomputed if precomputed is not None
            else _robustness_assessment(model, samples)
        )
        return (
            assessment.summary()
            + f"\n\nThe conclusion resampled -- '{name}' -- is the one this "
            "model's own steady-state search produced, not a fixed question "
            "asked of every model. Asking a monostable model whether it "
            "stays bistable returns a true 0% about something nobody "
            "claimed."
        )

    sections.attempt(title, (RobustnessError, AnalysisError), produce)


def _perturbation_section(
    sections: Sections,
    model: Any,
    knockouts: Sequence[str],
    overexpressions: Sequence[str],
    screen: bool,
    readout: Optional[str],
) -> None:
    from Terium.compose.perturbation import (
        PerturbationRefused, compare, knockout, overexpress, single_knockouts,
    )

    title = "Perturbations"

    def produce() -> str:
        if readout is None:
            raise PerturbationRefused(
                "no readout. A fold change is a fold change IN something, "
                "and no motif in this model declares a product or a complex "
                "for this to default to. Name the species with "
                "--rank-against SPECIES."
            )
        parts: List[str] = []
        applied = (
            [knockout(model.network, name) for name in knockouts]
            + [overexpress(model.network, name) for name in overexpressions]
        )
        if applied:
            parts.append(compare(model.network, applied, readout).summary())
        if screen:
            if applied:
                parts.append("")
            parts.append(single_knockouts(model.network, readout).summary())
        parts.append("")
        parts.append(
            f"Every fold change above is in **{readout}**, at the "
            "placeholder values this model is carrying. A knockout removes "
            "the protein; a catalytically dead mutant leaves it in place "
            "still sequestering its substrate, and the two give different "
            "answers -- see `perturbation.catalytically_dead`."
        )
        return "\n".join(parts)

    sections.attempt(title, (PerturbationRefused,), produce)


def _stochastic_section(
    sections: Sections,
    model: Any,
    volume: float,
    end: Optional[float],
    seed: int,
) -> None:
    """The diagnosis and then the treatment, in that order.

    `discreteness_matters` runs first and does NOT require mass action,
    which is the point: the most useful thing it can tell the reader about
    a Michaelis-Menten model is that the enzyme is present at four copies,
    at which point the quasi-steady-state assumption behind that rate law
    has already failed. The SSA then refuses the same model for the same
    underlying reason, and the refusal reads as a conclusion rather than as
    a missing feature because the diagnosis came first.
    """
    from Terium.compose.simulate import choose_window
    from Terium.compose.stochastic import (
        StochasticRefusal, discreteness_matters, simulate_ssa, to_propensities,
    )

    title = "Stochastic simulation"
    unit = _concentration_unit(model)

    def diagnosis() -> str:
        return discreteness_matters(
            model.network, volume=volume, concentration_unit=unit
        ).summary()

    def trajectory() -> str:
        window, basis = choose_window(model.network, end)
        system = to_propensities(
            model.network, volume=volume, concentration_unit=unit
        )
        run = simulate_ssa(system, end=window, seed=seed)
        return (
            f"Horizon {window:g} s -- {basis}.\n\n"
            + run.summary()
            + f"\n\nCounts were taken from concentrations in {unit} at "
            f"{volume:g} L. Both were stated rather than assumed: the "
            "network IR records neither, and each changes every count "
            "here by whatever factor the guess was wrong by."
        )

    parts: List[str] = []
    for produce in (diagnosis, trajectory):
        try:
            parts.append(produce())
        except StochasticRefusal as exc:
            parts.append(sections.refusal(title, str(exc)))
        parts.append("")
    sections.write(title, "\n".join(parts).rstrip())


def _validate_section(
    sections: Sections, model: Any, species: Optional[str],
    precomputed: Any = None,
) -> None:
    """Cross-module consistency, with the quantity named by the caller.

    `species` is passed through rather than defaulted. `validate.validate`
    argues for this itself: choosing a species chooses which of the model's
    conclusions gets cross-checked, and a reader given no way to see that
    choice cannot discount it. With none named the sensitivity check
    reports itself unchecked and says so, which is the honest outcome and
    not a gap in this file.
    """
    from Terium.compose.validate import ValidationError, validate

    def produce() -> str:
        report = (
            precomputed if precomputed is not None
            else validate(model, species=species)
        )
        tail = (
            ""
            if species
            else (
                "\n\nNo species was named, so the sensitivity cross-check "
                "did not run. Pass --rank-against SPECIES to choose the "
                "quantity it differentiates -- choosing one here would pick "
                "which of this model's conclusions gets checked without "
                "saying which."
            )
        )
        return report.summary() + tail

    sections.attempt("Cross-checks", (ValidationError,), produce)


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


def _search_the_literature(
    model: Any, args: Any,
) -> Tuple[Any, Optional[str], bool]:
    """Resolve this model's constants from the literature.

    Returns `(model, note, refused)`. `refused` is True when the search
    could not be RUN -- an ambiguous enzyme name, a missing substrate, no
    literature layer, a crash -- and False when it ran, whatever it found.

    THE DISTINCTION THE EXIT CODE NEEDS
    -----------------------------------
    This CLI's contract, stated in its own `--help`, is "0 produced
    everything asked for, 3 something refused and said why (the report is
    still printed)". Passing `--subject "lactate dehydrogenase"` asks for a
    search; the resolver refuses because that name is six enzymes; and the
    report said so in prose while exiting 0. A script could not tell, which
    is the whole reason the three-state convention exists here.

    A search that RAN and found nothing is not a refusal. It produced its
    answer, and the answer is that the database has no value -- which the
    provenance table now states per constant, in the resolver's words.

    Returns the model with whatever the search returned substituted in, and
    a note for the report when something could not be done. EVERY failure
    here is a note rather than an exception: a literature search that could
    not run must not cost the reader the structure, the invariants, the
    dimensions and the behaviour, all of which are true regardless (ADR
    0178). What it must never do is leave the reader unable to tell that no
    search happened, which is why every branch returns a sentence.

    A NAME IS NOT AN ENZYME. `--subject "lactate dehydrogenase"` is six EC
    numbers; the resolver refuses and names all six rather than picking,
    because a wrong EC number is a citation for the wrong protein rather
    than merely a wrong value.
    """
    from Terium.checkout import LiteratureLayerUnavailable, literature_module

    subject = args.subject
    ec = model.ec_number
    if ec is None:
        try:
            lookup = literature_module("enzyme_lookup")
        except LiteratureLayerUnavailable as exc:
            return model, str(exc), True
        try:
            ec = lookup.ec_number_for_name(subject)
        except Exception as exc:  # noqa: BLE001 - the refusal names the candidates
            return model, f"No search was run: {exc}", True
        model = replace(model, subject=ec)

    needs_substrate = sorted(
        q.table for q in model.resolvable
        if q.table in ("km", "ki") and q.table is not None
    )
    if needs_substrate and not args.substrate:
        return model, (
            f"No search was run: this model needs {', '.join(sorted(set(needs_substrate)))} "
            f"from BRENDA, and those tables are per-substrate. A motif knows "
            f"it needs a Km; it cannot know what the Km is FOR. Re-run with "
            f"--substrate NAME."
        ), True

    try:
        from Terium.compose.export import (
            measured_from_search, unresolved_from_search,
        )
        from Terium.compose.pipeline import compose_and_parameterise
        _, search = compose_and_parameterise(
            model.query, subject=ec, organism=args.organism,
            substrate=args.substrate,
        )
    except LiteratureLayerUnavailable as exc:
        return model, str(exc), True
    except Exception as exc:  # noqa: BLE001 - a failed search is a note, not a crash
        return model, f"The literature search failed: {type(exc).__name__}: {exc}", True

    if search is None:
        return model, "No search was run: this model has nothing a database could supply.", False

    measured = measured_from_search(search)
    not_found = unresolved_from_search(search)
    failures = [
        run for branch in getattr(search, "branches", ())
        for record in getattr(branch.build.run, "rounds", ())
        for run in getattr(record, "ran", ())
        if getattr(run, "failed", False)
    ]
    sourced = model.with_measured(measured, not_found=not_found)
    if not measured:
        why = "; ".join(sorted({r.failure for r in failures})) if failures else (
            "every table was searched and none held a value for this "
            "enzyme, organism and substrate"
        )
        return sourced, f"The search returned no measured value: {why}", False

    note = (
        f"{len(measured)} constant(s) resolved from the literature: "
        + ", ".join(sorted(measured))
    )
    still = sourced.unmeasured
    if still:
        note += (
            f". {len(still)} still the motif library's placeholder "
            f"({', '.join(still)}): the search ran and returned nothing for "
            f"them, which is different from their not having been looked for"
        )
    return sourced, note, False


def _export(description: str, subject: Optional[str], fmt: str,
            args: Any = None) -> int:
    """Write one artefact to stdout, or a refusal to stderr.

    NOTHING ELSE GOES TO STDOUT. A CSV with a markdown report in front of it
    is a CSV no parser reads, and an SBML file with one is not XML. That is
    why `--export` refuses to run alongside the analysis flags rather than
    printing both -- see `_check_combination`.
    """
    from Terium.compose.export import (
        ExportRefused, provenance_of, to_antimony, to_methods_paragraph,
        to_parameter_csv, to_sbml,
    )
    from Terium.compose.pipeline import compose

    writers = {
        "sbml": to_sbml,
        "antimony": to_antimony,
        "csv": to_parameter_csv,
        "methods": to_methods_paragraph,
    }
    try:
        model = compose(description, subject=subject,
                        organism=getattr(args, "organism", None),
                        substrate=getattr(args, "substrate", None))
        if subject and args is not None:
            # An export that quietly carried placeholders while the report
            # beside it carried measurements would be the disagreement the
            # provenance machinery exists to prevent.
            model, _, _ = _search_the_literature(model, args)
        provenanced = provenance_of(model, measured=dict(model.measured) or None)
        print(writers[fmt](provenanced))
    except ExportRefused as exc:
        print(f"Not exported.\n\n{exc}", file=sys.stderr)
        return 3
    return 0


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def _check_combination(parser: argparse.ArgumentParser, args: Any) -> None:
    """Reject combinations that would have to ignore one of the flags given.

    A flag accepted and then not honoured is the worse defect: the user
    typed it, the run reported success, and nothing said the request was
    dropped. So these are argparse errors -- exit 2, the question was not
    well formed -- rather than a silent precedence rule.
    """
    if args.stochastic is None and (
        args.stochastic_end is not None or args.stochastic_seed is not None
    ):
        parser.error(
            "--stochastic-end and --stochastic-seed set the horizon and the "
            "RNG seed of a stochastic run, and no stochastic run was asked "
            "for. Add --stochastic LITRES, or drop them -- a flag accepted "
            "and then not honoured is worse than one rejected."
        )

    if args.export is None:
        return
    # Tested one at a time rather than with `value not in (None, False, ...)`,
    # because `0 == False` in Python and a sample count of zero would slip
    # through a membership test as though the flag had not been given.
    asked: List[str] = []
    for name in ANALYSIS_FLAGS:
        value = getattr(args, name)
        if value is None or value is False:
            continue
        if isinstance(value, list) and not value:
            continue
        asked.append(name)
    if asked:
        parser.error(
            "--export writes one artefact to stdout and nothing else, so "
            "--" + ", --".join(asked) + " could not be honoured in the same "
            "run. Run the export and the report as two commands."
        )
    if args.antimony:
        parser.error(
            "--antimony and --export both take over stdout. --antimony emits "
            "the compiled source; --export antimony emits the same model with "
            "every value's origin annotated beside it. Pick one."
        )


def main(argv: Optional[Sequence[str]] = None, prog: Optional[str] = None) -> int:
    parser = build_parser(prog) if prog else build_parser()
    args = parser.parse_args(argv)

    from Terium.compose.grammar import UnrecognisedShape, shapes

    if args.shapes:
        print("Shapes this builds:\n")
        for shape in shapes():
            print(f"  {shape}")
        print(
            "\nIt recognises a SHAPE, never a SUBJECT. 'three step "
            "phosphorylation cascade' builds; 'glycolysis' does not, and "
            "says why."
        )
        return 0

    if not args.description:
        parser.print_help()
        return 2

    if (
        args.robustness is not None
        and args.robustness != SAMPLES_UNSTATED
        and args.robustness < 1
    ):
        parser.error(
            f"--robustness needs at least one sample; got "
            f"{args.robustness}. A fraction over zero draws is not a small "
            f"number, it is no number."
        )

    _check_combination(parser, args)

    try:
        if args.export is not None:
            return _export(args.description, args.subject, args.export, args)

        if args.antimony:
            from Terium.compose.pipeline import compose
            from Terium.core.network import compile_to_antimony

            model = compose(args.description, subject=args.subject)
            print(compile_to_antimony(model.network))
            return 0

        from Terium.compose.pipeline import compose
        from Terium.compose.report import dossier

        # COMPOSE ONCE, AND RUN THE VERDICT'S INPUTS BEFORE THE VERDICT.
        #
        # The dossier's verdict page reports whether `validate` and
        # `robustness` ran. It used to be formed before either had, so a
        # run with `--validate --robustness` printed "validate: not run,
        # robustness: not run" at the top and then ran both underneath --
        # one report whose headline contradicted its own body. Both are
        # computed here when asked for, handed to the dossier so the
        # verdict can read them, and printed by their sections afterwards
        # without being computed a second time.
        model = compose(args.description, subject=args.subject,
                        organism=args.organism, substrate=args.substrate)
        search_note = None
        search_refused = False
        if args.subject:
            # The search runs BEFORE the analyses, so every section below --
            # stability, sensitivity, the time course, the verdict -- reads
            # the literature's numbers rather than the library's (ADR 0178).
            model, search_note, search_refused = _search_the_literature(model, args)
        precomputed = _precompute_for_verdict(args, model)

        report = dossier(
            args.description,
            subject=args.subject,
            analyse_stability=not args.no_analysis,
            simulate=not args.no_simulate,
            sweep_parameters=args.sweep,
            sweep_range=(args.sweep_from, args.sweep_to),
            sweep_steps=args.sweep_steps,
            rank_unmeasured=not args.no_ranking,
            rank_against=args.rank_against,
            model=model,
            validation=precomputed.validation,
            robustness=precomputed.robustness,
            conclusion_name=precomputed.conclusion_name,
        )
        # Footer withheld until the analysis sections have run: a document
        # that says "Built by Terrium..." and then carries on for three more
        # pages has put its last word in the middle.
        if search_note:
            model.recognition.composition.note(search_note)
        print(report.markdown(footer=False))

        code = _analyses(args, report.model, precomputed)
        if search_refused and code == 0:
            # The reason is already in the report, beside what it is about.
            # This says only that a script should look (the same shape the
            # analysis refusals use).
            print(
                "1 refusal(s) in 1 section(s), each explained where it "
                "belongs in the report: the literature search.",
                file=sys.stderr,
            )
            code = 3
        print("\n".join(report.footer_section()))
        return code

    except UnrecognisedShape as exc:
        # Exit 3, not 1: this is a REFUSAL with information in it, not a
        # crash, and a script should be able to tell the two apart.
        print(f"Not built.\n\n{exc}", file=sys.stderr)
        return 3


class _Precomputed:
    """What `main` ran ahead of the dossier so the verdict could read it.

    Each is None when its flag was absent OR when it refused; the section
    that prints it re-raises the refusal in the latter case, so the reason
    lands under the right heading rather than being swallowed here.
    """

    def __init__(self) -> None:
        self.validation: Any = None
        self.robustness: Any = None
        self.conclusion_name: Optional[str] = None
        self.robustness_pair: Optional[Tuple[Any, str]] = None


def _precompute_for_verdict(args: Any, model: Any) -> _Precomputed:
    out = _Precomputed()
    if args.validate:
        try:
            from Terium.compose.validate import validate

            out.validation = validate(model, species=args.rank_against)
        except Exception:  # noqa: BLE001 - the section will re-raise and print it
            out.validation = None
    if args.robustness is not None:
        try:
            assessment, name = _robustness_assessment(model, args.robustness)
            out.robustness = assessment
            out.conclusion_name = name
            out.robustness_pair = (assessment, name)
        except Exception:  # noqa: BLE001 - the section will re-raise and print it
            out.robustness = None
    return out


def _analyses(
    args: Any, model: Any, precomputed: Optional[_Precomputed] = None,
) -> int:
    """Run every analysis asked for, and return the exit code.

    Order is structure first, then the numbers, then the cross-checks --
    the same order the dossier itself uses, and the order in which a reader
    can discount what comes later. `--crnt` needs no parameter value at all,
    so a reader who distrusts the placeholders can stop after it and still
    have something true.
    """
    sections = Sections()

    if args.crnt:
        _crnt_section(sections, model)
    if args.scale:
        _scale_section(sections, model)
    if args.predictions:
        _predictions_section(sections, model)
    if args.reduction:
        _reduction_section(sections, model)
    if args.identifiability:
        _identifiability_section(sections, model)
    if args.design:
        _design_section(sections, model)
    if args.robustness is not None:
        _robustness_section(
            sections, model, args.robustness,
            precomputed=precomputed.robustness_pair if precomputed else None,
        )
    if args.knockout or args.overexpress or args.screen:
        _perturbation_section(
            sections, model, args.knockout, args.overexpress, args.screen,
            _answer_species(model, args.rank_against),
        )
    if args.stochastic is not None:
        _stochastic_section(
            sections, model, args.stochastic, args.stochastic_end,
            DEFAULT_SEED if args.stochastic_seed is None
            else args.stochastic_seed,
        )
    if args.validate:
        _validate_section(
            sections, model, args.rank_against,
            precomputed=precomputed.validation if precomputed else None,
        )

    if not sections.refused:
        return 0
    # On stderr, so it survives `| less` and does not land in a redirected
    # report. The reasons are already in the report, next to what they are
    # about; this line says only that a script should look.
    #
    # Refusals and sections are counted separately because they differ:
    # `--crnt` asks three questions under one heading and two of them can
    # decline while the third answers. Collapsing that to "1 section
    # refused" would understate it and "3 sections refused" would name a
    # heading twice.
    where: List[str] = []
    for title in sections.refused:
        if title not in where:
            where.append(title)
    print(
        f"{len(sections.refused)} refusal(s) in {len(where)} section(s), "
        f"each explained where it belongs in the report: "
        + ", ".join(where) + ".",
        file=sys.stderr,
    )
    return 3


__all__ = ["Sections", "build_parser", "main"]



def console_main() -> int:
    """Entry point of the `terium-compose` console script."""
    return main(prog="terium-compose")


if __name__ == "__main__":
    raise SystemExit(main())
