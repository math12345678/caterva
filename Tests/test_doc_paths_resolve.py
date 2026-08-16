"""Paths in the docs a newcomer reads must point at real files.

Wraps `scripts/check_doc_paths_resolve.py` so something runs it unasked,
and — more importantly — exercises its failing branch. The guard passes
today because the two defects it was written against are fixed. A guard
whose failure path is never run is a guard nobody has checked.
"""
from __future__ import annotations

import pathlib
import sys

_SCRIPTS_DIR = pathlib.Path(__file__).resolve().parents[1] / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from check_doc_paths_resolve import (  # noqa: E402
    DOCS,
    KNOWN_ABSENT,
    ROOT,
    extract,
    main,
    unresolved,
)


def test_every_documented_path_resolves() -> None:
    assert main() == 0, (
        "a contributor-facing document names a file that does not exist. Run "
        "`python scripts/check_doc_paths_resolve.py` for the list."
    )


def test_it_reports_a_path_that_does_not_exist() -> None:
    """The real defect, replayed.

    `Tests/test_brenda_flags.py` is the exact wrong path that was written
    into CONTRIBUTING.md while fixing other wrong paths. It is plausible
    and it is not there.
    """
    bad = unresolved("x.md", "see `Tests/test_brenda_flags.py` for it", set())
    assert bad == ["Tests/test_brenda_flags.py"]


def test_it_accepts_a_path_that_does_exist() -> None:
    """Crying wolf is how a guard gets ignored."""
    real = "see `Terium/tests/test_brenda_integration.py` for it"
    assert unresolved("x.md", real, {"Terium/tests/test_brenda_integration.py"}) == []
    # ...and via the filesystem, not just the tracked-file set, since new
    # files are untracked until they are added.
    assert unresolved("x.md", real, set()) == []


def test_bare_filenames_are_left_alone() -> None:
    """Deliberate scope limit, pinned so it is not narrowed by accident.

    These documents name `terium_engine.py` conversationally. Requiring a
    directory there would fail on prose and teach people to stop naming
    files.
    """
    assert extract("`terium_engine.py` and `brenda_client.py`") == set()
    assert extract("`Terium/terium_engine.py`") == {"Terium/terium_engine.py"}


def test_it_finds_paths_in_prose_and_in_lists() -> None:
    text = "Read `docs/adr/0012-a.md`.\n\n- then `scripts/doctor.py`\n"
    assert extract(text) == {"docs/adr/0012-a.md", "scripts/doctor.py"}


def test_every_listed_document_exists() -> None:
    """DOCS naming a file that is gone means silent loss of coverage."""
    for doc in DOCS:
        assert (ROOT / doc).exists(), (
            f"{doc} is in DOCS but not in the repository. Update the list "
            "rather than letting the guard check nine files while naming ten."
        )


def test_known_absent_entries_carry_a_reason() -> None:
    for ref, reason in KNOWN_ABSENT.items():
        assert reason and len(reason) > 20, (
            f"KNOWN_ABSENT[{ref!r}] has no explanation. An exemption without "
            "a reason is a broken link with paperwork."
        )
