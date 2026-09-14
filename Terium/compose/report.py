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
            from Terium.core.network import describe_conservation_laws
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
        findings = self.model.recognition.composition.unit_findings()
        lines = ["", "## Dimensions", ""]
        if not findings:
            lines.append(
                "Every rate law balances, in dimension and in scale. Checked "
                "before compilation: a law with the wrong dimensions "
                "integrates perfectly well and is wrong by whatever factor "
                "the mistake introduced."
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
        if not self.trajectory.sound:
            lines.append("")
            lines.append(
                "**The trajectory above should not be trusted.** A "
                "conservation law that is exact in the model did not hold "
                "during the integration, which means the integrator, not the "
                "model, produced those numbers."
            )
        return lines

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
        if not self.model.structure_only:
            return None
        count = len(self.model.resolvable)
        if not count:
            return None
        return (
            f"**These conclusions are about the model's SHAPE, not about any "
            f"real system.** All {count} rate constants are the motif "
            f"library's illustrative values, because no enzyme was named. "
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
        "Built by Terrium..." and then carries on for three more pages. The
        footer is the last thing a reader should meet, so whoever assembles
        the document decides when to place it.
        """
        return [
            "",
            "---",
            "",
            "Built by Terrium's compositional model builder. The structure "
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
) -> ModelDossier:
    """Compose a model and assemble everything known about it."""
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
        verdict = form_verdict(model, stability=stability)
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
