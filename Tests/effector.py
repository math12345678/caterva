"""
effector.py

Cofactors and allosteric effectors present in — or deliberately absent from —
the assay.

WHY THIS EXISTS
---------------
Lisa Jeske named four things that make kinetic values incomparable:

    "Reaction conditions: pH value, temperature, **cofactors**, and buffers
     play a huge role in the reactions."

ADR 0026 compared pH and temperature. ADR 0028 compared buffers, and said
plainly that cofactors were still not extracted at all. This closes the
fourth.

It was not built earlier because BRENDA reports them in free text with no
consistent form. What made it buildable was `check_commentary_coverage.py`
measuring the residue — the part of each commentary nothing reads — which
turned "cofactors are hard" into a list of exactly what is being discarded.

THE PAIR THAT MOTIVATED IT
--------------------------
Two real rows from the lactate dehydrogenase fixture:

    "pH 6.0, 25°C, recombinant wild-type enzyme in presence of
     fructose 1,6-bisphosphate"
    "pH 6.0, 25°C, recombinant wild-type enzyme in absence of
     fructose 1,6-bisphosphate"

Same enzyme. Same pH. Same temperature. Same organism. Same paper. Same
wild-type verdict. **Every check Terrium has says these two rows are
identical**, and they are opposite allosteric conditions — fructose
1,6-bisphosphate is the classic activator of bacterial L-lactate
dehydrogenase, and the pair exists precisely because the two states differ.

The corpus also holds a Km series at four cosubstrate concentrations:

    "LDHB, in the presence of 0.125 mM NADH"
    "LDHB, in the presence of 0.15  mM NADH"
    "LDHB, in the presence of 0.2   mM NADH"
    "LDHB, in the presence of 0.25  mM NADH"

Four numbers, all correct, none comparable with the others. Selecting the
minimum across them reports the one measured under whichever cosubstrate
concentration happened to be lowest.

PRESENCE IS NOT A DETAIL OF IDENTITY
------------------------------------
The obvious model is "which compounds were in the assay". That model cannot
represent the pair above, because both rows name the same compound. So
presence is a first-class field with three values — `present`, `absent`,
`unstated` — and two effectors match only when the compound AND the presence
agree.

An `absent` reading is a real, deliberate experimental statement: the curator
wrote "in absence of", meaning the paper measured without it on purpose. That
is different from `unstated`, where nobody said.

IDENTITY COMES FROM PUBCHEM, FOR THE SAME REASON BUFFERS DO
-----------------------------------------------------------
The corpus spells one compound four ways:

    "fructose 1,6-diphosphate"      "D-fructose-1,6-diphosphate"
    "fructose 1,6-bisphosphate"     "fructose-1,6-bisphosphate"

String equality reports four different effectors. `buffer_identity` already
solves exactly this — resolve to a PubChem compound, compare at the parent —
so this module calls that rather than growing a second implementation. ADR
0027 is the reason that instinct is worth stating out loud.

WHAT THIS DOES NOT DO
---------------------
It does not compare concentrations. 0.125 mM NADH and 0.25 mM NADH resolve
to the same compound with the same presence and will compare as `same`. The
concentration text is kept on the record so a reader can see that, exactly as
`buffer_identity` keeps it.

That is a real limit and the NADH series above is precisely the case it
misses. Comparing concentrations needs a threshold — how much of a
difference matters — and that threshold is enzyme-specific and unsourced.
Reporting the numbers and refusing the judgement is what this project does
with every other unsourced threshold.
"""
from __future__ import annotations

import re
from typing import Callable

from pydantic import BaseModel

import buffer_identity
from buffer_identity import BufferIdentity

#: Clauses BRENDA uses to say a compound was in the assay.
#:
#: Ordered longest-first so "in the presence of" wins over "presence of";
#: alternation in Python's `re` is first-match, not longest-match, and the
#: shorter form would otherwise leave "in the " unconsumed and count as
#: residue.
_PRESENT_LEAD = (
    r"in\s+the\s+presence\s+of|in\s+presence\s+of|presence\s+of|"
    r"activated\s+by|in\s+the\s+absence\s+of\s+added|with\s+added|with"
)
_ABSENT_LEAD = r"in\s+the\s+absence\s+of|in\s+absence\s+of|absence\s+of|without"

#: A compound phrase: letters, digits, commas, hyphens, plus signs.
#: Stops at a clause boundary -- a comma FOLLOWED BY a space and a
#: non-digit, so "fructose 1,6-bisphosphate" survives while
#: "NADH, pH 7" splits.
_COMPOUND = r"[A-Za-z][A-Za-z0-9'()\[\]+-]*(?:[\s,-](?![\s]|\d+\s*[°%]|pH\b|at\b)[A-Za-z0-9'()\[\]+-]+)*"

_CONCENTRATION = r"\d+(?:\.\d+)?\s*[munMUN]?M"

_EFFECTOR_RE = re.compile(
    rf"\b(?P<lead>{_ABSENT_LEAD}|{_PRESENT_LEAD})\s+"
    rf"(?:(?P<conc>{_CONCENTRATION})\s+)?"
    rf"(?P<compound>{_COMPOUND})",
    re.IGNORECASE,
)

#: A bare salt in a comma-separated condition list: "20 mM CaCl2".
#: Only fires on a concentration immediately followed by a formula-shaped
#: token, so it cannot swallow "20 mM Tris" style buffer text that
#: assay_conditions.py already claims.
_BARE_SALT_RE = re.compile(
    rf"\b(?P<conc>{_CONCENTRATION})\s+(?P<compound>[A-Z][A-Za-z]*\d*(?:Cl\d?|SO4|PO4|Br\d?)\b)",
)

_ABSENT_RE = re.compile(_ABSENT_LEAD, re.IGNORECASE)


class Effector(BaseModel):
    """One cofactor or effector clause, as reported."""

    #: The clause exactly as written, so a reader can disagree with the rest.
    raw: str

    #: Compound name as extracted, before resolution.
    compound_text: str

    #: "present" | "absent" | "unstated"
    presence: str

    #: Concentration text, kept and NOT compared. See the module header.
    concentration_text: str | None = None

    #: PubChem resolution, reusing buffer_identity. None when not attempted.
    identity: BufferIdentity | None = None

    @property
    def comparison_key(self) -> tuple[object, str]:
        """What two effectors must share to count as the same condition.

        Identity by PubChem parent when resolved, else the lowercased text —
        and the PRESENCE either way. Two rows naming the same compound with
        opposite presence are the case this whole module exists for, so the
        key must never collapse them.
        """
        if self.identity is not None and self.identity.parent_cid is not None:
            return (self.identity.parent_cid, self.presence)
        return (self.compound_text.strip().lower(), self.presence)


class EffectorComparison(BaseModel):
    status: str  # "same" | "different" | "unknown" | "not_reported"
    reason: str
    left: list[Effector] = []
    right: list[Effector] = []

    @property
    def is_same(self) -> bool:
        """True ONLY for a positive match. Same discipline as
        `BufferComparison.is_same` and `VariantVerdict.is_wild_type`:
        `unknown` and `not_reported` must never read as agreement."""
        return self.status == "same"


def _presence_of(lead: str) -> str:
    return "absent" if _ABSENT_RE.match(lead.strip()) else "present"


def extract_effectors(commentary: str | None) -> list[Effector]:
    """Every effector clause in one commentary. Empty list when none.

    Pure text handling: it identifies clauses and compound names and makes
    no claim about what the compounds do. Whether two extracted names are
    one substance is `resolve_effectors`' business, and it asks PubChem.
    """
    if not commentary or not commentary.strip():
        return []

    found: list[Effector] = []
    claimed: list[tuple[int, int]] = []

    for m in _EFFECTOR_RE.finditer(commentary):
        compound = m.group("compound").strip(" ,;.-")
        if not compound:
            continue
        found.append(
            Effector(
                raw=m.group(0).strip(),
                compound_text=compound,
                presence=_presence_of(m.group("lead")),
                concentration_text=(m.group("conc") or None),
            )
        )
        claimed.append((m.start(), m.end()))

    for m in _BARE_SALT_RE.finditer(commentary):
        # Skip anything a presence/absence clause already took, so
        # "in presence of 20 mM CaCl2" yields one effector, not two.
        if any(start <= m.start() < end for start, end in claimed):
            continue
        found.append(
            Effector(
                raw=m.group(0).strip(),
                compound_text=m.group("compound"),
                presence="present",
                concentration_text=m.group("conc"),
            )
        )

    return found


def resolve_effectors(
    effectors: list[Effector],
    cid_provider: Callable[[str], str] | None = None,
    parent_provider: Callable[[int], str] | None = None,
) -> list[Effector]:
    """Attach a PubChem identity to each effector.

    Failure is not an error. An unresolved effector keeps its text and
    compares by lowercased name, which is weaker but not wrong — and the
    comparison reports `unknown` rather than claiming agreement.
    """
    resolved: list[Effector] = []
    for e in effectors:
        try:
            identity = buffer_identity.resolve_identity(
                e.compound_text, cid_provider, parent_provider
            )
        except Exception:  # noqa: BLE001
            identity = None
        resolved.append(e.model_copy(update={"identity": identity}))
    return resolved


def compare_effectors(
    left: list[Effector],
    right: list[Effector],
) -> EffectorComparison:
    """Were two measurements made under the same effector conditions?"""
    if not left and not right:
        return EffectorComparison(
            status="not_reported",
            reason=(
                "Neither source named a cofactor or effector. Comparability "
                "on this axis is unknown -- a gap in the sources, not a "
                "finding that the conditions agreed."
            ),
            left=left,
            right=right,
        )

    if not left or not right:
        named = [e.compound_text for e in (left or right)]
        return EffectorComparison(
            status="different",
            reason=(
                f"One source names {', '.join(named)} and the other names no "
                "effector at all. That is a difference in what was reported, "
                "and it may be a difference in what was in the tube; BRENDA "
                "does not distinguish 'absent' from 'unmentioned'."
            ),
            left=left,
            right=right,
        )

    unresolved = [
        e for e in left + right
        if e.identity is None or e.identity.status != "resolved"
    ]
    left_keys = {e.comparison_key for e in left}
    right_keys = {e.comparison_key for e in right}

    if left_keys == right_keys:
        if unresolved:
            return EffectorComparison(
                status="unknown",
                reason=(
                    "The effector names match as text, but "
                    f"{', '.join(sorted({e.compound_text for e in unresolved}))} "
                    "could not be resolved to a compound, so they are not "
                    "confirmed to be the same substance. Matching text is not "
                    "matching chemistry -- see the four spellings of fructose "
                    "1,6-bisphosphate in this corpus."
                ),
                left=left,
                right=right,
            )
        concentrations = [
            e.concentration_text for e in left + right if e.concentration_text
        ]
        note = (
            f" Concentration was NOT compared ({', '.join(concentrations)})."
            if concentrations else ""
        )
        return EffectorComparison(
            status="same",
            reason=(
                "Both measurements report the same effectors in the same "
                f"presence state.{note}"
            ),
            left=left,
            right=right,
        )

    # The sharpest case: same compound, opposite presence.
    def by_compound(items: list[Effector]) -> dict[object, str]:
        out: dict[object, str] = {}
        for e in items:
            key = (
                e.identity.parent_cid
                if e.identity is not None and e.identity.parent_cid is not None
                else e.compound_text.strip().lower()
            )
            out[key] = e.presence
        return out

    lc, rc = by_compound(left), by_compound(right)
    flipped = [
        k for k in set(lc) & set(rc)
        if lc[k] != rc[k] and "unstated" not in (lc[k], rc[k])
    ]
    if flipped:
        names = sorted({
            e.compound_text for e in left + right
            if (e.identity.parent_cid if e.identity and e.identity.parent_cid
                else e.compound_text.strip().lower()) in flipped
        })
        return EffectorComparison(
            status="different",
            reason=(
                f"One measurement was made in the PRESENCE of "
                f"{', '.join(names)} and the other in its ABSENCE. These are "
                "opposite experimental conditions, not a difference of "
                "degree: an allosteric effector is added precisely because it "
                "changes the kinetics, so the two values describe different "
                "states of the same enzyme."
            ),
            left=left,
            right=right,
        )

    described_l = ", ".join(f"{e.compound_text} ({e.presence})" for e in left) or "none"
    described_r = ", ".join(f"{e.compound_text} ({e.presence})" for e in right) or "none"
    return EffectorComparison(
        status="different",
        reason=(
            f"Different effector conditions -- one reports {described_l}, the "
            f"other {described_r}. Cofactors and effectors change kinetics, so "
            "these measurements were not made under the same conditions."
        ),
        left=left,
        right=right,
    )
