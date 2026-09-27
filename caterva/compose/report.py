"""A full dossier for a composed model, in one readable document.

WHY ONE DOCUMENT
----------------
The pieces exist separately -- structure, units, conservation laws,
provenance, steady states, sweeps -- and a researcher deciding whether to
trust a model has to hold all of them at once. Split across six calls with
six return types, nobody does.

More particularly: the interesting judgements are the ones that need two
pieces together. A steady state is only meaningful with the conservation
law that pins its leaf. A "no measured value" is only actionable with the
unit and the table the value would come from. A bistability claim means
something different when three of the constants are placeholders.

So this assembles them, and it puts the caveats NEXT TO the results they
qualify rather than in a footnote. A reader who skips the last paragraph
should still not be misled.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Optional, Sequence, Tuple


@dataclass(frozen=True)
class ModelDossier:
    """Everything known about one composed model."""

    query: str
    model: Any                      # ComposedModel
    stability: Optional[Any] = None  # StabilityReport
    sweeps: Tuple[Any, ...] = ()     # SweepReport
    search: Optional[Any] = None     # ModelSearch, when parameters resolved
    trajectory: Optional[Any] = None  # Trajectory, when the engine is present
    #: SensitivityReport, when a ranking could be computed. Reported INSIDE
    #: the provenance table rather than in a section of its own -- see
    #: `provenance_section`.
    sensitivity: Optional[Any] = None
    #: Verdict, from compose/verdict.py. Rendered FIRST, because the
    #: judgement a reader needs is whether the model is worth using and for
    #: what, and that decision needs several sections at once. A reader who
    #: stops after the first page should have the part that matters.
    verdict: Optional[Any] = None

    # -- sections -----------------------------------------------------

    def verdict_section(self) -> List[str]:
        """What the model supports, before any of the detail.

        FIRST, not last. A summary at the end is read by whoever finished,
        and the reader most at risk of over-reading this report is the one
        who skims. The sections below qualify this page; this page says
        which of them to read.
        """
        if self.verdict is None:
            return []
        return ["## Verdict", "", "```", self.verdict.summary(), "```", ""]

    def structure_section(self) -> List[str]:
        network = self.model.network
        recognition = self.model.recognition
        lines = [
            "## Structure",
            "",
            f"Recognised as: **{recognition.rule.replace('_', ' ')}** "
            f"({recognition.reading}).",
            "",
            f"{len(network.species)} species, {len(network.reactions)} "
            f"reactions, {len(network.parameters)} parameters.",
            "",
            "| reaction | rate law |",
            "|---|---|",
        ]
        for reaction in network.reactions:
            lines.append(f"| `{reaction.id}` | `{reaction.rate_law}` |")
        lines.append("")
        for note in recognition.composition.notes:
            lines.append(f"- {note.rstrip('.')}.")
        return lines

    def invariants_section(self) -> List[str]:
        try:
            from caterva.core.network import describe_conservation_laws
        except ImportError:  # pragma: no cover
            from core.network import describe_conservation_laws  # type: ignore

        laws = list(describe_conservation_laws(self.model.network))
        lines = ["", "## Invariants", ""]
        if laws:
            lines.append(
                "These are **derived**, not asserted: they are the left null "
                "space of this model's own stoichiometry matrix, computed "
                "exactly over rationals."
            )
            lines.append("")
            for law in laws:
                lines.append(f"- `{law}` is constant")
        else:
            lines.append(
                "No conservation law holds. Every species in this model is "
                "created or destroyed rather than only moved around."
            )

        mentioned = set()
        for law in laws:
            import re
            mentioned.update(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", law))
        open_species = [
            s.id for s in self.model.network.species if s.id not in mentioned
        ]
        if open_species and laws:
            lines.append("")
            lines.append(
                f"`{'`, `'.join(open_species)}` appear in no law: the system "
                f"is open in those directions."
            )
        return lines

    def units_section(self) -> List[str]:
        examined, findings = self.model.recognition.composition.unit_check()
        lines = ["", "## Dimensions", ""]
        if not examined:
            # "Every rate law balances" over zero rate laws is true and
            # reads as a clean bill of health. This section is one of the
            # places a reader looks to decide whether to trust the model.
            lines.append(
                "No rate law was checked -- this composition declares none. "
                "That is an absence of examination, not a clean result."
            )
            return lines
        if not findings:
            lines.append(
                f"All {examined} rate laws balance, in dimension and in "
                "scale. Checked before compilation: a law with the wrong "
                "dimensions integrates perfectly well and is wrong by "
                "whatever factor the mistake introduced."
            )
            return lines
        lines.append(f"**{len(findings)} problem(s):**")
        lines.append("")
        for finding in findings:
            lines.append(f"- **{finding.severity}** in `{finding.where}` — {finding.detail}")
        return lines

    def provenance_section(self) -> List[str]:
        lines = ["", "## Where the numbers come from", ""]

        if self.model.structure_only:
            lines.append(
                "**Nothing was searched for.** No enzyme was named, so there "
                "is nothing whose measured constants could be looked up. "
                "These are the measurements that would complete the model:"
            )
            lines.append("")
            lines += self._resolvable_table()
        elif getattr(self.model, "searched", False):
            # A SEARCH RAN AND THIS IS WHAT IT RETURNED (ADR 0178).
            # Measured and still-placeholder are listed in the same section,
            # because the one thing a reader must not have to work out is
            # which of the numbers below a paper stands behind.
            lines += self._measured_table()
        elif self.search is None:
            lines.append(
                f"Subject named (`{self.model.subject}`) but no search was "
                f"run in this report."
            )
        else:
            lines.append(self.search.summary())

        lines.append("")
        lines.append(
            f"**Yours to set** ({len(self.model.chosen)}): "
            + ", ".join(f"`{name}`" for name in self.model.chosen)
            + ". Starting amounts and any cooperativity — no paper supplies "
            "these, and they are recorded as your choices rather than as "
            "measurements."
        )
        return lines

    def _measured_table(self) -> List[str]:
        """What the literature returned, and what it did not.

        Every measured row carries its citation. A value without one is not
        a measurement as far as any artefact here is concerned, which is why
        `Measurement` requires the field and this table can print it
        unconditionally.
        """
        measured = dict(getattr(self.model, "measured", {}) or {})
        by_id = {q.parameter_id: q for q in self.model.resolvable}
        lines = [
            f"**{len(measured)} of {len(self.model.resolvable)} constant(s) "
            f"came from the literature**, searched for "
            f"`{self.model.subject}`"
            + (f" in {self.model.organism}" if self.model.organism else "")
            + (f", substrate {self.model.substrate}" if self.model.substrate else "")
            + ".",
            "",
            "| quantity | value | origin | source |",
            "|---|---|---|---|",
        ]
        for identifier in sorted(measured):
            record = measured[identifier]
            organism = f" ({record.organism})" if getattr(record, "organism", None) else ""
            lines.append(
                f"| `{identifier}` | {record.value} {record.unit} | literature"
                f"{organism} | {record.citation} |"
            )
        reasons = dict(getattr(self.model, "not_found", {}) or {})
        for identifier in self.model.unmeasured:
            quantity = by_id.get(identifier)
            table = (quantity.table if quantity else None) or "no table"
            # THE RESOLVER'S OWN WORDS, NOT A SUMMARY OF THEM. It
            # distinguishes four outcomes -- the value exists in another
            # organism and was not substituted, it exists only in distant
            # ones, papers were found and no number extracted, or nothing
            # anywhere -- and "found nothing" is FALSE for two of them,
            # telling a reader to stop looking for a number that is in the
            # database.
            why = reasons.get(identifier) or f"searched the {table} table and found nothing"
            lines.append(
                f"| `{identifier}` | "
                f"{quantity.placeholder if quantity else '?'} "
                f"{quantity.unit if quantity else ''} | **placeholder** | "
                f"{why} |"
            )
        if self.model.unmeasured:
            # NOT "looked for and not found". The reasons column above may
            # say the value exists in four other species, or that papers
            # were found and no number extracted -- in which case something
            # WAS found, and a summary saying otherwise contradicts the
            # table it sits under.
            lines += [
                "",
                f"The {len(self.model.unmeasured)} placeholder(s) above are "
                f"the motif library's illustrative values, kept because the "
                f"search did not return one. The reason column says what "
                f"the search actually met, which is not always \"nothing\": "
                f"read it before concluding the measurement does not exist. "
                f"Any conclusion resting on one of these is a statement "
                f"about the library's value, not about this enzyme.",
            ]
        lines += self._condition_lines(measured)
        lines += self._disagreement_lines(measured)
        return lines

    def _condition_lines(self, measured: dict) -> List[str]:
        """The pH, temperature and buffer each value was measured under.

        WHY A CITED NUMBER WITHOUT THESE IS NOT ENOUGH
        ----------------------------------------------
        Lisa Jeske (BRENDA curation, DSMZ) named exactly this as what makes
        a resolved value meaningless without it: pH, temperature and buffer
        decide whether two values from two papers may be mixed at all. The
        `Measurement` record has carried them since it was written and the
        CSV export prints them in columns of their own; the composed
        report, the artefact a person actually reads, did not.

        It also checks the thing the conditions are FOR. Two constants
        pulled from two papers and put in one model describe an experiment
        nobody ran, and the project already has thresholds for when that
        matters -- `PH_UNITS_SERIOUS` (1.0) and `TEMPERATURE_C_SERIOUS`
        (10.0 C, from a Q10 of 2-3) in `model_compatibility`. They are read
        from there rather than restated, so one judgement does not become
        two.
        """
        stated = {
            identifier: record for identifier, record in measured.items()
            if record.assay_ph is not None
            or record.assay_temperature_c is not None
            or record.assay_buffer
        }
        if not stated:
            return []

        lines = ["", "### The conditions these were measured under", ""]
        for identifier in sorted(stated):
            record = stated[identifier]
            parts = []
            if record.assay_ph is not None:
                parts.append(f"pH {record.assay_ph:g}")
            if record.assay_temperature_c is not None:
                parts.append(f"{record.assay_temperature_c:g} °C")
            if record.assay_buffer:
                parts.append(f"in {record.assay_buffer}")
            unreported = getattr(record, "assay_unreported", ()) or ()
            suffix = (
                f" The source states it did not report: {', '.join(unreported)}."
                if unreported else ""
            )
            lines.append(f"- `{identifier}` — measured at {', '.join(parts)}.{suffix}")

        silent = sorted(set(measured) - set(stated))
        if silent:
            lines.append(
                f"- {', '.join(f'`{name}`' for name in silent)} — the source "
                f"stated no conditions. That is a fact about the paper, not "
                f"a gap in the search, and it cannot be assumed to match the "
                f"rows above."
            )

        lines += self._mixing_lines(stated)
        return lines

    def _mixing_lines(self, stated: dict) -> List[str]:
        """Whether the measured constants describe one experiment or several."""
        try:
            from caterva.checkout import literature_module

            compatibility = literature_module("model_compatibility")
            ph_serious = compatibility.PH_UNITS_SERIOUS
            temperature_serious = compatibility.TEMPERATURE_C_SERIOUS
        except Exception:  # noqa: BLE001 - a missing layer is not a wrong answer
            return []

        names = sorted(stated)
        if len(names) < 2:
            # Nothing to compare. Saying "the measured constants can be read
            # as describing comparable experiments" about a single constant
            # is a check that cannot fail, printed where a reader would take
            # it for one that did.
            return []

        clashes = []
        for i, first in enumerate(names):
            for second in names[i + 1:]:
                a, b = stated[first], stated[second]
                if a.assay_ph is not None and b.assay_ph is not None:
                    gap = abs(a.assay_ph - b.assay_ph)
                    if gap >= ph_serious:
                        clashes.append(
                            f"`{first}` and `{second}` differ by {gap:g} pH "
                            f"unit(s) ({a.assay_ph:g} against {b.assay_ph:g})"
                        )
                if (a.assay_temperature_c is not None
                        and b.assay_temperature_c is not None):
                    gap = abs(a.assay_temperature_c - b.assay_temperature_c)
                    if gap >= temperature_serious:
                        clashes.append(
                            f"`{first}` and `{second}` differ by {gap:g} °C "
                            f"({a.assay_temperature_c:g} against "
                            f"{b.assay_temperature_c:g})"
                        )
        comparable = sum(
            1 for name in names
            if stated[name].assay_ph is not None
            or stated[name].assay_temperature_c is not None
        )
        if not clashes:
            if comparable < 2:
                # Conditions are stated, but not the axes that can be
                # compared: two buffers alone do not make a comparison.
                return []
            return [
                "",
                f"No two of the {comparable} constants above differ by more "
                f"than the thresholds this project treats as serious "
                f"({ph_serious:g} pH unit, {temperature_serious:g} °C), so "
                "they can be read as describing comparable experiments. That "
                "is a check on the conditions the sources STATED, not a "
                "claim that the assays were otherwise alike.",
            ]
        return [
            "",
            "**These were not measured under the same conditions:**",
            "",
            *[f"- {clash}" for clash in clashes],
            "",
            f"A model built from them describes an experiment nobody ran. "
            f"The thresholds ({ph_serious:g} pH unit, {temperature_serious:g} "
            f"°C) are this project's stated judgements, in "
            f"`model_compatibility`; Q10 for enzyme-catalysed rates is "
            f"typically 2-3, so ten degrees is roughly a factor of two in "
            f"rate.",
        ]

    def _disagreement_lines(self, measured: dict) -> List[str]:
        """The rows the resolver ranked equal and did not pick.

        WHY THIS IS NOT OPTIONAL
        ------------------------
        BRENDA holds two equally well evidenced values of Km for EC 1.1.1.27
        and pyruvate in Homo sapiens: 0.03 mM and 0.398 mM. The resolver
        picks the lower and says the evidence does not justify picking. A
        report that printed the winner with its citation and stopped would
        present one paper's number as THE value while its own resolver had
        just reported a tie -- and it would look more authoritative than the
        placeholder case, not less, because it carries a reference.

        The lab-report path has printed this since it was written. The
        composed model did not until ADR 0178, which is the gap this closes.
        """
        disagreements = []
        for identifier in sorted(measured):
            record = measured[identifier]
            span = getattr(record, "disagreement", None)
            if span is None:
                continue
            low, high = span
            fold = high / low if low else float("inf")
            rows = [r for r in getattr(record, "alternatives", ()) if isinstance(r, dict)]
            values = {r.get("value") for r in rows if r.get("value") is not None}
            references = sorted({
                str(r["reference_id"]) for r in rows if r.get("reference_id")
            })

            # ONE PAPER REPORTING TWO VALUES IS NOT TWO PAPERS DISAGREEING.
            # BRENDA's Ki rows for EC 1.1.1.27 are both reference 739793:
            # the same publication, two measurements, most often different
            # conditions or a different inhibitor. Calling that "the
            # literature disagrees" would invent a controversy, and telling
            # the reader to decide "which paper you believe" would send them
            # to one paper to adjudicate itself.
            if len(references) == 1:
                what = (
                    f"one source (BRENDA ref {references[0]}) reports "
                    f"{len(values)} values"
                )
                why = (
                    "two rows from one publication usually differ in the "
                    "conditions or the exact substrate, so read that paper "
                    "before choosing"
                )
            else:
                what = (
                    f"{len(references)} sources report {len(values)} values"
                    + (f" (BRENDA ref {', '.join(references)})" if references else "")
                )
                why = "which one is right is a question about the papers"

            disagreements.append(
                f"- `{identifier}`: {what}, spanning **{low:g} to {high:g} "
                f"{record.unit}** ({fold:.3g}-fold). The model carries "
                f"{record.value:g} — the resolver's pick, not a verdict; "
                f"{why}."
            )
        if not disagreements:
            return []
        return [
            "",
            # Not "the literature disagrees": one of these cases is a single
            # paper reporting two rows, which is not a controversy.
            "### Where the evidence did not settle on one value",
            "",
            *disagreements,
            "",
            "These spreads are carried through to the model rather than "
            "averaged away. They are **not an uncertainty estimate**: the "
            "range is bounded by which rows happen to be in the database, "
            "not by any statement about the true value. A conclusion that "
            "changes across one of these ranges rests on a choice the "
            "evidence did not make for you.",
        ]

    def _resolvable_table(self) -> List[str]:
        """The unmeasured constants, ordered by how much the answer moves.

        WHY THE RANKING GOES IN THIS TABLE AND NOT IN A SECTION OF ITS OWN
        ------------------------------------------------------------------
        This table used to list twelve constants in construction order, and
        "go and measure twelve things" is not advice. The ranking is not a
        separate finding to be read afterwards -- it is the property that
        turns this table from a list into a plan, and a reader who stops at
        the table should already have it.

        Without a sensitivity report the table is printed in its old form
        rather than in a guessed order. An unranked list is honest; a list
        ordered by something other than what it claims is not.
        """
        rows = list(self.model.resolvable)
        if self.sensitivity is None:
            lines = ["| quantity | what it is | unit | source table |",
                     "|---|---|---|---|"]
            for quantity in rows:
                lines.append(
                    f"| `{quantity.parameter_id}` | "
                    f"{quantity.description or quantity.parameter_name} | "
                    f"{quantity.unit} | {quantity.table or '_no table_'} |"
                )
            return lines

        influence = {s.parameter: s for s in self.sensitivity.sensitivities}
        # Ranked first, unrankable last -- a constant the sensitivity run
        # skipped has not been judged unimportant, and must not be sorted as
        # though it scored zero.
        rows.sort(
            key=lambda q: (
                q.parameter_id not in influence,
                -abs(getattr(influence.get(q.parameter_id), "relative", 0.0)),
            )
        )
        lines = [
            "| quantity | what it is | unit | source table | influence |",
            "|---|---|---|---|---|",
        ]
        for quantity in rows:
            lines.append(
                f"| `{quantity.parameter_id}` | "
                f"{quantity.description or quantity.parameter_name} | "
                f"{quantity.unit} | {quantity.table or '_no table_'} | "
                f"{_influence_cell(influence.get(quantity.parameter_id))} |"
            )
        lines.append("")
        if self.sensitivity.sensitivities:
            lines.append(
                f"Ordered by influence on **{self.sensitivity.quantity}**: S "
                f"is the fractional change in it per fractional change in "
                f"the constant, so S = +2 means a 1% increase raises the "
                f"answer by 2%."
            )
            lines.append("")

        # WHAT THE READER SHOULD DO, which depends on what was found. A
        # table where nothing clears the act-on threshold must not be
        # captioned "measure the top of this list": at saturation the top of
        # the list is not worth measuring either, and the honest advice is
        # the opposite one.
        actionable = [
            s for s in self.sensitivity.sensitivities if not s.negligible
        ]
        law = getattr(self.sensitivity, "conserved_by", None)
        if law and actionable:
            # The steady state was pinned, so this ranks the settling time
            # instead. The reader has to be told, or `kcat` at S = -1 reads
            # as a claim about where the system lands rather than how fast
            # it gets there.
            lines.append(
                f"The steady state of this model is **not** what the rate "
                f"constants decide: `{law}` is conserved, so the destination "
                f"is fixed by the initial condition and every steady-state "
                f"sensitivity is zero. What the kinetics DO decide is how "
                f"fast it arrives, so the column above ranks influence on "
                f"the **{self.sensitivity.quantity}** instead. Measuring the "
                f"top of this list buys more than measuring the bottom of it."
            )
        elif actionable:
            lines.append(
                "Measuring the top of this list buys more than measuring "
                "the bottom of it."
            )
        elif not self.sensitivity.sensitivities:
            # Nothing was differentiated, which is not the same as
            # everything coming back small -- see the summary in
            # compose/sensitivity.py for the model that reaches this.
            lines.append(
                f"**No influence could be computed for any of these.** "
                f"Every parameter was skipped, so this table is unranked and "
                f"nothing here has been judged unimportant — nothing was "
                f"measured. The usual cause is a starting amount left at "
                f"zero, which leaves the mechanism switched off and its "
                f"answer at zero, and a relative sensitivity around zero is "
                f"undefined rather than small. Set the starting amounts "
                f"under **Yours to set** and ask again."
            )
        elif getattr(self.sensitivity, "conserved_by", None):
            # An all-zero ranking with a STRUCTURAL cause, not a kinetic
            # one. Captioning this as saturation would be a plausible wrong
            # reason attached to a correct number.
            lines.append(
                f"**No rate constant influences this answer at all**, and "
                f"the reason is structural: `{self.sensitivity.conserved_by}` "
                f"is conserved, which fixes this quantity at the total the "
                f"initial condition set. The constants decide how FAST the "
                f"system arrives, never WHERE. Nothing in this table is "
                f"worth measuring *for this question* — ask instead for the "
                f"settling time or the time course, which are the things "
                f"the kinetics do determine."
            )
        else:
            lines.append(
                f"**No constant here clears |S| = "
                f"{_negligible_influence():g}**, so measuring any single one "
                f"of them would not move this answer. That is what "
                f"saturation looks like — the mechanism is running flat out "
                f"and nothing upstream can push it further — and it is a "
                f"property of the illustrative values, which are themselves "
                f"the reason the model sits here. It is a reason to ground "
                f"the model, not a reason to leave it ungrounded."
            )
        lines.append("")
        lines.append(
            f"Two things this ordering is not. It is **local** — computed "
            f"at the library's illustrative values, and a constant that is "
            f"negligible there can dominate two decades away. And it ranks "
            f"influence, not **priority**: a constant with high influence "
            f"that BRENDA already holds is not work, while a modest one "
            f"nobody has ever measured is. A row marked _below the noise "
            f"floor_ (|S| < {self.sensitivity.resolution:.1g}) is one the "
            f"arithmetic could not tell from its own rounding, which is not "
            f"the same as one measured to be small."
        )
        return lines

    def behaviour_section(self) -> List[str]:
        lines = ["", "## Behaviour", ""]
        if self.stability is None:
            lines.append("No stability analysis was run.")
            return lines

        lines.append(self.stability.summary())

        if self.placeholder_warning():
            lines.append("")
            lines.append(self.placeholder_warning())
        return lines

    def trajectory_section(self) -> List[str]:
        if self.trajectory is None:
            return []
        lines = ["", "## Time course", "", self.trajectory.summary()]
        if not getattr(self.trajectory, "checked", True):
            # `sound` is vacuously True here, and this section used to say
            # nothing -- which beside a final state reads as verified. An
            # open system has no law to check; the reader is told so.
            lines.append("")
            lines.append(
                "**No independent check on this integration was possible.** "
                "The network has no conservation law, so nothing exact "
                "exists to compare the integrator's numbers against. This "
                "is not a fault in the run; it is the absence of the one "
                "thing that would have confirmed it."
            )
        elif not self.trajectory.sound:
            lines.append("")
            lines.append(
                "**The trajectory above should not be trusted.** A "
                "conservation law that is exact in the model did not hold "
                "during the integration, which means the integrator, not the "
                "model, produced those numbers."
            )
        lines += self._trajectory_plausibility()
        return lines

    def _trajectory_plausibility(self) -> List[str]:
        """Whether the run passed through a state a cell cannot be in.

        The conservation check above says whether the INTEGRATOR behaved.
        This says whether the MODEL did: a run can conserve every total
        exactly and still overshoot to fifty molar on its way to a
        sensible micromolar, and that spike is what a student will try to
        interpret. The steady-state check on the verdict page sees nothing
        wrong with it, because where the system ended is fine.
        """
        try:
            from .predictions import UNEXAMINED, check_trajectory
        except ImportError:  # pragma: no cover - flat import
            from predictions import (  # type: ignore[no-redef]
                UNEXAMINED, check_trajectory,
            )

        composition = getattr(
            getattr(self.model, "recognition", None), "composition", None
        )
        unit = getattr(composition, "concentration_unit", None)
        if not unit:
            return [
                "",
                "Whether this run stays inside what a cell can hold was NOT "
                "checked: the model declares no concentration unit, and a "
                "bound in molar compared against numbers in an unknown unit "
                "would be a guess.",
            ]

        proteins = ()
        if hasattr(composition, "protein_species"):
            proteins = tuple(sorted(composition.protein_species()))
        try:
            report = check_trajectory(
                self.trajectory, unit=str(unit), subject="this time course",
                proteins=proteins,
            )
        except Exception as exc:  # noqa: BLE001
            return [
                "",
                f"Whether this run stays inside what a cell can hold was NOT "
                f"checked: {type(exc).__name__}: {exc}",
            ]

        if report.verdict == UNEXAMINED:
            return ["", report.summary()]
        if not report.findings:
            # Said briefly. A clean result is worth one line, not a
            # paragraph a reader has to scan past to reach the sweeps.
            return [
                "",
                f"Every species stays inside what a cell can hold for the "
                f"whole run ({report.coverage}). A capacity check, not a "
                f"claim the curve is right.",
            ]
        return ["", "**Physical plausibility of the run:**", "", report.summary()]

    def sweeps_section(self) -> List[str]:
        if not self.sweeps:
            return []
        lines = ["", "## Parameter sweeps", ""]
        for report in self.sweeps:
            lines.append(f"### `{report.parameter}`")
            lines.append("")
            lines.append(report.summary())
            lines.append("")
        return lines

    # -- the judgement that needs two sections at once ----------------

    def placeholder_warning(self) -> Optional[str]:
        """The caveat that only makes sense beside the behaviour.

        A bistability claim is a different thing when every rate constant in
        the model is a placeholder. Put in the behaviour section rather than
        in provenance, because that is where a reader forms the belief it
        qualifies.
        """
        unmeasured = tuple(getattr(self.model, "unmeasured", ()) or ())
        count = len(unmeasured)
        if not count:
            return None
        # The denominator: a ComposedModel knows its resolvable set; a
        # ProvenancedModel knows what it measured, and the two sum.
        measured = getattr(self.model, "measured", None)
        if isinstance(measured, dict):
            # A ComposedModel's search results: id -> Measurement. Iterating
            # it yields ids, which have no `role`, and counted zero.
            total = count + len(measured)
        elif measured is not None:
            total = count + sum(
                1 for o in measured if getattr(o, "role", "") == "parameter"
            )
        else:
            total = len(getattr(self.model, "resolvable", ()) or ()) or count
        subject = getattr(self.model, "subject", None)
        # The caveat used to vanish the moment a subject was NAMED, with no
        # search run -- so a query mentioning an enzyme lost the one line
        # telling the reader its constants were still placeholders.
        why = (
            "because no enzyme was named" if not subject
            else f"because no search has been run for {subject!r}"
            if count == total and not getattr(self.model, "searched", False)
            else f"because the search for {subject!r} did not find them"
            if count == total
            else f"the search for {subject!r} did not find them"
        )
        scope = f"All {count}" if count == total else f"{count} of the {total}"
        return (
            f"**These conclusions are about the model's SHAPE, not about any "
            f"real system.** {scope} rate constants are the motif "
            f"library's illustrative values, {why}. "
            f"Whether a real instance of this mechanism behaves this way "
            f"depends on its actual constants, and this says nothing about "
            f"that. What it does say is what the mechanism CAN do — which is "
            f"the question a structural model is asked."
        )

    # -- assembly -----------------------------------------------------

    def markdown(self, *, footer: bool = True) -> str:
        lines = [
            f"# {self.model.network.name}",
            "",
            f"> {self.query}",
            "",
        ]
        lines += self.verdict_section()
        lines += self.structure_section()
        lines += self.invariants_section()
        lines += self.units_section()
        lines += self.provenance_section()
        lines += self.behaviour_section()
        lines += self.trajectory_section()
        lines += self.sweeps_section()
        if footer:
            lines += self.footer_section()
        return "\n".join(lines)

    def footer_section(self) -> List[str]:
        """The provenance footer, separable so it can stay LAST.

        The CLI appends analysis sections after the dossier, and an earlier
        version printed this in the middle of them -- a document that says
        "Built by Caterva..." and then carries on for three more pages. The
        footer is the last thing a reader should meet, so whoever assembles
        the document decides when to place it.
        """
        return [
            "",
            "---",
            "",
            "Built by Caterva's compositional model builder. The structure "
            "was recognised deterministically from the description — no "
            "language model was involved and no API key is required. "
            "Conservation laws are exact; steady states and sweeps are "
            "numerical, and say so where they appear.",
        ]


def dossier(
    query: str,
    *,
    subject: Optional[str] = None,
    analyse_stability: bool = True,
    simulate: bool = True,
    sweep_parameters: Sequence[str] = (),
    sweep_range: Tuple[float, float] = (0.1, 10.0),
    sweep_steps: int = 15,
    rank_unmeasured: bool = True,
    rank_against: Optional[str] = None,
    model: Any = None,
    validation: Any = None,
    robustness: Any = None,
    conclusion_name: Optional[str] = None,
) -> ModelDossier:
    """Compose a model and assemble everything known about it.

    `model`, `validation` and `robustness` EXIST BECAUSE THE VERDICT WAS
    CONTRADICTING THE SECTIONS BELOW IT. The CLI printed this dossier --
    whose verdict page said "validate: not run, robustness: not run" --
    and then ran `--validate` and `--robustness` as sections underneath
    it. One report, and its headline disagreed with its own body about
    what had happened. The verdict is formed here, so the only way for it
    to know is for the caller to compute those first and pass them in;
    `model` lets the caller compose once and hand the same object to
    both, rather than composing twice.
    """
    try:
        from .analysis import analyse
        from .bifurcation import logarithmic_values, sweep as run_sweep
        from .pipeline import compose
    except ImportError:  # pragma: no cover - flat import
        from analysis import analyse  # type: ignore[no-redef]
        from bifurcation import (  # type: ignore[no-redef]
            logarithmic_values, sweep as run_sweep,
        )
        from pipeline import compose  # type: ignore[no-redef]

    if model is None:
        model = compose(query, subject=subject)

    stability = None
    if analyse_stability:
        try:
            stability = analyse(model.network)
        except Exception as exc:  # noqa: BLE001
            # A failed analysis must not lose the structure, which is the
            # part that always works.
            stability = None
            model.recognition.composition.note(
                f"stability analysis did not run: {exc}"
            )

    trajectory = None
    if simulate:
        try:
            from .simulate import run as run_simulation
        except ImportError:  # pragma: no cover - flat import
            from simulate import run as run_simulation  # type: ignore[no-redef]
        try:
            trajectory = run_simulation(model)
        except Exception as exc:  # noqa: BLE001
            # The engine is optional. Structure, dimensions, invariants and
            # steady states are all available without it, and losing the
            # whole report because a time course could not run would be a
            # poor trade.
            model.recognition.composition.note(
                f"no time course: {exc}"
            )

    sensitivity = None
    if rank_unmeasured and model.resolvable:
        try:
            from .sensitivity import rank_unmeasured as rank
        except ImportError:  # pragma: no cover - flat import
            from sensitivity import rank_unmeasured as rank  # type: ignore[no-redef]
        # Which species to rank against. The last species of the last
        # reaction is the one the mechanism produces -- a cascade's bottom
        # tier, a binding motif's complex -- which is what a reader means by
        # "the answer". Named explicitly by the caller when that guess is
        # wrong, and the report says which species it ranked against rather
        # than leaving the choice implicit.
        target = rank_against or _default_target(model)
        if target is not None:
            try:
                sensitivity = rank(model, target)
                # WHEN THE STEADY STATE IS PINNED, RANK WHAT IS NOT.
                #
                # A closed system's destination is fixed by its conservation
                # law, so every steady-state sensitivity is zero and the
                # honest advice is "ask for the settling time instead". That
                # advice pointed at something one call away and did not make
                # it -- a gap wearing a recommendation's clothes. The
                # settling time IS determined by the kinetics, and for
                # substrate inhibition it ranks kcat at -1 and Km at +1,
                # which is the answer the reader came for.
                if sensitivity.conserved_by:
                    sensitivity = (
                        _settling_ranking(model, sensitivity.conserved_by)
                        or sensitivity
                    )
            except Exception as exc:  # noqa: BLE001
                # Every refusal in that module is a real one -- no unique
                # stable state, a continuum, a quantity that will not
                # evaluate -- and none of them should cost the reader the
                # rest of the report.
                model.recognition.composition.note(
                    f"no influence ranking: {exc}"
                )

    sweeps = []
    for parameter in sweep_parameters:
        try:
            sweeps.append(
                run_sweep(
                    model.network, parameter,
                    logarithmic_values(*sweep_range, steps=sweep_steps),
                )
            )
        except Exception:  # noqa: BLE001 - one failed sweep is not a failed report
            continue

    verdict = None
    try:
        from .verdict import form as form_verdict
    except ImportError:  # pragma: no cover - flat import
        from verdict import form as form_verdict  # type: ignore[no-redef]
    try:
        # The stability report goes in, so the page can say what the model
        # DOES. Without it every composed model got the same verdict, the
        # same concern and the same next step -- true of all eleven and
        # useless for telling any two apart.
        verdict = form_verdict(
            model, stability=stability, validation=validation,
            robustness=robustness, influence=sensitivity,
            conclusion_name=conclusion_name,
        )
    except Exception as exc:  # noqa: BLE001
        # The verdict is a reading of the other sections; losing it must not
        # cost the sections themselves.
        model.recognition.composition.note(f"no verdict page: {exc}")

    return ModelDossier(
        query=query, model=model, stability=stability, sweeps=tuple(sweeps),
        trajectory=trajectory, sensitivity=sensitivity, verdict=verdict,
    )


def _settling_ranking(model: Any, law: str) -> Optional[Any]:
    """Rank against how fast the system arrives, not where it lands.

    For a closed system the second question is the only one the rate
    constants answer. Returns `None` rather than raising if the settling
    time cannot be computed either -- the pinned steady-state report is
    still worth showing, and it explains itself.

    The returned report carries `conserved_by` forward so the table still
    says WHY it is ranking a settling time: a reader who sees kcat at -1
    without that sentence would reasonably think it was the steady state.
    """
    try:
        from .sensitivity import analyse, settling_time
    except ImportError:  # pragma: no cover - flat import
        from sensitivity import analyse, settling_time  # type: ignore[no-redef]

    from dataclasses import replace

    try:
        report = analyse(
            model.network,
            settling_time(),
            unmeasured=tuple(q.parameter_id for q in model.resolvable),
        )
    except Exception:  # noqa: BLE001 - the pinned report is still useful
        return None
    if not report.sensitivities:
        return None
    return replace(report, conserved_by=law)


def _negligible_influence() -> float:
    try:
        from .sensitivity import NEGLIGIBLE_INFLUENCE
    except ImportError:  # pragma: no cover - flat import
        from sensitivity import NEGLIGIBLE_INFLUENCE  # type: ignore[no-redef]
    return NEGLIGIBLE_INFLUENCE


def _influence_cell(entry: Any) -> str:
    """One row's influence, in the form that carries the most information.

    THE NUMBER, whenever there is one. An earlier version printed
    "negligible here" for every row of a saturated cascade, which is true
    and useless: the twelve constants span four orders of magnitude, from
    9e-5 down to 1e-9, and that spread IS the ranking. A column that
    collapses it to one word has thrown away everything the column was for.

    "Negligible" survives as a QUALIFIER on the number rather than as a
    replacement for it, and the one case with no number to print -- below
    the run's noise floor -- says so in those words, because there the
    number really would be meaningless.
    """
    if entry is None:
        return "_not ranked_"
    if entry.unresolvable:
        return "_below the noise floor_"
    if entry.negligible:
        return f"S = {entry.relative:+.2g} _(negligible)_"
    return f"**S = {entry.relative:+.2g}**"


def _default_target(model: Any) -> Optional[str]:
    """The species an influence ranking is about, when nobody says.

    THE MOTIF'S OWN DECLARATION, NOT A GUESS FROM THE REACTIONS. The first
    version of this took the last product of the last reaction, which for a
    phosphorylation cascade is the DEPHOSPHORYLATED form: the last reaction
    of the last tier is the phosphatase step, whose product is X, and the
    answer a reader means is Xp. It produced a confident ranking against the
    opposite of the question.

    The motifs already say which of their ports is a product -- `Port.role`
    -- so the last product port of the last motif placed is the deepest
    thing the mechanism makes. That is a stated property of the library
    rather than an inference from reaction order, and it reads correctly for
    the cases the reaction-order rule got wrong: a cascade's bottom tier Xp,
    and a competing enzyme's P rather than the enzyme itself.

    A binding motif declares no product -- it has partners and a COMPLEX --
    so products are tried first and complexes second. Without that fallback
    "reversible binding of a ligand to a receptor" got no ranking at all:
    `complex_AB` is plainly what a reader means by the answer, and returning
    `None` there was a gap rather than a refusal.

    `None` when no motif declares either, rather than any fallback to a
    first or last species. Ranking against an arbitrary species would put a
    confident ordering next to the wrong question, which is worse than no
    ordering -- and is exactly the failure this function already had once.
    """
    try:
        from .motifs import ROLE_COMPLEX, ROLE_PRODUCT
    except ImportError:  # pragma: no cover - flat import
        from motifs import ROLE_COMPLEX, ROLE_PRODUCT  # type: ignore[no-redef]

    instances = list(getattr(model.recognition.composition, "instances", ()))
    # Products across all instances first, then complexes across all of
    # them -- not "product or complex" per instance. A composition whose
    # LAST motif binds and whose earlier one produces should still rank
    # against the thing produced.
    for role in (ROLE_PRODUCT, ROLE_COMPLEX):
        for instance in reversed(instances):
            ports = instance.motif.ports_with_role(role)
            if ports:
                return instance.species_for(ports[-1].name)
    return None


__all__ = ["ModelDossier", "dossier"]
