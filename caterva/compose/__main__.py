"""`python -m caterva.compose "three step phosphorylation cascade"`.

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
from the same sentence either way. `caterva crnt --model ...` would require a
model file to exist first; `python -m caterva.compose "..." --crnt` asks the
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

ONE RUN, TWO READERS
--------------------
`compose_report` is the whole of a report run: compose, search, the
verdict's inputs, the dossier, the sections, the footer. `main` calls it
with the terminal's streams; Caterva Studio (caterva/studio/adapters/
compose.py) calls it with two string buffers and reads back the objects it
printed from. Each section keeps the report object its text was rendered
from (`SectionRecord.data`), so the studio serialises the same object the
terminal reader was shown and never computes a section a second time. The
exports go through `export_texts` for the same reason: `--export` and the
studio's four artefacts are one function over one ProvenancedModel.

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

from dataclasses import dataclass, field, replace
import re

import argparse
import contextlib
import sys
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

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


def build_parser(prog: str = "python -m caterva.compose") -> argparse.ArgumentParser:
    """`prog` is how the caller is invoked: the module form from a checkout,
    `caterva-compose` from the wheel's console script, `caterva compose` from
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
            f"  {prog} 'Michaelis Menten' --subject 2.7.1.1 --organism human --substrate glucose\n"
            f"  {prog} 'three step phosphorylation cascade'\n"
            f"  {prog} 'a toggle switch between two repressors' --sweep geneA_n\n"
            f"  {prog} 'three step phosphorylation cascade' --rank-against tier2_Xp\n"
            f"  {prog} 'reversible binding of a ligand to a receptor' --crnt --scale\n"
            f"  {prog} 'two enzymes competing for the same substrate' --screen\n"
            f"  {prog} 'reversible binding of a ligand to a receptor' --export sbml > model.xml\n"
            f"  {prog} 'Michaelis Menten' --subject 2.7.1.1 --organism human --substrate glucose --claims ./claims\n"
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
                        help="the organism the constants should belong to: "
                             "'Homo sapiens', or a common name such as human, "
                             "mouse, yeast or 'E. coli'. Only used when "
                             "--subject names one")
    parser.add_argument("--substrate",
                        help="the substrate a Km or Ki belongs to. A motif knows "
                             "it needs a Km; it cannot know what the Km is FOR, "
                             "and BRENDA's km and ki tables cannot be read "
                             "without it")
    parser.add_argument("--inhibitor",
                        help="the inhibitor an inhibition constant belongs to. BRENDA files "
                             "a Ki under the inhibitor, so without this an inhibition "
                             "model's Ki is left a labelled placeholder rather than looked "
                             "up under the substrate's name")
    parser.add_argument("--isoform",
                        help="the isoform the model is about, e.g. LDH-A. Each constant is taken "
                             "from a row that measured it; where none did, a row naming no "
                             "isoform is used and the report says so, and a constant only "
                             "measured on other isoforms is refused")
    parser.add_argument("--any-mode", action="store_true",
                        help="take an inhibition constant from the row the resolver returns when "
                             "asked for no inhibition mode, as the TypeScript CLI does without "
                             "--mode, whatever mode it states. By default a Ki comes from a row "
                             "stating this model's mode (mixed counts for noncompetitive), else from "
                             "one stating none, and a Ki only measured for another mode is refused. "
                             "The report flags a mismatch either way, and names the row the default "
                             "would carry when that row is another")
    parser.add_argument("--product",
                        help="the product, for constants measured on it: a reverse Km, a "
                             "product-inhibition Kp")
    parser.add_argument("--compound", action="append", default=[], metavar="PORT=NAME",
                        help="the compound on any other port of the mechanism, e.g. "
                             "--compound ATP=ATP or --compound B=NAD+; the report says which "
                             "port each unsearched constant needs")
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
        help=("cross-check Caterva against Caterva: steady state against "
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
    exports.add_argument(
        "--claims", default=None, metavar="DIR",
        help=("keep the evidence: every BRENDA page the search read, as the "
              "bytes it read, the rows taken from them, and one claim per "
              "number naming its derivation, written to DIR as a bundle that "
              "`caterva verify DIR` re-checks offline. BRENDA's reference page "
              "for each cited row is fetched and pinned too. The report gains a "
              "`## Claims` section before its footer; with --export, the "
              "artefact carries each number's claim id. Without this flag "
              "nothing is written and nothing changes"),
    )
    return parser


# ---------------------------------------------------------------------------
# Sections
# ---------------------------------------------------------------------------


#: A section's status, as SectionRecord.status reports it.
ANSWERED, REFUSED, PARTLY_REFUSED = "answered", "refused", "partly_refused"


@dataclass
class SectionRecord:
    """One section as it was printed, and the objects it was printed from.

    `text` is the body exactly as it went to the stream under `## title`.
    `refusals` are the reasons, in the module's words, of every part that
    declined. `data` holds the module's own report objects (a ScaleReport,
    a RobustnessReport, ...) under the names the section gave them, so a
    reader who wants the numbers reads the object the text came from.
    """

    key: str
    title: str
    status: str
    text: str
    refusals: List[str] = field(default_factory=list)
    data: Dict[str, Any] = field(default_factory=dict)


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

    Every section written is also kept as a SectionRecord in `records`,
    with the report objects the section handed to `keep`. Printing is
    unchanged by it: the record is what was printed, not a second rendering.
    """

    def __init__(self, stream: Any = None) -> None:
        self.stream = sys.stdout if stream is None else stream
        self.refused: List[str] = []
        self.records: List[SectionRecord] = []
        self._key = ""
        self._data: Dict[str, Any] = {}
        self._reasons: List[str] = []

    def start(self, key: str) -> None:
        """Begin the section named by its flag (`crnt`, `scale`, ...)."""
        self._key = key
        self._data = {}
        self._reasons = []

    def keep(self, name: str, obj: Any) -> Any:
        """Keep a report object the current section is printed from."""
        self._data[name] = obj
        return obj

    def write(self, title: str, body: str, *, whole_refusal: bool = False) -> None:
        print(f"\n## {title}\n", file=self.stream)
        print(body, file=self.stream)
        status = (REFUSED if whole_refusal
                  else PARTLY_REFUSED if self._reasons else ANSWERED)
        self.records.append(SectionRecord(
            key=self._key, title=title, status=status, text=body,
            refusals=list(self._reasons), data=dict(self._data),
        ))
        self._data = {}
        self._reasons = []

    def refusal(self, title: str, reason: str) -> str:
        """Record a refusal and return the paragraph that reports it.

        Returns the text rather than printing it so a section with several
        parts -- `--crnt` asks three questions -- can splice one declined
        part into a body whose other parts answered.
        """
        self.refused.append(title)
        self._reasons.append(reason)
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
            self.write(title, self.refusal(title, str(exc)), whole_refusal=True)
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
    from caterva.compose.report import _default_target

    return _default_target(model)


def _concentration_unit(model: Any) -> str:
    """The unit the model's own composition writes its amounts in.

    Read off the composition rather than assumed, for the reason
    `scale.units_from_model` documents: `core.network.Parameter` has an id
    and a value and NO unit, so the network alone cannot say whether a 1.0
    is a millimolar or a molar -- and the conversion to molecule counts is
    wrong by a thousand if that is guessed.
    """
    from caterva.compose.scale import LIBRARY_CONCENTRATION_UNIT

    composition = getattr(getattr(model, "recognition", None), "composition", None)
    return str(
        getattr(composition, "concentration_unit", None)
        or LIBRARY_CONCENTRATION_UNIT
    )


def _scale_section(sections: Sections, model: Any) -> None:
    from caterva.compose.scale import ScaleError, check_model

    def produce() -> str:
        report = sections.keep("report", check_model(model))
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
    from caterva.compose.analysis import analyse
    from caterva.compose.predictions import (
        PredictionRefused, check_steady_states, check_trajectory,
    )

    def produce() -> str:
        parts: list[str] = []
        composition = model.recognition.composition
        proteins = tuple(sorted(composition.protein_species()))

        stability = sections.keep("stability", analyse(model.network))
        steady = sections.keep(
            "steady_states", check_steady_states(stability, proteins=proteins)
        )
        for report in steady:
            parts.append(report.summary())

        # The transient is the reading that earns this section: a run can
        # pass through an impossible state and settle somewhere fine, and
        # the steady-state check above sees nothing.
        try:
            from caterva.compose.simulate import run

            parts.append("")
            parts.append(sections.keep("trajectory", check_trajectory(
                run(model), subject="the simulated run", proteins=proteins,
            )).summary())
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
    from caterva.compose.crnt import (
        StructuralRefusal, deficiency_one_verdict, deficiency_zero_verdict,
        describe,
    )

    title = "Reaction network structure"
    network = model.network

    def produce() -> str:
        parts = [
            sections.keep("description", describe(network)),
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
                parts.append(sections.keep(name, verdict(network)).summary())
            except StructuralRefusal as exc:
                parts.append(f"{name}: " + sections.refusal(title, str(exc)))
        return "\n".join(parts)

    sections.attempt(title, (StructuralRefusal,), produce)


def _reduction_section(sections: Sections, model: Any) -> None:
    from caterva.compose.reduction import (
        ReductionRefused, candidates_for_elimination, timescale_separation,
        validity_report,
    )
    from caterva.compose.sensitivity import SensitivityUnavailable

    def produce() -> str:
        separation = sections.keep("separation", timescale_separation(model.network))
        candidates = sections.keep("candidates", candidates_for_elimination(
            model.network, separation=separation
        ))
        parts = [separation.summary(), ""]
        for candidate in candidates:
            parts.append(f"- {candidate.describe()}")
        parts.append("")
        parts.append(sections.keep(
            "validity", validity_report(separation, candidates)).summary())
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
    from caterva.compose.identifiability import IdentifiabilityUnavailable, analyse
    from caterva.compose.sensitivity import (
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
        report = sections.keep("report", analyse(
            model.network, quantities,
            parameters=targets, quantity_names=names,
        ))
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
    from caterva.compose.design import (
        DesignError, NoInformativeMeasurement, rank_observations,
    )
    from caterva.compose.sensitivity import SensitivityUnavailable

    def produce() -> str:
        targets = [q.parameter_id for q in model.resolvable]
        if not targets:
            raise DesignError(
                "this model has no constant the literature could supply, so "
                "no measurement has anything to identify. Ranking "
                "measurements against the starting amounts would rank them "
                "against numbers you already know, because you chose them."
            )
        return sections.keep(
            "report", rank_observations(model.network, targets)).summary()

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
    from caterva.compose.analysis import analyse
    from caterva.compose.robustness import (
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
    from caterva.compose.analysis import AnalysisError
    from caterva.compose.robustness import RobustnessError

    title = "Robustness to the placeholders"

    def produce() -> str:
        assessment, name = (
            precomputed if precomputed is not None
            else _robustness_assessment(model, samples)
        )
        sections.keep("report", assessment)
        sections.keep("conclusion", name)
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
    from caterva.compose.perturbation import (
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
        sections.keep("readout", readout)
        if applied:
            parts.append(sections.keep(
                "comparison", compare(model.network, applied, readout)).summary())
        if screen:
            if applied:
                parts.append("")
            parts.append(sections.keep(
                "screen", single_knockouts(model.network, readout)).summary())
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
    from caterva.compose.simulate import choose_window
    from caterva.compose.stochastic import (
        StochasticRefusal, discreteness_matters, simulate_ssa, to_propensities,
    )

    title = "Stochastic simulation"
    unit = _concentration_unit(model)

    def diagnosis() -> str:
        return sections.keep("diagnosis", discreteness_matters(
            model.network, volume=volume, concentration_unit=unit
        )).summary()

    def trajectory() -> str:
        window, basis = choose_window(model.network, end)
        sections.keep("window", window)
        sections.keep("window_basis", basis)
        system = to_propensities(
            model.network, volume=volume, concentration_unit=unit
        )
        run = sections.keep("run", simulate_ssa(system, end=window, seed=seed))
        return (
            f"Horizon {window:g} s -- {basis}.\n\n"
            + run.summary()
            + f"\n\nCounts were taken from concentrations in {unit} at "
            f"{volume:g} L. Both were stated rather than assumed: the "
            "network IR records neither, and each changes every count "
            "here by whatever factor the guess was wrong by."
        )

    parts: List[str] = []
    declined = 0
    sections.keep("volume_l", volume)
    sections.keep("seed", seed)
    sections.keep("concentration_unit", unit)
    for produce in (diagnosis, trajectory):
        try:
            parts.append(produce())
        except StochasticRefusal as exc:
            parts.append(sections.refusal(title, str(exc)))
            declined += 1
        parts.append("")
    sections.write(title, "\n".join(parts).rstrip(), whole_refusal=declined == 2)


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
    from caterva.compose.validate import ValidationError, validate

    def produce() -> str:
        report = sections.keep("report", (
            precomputed if precomputed is not None
            else validate(model, species=species)
        ))
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
# What the description itself names (ADR 0181)
# ---------------------------------------------------------------------------

#: The shapes a description's enzyme is applied to: ONE enzyme, whatever it
#: is inhibited by or however many substrates it takes. A cascade, a
#: competition, a pathway or a futile cycle has an enzyme per step, and one
#: named enzyme's constants on every step is ADR 0076's adjacent-paper
#: miscitation: "three step cascade of hexokinase" would carry hexokinase's
#: Km on two steps hexokinase does not run.
SINGLE_ENZYME_RULES = frozenset({
    "michaelis_menten", "competitive_inhibition", "noncompetitive_inhibition",
    "uncompetitive_inhibition", "mixed_inhibition", "substrate_inhibition",
    "product_inhibition", "cooperative_catalysis", "reversible_catalysis",
    "ordered_bi_bi", "ping_pong_bi_bi", "mwc_allostery",
})

#: The shape built when a description names an enzyme and no mechanism.
NAMED_ENZYME_SHAPE = "Michaelis Menten"

#: Word stems that describe a mechanism. A description the grammar did not
#: recognise that names an enzyme AND one of these ("hexokinase
#: oscillator") is refused, not read as one enzyme on one substrate: the
#: person asked for a mechanism this grammar does not build, and building
#: Michaelis-Menten instead would answer a question they did not ask.
_MECHANISM_STEMS = (
    "oscillat", "switch", "toggle", "feedback", "feed-forward", "feedforward", "loop", "cascade",
    "cycle", "pathway", "bistab", "gene", "promoter", "repress", "transcri", "translat",
    "transport", "pump", "channel", "receptor", "binding", "complex", "inhibit", "allosteric",
    "cooperativ", "hill", "network", "circuit", "signal", "phosphorylation", "dephosph", "competition",
    "competing", "branch", "reversible", "two-substrate", "bi-bi", "ping-pong",
)


@dataclass
class DescriptionReading:
    """What `read_description` made of `args.description`.

    `description` is what to compose: the description as typed, or
    NAMED_ENZYME_SHAPE when it named an enzyme and no mechanism. `notes`
    are sentences for the report, each inference stated. `name_refusal`
    is the policy's `NameNotResolved` when the enzyme the description names
    is several enzymes, and `refusal_note` the search note that says so.
    `unapplied` says why a named enzyme was not made the subject.
    """

    description: str
    notes: List[str] = field(default_factory=list)
    name_refusal: Optional[Any] = None
    refusal_note: Optional[str] = None
    unapplied: Optional[str] = None
    enzyme_text: Optional[str] = None
    #: Choices made while reading (ADR 0182): the enzyme a name that is a
    #: few enzymes was taken as, when BRENDA's data singles one out.
    choices: List[Any] = field(default_factory=list)


#: The shape built when a description that named an enzyme and no
#: mechanism also named an inhibitor (ADR 0182): the commonest mode, said.
INHIBITED_ENZYME_SHAPE = "Michaelis-Menten with a competitive inhibitor"


def _rerun_command(description: str) -> str:
    """`caterva compose "<description>" --subject {ec}`, quoted for a shell and
    with its braces doubled, because the refusal fills `{ec}` with format()."""
    import shlex

    quoted = (f'"{description}"' if not re.search(r'["$`\\!]', description)
              else shlex.quote(description))
    return f"caterva compose {quoted} --subject {{ec}}".replace("{", "{{").replace("}", "}}") \
        .replace("{{ec}}", "{ec}")


def _flag_subject_ec(args: Any) -> Optional[str]:
    """The EC number `--subject` names, offline, or None when it does not
    name exactly one (the search then refuses it, as it always has)."""
    try:
        from caterva.enzymes.policy import resolve_enzyme_name

        return resolve_enzyme_name(args.subject, args.organism, allow_unlisted_ec=True).ec
    except Exception:  # noqa: BLE001 - read_subject refuses it, with the candidates named
        return None


def _shape_from(description: str, reading: Any) -> Tuple[str, str, Optional[str]]:
    """(what to compose, the rule it builds, a note) for `description`.

    Raises the grammar's UnrecognisedShape unless the description named an
    enzyme and nothing a mechanism is made of, in which case the shape is
    one enzyme turning one substrate into product and the note says so.
    """
    from caterva.compose.grammar import UnrecognisedShape, _named_pathway_in, recognise

    try:
        return description, recognise(description).rule, None
    except UnrecognisedShape as exc:
        # A named pathway ("glycolysis") and a missing motif library are
        # refusals with their own remedy; only "no shape matches" is a
        # description that may just have named an enzyme and stopped.
        if (type(exc) is not UnrecognisedShape or not reading.names_enzyme
                or _named_pathway_in(description.lower()) is not None):
            raise
        enzyme = reading.enzyme_text
        mechanism = [w for w in reading.remainder.lower().split()
                     if any(w.startswith(stem) for stem in _MECHANISM_STEMS)]
        if mechanism:
            ec = reading.ec or "<its EC number>"
            raise UnrecognisedShape(
                description,
                exc.reason + f" Your description names the enzyme {enzyme!r}, and also "
                + ", ".join(repr(w) for w in mechanism) + ", which is not a mechanism this grammar "
                "builds, so it was not read as one enzyme turning one substrate into product. "
                f"To model it that way, run: caterva compose \"{NAMED_ENZYME_SHAPE}\" --subject {ec}",
                suggestions=exc.suggestions) from None
        return NAMED_ENZYME_SHAPE, "michaelis_menten", (
            f"Your description named an enzyme ({enzyme!r}) and no mechanism this grammar "
            "recognises, so its shape was read as Michaelis-Menten: one enzyme turning one "
            "substrate into one product. To build another mechanism, describe it, e.g. "
            "'Michaelis-Menten with a competitive inhibitor'.")


def _why_not_applied(rule: str, model_tables: Sequence[Optional[str]], reading: Any) -> str:
    named = f"the enzyme your description names ({reading.enzyme_text!r}"
    named += f", EC {reading.ec})" if reading.ec else ")"
    kcats = sum(1 for t in model_tables if t == "kcat")
    if not any(t in ("kcat", "km") for t in model_tables):
        return (f"{named} was not applied: this mechanism ({rule.replace('_', ' ')}) has no enzyme step, "
                "so no constant of it is an enzyme's")
    if kcats > 1:
        return (f"{named} was not applied: this mechanism ({rule.replace('_', ' ')}) has {kcats} catalytic "
                "steps, and one enzyme's measured constants on every step would ground steps the "
                "description did not attach to it (ADR 0076)")
    return (f"{named} was not applied: this mechanism ({rule.replace('_', ' ')}) is not one of the "
            "single-enzyme shapes a description's enzyme is applied to (ADR 0181). Pass --subject to "
            "apply it deliberately")


def read_description(args: Any, *, err: Any = None, look_up_substrate: bool = True) -> DescriptionReading:
    """Fill what no flag set from what the description names, and say so.

    THE ONE PLACE a description is read for its subject: `compose_report`
    (so the terminal and Caterva Studio), `_export` and `--antimony` all call
    this, so the three cannot read one sentence three ways. Flags always win:
    the description only fills `args.subject`, `args.organism`,
    `args.substrate` and `args.inhibitor` where no flag set them, and every
    value it fills is a note in the report.

    * An enzyme (caterva.enzymes.sentence: exact names and EC numbers only)
      becomes the subject only in a single-enzyme shape (SINGLE_ENZYME_RULES);
      in any other the report says it was not applied and why. A
      description that named an enzyme and no mechanism is built as
      Michaelis-Menten, and the note says that is how it was read.
    * A name that is several enzymes is refused, the candidates named and
      the exact command that accepts one given (`name_refusal`).
    * A substrate only when BRENDA lists it for that enzyme
      (`brenda_km_substrates`, `match_substrate`); otherwise the search
      chooses the best-measured substrate BRENDA lists and says so (ADR
      0182, `_search_resolved`). A word BRENDA lists only as an inhibitor
      ("dihydrofolate reductase with methotrexate") is read as the
      inhibitor, and a description with no mechanism is then built with
      it (`_built_with_its_inhibitor`). `look_up_substrate` False skips
      the fetch.
    * A name that is a few enzymes of which BRENDA has rows for one only is
      taken as that one, as a choice the report states
      (`_enzyme_the_data_singles_out`); otherwise it is refused as before.
    * `--organism`, `--substrate` or `--inhibitor` given while no subject
      was named or read are said to have gone unused, on `err` and in a
      note, instead of being dropped without a word.
    """
    from caterva.enzymes.sentence import read_sentence

    err = sys.stderr if err is None else err
    typed = args.description
    reading = read_sentence(typed, organism=getattr(args, "organism", None))
    description, rule, shape_note = _shape_from(typed, reading)
    out = DescriptionReading(description=description)
    if shape_note:
        out.notes.append(shape_note)
    tables: Sequence[Optional[str]] = ()
    if reading.names_enzyme and rule not in SINGLE_ENZYME_RULES:
        from caterva.compose.pipeline import compose

        tables = [q.table for q in compose(description).resolvable]

    if getattr(args, "subject", None):
        if reading.ec and args.subject.strip() not in (reading.ec, reading.enzyme_text):
            out.notes.append(
                f"Your description names {reading.enzyme_text!r} (EC {reading.ec}); --subject "
                f"{args.subject} was used, because a flag wins over the description.")
    elif reading.names_enzyme and rule not in SINGLE_ENZYME_RULES:
        out.unapplied = _why_not_applied(rule, tables, reading)
        out.notes.append(out.unapplied[:1].upper() + out.unapplied[1:] + ".")
    elif reading.ec:
        args.subject = reading.ec
        out.notes.append(reading.enzyme_note())
        # ADR 0182: a symbol is one protein of its EC number ("HK2"); the
        # enzyme note says the constants come from rows that name it, so the
        # isoform is searched for unless --isoform set one.
        if getattr(reading, "isoform", None) and not getattr(args, "isoform", None):
            args.isoform = reading.isoform
        elif getattr(reading, "isoform", None) and args.isoform != reading.isoform:
            # The enzyme note above says the constants come from rows naming
            # the description's isoform; the flag's isoform is the one used.
            out.notes.append(f"Your description names the isoform {reading.isoform}; --isoform {args.isoform} "
                             "was used instead, because a flag wins over the description.")
    elif reading.ambiguity is not None and (
            chosen := _enzyme_the_data_singles_out(reading, args)) is not None:
        # A name that is a few specific enzymes ("citrate synthase": the Si-
        # and Re- enzymes), of which BRENDA has measurements for one only
        # (ADR 0182). Taken, and said with the others named; a class word, a
        # symbol, a typo, or two candidates that both have rows stay refused.
        args.subject = chosen.chosen
        out.choices.append(chosen)
    elif reading.ambiguity is not None:
        from caterva.enzymes.policy import AMBIGUOUS, _refuse

        out.enzyme_text = reading.enzyme_text
        out.name_refusal = _refuse(reading.ambiguity, _rerun_command(typed), AMBIGUOUS)
        out.refusal_note = (f"No search was run: your description names {reading.enzyme_text!r}, "
                            f"which is not one enzyme. {out.name_refusal}")
    elif reading.near is not None:
        note = reading.near_note()
        out.unapplied = note[:1].lower() + note[1:].rstrip(".")
        out.notes.append(note)
    elif reading.other_enzymes:
        out.unapplied = ("the enzymes your description names ("
                         + ", ".join(f"{t!r}, EC {ec}" for t, ec, _ in reading.other_enzymes)
                         + ") are several, and none was applied: a model grounded in one of them would "
                         "carry constants for a protein the description did not single out")
        out.notes.append(out.unapplied[:1].upper() + out.unapplied[1:] + ".")

    if args.subject:
        if reading.organism and not args.organism:
            args.organism = reading.organism
            out.notes.append(reading.organism_note())
        elif reading.organism and args.organism != reading.organism:
            out.notes.append(
                f"Your description names {reading.organism_text!r} ({reading.organism}); --organism "
                f"{args.organism} was used, because a flag wins over the description.")
        if len(reading.organisms_named) > 1 and not args.organism:
            out.notes.append("Your description names " + " and ".join(
                f"{t!r} ({b})" for t, b in reading.organisms_named)
                + "; no organism was read from it, because choosing one would be a guess.")
        if reading.unread_organism is not None and not args.organism:
            out.notes.append(reading.unread_organism_note())
        inhibitor_read = False
        if reading.inhibitor_text and not getattr(args, "inhibitor", None):
            args.inhibitor = reading.inhibitor_text
            inhibitor_read = True
            out.notes.append(f"Read {reading.inhibitor_text!r} in your description as the inhibitor.")
        if look_up_substrate and not args.substrate and reading.substrate_candidates:
            inhibitor_read = _substrate_from(args, reading, out) or inhibitor_read
        if inhibitor_read and rule == "michaelis_menten":
            _built_with_its_inhibitor(args, out)
    else:
        unused = [f"--{flag} {getattr(args, flag)}" for flag in ("organism", "substrate", "inhibitor")
                  if getattr(args, flag, None)]
        if unused and out.name_refusal is None:
            why = out.unapplied or "no enzyme was named, by --subject or in the description"
            text = (f"{' and '.join(unused)} {'was' if len(unused) == 1 else 'were'} given, but "
                    f"{why}, so nothing was searched for and {'it was' if len(unused) == 1 else 'they were'} "
                    "not used. Name the enzyme with --subject to search for it.")
            out.notes.append(text)
            print(f"Not used: {text}", file=err)
    return out


def _enzyme_the_data_singles_out(reading: Any, args: Any) -> Optional[Any]:
    """The `Choice` of one EC number for an enzyme name that is a few
    enzymes, when BRENDA's Km rows single one out (ADR 0182); None otherwise.

    Only the candidates the finder ranks best (its lowest tier: "these 2
    match best") are weighed, at most four, and never for a class word, an
    abbreviation or symbol offered for confirmation, or typo suggestions:
    those are not a few readings of one name but a question only the user
    can answer. `defaults.choose_enzyme` then takes one only when it is the
    one candidate with rows in the organism, or (no organism) has five
    times the rows of every other.
    """
    ambiguity = reading.ambiguity
    if (ambiguity is None or getattr(ambiguity, "class_word", False)
            or getattr(ambiguity, "confirm_only", False)
            or getattr(ambiguity, "suggestions_only", False) or not ambiguity.candidates):
        return None
    best = min(c.tier for c in ambiguity.candidates)
    tied_candidates = [c for c in ambiguity.candidates if c.tier == best]
    # A fragment of a longer name, a typo, an abbreviation or a class match
    # is not a reading of the name the user typed: never settled by rows.
    if any(getattr(c, "partial", False) or getattr(c, "abbreviation", False)
           or getattr(c, "via", "name") not in ("name", "ec") for c in tied_candidates):
        return None
    tied = [(c.ec, c.name) for c in tied_candidates]
    from caterva.compose.defaults import ENZYME_CANDIDATES_CONSIDERED, choose_enzyme

    if len(tied) > ENZYME_CANDIDATES_CONSIDERED:
        return None
    organism = getattr(args, "organism", None) or reading.organism
    return choose_enzyme(reading.enzyme_text or reading.text, tied, organism)


def _built_with_its_inhibitor(args: Any, out: DescriptionReading) -> None:
    """A description that named an enzyme and an inhibitor and no mechanism
    is built with the inhibitor in it (ADR 0182), and the note says which
    mode, and what BRENDA's rows for that inhibitor state about theirs.

    "dihydrofolate reductase with methotrexate in E. coli" was built as
    plain Michaelis-Menten, two constants, with methotrexate dropped without
    a word: the model had no place for the one compound the user named.
    Competitive is the commonest mode and the one the grammar names first;
    the note quotes the rows' own modes so a reader whose inhibitor is
    noncompetitive sees it and can say so.
    """
    out.description = INHIBITED_ENZYME_SHAPE
    stated = ""
    ec = _flag_subject_ec(args) if args.subject else None
    if ec:
        try:
            from caterva.compose.defaults import ki_modes

            modes = ki_modes(ec, args.organism, args.inhibitor)
        except Exception:  # noqa: BLE001 - the mode note is a courtesy
            modes = None
        where = f" in {args.organism}" if args.organism else ""
        if modes:
            stated = (f"; BRENDA's Ki rows for {args.inhibitor} under EC {ec}{where} state: "
                      + ", ".join(f"{m} ({n} row{'s' if n != 1 else ''})"
                                  for m, n in sorted(modes.items(), key=lambda kv: (-kv[1], kv[0]))))
        elif modes is not None:
            stated = f"; BRENDA has no Ki row for {args.inhibitor} under EC {ec}{where}"
    out.notes.append(
        f"Your description named an inhibitor ({args.inhibitor!r}) and no mechanism, so the model "
        f"is competitive inhibition{stated}. To build another mode, describe it, e.g. "
        "'noncompetitive inhibition'.")


def _substrate_from(args: Any, reading: Any, out: DescriptionReading) -> bool:
    """Accept a word of the description as `args.substrate`, only against
    what BRENDA lists for the subject's EC number; a word BRENDA lists as an
    inhibitor (a Ki row) instead, with no inhibitor named, as
    `args.inhibitor`. True when an inhibitor was read."""
    from caterva.enzymes.sentence import match_substrate

    ec = reading.ec if reading.ec and args.subject == reading.ec else _flag_subject_ec(args)
    if ec is None:
        return False
    listed = brenda_km_substrates(ec, args.organism)
    shown = ", ".join(repr(c) for c in reading.substrate_candidates[:4])
    where = f" for {args.organism}" if args.organism else ""
    if listed is None:
        out.notes.append(
            f"BRENDA's substrate list for EC {ec} could not be read, so no word of your description "
            f"({shown}) was taken as the substrate.")
        return False
    match = match_substrate(reading.substrate_candidates, list(listed))
    if match.name is None and not match.rivals and not getattr(args, "inhibitor", None):
        inhibitor = _inhibitor_from(ec, args.organism, reading.substrate_candidates)
        if inhibitor is not None:
            typed, name = inhibitor
            args.inhibitor = name
            out.notes.append(
                f"Read {typed!r} in your description as the inhibitor {name}, which BRENDA lists Ki "
                f"rows for under EC {ec}{where} (it lists no Km for it as a substrate).")
            return True
    if match.name is not None:
        args.substrate = match.name
        how = (" with its stereo or anomer prefix set aside, the only substrate BRENDA lists under "
               "that name" if match.prefix_set_aside else "")
        out.notes.append(
            f"Read {match.typed!r} in your description as the substrate {match.name}, which BRENDA "
            f"lists for EC {ec}{where}{how}.")
    elif match.rivals:
        out.notes.append(
            "Your description's words match more than one substrate BRENDA lists for EC "
            f"{ec}{where} (" + "; ".join(f"{t!r} as {n}" for t, n in match.rivals)
            + "), so none was read as the substrate; the search chooses among them by their rows.")
        # The choice is held to what the user's word matched (ADR 0182):
        # "glucose" decides between D-glucose and beta-D-glucose by rows, and
        # never becomes D-mannose because D-mannose is better measured.
        _remember(args, substrate_among=tuple(n for _, n in match.rivals),
                  substrate_instead=(
                      "Your description's words match several substrates BRENDA lists ("
                      + "; ".join(f"{t!r} as {n}" for t, n in match.rivals) + ")"))
    else:
        # The word is never relabelled as a listed substrate (ADR 0076).
        # The search then chooses the best-measured one BRENDA lists and
        # says so in its own note (ADR 0182); this says the typed word is
        # not what the model is of, so the two notes cannot be misread.
        out.notes.append(
            f"No word of your description ({shown}) is a substrate BRENDA lists for EC {ec}{where}, "
            "so none was taken as the substrate, and if you typed one it was not used: the model is "
            "not of it. Pass --substrate with BRENDA's own name for the compound you meant.")
        # The choice's note must not then open "No substrate was named":
        # the user may well have named one BRENDA does not list.
        _remember(args, substrate_instead=(
            f"No substrate BRENDA lists Km rows for under EC {ec}"
            + (f" in {args.organism}" if args.organism else "")
            + f" was named (no word of your description, {shown}, is one)"))
    return False


def _remember(args: Any, **fields: Any) -> None:
    """Carry what the reader learned to the search's choice (`args` is the
    one object both see); silently nothing for an args that refuses it."""
    for name, value in fields.items():
        try:
            setattr(args, name, value)
        except (AttributeError, TypeError):  # pragma: no cover - a frozen args
            pass


def _inhibitor_from(ec: str, organism: Optional[str],
                    candidates: Sequence[str]) -> Optional[Tuple[str, str]]:
    """(the word as typed, BRENDA's name) for the first candidate that is,
    case aside, a compound BRENDA lists Ki rows for under `ec` (in
    `organism`); None when none is, or the page cannot be read. Exact
    names only, as for a substrate: "methotrexate", never a word inside
    a longer compound's name."""
    try:
        from caterva.compose.defaults import ki_compounds

        listed = ki_compounds(ec, organism)
    except Exception:  # noqa: BLE001 - not reading one is not reading one
        return None
    by_key = {" ".join(n.split()).casefold(): n for n in listed}
    for typed in candidates:
        name = by_key.get(" ".join(typed.split()).casefold())
        if name is not None:
            return typed, name
    return None


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


def compounds_from(args) -> Dict[str, str]:
    """--inhibitor, --product and --compound PORT=NAME as a ports -> names map."""
    out: Dict[str, str] = {}
    if getattr(args, "inhibitor", None):
        out["@inhibitor"] = args.inhibitor
    if getattr(args, "product", None):
        out["@product"] = args.product
    for item in getattr(args, "compound", None) or []:
        port, sep, name = item.partition("=")
        if not sep or not port.strip() or not name.strip():
            raise SystemExit(f"--compound takes PORT=NAME, got {item!r}")
        out[port.strip()] = name.strip()
    return out


def read_subject(model: Any, args: Any) -> Tuple[Any, Optional[str], Optional[str], Optional[Any]]:
    """Turn `--subject` into an EC number: `(model, what it was read as, a refusal, why)`.

    `why` is the policy's `NameNotResolved` when a name was refused, so a
    caller that renders the candidates (the studio) has them NAMED rather
    than parsed back out of the refusal's sentence; None otherwise.

    ONE POLICY, NOT A COPY. The name goes to `caterva.enzymes.policy`, the
    function every command that takes an enzyme name uses: the enzyme
    nomenclature first, UniProt's protein-name search only for a name the
    nomenclature does not hold. A name that is several enzymes is refused
    here with each candidate NAMED and the flag that would accept one, and
    nothing is searched. An EC number is read by the same function, so one
    the nomenclature has transferred is replaced by its successor and the
    report says so; one it has deleted is refused; one it does not list is
    used as given, because BRENDA may know a number this release does not.

    The second element is a sentence for the report when the subject was
    changed or needs a caveat (a name read as an EC number, a transferred
    number, an enzyme with no protein from the organism asked about), and
    None when nothing was.
    """
    from caterva.enzymes.policy import NameNotResolved, literature_uniprot_lookup, resolve_enzyme_name

    subject = args.subject
    if re.fullmatch(r"\s*\d+(\.\d+){0,2}\.?\s*", subject or "") and model.ec_number is None:
        # "2.7.1" is an EC class, not an enzyme, and looking it up in
        # UniProt as a NAME produced "no reviewed enzyme named '2.7.1'".
        return model, None, (
            f"No search was run: {subject.strip()!r} is an incomplete EC "
            f"number, which names a class of enzymes rather than one. A full "
            f"EC number has four parts, like 2.7.1.1 (hexokinase)"
        ), None
    try:
        # Without the literature layer (the installed app) the nomenclature
        # still resolves the name; only the UniProt fallback for a protein
        # name that is not an enzyme name is missing, and the search says so.
        resolution = resolve_enzyme_name(
            subject, getattr(args, "organism", None), uniprot=literature_uniprot_lookup(),
            allow_unlisted_ec=True)
    except NameNotResolved as exc:
        return model, None, f"No search was run: {exc}", exc
    # ADR 0182: what the name implies (the isoform of "HK2", Homo sapiens
    # for a human gene symbol) fills only what no flag set, and the notes
    # claim a search narrowed to it only when it was filled here.
    isoform_applied = bool(getattr(resolution, "isoform", None) and not getattr(args, "isoform", None))
    organism_applied = bool(getattr(resolution, "organism", None) and not getattr(args, "organism", None))
    if isoform_applied:
        args.isoform = resolution.isoform
    if organism_applied:
        args.organism = resolution.organism
    notes = resolution.notes(subject, isoform_applied=isoform_applied, organism_applied=organism_applied)
    if getattr(resolution, "isoform", None) and not isoform_applied and args.isoform != resolution.isoform:
        notes.append(f"--isoform {args.isoform} was used, because a flag wins over what {subject.strip()!r} implies.")
    note = " ".join(notes) or None
    if resolution.ec != (model.subject or "").strip():
        model = replace(model, subject=resolution.ec)
    return model, note, None, None


def _resolve_subject(model: Any, args: Any) -> Tuple[Any, Optional[str], Optional[str]]:
    """`read_subject` without the policy's refusal object."""
    model, read_as, refusal, _ = read_subject(model, args)
    return model, read_as, refusal


@dataclass
class LiteratureSearch:
    """What `--subject` and the literature search came to.

    `refused` is `search_the_literature`'s third value; `name_refusal` is
    the policy's `NameNotResolved` when the refusal was a name that is not
    exactly one enzyme (several enzymes, none, a deleted number)."""

    model: Any
    note: Optional[str]
    refused: bool
    name_refusal: Optional[Any] = None


def search_literature(
    model: Any, args: Any, *, resolve: Optional[Callable[..., Any]] = None,
) -> LiteratureSearch:
    """Resolve `--subject` to an EC number, then search the literature.

    The subject is read by the one policy (`read_subject`), then
    `_search_resolved` searches; what the subject was read as goes in front
    of the search's own note. `resolve` replaces the resolver
    `compose_and_parameterise` would build (`agents.scouts.brenda_resolver()`);
    the studio passes that same resolver wrapped so it can say which
    constant is being looked up.
    """
    model, read_as, refusal, why = read_subject(model, args)
    if refusal is not None:
        return LiteratureSearch(model, refusal, True, why)
    model, note, refused = _search_resolved(model, args, resolve=resolve)
    if read_as:
        note = f"{read_as} {note}" if note else read_as
    return LiteratureSearch(model, note, refused)


def search_the_literature(
    model: Any, args: Any, *, resolve: Optional[Callable[..., Any]] = None,
) -> Tuple[Any, Optional[str], bool]:
    """`search_literature` as `(model, note, refused)`: the form `caterva md`
    and the tests import, under its old private name `_search_the_literature`
    too. `refused` is True when the search could not be RUN."""
    found = search_literature(model, args, resolve=resolve)
    return found.model, found.note, found.refused


#: How many organisms the no-rows-in-your-organism refusal names at most.
#: (It named substrates until ADR 0182, when a missing substrate became a
#: choice that names its alternatives itself: `defaults.ALTERNATIVES_NAMED`.)
SUBSTRATES_NAMED = 8


def brenda_km_substrates(ec: str, organism: Optional[str]) -> Optional[Dict[str, int]]:
    """substrate -> Km row count on BRENDA's page for `ec`, for `organism`
    when one is given; None when the page could not be read.

    The plain-language reader accepts a word of the description as the
    substrate only when it is one of these; `defaults.choose_substrate`
    reads the same page with the same parser, so a word is never read as a
    substrate the choice would not have listed.
    """
    try:
        from caterva.checkout import literature_module
        from caterva.compose.organisms import normalise_organism
        client = literature_module("brenda_client")
        name, _ = normalise_organism(organism) if organism else (None, None)
        html = client.fetch_brenda_html(ec)
        rows = client.parse_brenda_km_html(
            html, ec, [], name, require_substrate_match=False)
    except Exception:  # noqa: BLE001 - each caller says what not having it means
        return None
    counts: Dict[str, int] = {}
    for row in rows:
        counts[row.substrate] = counts.get(row.substrate, 0) + 1
    return counts


def _not_named(model: Any, args: Any) -> Tuple[List[str], bool, bool]:
    """(the tables this model reads, whether a constant needs a substrate
    nobody named, whether one needs an inhibitor nobody named)."""
    named = replace(model, substrate=getattr(args, "substrate", None) or None,
                    compounds=compounds_from(args))
    asked = [q for q in model.resolvable if q.table is not None and not q.lookup_refused]
    tables = [t for t in ("km", "kcat", "ki") if any(q.table == t for q in asked)]
    substrate = any(q.primary and named.compound_for(q) is None for q in asked)
    inhibitor = any(q.ligand_role == "regulator" and named.compound_for(q) is None for q in asked)
    return tables, substrate, inhibitor


def _organism_has_no_rows(ec: str, organism: str) -> Optional[str]:
    """The refusal for an organism the user NAMED that has no Km row for
    `ec` at all, listing the organisms that do; None when it has rows, or
    when the page cannot be read (the substrate choice then says that).

    "glucose-6-phosphate dehydrogenase in S. cerevisiae" was refused with
    "Re-run with --substrate NAME" -- and a user who did would have got
    placeholders again, because BRENDA's page for EC 1.1.1.49 has no yeast
    Km row at all. The organism is the blocker, so the advice names it.
    Another organism is never substituted for the one named (ADR 0024).
    """
    from caterva.compose.defaults import km_organisms, table_rows

    try:
        by_organism = km_organisms(ec)
        mine = len(table_rows(ec, "km", organism))
    except Exception:  # noqa: BLE001
        return None
    if mine:
        return None
    ranked = sorted(by_organism, key=lambda o: (-by_organism[o], o))
    listed = "; ".join(f"{o} ({by_organism[o]} row{'s' if by_organism[o] != 1 else ''})"
                       for o in ranked[:SUBSTRATES_NAMED])
    more = f" and {len(ranked) - SUBSTRATES_NAMED} more" if len(ranked) > SUBSTRATES_NAMED else ""
    if not ranked:
        return (f"No search was run: BRENDA's page for EC {ec} holds no Km row for any organism, "
                "so there is no measured substrate to model. Supply the constants yourself.")
    return (f"No search was run: BRENDA holds no Km row for EC {ec} in {organism}, so no substrate "
            f"could be chosen and no constant of this model can be measured there. The organism, "
            f"not the substrate, is what is missing: naming a substrate would not help. Organisms "
            f"with Km rows for EC {ec}: {listed}{more}. Re-run with --organism set to one of them "
            f"(Caterva never substitutes another organism's value for the one you named, ADR 0024), "
            f"or supply the constants yourself.")


def _choose_what_was_not_named(model: Any, args: Any) -> Tuple[Any, Optional[str]]:
    """Choose, out loud, the organism, substrate and inhibitor the user did
    not name, before the search, so the search is run for them (ADR 0182).

    Returns `(model, refusal)`: the model with the choices recorded on it
    (`ComposedModel.choices`) and `args` filled as if the flags had been
    typed, or a refusal sentence when nothing can be searched.

    ORDER MATTERS. The organism first, given the substrate and inhibitor
    when either was named (so "xanthine oxidase inhibited by allopurinol"
    is modelled in Bos taurus, the one organism with an allopurinol Ki row,
    not in whichever organism a search of everything happened to settle
    on); then the substrate, in that organism; then the inhibitor, given
    both. A flag or a compound the sentence named is never replaced. An
    organism the user named that has no Km row at all is a refusal naming
    the organisms that have one, never a switch.

    WHEN NOTHING CAN BE CHOSEN the old refusal stands, worded for what is
    actually missing: the page could not be read (re-run with --substrate,
    as before), or it lists no substrate.
    """
    from caterva.compose import defaults

    ec = model.ec_number
    if ec is None:
        return model, None
    tables, needs_substrate, needs_inhibitor = _not_named(model, args)
    choices = list(getattr(model, "choices", ()) or ())
    inhibitor = compounds_from(args).get("@inhibitor")

    if not args.organism and (needs_substrate or needs_inhibitor or args.substrate):
        chosen = defaults.choose_organism(
            ec, substrate=args.substrate or None, inhibitor=inhibitor, needs=tables or ("km",))
        if chosen is not None:
            args.organism = chosen.chosen
            choices.append(chosen)
    elif args.organism and needs_substrate:
        blocked = _organism_has_no_rows(ec, args.organism)
        if blocked is not None:
            return replace(model, choices=tuple(choices)), blocked

    if needs_substrate:
        among = getattr(args, "substrate_among", None)
        among = tuple(among) if isinstance(among, (tuple, list)) and among else None
        try:
            chosen = defaults.choose_substrate(ec, args.organism, needs_kcat="kcat" in tables,
                                               strict=True, among=among)
            if chosen is None and among:
                # None of the matched names has a row here after all: the
                # whole list, said as such by the `instead` clause.
                chosen = defaults.choose_substrate(ec, args.organism, needs_kcat="kcat" in tables,
                                                   strict=True)
        except Exception:  # noqa: BLE001 - the page could not be read: the old refusal
            chosen = None
            unreadable = True
        else:
            unreadable = False
        instead = getattr(args, "substrate_instead", None)
        if chosen is not None and isinstance(instead, str) and instead:
            chosen = replace(chosen, instead=instead)
        if chosen is None:
            where = f" in {args.organism}" if args.organism else ""
            missing = ", ".join(t for t in tables if t in ("km", "kcat", "ki"))
            reason = ("BRENDA's page for it could not be read to choose one" if unreadable else
                      f"BRENDA lists no substrate with a Km row for EC {ec}{where} to choose")
            return replace(model, choices=tuple(choices)), (
                f"No search was run: this model needs {missing} from BRENDA, and those tables "
                f"are per-substrate; no substrate was named and {reason}. Re-run with "
                f"--substrate NAME.")
        args.substrate = chosen.chosen
        choices.append(chosen)

    if needs_inhibitor:
        chosen = defaults.choose_inhibitor(ec, args.organism, args.substrate)
        if chosen is not None:
            args.inhibitor = chosen.chosen
            choices.append(chosen)

    model = replace(model, organism=args.organism, substrate=args.substrate or None,
                    compounds=compounds_from(args), choices=tuple(choices))
    return model, None


def _search_resolved(
    model: Any, args: Any, *, resolve: Optional[Callable[..., Any]] = None,
) -> Tuple[Any, Optional[str], bool]:
    """Resolve this model's constants from the literature.

    Returns `(model, note, refused)`. `refused` is True when the search
    could not be RUN -- an ambiguous enzyme name, an organism named with no
    Km row, a page that could not be read to choose a substrate, no
    literature layer, a crash -- and False when it ran, whatever it found.
    What the user did not name is chosen first, out loud
    (`_choose_what_was_not_named`, ADR 0182).

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

    A NAME IS NOT AN ENZYME. `--subject "lactate dehydrogenase"` is the
    L- and the D-lactate dehydrogenases, among others; `read_subject`
    refuses and names each rather than picking, because a wrong EC number is
    a citation for the wrong protein rather than merely a wrong value.

    THE RESOLVER IS TOLD WHAT THE MODEL IS OF. Its evidence grades cannot
    tell LDH-A's row from LDH-B's, or a competitive Ki from a noncompetitive
    one, so each request carries the isoform `--isoform` asked for and, for
    an inhibition constant, the motif's mode and the model's substrate
    (with `--any-mode`, the mode only as one to compare with, so the row
    carried is the one asked for no mode, and the report names the row the
    mode would have given). The resolver ranks every row by them before it
    chooses, as it does for the API and the TypeScript CLI, and the row it
    returns is the row carried (narrowed.py). The two selections then say
    what that choice did, against the row the evidence alone would have
    taken: the isoform (isoform.py), then the mode (ki_mode.py). A constant
    the resolver or a selection refuses is a placeholder whose reason says
    so, never one described as not found.
    """
    from caterva.checkout import LiteratureLayerUnavailable

    if getattr(args, "isoform", None):
        model = replace(model, isoform=args.isoform)
    ec = model.ec_number
    model, blocked = _choose_what_was_not_named(model, args)
    if blocked is not None:
        return model, blocked, True

    try:
        from caterva.compose.export import unresolved_from_search
        from caterva.compose.pipeline import compose_and_parameterise
        _, search = compose_and_parameterise(
            model.query, subject=ec, organism=args.organism,
            substrate=args.substrate, compounds=compounds_from(args),
            isoform=getattr(args, "isoform", None) or None,
            any_mode=bool(getattr(args, "any_mode", False)),
            resolve=resolve,
        )
    except LiteratureLayerUnavailable as exc:
        return model, str(exc), True
    except Exception as exc:  # noqa: BLE001 - a failed search is a note, not a crash
        return model, f"The literature search failed: {type(exc).__name__}: {exc}", True

    skipped = replace(model, compounds=compounds_from(args)).unsearched()
    if search is None:
        if skipped:
            return model.with_measured({}, not_found=skipped), (
                "No search was run: every constant this model could look up belongs to a "
                "compound that was not named. " + "; ".join(sorted(set(skipped.values())))), False
        return model, "No search was run: this model has nothing a database could supply.", False

    # The resolver was told what the model is of, and its row for each
    # constant is carried; the selections say what that choice did
    # (narrowed.py). On by default: a noncompetitive model carrying a
    # competitive constant is wrong whether or not the report admits it.
    # --any-mode keeps the resolver's pick asked for no mode, and the notes
    # name the row its mode would have given (fallback_logic.ModeDefault).
    from caterva.compose.ki_mode import constants_of
    from caterva.compose.narrowed import select_for_model

    from caterva.compose.export import ExportRefused

    not_found = {**skipped, **unresolved_from_search(search)}
    try:
        chosen = select_for_model(
            search, constants_of(model),
            substrate=getattr(model, "substrate", None) or getattr(args, "substrate", None),
            isoform=getattr(args, "isoform", None) or None,
            any_mode=bool(getattr(args, "any_mode", False)),
        )
    except ExportRefused as exc:
        # The search ran over every organism and settled on none (several
        # gave a whole model, or none did). This was an uncaught traceback
        # for "pepsin with hemoglobin" and "alpha-amylase with starch" with
        # no organism; it is a report, with the organisms named. Reached
        # only when no organism could be chosen before the search.
        undecided = [o for o in getattr(search, "undecided", ()) if o]
        why = (f"the search ran over every organism and settled on no single one: "
               + (f"{', '.join(undecided)} each give a whole model, and nothing separates them"
                  if undecided else "no organism gave a value for every constant")
               + ". Re-run with --organism NAME")
        return replace(model, search_refused=why), f"No measured value was used: {why}", True
    measured = dict(chosen.measured)
    # A value whose BRENDA row is another compound's -- the resolver finds
    # a name inside longer names -- is withheld, never carried under the
    # name the user typed or Caterva chose (`_neighbours_withheld`).
    neighbours = _neighbours_withheld(model, measured, ec)
    for identifier in neighbours:
        measured.pop(identifier, None)
    # Constants the search returned a value for, or found rows for, and did
    # not use. They end up placeholders like the ones the search found
    # nothing for, and must not be described as found-nothing.
    withheld: Dict[str, str] = {**chosen.withheld, **neighbours}
    not_found.update(withheld)
    selection_notes = chosen.notes
    if getattr(args, "isoform", None):
        from caterva.enzymes.isozyme import describe_isoform

        reading = describe_isoform(ec, args.organism, args.isoform)
        if reading:
            selection_notes = [reading, *selection_notes]
    failures = [
        run for branch in getattr(search, "branches", ())
        for record in getattr(branch.build.run, "rounds", ())
        for run in getattr(record, "ran", ())
        if getattr(run, "failed", False)
    ]
    sourced = model.with_measured(measured, not_found=not_found)
    if not measured and failures and not not_found:
        # Every scout failed and none reported an absence: the search did
        # not run, whatever the HTTP layer called it. A 404 from BRENDA's
        # enzyme page means the EC number is not one BRENDA has.
        text = "; ".join(sorted({str(r.failure) for r in failures}))
        if "404" in text:
            why = (
                f"BRENDA has no enzyme {ec}. Check the EC number: search "
                f"the enzyme's name on https://www.brenda-enzymes.org and "
                f"copy the number at the top of its page"
            )
        else:
            why = f"the literature search could not run: {text}"
        return replace(model, search_refused=why), why, True
    if not measured:
        why = "; ".join(sorted({r.failure for r in failures})) if failures else (
            "every table was searched and none held a value for this "
            "enzyme, organism and substrate"
        )
        if not withheld:
            return sourced, f"The search returned no measured value: {why}", False
        # "Every table was searched and none held a value" would be false
        # here: values came back and were refused, each for a reason the
        # provenance table prints beside it. The rest of what the search
        # did is still said. An earlier version returned before `why` was
        # built, so a refused Ki beside a failed kcat search read as if
        # the Ki were the only thing that had happened.
        note = (
            f"No measured value was used: the search returned values for "
            f"{', '.join(sorted(withheld))} and each was withheld, for the "
            f"reason the provenance table gives"
        )
        rest = [q for q in sourced.unmeasured if q not in withheld and q not in skipped]
        if rest and failures:
            note += (f". {len(rest)} still the motif library's placeholder "
                     f"({', '.join(rest)}), and part of the search failed: {why}")
        elif rest:
            note += (
                f". {len(rest)} still the motif library's placeholder "
                f"({', '.join(rest)}): the search ran and returned nothing for "
                f"them, which is different from their not having been looked for"
            )
        elif failures:
            note += f". Part of the search failed: {why}"
        note += _not_looked_up(skipped)
        if selection_notes:
            note += ". " + "; ".join(selection_notes)
        return sourced, note, False

    note = (
        f"{len(measured)} constant(s) resolved from the literature: "
        + ", ".join(sorted(measured))
    )
    if not args.organism:
        # Nobody asked for an organism, so the resolver's default chose one
        # -- for hexokinase and glucose, a chicken parasite. Legitimate and
        # cited, and not what someone modelling their own system expects to
        # read past without being told.
        chosen = sorted({m.organism for m in measured.values()
                         if getattr(m, "organism", None)})
        if chosen:
            note += (
                f". No --organism was given, so these come from "
                f"{', '.join(chosen)}, which the search chose; pass "
                f"--organism to choose it yourself"
            )
    # A constant deliberately not looked up (its compound unnamed) is not
    # one the search "ran and returned nothing for": the note said exactly
    # that about a Ki whose provenance row, three lines below, said "not
    # looked up" (found 2026-11-11, granzyme B with --substrate).
    still = [q for q in sourced.unmeasured if q not in withheld and q not in skipped]
    if still:
        note += (
            f". {len(still)} still the motif library's placeholder "
            f"({', '.join(still)}): the search ran and returned nothing for "
            f"them, which is different from their not having been looked for"
        )
    note += _not_looked_up(skipped)
    if withheld:
        # Found and refused is a third fact, beside found and not found:
        # "returned nothing" said of a refused --isoform constant was false.
        note += (
            f". {len(withheld)} returned by the search and not used "
            f"({', '.join(sorted(withheld))}): the provenance table says why"
        )
    if selection_notes:
        note += ". " + "; ".join(selection_notes)
    return sourced, note, False


def _neighbours_withheld(model: Any, measured: Mapping[str, Any], ec: Optional[str]) -> Dict[str, str]:
    """parameter id -> the reason it is withheld, for each value the search
    returned whose BRENDA row is a different compound's than the one the
    constant is for (`defaults.neighbour_of`).

    Found by reviewing ADR 0182's own live run: chymotrypsin in Homo
    sapiens, the substrate chosen as L-alanyl-L-alanyl-L-prolyl-L-
    phenylalanine p-nitroanilide, carried Km 0.219 mM (ref 769319), which is
    BRENDA's row for the N-succinyl compound the note named as the
    alternative. Withholding it leaves a labelled placeholder with the
    reason; the other compound is named, so the reader can model it
    instead. A page that cannot be read withholds nothing: the search read
    the same page, and an unverifiable check is not a failed one.
    """
    if not ec or not measured:
        return {}
    from caterva.compose import defaults

    out: Dict[str, str] = {}
    for q in getattr(model, "resolvable", ()) or ():
        m = measured.get(q.parameter_id)
        if m is None or q.table not in ("km", "kcat", "ki"):
            continue
        compound = model.compound_for(q)
        # The search's Measurement carries the reference in its citation
        # ("BRENDA ref 769319"), not always in `reference_id`.
        ref = getattr(m, "reference_id", None)
        if ref is None:
            cited = re.search(r"BRENDA ref (\d+)", str(getattr(m, "citation", "") or ""))
            ref = cited.group(1) if cited else None
        try:
            other = defaults.neighbour_of(
                ec, q.table, compound, getattr(m, "organism", None) or getattr(model, "organism", None),
                m.value, ref)
        except Exception:  # noqa: BLE001 - unverifiable is not wrong
            other = None
        if not other:
            continue
        flag = "--inhibitor" if q.table == "ki" else "--substrate"
        out[q.parameter_id] = (
            f"withheld: the value the search returned ({m.value:g} {m.unit}, BRENDA ref "
            f"{ref}) is BRENDA's row for {' / '.join(other)}, not for {compound} -- the "
            f"search matches a name inside longer names, and another compound's value is never "
            f"carried under this one's (ADR 0076). Pass {flag} with that name to model it, or "
            f"supply this constant yourself")
    return out


def _not_looked_up(skipped: Mapping[str, str]) -> str:
    """The note's clause for constants deliberately not looked up, or ""."""
    if not skipped:
        return ""
    return (f". {len(skipped)} not looked up ({', '.join(sorted(skipped))}): "
            "the provenance table says which compound would let it be")


_search_the_literature = search_the_literature


def provenanced_for_export(model: Any) -> Any:
    """The ProvenancedModel every export of `model` is written from.

    One call, so `--export` and the studio's artefacts cannot be written
    from two different decisions about where each number came from."""
    from caterva.compose.export import provenance_of

    return provenance_of(model, measured=dict(model.measured) or None)


def export_texts(
    provenanced: Any, formats: Sequence[str] = EXPORT_FORMATS,
    *, claim_ids: Optional[Mapping[str, str]] = None,
) -> Dict[str, Tuple[Optional[str], Optional[str]]]:
    """format -> (the artefact's text, None), or (None, ExportRefused's
    message) for a format that could not be written.

    The text is what `--export FORMAT` prints, without print's newline.
    Each format is refused on its own: the SBML toolchain being absent is
    no reason to withhold the CSV. `claim_ids` (identifier -> claim ref,
    from `--claims`) is handed to every writer; None leaves each artefact
    byte for byte what it was.
    """
    from caterva.compose.export import (
        ExportRefused, to_antimony, to_methods_paragraph, to_parameter_csv,
        to_sbml,
    )

    writers = {
        "sbml": to_sbml,
        "antimony": to_antimony,
        "csv": to_parameter_csv,
        "methods": to_methods_paragraph,
    }
    out: Dict[str, Tuple[Optional[str], Optional[str]]] = {}
    for fmt in formats:
        try:
            out[fmt] = (writers[fmt](provenanced, claim_ids=claim_ids), None)
        except ExportRefused as exc:
            out[fmt] = (None, str(exc))
    return out


def _export(description: str, subject: Optional[str], fmt: str,
            args: Any = None) -> int:
    """Write one artefact to stdout, or a refusal to stderr.

    NOTHING ELSE GOES TO STDOUT. A CSV with a markdown report in front of it
    is a CSV no parser reads, and an SBML file with one is not XML. That is
    why `--export` refuses to run alongside the analysis flags rather than
    printing both -- see `_check_combination`.
    """
    from caterva.compose.export import ExportRefused
    from caterva.compose.pipeline import compose

    claims = None
    try:
        read = None
        if args is not None:
            # The same reading `compose_report` makes, so an export of a
            # sentence carries the values its report carries (ADR 0181).
            read = read_description(args)
            description, subject = read.description, args.subject
        model = compose(description, subject=subject,
                        organism=getattr(args, "organism", None),
                        substrate=getattr(args, "substrate", None),
                        compounds=compounds_from(args) if args is not None else None)
        if read is not None and read.unapplied:
            model = replace(model, unapplied_subject=read.unapplied)
        if read is not None and read.choices:
            model = replace(model, choices=tuple(read.choices))
        if read is not None and read.name_refusal is not None:
            # An export has no report to carry the refusal, so it goes to
            # stderr, and the artefact carries placeholders, labelled so.
            model = replace(model, subject=read.enzyme_text, search_refused=read.refusal_note)
            print(read.refusal_note, file=sys.stderr)
        # Opened only once there is a model, as in `compose_report`: a
        # description that builds nothing writes no store (`_claims_run`).
        claims = _claims_run(args)
        if subject and args is not None:
            # An export that quietly carried placeholders while the report
            # beside it carried measurements would be the disagreement the
            # provenance machinery exists to prevent.
            if claims is not None:
                claims.start_recording()
            try:
                model, _, _ = _search_the_literature(model, args)
            finally:
                if claims is not None:
                    claims.stop_recording()
            # An export has no report: what was chosen for the user goes to
            # stderr, so the artefact on stdout stays parseable and the
            # choice is still said (ADR 0182).
            for line in choice_notes(model):
                print(f"Chose: {line}", file=sys.stderr)
        provenanced = provenanced_for_export(model)
        # The ids in the artefact are the ids in the bundle: one ClaimSet,
        # built from the same ProvenancedModel the artefact is written from.
        claim_ids = claims.finish(provenanced, model).by_identifier if claims is not None else None
        text, refused = export_texts(provenanced, (fmt,), claim_ids=claim_ids)[fmt]
        if refused is not None:
            raise ExportRefused(refused)
        print(text)
    except ExportRefused as exc:
        print(f"Not exported.\n\n{exc}", file=sys.stderr)
        return 3
    finally:
        if claims is not None:
            claims.close()
    return 0


def _claims_run(args: Any) -> Any:
    """The `--claims DIR` run to pin pages into and write the bundle from, or
    None without the flag.

    The evidence layer is imported here and nowhere else in this module, so
    a run without `--claims` imports nothing of it and behaves exactly as it
    did before claims existed (ADR 0179).

    CALLED ONLY ONCE A MODEL IS BUILT. Opening the run creates `DIR/store`,
    and it used to be opened before `compose`, so `caterva compose
    glycolysis --claims DIR` refused ("Not built.", exit 3) and left a
    store with no bundle beside it, which `caterva verify DIR` then
    rejected as not a bundle. A refused description now writes nothing:
    no model means no number for a claim to be about, and a bundle with a
    refused claim at its root would verify as ok while backing nothing. A
    run that does build a model writes a bundle whatever its search or its
    export then refuses, because that bundle is a true account of the model
    that was built.
    """
    directory = getattr(args, "claims", None)
    if not directory:
        return None
    from caterva.evidence.compose_claims import ClaimsRun

    return ClaimsRun(directory)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def _not_a_directory(directory: Any) -> Optional[str]:
    """Why `directory` cannot be made a directory, naming the path in the
    way, or None.

    `--claims DIR` makes DIR and every missing parent, so the request is
    malformed exactly when DIR, or the nearest of its parents that exists,
    is something other than a directory: `--claims notes.txt`, or
    `--claims notes.txt/run1`. Only what already exists is read; whether
    DIR can be written is the filesystem's to say when the run writes it.

    TWO THINGS `Path.exists()` ALONE MISSED. A symbolic link to nothing is
    an entry that is not a directory, and `exists()` follows the link and
    says no, so `--claims link` was let through and the store's mkdir then
    raised FileExistsError after the model was built: the traceback this
    check is here to prevent. (A link to a directory is a directory here,
    as it is to mkdir.) And a path that cannot even be looked at (an
    ancestor without search permission) made `exists()` raise
    PermissionError out of the argument check itself on Python 3.10 to
    3.12, where 3.13 says False and lets it through to the same failure
    later. The run could not have written there either, so both are refused
    here with the reason. `stat()` is asked directly, and raises the same
    on every Python this package supports, where `exists()` does not.
    """
    import stat
    from pathlib import Path

    path = Path(str(directory))
    for candidate in (path, *path.parents):
        try:
            mode = candidate.stat().st_mode
        except (FileNotFoundError, NotADirectoryError):
            # Nothing there (the walk goes on to the parent), or a parent
            # is a file (the walk reaches it). A link to nothing is the one
            # entry that is there while what it names is not.
            if candidate.is_symlink():
                return f"{candidate} is a symbolic link, and not to a directory"
            continue
        except OSError as exc:
            return f"{candidate} cannot be looked at ({exc.strerror or exc})"
        if stat.S_ISDIR(mode):
            return None
        if candidate.is_symlink():
            return f"{candidate} is a symbolic link, and not to a directory"
        return f"{candidate} is a file, not a directory"
    return None


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

    claims = getattr(args, "claims", None)
    if claims is not None and not str(claims).strip():
        parser.error("--claims needs a directory to write the bundle to.")
    blocked = _not_a_directory(claims) if claims is not None else None
    if blocked is not None:
        # Asked here, before anything runs, rather than when the store is
        # opened: that was a NotADirectoryError traceback (exit 1) after the
        # model was built, for a request that was malformed from the start.
        parser.error(
            f"--claims {claims}: {blocked}, so no bundle can be written under "
            "it. Name a directory, new or existing."
        )
    if claims is not None and args.antimony:
        # --antimony emits the compiled source with nothing about where its
        # numbers came from, so there is no artefact to carry a claim id and
        # no search whose pages a bundle would pin.
        parser.error(
            "--antimony emits the compiled source with no provenance on it, "
            "so there is nothing for --claims to attach an id to. Use "
            "--export antimony --claims DIR for the annotated source with "
            "its claim ids, or drop --claims."
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


def check_request(parser: argparse.ArgumentParser, args: Any) -> None:
    """Every check `main` makes after parsing, each through `parser.error`.

    A report needs a description (`main` prints the help instead, exit 2),
    a sample count of at least one, and a combination of flags that can all
    be honoured. One function so the studio refuses exactly what the
    terminal refuses, with the same words, before anything runs.
    """
    if not args.description:
        parser.error("the following arguments are required: description")
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


def main(argv: Optional[Sequence[str]] = None, prog: Optional[str] = None) -> int:
    parser = build_parser(prog) if prog else build_parser()
    args = parser.parse_args(argv)

    from caterva.compose.grammar import UnrecognisedShape, shapes

    if args.shapes:
        print("Shapes this builds:\n")
        for shape in shapes():
            print(f"  {shape}")
        print(
            "\nIt recognises a SHAPE, never a SUBJECT. 'three step "
            "phosphorylation cascade' builds; 'glycolysis' does not, and "
            "says why. An enzyme named exactly in a one-enzyme mechanism "
            "('Michaelis-Menten kinetics of human hexokinase on glucose') "
            "is searched for, and the report says how each word was read "
            "(ADR 0181)."
        )
        return 0

    if not args.description:
        parser.print_help()
        return 2

    check_request(parser, args)

    from caterva.compose.organisms import normalise_organism

    # "human" and "homo sapiens" searched for an organism BRENDA does not
    # spell that way, and reported the absence as a fact about the science.
    args.organism, organism_note = normalise_organism(args.organism)

    try:
        if args.export is not None:
            return _export(args.description, args.subject, args.export, args)

        if args.antimony:
            return _antimony(args)

        return compose_report(args, organism_note=organism_note).code

    except UnrecognisedShape as exc:
        # Exit 3, not 1: this is a REFUSAL with information in it, not a
        # crash, and a script should be able to tell the two apart.
        print(f"Not built.\n\n{exc}", file=sys.stderr)
        return 3


def _antimony(args: Any) -> int:
    """`--antimony`: the compiled source of the model the report would show,
    with the numbers the report would carry and a comment saying where each
    came from.

    It used to search nothing: `caterva compose "thrombin with a competitive
    inhibitor in human" --substrate ... --inhibitor argatroban --antimony`
    printed kcat = 100, Km = 0.1, Ki = 0.5 -- the motif library's
    placeholders, with no comment -- while the same command's report and
    `--export antimony` carried three cited BRENDA values (found
    2026-11-11). Source a reader pastes into a simulator must not be the
    one artefact that silently drops the measurements. So the description
    is read and searched exactly as for the report, the measured values are
    in the network compiled, and a comment block above it names each
    constant's origin; `--export antimony` remains the fully annotated form.
    """
    from caterva.compose.pipeline import compose
    from caterva.core.network import compile_to_antimony

    read = read_description(args)
    model = compose(read.description, subject=args.subject, organism=args.organism,
                    substrate=args.substrate, compounds=compounds_from(args))
    if read.choices:
        model = replace(model, choices=tuple(read.choices))
    note = None
    if args.subject:
        model, note, _ = _search_the_literature(model, args)
    elif read.refusal_note:
        note = read.refusal_note
    lines = ["# Compiled by caterva compose --antimony. Where each constant came from:"]
    for q in model.resolvable:
        m = (getattr(model, "measured", {}) or {}).get(q.parameter_id)
        if m is not None:
            where = f" ({m.organism})" if getattr(m, "organism", None) else ""
            lines.append(f"#   {q.parameter_id} = {m.value:g} {m.unit}: {m.citation}{where}")
        else:
            reason = (getattr(model, "not_found", {}) or {}).get(q.parameter_id) or (
                "no enzyme was named, so nothing was searched" if not args.subject else
                "not found by the search")
            lines.append(f"#   {q.parameter_id}: PLACEHOLDER, the motif library's illustrative "
                         f"value -- {' '.join(str(reason).split())[:240]}")
    for line in [*choice_notes(model), *([note] if note else [])]:
        lines.append("# " + " ".join(str(line).split()))
    print("\n".join(lines))
    print(compile_to_antimony(model.network))
    return 0


@dataclass
class ComposedReport:
    """What one report run of `caterva compose` produced and printed.

    `model` is the ComposedModel after the search, the one every section
    read; `dossier` the report.ModelDossier whose markdown was printed;
    `sections` the analysis sections with their records; `code` the exit
    code `main` returns.
    """

    model: Any
    dossier: Any
    precomputed: Any
    sections: "Sections"
    search_note: Optional[str]
    search_refused: bool
    code: int
    #: The policy's `NameNotResolved` when `--subject` was refused as a name
    #: that is not exactly one enzyme; None otherwise.
    name_refusal: Optional[Any] = None
    #: The `caterva.evidence.compose_claims.ClaimSet` written by `--claims`
    #: (its root, every claim, the identifier -> ref map the exports take);
    #: None without the flag.
    claims: Optional[Any] = None


def _quiet_stage(key: str, label: str, fraction: Optional[float] = None) -> None:
    """The terminal reports no stages: the report is what it prints."""


def compose_report(
    args: Any,
    *,
    organism_note: Optional[str] = None,
    stream: Any = None,
    err: Any = None,
    progress: Any = None,
) -> ComposedReport:
    """Compose, search, run the verdict's inputs, print the dossier and the
    sections, and return what was printed from.

    `args` is the parsed and checked namespace, with the organism already
    normalised (`organism_note` says how). `stream` and `err` default to
    the process's streams at call time. `progress`, when given, has
    `stage(key, label, fraction)` and `check_cancelled()`; each stage
    boundary reports and then checks, and the literature search reports
    each constant as it is looked up. UnrecognisedShape propagates, as it
    did from `main`, which turns it into exit 3.
    """
    out = sys.stdout if stream is None else stream
    err = sys.stderr if err is None else err

    def at(key: str, label: str, fraction: Optional[float] = None) -> None:
        if progress is not None:
            progress.check_cancelled()
            progress.stage(key, label, fraction)

    from caterva.compose.pipeline import compose
    from caterva.compose.report import dossier

    with contextlib.ExitStack() as closing:
        return _compose_report(
            args, closing, at, out, err, progress, organism_note=organism_note,
            compose=compose, dossier=dossier,
        )


def _compose_report(
    args: Any, closing: contextlib.ExitStack, at: Callable[..., None], out: Any, err: Any,
    progress: Any, *, organism_note: Optional[str], compose: Callable[..., Any],
    dossier: Callable[..., Any],
) -> ComposedReport:
    """`compose_report` after its imports. The `--claims` run is opened here,
    once `compose` has built a model (`_claims_run` says why not before),
    and entered on `closing`, which the caller exits whatever happens."""
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
    at("compose", "Composing the model from its description")
    # What the description names fills what no flag set, before anything is
    # composed or searched, so the search, the report and the studio's
    # result all read the same subject (ADR 0181).
    read = read_description(args, err=err)
    model = compose(read.description, subject=args.subject,
                    organism=args.organism, substrate=args.substrate,
                    compounds=compounds_from(args))
    if read.unapplied:
        model = replace(model, unapplied_subject=read.unapplied)
    if read.choices:
        model = replace(model, choices=tuple(read.choices))
    claims = _claims_run(args)
    if claims is not None:
        closing.enter_context(claims)
    search_note = None
    search_refused = False
    name_refusal = None
    if args.subject:
        # The search runs BEFORE the analyses, so every section below --
        # stability, sensitivity, the time course, the verdict -- reads
        # the literature's numbers rather than the library's (ADR 0178).
        # With --claims the pages it reads are pinned as it reads them,
        # and only for the length of the search.
        at("search", f"Searching the literature for {args.subject}")
        if claims is not None:
            claims.start_recording()
        try:
            found = search_literature(model, args, resolve=_announcing_resolver(progress))
        finally:
            if claims is not None:
                claims.stop_recording()
        model, search_note, search_refused = found.model, found.note, found.refused
        name_refusal = found.name_refusal
        if search_refused and not model.searched and model.search_refused is None:
            model = replace(model, search_refused=search_note)
    elif read.name_refusal is not None:
        # The description named an enzyme that is several. Refused exactly
        # as `--subject "lactate dehydrogenase"` is, with the candidates
        # named and the whole command that accepts one, never skipped: a
        # report saying "no enzyme was named" here would be false, and one
        # that picked would cite the wrong protein.
        search_note, search_refused, name_refusal = read.refusal_note, True, read.name_refusal
        model = replace(model, subject=read.enzyme_text, search_refused=search_note)
    claim_set = None
    if claims is not None:
        # Built now, from the same ProvenancedModel every export is written
        # from, so the ids in the bundle are the ids an export would carry;
        # printed after the analyses, where the report's last section goes.
        at("claims", f"Writing the claims bundle to {args.claims}")
        claim_set = claims.finish(provenanced_for_export(model), model)
    if args.validate or args.robustness is not None:
        at("precompute", "Running the checks the verdict reads: "
           + ", ".join(n for n, asked in (("validate", args.validate),
                                           ("robustness", args.robustness is not None))
                       if asked))
    precomputed = precompute_for_verdict(args, model)

    at("dossier", "Building the dossier: stability, time course, influence ranking, sweeps, verdict")
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
    # that says "Built by Caterva..." and then carries on for three more
    # pages has put its last word in the middle.
    if organism_note and args.subject:
        model.recognition.composition.note(organism_note)
    for line in read.notes:
        model.recognition.composition.note(line)
    # Every choice Caterva made for something the user did not name, in the
    # order it was made, before the search's own note (ADR 0182).
    for line in choice_notes(model):
        model.recognition.composition.note(line)
    if search_note:
        model.recognition.composition.note(search_note)
    print(report.markdown(footer=False), file=out)

    code, sections = run_analyses(
        args, report.model, precomputed, stream=out, err=err, progress=progress,
    )
    if search_refused and code == 0:
        # The reason is already in the report, beside what it is about.
        # This says only that a script should look (the same shape the
        # analysis refusals use).
        print(
            "1 refusal(s) in 1 section(s), each explained where it "
            "belongs in the report: the literature search.",
            file=err,
        )
        code = 3
    if claim_set is not None:
        # The last section before the footer, through `Sections` so the
        # studio gets the ClaimSet under the record it was printed from.
        # It moves no exit code: a claims bundle that says a row was not
        # found is a finding written down, not a run that failed.
        sections.start("claims")
        sections.keep("claims", claim_set)
        sections.write("Claims", claim_set.section(str(args.claims)))
    print("\n".join(report.footer_section()), file=out)
    return ComposedReport(
        model=report.model, dossier=report, precomputed=precomputed,
        sections=sections, search_note=search_note,
        search_refused=search_refused, code=code, name_refusal=name_refusal,
        claims=claim_set,
    )


def choice_notes(model: Any) -> List[str]:
    """The report's note for each choice the model carries (ADR 0182)."""
    return [choice.note() for choice in getattr(model, "choices", ()) or ()]


def _announcing_resolver(progress: Any) -> Optional[Callable[..., Any]]:
    """The resolver `compose_and_parameterise` would build, reporting each
    constant before it is looked up; None (that resolver, unwrapped) when
    nobody is listening."""
    if progress is None:
        return None
    from caterva.agents.scouts import brenda_resolver

    live = brenda_resolver()

    def resolve(request: Any, **kwargs: Any) -> Any:
        progress.stage(
            "search",
            f"Looking up {request.quantity} in BRENDA's {request.table} table "
            f"for EC {request.ec_number}",
            None,
        )
        return live(request, **kwargs)

    return resolve


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


def precompute_for_verdict(args: Any, model: Any) -> _Precomputed:
    out = _Precomputed()
    if args.validate:
        try:
            from caterva.compose.validate import validate

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


_precompute_for_verdict = precompute_for_verdict


def run_analyses(
    args: Any, model: Any, precomputed: Optional[_Precomputed] = None,
    *, stream: Any = None, err: Any = None, progress: Any = None,
) -> Tuple[int, Sections]:
    """Run every analysis asked for; return the exit code and the sections.

    Order is structure first, then the numbers, then the cross-checks --
    the same order the dossier itself uses, and the order in which a reader
    can discount what comes later. `--crnt` needs no parameter value at all,
    so a reader who distrusts the placeholders can stop after it and still
    have something true.
    """
    sections = Sections(stream)
    err = sys.stderr if err is None else err

    asked: List[Tuple[str, str, Callable[[], None]]] = []
    if args.crnt:
        asked.append(("crnt", "Reaction network structure",
                      lambda: _crnt_section(sections, model)))
    if args.scale:
        asked.append(("scale", "Physical scale", lambda: _scale_section(sections, model)))
    if args.predictions:
        asked.append(("predictions", "Predicted amounts",
                      lambda: _predictions_section(sections, model)))
    if args.reduction:
        asked.append(("reduction", "Timescale separation",
                      lambda: _reduction_section(sections, model)))
    if args.identifiability:
        asked.append(("identifiability", "Identifiability",
                      lambda: _identifiability_section(sections, model)))
    if args.design:
        asked.append(("design", "What to measure next",
                      lambda: _design_section(sections, model)))
    if args.robustness is not None:
        asked.append(("robustness", "Robustness to the placeholders", lambda: _robustness_section(
            sections, model, args.robustness,
            precomputed=precomputed.robustness_pair if precomputed else None,
        )))
    if args.knockout or args.overexpress or args.screen:
        asked.append(("perturbations", "Perturbations", lambda: _perturbation_section(
            sections, model, args.knockout, args.overexpress, args.screen,
            _answer_species(model, args.rank_against),
        )))
    if args.stochastic is not None:
        asked.append(("stochastic", "Stochastic simulation", lambda: _stochastic_section(
            sections, model, args.stochastic, args.stochastic_end,
            DEFAULT_SEED if args.stochastic_seed is None
            else args.stochastic_seed,
        )))
    if args.validate:
        asked.append(("validate", "Cross-checks", lambda: _validate_section(
            sections, model, args.rank_against,
            precomputed=precomputed.validation if precomputed else None,
        )))

    for done, (key, title, section) in enumerate(asked):
        if progress is not None:
            progress.check_cancelled()
            progress.stage(f"section:{key}", title, done / len(asked))
        sections.start(key)
        section()

    if not sections.refused:
        return 0, sections
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
        file=err,
    )
    return 3, sections


__all__ = [
    "ComposedReport", "SectionRecord", "Sections", "build_parser",
    "check_request", "compose_report", "export_texts", "main",
    "precompute_for_verdict", "provenanced_for_export", "run_analyses",
    "search_the_literature", "search_literature", "read_subject", "LiteratureSearch",
    "read_description", "DescriptionReading", "brenda_km_substrates",
]


def console_main() -> int:
    """Entry point of the `caterva-compose` console script."""
    return main(prog="caterva-compose")


if __name__ == "__main__":
    raise SystemExit(main())
