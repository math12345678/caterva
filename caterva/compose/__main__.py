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
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

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
        rule = recognise(description).rule
        compound = _only_cue_is_a_compound(description, reading)
        if (compound is None and rule not in SINGLE_ENZYME_RULES and reading.names_enzyme
                and getattr(reading, "inhibitor_text", None)):
            # "Na+/K+-ATPase inhibited by ouabain": the pump's name made the
            # grammar build primary active transport, the enzyme was then not
            # applied, and the run ended with three placeholders. A sentence
            # naming an enzyme and what inhibits it asks about the
            # inhibition (fourth round of the real-values review).
            return INHIBITED_ENZYME_SHAPE, "competitive_inhibition", (
                f"Your description named an enzyme ({reading.enzyme_text!r}) and an inhibitor "
                f"({reading.inhibitor_text!r}); the grammar also reads it as "
                f"{rule.replace('_', ' ')}, but with an enzyme and its inhibitor named the question is "
                "the inhibition, so it was built as Michaelis-Menten with a competitive inhibitor. To "
                f"build {rule.replace('_', ' ')}, describe it without naming the enzyme.")
        if compound is None:
            return description, rule, None
        return NAMED_ENZYME_SHAPE, "michaelis_menten", (
            f"Your description named an enzyme ({reading.enzyme_text!r}) and {compound!r}, which the "
            f"grammar also reads as a cue for {rule.replace('_', ' ')}; with an enzyme named and no other "
            f"word of a mechanism, {compound!r} was read as a compound the enzyme acts on, and the "
            "shape as Michaelis-Menten: one enzyme turning one substrate into one product. To build "
            f"{rule.replace('_', ' ')}, describe it without naming the enzyme, or name its mechanism.")
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


def _only_cue_is_a_compound(description: str, reading: Any) -> Optional[str]:
    """The compound word that alone made the grammar recognise a mechanism,
    when the description also names one enzyme; None otherwise.

    "pepsin with hemoglobin" was built as cooperative binding, because
    "hemoglobin" is the textbook cooperative protein, and pepsin was then
    "not applied": nothing was searched, though BRENDA has pepsin's
    hemoglobin Km and kcat rows (round-1 review of ADR 0182). A compound
    named beside an enzyme is what the enzyme acts on. Decided by masking:
    the description with the compound words replaced must recognise no
    shape at all, so a mechanism stated in other words ("hexokinase with
    glucose with a competitive inhibitor", "phosphofructokinase") stands.
    """
    from caterva.compose.grammar import UnrecognisedShape, _named_pathway_in, recognise

    if not getattr(reading, "ec", None) or not getattr(reading, "substrate_candidates", None):
        return None
    masked = description
    found = None
    for candidate in reading.substrate_candidates:
        low = candidate.lower()
        if any(stem in low for stem in _MECHANISM_STEMS) or not candidate.strip():
            continue
        pattern = re.compile(re.escape(candidate), re.IGNORECASE)
        if pattern.search(masked):
            masked = pattern.sub("the compound", masked)
            found = found or candidate
    if found is None or _named_pathway_in(masked.lower()) is not None:
        return None
    try:
        recognise(masked)
    except UnrecognisedShape as exc:
        return found if type(exc) is UnrecognisedShape else None
    return None


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
        _remember(args, enzyme_text=reading.enzyme_text)
        # "glucokinase from rat liver": the name's EC number has no rat
        # protein and no rat row, and rat glucokinase is HXK4 of EC 2.7.1.1,
        # whose rows name it (fifth round's review). Sets --subject and
        # --isoform when it applies.
        elsewhere = (_read_as_the_protein_filed_elsewhere(reading, args)
                     or _read_where_the_organism_has_rows(reading, args))
        out.notes.append(elsewhere or reading.enzyme_note())
        # ADR 0182: a symbol is one protein of its EC number ("HK2"); the
        # enzyme note says the constants come from rows that name it, so the
        # isoform is searched for unless --isoform set one.
        if getattr(reading, "isoform", None) and not getattr(args, "isoform", None):
            args.isoform = reading.isoform
            args.isoform_asked = DESCRIPTION_ASKED
        tissue = _tissue_isoform(args.subject, typed)
        if tissue and not getattr(args, "isoform", None):
            word, isoform, said = tissue
            args.isoform = isoform
            args.isoform_asked = DESCRIPTION_ASKED
            out.notes.append(f"Read {word!r} with EC {args.subject} as its {word} isoform {isoform}"
                             f"{said}; the constants are taken from rows naming it where there are any "
                             "(pass --isoform to change it).")
        elif tissue is None and _TISSUE_WORD.search(typed) and not getattr(args, "isoform", None):
            word = _TISSUE_WORD.search(typed).group(0)
            out.notes.append(f"The word {word!r} in your description was not used: Caterva has no "
                             f"tissue isoform of EC {args.subject} for it, so the constants may be any "
                             "tissue's; pass --isoform to choose one.")
        if getattr(reading, "mutations", None):
            # "IDH1 R132H": the constants come from the mutant's own rows,
            # never the wild type's (resolve_kinetic_value's `mutation`).
            args.mutation = "/".join(reading.mutations)
        elif getattr(reading, "isoform", None) and args.isoform != reading.isoform:
            # The enzyme note above says the constants come from rows naming
            # the description's isoform; the flag's isoform is the one used.
            out.notes.append(f"Your description names the isoform {reading.isoform}; --isoform {args.isoform} "
                             "was used instead, because a flag wins over the description.")
    elif reading.ambiguity is not None and (
            chosen := (_enzyme_the_data_singles_out(reading, args)
                       or _enzyme_the_organism_singles_out(reading, args))) is not None:
        # A name that is a few specific enzymes ("citrate synthase": the Si-
        # and Re- enzymes), of which BRENDA has measurements for one only
        # (ADR 0182). Taken, and said with the others named; a class word, a
        # symbol, a typo, or two candidates that both have rows stay refused.
        args.subject = chosen.chosen
        out.choices.append(chosen)
        # The tissue word reads the same here as for a name that is one
        # enzyme: "lactate dehydrogenase from rabbit muscle" chose EC
        # 1.1.1.27 by its rows and then left LDHA or LDHB open (S5-08).
        tissue = _tissue_isoform(args.subject, typed)
        if tissue and not getattr(args, "isoform", None):
            word, isoform, said = tissue
            args.isoform = isoform
            args.isoform_asked = DESCRIPTION_ASKED
            out.notes.append(f"Read {word!r} with EC {args.subject} as its {word} isoform {isoform}"
                             f"{said}; the constants are taken from rows naming it where there are any "
                             "(pass --isoform to change it).")
    elif reading.ambiguity is not None:
        from caterva.enzymes.policy import AMBIGUOUS, _refuse

        out.enzyme_text = reading.enzyme_text
        ambiguity, by_substrate = _ordered_by_the_substrate(
            reading.ambiguity, getattr(args, "substrate", None) or next(
                iter(getattr(reading, "substrate_candidates", ()) or ()), None),
            getattr(args, "organism", None) or reading.organism)
        out.name_refusal = _refuse(ambiguity, _rerun_command(typed), AMBIGUOUS)
        if by_substrate:
            from caterva.enzymes.policy import NameNotResolved

            r = out.name_refusal
            said = str(r).rstrip()
            stop = "" if said.endswith((".", "!", "?", ")")) else "."
            out.name_refusal = NameNotResolved(
                f"{said}{stop} {by_substrate}", r.candidates, r.named, r.kind, recommended=r.recommended,
                rerun=r.rerun, confirm_only=r.confirm_only)
        blocker = _no_candidate_in_the_organism(
            reading.ambiguity, getattr(args, "organism", None) or reading.organism)
        if blocker:
            from caterva.enzymes.policy import NameNotResolved

            r = out.name_refusal
            # The refusal can end on its example command, with no stop.
            said = str(r).rstrip()
            if blocker.startswith("None of"):
                # Its example ("--subject 2.3.3.1") would be refused again
                # for the organism, as the next sentence says: lead with the
                # flags that would run (third round's review, citrate
                # synthase in mouse).
                said = re.sub(r"Re-run with the one you meant, for example .*$",
                              "Name the one you meant with --subject, together with an --organism "
                              "that has its rows, as listed next.", said, flags=re.S)
            stop = "" if said.endswith((".", "!", "?", ")")) else "."
            out.name_refusal = NameNotResolved(
                f"{said}{stop} {blocker}", r.candidates, r.named, r.kind, recommended=r.recommended,
                rerun=r.rerun, confirm_only=r.confirm_only)
        # A near spelling or a bare abbreviation is not "several enzymes":
        # the refusal's own first line says what it is.
        plain = (getattr(reading.ambiguity, "suggestions_only", False)
                 or getattr(reading.ambiguity, "confirm_only", False)
                 or not getattr(reading.ambiguity, "candidates", ()))
        out.refusal_note = (f"No search was run: your description names {reading.enzyme_text!r}"
                            + (". " if plain else ", which is not one enzyme. ")
                            + f"{out.name_refusal}")
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
            # The search must not choose an organism in its place (below).
            args.organism_unread = reading.unread_organism[0]
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
        named_inhibitor = getattr(reading, "inhibitor_text", None) if reading is not None else None
        if named_inhibitor and not getattr(args, "inhibitor", None):
            # "Na+/K+-ATPase inhibited by ouabain" built a pump with no word
            # about ouabain (third round's review): an inhibitor the sentence
            # names is said to be unused, with why, never dropped.
            why = out.unapplied or "no enzyme was read from the description"
            out.notes.append(
                f"Read {named_inhibitor!r} in your description as an inhibitor; it is not in this "
                f"model and no Ki was looked up for it, because {why}. To model it, name the enzyme "
                "with --subject and describe a mechanism with an inhibition step (for example "
                "'competitive inhibition'), with --inhibitor naming it.")
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


#: At most this many of a refused name's candidates are read for rows in
#: the organism named (each is a parse of a BRENDA page).
CANDIDATES_READ_FOR_THE_ORGANISM = 5


def _ordered_by_the_substrate(ambiguity: Any, substrate: Optional[str],
                              organism: Optional[str]) -> Tuple[Any, Optional[str]]:
    """(ambiguity, sentence): a refused name's best-tied candidates in order
    of their rows for the substrate the description names, and a sentence
    with the counts; the ambiguity unchanged and None without a substrate,
    with a recommendation, or when the pages cannot be read.

    "michaelis menten for amylase with starch" was refused with beta-amylase
    first and "--subject 3.2.1.2" as the example, while alpha-amylase holds
    more than five times as many starch rows (third round's review)."""
    if not substrate or ambiguity is None or getattr(ambiguity, "recommended", None) is not None:
        return ambiguity, None
    if getattr(ambiguity, "class_word", False) or getattr(ambiguity, "suggestions_only", False):
        return ambiguity, None
    candidates = list(getattr(ambiguity, "candidates", ()) or ())
    if len(candidates) < 2:
        return ambiguity, None
    best = min(c.tier for c in candidates)
    tied = [c for c in candidates if c.tier == best]
    if len(tied) < 2 or len(tied) > CANDIDATES_READ_FOR_THE_ORGANISM:
        return ambiguity, None
    from caterva.compose import defaults

    counts: Dict[str, Dict[str, int]] = {}
    try:
        for c in tied:
            counts[c.ec] = {t: sum(1 for r in _usable(defaults.table_rows(c.ec, t, organism))
                                   if defaults._matches(r.compound, substrate))
                            for t in ("km", "kcat")}
    except Exception:  # noqa: BLE001 - unreadable pages: the finder's order stands
        return ambiguity, None
    if not any(sum(v.values()) for v in counts.values()):
        # No rows for it anywhere: the enzyme whose own name is of the
        # substrate comes first. "PTEN with PIP3" offered --subject 3.1.3.48
        # (protein-tyrosine phosphatase), and following it modelled PTP1B;
        # PIP3 is in the name of EC 3.1.3.67 (fifth round, R5V1-15).
        key = defaults._identity_key(substrate) or ""
        named = [c for c in tied if key and len(key) > 4
                 and key in (defaults._identity_key(c.name) or "")]
        if len(named) != 1:
            return ambiguity, None
        from dataclasses import replace as _replace

        try:
            ambiguity = _replace(ambiguity, candidates=tuple(
                named + [c for c in candidates if c not in named]))
        except (TypeError, ValueError):
            return ambiguity, None
        return ambiguity, (f"{substrate!r} in your description is in the name of EC {named[0].ec} "
                           f"({named[0].name}), so it is the example; BRENDA holds no Km or kcat "
                           f"row for {substrate} under any of these.")
    ordered = sorted(tied, key=lambda c: (-sum(counts[c.ec].values()), candidates.index(c)))
    rest = [c for c in candidates if c not in tied]
    from dataclasses import replace as _replace

    try:
        ambiguity = _replace(ambiguity, candidates=tuple(ordered + rest))
    except (TypeError, ValueError):
        return ambiguity, None
    where = f" in {organism}" if organism else ""
    listed = "; ".join(f"EC {c.ec} ({counts[c.ec]['km']} Km, {counts[c.ec]['kcat']} kcat)"
                       for c in ordered)
    return ambiguity, (f"BRENDA's rows for {substrate}{where} the search can use (spelled "
                       f"{substrate!r} or a stereo form of it; other spellings, variants and "
                       f"flagged rows not counted), which order these and the example: {listed}.")


def _no_candidate_in_the_organism(ambiguity: Any, organism: Optional[str]) -> Optional[str]:
    """For a name refused as several enzymes, with an organism named: a
    sentence saying which candidates have Km rows in that organism, or that
    none does and the organism is what is missing; None without an organism,
    when every candidate has rows, or when a page cannot be read.

    "citrate synthase --organism mouse" was refused with "Re-run with ...
    --subject 2.3.3.1", and that run was refused again: neither best match,
    nor EC 2.3.3.16, has a mouse Km row. The advice must lead to a run that
    can succeed (round-1 review of ADR 0182).
    """
    if not organism or ambiguity is None or getattr(ambiguity, "class_word", False) \
            or getattr(ambiguity, "suggestions_only", False):
        return None
    from caterva.compose import defaults
    from caterva.compose.organisms import normalise_organism

    where = normalise_organism(organism)[0] or organism
    candidates = [c for c in ambiguity.candidates
                  if getattr(c, "via", "name") in ("name", "ec")][:CANDIDATES_READ_FOR_THE_ORGANISM]
    if not candidates:
        return None
    try:
        rows = {c.ec: len(defaults.table_rows(c.ec, "km", where)) for c in candidates}
    except Exception:  # noqa: BLE001 - nothing is claimed about a page not read
        return None
    with_rows = [c.ec for c in candidates if rows[c.ec]]
    if len(with_rows) == len(candidates):
        return None
    if with_rows:
        return (f"Of these, the ones with Km rows in {where} are "
                + ", ".join(f"EC {ec} ({rows[ec]} row{'s' if rows[ec] != 1 else ''})" for ec in with_rows)
                + f"; the others have none there, so naming one of them would be refused for the organism.")
    first = candidates[0].ec
    try:
        organisms = _km_organisms_usable(first)
    except Exception:  # noqa: BLE001
        organisms = {}
    text = (f"None of " + ", ".join(f"EC {c.ec}" for c in candidates) + f" has a Km row in {where} in "
            "BRENDA, so naming one would be refused again: the organism, not the enzyme name, is what "
            "is missing.")
    if organisms:
        text += (f" Organisms with Km rows for EC {first}: {_counted(organisms)}. Re-run with --subject "
                 "and --organism set to one of them (Caterva never substitutes another organism's value "
                 "for the one you named, ADR 0024), or supply the constants yourself.")
    return text


def _enzyme_the_inhibitor_singles_out(reading: Any, ambiguity: Any) -> Optional[Any]:
    """For a name several enzymes go by ("HMG-CoA reductase": EC 1.1.1.34
    and 1.1.1.88) and an inhibitor named in the sentence, the one candidate
    whose BRENDA page has Ki rows for that inhibitor, in any organism, as a
    `Choice`; None when none or several have. "HMG-CoA reductase inhibited
    by atorvastatin" was refused, though only EC 1.1.1.34 has atorvastatin
    Ki rows (fourth round of the real-values review)."""
    inhibitor = getattr(reading, "inhibitor_text", None)
    if not inhibitor:
        return None
    from caterva.compose import defaults

    best = min(c.tier for c in ambiguity.candidates)
    tied = [c for c in ambiguity.candidates if c.tier == best][:defaults.ENZYME_CANDIDATES_CONSIDERED]
    if len(tied) < 2:
        return None
    rows: Dict[str, int] = {}
    for c in tied:
        try:
            rows[c.ec] = sum(1 for r in defaults.table_rows(c.ec, "ki", None)
                             if defaults._matches(r.compound, inhibitor) and not r.flagged)
        except Exception:  # noqa: BLE001 - one unreadable page and nothing is singled out
            return None
    with_rows = [ec for ec, n in rows.items() if n]
    if len(with_rows) != 1:
        return None
    ec = with_rows[0]
    names = {c.ec: c.name for c in tied}
    why = (f"your description names {reading.enzyme_text or reading.text!r}, a name "
           f"{len(tied)} enzymes go by; {names[ec]} is used because it is the only one of them with "
           f"Ki rows for {inhibitor}, the inhibitor you named ({rows[ec]} in BRENDA, any organism)")
    alternatives = tuple(defaults.Option(f"EC {e} ({names[e]})", {"ki": rows[e]}) for e in rows if e != ec)
    return defaults.Choice("enzyme", ec, why, alternatives, len(tied), {"ki": rows[ec]})


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
    if (ambiguity is not None and getattr(ambiguity, "confirm_only", False)
            and not getattr(ambiguity, "class_word", False) and ambiguity.candidates):
        by_inhibitor = _enzyme_the_inhibitor_singles_out(reading, ambiguity)
        if by_inhibitor is not None:
            return by_inhibitor
    if (ambiguity is None or getattr(ambiguity, "class_word", False)
            or getattr(ambiguity, "confirm_only", False)
            or getattr(ambiguity, "suggestions_only", False) or not ambiguity.candidates):
        return None
    best = min(c.tier for c in ambiguity.candidates)
    tied_candidates = [c for c in ambiguity.candidates if c.tier == best]
    tied = [(c.ec, c.name) for c in tied_candidates]
    from caterva.compose.defaults import ENZYME_CANDIDATES_CONSIDERED, choose_enzyme

    organism = getattr(args, "organism", None) or reading.organism
    plain = not any(getattr(c, "partial", False) or getattr(c, "abbreviation", False)
                    or getattr(c, "via", "name") not in ("name", "ec") for c in tied_candidates)
    if plain and len(tied) <= ENZYME_CANDIDATES_CONSIDERED:
        return choose_enzyme(reading.enzyme_text or reading.text, tied, organism)
    recommended = getattr(ambiguity, "recommended", None)
    if (organism and recommended is not None and recommended.ec in dict(tied)
            and getattr(recommended, "via", "name") == "name"
            and not getattr(recommended, "abbreviation", False)
            and not any(getattr(c, "abbreviation", False) or getattr(c, "via", "name") != "name"
                        for c in tied_candidates)):
        # One reading singled out twice over: the only one matched with a
        # protein of the organism given AND the only one with Km rows there,
        # however many readings the name has. "glyceraldehyde-3-phosphate
        # dehydrogenase from rabbit muscle" is a phrase inside seven accepted
        # names; EC 1.2.1.12 is both, and the run was refused although the
        # refusal said so (third round's review).
        chosen = choose_enzyme(reading.enzyme_text or reading.text, tied, organism, limit=None,
                               by_protein=recommended.ec)
        if chosen is not None:
            return chosen
    # A fragment of a longer name, a typo, an abbreviation or a class match
    # is not a reading of the name the user typed: never settled by rows
    # alone.
    return None


#: At most this many candidates listing a protein of the organism are read
#: for an enzyme the organism singles out; more is a family, not a few readings.
ORGANISM_PROTEIN_CANDIDATES = 4


def _enzyme_the_organism_singles_out(reading: Any, args: Any) -> Optional[Any]:
    """The `Choice` of one EC number for a name several enzymes match, when
    the organism named settles it twice over: exactly one candidate both
    lists a protein of that organism in the enzyme nomenclature and has Km
    rows for it in BRENDA, and no other candidate read has any Km row there.

    "soybean lipoxygenase with linoleic acid" listed 13 enzymes; two list a
    soybean protein and only EC 1.13.11.12 has soybean Km rows (10), and the
    refusal said exactly that before refusing. "thioredoxin reductase
    inhibited by auranofin in rat" is a phrase inside eight enzymes' names;
    only EC 1.8.1.9 lists rat proteins (TRXR1, TRXR2) and has rat Km rows
    (fifth round of the real-values review). Both were placeholders. A
    class word, a typo, an abbreviation, a symbol or a mnemonic is never
    settled this way: those are questions about what was meant, which no
    row answers. The note names the choice, the reason and the others.
    """
    ambiguity = getattr(reading, "ambiguity", None)
    organism = getattr(args, "organism", None) or getattr(reading, "organism", None)
    # A family name ("dihydroorotate dehydrogenase": EC 1.3.98.1 by another
    # name, and the family word of 1.3.5.2, 1.3.1.14, 1.3.1.15) is settled
    # the same way: in human only EC 1.3.5.2 lists a protein (DHODH) and
    # has Km rows, and the run was refused (fifth round, R5V1-03).
    if not organism or ambiguity is None or getattr(ambiguity, "confirm_only", False) \
            or (getattr(ambiguity, "class_word", False) and not getattr(ambiguity, "family", False)):
        return None
    from caterva.enzymes.finder import TIER_TYPO

    candidates = [c for c in getattr(ambiguity, "candidates", ()) or ()
                  if getattr(c, "via", "name") in ("name", "ec") and not getattr(c, "abbreviation", False)
                  and c.tier != TIER_TYPO]
    if len(candidates) < 2:
        return None
    with_protein = [c for c in candidates if c.has_organism_protein]
    if not with_protein or len(with_protein) > ORGANISM_PROTEIN_CANDIDATES:
        return None
    from caterva.compose import defaults
    from caterva.compose.organisms import normalise_organism

    where = normalise_organism(organism)[0] or organism
    others = [c for c in candidates if c not in with_protein][:CANDIDATES_READ_FOR_THE_ORGANISM]
    read = with_protein + others
    try:
        rows = {c.ec: len(_usable(defaults.table_rows(c.ec, "km", where))) for c in read}
    except Exception:  # noqa: BLE001 - one unreadable page and nothing is singled out
        return None
    with_rows = [c for c in read if rows[c.ec]]
    if len(with_rows) != 1 or with_rows[0] not in with_protein:
        return None
    best = with_rows[0]
    proteins = ", ".join(p.label for p in best.organism_proteins[:4]) or \
        f"{best.organism_protein_count} UniProt entries"
    listing = "; ".join(f"EC {c.ec}" for c in with_protein)
    unread = len(candidates) - len(read)
    how = (f"of the {len(candidates)} enzymes the name matches, "
           + (f"only it lists a protein of {where} in the enzyme nomenclature ({proteins})"
              if len(with_protein) == 1 else
              f"{len(with_protein)} list a protein of {where} in the enzyme nomenclature ({listing}), "
              f"and it is the only one of them with Km rows there")
           + f"; BRENDA holds {defaults._plural(rows[best.ec], 'Km row')} for it in {where}, and none for "
           + (f"the {len(read) - 1} other{'s' if len(read) != 2 else ''} read"
              + (f" ({unread} more, which list no {where} protein, were not read)" if unread else "")))
    text = reading.enzyme_text or reading.text
    why = (f"your description names {text!r}, which is not one enzyme; {best.name} is used because {how}")
    alternatives = tuple(defaults.Option(f"EC {c.ec} ({c.name})", {"km": rows[c.ec]})
                         for c in read if c is not best)[:defaults.ALTERNATIVES_NAMED]
    return defaults.Choice("enzyme", best.ec, why, alternatives, len(candidates), {"km": rows[best.ec]})


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


def _not_organism_words(ec: str, candidates: Tuple[str, ...], listed: Any = None) -> Tuple[str, ...]:
    """`candidates` less a lone word that is a word of an organism's name on
    the EC number's page: "influenza neuraminidase" listed 'influenza' as a
    word that is not a substrate (fifth round, R5V1-07). It names the source."""
    try:
        from caterva.compose.defaults import km_organisms

        words = {w.casefold() for o in km_organisms(ec) for w in o.split() if len(w) > 3}
    except Exception:  # noqa: BLE001
        return candidates
    # A compound BRENDA lists is kept whatever organism shares its word
    # ("glycine" and Glycine max).
    words -= {strict_key_of(n) for n in (listed or ())}
    words -= {str(n).casefold() for n in (listed or ())}
    return tuple(c for c in candidates
                 if not (len(c.split()) == 1 and c.strip().casefold() in words))


def _substrate_from(args: Any, reading: Any, out: DescriptionReading) -> bool:
    """Accept a word of the description as `args.substrate`, only against
    what BRENDA lists for the subject's EC number; a word BRENDA lists as an
    inhibitor (a Ki row) instead, with no inhibitor named, as
    `args.inhibitor`. True when an inhibitor was read."""
    from caterva.enzymes.sentence import match_substrate

    ec = reading.ec if reading.ec and args.subject == reading.ec else _flag_subject_ec(args)
    if ec is None:
        return False
    listed = _read_substrates(ec, args.organism)
    candidates = _not_organism_words(ec, tuple(reading.substrate_candidates), listed)
    shown = ", ".join(repr(c) for c in candidates[:4])
    where = f" for {args.organism}" if args.organism else ""
    if listed is None:
        out.notes.append(
            f"BRENDA's substrate list for EC {ec} could not be read, so no word of your description "
            f"({shown}) could be checked as the substrate, and none was taken.")
        # The search must not then choose a substrate in its place: a read
        # that failed here and succeeded a moment later in the chooser
        # replaced "mannose" with D-glucose under "No substrate was named"
        # (round-1 review of ADR 0182). `_choose_what_was_not_named` refuses.
        # A lone letter or numeral left over from an isozyme's name
        # ("lactate dehydrogenase A", "hexokinase II") is not a compound,
        # and must not stop the search on its own.
        _remember(args, substrate_unread=tuple(
            c for c in candidates if not _ISOZYME_CODE.fullmatch(c.strip())))
        return False
    # The mapping, not its keys: with the row counts, an abbreviation that
    # BRENDA lists under several spellings takes the best-measured one.
    match = match_substrate(candidates, listed)
    possible = getattr(reading, "possible_inhibitor_text", None)
    others = [c for c in ((possible,) if possible else ()) + tuple(candidates)
              if match.name is not None and strict_key_of(c) != strict_key_of(match.typed)]
    if others and not getattr(args, "inhibitor", None):
        # Another compound beside the substrate that was read ("with X", "in
        # the presence of X", "dihydrofolate and methotrexate"): it is the
        # inhibitor when BRENDA lists Ki rows for it under this EC number,
        # and nothing otherwise (the reader only flags it: sentence.py). A
        # "with X" the reader flagged is tried first.
        inhibitor = _inhibitor_from(ec, args.organism, others, prefix_set_aside=True)
        if inhibitor is not None:
            typed, name = inhibitor
            args.inhibitor = name
            args.substrate = match.name
            how = (" (its stereo or anomer prefix set aside, the only substrate BRENDA lists under "
                   "that name)" if match.prefix_set_aside else "")
            out.notes.append(
                f"Read {match.typed!r} in your description as the substrate {match.name}, which "
                f"BRENDA lists for EC {ec}{where}{how}, and {typed!r} as the inhibitor {name}, "
                f"which BRENDA lists Ki rows for under EC {ec}{where}.")
            return True
    if match.name is None and not match.rivals and not getattr(args, "inhibitor", None):
        inhibitor = _inhibitor_from(ec, args.organism, candidates)
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
        elsewhere = _substrate_measured_elsewhere(ec, args.organism, candidates)
        if elsewhere is not None:
            typed, name, counts = elsewhere
            called = "" if strict_key_of(typed) == strict_key_of(name) else f" {name},"
            out.notes.append(
                f"{typed!r} in your description is{called} a substrate BRENDA lists Km rows for under "
                f"EC {ec}, but in other organisms only, none in {args.organism}: {_counted(counts)}. "
                f"So it was not taken as the substrate, and the model is not of it. To model it, "
                f"re-run with --organism set to one of them (each organism's own measurement, never "
                f"substituted for yours, ADR 0024), or supply its constants yourself.")
        else:
            listed = _listed_without_rows(ec, candidates)
            if listed:
                # "CYP3A4 metabolising midazolam": BRENDA lists midazolam's
                # reaction for EC 1.14.14.1 (Substrates/Products) and holds no
                # Km or kcat row for it; "not a substrate BRENDA lists" was
                # false (fourth round of the real-values review).
                out.notes.append(
                    f"{listed!r} in your description is a substrate BRENDA lists for EC {ec} (in its "
                    f"Substrates/Products table), but BRENDA holds no Km or kcat row for it"
                    f"{where}, so it could not be the model's substrate: the model is not of it. "
                    "Supply its constants yourself, or pass --substrate with a compound that has rows.")
            else:
                out.notes.append(
                    f"No word of your description ({shown}) is a substrate BRENDA lists for EC "
                    f"{ec}{where}, so none was taken as the substrate, and if you typed one it was not "
                    "used: the model is not of it. Pass --substrate with BRENDA's own name for the "
                    "compound you meant.")
        # The choice's note must not then open "No substrate was named":
        # the user may well have named one BRENDA does not list.
        _remember(args, substrate_instead=(
            f"No substrate BRENDA lists Km rows for under EC {ec}"
            + (f" in {args.organism}" if args.organism else "")
            + f" was named (no word of your description, {shown}, is one)"))
    return False


def _listed_without_rows(ec: str, candidates: Sequence[str]) -> Optional[str]:
    """The first word of the description BRENDA's Substrates/Products or
    Natural Substrates tables list for `ec` (a reaction it has, with no
    kinetic row for it here), or None."""
    from caterva.compose import defaults

    try:
        natural, reaction = defaults._reaction_compounds(ec)
    except Exception:  # noqa: BLE001 - unreadable: say nothing more
        return None
    listed = natural | reaction
    for word in candidates or ():
        if word and defaults._in(word, defaults._group_key(word), listed):
            return word
    return None


def strict_key_of(name: Optional[str]) -> str:
    """A compound name with case and spacing set aside."""
    return " ".join((name or "").split()).casefold()


def _remember(args: Any, **fields: Any) -> None:
    """Carry what the reader learned to the search's choice (`args` is the
    one object both see); silently nothing for an args that refuses it."""
    for name, value in fields.items():
        try:
            setattr(args, name, value)
        except (AttributeError, TypeError):  # pragma: no cover - a frozen args
            pass


def _inhibitor_from(ec: str, organism: Optional[str], candidates: Sequence[str],
                    *, prefix_set_aside: bool = False) -> Optional[Tuple[str, str]]:
    """(the word as typed, BRENDA's name) for the first candidate that is,
    case aside, a compound BRENDA lists Ki rows for under `ec` (in
    `organism`); None when none is, or the page cannot be read. Whole
    names only, never a word inside a longer compound's name: exactly, case
    aside ("methotrexate"), or with `prefix_set_aside` by the substrate's
    rule (`match_substrate`: "glucose 6-phosphate" for the one listed
    "D-glucose 6-phosphate"). The looser rule is for a compound named
    BESIDE a substrate already read, which can only be the inhibitor; a
    word that was the only candidate ("hexokinase on glucose 6-phosphate")
    may be a substrate BRENDA does not list, and is not relabelled."""
    from caterva.enzymes.sentence import match_substrate

    try:
        from caterva.compose.defaults import ki_compounds

        listed = ki_compounds(ec, organism)
    except Exception:  # noqa: BLE001 - not reading one is not reading one
        return None
    by_key = {strict_key_of(n): n for n in listed}
    for typed in candidates:
        name = by_key.get(strict_key_of(typed))
        if name is None and prefix_set_aside:
            name = match_substrate((typed,), list(listed)).name
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
        if getattr(args, "isoform_asked", None) is None:
            args.isoform_asked = NAME_ASKED
    if organism_applied:
        args.organism = resolution.organism
    from caterva.enzymes.policy import split_mutation
    _, mutations = split_mutation(" ".join(str(subject).split()))
    if mutations and not getattr(args, "mutation", None):
        # The note says the constants come from the mutant's rows only.
        args.mutation = "/".join(mutations)
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


#: Reads of BRENDA's substrate list made before a word of the description
#: is given up on, and the pause between them, in seconds: a timeout is
#: usually transient, and a word lost to one is a model of something else.
SUBSTRATE_LIST_READS = 3
SUBSTRATE_LIST_PAUSE = 2.0


#: A word that is an isozyme's code, not a compound: one letter or digit,
#: or a Roman numeral ("A", "2", "II", "IV").
_ISOZYME_CODE = re.compile(r"[A-Za-z0-9]|[IVXivx]{1,4}")


def _substrate_measured_elsewhere(
    ec: str, organism: Optional[str], candidates: Sequence[str],
) -> Optional[Tuple[str, str, Dict[str, int]]]:
    """(the word typed, BRENDA's name for it, organism -> usable Km rows) when
    a word of the description is a substrate BRENDA lists Km rows for under
    `ec` in other organisms but not in `organism`; None otherwise, or when
    that cannot be read.

    "pepsin with hemoglobin --organism pig" said "No word of your
    description ('hemoglobin') is a substrate BRENDA lists for EC 3.4.23.1
    for Sus scrofa" and to pass --substrate with BRENDA's own name. BRENDA
    lists "Hemoglobin + H2O" as pig pepsin's natural substrate, and its
    hemoglobin Km rows are fish pepsins' (Saurida micropectoralis, 3 rows):
    the word was BRENDA's own name, and what is missing is the organism
    (review of ADR 0182's F14 fix). Variant rows are not counted
    (`_usable`), so an organism is offered only where a re-run would use it.
    """
    if not organism or not candidates:
        return None
    from caterva.compose import defaults
    from caterva.enzymes.sentence import match_substrate

    everywhere = _read_substrates(ec, None)
    if not everywhere:
        return None
    match = match_substrate(candidates, everywhere)
    if match.name is None:
        return None
    key = defaults._search_key(match.name)
    try:
        rows = defaults.table_rows(ec, "km", None)
    except Exception:  # noqa: BLE001 - the sentence then stays as it was
        return None
    counts: Dict[str, int] = {}
    for row in _usable(r for r in rows if defaults._search_key(r.compound) == key):
        if row.organism and row.organism != organism:
            counts[row.organism] = counts.get(row.organism, 0) + 1
    if not counts:
        return None
    return match.typed, match.name, counts


def _read_substrates(ec: str, organism: Optional[str]) -> Optional[Dict[str, int]]:
    """`brenda_km_substrates`, read again after a pause when it fails."""
    import time

    for attempt in range(SUBSTRATE_LIST_READS):
        listed = brenda_km_substrates(ec, organism)
        if listed is not None:
            return listed
        if attempt + 1 < SUBSTRATE_LIST_READS:
            time.sleep(SUBSTRATE_LIST_PAUSE)
    return None


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


def _protein_under_another_ec(ec: str, organism: str, text: Optional[str]) -> Optional[Tuple[Any, Any, list, list]]:
    """(candidate, protein, usable Km rows, rows naming the protein) for the
    enzyme words `text` when they name a protein of `organism` that the
    nomenclature files under ANOTHER EC number than `ec`; None otherwise,
    or when that EC number's page cannot be read.

    The words name the protein when UniProt gives it them as a name
    ("Glucokinase" for human GCK), or when they are the isozyme's name in
    the words papers use ("glucokinase" is HXK4, hexokinase IV, in rat,
    whose UniProt names this build does not hold). A word inside a longer
    name ("ADP-dependent glucokinase") does not count. A row names the
    protein by its commentary's words or by its own UniProt accession: human
    GCK's wild-type K0.5 row (ref 739603) names it only by P35557, and the
    refusal said none of the 54 rows named GCK (fifth round's review).
    """
    if not text:
        return None
    from caterva.enzymes import finder
    from caterva.enzymes.index import load_index
    from caterva.compose import defaults
    from caterva.bind.core import read_isoform, same_isoform

    key = finder.strict_key(text)
    try:
        ranked = finder._search(text, finder.organism_code(organism), load_index())
    except Exception:  # noqa: BLE001
        return None
    for candidate in ranked:
        if candidate.ec == ec or candidate.via != "name" or candidate.tier == finder.TIER_TYPO:
            continue
        for protein in candidate.organism_proteins:
            if not (any(finder.strict_key(n) == key for n in protein.names)
                    or same_isoform(protein.label, text)):
                continue
            try:
                # Counted as the search would use them: a variant's row is
                # withheld (ADR 0029), so it is no way out.
                rows = _usable(defaults.table_rows(candidate.ec, "km", organism))
            except Exception:  # noqa: BLE001
                return None
            accession = getattr(protein, "accession", None)

            def names_it(row: Any) -> bool:
                said = read_isoform(row.conditions or "")
                if said and (same_isoform(said, protein.label) or same_isoform(said, text)):
                    return True
                cells = [c.strip() for c in (row.uniprot or "").split(",") if c.strip()]
                if len(cells) != 1:
                    return False
                return cells[0] == accession or defaults._accession_says(cells[0], protein.label) is True

            return candidate, protein, rows, [r for r in rows if names_it(r)]
    return None


def _filed_under_another_ec(ec: str, organism: str, text: Optional[str]) -> Optional[str]:
    """When the enzyme words name a protein of `organism` that the
    nomenclature files under ANOTHER EC number, the sentence that says so and
    gives the command; None otherwise.

    "glucokinase in human" was refused for EC 2.7.1.2, which has no human Km
    row, and pointed at Zymomonas mobilis, while human glucokinase is GCK,
    listed under EC 2.7.1.1 (hexokinase), whose human rows include GCK's own.
    Only a protein whose UniProt names include the words exactly counts (GCK
    is "Glucokinase"); a word inside a longer name ("ADP-dependent
    glucokinase") does not. When rows do name it, compose reads that EC
    number itself (`_read_as_the_protein_filed_elsewhere`); this sentence is
    for a run that did not.
    """
    found = _protein_under_another_ec(ec, organism, text)
    if found is None:
        return None
    candidate, protein, rows, naming = found
    if not rows:
        return None
    said = (f"In {organism}, {text!r} is the protein {protein.label}, which the nomenclature files "
            f"under EC {candidate.ec} ({candidate.name}); BRENDA has {len(rows)} Km "
            f"row{'s' if len(rows) != 1 else ''} for EC {candidate.ec} in {organism}")
    if naming:
        return (said + f", {len(naming)} of which name{'s' if len(naming) == 1 else ''} {protein.label} "
                f"(in their words or by UniProt accession). To model it, re-run with --subject "
                f"{candidate.ec} --isoform {protein.label} (the constants are then taken from rows that "
                f"name {protein.label} where there are any, and the report says which rows name no "
                "isozyme).")
    # No row names the protein: the run the advice leads to carries a
    # row of whichever protein of that EC number it measured.
    # "glucokinase in mouse" was sent to EC 2.7.1.1 --isoform Gck and
    # came back GROUNDED with Km 0.42 mM from a mouse row naming no
    # isozyme: a low-Km hexokinase's value, not glucokinase's (S0.5
    # near 8 mM). Said before the command, not left to a flag after it.
    return (said + f", and none of them names {protein.label}, in its words or by UniProt accession, so "
            f"each may have measured another protein of EC {candidate.ec}. To model it from those rows, "
            f"re-run with --subject {candidate.ec} --isoform {protein.label} and read the papers of the "
            "rows it carries (the report flags each row that names no isozyme; it cannot say whose it "
            f"is), or supply {protein.label}'s constants yourself.")


def _read_as_the_protein_filed_elsewhere(reading: Any, args: Any) -> Optional[str]:
    """For an enzyme name read as an EC number that lists no protein of the
    organism and has no Km row there, while the words name a protein of that
    organism filed under another EC number whose BRENDA rows name it: that
    EC number and protein are used (`args.subject`, `args.isoform`), and
    the sentence saying so is returned; None otherwise.

    "glucokinase from rat liver" was read as EC 2.7.1.2, the bacterial
    glucokinase, which lists no rat protein, and refused with advice to
    model Zymomonas mobilis, while BRENDA's rat rows for hexokinase IV
    (glucokinase, HXK4) are under EC 2.7.1.1: 7.7 mM for D-glucose (ref
    641070, "adult glucokinase"). The cofactor-sibling rule for glutamate
    dehydrogenase (EC 1.4.1.2 to 1.4.1.3, fourth round) is the same idea;
    this one rests on rows that name the protein (fifth round's review).
    """
    ec = reading.ec
    organism = getattr(args, "organism", None) or reading.organism
    if not ec or not organism or getattr(args, "isoform", None) or getattr(reading, "isoform", None):
        return None
    from caterva.compose import defaults
    from caterva.compose.organisms import normalise_organism

    where = normalise_organism(organism)[0] or organism
    try:
        from caterva.enzymes import finder
        from caterva.enzymes.index import load_index

        code = finder.organism_code(where)
        _, count = load_index().proteins_in(ec, code)
        if code is None or count:
            return None
        if _usable(defaults.table_rows(ec, "km", where)):
            return None
    except Exception:  # noqa: BLE001 - unreadable: the reading stands
        return None
    found = _protein_under_another_ec(ec, where, reading.enzyme_text)
    if found is None:
        return None
    other, protein, rows, naming = found
    if not naming:
        return None
    args.subject = other.ec
    args.isoform = protein.label
    args.isoform_asked = DESCRIPTION_ASKED
    name = reading.enzyme_name or ec
    return (f"Read {reading.enzyme_text!r} in your description as EC {other.ec} ({other.name}), the "
            f"{where} protein {protein.label}: EC {ec} ({name}), whose name it is, lists no {where} "
            f"protein in the enzyme nomenclature and BRENDA holds no Km row for it there, while the "
            f"nomenclature files {where} {protein.label} under EC {other.ec}, where "
            f"{defaults._plural(len(naming), 'Km row')} of {len(rows)} name it. The constants are taken "
            f"from rows that name {protein.label} where there are any; pass --subject {ec} to model "
            f"EC {ec} instead.")


def _read_where_the_organism_has_rows(reading: Any, args: Any) -> Optional[str]:
    """For an enzyme name whose EC number has no Km row in the organism
    named, while exactly one other EC number the same name is a name of has
    such rows, and the nomenclature lists no protein of that organism (it
    indexes few organisms): that EC number is used (`args.subject`), and the
    sentence saying so is returned; None otherwise.

    "lactase from Kluyveromyces lactis", the industrial lactase, was read
    as EC 3.2.1.108 (mammalian lactase-phlorizin hydrolase) and refused with
    advice to model sheep, rat or human lactase, while "lactase" is also a
    name of EC 3.2.1.23 (beta-galactosidase), where BRENDA holds K. lactis
    lactose Km rows (19.8 mM, ref 655098) (fifth round, R5V1-04).
    """
    ec = reading.ec
    organism = getattr(args, "organism", None) or reading.organism
    text = getattr(reading, "enzyme_text", None)
    if not ec or not organism or not text or getattr(args, "isoform", None) \
            or getattr(reading, "isoform", None):
        return None
    from caterva.compose import defaults
    from caterva.compose.organisms import normalise_organism

    where = normalise_organism(organism)[0] or organism
    try:
        from caterva.enzymes import finder
        from caterva.enzymes.index import load_index

        code = finder.organism_code(where)
        if code is not None:
            return None  # an indexed organism: `_read_as_the_protein_filed_elsewhere`'s case
        if _usable(defaults.table_rows(ec, "km", where)):
            return None
        ranked = [c for c in finder._search(text, None, load_index())
                  if c.ec != ec and c.via == "name" and c.tier != finder.TIER_TYPO
                  and not getattr(c, "abbreviation", False)][:CANDIDATES_READ_FOR_THE_ORGANISM]
        rows = {c.ec: len(_usable(defaults.table_rows(c.ec, "km", where))) for c in ranked}
    except Exception:  # noqa: BLE001 - unreadable: the reading stands
        return None
    with_rows = [c for c in ranked if rows.get(c.ec)]
    if len(with_rows) != 1:
        return None
    other = with_rows[0]
    args.subject = other.ec
    _remember(args, enzyme_text=text)
    name = reading.enzyme_name or ec
    return (f"Read {text!r} in your description as EC {other.ec} ({other.name}): EC {ec} ({name}), "
            f"whose name it is, has no Km row in {where} on BRENDA, while {text!r} is also a name of "
            f"EC {other.ec}, which has {defaults._plural(rows[other.ec], 'Km row')} there. Pass "
            f"--subject {ec} to model EC {ec} instead.")


def _km_organisms_usable(ec: str) -> Dict[str, int]:
    """`defaults.km_organisms(ec)` less the rows of a protein variant
    (`_usable`): an organism offered as the way out of a refusal must hold a
    Km row the search would use."""
    from caterva.compose import defaults

    counts = dict(defaults.km_organisms(ec))
    for row in defaults.table_rows(ec, "km", None):
        if row.organism in counts and _a_variant(row):
            counts[row.organism] -= 1
    return {o: n for o, n in counts.items() if n > 0}


def _organism_has_no_rows(ec: str, organism: str, enzyme_text: Optional[str] = None) -> Optional[str]:
    """The refusal for an organism the user NAMED that has no Km row for
    `ec` at all, listing the organisms that do; None when it has rows, or
    when the page cannot be read (the substrate choice then says that).

    "glucose-6-phosphate dehydrogenase in S. cerevisiae" was refused with
    "Re-run with --substrate NAME" -- and a user who did would have got
    placeholders again, because BRENDA's page for EC 1.1.1.49 has no yeast
    Km row at all. The organism is the blocker, so the advice names it.
    Another organism is never substituted for the one named (ADR 0024).
    """
    from caterva.compose.defaults import table_rows

    try:
        by_organism = _km_organisms_usable(ec)
        mine = len(table_rows(ec, "km", organism))
    except Exception:  # noqa: BLE001
        return None
    if mine:
        return None
    ranked = sorted(by_organism, key=lambda o: (-by_organism[o], o))
    listed = "; ".join(f"{o} ({by_organism[o]} row{'s' if by_organism[o] != 1 else ''})"
                       for o in ranked[:SUBSTRATES_NAMED])
    more = f" and {len(ranked) - SUBSTRATES_NAMED} more" if len(ranked) > SUBSTRATES_NAMED else ""
    sibling = _filed_under_another_ec(ec, organism, enzyme_text)
    if not ranked:
        return (f"No search was run: BRENDA's page for EC {ec} holds no Km row for any organism, "
                "so there is no measured substrate to model. "
                + (f"{sibling} Otherwise supply" if sibling else "Supply") + " the constants yourself.")
    text = (f"No search was run: BRENDA holds no Km row for EC {ec} in {organism}, so no substrate "
            f"could be chosen and no constant of this model can be measured there. The organism, "
            f"not the substrate, is what is missing: naming a substrate would not help. ")
    if sibling:
        # The protein the user means is under another EC number: that is
        # the first remedy, before any other organism.
        return (text + f"{sibling} Organisms with Km rows for EC {ec} itself: {listed}{more} (Caterva "
                "never substitutes another organism's value for the one you named, ADR 0024).")
    return (text + f"Organisms "
            f"with Km rows for EC {ec}: {listed}{more}. Re-run with --organism set to one of them "
            f"(Caterva never substitutes another organism's value for the one you named, ADR 0024), "
            f"or supply the constants yourself.")


def _inhibition_mode(model: Any, args: Any) -> Optional[str]:
    """The inhibition mode the search will ask a Ki for (the motif's; none
    under --any-mode), so an inhibitor is chosen by the rows it will take."""
    if getattr(args, "any_mode", False):
        return None
    from caterva.compose.row_scope import INHIBITION_TABLES, MODE_OF_MOTIF

    for q in getattr(model, "resolvable", ()) or ():
        if q.table in INHIBITION_TABLES and MODE_OF_MOTIF.get(q.motif_name):
            return MODE_OF_MOTIF[q.motif_name]
    return None


def _species_of_genus(ec: str, typed: str) -> Optional[Any]:
    """The `Choice` of the best-measured species of the genus `typed`
    names, when it is one word that is the genus of organisms with Km rows
    for `ec`; None otherwise.

    "glucose isomerase from Streptomyces" was refused as naming no organism
    Caterva reads, and the advice listed every organism on the page
    (Actinoplanes, Thermus ...) rather than the Streptomyces species (fifth
    round, R5V1-13). A genus is a choice among its species, made as ADR 0182
    makes one for an organism not named: the most rows, said, with the others.
    """
    word = (typed or "").strip()
    if not re.fullmatch(r"[A-Z][a-z]{2,}", word):
        return None
    from caterva.compose import defaults

    try:
        counts = _km_organisms_usable(ec)
    except Exception:  # noqa: BLE001
        return None
    species = {o: n for o, n in counts.items()
               if o.split()[0] == word and len(o.split()) >= 2 and n > 0}
    if not species:
        return None
    ranked = sorted(species, key=lambda o: (-species[o], o.endswith(" sp."), o))
    best = ranked[0]
    others = ranked[1:]
    why = (f"of the {len(species)} species of {word} with Km rows under EC {ec}, it has the most "
           f"({defaults._plural(species[best], 'Km row')})")
    alternatives = tuple(defaults.Option(o, {"km": species[o]}) for o in others[:defaults.ALTERNATIVES_NAMED])
    return defaults.Choice("organism", best, why, alternatives, len(species), {"km": species[best]},
                           instead=f"Your description names the genus {word!r}, not a species")


def _unread_organism_refusal(ec: str, typed: str) -> str:
    """The refusal for a description that named the enzyme's source in words
    Caterva does not read as an organism ("beta-glucosidase from almond"
    before almond was in the table). The search used to go on and choose an
    organism as though none had been named -- Homo sapiens, GROUNDED, for
    sweet-almond beta-glucosidase (names-stream review, 2026-11-12). The
    person named one, so another is never put in its place (ADR 0024); the
    organisms with Km rows are listed for the re-run.
    """
    from caterva.compose.defaults import km_organisms

    try:
        by_organism = km_organisms(ec)
    except Exception:  # noqa: BLE001
        by_organism = {}
    ranked = sorted(by_organism, key=lambda o: (-by_organism[o], o))
    listed = "; ".join(f"{o} ({by_organism[o]} row{'s' if by_organism[o] != 1 else ''})"
                       for o in ranked[:SUBSTRATES_NAMED])
    more = f" and {len(ranked) - SUBSTRATES_NAMED} more" if len(ranked) > SUBSTRATES_NAMED else ""
    where = (f" Organisms with Km rows for EC {ec}, most rows first: {listed}{more}." if ranked else "")
    return (f"No search was run: your description names {typed!r} as the enzyme's source, which is not an "
            f"organism name Caterva reads, and another organism is never put in place of the one you named "
            f"(ADR 0024): a value measured in it would be cited for {typed!r}. Re-run with --organism and the "
            f"binomial BRENDA files that source under.{where}")


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

    unread = getattr(args, "organism_unread", None)
    if not args.organism and isinstance(unread, str) and unread:
        genus = _species_of_genus(ec, unread)
        if genus is None:
            return replace(model, choices=tuple(choices)), _unread_organism_refusal(ec, unread)
        args.organism = genus.chosen
        _remember(args, organism_chosen=True)
        choices.append(genus)

    if not args.organism and (needs_substrate or needs_inhibitor or args.substrate):
        chosen = defaults.choose_organism(
            ec, substrate=args.substrate or None, inhibitor=inhibitor, needs=tables or ("km",),
            isoform=getattr(args, "isoform", None) or None)
        if chosen is not None:
            args.organism = chosen.chosen
            _remember(args, organism_chosen=True)
            choices.append(chosen)
    elif args.organism and needs_substrate:
        text = getattr(args, "enzyme_text", None)
        if not isinstance(text, str) and getattr(args, "subject", None) and _flag_subject_ec(args) == ec \
                and not re.fullmatch(r"[\d.\-n]+", str(args.subject).strip()):
            text = args.subject
        blocked = _organism_has_no_rows(ec, args.organism,
                                        text if isinstance(text, str) else None)
        if blocked is not None:
            return replace(model, choices=tuple(choices)), blocked

    isoform = getattr(args, "isoform", None) or None
    unread = getattr(args, "substrate_unread", None)
    if needs_substrate and isinstance(unread, tuple) and unread:
        # The sentence named words that may be the substrate, and BRENDA's
        # list could not be read to check them: choosing another substrate
        # now would replace the user's word with Caterva's pick.
        shown = ", ".join(repr(c) for c in unread[:4])
        return replace(model, choices=tuple(choices)), (
            f"No search was run: your description names what may be the substrate ({shown}), and "
            f"BRENDA's substrate list for EC {ec} could not be read to check it, so it could not be "
            "taken, and no other substrate is chosen in its place. Re-run when BRENDA answers, or "
            "pass --substrate with BRENDA's name for the compound.")

    if needs_substrate:
        among = getattr(args, "substrate_among", None)
        among = tuple(among) if isinstance(among, (tuple, list)) and among else None
        try:
            mutation = getattr(args, "mutation", None) or None
            chosen = defaults.choose_substrate(ec, args.organism, needs_kcat="kcat" in tables,
                                               strict=True, among=among, isoform=isoform,
                                               mutation=mutation)
            if chosen is None and among:
                # None of the matched names has a row here after all: the
                # whole list, said as such by the `instead` clause.
                chosen = defaults.choose_substrate(ec, args.organism, needs_kcat="kcat" in tables,
                                                   strict=True, isoform=isoform, mutation=mutation)
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
            if unreadable:
                # A page that did not answer is an outage, not an absence: the
                # remedy is a re-run, and --substrate only skips the choice
                # (the search still reads the page). Fourth round's review.
                return replace(model, choices=tuple(choices)), (
                    f"No search was run: this model needs {missing} from BRENDA, and no substrate "
                    f"was named; BRENDA's page for EC {ec} could not be read just now (the site did "
                    f"not answer in time), so none could be chosen. This is not a finding about the "
                    f"enzyme: re-run when BRENDA answers. Passing --substrate NAME only skips the "
                    f"choice; the search still reads the same page.")
            if mutation:
                # The mutant has no row, not the organism: EGFR T790M and
                # carbonic anhydrase II H64A in human were told BRENDA had no
                # human Km row for the EC, and to name a substrate, which
                # changed nothing (fifth round, R5V1-16).
                try:
                    wild = defaults.choose_substrate(ec, args.organism, needs_kcat="kcat" in tables,
                                                     strict=True, isoform=isoform)
                except Exception:  # noqa: BLE001
                    wild = None
                if wild is not None:
                    return replace(model, choices=tuple(choices)), (
                        f"No search was run: no Km row{where} under EC {ec} measures the mutant "
                        f"{mutation}, and naming a substrate will not change that: BRENDA's rows"
                        f"{where} are of the wild type or other variants. To model the wild-type "
                        f"enzyme instead, re-run without {mutation} in the description (Caterva "
                        f"would then use {wild.chosen}), or supply the mutant's constants yourself.")
            reason = f"BRENDA lists no substrate with a Km row for EC {ec}{where} to choose"
            return replace(model, choices=tuple(choices)), (
                f"No search was run: this model needs {missing} from BRENDA, and those tables "
                f"are per-substrate; no substrate was named and {reason}. Re-run with "
                f"--substrate NAME.")
        args.substrate = chosen.chosen
        choices.append(chosen)

    if needs_inhibitor:
        chosen = defaults.choose_inhibitor(ec, args.organism, args.substrate, isoform=isoform,
                                           mode=_inhibition_mode(model, args))
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
        model = replace(model, isoform=args.isoform, isoform_asked=_isoform_asked(args))
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
            mutation=getattr(args, "mutation", None) or None,
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
            isoform_asked=_isoform_asked(args),
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
    measured = _pairing_said_after_windows(dict(chosen.measured))
    # A value whose BRENDA row is another compound's -- the resolver finds
    # a name inside longer names -- is withheld, never carried under the
    # name the user typed or Caterva chose (`_neighbours_withheld`).
    neighbours = _neighbours_withheld(model, measured, ec)
    for identifier in neighbours:
        measured.pop(identifier, None)
    # A value carried for a named protein (SIRT1, HER2, KPC-2) whose BRENDA
    # row is another protein's -- by its UniProt accession, or, for a name
    # filed under an EC number of many proteins, by not naming it -- is
    # withheld likewise (`protein_rows`).
    if getattr(args, "isoform", None):
        from caterva.compose.protein_rows import other_protein_withheld

        try:
            other_protein = other_protein_withheld(model, measured, ec, args.isoform,
                                                   getattr(args, "organism", None))
        except Exception:  # noqa: BLE001 - unverifiable is not wrong
            other_protein = {}
        for identifier in other_protein:
            measured.pop(identifier, None)
        neighbours = {**neighbours, **other_protein}
    # Constants the search returned a value for, or found rows for, and did
    # not use. They end up placeholders like the ones the search found
    # nothing for, and must not be described as found-nothing.
    withheld: Dict[str, str] = {**chosen.withheld, **neighbours}
    not_found.update(withheld)
    # Each reason said for the organism searched, not BRENDA's whole page.
    said = _said_for_the_organism(
        replace(model, organism=args.organism, compounds=compounds_from(args)),
        {k: v for k, v in not_found.items() if k not in skipped}, ec, args.organism)
    not_found.update(said)
    not_found.update(_no_inhibitor_would_fill(model, skipped, ec, args.organism))
    if getattr(args, "organism_chosen", False) is True:
        not_found.update(_organism_chosen_said(not_found))
        said = {k: not_found[k] for k in said}
    withheld.update({k: said[k] for k in withheld if k in said})
    far = _far_from_other_organisms(model, measured, ec, args.organism)
    selection_notes = list(chosen.notes) + far + _filed_under_other_names(model, measured, ec)
    cautions = tuple((note[1:note.index("`", 1)], note.split(": ", 1)[1]) for note in far
                     if note.startswith("`") and ": " in note)
    if getattr(args, "isoform", None):
        from caterva.enzymes.isozyme import describe_isoform

        reading = describe_isoform(ec, args.organism, args.isoform)
        if reading and _isoform_asked(args) != "--isoform":
            # The flag was not passed: say where the label came from (fifth
            # round's review, V5-5).
            reading = reading.replace(f"--isoform {args.isoform!r}",
                                      f"{args.isoform!r} in {_isoform_asked(args)}", 1)
        if reading:
            selection_notes = [reading, *selection_notes]
    failures = [
        run for branch in getattr(search, "branches", ())
        for record in getattr(branch.build.run, "rounds", ())
        for run in getattr(record, "ran", ())
        if getattr(run, "failed", False)
    ]
    # A constant whose own scout failed (a timeout, a 503) was not searched.
    # Without a reason of its own the report printed "searched the km table
    # and found nothing" and advised another organism -- a false statement
    # of absence for rows BRENDA holds, which a plain re-run filled
    # (round-3 review: queries 10 and 24).
    for run in failures:
        quantity = str(getattr(run, "agent", "")).partition("scout:")[2]
        if quantity and quantity not in measured and quantity not in not_found:
            not_found[quantity] = _not_searched(str(run.failure))
    sourced = model.with_measured(measured, not_found=not_found)
    if cautions:
        sourced = replace(sourced, cautions=cautions)
    if not measured and failures and not any(
            not str(v).startswith("not searched") for v in not_found.values()):
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
            why = f"the literature search could not run: {_service_failed(text)}"
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


def _organism_chosen_said(reasons: Mapping[str, Any]) -> Dict[str, Any]:
    """`reasons` with the scout's "raised by your own request" said of an
    organism Caterva CHOSE (`_choose_what_was_not_named`). The scout sees
    the chosen organism as the input's, so "xanthine oxidase inhibited by
    febuxostat" read "organism must be Bos taurus, raised by your own
    request" when no organism was typed. An automatic choice is never
    reported as the user's (ADR 0182)."""
    return {k: (v.replace(", raised by your own request)",
                          ", the organism Caterva chose because your description named none)")
                if isinstance(v, str) else v)
            for k, v in reasons.items()}


#: The clause `adapters.name_miss_clause` writes: the compound's name has
#: no row, and the names BRENDA lists in any organism.
_NAME_MISS = re.compile(r" -- BRENDA has no (?:Ki |Km |kcat )?row for that (?:substrate|inhibitor) "
                        r"name;.*?set to the one you meant", re.S)

#: How many names a placeholder's reason lists before "and N more".
NAMES_LISTED = 8


def _counted(counts: Mapping[str, int], shown: int = NAMES_LISTED,
             first: Optional[Iterable[str]] = None) -> str:
    """"A (3 rows); B (1 row) and 2 more", by rows; the names in `first`
    (organisms of the asked one's class) before the rest."""
    near = set(first or ())
    ranked = sorted(counts, key=lambda k: (k not in near, -counts[k], k))
    text = "; ".join(f"{k} ({counts[k]} row{'s' if counts[k] != 1 else ''})" for k in ranked[:shown])
    return text + (f" and {len(ranked) - shown} more" if len(ranked) > shown else "")


def _said_for_the_organism(model: Any, reasons: Mapping[str, str], ec: Optional[str],
                           organism: Optional[str]) -> Dict[str, str]:
    """`reasons` with each "BRENDA has no row for that name" clause replaced
    by what BRENDA holds IN THE ORGANISM SEARCHED (round-1 review of ADR 0182).

    The resolver lists the names the table carries in every organism, so a
    human kcat placeholder for CYP3A4 listed Bacillus fatty acids under
    "Re-run with --substrate" while BRENDA has no human Turnover row on that
    page at all: no substrate could fill it, and the organism was the
    blocker. Here, per constant:

    * the organism has no row of that table under the EC number at all: said,
      as the organism being what is missing, with the organisms that have
      rows (and those with rows for the compound named, first);
    * it has rows, none for the compound named: the compounds it has rows
      for THERE, with the flag that names one (--inhibitor for a Ki, which
      BRENDA files under the inhibitor), and whether the compound has rows
      in another organism (labelled as that organism's, never substituted,
      ADR 0024) or in none under that name.

    A clause is left as the resolver wrote it when no organism was searched
    or the page cannot be read.
    """
    if not ec or not organism or not reasons:
        return dict(reasons)
    from caterva.compose.organisms import normalise_organism

    where = normalise_organism(organism)[0] or organism
    by_id = {q.parameter_id: q for q in getattr(model, "resolvable", ())}
    out = dict(reasons)
    isoform = getattr(model, "isoform", None)
    for name, reason in reasons.items():
        q = by_id.get(name)
        if q is None or q.table not in ("km", "kcat", "ki"):
            continue
        if isoform and "measured another isoform" in reason:
            try:
                out[name] = reason + _measured_on_the_isoform(ec, q.table, where, isoform,
                                                              "inhibitor" if q.table == "ki" else "substrate")
            except Exception:  # noqa: BLE001 - the resolver's reason stands
                pass
            continue
        if _AVAILABLE_IN.search(reason):
            try:
                rewritten = _available_elsewhere(ec, q.table, model.compound_for(q), reason,
                                                 isoform=isoform, asked=where)
            except Exception:  # noqa: BLE001 - the resolver's reason stands
                rewritten = None
            if rewritten:
                out[name] = rewritten
            if q.table == "ki":
                try:
                    here = _inhibitors_here(ec, where, model, model.compound_for(q))
                except Exception:  # noqa: BLE001 - the reason stands
                    here = ""
                if here:
                    out[name] = out.get(name, reason) + here
            if q.table == "kcat":
                under = _kcat_under_a_cosubstrate(ec, where, model.compound_for(q))
                if under:
                    out[name] = out.get(name, reason) + under
            continue
        if not _NAME_MISS.search(reason):
            continue
        # A substrate named instead changes every constant looked up under
        # it: the advice says which of the substrates offered fill them all.
        also = () if q.table == "ki" else tuple(sorted({
            other.table for other in by_id.values()
            if other is not q and other.table in ("km", "kcat") and other.table != q.table
            and model.compound_for(other) == model.compound_for(q)}))
        try:
            clause = _what_the_organism_holds(ec, q.table, model.compound_for(q), where,
                                              "inhibitor" if q.table == "ki" else "substrate",
                                              isoform=isoform, also=also)
        except Exception:  # noqa: BLE001 - the resolver's clause stands
            continue
        out[name] = _NAME_MISS.sub(lambda _m: clause, reason, count=1)
    return out


def _inhibitors_here(ec: str, organism: str, model: Any, compound: Optional[str]) -> str:
    """For a Ki whose inhibitor has rows only in other organisms: the
    inhibitors the organism searched DOES have Ki rows for, counted the way
    the inhibitor choice counts them (rows the search can use for this
    model's mode and isoform), so naming one leads to a run that fills it.
    Human AChE with donepezil sent the reader to Mus musculus only, though
    human Ki rows exist for other inhibitors (fifth round's review, A4-08).
    "" when the organism has none."""
    from caterva.compose import defaults
    from caterva.compose.row_scope import INHIBITION_TABLES, MODE_OF_MOTIF

    mode = next((MODE_OF_MOTIF[q.motif_name] for q in getattr(model, "resolvable", ()) or ()
                 if q.table in INHIBITION_TABLES and MODE_OF_MOTIF.get(q.motif_name)), None)
    choice = defaults.choose_inhibitor(ec, organism, getattr(model, "substrate", None),
                                       isoform=getattr(model, "isoform", None), mode=mode)
    if choice is None:
        return ""
    counted: Dict[str, int] = {}
    if choice.rows.get("ki"):
        counted[choice.chosen] = choice.rows["ki"]
    for option in choice.alternatives:
        if option.rows.get("ki"):
            counted[option.name] = option.rows["ki"]
    if compound:
        counted = {k: v for k, v in counted.items()
                   if defaults._search_key(k) != defaults._search_key(compound)}
    if not counted:
        return ""
    return (f". In {organism}, the inhibitors with Ki rows the search can use"
            + (f" for a {mode} model" if mode else "") + ", best measured first: "
            + "; ".join(f"{k} ({v} row{'s' if v != 1 else ''})" for k, v in counted.items())
            + "; re-run with "
            "--inhibitor set to one of them to model that inhibitor in this organism instead")


#: What asked for the isoform when no --isoform flag was passed, for the
#: notes that said "as --isoform asked" of an isoform read from the sentence
#: (DPP4, CA2, IMPDH2, NOS2: fifth round's review, V5-5).
DESCRIPTION_ASKED = "your description"
NAME_ASKED = "the enzyme name"


def _isoform_asked(args: Any) -> str:
    """"--isoform" when the flag set the isoform, else what did."""
    asked = getattr(args, "isoform_asked", None)
    return asked if isinstance(asked, str) and asked else "--isoform"


def _no_inhibitor_would_fill(model: Any, skipped: Mapping[str, str], ec: Optional[str],
                             organism: Optional[str]) -> Dict[str, str]:
    """For a Ki left unlooked-up because no inhibitor was named, in an
    organism with no Ki row the search can use under the EC number: the
    reason says the organism is what is missing and lists the organisms that
    do have Ki rows. It said "Name it with --inhibitor NAME", and no name
    could fill it: rat acetyl-CoA carboxylase has no Ki row for any inhibitor
    (fifth round's review, N11). {} otherwise, and when a page cannot be read.
    """
    if not ec or not organism or not skipped:
        return {}
    from caterva.compose.organisms import normalise_organism

    where = normalise_organism(organism)[0] or organism
    by_id = {q.parameter_id: q for q in getattr(model, "resolvable", ())}
    out: Dict[str, str] = {}
    for name, reason in skipped.items():
        q = by_id.get(name)
        if q is None or q.table != "ki" or "--inhibitor" not in reason:
            continue
        try:
            from caterva.compose import defaults

            if _usable(defaults.table_rows(ec, "ki", where)):
                continue
            whole = tuple(t for t in ("km", "kcat") if any(o.table == t for o in by_id.values()))
            clause = _what_the_organism_holds(ec, "ki", None, where, "inhibitor",
                                              isoform=getattr(model, "isoform", None), whole=whole)
        except Exception:  # noqa: BLE001 - the reason stands as it was
            continue
        out[name] = ("not looked up: no inhibitor was named"
                     + clause.replace("naming another inhibitor", "naming an inhibitor"))
    return out


def _kcat_under_a_cosubstrate(ec: str, organism: str, compound: Optional[str]) -> str:
    """A clause for a kcat placeholder "measured only in another organism"
    when the organism DOES hold kcat rows, filed under a cosubstrate: yeast
    glutathione reductase's 900 1/s (native Glr1, ref 689967, the Km's own
    paper) is filed under NADPH, and the advice sent the reader to another
    organism (third round's review). Offered, labelled as a turnover measured
    varying the cosubstrate, never carried as the substrate's. "" otherwise."""
    from caterva.compose import defaults

    try:
        rows = _usable(defaults.table_rows(ec, "kcat", organism))
    except Exception:  # noqa: BLE001
        return ""
    if not rows or any(compound and defaults._matches(r.compound, compound) for r in rows):
        return ""
    under: Dict[str, int] = {}
    for r in rows:
        if defaults.is_cofactor(r.compound):
            under[r.compound] = under.get(r.compound, 0) + 1
    if not under or len(under) < len({r.compound for r in rows}):
        return ""
    first = max(under, key=under.get)
    return (f". {organism} does have kcat rows under EC {ec}, filed under the cosubstrate "
            f"{_counted(under)}: a turnover number measured varying the cosubstrate, usually in the "
            f"same assay, which is not carried as {compound}'s; re-run with --substrate {first} to "
            "model it, or supply this constant from those rows yourself")


def _measured_on_the_isoform(ec: str, table: str, organism: str, isoform: str, role: str) -> str:
    """The compounds whose rows in `organism` name `isoform`, for a constant
    withheld because every row for the compound modelled measured another
    isoform: "CYP3A4 metabolising midazolam" was given 7-ethoxyresorufin,
    whose human rows are CYP1A1's, and the advice was "re-run with
    --organism", while human rows naming CYP3A4 exist for other substrates."""
    from caterva.bind.core import read_isoform, same_isoform
    from caterva.compose import defaults

    label = defaults.TABLE_NAMES[table]
    named: Dict[str, int] = {}
    try:
        from caterva.compose.protein_rows import strict_alias

        curated = {str(a) for a in (strict_alias(ec, isoform) or {}).get("accessions", [])}
    except Exception:  # noqa: BLE001 - no curated accessions: words and the index
        curated = set()
    shared_only: Dict[str, set] = {}
    for row in _usable(defaults.table_rows(ec, table, organism)):
        cells = {a.strip() for a in str(row.uniprot or "").split(",") if a.strip()}
        if curated and curated & cells:
            if len(cells) > 1 and not read_isoform(row.conditions):
                # A row listing several proteins and naming none is not
                # taken by the search: TEM-1's nitrocefin rows (ref 696728,
                # "P13661, P62593") were offered as filling the Km, and the
                # run they led to withheld them (fifth round, R5B-01).
                shared_only.setdefault(str(row.reference_id or "?"), set()).add(row.compound)
                continue
            named[row.compound] = named.get(row.compound, 0) + 1
            continue
        # By its words, or by its own UniProt cell: TEM-1's E. coli rows name
        # it only as P62593 (nitrocefin, cephalothin), and the advice said no
        # row named it (third round's review).
        if same_isoform(read_isoform(row.conditions), isoform) or defaults._accession_says(
                row.uniprot, isoform):
            named[row.compound] = named.get(row.compound, 0) + 1
    if not named:
        # Where the isoform's rows of this table ARE: its orthologue in
        # another organism, named in words (HK2's kcat: mouse Hk2, ref
        # 758915), labelled as that organism's and never substituted.
        # The orthologue by its UniProt cell first (the enzyme index files
        # mouse O08528 as Hk2); words alone only when no cell names it, since
        # "HXK2" in Entamoeba is that amoeba's second hexokinase.
        elsewhere: Dict[str, int] = {}
        by_words: Dict[str, int] = {}
        try:
            from caterva.checkout import literature_module

            row_form = literature_module("row_form")
            for row in _usable(defaults.table_rows(ec, table, None)):
                if not row.organism or row.organism == organism:
                    continue
                cell = row_form.isoforms_of_accessions(ec, row.uniprot) if row.uniprot else ()
                if any(same_isoform(label, isoform) for label in cell):
                    elsewhere[row.organism] = elsewhere.get(row.organism, 0) + 1
                elif same_isoform(read_isoform(row.conditions), isoform):
                    by_words[row.organism] = by_words.get(row.organism, 0) + 1
        except Exception:  # noqa: BLE001 - the clause stands without it
            elsewhere, by_words = {}, {}
        elsewhere = elsewhere or by_words
        clause = (f". BRENDA has no {label} row naming {isoform} under EC {ec} in {organism} for any "
                  f"{role}")
        if shared_only:
            refs = sorted(shared_only)
            clause += (f" that the search takes: the rows of BRENDA ref {', '.join(refs[:3])} ("
                       + ", ".join(sorted({c for r in refs for c in shared_only[r]})[:3])
                       + f") list {isoform}'s accession among other proteins' and name none of them, "
                         "so whose constant each is cannot be told; supply it yourself, reading "
                         "that paper")
        if elsewhere:
            clause += (f"; rows naming it are in {_counted(elsewhere)} (another organism's "
                       f"protein, never substituted: re-run with --organism set to one of them "
                       f"to model it there)")
        return clause
    shared = sorted({r.reference_id for r in defaults.table_rows(ec, table, organism)
                     if r.compound in named and r.reference_id
                     and len([c for c in (r.uniprot or "").split(",") if c.strip()]) > 1})
    tail = ""
    if shared:
        # TEM-1: nitrocefin's rows list both OXA-1's and TEM-1's accessions
        # (ref 696728), and naming it fills this constant only (fourth round).
        tail = (f" (the rows of BRENDA ref {', '.join(shared[:3])} list several proteins' accessions, "
                f"{isoform}'s among them, so which one they measured is not certain)")
    return (f". The {role}s with {label} rows naming {isoform} under EC {ec} in {organism}: "
            f"{_counted(named)}{tail}. Re-run with --{role} set to one of them; that fills this "
            f"{label} only, and the model's other constants are looked up for it afresh")


def _a_variant(row: Any) -> bool:
    """Whether a BRENDA row measured a sequence variant ("mutant N580A"),
    which the search withholds (ADR 0029), by the classifier the search
    itself uses. An isozyme is not a variant here: it is wild-type in its
    own right, and the isoform rule decides about it."""
    if getattr(row, "variant", False) and not getattr(row, "isozyme", False):
        return True  # the parser's own verdict (defaults._Row), which the chooser counts by
    from caterva.checkout import literature_module

    verdict = literature_module("protein_variant").classify(getattr(row, "conditions", "") or None)
    return verdict.status == "variant" and verdict.kind != "isozyme"


def _usable(rows: Iterable[Any]) -> List[Any]:
    """The rows a search could carry: every row but a variant's, and never
    one the parser flagged as implausible (the chooser's `defaults._usable`
    sets those aside too, so advice and choice count the same rows).

    "PTGS2 with arachidonic acid in human" had no human kcat row, and the
    advice was "re-run with --organism set to one of them: Mus musculus (3
    rows)". All three mouse rows measured the N580A mutant, so that run
    came back with placeholders too. A row is only offered as a way out
    when the search would use it (round-1 review of ADR 0182)."""
    return [row for row in rows if not getattr(row, "flagged", False) and not _a_variant(row)]


def _rows_for_the_compound_here(ec: str, table: str, key: str, organism: str) -> bool:
    """Whether another of the Km/kcat/Ki tables holds a usable row for the
    compound (by `defaults._key`) in `organism`: the compound is then one
    this model carries there, not only a name."""
    from caterva.compose import defaults

    for other in ("km", "kcat", "ki"):
        if other != table and any(defaults._search_key(r.compound) == key
                                  for r in _usable(defaults.table_rows(ec, other, organism))):
            return True
    return False


def _what_the_organism_holds(ec: str, table: str, compound: Optional[str], organism: str,
                             role: str, isoform: Optional[str] = None,
                             also: Sequence[str] = (), whole: Sequence[str] = ()) -> str:
    """The clause for `_said_for_the_organism`, from BRENDA's own rows.
    Only rows the search would use are counted or offered (`_usable`).

    With an isoform asked for, an organism is offered as the way out only
    for rows that name that isoform: "CYP3A4 ... in human" has no human kcat
    row on EC 1.14.14.1, and the organisms that have one are Bacillus and
    Streptomyces, whose rows measured CYP102 enzymes; re-running there is
    refused again by the isoform rule, so it is not offered.

    The compounds offered in the organism are counted the same way: with an
    isoform asked for, a row that names ANOTHER isoform is not counted (the
    isoform rule refuses it). `also` is the model's other tables looked up
    under the same substrate: "Renilla-type luciferase with coelenterazine"
    had no kcat row for coelenterazine, and the advice offered "Luciferin",
    which has no Km row there, so following it would have emptied the Km in
    place of the kcat. The substrates that fill every one are said first.
    """
    from caterva.compose import defaults

    label = defaults.TABLE_NAMES[table]
    flag = f"--{role}"
    key = defaults._search_key(compound) if compound else None
    every_row = defaults.table_rows(ec, table, None)
    here_row = defaults.table_rows(ec, table, organism)
    every = _usable(every_row)
    here = _usable(here_row)
    elsewhere: Dict[str, int] = {}
    if key:
        for row in every:
            if row.organism and row.organism != organism and defaults._search_key(row.compound) == key:
                elsewhere[row.organism] = elsewhere.get(row.organism, 0) + 1
    named = f" for {compound}" if compound else ""
    if not here:
        organisms: Dict[str, int] = {}
        for row in every:
            if row.organism:
                organisms[row.organism] = organisms.get(row.organism, 0) + 1
        if organisms and isoform:
            from caterva.bind.core import read_isoform, same_isoform

            organisms = {}
            for row in every:
                if row.organism and same_isoform(read_isoform(row.conditions), isoform):
                    organisms[row.organism] = organisms.get(row.organism, 0) + 1
            if not organisms:
                return (f" -- BRENDA holds no {label} row for EC {ec} in {organism} at all, and no row "
                        f"of that table in any organism names {isoform} (BRENDA's rows for that EC number "
                        f"measured other proteins): neither another {role} nor a different species "
                        "would fill it, so supply it yourself")
        if not organisms:
            if every_row:
                return (f" -- every {label} row BRENDA holds for EC {ec}, in any organism, measured a "
                        "protein variant, and variants are withheld (ADR 0029): neither another "
                        f"{role} nor a different species would fill it, so supply it yourself")
            return f" -- BRENDA holds no {label} row for EC {ec} in any organism: supply it yourself"
        anywhere = key and any(defaults._search_key(r.compound) == key
                               or defaults._matches(r.compound, compound) for r in every_row)
        if key and not anywhere and role == "inhibitor":
            # "glycogen phosphorylase inhibited by caffeine": no organism has
            # a caffeine Ki, so "the organism is what is missing" sent the
            # reader to rabbit, where it is missing too (fourth round).
            which = f"naming {isoform}" if isoform else "that are not of a variant"
            return (f" -- BRENDA holds no {label} row for {compound} under EC {ec} in any organism "
                    f"(under that name; a compound is filed under the name its paper used), so the "
                    f"{role}, not only the organism, is what is missing: another organism would not "
                    f"fill it for {compound}. {organism} has no {label} row for EC {ec} at all; "
                    f"organisms with {label} rows for other {role}s {which}: {_counted(organisms)}. "
                    f"Supply it yourself, or re-run with --organism and {flag} set to a compound one "
                    "of them has rows for")
        if here_row:
            text = (f" -- BRENDA's {label} rows for EC {ec} in {organism} all measured a protein variant, "
                    f"and variants are withheld (ADR 0029), so naming another {role} would not fill it: "
                    "the organism is what is missing")
        else:
            text = (f" -- BRENDA holds no {label} row for EC {ec} in {organism} at all, so naming "
                    f"another {role} would not fill it: the organism is what is missing")
        if elsewhere:
            text += (f". {label} rows{named} are in: {_counted(elsewhere)}, each that organism's "
                     "measurement, never substituted for yours (ADR 0024)")
        elif key and _rows_for_the_compound_here(ec, table, key, organism):
            # "cathepsin D with hemoglobin": the Km is hemoglobin's, and no
            # organism has a kcat row for hemoglobin, so the organisms below
            # would give a model of another substrate. Said, not left implied.
            text += (f". No organism has a {label} row for {compound} under EC {ec}, so in any organism "
                     f"listed next the model would be of another {role}, not {compound}")
        which = f"naming {isoform}" if isoform else "that are not of a variant"
        listed = _counted(organisms)
        if whole:
            # The organisms where the model's other tables have rows too come
            # first: rat acetyl-CoA carboxylase's Ki sent the reader to E.
            # coli, which has no kcat row, ahead of Homo sapiens, which has
            # all three (fifth round's review, N11).
            # One compound with a row in every one of those tables, as the
            # substrate choice needs: yeast has Km rows and kcat rows under
            # EC 6.4.1.2, for different compounds, and its kcat stayed a
            # placeholder. A cosubstrate (ATP) is set aside by the choice,
            # so it does not count.
            have = [{(r.organism, defaults._search_key(r.compound))
                     for r in _usable(defaults.table_rows(ec, t, None))
                     if r.organism and not defaults.is_cofactor(r.compound)} for t in whole]
            pairs = set.intersection(*have) if have else set()
            full = {o: n for o, n in organisms.items() if any(org == o for org, _ in pairs)}
            rest = {o: n for o, n in organisms.items() if o not in full}
            if full and rest:
                tables = " and ".join(defaults.TABLE_NAMES[t] for t in whole)
                listed = (f"{_counted(full)} (with {tables} rows there too, so the whole model is "
                          f"measured); then {_counted(rest)}")
        text += (f". Organisms with {label} rows for EC {ec} {which}: "
                 f"{listed}. Re-run with --organism set to one of them to model that "
                 "organism, or supply it yourself")
        return text
    if isoform:
        from caterva.bind.core import read_isoform, same_isoform

        def _not_another_isoform(rows: Iterable[Any]) -> List[Any]:
            # Its own UniProt cell counts as well as its words: CYP2D6 was
            # offered erdafitinib, whose rows name P20815 and Q9HB55 (CYP3A5,
            # CYP3A43), and the run it led to refused them (fifth round,
            # R5V1-14).
            out = []
            for row in rows:
                read = read_isoform(row.conditions)
                if read is None and defaults._accession_says(getattr(row, "uniprot", None),
                                                             isoform) is False:
                    continue
                if read is None or same_isoform(read, isoform):
                    out.append(row)
            return out
    else:
        def _not_another_isoform(rows: Iterable[Any]) -> List[Any]:
            return list(rows)
    listed: Dict[str, int] = {}
    for row in _not_another_isoform(here):
        listed[row.compound] = listed.get(row.compound, 0) + 1
    if not listed:
        return (f" -- BRENDA has no {label} row{named} under EC {ec} in {organism}, and every {label} row "
                f"it holds there names another isoform than {isoform}, which the isoform rule refuses: "
                f"naming another {role} would not fill it, so supply it yourself")
    text = (f" -- BRENDA has no {label} row{named} under EC {ec} in {organism}; the {role}s it lists "
            f"{label} rows for there: {_counted(listed)}. Re-run with {flag} set to one of them, or "
            "supply it yourself")
    if also:
        others = " and ".join(defaults.TABLE_NAMES[t] for t in also)
        have: Dict[str, set] = {}
        for t in also:
            have[t] = {defaults._search_key(r.compound)
                       for r in _not_another_isoform(_usable(defaults.table_rows(ec, t, organism)))}
        both = {c: n for c, n in listed.items() if all(defaults._search_key(c) in have[t] for t in also)}
        if both:
            text += (f". Of these, the ones with a {others} row there too, so that naming one fills this "
                     f"model's other constant{'s' if len(also) > 1 else ''} as well: {_counted(both)}")
        else:
            text += (f". None of them has a {others} row there, so naming one would leave the {others} a "
                     "placeholder in this one's place")
    if compound and elsewhere:
        text += (f". {compound} has {label} rows in other organisms only: {_counted(elsewhere)}, each "
                 "that organism's measurement, never substituted for yours (ADR 0024)")
    elif compound:
        text += (f". BRENDA holds no {label} row for {compound} under EC {ec} in any organism under that "
                 "name (a compound is filed under the name its paper used, so it may be there under "
                 "another)")
    return text


#: The clause `adapters.to_parameter_source` appends to a cross-species
#: refusal: the organisms the resolver found rows in.
_AVAILABLE_IN = re.compile(r" -- available in: ([^-(]+?)(?= -- | \(|$)")


def _same_class(asked: Optional[str], organisms: Iterable[str]) -> List[str]:
    """Those of `organisms` in the asked organism's class, as far as the
    enzyme index's organism codes tell: a mammal for a mammal. Mouse
    tyrosinase's kcat advice led with Streptomyces and hid human's native
    L-Dopa kcat in "and 15 more" (sixth round, NEW-17). [] when it cannot
    be told."""
    try:
        from caterva.enzymes.symbols import MAMMALS, _code_of
    except ImportError:  # pragma: no cover
        return []
    if _code_of(asked) not in MAMMALS:
        return []
    return [o for o in organisms if _code_of(o) in MAMMALS]


def _available_elsewhere(ec: str, table: str, compound: Optional[str], reason: str,
                         isoform: Optional[str] = None,
                         asked: Optional[str] = None) -> Optional[str]:
    """`reason` with its "available in" organisms cut to those holding a row
    the search would use for `compound`; a reason with no such organism is
    rewritten to say the rows elsewhere are variants', and to supply the
    constant. None leaves the reason as it is (no list, no compound, or the
    rows cannot be matched to the compound by name)."""
    from caterva.compose import defaults

    match = _AVAILABLE_IN.search(reason)
    if not match or not compound:
        return None
    key = defaults._search_key(compound)
    listed = [o.strip() for o in match.group(1).split(",") if o.strip()]
    usable: Dict[str, int] = {}
    variants: Dict[str, int] = {}
    isozymes: Dict[str, int] = {}
    for organism in listed:
        rows = [r for r in defaults.table_rows(ec, table, organism) if defaults._search_key(r.compound) == key]
        good = _usable(rows)
        if not isoform:
            # With no --isoform, the search sets a named isozyme's row aside
            # (defaults._usable: "taken only when --isoform asks for it").
            # Vibrio tyrosinaticus's kcat rows are "isoenzyme A" and
            # "isoenzyme B"; offered as a re-run, that run withheld both
            # (sixth round, XS5R2-03).
            named = [r for r in good if getattr(r, "isozyme", False)]
            good = [r for r in good if not getattr(r, "isozyme", False)]
            if named and not good:
                isozymes[organism] = len(named)
                continue
        if good:
            usable[organism] = len(good)
        elif rows:
            variants[organism] = len(rows)
    near = _same_class(asked, usable)
    if isozymes:
        # Said as isozymes, not variants: wild-type proteins in their own
        # right, which a re-run takes only when --isoform names one.
        aside = (f" (rows of a named isozyme only, which a re-run takes only with --isoform naming "
                 f"it: {_counted(isozymes)})")
        if usable and not variants:
            return _AVAILABLE_IN.sub(lambda _m: f" -- available in: {_counted(usable, first=near)}{aside}",
                                     reason, count=1)
    if isoform and usable:
        # With an isoform carried, an organism whose rows name another
        # isoform is not where to find this one's: human LDHA's kcat
        # placeholder offered Plasmodium falciparum (parasite LDH) and
        # Rhizopus delemar (rows naming LDHB) first, and rabbit, the muscle
        # LDH-A4 source, fifth (third round's review).
        naming, silent, other = {}, {}, {}
        # A name matches in another organism only where that organism has
        # the isoform's ortholog: Enterococcus mundtii's "LDH-1" rows were
        # offered first as "rows naming LDHA" (fourth round's review).
        orthologs = set(defaults.organisms_with_isoform(ec, isoform))
        for organism, count in usable.items():
            rows = _usable([r for r in defaults.table_rows(ec, table, organism)
                            if defaults._search_key(r.compound) == key])
            said = [defaults._isoform_read(r.conditions) for r in rows]
            names_it = any(x and defaults._same_isoform(x, isoform) for x in said) or any(
                defaults._accession_says(r.uniprot, isoform) for r in rows)
            if names_it and orthologs and organism not in orthologs:
                other[organism] = count
            elif names_it:
                naming[organism] = count
            elif all(x for x in said):
                other[organism] = count
            else:
                silent[organism] = count
        parts = []
        if naming:
            parts.append(f"rows naming {isoform}: {_counted(naming)}")
        if silent:
            # The organisms with the isoform's ortholog first (rabbit for
            # human LDHA), then by rows.
            near = {o: n for o, n in silent.items() if o in orthologs}
            far = {o: n for o, n in silent.items() if o not in orthologs}
            listed = "; ".join(x for x in (_counted(near), _counted(far)) if x)
            parts.append(f"rows naming no isoform, so whether they measured {isoform}'s counterpart is "
                         f"unknown: {listed}")
        if other:
            parts.append(f"not offered, their rows name another isoform than {isoform}: {_counted(other)}")
        if variants:
            parts.append(f"rows of a protein variant only, withheld: {_counted(variants)}")
        return _AVAILABLE_IN.sub(lambda _m: " -- available in: " + "; ".join(parts), reason, count=1)
    if not variants:
        # Counted, so the advice can name where the measurements are and how
        # many: "available in: Mus musculus, Tetronarce californica" gave no
        # sense of which to pick (fifth round's review, A4-08).
        if not usable and not isozymes:
            return None
        if usable:
            return _AVAILABLE_IN.sub(lambda _m: f" -- available in: {_counted(usable, first=near)}", reason,
                                     count=1)
    if usable:
        return _AVAILABLE_IN.sub(lambda _m: f" -- available in: {_counted(usable, first=near)} (rows of a "
                                 f"protein variant only, withheld: {_counted(variants)})"
                                 + (f"{aside}" if isozymes else ""), reason, count=1)
    label = defaults.TABLE_NAMES[table]
    if isozymes and not variants:
        return (f"no usable value: the organism searched has no {label} row for {compound}, and the only "
                f"rows elsewhere ({_counted(isozymes)}) each name an isozyme, which a re-run takes only "
                "with --isoform naming it, so re-running with --organism alone would not fill it: pass "
                "--isoform with the isozyme a row names, or supply it yourself"
                + reason[match.end():])
    return (f"no usable value: the organism searched has no {label} row for {compound}, and the only "
            f"rows elsewhere ({_counted(variants)}) measured a protein variant, which is withheld "
            f"(ADR 0029), so re-running in {'that organism' if len(variants) == 1 else 'any of them'} would "
            "not fill it either: supply it yourself"
            + (f"{aside}" if isozymes else "")
            + reason[match.end():])


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


def _filed_under_other_names(model: Any, measured: Mapping[str, Any], ec: Optional[str]) -> List[str]:
    """One sentence per carried value whose BRENDA row files its compound
    under another name than the one the model uses, saying both.

    "acetylcholinesterase inhibited by donepezil" carried Ki 2.2e-06 mM
    (ref 651163) from a row BRENDA files as "(R,S)-1-benzyl-4-[(5,6-
    dimethoxy-1-indanon)-2-yl]methylpiperidine hydrochloride", racemic
    donepezil hydrochloride, which Caterva's compound names read as
    donepezil; no surface said so (fifth round of the real-values review).
    A spelling that differs only in case, spacing or a counter-ion is not
    another name and is not said. A page that cannot be read says nothing.
    """
    if not ec or not measured:
        return []
    from caterva.compose import defaults

    out: List[str] = []
    for q in getattr(model, "resolvable", ()) or ():
        m = measured.get(q.parameter_id)
        if m is None or q.table not in ("km", "kcat", "ki"):
            continue
        compound = model.compound_for(q)
        if not compound:
            continue
        ref = getattr(m, "reference_id", None)
        if ref is None:
            cited = re.search(r"BRENDA ref (\d+)", str(getattr(m, "citation", "") or ""))
            ref = cited.group(1) if cited else None
        try:
            rows = defaults.rows_of_value(
                ec, q.table, getattr(m, "organism", None) or getattr(model, "organism", None), m.value, ref)
        except Exception:  # noqa: BLE001 - unverifiable: nothing said
            continue
        # Only the rows the search takes for the compound: another compound
        # of the same paper can share the value (CPA's 6.08 1/s, ref 650016).
        cells = sorted({r.compound for r in rows if defaults._matches(r.compound, compound)})
        if not cells or any(defaults._search_key(c) == defaults._search_key(compound) for c in cells):
            continue
        shown = " / ".join(repr(c) for c in cells[:2])
        same = all(defaults._group_key(c) == defaults._group_key(compound) for c in cells)
        out.append(f"`{q.parameter_id}`: BRENDA files the row it came from (ref {ref}) as {shown}, "
                   + (f"which Caterva reads as {compound}, the compound the model names: the same "
                      "compound under another name" if same else
                      f"which the search took for {compound}, the compound the model names, because "
                      "BRENDA's name holds it; read the row to check it is the compound you mean"))
    return out


#: How a window re-selection's reason begins (caterva.agents.scouts).
_WINDOW_MOVED = "it is the row nearest the assay window"
_INDEPENDENT = "the Km and the kcat were chosen independently, not as a measured pair"


def _pairing_said_after_windows(measured: Dict[str, Any]) -> Dict[str, Any]:
    """A constant whose reason says the Km and kcat were "chosen
    independently, not as a measured pair", when an assay window then moved
    the other constant onto the same paper's row, is told so: rabbit
    aldolase's kcat said the pair of ref 770643 "was not carried", beside a
    Km the window had moved to ref 770643 (third round's review)."""
    import re as _re
    from dataclasses import replace as _replace

    def ref(m: Any) -> Optional[str]:
        found = _re.search(r"ref (\d+)", str(getattr(m, "citation", "") or ""))
        return found.group(1) if found else None

    moved = {ref(m) for m in measured.values()
             if str(getattr(m, "resolver_because", "") or "").startswith(_WINDOW_MOVED)}
    moved.discard(None)
    if not moved:
        return measured
    out = dict(measured)
    for name, m in measured.items():
        because = str(getattr(m, "resolver_because", "") or "")
        if _INDEPENDENT in because and ref(m) in moved:
            try:
                out[name] = _replace(m, resolver_because=(
                    because + f"; the assay window then moved the other constant onto BRENDA ref "
                    f"{ref(m)}'s row, so both carried rows are that paper's after all"))
            except (TypeError, ValueError):
                pass
    return out


#: How far (fold) a carried Ki may sit from the same compound's Ki rows in
#: other organisms under the EC before the report says so.
FAR_FROM_OTHER_ORGANISMS = 100.0


def _far_from_other_organisms(model: Any, measured: Mapping[str, Any], ec: Optional[str],
                              organism: Optional[str]) -> List[str]:
    """Notes for a carried Ki lying more than FAR_FROM_OTHER_ORGANISMS from
    the median of the compound's Ki rows in other organisms under the EC.

    E. coli DHFR and methotrexate: BRENDA's only E. coli Ki row is 0.0059 mM
    (ref 655867), about 1e5-fold weaker than the pM-nM binding the field
    knows, and the scale check said "all numbers possible" (third round's
    review). It is the only row and it is carried; the reader is told it is
    the only row and how far it sits from every other organism's."""
    if not ec or not organism or not measured:
        return []
    from statistics import median

    from caterva.compose import defaults

    notes: List[str] = []
    for q in getattr(model, "resolvable", ()) or ():
        m = measured.get(q.parameter_id)
        if m is None or q.table != "ki":
            continue
        compound = model.compound_for(q)
        try:
            value = float(m.value)
            rows = defaults.table_rows(ec, "ki", None)
        except Exception:  # noqa: BLE001
            continue
        mine = [r for r in rows if r.organism == organism and compound
                and defaults._matches(r.compound, compound) and not r.flagged]
        others = [float(r.value) for r in rows if r.organism != organism and compound
                  and r.value and defaults._matches(r.compound, compound) and not r.flagged]
        if len(others) < 3 or value <= 0:
            continue
        mid = median(others)
        fold = max(value / mid, mid / value)
        if fold < FAR_FROM_OTHER_ORGANISMS:
            continue
        only = "the only Ki row" if len(mine) == 1 else f"one of {len(mine)} Ki rows"
        notes.append(
            f"`{q.parameter_id}`: {m.value:g} {m.unit} is {only} for {compound} in {organism}, and it "
            f"lies {fold:.2g}-fold from the median ({mid:g} {m.unit}) of the {len(others)} rows for it "
            f"under EC {ec} in other organisms: read that paper before relying on it (a unit or "
            "transcription slip in the database is possible)")
    return notes


#: Tissue words that name a mammalian isoform for these EC numbers.
#: "pyruvate kinase muscle human PEP" dropped "muscle" without a word
#: (third round's review); the muscle and liver forms differ many-fold.
def _tissue_isoforms() -> Dict[str, Dict[str, Tuple[str, str]]]:
    # One table, the literature layer's (row_form.TISSUE_ISOFORMS): the
    # resolver reads a row's tissue by it ("heart phosphorylase"), so the
    # description's word and the row's cannot disagree.
    try:
        from caterva.checkout import literature_module

        return literature_module("row_form").TISSUE_ISOFORMS
    except Exception:  # noqa: BLE001 - without the literature layer, no table
        return {}


_TISSUE_WORD = re.compile(r"\b(?:muscle|liver|heart|brain|erythrocyte|red cell|platelet|kidney)\b",
                          re.IGNORECASE)


def _tissue_isoform(ec: Optional[str], typed: str) -> Optional[Tuple[str, str, str]]:
    """(word, isoform, what it is) for a tissue word naming one of the EC's
    isoforms; None when the EC has no tissue isoforms listed or no word
    names one; "" (falsy, not None) is never returned."""
    table = _tissue_isoforms().get(ec or "")
    if not table:
        return None
    for word, (isoform, said) in table.items():
        if re.search(rf"\b{re.escape(word)}\b", typed, re.IGNORECASE):
            return word, isoform, said
    return None


def _service_failed(text: str) -> str:
    """Which service failed, said for a reader, with the remedy: a network
    failure is fixed by running again, not by another organism or name."""
    low = text.lower()
    service = ("UniProt" if "uniprot" in low else "NCBI taxonomy" if "ncbi" in low
               else "BRENDA" if "brenda" in low else "a database the search reads")
    kind = ("timed out" if "timeout" in low else
            "answered with a server error" if any(c in low for c in ("503", "502", "504", "500"))
            else "failed")
    return (f"{service} {kind} ({text.strip()[:160]}). This is a network failure, not an "
            f"absence of measurements: re-run the same command, which usually succeeds")


def _not_searched(failure: str) -> str:
    """The reason a constant whose scout failed carries: not searched."""
    return f"not searched: {_service_failed(failure)}"


def _not_looked_up(skipped: Mapping[str, str]) -> str:
    """The note's clause for constants deliberately not looked up, or ""."""
    if not skipped:
        return ""
    return (f". {len(skipped)} not looked up ({', '.join(sorted(skipped))}): "
            "the provenance table says what would let "
            + ("it" if len(skipped) == 1 else "them") + " be looked up")


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
