"""
source_context.py

What the commentary says the enzyme was taken FROM.

WHY THIS EXISTS
---------------
ADR 0031's coverage guard left three groups of unread commentary. Two are
now read (ADR 0032 effectors, ADR 0035 named forms). This is the third, and
it turned out to contain the sharpest finding of the set.

BRENDA's commentary names the biological source in prose:

    "enzyme from heart"
    "enzyme from muscle"
    "enzyme from adult" / "from pupa" / "from larva"
    "healthy breast tissue enzyme"
    "breast cancer tissue enzyme"
    "from human"   <- on a row whose ORGANISM COLUMN says Drosophila

THE TWO FINDINGS
----------------
**1. The commentary contradicts the organism column.**

Three acetylcholinesterase turnover rows carry
`organism = "Drosophila melanogaster"` while the commentary says the enzyme
came `from human` (6670) and `from eel` (13700).

That matters more than it first looks. ADR 0024 made cross-species
substitution opt-in on Lisa Jeske's recommendation, and the entire gate
reads the organism column. A row whose column says Drosophila and whose
commentary says human passes that gate as a Drosophila measurement --
the protection is intact and the data walks around it.

**2. Tissue changes the value more than species does.**

In the LDH turnover table, within ONE organism:

    Gallus gallus, heart    60.0
    Gallus gallus, muscle    1.1 - 3.3

A factor of fifty-four, and `min()` takes 1.1 and calls it the chicken LDH
turnover number. Bactrocera dorsalis spans 587 (adult), 1079 (pupa) and
1820 (larva) the same way.

Terrium spent four ADRs making sure a rabbit's Km is not offered as a
human's. Nothing was checking that a chicken's *muscle* Km is not offered as
a chicken's *heart* Km, and here the second gap is the larger number.

HOW THE TWO ARE TOLD APART, WITHOUT A LIST OF TISSUES
-----------------------------------------------------
`"from human"` and `"from heart"` are the same shape. Distinguishing them
means knowing that one is an organism and the other is an anatomical part.

The authority answers it: a token that **resolves to an NCBI taxon** is an
organism claim; one that does not is a source claim. Same move as
`form_mixture.py` asking PubChem whether "NAD" is a compound, and for the
same reason -- a hardcoded tissue vocabulary would be unsourced biology in a
file nobody reviews as biology.

WHY A SEPARATE TAXON LOOKUP
---------------------------
`enzyme_lookup.fetch_taxon_id` restricts its search to `[Scientific Name]`,
deliberately: BRENDA's organism COLUMN is binomial, and an unrestricted
search risks resolving an ambiguous string to the wrong taxon.

Commentary is prose and says "human", not "Homo sapiens". So this module
needs an unrestricted lookup, and inherits the ambiguity the other function
avoids. That is acceptable HERE and would not be acceptable there, because
the output is a discrepancy to check rather than a value to use: a
spuriously resolved token produces a flag a reader dismisses, where a
spuriously resolved organism would produce a number they trust.

THREE STATES
------------
`organism`, `source`, `unresolved`. A token whose lookup failed is not
"definitely a tissue" -- treating it as one would let a real organism
contradiction through as an anatomical note.
"""
from __future__ import annotations

import re
from typing import Callable

from pydantic import BaseModel

from http_retry import retry_get

NCBI_TAXONOMY_ESEARCH_URL = (
    "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
)

#: "enzyme from heart", "from human", "enzyme form heart and muscle".
#:
#: `f(?:ro|or)m` covers the typo "form" for "from", which appears in the
#: corpus as "enzyme form heart and muscle". Correcting a curator's typo
#: silently would be wrong; reading through it is not.
#:
#: Written `fro?m` at first -- which matches "from" and "frm" and NOT
#: "form", because the letters are transposed rather than dropped. Caught by
#: the test that names the corpus string explicitly, which is the argument
#: for tests being written from the corpus rather than from imagination.
_FROM_RE = re.compile(
    r"\b(?:enzyme\s+)?f(?:ro|or)m\s+(?P<token>[a-zA-Z][a-zA-Z ]{2,30}?)"
    r"(?=\s*(?:,|;|\.|$|and\b|at\b|in\b|with\b))",
    re.IGNORECASE,
)

#: "healthy breast tissue", "breast cancer tissue", "normal liver tissue".
_TISSUE_STATE_RE = re.compile(
    r"\b(?P<state>healthy|normal|cancer|cancerous|tumou?r|tumou?rous|malignant)\s+"
    r"(?P<token>[a-z]+(?:\s+[a-z]+)?)\s+tissue"
    r"|\b(?P<token2>[a-z]+(?:\s+[a-z]+)?)\s+(?P<state2>cancer|tumou?r)\s+tissue",
    re.IGNORECASE,
)

#: Words that follow "from" without naming a source.
_NOT_A_SOURCE = {"the", "which", "this", "that", "these", "those", "a", "an"}

_HEALTHY = {"healthy", "normal"}


class SourceClaim(BaseModel):
    """One thing the commentary says the enzyme came from."""

    #: The token as written: "heart", "human", "breast".
    token: str

    #: "organism" | "source" | "unresolved"
    kind: str = "unresolved"

    #: NCBI taxon id, when `kind == "organism"`.
    taxon_id: str | None = None

    #: "healthy" | "diseased" | None. Only set by the tissue-state pattern.
    disease_state: str | None = None

    #: The exact substring, so the extraction can be checked not trusted.
    evidence: str


class OrganismDiscrepancy(BaseModel):
    """The commentary names an organism the organism column does not."""

    value: float
    column_organism: str
    commentary_organism: str
    column_taxon: str | None
    commentary_taxon: str | None
    reason: str


class SourceMixture(BaseModel):
    """One organism, several biological sources, in one candidate pool."""

    organism: str
    #: source token -> the values reported for it, sorted.
    values_by_source: dict[str, list[float]]
    reason: str

    @property
    def fold_difference(self) -> float | None:
        values = [v for vs in self.values_by_source.values() for v in vs]
        if len(self.values_by_source) < 2 or not values:
            return None
        lo, hi = min(values), max(values)
        return hi / lo if lo else None


TaxonProvider = Callable[[str], str | None]


def fetch_taxon_id_any_name(organism_name: str, timeout: float = 15) -> str | None:
    """NCBI taxon id for a name searched across ALL fields.

    Unrestricted on purpose -- see the module header. `enzyme_lookup`'s
    scientific-name-only lookup cannot resolve "human", and commentary is
    prose.
    """
    from enzyme_lookup import _ncbi_params  # local import: avoids a cycle

    response = retry_get(
        NCBI_TAXONOMY_ESEARCH_URL,
        params=_ncbi_params(db="taxonomy", term=organism_name, retmode="json"),
        timeout=timeout,
    )
    response.raise_for_status()
    ids = (response.json().get("esearchresult") or {}).get("idlist") or []
    return ids[0] if ids else None


def _classify_token(
    token: str, taxon_provider: TaxonProvider | None
) -> tuple[str, str | None]:
    """`(kind, taxon_id)` for one extracted token."""
    provider = taxon_provider or fetch_taxon_id_any_name
    try:
        taxon = provider(token)
    except Exception:  # noqa: BLE001
        # A failed lookup is `unresolved`, never `source`. Calling it a
        # tissue would let a real organism contradiction through as an
        # anatomical note -- the silent direction.
        return "unresolved", None
    if taxon:
        return "organism", taxon
    return "source", None


def extract_source_claims(
    commentary: str | None, taxon_provider: TaxonProvider | None = None
) -> list[SourceClaim]:
    """Everything the commentary says about biological source."""
    if not commentary or not commentary.strip():
        return []

    claims: list[SourceClaim] = []

    for match in _TISSUE_STATE_RE.finditer(commentary):
        token = (match.group("token") or match.group("token2") or "").strip()
        state = (match.group("state") or match.group("state2") or "").lower()
        if not token:
            continue
        kind, taxon = _classify_token(token, taxon_provider)
        claims.append(
            SourceClaim(
                token=token,
                kind=kind,
                taxon_id=taxon,
                disease_state="healthy" if state in _HEALTHY else "diseased",
                evidence=match.group(0).strip(),
            )
        )

    for match in _FROM_RE.finditer(commentary):
        token = match.group("token").strip().lower()
        if not token or token in _NOT_A_SOURCE:
            continue
        if any(c.token.lower() == token for c in claims):
            continue
        kind, taxon = _classify_token(token, taxon_provider)
        claims.append(
            SourceClaim(
                token=token, kind=kind, taxon_id=taxon,
                evidence=match.group(0).strip(),
            )
        )
    return claims


def _is_name_refinement(a: str, b: str) -> bool:
    """Is one name a less precise way of writing the other?

    "Drosophila" against "Drosophila melanogaster": the first is the genus of
    the second, and BRENDA writes both. Compared on leading word tokens
    rather than by fetching two lineages, because this is a question about
    the NAMES and the cheap answer is the right one for the case that occurs.

    LIMITATION, stated rather than discovered later: this does not catch
    "D. melanogaster", and it does not catch a common name that happens to
    denote the same clade ("fruit fly"). Both would be reported as
    discrepancies -- a flag a reader dismisses, which is the safe direction.
    """
    ta = [w for w in a.lower().replace(".", " ").split() if w]
    tb = [w for w in b.lower().replace(".", " ").split() if w]
    if not ta or not tb:
        return False
    shorter, longer = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
    return longer[: len(shorter)] == shorter


def find_organism_discrepancies(
    rows: list[tuple[float, str, str | None]],
    taxon_provider: TaxonProvider | None = None,
) -> list[OrganismDiscrepancy]:
    """Rows whose commentary names a DIFFERENT organism than their column.

    `rows` is `(value, column_organism, commentary)`.

    Both sides must resolve before a discrepancy is claimed. An unresolved
    token is not a contradiction -- it is a token nobody could place.
    """
    found: list[OrganismDiscrepancy] = []
    for value, column_organism, commentary in rows:
        claims = [
            c
            for c in extract_source_claims(commentary, taxon_provider)
            if c.kind == "organism"
        ]
        if not claims:
            continue
        column_kind, column_taxon = _classify_token(column_organism, taxon_provider)
        if column_taxon is None:
            continue
        for claim in claims:
            if claim.taxon_id == column_taxon:
                continue
            if _is_name_refinement(claim.token, column_organism):
                # "from Drosophila" on a "Drosophila melanogaster" row is a
                # genus naming its own species: agreement written less
                # precisely, not a contradiction. NCBI gives them different
                # taxon ids (7215 and 7227), so an id comparison alone
                # reports every such row -- and BRENDA writes them
                # constantly.
                continue
            found.append(
                OrganismDiscrepancy(
                    value=value,
                    column_organism=column_organism,
                    commentary_organism=claim.token,
                    column_taxon=column_taxon,
                    commentary_taxon=claim.taxon_id,
                    reason=(
                        f"The organism column says {column_organism!r} "
                        f"(taxon {column_taxon}) and the commentary says the "
                        f"enzyme came from {claim.token!r} (taxon "
                        f"{claim.taxon_id}). Terrium's cross-species gate "
                        "reads the column, so this row passes as a "
                        f"{column_organism} measurement. One of the two is "
                        "wrong and Terrium cannot tell which."
                    ),
                )
            )
    return found


class SourceCheckUnavailable(BaseModel):
    """Tokens were extracted and none could be classified.

    Exists because `find_source_mixtures` returning `[]` otherwise means two
    different things: the pool was clean, or the classifier could not reach
    NCBI and every token came back `unresolved`.

    Found by running the real resolution path instead of a fixture. With the
    network blocked, `(Gallus gallus, NAD+)` -- a pool genuinely holding
    heart 60.0 and muscle 3.3 -- reported no mixture at all, silently. An
    empty result that can mean "nothing found" or "nothing checked" is the
    conflation this project spends most of its effort on, and this module
    had shipped it.
    """

    tokens: list[str]
    reason: str = (
        "Source tokens were found in the commentary and none could be "
        "classified, so this pool was NOT checked for mixed biological "
        "sources. That is different from a pool with none."
    )


def find_source_mixtures(
    rows: list[tuple[float, str, str | None]],
    taxon_provider: TaxonProvider | None = None,
) -> list[SourceMixture]:
    """One organism measured from several biological sources in one pool.

    Grouped BY ORGANISM deliberately. Heart and muscle across two species is
    two ordinary cross-species rows, already governed by ADR 0024. Heart and
    muscle within one species is a difference the organism gate cannot see,
    and in the LDH table it is a factor of fifty-four.
    """
    by_organism: dict[str, dict[str, list[float]]] = {}
    for value, organism, commentary in rows:
        for claim in extract_source_claims(commentary, taxon_provider):
            if claim.kind != "source":
                continue
            label = claim.token.lower()
            if claim.disease_state:
                label = f"{claim.disease_state} {label}"
            by_organism.setdefault(organism, {}).setdefault(label, []).append(value)

    mixtures: list[SourceMixture] = []
    for organism in sorted(by_organism):
        sources = by_organism[organism]
        if len(sources) < 2:
            continue
        values_by_source = {s: sorted(v) for s, v in sorted(sources.items())}
        mixture = SourceMixture(
            organism=organism, values_by_source=values_by_source, reason=""
        )
        fold = mixture.fold_difference
        magnitude = (
            f" The values span a factor of {fold:.0f}." if fold and fold > 1 else ""
        )
        described = ", ".join(
            f"{s} = {v[0]}" + (f"–{v[-1]}" if len(v) > 1 else "")
            for s, v in values_by_source.items()
        )
        mixture.reason = (
            f"Within {organism}, the candidate rows report {len(sources)} "
            f"different biological sources: {described}.{magnitude} The "
            "cross-species gate cannot see this -- every row is the organism "
            "that was asked for, and they are still measurements of "
            "different material."
        )
        mixtures.append(mixture)
    return mixtures


def source_check_status(
    rows: list[tuple[float, str, str | None]],
    taxon_provider: TaxonProvider | None = None,
) -> SourceCheckUnavailable | None:
    """`None` when classification worked, a report when it did not.

    Deliberately a separate call rather than a third return value: callers
    that only want mixtures should not have to unpack a tuple, and callers
    that skip this one are making a visible omission rather than an
    invisible one.
    """
    unresolved: list[str] = []
    resolved_any = False
    for _value, _organism, commentary in rows:
        for claim in extract_source_claims(commentary, taxon_provider):
            if claim.kind == "unresolved":
                unresolved.append(claim.token)
            else:
                resolved_any = True
    if unresolved and not resolved_any:
        return SourceCheckUnavailable(tokens=sorted(set(unresolved)))
    return None
