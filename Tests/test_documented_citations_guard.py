"""The documented-citations guard, exercised rather than assumed.

WHY THIS FILE EXISTS
--------------------
`check_documented_citations_are_real.py` was wired into `verify_build.py`
and nothing else. Two consequences, both of which this file fixes:

1. **It ran in one harness.** `check_guard_wiring.py`'s Stage 4 amendment
   says a guard is not delivered until something runs it unasked, and one
   harness is the minimum rather than the target. A pytest entry means the
   guard is exercised by `make test` as well as by a full build.

2. **Its mutation table had nothing to count.** A guard script exits 0 or 1;
   `scripts/mutate.py` establishes its verdicts from a test count, and
   refuses -- correctly -- to grade a suite it cannot count. ADR 0144
   published a mutation table with no re-runnable set file, which is the
   exact rule ADR 0144 itself restored to working order. The set file needs
   a countable suite, and this is it.

WHAT IS ASSERTED
----------------
That the guard passes on the real tree, and that it FAILS on each of the two
defects it exists to catch. A guard verified only in the passing direction
is the "check that cannot fail" this repository keeps finding; asserting the
failure direction is what makes it evidence.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
GUARD = REPO / "scripts" / "check_documented_citations_are_real.py"


def run_guard() -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(GUARD)],
        cwd=REPO, capture_output=True, text=True, timeout=120,
    )


def test_the_tree_has_no_invented_citations():
    result = run_guard()
    assert result.returncode == 0, (
        "a documented BRENDA reference does not exist in any fixture:\n"
        + result.stdout
    )


def test_the_guard_reports_what_it_checked():
    """A verdict with no numbers behind it cannot be audited."""
    result = run_guard()
    assert "Reference ids in fixtures:" in result.stdout
    assert "Surfaces checked:" in result.stdout


@pytest.mark.parametrize(
    "bad_ref, why",
    [
        ("12345", "the original placeholder, which appeared in no fixture"),
        ("999999", "a plausible-looking id that is still not real"),
    ],
)
def test_an_invented_citation_fails_the_guard(tmp_path, bad_ref, why, monkeypatch):
    """Restore the defect and require the guard to catch it.

    The README is copied to a scratch tree rather than edited in place: this
    repository is worked on by several agents at once, and a test that
    mutates a tracked file can be observed mid-flight by another process --
    or lose its restore to one. That has already happened here twice.
    """
    readme = (REPO / "README.md").read_text(encoding="utf-8")
    assert "BRENDA ref 740253" in readme, (
        "the README no longer carries the real reference this test mutates"
    )
    damaged = readme.replace("BRENDA ref 740253", f"BRENDA ref {bad_ref}", 1)
    assert damaged != readme

    scratch = tmp_path / "repo"
    (scratch / "Tests" / "fixtures").mkdir(parents=True)
    (scratch / "docs").mkdir()
    (scratch / "scripts").mkdir()
    (scratch / "README.md").write_text(damaged, encoding="utf-8")
    (scratch / "docs" / "DESIGN.md").write_text("", encoding="utf-8")
    (scratch / "CONTRIBUTING.md").write_text("", encoding="utf-8")
    for fixture in sorted((REPO / "Tests" / "fixtures").glob("brenda_*.html")):
        (scratch / "Tests" / "fixtures" / fixture.name).write_text(
            fixture.read_text(encoding="utf-8", errors="replace"), encoding="utf-8"
        )
    (scratch / "scripts" / GUARD.name).write_text(
        GUARD.read_text(encoding="utf-8"), encoding="utf-8"
    )

    result = subprocess.run(
        [sys.executable, str(scratch / "scripts" / GUARD.name)],
        cwd=scratch, capture_output=True, text=True, timeout=120,
    )

    assert result.returncode == 1, f"the guard passed on {why}:\n{result.stdout}"
    assert bad_ref in result.stdout
    assert "README.md" in result.stdout


def scratch_tree(tmp_path, *, readme: str, fixtures: bool = True,
                 surfaces: bool = True) -> Path:
    """A minimal tree the guard can run against, missing what we choose."""
    root = tmp_path / "repo"
    (root / "Tests" / "fixtures").mkdir(parents=True)
    (root / "docs").mkdir()
    (root / "scripts").mkdir()
    (root / "README.md").write_text(readme, encoding="utf-8")
    if surfaces:
        (root / "docs" / "DESIGN.md").write_text("", encoding="utf-8")
        (root / "CONTRIBUTING.md").write_text("", encoding="utf-8")
    if fixtures:
        for fixture in sorted((REPO / "Tests" / "fixtures").glob("brenda_*.html")):
            (root / "Tests" / "fixtures" / fixture.name).write_text(
                fixture.read_text(encoding="utf-8", errors="replace"),
                encoding="utf-8",
            )
    (root / "scripts" / GUARD.name).write_text(
        GUARD.read_text(encoding="utf-8"), encoding="utf-8"
    )
    return root


def run_in(root: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(root / "scripts" / GUARD.name)],
        cwd=root, capture_output=True, text=True, timeout=120,
    )


def test_an_empty_fixture_corpus_fails_rather_than_passing_vacuously(tmp_path):
    """With nothing to compare against, the guard must not report success.

    A check is at its most dangerous when it knows least: no reference ids
    loaded means every citation is trivially fine, and the run prints OK.
    ADR 0144 claims this fails loudly and names the fixtures as the cause.
    It was claimed and not tested until `scripts/mutate.py` reported the
    branch NOT CAUGHT.
    """
    root = scratch_tree(tmp_path, readme="BRENDA ref 740253\n", fixtures=False)
    result = run_in(root)

    assert result.returncode == 1, result.stdout

    # Asserted on the SENTENCE THIS BRANCH WRITES, not on the word
    # "fixtures". The first version of this test checked
    # `"fixtures" in stdout.lower()` and passed under mutation, because the
    # guard's own header prints "Reference ids in fixtures: 0" whatever
    # happens -- so the assertion matched output that is always there.
    #
    # That is ADR 0133's rule for the third time in this repository: when the
    # output being tested contains an explanation of itself, a document-wide
    # `contains` is not an assertion. It happened here inside the test
    # written to close a NOT CAUGHT, and only `scripts/mutate.py` reporting
    # the branch still uncovered found it.
    assert "No reference ids found" in result.stdout, (
        "the guard did not take the empty-corpus branch; it fell through and "
        "reported the citations as unknown instead, which blames the README "
        "for a missing corpus:\n" + result.stdout
    )


def test_a_missing_surface_is_reported_not_skipped(tmp_path):
    """Deleting the file being checked must not be a way to pass.

    The same rule `check_non_affiliation_notice.py` states: a guard that
    shrugs at a missing file rewards removing it. Also claimed by ADR 0144
    and untested until the harness said so.
    """
    root = scratch_tree(tmp_path, readme="BRENDA ref 740253\n", surfaces=False)
    result = run_in(root)

    assert result.returncode == 1, result.stdout
    assert "does not exist" in result.stdout
    assert "CONTRIBUTING.md" in result.stdout or "DESIGN.md" in result.stdout


def test_the_surface_list_cannot_be_quietly_gutted():
    """Deleting the checklist is the easiest way to pass a check.

    `_MIN_SURFACES` is the floor `check_non_affiliation_notice.py` uses for
    the same reason. Asserted here because a floor nothing tests is a
    constant with a comment.
    """
    source = GUARD.read_text(encoding="utf-8")
    assert "_MIN_SURFACES" in source
    import importlib.util

    spec = importlib.util.spec_from_file_location("citation_guard", GUARD)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert len(module.SURFACES) >= module._MIN_SURFACES
