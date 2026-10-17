"""What BRENDA says a reference id is: authors, title, journal, year, PMID.

WHY THIS EXISTS
---------------
A cited claim names a BRENDA reference id ("641068"). A reader of `caterva
why` wants the paper, not the id, and the checker wants the paper's page
pinned beside the enzyme page so the title it prints is also re-checkable.
BRENDA serves one page per (enzyme, reference):

    https://www.brenda-enzymes.org/literature.php?e=<EC>&r=<reference id>

Tests/citation.py's docstring records that `literature.php?refid=<id>`
returns the same empty template for every id (checked 2026-07); the
`?e=&r=` form above returns the reference (checked 2026-10-17; six such
pages for EC 2.7.1.1 are recorded under Tests/fixtures/recorded/). The
product's citation URL stays the enzyme page (`brenda_reference_url`), whose
output the TypeScript contract pins; `brenda_literature_url` beside it gives
this form.

WHAT IS READ, AND HOW
---------------------
The page holds one `<li class="reference">` after the heading "Literature
summary for <EC> extracted from": the authors in `reference__authors`, the
title in `reference__title`, then `(<year>), <em><journal></em>, ...`, and a
PubMed link. Each is read with a regular expression against that structure;
a page without the title block is refused (`EvidenceRefused`) rather than
returned with blanks, because a blank title is what BRENDA's template page
for an unknown id looks like, and a record that cannot tell the two apart
would cite the template.
"""
from __future__ import annotations

import html as html_module
import re
from dataclasses import dataclass

try:
    from caterva.evidence.claims import EvidenceRefused
except ImportError:  # pragma: no cover - flat layout
    from evidence.claims import EvidenceRefused  # type: ignore[no-redef]

LITERATURE_URL = "https://www.brenda-enzymes.org/literature.php"

_AUTHORS = re.compile(r'class="reference__authors">(.*?)</div>', re.S)
_TITLE = re.compile(r'class="reference__title">(.*?)</span>(.*?)</div>', re.S)
_YEAR = re.compile(r"\((\d{4})\)")
_JOURNAL = re.compile(r"<em>(.*?)</em>", re.S)
_PMID = re.compile(r"pubmed\.ncbi\.nlm\.nih\.gov/(\d+)")
_PAGE_TITLE = re.compile(r"<title>Reference to ([0-9.]+); Id = (\d+)", re.S)
_TAGS = re.compile(r"<[^>]+>")


@dataclass(frozen=True)
class ReferencePage:
    """One BRENDA reference, as its literature page states it."""

    authors: str
    title: str
    journal: str | None
    year: str | None
    pmid: str | None
    ec: str | None = None
    reference: str | None = None


def _text(fragment: str) -> str:
    return html_module.unescape(_TAGS.sub("", fragment)).strip()


def reference_url(ec: str, ref: str) -> str:
    """The literature page for reference `ref` of enzyme `ec`."""
    if not ec or not ref:
        raise EvidenceRefused("a reference URL needs both the EC number and the reference id")
    return f"{LITERATURE_URL}?e={ec}&r={ref}"


def parse_reference_page(html: str) -> ReferencePage:
    """Read a literature.php page; refuse one that holds no reference."""
    title = _TITLE.search(html)
    authors = _AUTHORS.search(html)
    if title is None or authors is None:
        raise EvidenceRefused(
            "this page holds no reference block (no reference__title / "
            "reference__authors): it is BRENDA's template for an id it does not "
            "know, or not a literature.php page at all"
        )
    tail = title.group(2)
    year = _YEAR.search(tail)
    journal = _JOURNAL.search(tail)
    pmid = _PMID.search(html)
    page_title = _PAGE_TITLE.search(html)
    return ReferencePage(
        authors=_text(authors.group(1)),
        title=_text(title.group(1)),
        journal=_text(journal.group(1)) if journal else None,
        year=year.group(1) if year else None,
        pmid=pmid.group(1) if pmid else None,
        ec=page_title.group(1) if page_title else None,
        reference=page_title.group(2) if page_title else None,
    )


__all__ = ["LITERATURE_URL", "ReferencePage", "parse_reference_page", "reference_url"]
