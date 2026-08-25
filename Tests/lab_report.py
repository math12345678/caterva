"""
lab_report.py

One document a student can hand in.

WHY THIS EXISTS
---------------
Terrium had, separately: a resolver that finds literature values, a
provenance record for each one, assay conditions, reliability grades on
Bakker's axes, an ensemble for values the evidence cannot rank, a BibTeX
exporter, an annotated model exporter, and a simulation engine.

Nine capabilities, and nothing a person could hand to a teacher.

Every one of those is an ANSWER TO A QUESTION NOBODY ASKED IN ISOLATION. A
student in a teaching lab has one job: run the simulation, and show where
the numbers came from. Terrium could do both halves and made the student
assemble them from a terminal transcript, two export files and a screen
they had already scrolled past.

WHAT MAKES THIS DIFFERENT FROM A PRINTOUT
-----------------------------------------
The section other tools do not have is **what Terrium refused to do**.

A report that silently omits what could not be sourced is this project's
own defect at document scale: computed, correct, and not delivered. A
reader cannot tell a parameter nobody has measured from one the tool
declined to substitute, and those are different facts with different
remedies. So refusals are content here, each with the reason and the action
that would change it.

NOTHING IS RESTATED
-------------------
Every sentence about a value comes from the module that owns that value's
reasoning -- `spread_consequence` for ensembles, `citation_export` for the
bibliography, the resolver's own `reason` strings for caveats. This module
arranges; it does not re-derive. Two renderers of one fact drift, and this
repository has spent most of its effort on instances of exactly that
(ADR 0003, ADR 0027, ADR 0113).
"""
from __future__ import annotations

import pathlib
from typing import Any, Sequence

from pydantic import BaseModel


class SuppliedValue(BaseModel):
    """A number the student chose, not one the literature reports.

    Kept apart from resolved values everywhere it appears. `s0` is the
    experiment being run; a Km is a property of the enzyme. Presenting them
    in one undifferentiated table is how a reader comes to believe the tool
    sourced something it did not, which is the failure the whole provenance
    layer exists to prevent.
    """

    name: str
    value: float
    unit: str | None = None
    #: Why this number rather than another. Optional -- a student may have
    #: no reason beyond "the lab handout said so", and inventing one for
    #: them would be worse than leaving it blank.
    basis: str | None = None


class DerivedValue(BaseModel):
    """A number computed from a cited one and a chosen one.

    THE THIRD KIND, AND WHY IT NEEDS ITS OWN TYPE
    ---------------------------------------------
    The report has always had two origins: `literature` (a value with a
    citation) and `yours` (a value the student picked). A bridged Vmax is
    neither, and calling it either is a lie in a specific direction:

      * `literature` claims BRENDA reports a Vmax for this assay. It does
        not -- it reports a kcat, and Vmax depends on how much enzyme the
        student put in (ADR 0012, ADR 0013).
      * `yours` discards the citation for the kcat, which is the whole
        reason the number is defensible.

    So it is its own origin, carrying BOTH halves: the cited part with its
    reference, and the chosen part marked as chosen. A reader can check
    each independently, which is the entire point of the document.
    """

    name: str
    value: float
    unit: str | None = None
    #: The literature half, rendered as-is: "kcat 1.07 1/s (BRENDA ref 740253)".
    #: Written by the caller that owns the resolution, never re-derived here.
    from_cited: str
    #: The student's half: "[E]0 0.001 mM, yours".
    from_chosen: str
    #: How they were combined, e.g. "Vmax = kcat x [E]0". Stated rather than
    #: implied: a reader who cannot see the operation cannot check the number.
    relation: str


def _fmt(value: Any) -> str:
    """Numbers a reader can check against the source, without noise."""
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value)


def _conditions_phrase(result: Any) -> str:
    """What the source said about how the measurement was made.

    Reads the resolver's own fields. Returns "" when the source said
    nothing AND nothing recorded its silence -- which is different from a
    source that explicitly reported nothing, and the caller renders that
    difference rather than this function flattening it.
    """
    measured = []
    if getattr(result, "assay_ph", None) is not None:
        measured.append(f"pH {_fmt(result.assay_ph)}")
    if getattr(result, "assay_temperature_c", None) is not None:
        measured.append(f"{_fmt(result.assay_temperature_c)} °C")
    if getattr(result, "assay_buffer", None):
        measured.append(f"in {result.assay_buffer}")
    return ", ".join(measured)


def _citation_text(result: Any) -> str:
    citation = getattr(result, "citation", None)
    if citation is None:
        return "no citation recorded"
    source = getattr(citation, "source", None) or "unknown source"
    reference = getattr(citation, "reference_id", None)
    title = getattr(citation, "title", None)
    parts = [f"{source} ref {reference}" if reference else source]
    if title:
        parts.append(f"“{title}”")
    return " — ".join(parts)


class LabReport(BaseModel):
    """The document, and the facts it was built from.

    A model rather than a bare string so a caller can assert on the parts
    without parsing prose -- a test that greps the rendered markdown is a
    test of the wording, and the wording is the least important thing here.
    """

    title: str
    question: str
    markdown: str

    #: Parameter names that carry a literature citation.
    sourced: list[str] = []
    #: Parameter names the student supplied.
    supplied: list[str] = []
    #: Parameter names computed from a cited value and a chosen one.
    derived: list[str] = []
    #: One line per thing Terrium declined to do, in the reader's terms.
    refusals: list[str] = []
    #: Parameters where the literature reports more than one value.
    disagreements: list[str] = []

    @property
    def is_defensible(self) -> bool:
        """Every number in the model is either cited or declared as the
        student's own.

        A POSITIVE test. `not refusals` would call a report with no
        parameters at all defensible, and an empty report is not a strong
        one -- it is an empty one.
        """
        accounted = self.sourced + self.supplied + self.derived
        return bool(accounted) and not any(
            name not in self.sourced
            and name not in self.supplied
            and name not in self.derived
            for name in accounted
        )


def _code_version(root: "pathlib.Path | None" = None) -> tuple[str, str | None]:
    """The commit this ran from, and why it cannot be trusted if so.

    Returns (description, caveat). The caveat is None only when the answer
    is genuinely usable.

    THREE STATES, BECAUSE A DIRTY TREE IS NOT THE COMMIT.
    -----------------------------------------------------
    Printing `commit abc1234` while the working tree has uncommitted changes
    is the most confident kind of wrong: a reader checks out abc1234, gets
    different numbers, and has no way to discover why. The code that ran was
    not that commit.

    Not a git checkout at all — an install from a tarball or a copied
    directory — is a third answer, and "I do not know" must not be rendered
    as a blank line the reader takes for "nothing to report".
    """
    import subprocess

    # Parameterised so the DETECTION can be tested against a real git
    # repository, not just the rendering. The first version of these tests
    # monkeypatched this whole function, so deleting the dirty-tree branch
    # left all four passing — a test of the wording standing in for a test
    # of the logic, which is the shape this project keeps finding.
    root = root or pathlib.Path(__file__).resolve().parent.parent
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, cwd=str(root), timeout=15,
        )
        if commit.returncode != 0:
            return ("unknown", "this is not a git checkout, so the exact "
                               "code that produced this cannot be named.")
        sha = commit.stdout.strip()
        dirty = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True, text=True, cwd=str(root), timeout=20,
        )
        if dirty.returncode == 0 and dirty.stdout.strip():
            changed = len(dirty.stdout.strip().splitlines())
            return (
                f"{sha} plus {changed} uncommitted change(s)",
                "the working tree was modified, so checking out "
                f"{sha} will NOT reproduce this exactly. Commit first if "
                "this document is going anywhere.",
            )
        return (sha, None)
    except (OSError, subprocess.SubprocessError):
        return ("unknown", "git could not be run, so the exact code that "
                           "produced this cannot be named.")


def _provenance_lines(rate_law: str | None = None) -> list[str]:
    """How this document was produced, at the bottom of the document.

    WHY A REPORT HAS TO SAY THIS
    ----------------------------
    The band section already claims *"Seed 1 — re-running with it reproduces
    this band exactly."* That sentence was true and unusable: re-running
    with WHICH version? A report carried no commit, no date, and no command.

    For a tool whose entire argument is that its numbers can be re-derived,
    and whose most likely reader is a reproducibility centre, a
    reproducibility claim with nothing behind it is the house defect at the
    worst possible address — the claim delivered, the means withheld.

    WHAT IS DELIBERATELY NOT HERE
    -----------------------------
    A hash of the inputs. `scientificPipeline` computes one and this
    function cannot see it, and a second implementation would be a second
    thing to keep true. Named as absent rather than half-built.
    """
    from datetime import datetime, timezone

    version, caveat = _code_version()
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines = [
        "",
        "---",
        "",
        "## How this document was produced",
        "",
        "| | |",
        "|---|---|",
        f"| Terrium commit | `{version}` |",
        f"| Generated | {generated} |",
    ]

    # WHICH EQUATION THE NUMBERS CAME OUT OF
    #
    # The document said "running the model at each" and never said what the
    # model was. Every figure in it -- the band, the disagreement spread, the
    # trajectory -- is the output of one specific rate law, and a reader
    # cannot check a number without knowing which.
    #
    # It became load-bearing when `release/app/lesson.js` began explaining
    # results in terms of `v = Vmax*S/(Km+S)`. That sentence was TRUE of this
    # run and asserted about any run: nothing in the document said the run
    # used Michaelis-Menten, so a future domain with a `km` and a different
    # rate law would have been handed an explanation that did not apply to
    # it. The fix is not for the lesson to guess better -- it is for the
    # document to say, once, here.
    #
    # None rather than a default: a run whose rate law is not known to the
    # caller must report that it is not known, because "assume Michaelis-
    # Menten" is exactly the substitution this project exists to refuse.
    if rate_law:
        lines.append(f"| Rate law | {rate_law} |")
    else:
        lines.append(
            "| Rate law | not stated by the caller — the equation behind "
            "these numbers is not recorded in this document |"
        )
    lines.append("")
    if caveat:
        lines += [
            f"**This document is not reproducible as it stands:** {caveat}",
            "",
        ]
    else:
        lines += [
            "Check out that commit and re-run the command that produced "
            "this — with the same seed — and every number above should come "
            "back identical. If it does not, one of them is wrong and this "
            "row is how you find out which.",
            "",
        ]
    return lines


def build_report(
    *,
    title: str,
    question: str,
    resolved: dict[str, Any],
    supplied: Sequence[SuppliedValue] = (),
    derived: Sequence[DerivedValue] = (),
    simulation: Any | None = None,
    bibtex: str | None = None,
    ensembles: dict[str, Any] | None = None,
    bands: dict[str, Any] | None = None,
    also_refused: Sequence[str] = (),
    rate_law: str | None = None,
) -> LabReport:
    """Assemble one document from what the run actually established.

    `resolved` maps a parameter name to a `KineticResult` -- found or not.
    A NOT-found result is not skipped: it becomes a refusal, because "the
    tool could not source this" is the single most important thing a reader
    of a lab report needs to know and the easiest thing for a printout to
    lose.

    `also_refused` carries refusals the CALLER established, which this
    function cannot see -- chiefly "the model was not run, and here is what
    was missing". They render in the same section as the ones found here,
    because a reader looking for what Terrium would not do must find all of
    it in one place; a second list somewhere else is a gap with extra steps.
    """
    lines: list[str] = [f"# {title}", "", question, ""]

    sourced: list[str] = []
    supplied_names = [s.name for s in supplied]
    refusals: list[str] = []
    disagreements: list[str] = []

    # ---- What the model ran on -------------------------------------------
    lines += ["## Parameters", ""]
    lines += ["| parameter | value | origin | source |", "|---|---|---|---|"]

    for name, result in resolved.items():
        if getattr(result, "found", False):
            sourced.append(name)
            lines.append(
                f"| {name} | {_fmt(result.value)} {getattr(result, 'unit', '') or ''} "
                f"| literature | {_citation_text(result)} |"
            )
        elif name in supplied_names:
            # ONE ROW PER PARAMETER, EVEN WHEN TWO THINGS ARE TRUE ABOUT IT.
            #
            # A km the literature could not supply and the student measured
            # themselves produced TWO rows: "km — not sourced" and "km 5.2 mM
            # yours". Both were accurate and the table was not: a document
            # handed to a teacher listing the same parameter twice, once as
            # absent, is a document nobody can read.
            #
            # The supplied row below carries the value and its basis. Only
            # the empty row is dropped, and the lookup's failure is still in
            # "What Terrium would not do" — so nothing is hidden, it is just
            # not said twice in contradictory ways.
            continue
        else:
            lines.append(
                f"| {name} | — | **not sourced** | see *What Terrium would "
                f"not do* |"
            )

    for value in supplied:
        lines.append(
            f"| {value.name} | {_fmt(value.value)} {value.unit or ''} "
            f"| **yours** | {value.basis or 'not stated'} |"
        )

    derived_names: list[str] = []
    for value in derived:
        derived_names.append(value.name)
        # BOTH halves in the source column. A reader checking this number
        # needs the paper for the cited part and the knowledge that the
        # other part was chosen -- collapsing either one is the misreport
        # `DerivedValue` exists to prevent.
        lines.append(
            f"| {value.name} | {_fmt(value.value)} {value.unit or ''} "
            f"| **derived** | {value.relation}: {value.from_cited}, "
            f"and {value.from_chosen} |"
        )

    # THAT SENTENCE STOPPED BEING TRUE WHEN A MEASUREMENT COULD BE SUPPLIED.
    #
    # "describes the experiment, not the enzyme" is right for s0 and e0 --
    # conditions the student chose, which need no citation (START_HERE). It
    # is WRONG for a km they measured at a bench: that is a property of the
    # enzyme, it simply has the student as its source rather than a paper.
    #
    # Printing the condition sentence under a supplied km would tell a
    # teacher the number is not about the enzyme, which is the opposite of
    # what it is. So the caveat follows what was actually supplied.
    # km, ki, kcat -- the three quantities BRENDA reports and somebody
    # measured at a bench. NOT vmax: ADR 0142 settled that Vmax is a property
    # of the student's own tube, which no database reports, so it belongs
    # with the conditions above and putting it here would have told a reader
    # the literature had failed to supply something it never holds.
    _MEASURED = {"km", "ki", "kcat"}
    supplied_measurements = sorted(_MEASURED.intersection(supplied_names))

    lines += [
        "",
        "A value marked **yours** describes the experiment, not the enzyme. "
        "No database reports it, and Terrium has not checked it.",
        "",
    ]
    if supplied_measurements:
        lines += [
            "Except for "
            + ", ".join(f"**{n}**" for n in supplied_measurements)
            + ": that IS a property of the enzyme, and you are its source "
            "rather than a paper. The literature could not supply it and "
            "Terrium did not invent one — the basis in the table is what "
            "stands behind the number, and it is the thing to question.",
            "",
        ]

    if derived_names:
        lines += [
            "A value marked **derived** was computed, not looked up. It is "
            "only as good as both of its parts: the cited measurement, and "
            "the number you chose. No database reports it for this assay.",
            "",
        ]

    # ---- The conditions each measurement was made under -------------------
    condition_lines: list[str] = []
    for name, result in resolved.items():
        if not getattr(result, "found", False):
            continue
        measured = _conditions_phrase(result)
        unreported = list(getattr(result, "assay_unreported", []) or [])
        if not measured and not unreported:
            continue
        entry = f"- **{name}** — "
        entry += f"measured at {measured}" if measured else "no conditions reported"
        if unreported:
            entry += f"; the source did not report {', '.join(unreported)}"
        condition_lines.append(entry)

    if condition_lines:
        lines += [
            "## Conditions the values were measured under",
            "",
            "Kinetic values move with pH, temperature and buffer. Two values "
            "measured under different conditions describe experiments nobody "
            "ran together.",
            "",
            *condition_lines,
            "",
        ]

    # ---- Where the literature disagrees ----------------------------------
    for name, verdict in (ensembles or {}).items():
        reason = getattr(verdict, "reason", "")
        if not reason:
            continue
        disagreements.append(name)
        lines += [
            f"## The literature disagrees about {name}",
            "",
            # The module that owns the reasoning wrote this sentence. It is
            # quoted, not paraphrased: a second wording is a second claim.
            reason,
            "",
        ]
        outcomes = getattr(verdict, "outcomes", []) or []
        if outcomes:
            lines += ["| value | result |", "|---|---|"]
            for outcome in outcomes:
                shown = (
                    _fmt(outcome.outcome)
                    if getattr(outcome, "outcome", None) is not None
                    else f"could not be simulated — {getattr(outcome, 'failure', '')}"
                )
                mark = " (returned)" if getattr(outcome, "selected", False) else ""
                lines.append(f"| {_fmt(outcome.value)}{mark} | {shown} |")
            lines.append("")

    # ---- The band across everything the evidence supports ------------------
    #
    # The section above ENUMERATES: which paper gives which answer. This one
    # SAMPLES: what the model does across the distribution those papers
    # support, weighted by reliability (ADR 0131, ADR 0132).
    #
    # Both, because they answer different questions and a student needs
    # both — the specific row to defend a number to a teacher, and the band
    # to say how much the answer depends on which paper they picked. ADR
    # 0134 binds them: the band cannot reach outside the enumerated
    # outcomes, and `test_ensembles_agree.py` fails if it does.
    for name, band in (bands or {}).items():
        envelopes = list(getattr(band, "envelopes", []) or [])
        if not envelopes:
            continue
        if name not in disagreements:
            disagreements.append(name)

        failed = list(getattr(band, "failed", []) or [])
        lines += [
            f"## What the model does across the evidence — {name}",
            "",
            # The seed, because a band nobody can reproduce is not
            # evidence. `sample_ensemble` makes it a required argument for
            # that reason; dropping it from the document would undo the
            # requirement at the last step.
            f"{getattr(band, 'succeeded', '?')} run(s) at values drawn from "
            f"the literature and weighted by reliability. Seed "
            f"{getattr(band, 'seed', '?')} — re-running with it reproduces "
            "this band exactly.",
        ]
        if failed:
            # Runs that failed are not quietly dropped. A band computed from
            # the survivors and presented as if every draw had run is
            # narrower than the evidence, and says nothing about why.
            lines.append(
                f"{len(failed)} run(s) did not complete and are excluded from "
                "the figures below."
            )
        lines.append("")

        for envelope in envelopes:
            lines += [
                f"- **{envelope.column}** at the end of the run: "
                f"{_fmt(envelope.low[-1])} lowest, "
                f"{_fmt(envelope.p05[-1])} 5th, "
                f"{_fmt(envelope.median[-1])} median, "
                f"{_fmt(envelope.p95[-1])} 95th, "
                f"{_fmt(envelope.high[-1])} highest",
            ]
        lines.append("")

        disclaimer = getattr(band, "disclaimer", "")
        if disclaimer:
            # Quoted, not reworded. The module computing the band wrote the
            # sentence about what it does and does not mean; a second
            # wording here would be a second claim (ADR 0003).
            lines += [disclaimer, ""]

    # ---- What Terrium would not do ---------------------------------------
    #
    # THE SECTION THAT MAKES THIS A TERRIUM REPORT.
    #
    # Every other tool's output is what it managed to produce. A refusal
    # that appears nowhere is indistinguishable from a question nobody
    # asked, and the student cannot act on it or defend the gap to a
    # teacher.
    for name, result in resolved.items():
        if getattr(result, "found", False):
            continue
        source = getattr(result, "source", "") or "not_found"
        detail = {
            "cross_species_withheld": (
                "a value exists in another organism and was not substituted, "
                "because a kinetic constant is species-specific"
            ),
            "variant_withheld": (
                "every value found was measured on a protein variant rather "
                "than the enzyme as found"
            ),
            "ec_ambiguous": (
                "the enzyme name matched more than one EC number, and "
                "choosing one would cite a different protein"
            ),
            "ec_not_resolved": (
                "no EC number could be found for that name, so no database "
                "was asked"
            ),
            "literature_candidates": (
                "no database value was found; candidate papers were located "
                "but no number was read out of them"
            ),
        }.get(source, "no value was found in BRENDA, KEGG or PubMed")

        # A `not_found` covers two quite different situations, and the
        # resolver already distinguishes them (ADR 0118): the substrate name
        # matched nothing while the enzyme reports others, versus a genuine
        # gap. The first is fixable by the reader in one edit, so saying
        # only "not found" wastes the work that established which it was.
        available = list(getattr(result, "substrates_available", []) or [])
        if available:
            detail = (
                "the substrate name matched nothing, though this enzyme "
                f"reports values for {', '.join(available)} — Terrium does "
                "not substitute a similar name, because a similar name can "
                "be a different molecule"
            )
        refusals.append(f"{name}: {detail}")

    for name, result in resolved.items():
        preparation = getattr(result, "preparation", None)
        if preparation is not None and getattr(
            preparation, "differs_from_the_free_enzyme", False
        ):
            refusals.append(
                f"{name}: the value returned was measured on a "
                f"{preparation.status} enzyme, not the free enzyme"
            )
        for mixture in getattr(result, "source_mixtures", []) or []:
            reason = getattr(mixture, "reason", "")
            if reason:
                refusals.append(f"{name}: {reason}")

    refusals.extend(also_refused)

    if refusals:
        lines += [
            "## What Terrium would not do",
            "",
            "These are not omissions. Each one is a decision, with the reason "
            "and what would change it.",
            "",
            *[f"- {r}" for r in refusals],
            "",
        ]
    else:
        lines += [
            "## What Terrium would not do",
            "",
            "Nothing was withheld: every parameter resolved to a cited value "
            "or was supplied by you.",
            "",
        ]

    # ---- The run ----------------------------------------------------------
    if simulation is not None:
        colnames = list(getattr(simulation, "colnames", []) or [])
        data = list(getattr(simulation, "data", []) or [])
        if colnames and data:
            lines += ["## Result", "", "| " + " | ".join(colnames) + " |",
                      "|" + "---|" * len(colnames)]
            # First and last row only. A lab report is not a data dump, and
            # the full trajectory belongs in the CSV export.
            for row in (data[0], data[-1]):
                lines.append("| " + " | ".join(_fmt(v) for v in row) + " |")
            lines += [
                "",
                f"{len(data)} time points; first and last shown. The full "
                "trajectory is in the CSV export.",
                "",
            ]

    # ---- Citations --------------------------------------------------------
    if bibtex:
        lines += [
            "## Citations",
            "",
            "Import into Zotero, Mendeley or EndNote. Author, year and "
            "journal are absent rather than invented — complete each entry "
            "from its source before citing it.",
            "",
            "```bibtex",
            bibtex.rstrip(),
            "```",
            "",
        ]

    lines += _provenance_lines(rate_law)

    return LabReport(
        title=title,
        question=question,
        markdown="\n".join(lines).rstrip() + "\n",
        sourced=sourced,
        supplied=supplied_names,
        derived=derived_names,
        refusals=refusals,
        disagreements=disagreements,
    )
