"""Do these parameters belong in the same model?

THE JOB THIS DOES THAT NOBODY ELSE DOES
---------------------------------------
Assembling a kinetic model means scavenging constants from several papers.
A postdoc doing it by hand knows to check something software never does:
**whether the values compose.**

A Km measured in rat liver at pH 7.4 and 37 C and a kcat measured in
E. coli at pH 6.0 and 25 C are each perfectly good numbers with perfectly
good citations. Multiplied together they produce a Vmax that describes no
enzyme in any organism under any condition. Every individual provenance
check passes. The model is still wrong.

BRENDA can tell you each value's conditions. Tellurium and COPASI will
integrate whatever you give them. Neither asks whether the set is
mutually coherent, because neither has both halves. Caterva does:
`fallback_logic.KineticResult` carries the organism and the source tier,
and `assay_conditions.AssayConditions` carries pH, temperature and buffer.
This module is the missing judgement over a SET of them.

WHAT IT REPORTS, AND WHAT IT REFUSES TO REPORT
----------------------------------------------
It reports facts: these two values came from different organisms; these
were measured 12 C apart; this one's conditions were never published.

It does NOT compute a correction. A Q10 of 2-3 for enzymatic rates is a
real and citable rule of thumb, and it would be easy to multiply a kcat by
2.3 and present a "temperature-corrected" number. That would be a
fabricated measurement wearing a correction's clothes -- the exact defect
this codebase exists to refuse -- because the true Q10 for a specific
enzyme is itself a measured quantity nobody looked up. So the temperature
gap is reported, its consequence is stated in the direction and rough
magnitude the literature supports, and the arithmetic is left undone.

THE THIRD CATEGORY, WHICH IS THE POINT OF STRENDA
-------------------------------------------------
Findings are `blocking`, `serious` or **`unassessable`**.

That last one is not a weaker version of "fine". If a paper never reported
its assay temperature, the compatibility of its value with another cannot
be checked at all, and reporting silence as compatibility is how a model
becomes wrong quietly. Tipton et al. (2014) built the STRENDA standard
around exactly this, and Caterva already demotes a citation to `flagged`
for it. This carries that demotion up to the level of the whole model.

THRESHOLDS ARE JUDGEMENTS AND ARE MARKED AS SUCH
------------------------------------------------
`PH_UNITS_SERIOUS` and `TEMPERATURE_C_SERIOUS` below are stated judgements,
not measured constants. Each carries its reasoning. They are module-level
so they can be argued with rather than buried in a comparison.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

#: A pH difference at or beyond which two kinetic constants should not be
#: combined without comment.
#:
#: A JUDGEMENT, not a measurement. Enzyme activity follows a bell-shaped pH
#: profile set by the ionisation states of catalytic residues, so both Km
#: and kcat move with pH; one unit is a tenfold change in [H+] and is
#: comfortably enough to move a constant severalfold for many enzymes. The
#: true sensitivity is enzyme-specific and is itself a measured quantity,
#: which is why this flags rather than corrects.
PH_UNITS_SERIOUS = 1.0

#: A temperature difference at or beyond which the same applies.
#:
#: Also a judgement. Q10 for enzyme-catalysed rates is typically 2-3, so
#: ten degrees is roughly a doubling-to-tripling of rate constants. Chosen
#: as one Q10 interval because that is the span over which the rule of
#: thumb is stated, not because 10 is special.
TEMPERATURE_C_SERIOUS = 10.0


@dataclass(frozen=True)
class ParameterSource:
    """One resolved quantity, with everything needed to judge it.

    Deliberately a plain record rather than a reuse of `KineticResult`:
    this module must also accept a value the user measured themselves, or
    one from a registry that is not BRENDA, and tying it to one resolver's
    return type would make those second-class.
    """

    quantity: str
    value: Optional[float] = None
    unit: Optional[str] = None
    organism: Optional[str] = None
    ph: Optional[float] = None
    temperature_c: Optional[float] = None
    buffer: Optional[str] = None
    citation: Optional[str] = None
    #: True when this value came from a different organism than requested.
    cross_species: bool = False
    #: "literature" | "user" | "registry". A value the user measured is not
    #: judged against the literature's conditions -- it is their assay.
    origin: str = "literature"

    #: Fields the source states the original publication did not report,
    #: as opposed to fields Caterva simply has no value for.
    #:
    #: The conclusion is the same either way -- compatibility cannot be
    #: checked -- but the ACTION is not. "The 1974 paper did not report a
    #: pH" is permanent and tells a researcher to go and measure it. "We
    #: have no pH" may be our parser failing on a commentary format, which
    #: is a bug on our side and would be fixed rather than remeasured.
    #: Reporting the second as the first sends somebody to the bench over
    #: a regex.
    explicitly_unreported: Tuple[str, ...] = ()

    #: Every alternative row the resolver returned for this quantity, as the
    #: plain dicts `KineticResult.ensemble_candidates` carries them: value,
    #: unit, organism, reference_id, conditions, and -- since the assay
    #: window work -- ph and temperature_c on each row; since 2026-09-30
    #: also substrate, the parser's label for the row (the request's name
    #: when it named one, the row's compound when it did not).
    #:
    #: Deliberately Optional rather than "falsy and gone": the coercion
    #: result and the registry row carry no frontier AT ALL, which is a
    #: different fact from carrying an empty one. A critic can only demand
    #: that a value match the conditions of another when the first value's
    #: own literature offers a row at those conditions -- and nothing else
    #: in this record tells it whether one does. Attaching the pool here
    #: lets the critic SEE the alternative before it turns a mismatch into
    #: an actionable constraint, which is the whole difference between a
    #: constraint and a demotion (ADR 0171).
    candidates: Tuple[Any, ...] = ()
    #: The source row's own commentary (isoform, inhibition mode, assay).
    commentary: Optional[str] = None
    #: `KineticResult.evidence_only`: when the resolver was asked for an
    #: isoform or an inhibition mode, the rows it would have chosen among
    #: without them, its choice first. Empty otherwise. Read by `caterva
    #: compose` to say which row the request replaced and why; not a
    #: candidate for this value, which `candidates` holds.
    evidence_only: Tuple[Any, ...] = ()
    #: `KineticResult.mode_default`, as a plain dict (mode, model_substrate,
    #: row, modes_available): when the resolver was asked for no mode with a
    #: model's mode to compare, what it would have returned asked for that
    #: mode. None otherwise. Read by `caterva compose --any-mode` to name the
    #: row its default carries; like `evidence_only`, not a candidate.
    mode_default: Optional[Any] = None

    @property
    def conditions_stated(self) -> bool:
        return self.ph is not None and self.temperature_c is not None


@dataclass(frozen=True)
class Finding:
    """One reason this set of parameters may not belong together."""

    kind: str
    severity: str  # "blocking" | "serious" | "unassessable"
    quantities: Tuple[str, ...]
    detail: str

    def __str__(self) -> str:  # pragma: no cover - convenience only
        return f"[{self.severity}] {self.kind}: {self.detail}"


@dataclass(frozen=True)
class CompatibilityReport:
    findings: Tuple[Finding, ...]
    assessed: Tuple[str, ...]
    #: Quantities whose conditions were never published, so nothing about
    #: their compatibility could be established either way.
    unassessable: Tuple[str, ...]

    @property
    def blocking(self) -> Tuple[Finding, ...]:
        return tuple(f for f in self.findings if f.severity == "blocking")

    @property
    def coherent(self) -> bool:
        """No blocking or serious finding.

        `unassessable` findings do NOT make a set incoherent -- they mean
        the question could not be asked. Treating them as failure would
        make every model with one under-reported source unusable; treating
        them as success would be the silence-as-compatibility error. They
        are reported and left to the reader.
        """
        return not any(
            f.severity in ("blocking", "serious") for f in self.findings
        )

    def summary(self) -> str:
        if not self.assessed:
            return "No parameters to assess."
        parts: List[str] = []
        blocking = [f for f in self.findings if f.severity == "blocking"]
        serious = [f for f in self.findings if f.severity == "serious"]
        if blocking:
            parts.append(
                f"{len(blocking)} blocking: "
                + "; ".join(f.detail for f in blocking)
            )
        if serious:
            parts.append(
                f"{len(serious)} serious: "
                + "; ".join(f.detail for f in serious)
            )
        # Every unassessable FINDING, not just the unpublished-conditions
        # ones. There are now two kinds with different meanings -- an assay
        # condition nobody printed, and an organism nobody recorded -- and
        # summarising only the first made the second invisible on exactly
        # the query where it matters most: the one that named no organism.
        unassessable_findings = [
            f for f in self.findings if f.severity == "unassessable"
        ]
        if unassessable_findings:
            parts.append(
                f"{len(unassessable_findings)} thing(s) that could not be "
                f"checked either way: "
                + "; ".join(f.detail for f in unassessable_findings)
            )
        if not parts:
            return (
                f"All {len(self.assessed)} parameters are mutually "
                f"compatible: same organism, and assay conditions within "
                f"{PH_UNITS_SERIOUS} pH unit and {TEMPERATURE_C_SERIOUS:g} C."
            )
        return " | ".join(parts)


def _named_unreported(source: ParameterSource, field_name: str) -> bool:
    """Did the source explicitly say the publication omitted this field?

    Matches loosely because BRENDA writes "pH", "temperature" and
    "temperature not given" in the same list, and a reader who sees
    "temperature" in the unreported list means the same thing in all three.
    """
    wanted = field_name.strip().lower()
    return any(
        wanted in str(entry).strip().lower()
        for entry in source.explicitly_unreported
    )


def _literature(sources: Iterable[ParameterSource]) -> List[ParameterSource]:
    """Only values whose conditions are somebody else's to report.

    A value the user measured is their own assay and is not judged against
    a paper's conditions; combining it with literature is the normal case
    this tool exists to support, not a defect.
    """
    return [s for s in sources if s.origin == "literature"]


def _spread(
    values: Sequence[Tuple[str, float]]
) -> Optional[Tuple[float, str, float, str, float]]:
    """(spread, low_quantity, low, high_quantity, high) or None."""
    if len(values) < 2:
        return None
    low_q, low = min(values, key=lambda kv: kv[1])
    high_q, high = max(values, key=lambda kv: kv[1])
    return (high - low, low_q, low, high_q, high)


def assess(sources: Sequence[ParameterSource]) -> CompatibilityReport:
    """Judge whether a set of resolved parameters belongs in one model."""
    findings: List[Finding] = []
    literature = _literature(sources)
    assessed = tuple(s.quantity for s in sources)

    # -- organism coherence ------------------------------------------
    #
    # Blocking, not serious. Two constants from different species do not
    # describe one enzyme, and no assay condition makes them commensurate.
    # This is the check ADR 0024 already applies to a SINGLE value; a set
    # can be individually clean and jointly incoherent.
    by_organism: Dict[str, List[str]] = {}
    for source in literature:
        if source.organism:
            by_organism.setdefault(source.organism, []).append(source.quantity)
    if len(by_organism) > 1:
        described = "; ".join(
            f"{organism}: {', '.join(sorted(quantities))}"
            for organism, quantities in sorted(by_organism.items())
        )
        findings.append(
            Finding(
                kind="organism_mismatch",
                severity="blocking",
                quantities=tuple(
                    q for qs in by_organism.values() for q in sorted(qs)
                ),
                detail=(
                    f"values come from {len(by_organism)} different "
                    f"organisms ({described}). Combining them describes no "
                    f"enzyme in any of them."
                ),
            )
        )

    # A value with no organism recorded is not a value from a matching
    # organism -- it is one whose organism nobody wrote down.
    #
    # Found on real BRENDA data: `resolve_kinetic_value` called with an
    # empty organism matches every row in the table, returns the minimum
    # across all species, and reports the organism as "". Two such values
    # then look identical to this function and pass as compatible, because
    # there is nothing left to disagree about. That is the
    # silence-as-compatibility error the `unassessable` category exists to
    # prevent, appearing one field below where it was first caught.
    unattributed = [
        s.quantity for s in literature if not (s.organism or "").strip()
    ]
    if unattributed and len(literature) > 1:
        findings.append(
            Finding(
                kind="organism_unattributed",
                severity="unassessable",
                quantities=tuple(unattributed),
                detail=(
                    f"no organism is recorded for "
                    f"{', '.join(sorted(unattributed))}, so whether "
                    f"{'they belong' if len(unattributed) > 1 else 'it belongs'} "
                    f"with the other values cannot be checked. A kinetic "
                    f"constant is a property of an enzyme IN an organism; a "
                    f"value with no organism attached is not a measurement of "
                    f"anything in particular"
                ),
            )
        )

    for source in literature:
        if source.cross_species:
            findings.append(
                Finding(
                    kind="cross_species_value",
                    severity="serious",
                    quantities=(source.quantity,),
                    detail=(
                        f"{source.quantity} was transferred from "
                        f"{source.organism or 'another organism'}, not "
                        f"measured in the one requested"
                    ),
                )
            )

    # -- assay conditions --------------------------------------------
    stated_ph = [(s.quantity, s.ph) for s in literature if s.ph is not None]
    spread = _spread(stated_ph)
    if spread and spread[0] >= PH_UNITS_SERIOUS:
        gap, low_q, low, high_q, high = spread
        findings.append(
            Finding(
                kind="ph_mismatch",
                severity="serious",
                quantities=(low_q, high_q),
                detail=(
                    f"measured {gap:.1f} pH units apart ({low_q} at pH "
                    f"{low:g}, {high_q} at pH {high:g}). Enzyme activity "
                    f"follows a bell-shaped pH profile, so both Km and kcat "
                    f"move; Caterva reports the gap and does not correct for "
                    f"it, because the correction is itself enzyme-specific "
                    f"and unmeasured here."
                ),
            )
        )

    stated_t = [
        (s.quantity, s.temperature_c)
        for s in literature
        if s.temperature_c is not None
    ]
    spread = _spread(stated_t)
    if spread and spread[0] >= TEMPERATURE_C_SERIOUS:
        gap, low_q, low, high_q, high = spread
        findings.append(
            Finding(
                kind="temperature_mismatch",
                severity="serious",
                quantities=(low_q, high_q),
                detail=(
                    f"measured {gap:.0f} C apart ({low_q} at {low:g} C, "
                    f"{high_q} at {high:g} C). Q10 for enzyme-catalysed "
                    f"rates is typically 2-3, so this is roughly a "
                    f"doubling-to-tripling of rate constants between the two "
                    f"assays. Reported, not corrected: the true Q10 for this "
                    f"enzyme is itself a measured quantity nobody looked up."
                ),
            )
        )

    buffers = {
        s.buffer.strip().lower()
        for s in literature
        if s.buffer and s.buffer.strip()
    }
    if len(buffers) > 1:
        findings.append(
            Finding(
                kind="buffer_mismatch",
                severity="serious",
                quantities=tuple(
                    s.quantity for s in literature if s.buffer
                ),
                detail=(
                    f"measured in {len(buffers)} different buffers "
                    f"({', '.join(sorted(buffers))}). Ionic strength and "
                    f"specific ion effects move kinetic constants."
                ),
            )
        )

    # -- what could not be checked -----------------------------------
    #
    # Reported as its own category. Silence is not compatibility: an
    # unpublished assay temperature means the question cannot be asked,
    # which is exactly why STRENDA (Tipton et al. 2014) requires it and
    # why Caterva already demotes such a citation to `flagged`.
    unassessable = tuple(
        s.quantity for s in literature if not s.conditions_stated
    )
    for source in literature:
        if source.conditions_stated:
            continue
        missing = []
        if source.ph is None:
            missing.append("pH")
        if source.temperature_c is None:
            missing.append("temperature")
        stated_absent = [f for f in missing if _named_unreported(source, f)]
        if stated_absent == missing:
            attribution = (
                "which the source states the original publication did not "
                "report"
            )
        elif stated_absent:
            named = " and ".join(stated_absent)
            attribution = (
                f"of which {named} is stated unreported by the publication "
                f"and the rest is simply absent from the record Caterva read"
            )
        else:
            attribution = (
                "absent from the record Caterva read, which may mean the "
                "publication omitted them or that they were not captured"
            )
        findings.append(
            Finding(
                kind="conditions_unpublished",
                severity="unassessable",
                quantities=(source.quantity,),
                detail=(
                    f"{source.quantity}: {' and '.join(missing)} not "
                    f"available, {attribution}. Its compatibility with the "
                    f"other values cannot be checked either way (STRENDA, "
                    f"Tipton et al. 2014)"
                ),
            )
        )

    return CompatibilityReport(
        findings=tuple(findings),
        assessed=assessed,
        unassessable=unassessable,
    )


__all__ = [
    "ParameterSource",
    "Finding",
    "CompatibilityReport",
    "assess",
    "PH_UNITS_SERIOUS",
    "TEMPERATURE_C_SERIOUS",
]
