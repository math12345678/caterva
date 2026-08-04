"""
citation.py

A single, shared Citation model for every data source Terrium pulls
kinetics data from (BRENDA today; PubMed literature and others later).
Keeping one model means downstream code (UI, exports, the eventual
Citation object in the product) never has to branch on "which source
gave me this number" - it just reads a Citation.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class Citation(BaseModel):
    source: str  # "BRENDA" | "PubMed" | "manual"
    reference_id: Optional[str] = None      # BRENDA ref id or PMID
    url: Optional[str] = None
    title: Optional[str] = None
    organism: Optional[str] = None
    notes: Optional[str] = None             # e.g. flag_reason, caveats


def brenda_reference_url(
    reference_id: str | None, ec_number: str | None = None
) -> str | None:
    """Best available link for a BRENDA reference.

    IMPORTANT: BRENDA does NOT have a working per-reference deep link.
    "literature.php?refid=..." was assumed to be one and shipped
    unverified - live-checked 2026-07 and confirmed broken: every
    reference_id (740541, 740001, 286460, 740253, 721735, with and
    without an ecno param) returns the IDENTICAL generic template page
    (same byte length, blank "Reference for EC = " title) rather than
    real per-reference content. That pattern is not a real citation link
    and must never be presented as one.

    The only confirmed-working, real page containing this reference is
    the parent enzyme page itself (enzyme.php?ecno=...), which does
    genuinely list the reference (by reference_id) among its data - just
    not deep-linked to that specific entry. If ec_number is available,
    that's what's returned; the reference_id itself is still carried on
    the Citation separately so a user can locate it on that page. If
    ec_number isn't available either, this returns None rather than a
    broken link - no citation URL is better than a fake one.
    """
    if not reference_id:
        return None
    if not ec_number:
        return None
    return f"https://www.brenda-enzymes.org/enzyme.php?ecno={ec_number}"


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
