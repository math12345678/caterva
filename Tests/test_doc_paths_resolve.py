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

import re  # noqa: E402

import check_doc_paths_resolve as guard  # noqa: E402
from check_doc_paths_resolve import (  # noqa: E402
    DOCS,
    HANDOFF,
    KNOWN_ABSENT,
    ROOT,
    classify,
    extract,
    handoff_is_live,
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


def test_a_repository_slug_is_not_read_as_a_missing_file() -> None:
    """The defect that took this guard down, replayed verbatim.

    `START_HERE.md` explains the clone-URL disagreement by quoting three
    repository slugs. Each has one slash and a short suffix, so the path
    regex matched all three and the guard reported three missing files —
    turning a documentation fix into a red `make guards` for every
    contributor.
    """
    text = (
        "This said `Terrium-sim/main.git` while README said "
        "`Terrium-sim/terrium.git`, and origin says `math12345678/terrium.git`."
    )
    here, remote = classify(text)
    assert here == set(), f"a clone URL is being treated as a repo path: {here}"
    assert len(remote) == 3
    assert unresolved("START_HERE.md", text, set()) == []


def test_a_real_missing_path_still_fails_alongside_them() -> None:
    """The exemption must be narrow, not a hole the width of the check.

    Same sentence, one genuine broken path added. If the `.git` handling
    were implemented as "give up on this document" rather than "classify
    this token", this is where that would show.
    """
    text = "clone `Terrium-sim/terrium.git`, then read `Tests/test_nope.py`"
    assert unresolved("x.md", text, set()) == ["Tests/test_nope.py"]


def test_delegating_everything_trips_the_floor(monkeypatch) -> None:
    """The vacuity attack, and the reason the floor moved.

    A classifier that routes every token to "somebody else checks this"
    verifies nothing. The first version of the floor counted tokens *seen*,
    so 61 tokens cleared a floor of 20 while zero were checked — a check
    that cannot fail, which is worse than no check because it is trusted.

    The floor now counts tokens verified, so this returns 1.
    """
    monkeypatch.setattr(guard, "_REMOTE_RE", re.compile(r""))
    assert main() == 1, (
        "every path reference was delegated as a remote repository and the "
        "guard still reported success. The floor is counting tokens found "
        "rather than tokens checked."
    )


def test_the_handoff_is_verified_rather_than_assumed() -> None:
    """`.git` tokens are handed off, not waved through.

    The distinction is only real while the delegate is doing the work, so
    the guard checks that it is.
    """
    assert handoff_is_live() is None, (
        f"{HANDOFF} no longer checks clone URLs, so nothing does"
    )
    assert (ROOT / HANDOFF).exists()


def test_a_dead_handoff_fails_the_guard(monkeypatch) -> None:
    """The failing branch, run rather than described."""
    monkeypatch.setattr(guard, "HANDOFF", "Tests/test_no_such_delegate.py")
    assert guard.handoff_is_live() is not None
    assert main() == 1, (
        "the delegate is gone and the guard still exempted the clone URLs"
    )


def _delegate(monkeypatch, tmp_path, body: str) -> str | None:
    """Point the handoff at a stub file with `body` in it."""
    stub = tmp_path / "delegate.py"
    stub.write_text(body, encoding="utf-8")
    monkeypatch.setattr(guard, "ROOT", tmp_path)
    monkeypatch.setattr(guard, "HANDOFF", "delegate.py")
    return guard.handoff_is_live()


def test_each_condition_on_the_delegate_can_fail_on_its_own(
    monkeypatch, tmp_path
) -> None:
    """All three conditions, separately.

    Written because one of them was not being checked. The mutation that
    deletes the `.git` condition from `handoff_is_live` passed the whole
    suite: `test_a_dead_handoff_fails_the_guard` exercises the
    file-is-missing branch, and nothing reached the other two. Three
    conditions and one test between them is how a branch survives being
    deleted.

    A delegate that reads `git clone` but never matches `.git` is not
    hypothetical — that is precisely what removing `\\.git` from the
    delegate's own regex would produce, and the URLs would go unchecked
    while this guard kept exempting them.
    """
    present = "_CLONE_RE = re.compile(r'git clone .*\\.git')"
    assert _delegate(monkeypatch, tmp_path, present) is None

    no_clone = "_CLONE_RE = re.compile(r'fetch .*\\.git')"
    assert "no longer reads clone commands" in (
        _delegate(monkeypatch, tmp_path, no_clone) or ""
    )

    no_git = "_CLONE_RE = re.compile(r'git clone \\S+')"
    assert "no longer matches" in (_delegate(monkeypatch, tmp_path, no_git) or "")


def test_known_absent_entries_carry_a_reason() -> None:
    for ref, reason in KNOWN_ABSENT.items():
        assert reason and len(reason) > 20, (
            f"KNOWN_ABSENT[{ref!r}] has no explanation. An exemption without "
            "a reason is a broken link with paperwork."
        )
