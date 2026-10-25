"""
citation.py

A single, shared Citation model for every data source Caterva pulls
kinetics data from (BRENDA today; PubMed literature and others later).
Keeping one model means downstream code (UI, exports, the eventual
Citation object in the product) never has to branch on "which source
gave me this number" - it just reads a Citation.
"""

from __future__ import annotations


from pydantic import BaseModel


class Citation(BaseModel):
    source: str  # "BRENDA" | "PubMed" | "manual"
    reference_id: str | None = None      # BRENDA ref id or PMID
    url: str | None = None
    title: str | None = None
    organism: str | None = None
    notes: str | None = None             # e.g. flag_reason, caveats


def brenda_reference_url(
    reference_id: str | None, ec_number: str | None = None
) -> str | None:
    """The citation link for a BRENDA reference: the parent enzyme page.

    "literature.php?refid=..." was assumed to be a per-reference deep link
    and shipped unverified - live-checked 2026-07 and confirmed broken:
    every reference_id (740541, 740001, 286460, 740253, 721735, with and
    without an ecno param) returns the IDENTICAL generic template page
    (same byte length, blank "Reference for EC = " title) rather than
    real per-reference content. That pattern must never be presented as a
    citation link.

    BRENDA does have a per-reference page in another form,
    "literature.php?e=<EC>&r=<reference_id>", which returns the reference
    (authors, title, journal, year, PubMed link) - checked 2026-10-17 for
    six references of EC 2.7.1.1, recorded under
    Tests/fixtures/recorded/brenda_reference_*.html.gz. That form is
    `brenda_literature_url` below, and the evidence layer
    (caterva/evidence/references.py) reads it. It is NOT what this function
    returns: this function's output is pinned across the TypeScript
    contract (citeVerify.ts, the runner contract test), and the enzyme page
    is the page that lists the reference among the data it was taken from.
    If ec_number is available, that's what's returned; the reference_id
    itself is still carried on the Citation separately so a user can
    locate it on that page. If ec_number isn't available either, this
    returns None rather than a broken link - no citation URL is better
    than a fake one.
    """
    if not reference_id:
        return None
    if not ec_number:
        return None
    return f"https://www.brenda-enzymes.org/enzyme.php?ecno={ec_number}"


def brenda_literature_url(ec_number: str | None, reference_id: str | None) -> str | None:
    """BRENDA's page for one reference of one enzyme, or None without both ids.

    "literature.php?e=<EC>&r=<reference_id>" returns the reference's
    authors, title, journal, year and PubMed link (checked 2026-10-17; see
    `brenda_reference_url` for the refid form that does not work). The
    evidence layer pins this page beside the enzyme page so a cited paper's
    title is re-checkable; the product's citation link stays the enzyme
    page, because the TypeScript contract pins that output.
    """
    if not ec_number or not reference_id:
        return None
    return f"https://www.brenda-enzymes.org/literature.php?e={ec_number}&r={reference_id}"


def pubmed_url(pmid: str | None) -> str | None:
    if not pmid:
        return None
    return f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"


def citation_from_brenda_entry(entry) -> Citation:
    """Build a Citation from a brenda_client.BRENDAKmEntry."""
    return Citation(
        source="BRENDA",
        reference_id=entry.reference_id,
        url=brenda_reference_url(entry.reference_id, entry.ec_number),
        organism=entry.organism,
        notes=entry.flag_reason,
    )
