"""Which of your numbers is the conclusion resting on, and how good is it?

THE QUESTION NOBODY CAN CURRENTLY ANSWER
----------------------------------------
A researcher assembles a model from six papers. Some parameters were
measured in the organism they care about; some come from a relative;
some are their own bench values; one is a guess nobody has admitted to.
The model runs and produces a curve.

Which of those numbers is the curve actually resting on?

There is no tool that answers this, because answering it needs two things
that live in different places. COPASI computes sensitivities and knows
nothing about where a value came from. BRENDA knows exactly where a value
came from and cannot run a model. Terrium has both: `sensitivity.py`
measures influence, `network_provenance.py` records origin, and this module
puts them side by side.

    the three parameters this result depends on
    ... and two of them were measured in a different organism

That sentence is the product. It tells a researcher what to go and measure,
which is a better answer than a curve.

WHAT THIS DELIBERATELY DOES NOT DO
----------------------------------
It does not compute a risk score.

Combining "peak relative sensitivity 3.0" with "cross-species citation"
into a single number would require weights -- is a cross-species value
worth 0.7 of a bad one? -- and those weights would be invented. This
repository has spent its whole history removing invented numbers; adding a
scoring system whose constants nobody measured, to rank the trustworthiness
of measurements, would be the most ironic possible place to put one.

So influence stays measured, provenance stays categorical, and they are
reported together without being multiplied. The ranking is by influence
alone, which IS measured. The provenance tier is shown beside it and the
reader does the combining -- which they are qualified to do and this module
is not.

The one judgement made here is the `INFLUENCE_FLOOR` below, and it is
stated rather than buried.
"""

from __future__ import annotations


def _package_path_missing(exc: ModuleNotFoundError) -> bool:
    """See Terium/core/import_mode.py. Inlined deliberately: this
    guards the import machinery itself, so it cannot import a
    helper to do its job."""
    name = getattr(exc, "name", None)
    return bool(name) and (name == "Terium" or name.startswith("Terium."))


from dataclasses import dataclass
from typing import Dict, List, Mapping, Optional, Tuple

try:
    from Terium.core.network import ReactionNetwork
    from Terium.core.network_provenance import QuantitySource
    from Terium.core.sensitivity import (
        QuantitySensitivity,
        SensitivityReport,
    )
except ModuleNotFoundError as _exc:  # flat mode: Terium/ on sys.path
    if not _package_path_missing(_exc):
        # A missing THIRD-PARTY dependency. Flat mode cannot fix it, and
        # retrying replaces the real reason with a confusing
        # 'No module named core'. See Terium/core/import_mode.py.
        raise
    from core.network import ReactionNetwork  # type: ignore[no-redef]
    from core.network_provenance import QuantitySource  # type: ignore[no-redef]
    from core.sensitivity import (  # type: ignore[no-redef]
        QuantitySensitivity,
        SensitivityReport,
    )


#: Below this peak relative sensitivity, a quantity is reported as not
#: worth measuring more carefully.
#:
#: 0.01 means: a 1% change in this quantity moves every species by less
#: than 0.01% at every time point. It is a stated judgement, not a measured
#: constant, and it is here rather than inline so it can be argued with.
#:
#: The reason for a floor at all: without one, a researcher is handed a
#: ranked list of every parameter and told to improve all of them, which is
#: the same as being told nothing. The reason for THIS floor: 0.01 is two
#: orders of magnitude above the integration noise this can resolve, so
#: anything under it is not a claim this method can make.
INFLUENCE_FLOOR = 0.01


#: How well-sourced a quantity is, as an ORDERED category. No numbers.
#:
#: The order is the one `provenance.ts` already enforces elsewhere: a value
#: measured in the organism asked about beats one transferred from another
#: species, and anything the user measured themselves is as good as their
#: own bench, which this module is in no position to second-guess.
TIER_MEASURED_HERE = "measured in this assay (yours)"
TIER_LITERATURE_MATCHED = "literature, organism and conditions matched"
TIER_LITERATURE_FLAGGED = "literature, but flagged"
TIER_UNSOURCED = "no source"

TIER_ORDER: Tuple[str, ...] = (
    TIER_LITERATURE_MATCHED,
    TIER_MEASURED_HERE,
    TIER_LITERATURE_FLAGGED,
    TIER_UNSOURCED,
)


def classify_source(source: Optional[QuantitySource]) -> str:
    """Which tier a quantity's source falls in.

    Deliberately coarse. A finer scale would imply a precision about
    trustworthiness that the underlying records do not carry.
    """
    if source is None:
        return TIER_UNSOURCED
    if source.origin == "user":
        return TIER_MEASURED_HERE
    if source.origin == "resolved":
        citation = (source.citation or "").lower()
        note = (source.note or "").lower()
        blob = f"{citation} {note}"
        # The words this codebase already uses for a demoted citation:
        # `citationStatus: "flagged"` (ADR 0021's STRENDA demotion) and the
        # cross-species tier (ADR 0024). Read from the record rather than
        # re-derived, so the two cannot disagree about what "flagged" means.
        if "flagged" in blob or "cross-species" in blob or "cross species" in blob:
            return TIER_LITERATURE_FLAGGED
        return TIER_LITERATURE_MATCHED
    # `llm` and `default` never reach here -- compile_with_provenance
    # refuses them -- but a tier is returned rather than an exception so a
    # caller auditing a rejected model still gets a readable report.
    return TIER_UNSOURCED


@dataclass(frozen=True)
class AuditedQuantity:
    quantity: str
    sensitivity: QuantitySensitivity
    tier: str
    citation: Optional[str]

    @property
    def influential(self) -> bool:
        return self.sensitivity.peak >= INFLUENCE_FLOOR

    @property
    def worth_measuring(self) -> bool:
        """Influential AND not already the best it can be.

        The two conditions are reported separately everywhere else in this
        module; this is the one place they are combined, and only into a
        boolean -- never into a score.
        """
        return self.influential and self.tier in (
            TIER_LITERATURE_FLAGGED,
            TIER_UNSOURCED,
        )


@dataclass(frozen=True)
class ModelAudit:
    model: str
    quantities: Tuple[AuditedQuantity, ...]
    caveats: Tuple[str, ...]
    #: Quantities the model HAS but this analysis could not rank, with why.
    #:
    #: Carried explicitly because the alternative is a denominator that
    #: silently shrinks. A first version reported "5 of 5 quantities
    #: control this result" for a model with seven, having dropped the two
    #: it could not rank -- which reads as full coverage of a model that
    #: was two-sevenths unexamined.
    unranked: Tuple[Tuple[str, str], ...] = ()

    @property
    def influential(self) -> Tuple[AuditedQuantity, ...]:
        return tuple(q for q in self.quantities if q.influential)

    @property
    def to_measure(self) -> Tuple[AuditedQuantity, ...]:
        """What to go and do, in the order it matters."""
        return tuple(q for q in self.quantities if q.worth_measuring)

    def summary(self) -> str:
        """The sentence a researcher reads.

        Deliberately says how many quantities the result does NOT depend
        on as well: 'you can stop worrying about these eleven' is half the
        value, and a report that only ever adds to someone's workload gets
        closed.
        """
        ranked = len(self.quantities)
        total = ranked + len(self.unranked)
        influential = self.influential
        weak = self.to_measure

        # Stated whenever it is not the whole model, so "N of M" is never
        # read as coverage the analysis did not have.
        unranked_note = (
            ""
            if not self.unranked
            else (
                f" {len(self.unranked)} of the model's {total} quantities "
                f"could not be ranked ("
                + "; ".join(f"{q}: {why}" for q, why in self.unranked)
                + ")."
            )
        )

        if not influential:
            return (
                f"{self.model}: none of the {ranked} ranked quantities "
                f"measurably changes this result near these values. Either "
                f"the model is insensitive here, or the run is too short to "
                f"show it." + unranked_note
            )

        head = (
            f"{self.model}: {len(influential)} of {ranked} ranked quantit"
            f"{'y' if ranked == 1 else 'ies'} measurably control this result "
            f"({', '.join(q.quantity for q in influential)}); the other "
            f"{ranked - len(influential)} do not." + unranked_note
        )
        if not weak:
            return head + " Every one of them is matched literature or your own measurement."
        return (
            head
            + f" {len(weak)} of the influential ones "
            f"{'is' if len(weak) == 1 else 'are'} weakly sourced: "
            + "; ".join(f"{q.quantity} ({q.tier})" for q in weak)
            + ". Those are the measurements that would most change what you "
            "can claim."
        )


def audit(
    network: ReactionNetwork,
    report: SensitivityReport,
    sources: Mapping[str, QuantitySource],
) -> ModelAudit:
    """Put measured influence beside recorded provenance.

    Ranked by influence, because influence is the half that is measured.
    Provenance rides alongside as a category; the two are never multiplied.
    """
    audited: List[AuditedQuantity] = []
    for sensitivity in report.ranked:
        source = sources.get(sensitivity.quantity)
        audited.append(
            AuditedQuantity(
                quantity=sensitivity.quantity,
                sensitivity=sensitivity,
                tier=classify_source(source),
                citation=source.citation if source else None,
            )
        )

    # Anything the model has that the ranking does not, with the reason.
    ranked_ids = {s.quantity for s in report.ranked}
    unranked: List[Tuple[str, str]] = []
    for quantity in network.quantity_ids():
        if quantity in ranked_ids:
            continue
        value = None
        for s in network.species:
            if s.id == quantity:
                value = s.initial
        for p_ in network.parameters:
            if p_.id == quantity:
                value = p_.value
        unranked.append(
            (
                quantity,
                "value is exactly zero, where a relative sensitivity is "
                "undefined"
                if value == 0
                else "not included in this analysis",
            )
        )

    caveats = list(report.caveats)
    caveats.append(
        f"Influence and provenance are reported side by side, never "
        f"combined into a score: weighting them against each other would "
        f"need constants nobody has measured. Ranking is by influence "
        f"alone. The one judgement here is the {INFLUENCE_FLOOR} floor for "
        f"'measurably controls the result'."
    )
    return ModelAudit(
        model=network.name,
        quantities=tuple(audited),
        caveats=tuple(caveats),
        unranked=tuple(unranked),
    )


__all__ = [
    "INFLUENCE_FLOOR",
    "TIER_MEASURED_HERE",
    "TIER_LITERATURE_MATCHED",
    "TIER_LITERATURE_FLAGGED",
    "TIER_UNSOURCED",
    "TIER_ORDER",
    "AuditedQuantity",
    "ModelAudit",
    "audit",
    "classify_source",
]
