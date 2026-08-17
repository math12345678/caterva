"""
form_mixture.py

Does the candidate pool mix different named forms of one enzyme?

WHY THIS EXISTS
---------------
`protein_variant._ISOZYME_RE` matches the WORD "isozyme"/"isoform", so
"pH 8.5, 25°C, isozyme H4" is caught. BRENDA also names forms
**positionally**, and those are not:

    "LDHB, in the presence of 0.125 mM NADH"
    "pH 7.5, ..., LDH-1, with 3 mM fructose-1,6-bisphosphate"
    "pH 7.5, ..., wild-type LDH-2, with 3 mM fructose-1,6-bisphosphate"
    "hexokinase Ia"

`classify()` returns `unstated` for every one of them.

THE MEASUREMENT
---------------
The LDH turnover pool contains three forms at once:

    LDHB    142 -  350
    LDH-1  1500 - 1600
    LDH-2  1300 - 1800

Selection is `min()`. It takes **142.0 from LDHB** and reports it as the
turnover number of "lactate dehydrogenase" — an order of magnitude below the
LDH-1 and LDH-2 rows sitting in the same pool. The hexokinase pool does the
same with forms I, Ia and Ib.

WHY THIS IS NOT protein_variant.py's JOB
----------------------------------------
`protein_variant.classify()` answers a question about ONE row: is this a
variant? Answering it positionally would require knowing that "B" is a form
designator when it follows "LDH" and is not one when it follows "NAD" — which
means knowing what LDH and NADH are.

Hardcoding "LDH means lactate dehydrogenase" is the thing this project
refuses to do, and ADR 0031 recorded the gap rather than patching it with a
regex that would match a capital letter after any word.

THE RESHAPE THAT MAKES IT TRACTABLE
-----------------------------------
Ask a different question. Not *"is this row an isoform?"* but
**"do these rows name DIFFERENT forms of the same thing?"**

That is a pool-level question — the same move ADR 0033 made for effectors —
and it needs no domain knowledge at all. Group the rows by
`(base, designator)`. If one base appears with several designators, the pool
mixes named forms. Nothing here knows or needs to know what LDH stands for.

HOW COMPOUNDS ARE KEPT OUT, WITHOUT A LIST
------------------------------------------
The obvious false positive is "NADH": base NAD, designator H, by shape alone.
A pool holding NADH and NADP would report a mixture that is really two
cofactors.

The fix is not an exclusion list. A candidate token is dropped when
**PubChem resolves it to a compound** — `buffer_identity.resolve_identity`,
the same API-backed identity already used for buffers (ADR 0028) and
effectors (ADR 0032). NADH resolves; LDH does not. That is a claim with a
source, made by the same mechanism as every other chemical claim here.

WHAT THIS DOES NOT DO
---------------------
It does not decide which form the user wanted, and it does not withhold. A
request for "lactate dehydrogenase" genuinely is ambiguous between its
isoforms, and resolving that ambiguity is the user's to make. Reporting is
what makes the choice available to them.

It also cannot see a pool where every row names the SAME form. Homogeneous
is indistinguishable from unlabelled here, and both read as no finding.
"""
from __future__ import annotations

import re
from typing import Callable

from pydantic import BaseModel

import buffer_identity

#: An UPPERCASE acronym with a trailing form designator.
#:
#: "LDHB" -> (LDH, B).  "LDH-1" -> (LDH, 1).  "LDH 2" -> (LDH, 2).
#:
#: The base is 2-5 capitals so single letters and long shouted words do not
#: qualify. The designator is one digit or one capital, which is the form
#: BRENDA uses; a longer tail would swallow the next word.
_ACRONYM_FORM_RE = re.compile(r"\b(?P<base>[A-Z]{2,5})[- ]?(?P<designator>\d{1,2}|[A-Z])\b")

#: A spelled-out enzyme name with a roman-numeral form.
#:
#: "hexokinase I" -> (hexokinase, I).  "hexokinase Ia" -> (hexokinase, Ia).
#:
#: Requires a lowercase word of at least five letters so it does not fire on
#: prose like "in I" or on initials.
_WORD_ROMAN_RE = re.compile(
    r"\b(?P<base>[a-z]{5,})\s+(?P<designator>[IVX]{1,4}[a-c]?)\b"
)


class NamedForm(BaseModel):
    """One `(base, designator)` pair found in a commentary."""

    base: str
    designator: str
    #: The exact substring, so the extraction can be checked not trusted.
    evidence: str

    @property
    def label(self) -> str:
        return f"{self.base}{self.designator}"


class FormMixture(BaseModel):
    """One base named with several designators across the pool."""

    base: str
    #: designator -> the values reported for it, sorted.
    values_by_form: dict[str, list[float]]
    reason: str

    @property
    def fold_difference(self) -> float | None:
        """Ratio of the extremes across all forms, or None.

        A magnitude, not an effect size. The forms may also differ in assay
        conditions; this is the span a reader is being asked to look at.
        """
        values = [v for vs in self.values_by_form.values() for v in vs]
        if len(self.values_by_form) < 2 or not values:
            return None
        lo, hi = min(values), max(values)
        return hi / lo if lo else None


class SelectedForm(BaseModel):
    """The form the returned value actually belongs to.

    `FormMixture.reason` ends with "Returning the lowest **would** pick a
    form rather than answer the question" -- a warning about a hypothetical.
    It does not say whether that is what happened.

    On the hexokinase pool it is. Three forms are reported (I = 0.5,
    Ia = 0.77, Ib = 0.56) and `min()` returns 0.5, which IS hexokinase I. The
    warning's hypothetical was the actual outcome and the reader was not
    told, so the sentence reads as a caution about a risk rather than a
    description of the answer they are holding.

    This needs no new detection. It reads the mixture that was already
    found -- with whatever compound filtering that pass applied -- and asks
    which form the selected value fell into. Nothing here re-runs a regex,
    so a network outage cannot make it start naming forms that PubChem would
    have rejected as chemicals.
    """

    base: str
    designator: str
    value: float
    #: Every designator reported for this base, so "one of three" is
    #: checkable rather than asserted.
    sibling_designators: list[str] = []
    reason: str

    @property
    def label(self) -> str:
        return f"{self.base}{self.designator}"


def name_selected_form(
    mixtures: "list[FormMixture]", selected_value: float | None
) -> "SelectedForm | None":
    """Which reported form the returned value belongs to, or None.

    None when there is no mixture, no selected value, or the value does not
    appear under any form -- the last being the ordinary case where the
    returned row simply carried no designator. That is NOT a finding: it
    means the pool mixed forms and the answer did not come from one of them,
    which is the outcome the warning was hoping for.

    A value appearing under MORE THAN ONE designator yields None rather than
    a guess. Two forms reporting the same number is a coincidence this
    function cannot resolve, and naming one of them would be inventing the
    distinction the whole module exists to preserve.
    """
    if not mixtures or selected_value is None:
        return None

    hits = [
        (m, designator)
        for m in mixtures
        for designator, values in m.values_by_form.items()
        if any(v == selected_value for v in values)
    ]
    if len(hits) != 1:
        return None

    mixture, designator = hits[0]
    siblings = sorted(mixture.values_by_form)
    others = [d for d in siblings if d != designator]
    return SelectedForm(
        base=mixture.base,
        designator=designator,
        value=float(selected_value),
        sibling_designators=siblings,
        reason=(
            f"The value returned ({selected_value:g}) is {mixture.base}{designator}, "
            f"one of {len(siblings)} forms of {mixture.base} in the candidate pool "
            f"({', '.join(mixture.base + d for d in siblings)}). "
            "The warning above is not hypothetical for this result: a form was "
            f"picked. A request for {mixture.base} did not ask for "
            f"{mixture.base}{designator}"
            + (
                f", and {mixture.base}{others[0]} is a different gene product with "
                "its own kinetics."
                if others else "."
            )
        ),
    )


def extract_forms(commentary: str | None) -> list[NamedForm]:
    """Every `(base, designator)` pair in one commentary.

    Pure text. No compound filtering happens here -- that needs the network
    and belongs to the caller, so this function stays testable and cheap.
    """
    if not commentary or not commentary.strip():
        return []

    found: list[NamedForm] = []
    for match in _ACRONYM_FORM_RE.finditer(commentary):
        found.append(
            NamedForm(
                base=match.group("base"),
                designator=match.group("designator"),
                evidence=match.group(0),
            )
        )
    for match in _WORD_ROMAN_RE.finditer(commentary):
        found.append(
            NamedForm(
                base=match.group("base"),
                designator=match.group("designator"),
                evidence=match.group(0),
            )
        )
    return found


def _is_compound(
    token: str,
    cid_provider: Callable[[str], str] | None,
    parent_provider: Callable[[int], str] | None,
) -> bool:
    """Does PubChem know this token as a compound?

    A failed lookup answers False -- unresolvable is not "definitely a
    chemical", and treating it as one would silently drop real enzyme
    acronyms whenever the network hiccuped. The cost of the wrong answer
    here is a spurious mixture report, which a reader dismisses; the cost of
    the other wrong answer is a mixture never reported, which nobody sees.
    """
    try:
        identity = buffer_identity.resolve_identity(
            token, cid_provider, parent_provider
        )
    except Exception:  # noqa: BLE001
        return False
    return identity.status == "resolved"


def find_form_mixtures(
    rows: list[tuple[float, str | None]],
    cid_provider: Callable[[str], str] | None = None,
    parent_provider: Callable[[int], str] | None = None,
) -> list[FormMixture]:
    """Bases named with more than one designator across the candidate pool.

    `rows` is `(value, commentary)` — what the resolver is about to minimise
    over.
    """
    by_base: dict[str, dict[str, list[float]]] = {}
    for value, commentary in rows:
        for form in extract_forms(commentary):
            by_base.setdefault(form.base, {}).setdefault(
                form.designator, []
            ).append(value)

    mixtures: list[FormMixture] = []
    for base in sorted(by_base):
        forms = by_base[base]
        if len(forms) < 2:
            # One designator is not a mixture. Also the common case, so it
            # short-circuits before any network call.
            continue
        # Only now is the compound check worth its round trip.
        #
        # BOTH the base and the full tokens are checked, and the reason is a
        # bug this caught in its own first test run. The base of "NADH" is
        # the truncated "NAD", and asking PubChem about the truncation is
        # not the same question as asking about the token that actually
        # appears in the text. PubChem happens to know NAD, so the base
        # check alone would have worked here -- and would have failed
        # silently for the next acronym whose stem is not itself a
        # catalogued compound.
        candidates = [base] + [f"{base}{d}" for d in forms]
        if any(_is_compound(c, cid_provider, parent_provider) for c in candidates):
            continue

        values_by_form = {d: sorted(v) for d, v in sorted(forms.items())}
        mixture = FormMixture(base=base, values_by_form=values_by_form, reason="")
        fold = mixture.fold_difference
        magnitude = (
            f" The values span a factor of {fold:.0f}." if fold and fold > 1 else ""
        )
        described = ", ".join(
            f"{base}{d} = {v[0]}" + (f"–{v[-1]}" if len(v) > 1 else "")
            for d, v in values_by_form.items()
        )
        mixture.reason = (
            f"The candidate rows name {len(forms)} different forms of {base}: "
            f"{described}.{magnitude} These are distinct gene products with "
            "their own kinetics, and a request for the enzyme did not ask for "
            "one of them. Returning the lowest would pick a form rather than "
            "answer the question."
        )
        mixtures.append(mixture)
    return mixtures
