"""
evidence_rank.py

Choosing between candidate rows by how well they are evidenced, rather than
by which number happens to be smallest.

WHY THIS EXISTS
---------------
Barbara Bakker (UMC Groningen), asked how to handle values with missing
assay conditions, described what her group does:

    "We gave each parameter a score based on its reliability and
     applicability, such as physiological pH and T, species [...] and
     completeness of assay description. These scores were then used to give
     the parameter a weight in the sampling."

ADR 0024 Decision 3 adopted the scoring. `Tests/reliability.py` computes it,
the runner emits it, the API returns it, and the CLI prints it.

**Nothing ever used it to choose.** `fallback_logic.py` contains no reference
to reliability. After every filter this project has added -- flagged rows,
cross-species gating, relatedness, protein variants -- the final selection
among the survivors was still:

    best = min(entries, key=lambda e: e.km_value)

Take the smallest number. That is not a scientific criterion, and it is not
neutral either: it is *anti-correlated* with evidence quality, because a
poorly-described measurement is more likely to sit in the tail, and a minimum
seeks the tail.

WHAT IT COSTS, MEASURED
-----------------------
Human lactate dehydrogenase, this repository's own fixture, after the ADR
0029 variant filter leaves seven rows:

    0.03   STRENDA-incomplete, no commentary at all   <- min() picks this
    0.045  STRENDA-complete: "inhibition assay, pH 7.4, 37 C"
    0.398  STRENDA-incomplete, no commentary at all
    0.5    pH 8.0, temperature not specified
    ...

The resolver discards **the only row in the pool that meets the reporting
standard this entire project is built on**, in favour of one where BRENDA
reported nothing whatsoever about how the measurement was made, because
0.03 < 0.045.

WHY DOMINANCE, AND NOT A WEIGHTED SCORE
---------------------------------------
The obvious implementation combines the axes into one number and sorts by it.
That needs weights: how much is a complete assay description worth against an
exact organism match?

**Bakker was asked that question and has not answered it.** Inventing the
weights would fabricate the trade-off her group derived empirically, and
`reliabilityScore.ts` already refuses to produce a total for exactly this
reason (ADR 0024, Decision 3). Refusing there and inventing here would be
incoherent.

So this uses **Pareto dominance**, which needs no weights at all. Row A
dominates row B when A is at least as good as B on *every* axis and strictly
better on at least one. That is a fact about the two rows, not a judgement
about their relative importance. Dominated rows are discarded; what remains
is the non-dominated frontier.

Among the frontier, no row is beaten outright, and something still has to
choose. That choice remains `min()` -- and it remains arbitrary. Saying so is
the point: the arbitrariness has been pushed to where it cannot pick a row
that another row beats on the evidence, and no further.

THE AXES, AND WHY EACH IS AN ORDER
----------------------------------
Each axis is a total order that needs no calibration against the others.

  assay completeness   complete > partial > absent
      STRENDA requires temperature and pH on every reported measurement
      (ADR 0010). A row with both can be reproduced; a row with one cannot;
      a row with neither is a number without an experiment.

  variant statement    wild_type > unstated > absent
      A curator writing "wild-type" is strictly more informative than
      silence, and silence is strictly more informative than a row with no
      commentary at all. `variant` rows do not appear here -- ADR 0029
      removes them before this runs.

  organism match       exact > cross-species = not assessed
      ADR 0024's gate already refuses distant organisms; this orders what
      survives it. `not_assessed` shares an ordinal with `cross_species`
      so an unasked question cannot beat or lose to a fact.

None of these compares a *value* to another value. That is deliberate: this
module ranks evidence, and the number is not evidence about itself.
"""
from __future__ import annotations

from typing import Iterable, Sequence

from pydantic import BaseModel

from protein_variant import classify
from taxonomy import RANK_ORDER

#: Ordinal, not cardinal. The integers make `>=` readable; the GAPS between
#: them mean nothing and must never be summed. If a future change adds them
#: up it has invented the weighting this module exists to avoid.
_COMPLETENESS = {"complete": 2, "partial": 1, "absent": 0}
_VARIANT_STATEMENT = {"wild_type": 2, "unstated": 1, "absent": 0, "variant": -1}

#: `not_assessed` sits at the SAME ordinal as `cross_species` on purpose.
#:
#: When the requested organism is unknown, every row scores identically and
#: the axis discriminates nothing -- which is the honest behaviour for a
#: question that was never asked. Giving it its own rank would let "we did
#: not check" beat or lose to a fact, and this project's rule is that an
#: unassessed check is neither a pass nor a fail.
_ORGANISM = {"exact": 1, "cross_species": 0, "not_assessed": 0}


class EvidenceProfile(BaseModel):
    """Where one candidate row sits on each axis. No total, by design."""

    completeness: str
    variant_statement: str
    #: "exact" | "cross_species" | "not_assessed"
    organism_match: str

    #: Depth of the deepest shared taxonomic rank, from taxonomy.RANK_ORDER.
    #:
    #: None means NOT COMPARABLE, not "zero". ADR 0024's gate answers
    #: "close enough?"; this is the degree behind that yes, and the degree is
    #: genuinely unknown for a row whose lineage did not resolve. Ranking an
    #: unresolved lineage against a resolved one would let a failed lookup
    #: beat or lose to a fact.
    relatedness_depth: int | None = None

    #: Human-readable, for the search log. A ranking nobody can inspect is a
    #: ranking nobody can argue with.
    summary: str

    def ordinals(self) -> tuple[int | None, ...]:
        """Per-axis ordinals. `None` means this axis cannot be compared.

        Only `relatedness_depth` is ever None today. The others always have
        a value because their inputs are always readable off the row.
        """
        return (
            _COMPLETENESS.get(self.completeness, 0),
            _VARIANT_STATEMENT.get(self.variant_statement, 0),
            _ORGANISM.get(self.organism_match, 0),
            self.relatedness_depth,
        )


def profile(
    entry,
    requested_organism: str | None = None,
    relatedness_by_organism: dict | None = None,
) -> EvidenceProfile:
    """Read a BRENDAKmEntry's evidence axes.

    `requested_organism` is an ARGUMENT, not something read off the row.

    The first version read `entry._organism_exact`, an attribute nothing ever
    set, so the axis was the constant `True`. On the exact-match tier that
    was right by accident. On the cross-species tier -- the only tier where
    organism actually varies -- it discriminated nothing AND wrote
    "organism exact" into the search log for rows measured in a different
    organism than the caller asked about. A false statement in the audit
    trail is worse than a missing one.

    The row does not know what was requested. The caller does.
    """
    has_ph = getattr(entry, "assay_ph", None) is not None
    has_temp = getattr(entry, "assay_temperature_c", None) is not None
    completeness = (
        "complete" if (has_ph and has_temp)
        else "partial" if (has_ph or has_temp)
        else "absent"
    )

    verdict = getattr(entry, "variant", None) or classify(getattr(entry, "conditions", None))
    statement = verdict.status

    row_organism = (getattr(entry, "organism", None) or "").strip().lower()
    wanted = (requested_organism or "").strip().lower()
    if not wanted or not row_organism:
        organism_match = "not_assessed"
    elif row_organism == wanted:
        organism_match = "exact"
    else:
        organism_match = "cross_species"

    # Relatedness DEPTH, not just the pass/fail the gate already applied.
    #
    # ADR 0024 uses `assess_relatedness` as a threshold: share a class or be
    # refused. Everything that survives is then treated as equally related,
    # so on the cross-species tier a Homo sapiens value (shares the superorder
    # Euarchontoglires with a mouse, depth 10) ranks level with a Sus scrofa
    # one (shares only the class Mammalia, depth 7). The system already knows
    # which is closer and did not use it.
    depth = None
    if organism_match == "cross_species" and relatedness_by_organism:
        verdict = relatedness_by_organism.get(getattr(entry, "organism", None))
        shared = getattr(verdict, "shared_rank", None) if verdict else None
        if shared:
            depth = RANK_ORDER.get(str(shared).lower())

    organism_text = {
        "exact": "organism exact",
        "cross_species": "organism cross-species",
        "not_assessed": "organism not assessed",
    }[organism_match]

    return EvidenceProfile(
        completeness=completeness,
        variant_statement=statement,
        organism_match=organism_match,
        relatedness_depth=depth,
        summary=(
            f"assay {completeness}, commentary {statement}, {organism_text}"
            + (f" (shares {shared})" if depth is not None else "")
        ),
    )


def dominates(a: EvidenceProfile, b: EvidenceProfile) -> bool:
    """True when `a` is at least as good as `b` everywhere COMPARABLE and
    better somewhere comparable.

    An axis where either side is `None` is skipped, not scored. That is the
    honest reading of "we could not evaluate this for one of these two rows":
    it cannot support dominance and it cannot block it.

    Treating `None` as zero instead would let a row whose lineage failed to
    resolve lose to one that merely shares a class -- turning a failed lookup
    into evidence of distance. The same inversion this project keeps finding,
    and the reason `not_assessed` shares an ordinal with `cross_species` one
    axis over.

    When NO axis is comparable, nothing dominates. Two rows about which
    nothing can be compared are not ranked.
    """
    pairs = [
        (x, y)
        for x, y in zip(a.ordinals(), b.ordinals())
        if x is not None and y is not None
    ]
    if not pairs:
        return False
    return all(x >= y for x, y in pairs) and any(x > y for x, y in pairs)


def frontier(
    entries: Sequence,
    requested_organism: str | None = None,
    relatedness_by_organism: dict | None = None,
) -> list:
    """The non-dominated rows, in input order.

    Returns the input unchanged when it holds fewer than two rows: there is
    nothing to dominate, and returning an empty list for a single-row pool
    would turn "one candidate" into "no candidates".
    """
    if len(entries) < 2:
        return list(entries)

    profiles = [
        profile(e, requested_organism, relatedness_by_organism) for e in entries
    ]
    kept = []
    for index, entry in enumerate(entries):
        beaten_by = any(
            dominates(profiles[other], profiles[index])
            for other in range(len(entries))
            if other != index
        )
        if not beaten_by:
            kept.append(entry)

    # A cycle is impossible under a partial order, but an empty frontier
    # would silently drop the whole pool, so it is treated as a bug in this
    # function rather than as "no candidates".
    if not kept:
        raise AssertionError(
            "every candidate was dominated, which cannot happen under a "
            "partial order -- the axis ordering is inconsistent"
        )
    return kept


def describe_discards(
    entries: Sequence,
    kept: Sequence,
    requested_organism: str | None = None,
    relatedness_by_organism: dict | None = None,
) -> list[str]:
    """One line per discarded row, naming what beat it.

    The search log is the only place a reader can see that a row was removed
    from consideration. A selection that narrowed the pool without saying so
    is indistinguishable from a pool that never held the row.
    """
    if len(kept) == len(entries):
        return []
    kept_ids = {id(e) for e in kept}
    lines = []
    for entry in entries:
        if id(entry) in kept_ids:
            continue
        p = profile(entry, requested_organism, relatedness_by_organism)
        better = next(
            (
                profile(k, requested_organism, relatedness_by_organism).summary
                for k in kept
                if dominates(
                    profile(k, requested_organism, relatedness_by_organism), p
                )
            ),
            "a better-evidenced row",
        )
        lines.append(
            f"Discarded {getattr(entry, 'km_value', '?')} ({p.summary}); "
            f"beaten on every axis by one with {better}"
        )
    return lines
