"""scripts/check_no_placeholder_dois.py: the guard passes on the repository and catches a placeholder.

WHY THIS EXISTS
---------------
The guard reads tracked Markdown (`git ls-files`), so the repository check
needs a checkout; the rest builds its own files. Both directions are
exercised: a guard that is only ever seen green on a clean tree is
indistinguishable from one whose matcher matches nothing (ADR 0015).

The three patterns are built from pieces here, as they are in the guard,
so that this file itself never prints the strings it is about.
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
GUARD = REPO / "scripts" / "check_no_placeholder_dois.py"


def _load():
    spec = importlib.util.spec_from_file_location("check_no_placeholder_dois", GUARD)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


guard = _load()
EXAMPLE_LINE = '"doi": "' + "10." + "1234/" + 'example"'
ZERO_LINE = "see " + "10." + "0000/" + "placeholder"
TEMPLATE_LINE = "cite as " + "DOI:" + "10.XXXX" + " when known"


def test_the_selftest_passes():
    assert guard.selftest() == 0


def test_the_repository_prints_no_placeholder_doi():
    result = subprocess.run(
        [sys.executable, str(GUARD)], capture_output=True, text=True, cwd=REPO,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "tracked Markdown files" in result.stdout


@pytest.mark.parametrize("line", [EXAMPLE_LINE, ZERO_LINE, TEMPLATE_LINE])
def test_each_kind_of_placeholder_is_found(line, tmp_path):
    (tmp_path / "doc.md").write_text(f"fine\n{line}\n", encoding="utf-8")
    assert guard.findings(tmp_path, ["doc.md"]) == [f"doc.md:2: {line}"]


def test_a_real_doi_and_a_prefix_without_a_slash_are_clean(tmp_path):
    (tmp_path / "doc.md").write_text(
        "doi:10.1093/nar/gkaa1025\nhttps://doi.org/10.1002/pro.2473\n"
        "the example prefix 10.1234 is refused when a slash follows it\n",
        encoding="utf-8",
    )
    assert guard.findings(tmp_path, ["doc.md"]) == []


def test_the_archive_is_not_read_and_an_allowed_file_is_skipped(tmp_path):
    (tmp_path / "docs" / "archive").mkdir(parents=True)
    (tmp_path / "docs" / "archive" / "old.md").write_text(EXAMPLE_LINE, encoding="utf-8")
    (tmp_path / "docs" / "science").mkdir(parents=True)
    (tmp_path / "docs" / "science" / "TESTING_AND_ROADMAP.md").write_text(EXAMPLE_LINE, encoding="utf-8")
    (tmp_path / "docs" / "live.md").write_text(EXAMPLE_LINE, encoding="utf-8")
    names = ["docs/archive/old.md", "docs/science/TESTING_AND_ROADMAP.md", "docs/live.md"]
    assert guard.findings(tmp_path, names) == [f"docs/live.md:1: {EXAMPLE_LINE}"]


def test_a_stale_allowance_is_reported(tmp_path):
    (tmp_path / "clean.md").write_text("cites doi:10.1093/nar/gkaa1025 only\n", encoding="utf-8")
    stale = guard.stale_allowances(tmp_path, {"clean.md": "r", "gone.md": "r"})
    assert [s.split(":")[0] for s in stale] == ["clean.md", "gone.md"]


def test_a_binary_file_is_not_read(tmp_path):
    (tmp_path / "blob.md").write_bytes(b"\0\0" + EXAMPLE_LINE.encode())
    assert guard.findings(tmp_path, ["blob.md"]) == []


#: The allowances as they stood on 2026-10-24. The guard says its lists may
#: only shrink, and until then nothing held them to it: a new entry for a
#: file that does print a placeholder passed every check in the loops below.
#: The same two files at the paths they moved to that day, when the root's
#: loose documents went into docs/ subfolders: a move renames an allowance,
#: it does not add one.
ALLOWED_AT_MOST = frozenset({
    "docs/science/TESTING_AND_ROADMAP.md",
    "docs/science/SCIENTIFIC_VALIDATION_FRAMEWORK.md",
})
EXCLUDED_AT_MOST = frozenset({"docs/archive/"})


def test_every_allowance_names_a_tracked_file_that_still_needs_it():
    """The lists only shrink, and every entry left is still needed.

    The first two asserts sit outside the loops on purpose: with both lists
    emptied the loops check nothing, and the guard's own rule still holds.
    Removing an entry needs no edit here; adding one fails until this set is
    widened in review, which is the point."""
    assert set(guard.ALLOWED) <= ALLOWED_AT_MOST, sorted(set(guard.ALLOWED) - ALLOWED_AT_MOST)
    assert set(guard.EXCLUDED) <= EXCLUDED_AT_MOST, sorted(set(guard.EXCLUDED) - EXCLUDED_AT_MOST)
    tracked = set(guard.tracked_markdown(REPO))
    for key, reason in guard.ALLOWED.items():
        assert len(reason) > 40, key
        assert key in tracked, f"{key} is on ALLOWED but is not a tracked Markdown file"
        assert guard.hits_in((REPO / key).read_text(encoding="utf-8")), (
            f"{key} no longer contains a placeholder DOI; remove its allowance"
        )
    for key, reason in guard.EXCLUDED.items():
        assert key.endswith("/") and len(reason) > 40, key
        assert (REPO / key).is_dir(), key
