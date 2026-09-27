"""Bakker's reliability axes, Python side.

WHY THERE ARE TWO IMPLEMENTATIONS
---------------------------------
The resolver is Python and the API server is TypeScript, and neither can
import the other. `Science-Agent-Pipeline/.../reliabilityScore.ts` is the
same rules for the API; this module is the same rules for the CLI.

That is a language boundary, not a design choice. What IS a choice is
whether the two are allowed to drift apart silently, and the answer is
`Tests/reliability_cases.json`: both test suites read the same cases and
assert the same grades. A rule added to one implementation fails the other's
test.

Same pattern as ADR 0003 (shared plausibility bounds), which exists because
two copies of a numeric constant went out of sync. A grading rule is worse
to duplicate than a constant: the divergence surfaces as two views quietly
disagreeing about the same measurement, rather than as an obviously wrong
number.

WHAT THE AXES ARE
-----------------
Professor Barbara Bakker (UMC Groningen), asked whether "flag it, don't use
it" is right for a value missing its assay conditions:

    "In practice, we chose the best option, but do not exclude anything a
     priori. [...] We gave each parameter a score based on its reliability
     and applicability, such as physiological pH and T, species [...] and
     completeness of assay description."

A measurement with a poor assay description is not evidence of NOTHING. It
is weak evidence, and weak evidence still constrains a range. The binary
flag this replaces discarded it, which is a loss of information dressed up
as caution.

THERE IS NO TOTAL, DELIBERATELY
-------------------------------
Combining the axes needs to know how a right-species value with a bad assay
description trades off against a thorough assay in the wrong species. Bakker
has been asked and has not yet answered. Inventing weights would fabricate
exactly the kind of number this project refuses to fabricate — and a single
score would be strictly less useful, because "0.61" cannot tell a reader
WHICH axis was weak, and that is the only part they can act on.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

NO_AGGREGATE_REASON = (
    "The three axes are reported separately and deliberately not combined. "
    "Weighting them against each other requires knowing how a right-species "
    "value with a poor assay description trades off against a thorough assay "
    "in the wrong species. That trade-off is an empirical finding Caterva "
    "does not have, and inventing it would fabricate the very kind of number "
    "this system refuses to fabricate. See ADR 0024, Decision 3."
)


@dataclass(frozen=True)
class Axis:
    grade: str
    reason: str


@dataclass(frozen=True)
class PhysiologicalReference:
    """The conditions the model is meant to represent.

    AN EXPERIMENTAL CONDITION, NOT A MEASURED QUANTITY, which is why it has
    no default. "Physiological pH and T" has no organism-independent value:
    7.4 and 37 C describe a mammal and misdescribe Thermus thermophilus,
    whose enzymes are measured near 70 C. Baking in a mammalian default
    would report a confident "far" for a thermophile assay that was ideal.

    Supplied by whoever builds the model, exactly as s0 and end are
    (ADR 0012/0013).
    """

    ph: float
    temperature_c: float
    basis: str
    ph_tolerance: float
    temperature_tolerance_c: float


@dataclass(frozen=True)
class ReliabilityScore:
    assay_completeness: Axis
    condition_proximity: Axis
    organism_match: Axis
    no_aggregate_reason: str = NO_AGGREGATE_REASON

    def as_pairs(self) -> tuple[tuple[str, str], ...]:
        """(axis name, grade) pairs, for the model-file annotation."""
        return (
            ("assay completeness", self.assay_completeness.grade),
            ("condition proximity", self.condition_proximity.grade),
            ("organism match", self.organism_match.grade),
        )


def _is_number(value: object) -> bool:
    """A real, finite number. `None` and NaN are absences, and 0 is not."""
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def grade_assay_completeness(
    ph: float | None,
    temperature_c: float | None,
    unreported: list[str] | None = None,
) -> Axis:
    has_ph = _is_number(ph)
    has_temp = _is_number(temperature_c)

    # "The source states it did not report pH" and "we failed to parse a pH"
    # are different facts, and only the first is a statement about the
    # literature. Both grade the same; the reason must not claim knowledge
    # of the paper that Caterva does not have.
    declared = (
        f" The source states it did not report: {', '.join(unreported)}."
        if unreported
        else ""
    )

    if has_ph and has_temp:
        return Axis(
            "complete",
            f"Assay reports pH {ph} and {temperature_c} C, meeting STRENDA's "
            "minimum. The measurement can be compared against another lab's "
            "figure." + declared,
        )
    if has_ph or has_temp:
        present = f"pH {ph}" if has_ph else f"{temperature_c} C"
        missing = "temperature" if has_ph else "pH"
        return Axis(
            "partial",
            f"Assay reports {present} but no {missing}. Weak evidence rather "
            "than none: the value constrains a plausible range, and cannot be "
            "reproduced exactly." + declared,
        )
    return Axis(
        "absent",
        "Assay reports neither pH nor temperature. Km moves with both, so this "
        "value cannot be reproduced or compared, and cannot be placed on a "
        "scale relative to another measurement." + declared,
    )


def grade_condition_proximity(
    ph: float | None,
    temperature_c: float | None,
    reference: PhysiologicalReference | None,
) -> Axis:
    if reference is None:
        return Axis(
            "not_assessed",
            "No reference conditions were supplied, so proximity was not "
            "assessed. 'Physiological' has no organism-independent value -- pH "
            "7.4 and 37 C describe a mammal and misdescribe a thermophile -- so "
            "the reference is stated by whoever builds the model rather than "
            "assumed here (ADR 0012/0013).",
        )

    has_ph = _is_number(ph)
    has_temp = _is_number(temperature_c)
    if not has_ph and not has_temp:
        return Axis(
            "not_assessed",
            "The source reports neither pH nor temperature, so there is nothing "
            f"to compare against the reference ({reference.basis}). This is a "
            "gap in the source, not a judgement about the value.",
        )

    deviations: list[str] = []
    far = False

    if has_ph:
        delta = abs(float(ph) - reference.ph)
        if delta > reference.ph_tolerance:
            far = True
            deviations.append(
                f"pH {ph} is {delta:.2f} from the reference {reference.ph} "
                f"(tolerance +/-{reference.ph_tolerance})"
            )
    if has_temp:
        delta = abs(float(temperature_c) - reference.temperature_c)
        if delta > reference.temperature_tolerance_c:
            far = True
            deviations.append(
                f"{temperature_c} C is {delta:.1f} C from the reference "
                f"{reference.temperature_c} C (tolerance "
                f"+/-{reference.temperature_tolerance_c})"
            )

    # Graded on what IS reported. The unreported half is the completeness
    # axis's business; penalising it here too would make one gap look like
    # two.
    scope = (
        ""
        if has_ph and has_temp
        else (" (temperature unreported)" if has_ph else " (pH unreported)")
    )

    if far:
        return Axis(
            "far",
            "Measured away from the modelled conditions: "
            f"{'; '.join(deviations)}{scope}. Reference basis: {reference.basis}.",
        )
    return Axis(
        "near",
        f"Measured within tolerance of the modelled conditions{scope}. "
        f"Reference basis: {reference.basis}.",
    )


def grade_organism_match(
    requested_organism: str | None,
    measured_organism: str | None,
    cross_species: bool,
    relatedness: dict | None,
) -> Axis:
    if not cross_species and measured_organism and requested_organism:
        return Axis(
            "exact", f"Measured in {measured_organism}, the organism asked about."
        )

    measured = measured_organism or "an unnamed organism"
    requested = requested_organism or "the organism asked about"

    if relatedness is None:
        return Axis(
            "unknown",
            f"Measured in {measured} rather than {requested}, and no relatedness "
            "verdict accompanied the value. Absence of a verdict is not evidence "
            "of a match.",
        )

    status = relatedness.get("status")

    if status == "close_enough":
        shared_rank = relatedness.get("shared_rank")
        shared_name = relatedness.get("shared_name")
        shared = (
            f" They share the {shared_rank} {shared_name}."
            if shared_rank and shared_name
            else ""
        )
        return Axis(
            "related",
            f"Measured in {measured}, not {requested}.{shared} Relatedness is "
            "not kinetic similarity: this value is still not a measurement of "
            f"{requested}.",
        )

    # The resolver's reason is PREFIXED, never returned bare.
    #
    # A verdict can arrive with a reason as short as "NCBI unreachable",
    # which explains the cause and not the consequence. A reader seeing that
    # alone next to a grade has been told what went wrong and not what it
    # means for the number in front of them -- and the consequence is the
    # part they act on.
    detail = (relatedness.get("reason") or "").strip()
    suffix = f" ({detail})" if detail else ""

    if status == "too_distant":
        return Axis(
            "distant",
            f"Measured in {measured}, not {requested}. The organisms are too "
            f"distantly related for the value to transfer{suffix}.",
        )

    return Axis(
        "unknown",
        f"Measured in {measured}, not {requested}. Relatedness could not be "
        f"determined, which is not the same as a match{suffix}.",
    )


def score_reliability(
    *,
    ph: float | None = None,
    temperature_c: float | None = None,
    unreported: list[str] | None = None,
    reference: PhysiologicalReference | None = None,
    requested_organism: str | None = None,
    measured_organism: str | None = None,
    cross_species: bool = False,
    relatedness: dict | None = None,
) -> ReliabilityScore:
    return ReliabilityScore(
        assay_completeness=grade_assay_completeness(ph, temperature_c, unreported),
        condition_proximity=grade_condition_proximity(ph, temperature_c, reference),
        organism_match=grade_organism_match(
            requested_organism, measured_organism, cross_species, relatedness
        ),
    )
