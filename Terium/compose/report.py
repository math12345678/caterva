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

    # -- sections -----------------------------------------------------

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
            lines.append("| quantity | what it is | unit | source table |")
            lines.append("|---|---|---|---|")
            for quantity in self.model.resolvable:
                lines.append(
                    f"| `{quantity.parameter_id}` | "
                    f"{quantity.description or quantity.parameter_name} | "
                    f"{quantity.unit} | {quantity.table or '_no table_'} |"
                )
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

    def markdown(self) -> str:
        lines = [
            f"# {self.model.network.name}",
            "",
            f"> {self.query}",
            "",
        ]
        lines += self.structure_section()
        lines += self.invariants_section()
        lines += self.units_section()
        lines += self.provenance_section()
        lines += self.behaviour_section()
        lines += self.sweeps_section()
        lines += [
            "",
            "---",
            "",
            "Built by Terrium's compositional model builder. The structure "
            "was recognised deterministically from the description — no "
            "language model was involved and no API key is required. "
            "Conservation laws are exact; steady states and sweeps are "
            "numerical, and say so where they appear.",
        ]
        return "\n".join(lines)


def dossier(
    query: str,
    *,
    subject: Optional[str] = None,
    analyse_stability: bool = True,
    sweep_parameters: Sequence[str] = (),
    sweep_range: Tuple[float, float] = (0.1, 10.0),
    sweep_steps: int = 15,
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

    return ModelDossier(
        query=query, model=model, stability=stability, sweeps=tuple(sweeps),
    )


__all__ = ["ModelDossier", "dossier"]
