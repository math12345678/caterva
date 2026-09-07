"""Critics: the agents that turn a finding into a requirement.

The pipeline this replaces reports that a model's constants do not compose
and stops there. A critic here does the other half -- it emits a
`Constraint`, the scouts re-search inside it, and the run converges on a set
that holds together or on a precise statement of why none exists.

WHEN A FINDING BECOMES A CONSTRAINT
-----------------------------------
Only when some agent can act on it. That is a real restriction and it is
what keeps the loop honest:

  organism mismatch   -> CONSTRAINT. A scout can search one organism.
  cross-species value -> CONSTRAINT. A scout can decline the transfer.
  pH / temperature /
  buffer mismatch     -> finding only. `resolve_kinetic_value` selects a row
                         by evidence rank and exposes no condition filter,
                         so a pH requirement would be a demand nothing can
                         satisfy. Reported, and named below as the extension
                         that would make it actionable.
  unpublished
  conditions          -> finding only, and permanently so. No search finds a
                         number the 1974 paper did not print.

A critic that emitted an unactionable constraint would look more capable and
would spend rounds asking for something no agent can deliver.

CHOOSING THE ORGANISM TO REQUIRE
--------------------------------
The one the user asked for, when any value was found in it. Otherwise the
one that most values came from. On a tie with no requested organism, NO
constraint is emitted and the mismatch stands as blocking -- picking a
side by list order would be an invisible scientific decision, which is the
class of thing this codebase exists to remove.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

try:
    from .blackboard import View
    from .constraints import ANY_SUBJECT, Constraint
    from .protocol import AgentResult
    from .scouts import param_key
except ImportError:  # pragma: no cover - flat import
    from blackboard import View  # type: ignore[no-redef]
    from constraints import ANY_SUBJECT, Constraint  # type: ignore[no-redef]
    from protocol import AgentResult  # type: ignore[no-redef]
    from scouts import param_key  # type: ignore[no-redef]

COMPATIBILITY_KEY = "compatibility"
STRUCTURE_KEY = "structure"


def _assess():
    try:
        from Tests.model_compatibility import assess  # type: ignore
        return assess
    except ImportError:
        from model_compatibility import assess  # type: ignore
        return assess


@dataclass(frozen=True)
class CoherenceCritic:
    """Judges the resolved set, and requires what would fix it."""

    quantities: Tuple[str, ...]
    #: The organism the user asked about, when they named one.
    requested_organism: Optional[str] = None

    name: str = "critic:coherence"

    @property
    def reads(self) -> Tuple[str, ...]:
        return tuple(param_key(q) for q in self.quantities)

    @property
    def writes(self) -> Tuple[str, ...]:
        return (COMPATIBILITY_KEY,)

    def run(self, view: View) -> AgentResult:
        assess = _assess()
        resolutions = [
            view[param_key(q)] for q in self.quantities if view.has(param_key(q))
        ]
        sources = [r.source for r in resolutions if r.source is not None]
        report = assess(sources)

        constraints: List[Constraint] = []
        notes: List[str] = []

        already_required = {
            c.requirement
            for c in view.constraints_of_kind("organism")
        }

        if any(f.kind == "organism_mismatch" for f in report.findings):
            target = self._organism_to_require(sources)
            if target is None:
                notes.append(
                    "Values come from several organisms with no majority and "
                    "no organism was requested, so Terrium will not choose "
                    "one for you: name the organism and the search will run "
                    "again inside it."
                )
            elif target not in already_required:
                constraints.append(
                    Constraint(
                        kind="organism",
                        subject=ANY_SUBJECT,
                        requirement=target,
                        reason=(
                            "the resolved values came from more than one "
                            "organism, which describes no enzyme in any of them"
                        ),
                        raised_by=self.name,
                    )
                )

        for finding in report.findings:
            if finding.kind == "cross_species_value":
                for quantity in finding.quantities:
                    constraint = Constraint(
                        kind="organism",
                        subject=quantity,
                        requirement=self.requested_organism or "",
                        reason=finding.detail,
                        raised_by=self.name,
                    )
                    if constraint.requirement and constraint not in view.constraints:
                        constraints.append(constraint)

        for finding in report.findings:
            if finding.kind in (
                "ph_mismatch",
                "temperature_mismatch",
                "buffer_mismatch",
                "conditions_unpublished",
            ):
                notes.append(str(finding))

        return AgentResult(
            writes={COMPATIBILITY_KEY: report},
            constraints=tuple(constraints),
            notes=tuple(notes),
        )

    def _organism_to_require(
        self, sources: Sequence[Any]
    ) -> Optional[str]:
        organisms = [s.organism for s in sources if s.organism and s.origin == "literature"]
        if not organisms:
            return None
        counts = Counter(organisms)
        if self.requested_organism and self.requested_organism in counts:
            return self.requested_organism
        ordered = counts.most_common()
        if len(ordered) > 1 and ordered[0][1] == ordered[1][1]:
            return None  # a tie is not a majority; see the module docstring
        return ordered[0][0]


@dataclass(frozen=True)
class StructureCritic:
    """Checks the model itself, in parallel with the literature search.

    Structural defects are not fixable by re-searching, so this emits no
    constraints. It is a separate agent rather than a step because it needs
    only the network: there is no reason for a stoichiometry check to wait
    on BRENDA, and in the chain this replaces it did.
    """

    name: str = "critic:structure"
    reads: Tuple[str, ...] = ("network",)
    writes: Tuple[str, ...] = (STRUCTURE_KEY,)

    def run(self, view: View) -> AgentResult:
        network = view["network"]
        problems = tuple(network.problems())
        laws = network.conservation_laws()

        notes: List[str] = list(problems)
        if laws:
            notes.append(
                f"{len(laws)} conservation law(s) hold in this network; the "
                f"simulation is checked against them rather than assumed to "
                f"respect them."
            )
        return AgentResult(
            writes={
                STRUCTURE_KEY: {
                    "problems": problems,
                    "conservation_laws": laws,
                    "well_posed": not problems,
                }
            },
            notes=tuple(notes),
        )


__all__ = [
    "CoherenceCritic",
    "StructureCritic",
    "COMPATIBILITY_KEY",
    "STRUCTURE_KEY",
]
