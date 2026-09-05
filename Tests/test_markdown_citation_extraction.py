"""Which DOIs a markdown document ASSERTS, as opposed to discusses.

WHY THIS EXISTS
---------------
`verify_citations_live.py` checks every DOI Terrium cites. Until
2026-09-05 its `DOI_SOURCE_FILES` list held only `.ts` and `.py` sources,
so `LITERATURE_BACKING_DATABASE.md` -- the one document in the repository
whose entire purpose is to enumerate Terrium's citations -- was never read
by the citation checker.

The cost is measurable. `domain-literature.ts` was corrected on 2026-08-09
from `10.1038/ng.3285` (CrossRef: Polderman et al. 2015, a twin-studies
heritability meta-analysis) to Rahbari's real germline-mutation paper
`10.1038/ng.3469`. STAGE_10_PART_06 then recorded "the ng.3285 citation
surviving in two markdown files after the code was fixed" as a known
symptom of duplicated sources of truth. It survived in that document for
another month.

THE PROBLEM ENROLLING IT CREATES
--------------------------------
A document that records its own corrections NAMES the DOIs it no longer
cites. Scraping every DOI out of it turns each documented mistake into a
permanent failing check -- the exact trap `_is_prose_line` was written for
in code, where a `//` prefix marks discussion.

Markdown has no `//`. Two rules replace it, and these tests pin both:

  1. `>` blockquote lines are prose. This repository writes corrections as
     blockquotes, so that is the markdown equivalent of a comment.
  2. A DOI is asserted only in `https://doi.org/...` link form. This is
     what separates the two DOIs on the Harter line, where the cited paper
     is a link and the wrong one it replaced is backticked in the same
     sentence -- a distinction no line-level rule can make.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys

_ROOT = pathlib.Path(__file__).resolve().parents[1]
_SCRIPT = _ROOT / "scripts" / "verify_citations_live.py"


def _load():
    spec = importlib.util.spec_from_file_location("verify_citations_live", _SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["verify_citations_live"] = module
    spec.loader.exec_module(module)
    return module


verify = _load()

# The real Harter line from LITERATURE_BACKING_DATABASE.md: one asserted
# DOI and one discussed DOI, in a single sentence.
HARTER_LINE = (
    "- **Citation**: https://doi.org/10.2307/1403077 (corrected 2026-09-05: "
    "`10.2307/1402059` resolves to Wilks, Kendall & Stuart (1959))"
)


def test_a_linked_doi_is_asserted() -> None:
    assert verify._dois_asserted_in(HARTER_LINE, markdown=True) == [
        "10.2307/1403077"
    ]


def test_a_backticked_doi_on_the_same_line_is_not() -> None:
    """The case that motivated the link-form rule.

    Both DOIs sit on one line, so no prose rule that works line-by-line can
    tell them apart. Checking the backticked one would report a failure for
    a citation the document explicitly says it no longer makes.
    """
    assert "10.2307/1402059" not in verify._dois_asserted_in(
        HARTER_LINE, markdown=True
    )
    # And the premise: it IS present in the text, so the exclusion is doing
    # work rather than describing an absence.
    assert "10.2307/1402059" in HARTER_LINE


def test_blockquotes_are_prose() -> None:
    quoted = (
        "> **⚠️ CORRECTION:** this previously cited "
        "https://doi.org/10.1038/ng.3285, which is a different paper."
    )
    assert verify._is_prose_line(quoted, markdown=True) is True
    # Even in link form: the blockquote rule is checked first.
    assert verify._dois_asserted_in(quoted, markdown=True) == ["10.1038/ng.3285"]


def test_bullets_are_not_prose_in_markdown() -> None:
    """`*` continues a block comment in C, but opens a bullet in markdown.

    Reusing _COMMENT_PREFIXES verbatim would have silently excluded every
    `* ` reference bullet -- a checker that reads a reference list and
    reports zero DOIs looks identical to one that works.
    """
    bullet = "* **Citation**: https://doi.org/10.1093/nar/gkw952"
    assert verify._is_prose_line(bullet, markdown=True) is False
    assert verify._is_prose_line(bullet, markdown=False) is True


def test_code_files_are_unaffected() -> None:
    """The markdown rules must not change how sources are scanned."""
    comment = "  // BACKING: https://doi.org/10.1038/ng.3469"
    assert verify._is_prose_line(comment) is True
    bare = '  doi: "10.1038/ng.3469",'
    assert verify._is_prose_line(bare) is False
    # Code asserts bare DOIs; markdown's link requirement must not apply.
    assert verify._dois_asserted_in(bare) == ["10.1038/ng.3469"]


def test_the_document_is_actually_enrolled() -> None:
    doc = _ROOT / "LITERATURE_BACKING_DATABASE.md"
    assert doc in verify.DOI_SOURCE_FILES, (
        "LITERATURE_BACKING_DATABASE.md was dropped from DOI_SOURCE_FILES; "
        "the file that lists Terrium's citations would stop being checked"
    )


def test_the_corrected_citations_are_the_ones_checked() -> None:
    """End-to-end over the real document, not a fixture.

    Pins both halves at once: the corrected DOIs are checked, and the wrong
    ones they replaced -- still named in the correction notes, on purpose --
    are not.
    """
    found = verify.discovered_dois()
    doc_name = "LITERATURE_BACKING_DATABASE.md"
    from_doc = {d for d, files in found.items() if doc_name in files}

    assert len(from_doc) >= 20, (
        f"only {len(from_doc)} DOIs discovered in {doc_name}; a matcher that "
        "found almost nothing would pass every check below vacuously"
    )

    for corrected in ("10.1038/ng.3469", "10.1016/j.pisc.2014.02.012",
                      "10.2307/1403077"):
        assert corrected in from_doc, f"{corrected} is cited but not checked"

    for withdrawn in ("10.1038/ng.3285", "10.1038/nbt0610-592",
                      "10.2307/1402059"):
        assert withdrawn not in from_doc, (
            f"{withdrawn} is named in a correction note as a citation this "
            "document NO LONGER makes; checking it would make every "
            "documented mistake a permanent failure"
        )


def test_a_legacy_elsevier_doi_survives_extraction() -> None:
    """Parentheses are part of the DOI, not punctuation around it.

    Gillespie 1976 is `10.1016/0021-9991(76)90041-3`. An earlier version of
    DOI_PATTERN excluded `)`, truncating it to `10.1016/0021-9991(76` and
    reporting a 404 the citation had not earned.
    """
    line = "- **Citation**: https://doi.org/10.1016/0021-9991(76)90041-3"
    assert verify._dois_asserted_in(line, markdown=True) == [
        "10.1016/0021-9991(76)90041-3"
    ]
