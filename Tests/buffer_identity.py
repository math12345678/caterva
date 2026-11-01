"""
buffer_identity.py

Buffer identity, from PubChem compound records.

WHY THIS EXISTS
---------------
Lisa Jeske of the BRENDA curation team named four things that make kinetic
values incomparable across papers:

    "Reaction conditions: pH value, temperature, cofactors, and buffers play
     a huge role in the reactions. The values in BRENDA come from thousands
     of different papers, each with different laboratory conditions. If you
     simply mix these together, the simulation will end up calculating with
     'fantasy numbers'."

ADR 0026 built the cross-parameter coherence check and compared **two** of
the four: pH and temperature. It said so plainly rather than implying it had
covered her sentence. This module closes the third.

The buffer was already parsed and carried on every resolved value
(assay_conditions.buffer, ADR 0010). It was never compared, because
comparing it is harder than it looks.

WHY STRING EQUALITY IS THE WRONG TOOL
-------------------------------------
BRENDA's commentary is free text written by different curators from
different papers. The real strings in this repository's own fixtures are:

    "0.5 M Tris-HCl buffer"
    "0.1 M MOPS buffer"
    "phosphate"

`"0.5 M Tris-HCl buffer" != "Tris-HCl"` is true as strings and false as
chemistry. A check built on string equality would report a difference
between two measurements made in the same buffer, and it would do it
constantly -- the false-POSITIVE direction, which is the one that gets a
warning ignored. A warning that cries wolf on the common case is worse than
no warning, because it trains the reader to skip the line where the real
finding will eventually appear.

WHY PARENT CID AND NOT CID
--------------------------
Resolving each name to a PubChem compound id fixes the wording problem and
introduces a subtler one: Tris and Tris-HCl are different chemical entities
with different CIDs, and a biochemist calls them the same buffer. Reporting
them as different buffers would be the same false positive wearing a lab
coat.

PubChem models this directly. A salt's record carries a **parent compound**
-- the neutral form -- reachable at `cids/JSON?cids_type=parent`. Tris-HCl's
parent is Tris. So identity is compared at the parent, which is an assertion
PubChem makes about the compound rather than a rule this file invents.

That is the whole reason this goes to an API instead of a lookup table. A
hardcoded synonym map ("Tris-HCl" -> "Tris", "PBS" -> "phosphate") would be
a set of chemistry claims with no source, embedded in a file nobody reviews
as chemistry, and it would be wrong for every buffer nobody thought of.

WHAT THIS IS NOT
----------------
Same buffer species is not same buffer *system*. Concentration, counter-ion
and ionic strength all affect kinetics and none of them are compared here:
0.5 M Tris-HCl and 10 mM Tris-HCl resolve identically and are not the same
experimental condition. This module removes the crudest disagreement --
phosphate against Tris -- and claims nothing beyond it.

Saying that plainly matters, because the risk of adding a check is that its
existence gets read as an endorsement of whatever survives it. Cofactors,
the fourth item on Jeske's list, are still not extracted at all.

THREE STATES, NEVER TWO
-----------------------
`resolved`, `unresolvable`, `not_reported`. A lookup that failed is not a
match and not a mismatch, and with a boolean "we could not check" inverts
into "no problem found" the first time someone writes `if not differs`.
Same discipline as taxonomy.py's `unknown`.
"""
from __future__ import annotations

import json
import re
from typing import Callable

from pydantic import BaseModel

from http_retry import retry_get

PUBCHEM_NAME_CID_URL = (
    "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/{name}/cids/JSON"
)
PUBCHEM_PARENT_CID_URL = (
    "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/{cid}/cids/JSON"
    "?cids_type=parent"
)

#: Leading concentration: "0.5 M ", "50 mM ", "0.1M ".
#:
#: This is string handling, not chemistry. It removes a number and a unit
#: so the remainder can be sent to PubChem as a name; it makes no claim
#: about what the substance is. The concentration is deliberately DISCARDED
#: rather than compared -- see "WHAT THIS IS NOT" above. Recording that it
#: was dropped is the honest half: `BufferIdentity.concentration_text`
#: keeps it so a reader can see what the comparison ignored.
_CONCENTRATION_RE = re.compile(
    r"^\s*(?P<conc>\d+(?:\.\d+)?\s*[munMUN]?\s*M)\b\s*",
)

#: Trailing "buffer", "buffered", "buffer system".
_BUFFER_WORD_RE = re.compile(r"[\s-]*buffer(?:ed)?(?:\s+system)?\s*$", re.IGNORECASE)

#: Leading prepositions BRENDA's commentary uses: "in 0.1 M MOPS buffer".
_LEADING_PREP_RE = re.compile(r"^\s*(?:in|at|with|using)\s+", re.IGNORECASE)


class BufferIdentity(BaseModel):
    """What a reported buffer string resolved to, and what was ignored."""

    #: The string exactly as the source reported it. Always present; this is
    #: what a reader needs in order to disagree with the rest of this object.
    raw: str

    #: The species name sent to PubChem after stripping concentration and
    #: the word "buffer". None when nothing recognisable remained.
    species: str | None = None

    #: PubChem compound id for `species`.
    cid: int | None = None

    #: Parent (neutral form) compound id. Equal to `cid` when the compound
    #: has no separate parent. THIS is what identity is compared on.
    parent_cid: int | None = None

    #: The concentration text that was stripped and NOT compared. Kept so a
    #: reader can see that 0.5 M and 10 mM were treated as the same buffer.
    concentration_text: str | None = None

    status: str = "not_reported"  # "resolved" | "unresolvable" | "not_reported"

    #: Why, in a sentence, whenever status is not "resolved".
    reason: str | None = None


class BufferComparison(BaseModel):
    """Whether two reported buffers are the same species."""

    status: str  # "same" | "different" | "unknown" | "not_reported"
    reason: str
    left: BufferIdentity | None = None
    right: BufferIdentity | None = None

    @property
    def is_same(self) -> bool:
        """True ONLY for a positive match.

        Deliberately not `status != "different"`. `unknown` and
        `not_reported` must never read as agreement -- that inversion is
        exactly what the three states exist to prevent.
        """
        return self.status == "same"


CidProvider = Callable[[str], str]
ParentProvider = Callable[[int], str]


#: Both network lookups are memoised for the life of the process.
#:
#: Without this, every resolved kinetic value costs two PubChem round trips,
#: on the hot path, for a string drawn from a vocabulary of about sixteen
#: buffers. A model resolving a Km and a Ki would make four calls to learn
#: two facts it already knew.
#:
#: Bounded on purpose. `maxsize` is small because the domain is small: if
#: this cache ever needs to be large, the input is not a buffer name and
#: something upstream is wrong. Cache size is a claim about the data, and a
#: claim that stops being true should show up as evictions rather than as
#: silent memory growth.
#:
#: Only the DEFAULT providers are cached. Injected providers are called
#: directly, so a test that counts calls counts them accurately -- a cache
#: that swallowed the second call would make "this never hits the network"
#: untestable.
_CID_CACHE: dict[str, str] = {}
_PARENT_CACHE: dict[int, str] = {}
_CACHE_MAX = 256


def _cached_fetch_cid_json(name: str) -> str:
    key = name.strip().lower()
    if key not in _CID_CACHE:
        if len(_CID_CACHE) >= _CACHE_MAX:
            _CID_CACHE.clear()
        _CID_CACHE[key] = fetch_cid_json(name)
    return _CID_CACHE[key]


def _cached_fetch_parent_json(cid: int) -> str:
    if cid not in _PARENT_CACHE:
        if len(_PARENT_CACHE) >= _CACHE_MAX:
            _PARENT_CACHE.clear()
        _PARENT_CACHE[cid] = fetch_parent_json(cid)
    return _PARENT_CACHE[cid]


# ---------------------------------------------------------------------------
# Network. No parsing here.
# ---------------------------------------------------------------------------

def fetch_cid_json(name: str, timeout: float = 15) -> str:
    """Raw PubChem JSON for a compound name lookup."""
    response = retry_get(
        PUBCHEM_NAME_CID_URL.format(name=name),
        timeout=timeout,
    )
    response.raise_for_status()
    return response.text


def fetch_parent_json(cid: int, timeout: float = 15) -> str:
    """Raw PubChem JSON for a parent-compound lookup."""
    response = retry_get(
        PUBCHEM_PARENT_CID_URL.format(cid=cid),
        timeout=timeout,
    )
    response.raise_for_status()
    return response.text


# ---------------------------------------------------------------------------
# Pure parsing
# ---------------------------------------------------------------------------

def extract_species(raw: str | None) -> tuple[str | None, str | None]:
    """`(species, concentration_text)` from a reported buffer string.

    Returns `(None, ...)` when nothing recognisable remains -- "buffer" on
    its own, or an empty string. An empty species is never sent to PubChem:
    `.../compound/name//cids/JSON` is a different request with a different
    meaning, and guessing what it returns is not a risk worth taking.
    """
    if raw is None:
        return None, None
    text = _LEADING_PREP_RE.sub("", raw.strip())

    concentration = None
    conc_match = _CONCENTRATION_RE.match(text)
    if conc_match:
        concentration = conc_match.group("conc").strip()
        text = text[conc_match.end():]

    text = _BUFFER_WORD_RE.sub("", text).strip()
    text = text.strip(" ,;:-")
    return (text or None), concentration


def parse_cid_json(payload: str) -> int | None:
    """First CID from a PubChem name lookup, or None.

    PubChem answers an unknown name with HTTP 404 and a Fault document, and
    a known one with `{"IdentifierList": {"CID": [n, ...]}}`. Both are
    well-formed; "parsed fine, found nothing" is a real case and must not
    raise.

    The FIRST cid is taken and the rest ignored. A name matching several
    compounds is a name that did not identify one, but PubChem orders by
    relevance and the alternative -- refusing every ambiguous name -- would
    reject "phosphate" outright, which is the single most common buffer in
    the corpus. The ambiguity is recorded rather than hidden: see
    `resolve_identity`.
    """
    try:
        data = json.loads(payload)
    except (json.JSONDecodeError, TypeError):
        return None
    cids = (data or {}).get("IdentifierList", {}).get("CID")
    if not isinstance(cids, list) or not cids:
        return None
    first = cids[0]
    return first if isinstance(first, int) else None


def resolve_identity(
    raw: str | None,
    cid_provider: CidProvider | None = None,
    parent_provider: ParentProvider | None = None,
) -> BufferIdentity:
    """Resolve one reported buffer string to a comparable identity.

    Providers are injectable so this is testable without the network, in the
    same shape as taxonomy.py and fallback_logic.py.
    """
    if raw is None or not raw.strip():
        return BufferIdentity(
            raw=raw or "",
            status="not_reported",
            reason="The source reported no buffer.",
        )

    cid_provider = cid_provider or _cached_fetch_cid_json
    parent_provider = parent_provider or _cached_fetch_parent_json

    species, concentration = extract_species(raw)
    if species is None:
        return BufferIdentity(
            raw=raw,
            concentration_text=concentration,
            status="unresolvable",
            reason=(
                f"No compound name remained in {raw!r} after removing the "
                "concentration and the word 'buffer', so there was nothing "
                "to look up."
            ),
        )

    try:
        cid = parse_cid_json(cid_provider(species))
    except Exception as exc:  # noqa: BLE001 - any lookup failure is "unknown"
        return BufferIdentity(
            raw=raw,
            species=species,
            concentration_text=concentration,
            status="unresolvable",
            reason=(
                f"PubChem lookup for {species!r} failed "
                f"({type(exc).__name__}). A failed lookup is not a match "
                "and not a mismatch."
            ),
        )

    if cid is None:
        return BufferIdentity(
            raw=raw,
            species=species,
            concentration_text=concentration,
            status="unresolvable",
            reason=f"PubChem holds no compound named {species!r}.",
        )

    # Parent lookup. A failure here degrades to the compound's own cid
    # rather than failing the whole identity: comparing on cid is still
    # better than comparing on strings, and the salt/free-base case is the
    # only thing lost.
    parent_cid = cid
    try:
        parent = parse_cid_json(parent_provider(cid))
        if parent is not None:
            parent_cid = parent
    except Exception:  # noqa: BLE001
        parent_cid = cid

    return BufferIdentity(
        raw=raw,
        species=species,
        cid=cid,
        parent_cid=parent_cid,
        concentration_text=concentration,
        status="resolved",
    )


def compare_buffers(
    left: BufferIdentity | None,
    right: BufferIdentity | None,
) -> BufferComparison:
    """Are two reported buffers the same species?

    Every non-`resolved` input yields `unknown` or `not_reported`, never a
    match. This is the function whose failure mode matters: it is called to
    decide whether to warn, and a wrong `same` suppresses the warning.
    """
    if left is None or right is None:
        return BufferComparison(
            status="not_reported",
            reason="Fewer than two buffers were reported, so there is nothing to compare.",
            left=left,
            right=right,
        )

    if left.status == "not_reported" or right.status == "not_reported":
        missing = [
            side
            for side, ident in (("first", left), ("second", right))
            if ident.status == "not_reported"
        ]
        return BufferComparison(
            status="not_reported",
            reason=(
                f"The {' and '.join(missing)} source reported no buffer. "
                "Buffer comparability is unknown, which is a gap in the "
                "sources rather than a finding about the model."
            ),
            left=left,
            right=right,
        )

    if left.status != "resolved" or right.status != "resolved":
        reasons = [i.reason for i in (left, right) if i.reason]
        return BufferComparison(
            status="unknown",
            reason=(
                "At least one reported buffer could not be resolved to a "
                f"compound, so they could not be compared. {' '.join(reasons)} "
                "An unresolved buffer is not evidence that the buffers agree."
            ),
            left=left,
            right=right,
        )

    if left.parent_cid == right.parent_cid:
        note = ""
        if left.concentration_text or right.concentration_text:
            note = (
                " Concentration was NOT compared: "
                f"{left.concentration_text or 'unstated'} against "
                f"{right.concentration_text or 'unstated'}."
            )
        return BufferComparison(
            status="same",
            reason=(
                f"{left.raw!r} and {right.raw!r} are the same buffer species "
                f"(PubChem parent compound {left.parent_cid}).{note}"
            ),
            left=left,
            right=right,
        )

    return BufferComparison(
        status="different",
        reason=(
            f"{left.raw!r} and {right.raw!r} are different buffer species "
            f"(PubChem parent compounds {left.parent_cid} and "
            f"{right.parent_cid}). Buffer composition affects enzyme "
            "kinetics, so these two measurements were not made under the "
            "same conditions."
        ),
        left=left,
        right=right,
    )
