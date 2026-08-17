"""
selection_tie.py

When the evidence ranked several rows equal, say so.

WHY THIS EXISTS
---------------
Barbara Bakker's advice was that a parameter's reliability should drive
which value gets used:

    "We gave each parameter a score based on its reliability and
     applicability [...] These scores were then used to give the parameter a
     weight in the sampling."

`evidence_rank.py` (ADR 0047) implemented the first half: candidates are
narrowed to the non-dominated set, where a row is dropped only when another
beats it on EVERY axis. That needs no weights, which is why it could be
built without inventing any.

Its own docstring names what is left:

    That choice remains `min()` -- and it remains arbitrary. Saying so is
    the point: the arbitrariness has been pushed to where it cannot pick a
    row [...]

**Saying so in a docstring is not saying so to a user.** A student sees one
number. Nothing in the response tells them the evidence ranked three rows
equally good and a tie-break chose among them. The arbitrariness was
confined, documented, and still invisible at the only place it matters.

WHAT A TIE ACTUALLY MEANS
-------------------------
It is not a defect in the data and not a defect in the ranking. It means the
three axes -- assay completeness, what the row says about the protein,
organism match -- do not distinguish these rows, and they genuinely do not.
Two rows that are both STRENDA-complete, both wild-type, both the requested
organism are equally well evidenced. If their values differ, that difference
is real disagreement in the literature.

Reporting the minimum silently presents literature disagreement as a
measurement. The honest output is the number AND the fact that the evidence
did not select it.

NO THRESHOLD, AGAIN
-------------------
The obvious design asks "do the surviving values differ ENOUGH to mention?"
-- and that threshold is enzyme-specific and unsourced, so it is not
available. Every other comparison in this project reached the same wall and
answered it the same way (ADR 0026 conditions, ADR 0028 buffers, ADR 0032
concentrations): report the spread, refuse the judgement.

So a tie is reported whenever more than one row survives and the surviving
values are not all identical. Identical values are not a finding: the
evidence did not choose, and nothing turned on the choice.

THIS IS NOT AN ENSEMBLE
-----------------------
Bakker samples from a weighted distribution and rejects at the model level
after validating against flux data. ADR 0024 Decision 3 declined that, for a
reason that still holds: a teaching lab has no flux data to reject against,
and spread without a validation step looks like a rigorous uncertainty
estimate while being nothing of the kind.

This reports the alternatives the evidence could not rank. It does not
weight them, sample them, or combine them.
"""
from __future__ import annotations

from pydantic import BaseModel


class TiedCandidate(BaseModel):
    """One row the evidence could not rank below another."""

    value: float
    unit: str | None = None
    organism: str | None = None

    #: The BRENDA reference this row came from, so a reader can go and look.
    #: A named alternative is checkable; a bare number is not.
    reference_id: str | None = None

    #: The row's own commentary, verbatim. This is what a reader needs to
    #: form the judgement the ranking declined to make.
    conditions: str | None = None

    #: Whether this is the row that was returned.
    selected: bool = False


class SelectionTie(BaseModel):
    """The evidence ranked several rows equal and a tie-break chose one."""

    #: Every non-dominated row, including the one selected.
    candidates: list[TiedCandidate] = []

    #: min and max across the tied values, and the ratio between them.
    #: Reported rather than judged: whether a 1.6-fold spread matters is a
    #: question about this enzyme, which this module cannot answer.
    low: float | None = None
    high: float | None = None
    fold_range: float | None = None

    reason: str = ""

    @property
    def is_tied(self) -> bool:
        """True only when a tie was actually found and reported.

        A positive test, for the same reason `is_same` and `is_wild_type`
        are: `SelectionTie()` with no candidates must never read as "the
        evidence chose cleanly", because it is also what an unpopulated
        field looks like.
        """
        return len(self.candidates) > 1


def find_tie(kept, selected, unit: str | None = None) -> SelectionTie | None:
    """Report a tie among `kept`, or None when there is nothing to report.

    `kept` is `evidence_rank.frontier()`'s output -- the rows no other row
    beats on every axis. `selected` is the one the tie-break returned.

    Returns None when fewer than two rows survived, or when every surviving
    value is identical. Neither is a finding: in the first the evidence did
    choose, and in the second nothing turned on the choice.
    """
    if kept is None or len(kept) < 2:
        return None

    values = [float(getattr(e, "km_value")) for e in kept]
    if len(set(values)) == 1:
        return None

    low, high = min(values), max(values)
    # Guard the division rather than the input: a zero or negative kinetic
    # constant is a data problem for another check, and this one must not
    # crash on it or silently report an infinite fold-range.
    fold = (high / low) if low > 0 else None

    candidates = [
        TiedCandidate(
            value=float(e.km_value),
            unit=getattr(e, "unit", None) or unit,
            organism=getattr(e, "organism", None),
            reference_id=getattr(e, "reference_id", None),
            conditions=getattr(e, "conditions", None),
            selected=(e is selected),
        )
        for e in kept
    ]

    spread = (
        f"{low:g} to {high:g}"
        + (f", a {fold:.3g}-fold range" if fold is not None else "")
    )
    return SelectionTie(
        candidates=candidates,
        low=low,
        high=high,
        fold_range=fold,
        reason=(
            f"{len(kept)} rows were equally well evidenced -- no row beats "
            f"another on assay completeness, what it states about the "
            f"protein, and organism match -- and their values span {spread}. "
            "The value returned was chosen by taking the lowest, which the "
            "evidence does not justify. That spread is disagreement in the "
            "literature, not a measurement uncertainty, and the alternatives "
            "are listed so it can be read as such."
        ),
    )
