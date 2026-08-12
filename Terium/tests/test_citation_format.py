"""Every modelCitations entry must be lookuppable.

Stage 4 Part 4 checked all seven references against the literature and found
three wrong, including a molecular-dynamics citation whose title does not
exist: "Hoare M.R., Pal P. (1971) Physical clusters of simple liquids."

No structural test could have caught it. Part 3's Target A checks key
correspondence and Target B checks that citations appear only on resolved
parameters -- both verify the *shape* of a provenance record, and a
fabricated title is a perfectly well-shaped string.

`scripts/check_citation_format.py` closes the part of that gap automation can
reach. It cannot confirm a paper exists, but it can require the fields that
make a citation checkable by hand: authors, a year, and either a volume/page
range, a publisher, or a URL. The fabricated entry above had none of them.

This test exists because the guard shipped wired to nothing -- not to pytest,
not to CI, not to verify_domain.sh. That is exactly how
check_rng_convention.py sat unenforced after Stage 2 until a test wrapped it.
A guard nobody runs is a guard that rots.
"""

import pathlib
import sys

_SCRIPTS_DIR = pathlib.Path(__file__).resolve().parents[2] / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from check_citation_format import check, check_entry  # noqa: E402

# The real string from before the Part 4 correction.
FABRICATED = "Hoare M.R., Pal P. (1971) Physical clusters of simple liquids."

CORRECTED = (
    "Hoare M.R., Pal P. (1971) Physical cluster mechanics: statics and "
    "energy surfaces for monatomic systems. Advances in Physics 20(84), "
    "161-196."
)


def test_all_model_citations_are_lookuppable() -> None:
    violations = check()
    assert not violations, (
        "Citation-format violations found:\n"
        + "\n".join(f"  {v}" for v in violations)
        + "\n\nEvery modelCitations entry needs authors, a year, and either a "
        "volume/page range, a publisher, or a URL. See "
        "Business/build-stages/STAGE_04_PART_04.md."
    )


def test_guard_rejects_the_citation_that_motivated_it() -> None:
    """A guard that passes this is not doing anything."""
    problems = check_entry(1, FABRICATED)
    assert problems, (
        "the guard accepted a bare title with no volume, pages, publisher or "
        "URL -- it would not have caught the Part 4 defect"
    )
    assert any("cannot be looked up" in p for p in problems)


def test_guard_accepts_the_corrected_citation() -> None:
    """It must not reject the properly-formed replacement."""
    assert check_entry(1, CORRECTED) == []


def test_guard_accepts_a_database_url() -> None:
    """BRENDA is a database, not a paper: a URL substitutes for pages."""
    brenda = (
        "BRENDA — The Comprehensive Enzyme Information System, "
        "https://www.brenda-enzymes.org/"
    )
    assert check_entry(1, brenda) == []


def test_guard_rejects_a_missing_year() -> None:
    assert check_entry(1, "Hoare M.R., Pal P. Advances in Physics 20, 161-196.")


def test_guard_rejects_an_empty_entry() -> None:
    assert check_entry(1, "   ")
