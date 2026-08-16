"""No public page may claim an endorsement that is not on record.

Wraps `scripts/check_no_fabricated_endorsements.py`, and replays the real
fabricated testimonial to prove the guard would have caught it.

The replay matters more than the pass. The guard passes today because the
carousel was deleted; a guard written after the fact and never shown to
fire on the thing it was written for is a guess.
"""
from __future__ import annotations

import pathlib
import sys

_SCRIPTS_DIR = pathlib.Path(__file__).resolve().parents[1] / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import check_no_fabricated_endorsements as guard  # noqa: E402

#: Verbatim from the carousel that was live until 2026-08-15.
REAL_FABRICATION = '''    author: "Dr. Sarah Chen",
    role: "Biochemistry Faculty",
    source: "Stanford University",
'''


def test_no_public_page_claims_an_unbacked_endorsement() -> None:
    assert guard.main() == 0


def test_it_catches_the_testimonial_that_was_actually_live(tmp_path) -> None:
    """The replay. This is the whole reason the guard exists."""
    page = tmp_path / "TestimonialCarousel.tsx"
    page.write_text(REAL_FABRICATION)
    problems = guard.find_claims([page], recorded="")
    assert problems, (
        "the guard does not catch the exact fabricated testimonial it was "
        "written for"
    )
    assert "Stanford" in problems[0]


def test_the_trusted_by_heading_is_caught_too(tmp_path) -> None:
    """The heading was as much of a claim as the quotes under it."""
    page = tmp_path / "page.tsx"
    page.write_text('  Built for teaching labs. Trusted by MIT educators.\n')
    assert guard.find_claims([page], recorded="")


def test_a_recorded_endorsement_is_allowed(tmp_path) -> None:
    """The guard must not block a real, permissioned endorsement.

    If it did, the only way to ship a genuine testimonial would be to
    disable the check, and a disabled check protects nothing.
    """
    page = tmp_path / "page.tsx"
    page.write_text('    source: "Stanford University",\n')
    recorded = "| Stanford University | permission on file 2026-09-01 |"
    assert guard.find_claims([page], recorded=recorded) == []


def test_a_cited_database_is_not_an_endorsement(tmp_path) -> None:
    """Crying wolf on a citation is how this guard gets switched off.

    The molecular-dynamics domain checks its results against the Cambridge
    Cluster Database. Citing a source is the opposite of claiming its
    endorsement.
    """
    page = tmp_path / "terminal.ts"
    page.write_text("  and independently listed in the Cambridge Cluster Database.\n")
    assert guard.find_claims([page], recorded="") == []


def test_the_mit_licence_is_not_the_university(tmp_path) -> None:
    page = tmp_path / "about.tsx"
    page.write_text("Released under the MIT License.\n")
    assert guard.find_claims([page], recorded="") == []


def test_the_university_of_washington_attribution_is_not_a_claim(tmp_path) -> None:
    """Terrium is obliged to name libRoadRunner's copyright holder.

    An attribution the licence requires must not be mistaken for a boast.
    """
    page = tmp_path / "notice.tsx"
    page.write_text("libRoadRunner, Copyright University of Washington\n")
    assert guard.find_claims([page], recorded="") == []


def test_the_removal_table_does_not_excuse_the_fabrications_it_records(tmp_path, monkeypatch) -> None:
    """The hole that was live until the block was added.

    ENDORSEMENTS.md documents the five removed fabrications in a table.
    While the guard read the whole file, `"| Stanford" in recorded` matched
    that table -- so four of the five institutions were exempt from every
    public page, excused by the document written to condemn them.
    """
    recorded = guard._recorded()
    assert recorded is not None
    for name in ("Stanford", "MIT", "Johns Hopkins", "UC Berkeley"):
        assert f"| {name}" not in recorded, (
            f"{name} is excused by the allowlist block. If that is because "
            "the removal table leaked into it, the block delimiters moved."
        )

    page = tmp_path / "page.tsx"
    page.write_text('    source: "Stanford University",\n')
    assert guard.find_claims([page], recorded=recorded), (
        "a fabricated Stanford testimonial is still excused"
    )


def test_a_missing_allowlist_block_fails_rather_than_allowing_everything(
    tmp_path, monkeypatch, capsys
) -> None:
    """No block must not read as an empty-and-therefore-permissive one."""
    stub = tmp_path / "ENDORSEMENTS.md"
    stub.write_text("# Endorsements\n\nNothing machine-readable here.\n")
    monkeypatch.setattr(guard, "ENDORSEMENTS", stub)
    assert guard._recorded() is None
    assert guard.main() == 1
    assert "no REAL-ENDORSEMENTS-START block" in capsys.readouterr().out


def test_a_missing_endorsements_file_fails_rather_than_skips(monkeypatch, capsys) -> None:
    """'No file' must not mean 'no rules'."""
    monkeypatch.setattr(guard, "ENDORSEMENTS", pathlib.Path("/nonexistent/x.md"))
    assert guard.main() == 1
    assert "ENDORSEMENTS.md is missing" in capsys.readouterr().out


def test_the_floor_fires_when_the_scan_finds_nothing(monkeypatch, capsys) -> None:
    monkeypatch.setattr(guard, "PUBLIC_TREES", ("no/such/tree",))
    assert guard.main() == 1
    assert "below the floor" in capsys.readouterr().out


def test_the_citation_exemption_does_not_exempt_a_testimonial_field(tmp_path) -> None:
    """The near-miss that nearly shipped, pinned.

    `Source: Hoare & Pal (1971)` is a citation. `source: "Stanford
    University"` is a testimonial field. A case-insensitive check for
    "Source:" exempts both, and the first version of this guard did --
    meaning it would have passed the exact carousel it was written to
    catch.
    """
    citation = tmp_path / "README.md"
    citation.write_text("Source: Hoare & Pal, Adv. Phys. 20, 161 (1971), Cambridge\n")
    assert guard.find_claims([citation], recorded="") == []

    testimonial = tmp_path / "t.tsx"
    testimonial.write_text('    source: "Stanford University",\n')
    assert guard.find_claims([testimonial], recorded=""), (
        "a testimonial field was exempted by the citation rule"
    )


def test_every_exemption_carries_a_reason() -> None:
    for context, reason in {**guard.LEGITIMATE_CONTEXTS,
                            **guard.LEGITIMATE_PATTERNS}.items():
        assert len(reason) > 20, (
            f"LEGITIMATE_CONTEXTS[{context!r}] gives no reason. An exemption "
            "nobody can evaluate becomes a hole someone widens."
        )


def test_the_endorsements_file_still_says_there_are_none() -> None:
    """Pinned so the absence stays explicit.

    This SHOULD fail when a real endorsement is obtained -- that is the
    moment to update the file and this test together.
    """
    text = (guard.ROOT / "docs" / "ENDORSEMENTS.md").read_text()
    assert "There are none" in text, (
        "docs/ENDORSEMENTS.md no longer states that there are no "
        "endorsements. If one was obtained, record the permission behind it."
    )
