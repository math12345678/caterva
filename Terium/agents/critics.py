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
  pH / temperature
  mismatch            -> CONSTRAINT when the frontier permits it and only
                         one value can be re-selected to the other's
                         conditions (ADR 0171). The resolver already returns
                         every row it considered, graded; the critic checks
                         whether one of those rows sits inside the other
                         value's conditions, and only then emits an
                         `assay_window` requirement the scout can actually
                         satisfy by re-selecting among its own rows -- never
                         by inventing a number. When NO row is inside either
                         reference the mismatch stays a finding (nothing a
                         re-search could fix); when rows are inside BOTH,
                         it stays a finding too (two values could move and
                         neither is privileged to choose).
  buffer mismatch     -> finding only. The frontier carries no buffer axis,
                         so no re-selection could satisfy a buffer window.
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
    from .assay_window import within_window, window_requirement
    from .blackboard import View
    from .constraints import ANY_SUBJECT, Constraint
    from .protocol import AgentResult
    from .scouts import param_key
except ImportError:  # pragma: no cover - flat import
    from assay_window import within_window, window_requirement  # type: ignore[no-redef]
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
            if finding.kind in ("ph_mismatch", "temperature_mismatch"):
                constraint, note = self._condition_constraint(sources, finding)
                if constraint is not None and constraint not in view.constraints:
                    constraints.append(constraint)
                if note is not None:
                    notes.append(note)
            elif finding.kind in ("buffer_mismatch", "conditions_unpublished"):
                notes.append(str(finding))

        return AgentResult(
            writes={COMPATIBILITY_KEY: report},
            constraints=tuple(constraints),
            notes=tuple(notes),
        )

    def _within_window_candidate(
        self, source: Optional[Any], anchor: Optional[Any]
    ) -> bool:
        """Whether `source`'s own frontier offers a row inside `anchor`'s
        conditions.

        The check that decides whether a mismatch is fixable at all. The
        frontier is the set of rows the resolver itself already returned
        and graded; "can this value move" means "has the literature it
        found actually measured it there", and nothing in this method
        invents a number that sits in the window.
        """
        if source is None or anchor is None:
            return False
        if anchor.ph is None and anchor.temperature_c is None:
            return False
        return any(
            within_window(
                candidate,
                reference_ph=anchor.ph,
                reference_temperature_c=anchor.temperature_c,
            )
            for candidate in getattr(source, "candidates", ()) or ()
        )

    def _condition_constraint(
        self, sources: Sequence[Any], finding: Any
    ) -> Tuple[Optional[Constraint], Optional[str]]:
        """One pH/temperature finding reduced to a window constraint, or
        nothing with the note explaining why it stayed a finding.

        Exactly three outcomes, and which one is which is stated rather than
        left to the reader:

          * exactly one value's frontier sits inside the other's conditions
            -> CONSTRAINT on that value, demanding the other's conditions.
          * neither does -> the mismatch is not fixable by re-search, so it
            stands as a finding.
          * both do -> either could be re-selected and neither is privileged.
            Emitting a side would be an invisible scientific decision, which
            is the class of thing this module exists to remove; the pair
            stays a finding and the reader is told why.
        """
        srcs = {s.quantity: s for s in sources}
        quantities = tuple(finding.quantities)
        if len(quantities) != 2:
            return None, str(finding)
        mover, anchor = quantities
        a_is_anchor, b_is_anchor = srcs.get(anchor), srcs.get(mover)
        if a_is_anchor is None or b_is_anchor is None:
            # A mismatch with a gap in it is not fixable by re-selection --
            # the missing value has no frontier to re-select from.
            return None, str(finding)
        mover_moves = self._within_window_candidate(b_is_anchor, a_is_anchor)
        anchor_moves = self._within_window_candidate(a_is_anchor, b_is_anchor)

        if mover_moves and not anchor_moves:
            requirement = window_requirement(
                ph=a_is_anchor.ph, temperature_c=a_is_anchor.temperature_c
            )
            return (
                Constraint(
                    kind="assay_window",
                    subject=mover,
                    requirement=requirement,
                    reason=(
                        f"{finding.detail} -- {mover}'s own literature "
                        f"offers a row inside {anchor}'s conditions "
                        f"({requirement}), so the frontier can satisfy the "
                        f"mismatch by re-selection; {anchor} cannot return "
                        f"the favour, so it is the reference."
                    ),
                    raised_by=self.name,
                ),
                None,
            )
        if anchor_moves and not mover_moves:
            requirement = window_requirement(
                ph=b_is_anchor.ph, temperature_c=b_is_anchor.temperature_c
            )
            return (
                Constraint(
                    kind="assay_window",
                    subject=anchor,
                    requirement=requirement,
                    reason=(
                        f"{finding.detail} -- {anchor}'s own literature "
                        f"offers a row inside {mover}'s conditions "
                        f"({requirement}), so the frontier can satisfy the "
                        f"mismatch by re-selection; {mover} cannot return "
                        f"the favour, so it is the reference."
                    ),
                    raised_by=self.name,
                ),
                None,
            )
        if mover_moves and anchor_moves:
            return None, (
                f"{finding.detail} Both values have a row inside the "
                f"other's conditions, so either could be re-selected and "
                f"neither is privileged to choose; Terrium will not pick "
                f"one. State the conditions the model should be built at, "
                f"or accept the finding."
            )
        return None, f"{finding.detail} Neither value's literature offers a row inside the other's conditions, so no re-search could remove this mismatch; it stands as a finding."

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
