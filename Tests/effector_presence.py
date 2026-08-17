"""
effector_presence.py

Did the candidate pool contain BOTH arms of somebody's controlled experiment?

WHY THIS IS SEPARATE FROM effector.py
-------------------------------------
`effector.py` answers a question about one row: what did this assay contain,
and was it present or absent? It also compares two rows against each other.

This module asks a question no single row can answer, and no pair can
either: **does the pool the resolver is about to select from contain a
compound reported as present in some rows and absent in others?**

That is the shape of a designed comparison, and it is invisible to
per-row extraction by construction — every individual row is perfectly
well-formed. It is the same structural point as ADR 0026: the defect is not
in any value, it is in the set.

Extraction is NOT duplicated here. This calls `effector.extract_effectors`
and `effector.resolve_effectors`, so compound identity comes from the same
PubChem parent-CID matching, and "fructose 1,6-bisphosphate" pairs with
"D-fructose-1,6-diphosphate" for the same reason Tris pairs with Tris-HCl.

Two implementations of one extraction is precisely what ADR 0027 was written
about, and this module was briefly one of them before being rewritten to sit
on top of the other.

THE CASE
--------
Four rows from the LDH turnover fixture, one paper, same pH 6.0, same 25 °C:

    21.1  recombinant wild-type enzyme IN PRESENCE of fructose 1,6-bisphosphate
   327.2  recombinant wild-type enzyme IN ABSENCE of fructose 1,6-bisphosphate
   178.4  recombinant mutant D38R    IN PRESENCE of fructose 1,6-bisphosphate
   194.9  recombinant mutant D38R    IN ABSENCE of fructose 1,6-bisphosphate

The authors measured with and without an allosteric activator on purpose,
and the wild-type arms differ by a factor of **15.5**.

Terrium selects `min()`. It takes 21.1 — the activated arm — and reports it
as the enzyme's turnover number with a real citation, having no idea it
picked one side of a comparison. Larger than the mutant case in ADR 0029,
which was a factor of twelve.

WHAT THIS DECIDES, AND WHAT IT REFUSES TO
-----------------------------------------
It decides one thing, and it needs no biochemistry: the pool contains both
arms. That requires knowing nothing about FBP except that a curator wrote
"presence" beside one row and "absence" beside another.

It does not decide which arm is right, and it does not withhold. Choosing
would require separating "allosteric effector someone added" from
"cosubstrate the reaction requires" — a claim about each enzyme's mechanism
that Terrium has no source for. `effector.py`'s header makes the same point
about the NADH rows in this corpus.
"""
from __future__ import annotations

from typing import Callable

from pydantic import BaseModel

from effector import Effector, extract_effectors, resolve_effectors


class EffectorContrast(BaseModel):
    """A compound the candidate pool reports both with and without."""

    #: Compound as written, for the reader. Matching used the PubChem parent
    #: where one resolved; this is the human-facing label.
    compound: str

    #: Values from rows where the compound was present / absent.
    present_values: list[float] = []
    absent_values: list[float] = []

    reason: str

    @property
    def fold_difference(self) -> float | None:
        """Ratio of the extremes across both arms, or None.

        A magnitude, NOT a causal claim. The arms may also differ in ways
        the commentary did not state — in the LDH rows above they differ in
        genotype too — so this is the size of the thing a reader is being
        asked to look at, not an effect size.
        """
        values = self.present_values + self.absent_values
        if not self.present_values or not self.absent_values:
            return None
        lo, hi = min(values), max(values)
        return hi / lo if lo else None


def _key(effector: Effector) -> object:
    """Compound identity WITHOUT presence.

    `Effector.comparison_key` deliberately includes presence, because two
    rows naming one compound with opposite presence are different
    conditions. Here that is exactly what must collapse: finding the pair is
    the entire purpose, so identity is taken alone and presence is the axis.
    """
    if effector.identity is not None and effector.identity.parent_cid is not None:
        return effector.identity.parent_cid
    return effector.compound_text.strip().lower()


def find_contrasts(
    rows: list[tuple[float, str | None]],
    cid_provider: Callable[[str], str] | None = None,
    parent_provider: Callable[[int], str] | None = None,
) -> list[EffectorContrast]:
    """Compounds appearing as both present and absent across `rows`.

    `rows` is `(value, commentary)` — the candidate pool the resolver is
    about to take a minimum of.

    Providers are injectable so tests never touch the network, matching
    `effector.resolve_effectors` and `taxonomy.py`.
    """
    present: dict[object, list[float]] = {}
    absent: dict[object, list[float]] = {}
    label: dict[object, str] = {}

    for value, commentary in rows:
        extracted = extract_effectors(commentary)
        if not extracted:
            continue
        for effector in resolve_effectors(extracted, cid_provider, parent_provider):
            # `unstated` is not `absent`. Most papers do not enumerate what
            # they did not add, and reading silence as absence would
            # manufacture a contrast against every unlabelled row in the
            # pool — the warning would fire constantly and be ignored.
            if effector.presence not in ("present", "absent"):
                continue
            key = _key(effector)
            if not key:
                continue
            label.setdefault(key, effector.compound_text)
            (present if effector.presence == "present" else absent).setdefault(
                key, []
            ).append(value)

    contrasts: list[EffectorContrast] = []
    for key in sorted(set(present) & set(absent), key=lambda k: str(k)):
        contrast = EffectorContrast(
            compound=label[key],
            present_values=sorted(present[key]),
            absent_values=sorted(absent[key]),
            reason="",
        )
        fold = contrast.fold_difference
        magnitude = (
            f" The values span a factor of {fold:.1f}." if fold and fold > 1 else ""
        )
        contrast.reason = (
            f"The candidate rows include measurements made BOTH with and "
            f"without {label[key]}: {contrast.present_values} present, "
            f"{contrast.absent_values} absent.{magnitude} These are arms of a "
            "comparison somebody ran on purpose, so returning one of them as "
            "the value would be reporting half an experiment."
        )
        contrasts.append(contrast)
    return contrasts
