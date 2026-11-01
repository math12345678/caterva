"""The archive's own counts must match the archive.

WHY THIS EXISTS
---------------
ADR 0091 moved 57 documents out of the repository root and closed with:

    No guard covers those two numbers; if the archive grows again, they
    will need updating by hand.

That sentence named an unchecked number and left it. One pass later
`docs/archive/README.md` still opened with "53 documents" — the figure from
the first batch, before four more moved. The number went stale in the time
it took to write the ADR saying it might.

This is the smallest possible fix: read the directory, read the prose,
require agreement. It is the same shape as
`test_the_register_prose_matches_the_register`, which has now caught the
image register's prose going stale three separate times.

WHY IT LIVES HERE RATHER THAN IN check_documented_counts.py
-----------------------------------------------------------
That guard is another agent's and is heavily edited. Adding two more claims
to it means editing a file somebody else is working in, to check a fact
that belongs to a document neither of us owns. A separate test is cheaper
to read and cannot break their guard.
"""
from __future__ import annotations

import pathlib
import re
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "docs" / "archive"
ARCHIVE_README = ARCHIVE / "README.md"
INDEX = ROOT / "DOCUMENTATION_INDEX.md"


def archived_count() -> int:
    """Documents in the archive, not counting the archive's own README."""
    return len([p for p in ARCHIVE.glob("*.md") if p.name != "README.md"])


def root_count() -> int:
    """Markdown files at the root that are actually part of the repository.

    `ROOT.glob("*.md")` was one too many. It counted
    `.aider.chat.history.md` — a local tool's scratch file, listed in
    `.gitignore` and untracked, which no clone has ever contained. Nobody
    noticed because nothing compared this number to a document; the first
    thing that did failed instantly, saying 41 against 42.

    That is worth more than the one-off fix. The historical figures in the
    prose (98 before the triage, 41 after) came from a shell glob, which
    skips dotfiles. So this function and every number it was going to be
    checked against had been measuring different sets from the beginning,
    and the disagreement was invisible for exactly as long as the
    comparison was missing.

    Git decides, rather than a rule about leading dots: a file is in the
    repository if it is tracked, or untracked and not ignored. That covers
    documents added this session, which are not yet committed but are
    certainly here.
    """
    out = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "--", "*.md"],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )
    if out.returncode != 0:
        # No git, or not a repository. Fall back to the glob minus dotfiles
        # rather than returning a number from a failed command.
        return len([p for p in ROOT.glob("*.md") if not p.name.startswith(".")])
    return len({line for line in out.stdout.split() if "/" not in line})


def test_the_archive_readme_states_the_right_number() -> None:
    """The opening line is the one a reader trusts, so it must be true."""
    n = archived_count()
    text = ARCHIVE_README.read_text(encoding="utf-8")
    assert f"{n} documents, moved out of the repository root" in text, (
        f"docs/archive/ holds {n} documents (excluding its own README) but "
        f"docs/archive/README.md does not open by saying so. It said 53 for a "
        "full pass after the number became 57."
    )


def test_the_index_states_the_right_numbers() -> None:
    """`DOCUMENTATION_INDEX.md` is where a newcomer is sent."""
    # `root_count()` was computed here and never compared to anything — the
    # residue of the defect `test_the_live_root_count_in_the_opening_sentence_is_right`
    # was written to fix, and its docstring says so in as many words. Left
    # behind, it reads as an intention this test has and does not carry out.
    archived = archived_count()
    text = INDEX.read_text(encoding="utf-8")

    assert re.search(rf"\b{archived} files, with `git mv`", text), (
        f"{archived} files are archived; DOCUMENTATION_INDEX.md does not say so"
    )
    # The archive count is a live fact about a directory and is asserted.
    # "The root went from 98 to 41" is NOT: it is a dated statement about
    # what the move achieved, and the root moves every time an agent adds a
    # document. This test failed on its first real run because the root had
    # already gone 41 -> 42 while the ADR was being written.
    #
    # Pinning a historical claim to a live count would make the test fail
    # for a reason that is not a defect -- the same confusion between a
    # dated number and a current one that check_investor_claims.py exists
    # to draw. The trend is checked instead, by
    # test_the_root_has_actually_been_reduced.
    assert re.search(r"markdown files to \d+ as of \d{4}-\d{2}-\d{2}", text), (
        "DOCUMENTATION_INDEX.md states what the root count became without "
        "dating it. An undated number reads as current and this one is not."
    )


def test_the_live_root_count_in_the_opening_sentence_is_right() -> None:
    """The first number a newcomer reads, in the present tense.

    `DOCUMENTATION_INDEX.md` opened with "The repository root holds 81
    markdown files" for a pass after the archive move made it 41 — off by
    a factor of two, in the first line of the file the index sends people
    to, while this module computed `root_count()` on the line above and
    declined to compare it to anything.

    The comment in `test_the_index_states_the_right_numbers` draws exactly
    the right distinction and then applies it to only one of the two
    numbers. "The root went from 98 to 41 as of 2026-08-16" is dated and
    ages honestly. "The root **holds** 81" is a live claim and simply
    became false. Both were in the same file; only the dated one was
    guarded.

    So the tense is the test. `holds N` is pinned to the directory; a
    sentence carrying a date is left alone.
    """
    n = root_count()
    text = INDEX.read_text(encoding="utf-8")

    m = re.search(r"root holds (\d+) markdown files", text)
    assert m is not None, (
        "DOCUMENTATION_INDEX.md no longer opens with a present-tense root "
        "count. If that sentence was rewritten, this test needs to follow "
        "it — silently checking a sentence that is gone is how the 81 "
        "survived in the first place."
    )
    assert int(m.group(1)) == n, (
        f"DOCUMENTATION_INDEX.md says the root holds {m.group(1)} markdown "
        f"files; it holds {n}. Either update the sentence, or write it as a "
        "dated statement ('… as of YYYY-MM-DD') so it ages honestly instead "
        "of becoming false."
    )


def test_the_dated_and_live_claims_are_both_present() -> None:
    """One of each, so neither style can quietly replace the other.

    Rewriting the live sentence as a dated one would satisfy the test above
    by deleting what it checks. Rewriting the dated one as live would put a
    number that moves every time an agent adds a document into a sentence
    about a finished migration.
    """
    text = INDEX.read_text(encoding="utf-8")
    assert re.search(r"root holds \d+ markdown files", text), (
        "the live root count is gone from DOCUMENTATION_INDEX.md"
    )
    assert re.search(r"markdown files to \d+ as of \d{4}-\d{2}-\d{2}", text), (
        "the dated statement about what the archive move achieved is gone"
    )


def test_the_archive_is_not_empty() -> None:
    """A floor, so a broken glob cannot report agreement with nothing.

    If `ARCHIVE.glob` ever returned nothing, both tests above would compare
    "0" against prose that says "0" only if somebody had also edited the
    prose to say it — which is exactly the coincidence a floor exists to
    rule out.
    """
    assert archived_count() > 40, (
        f"only {archived_count()} archived documents found; the triage moved "
        "57, so either a large deletion happened or the scan is broken"
    )


def test_the_root_has_actually_been_reduced() -> None:
    """The point of the move, asserted rather than assumed.

    The root held 98 markdown files before the triage was executed. If it
    climbs back, the archive was a one-off tidy rather than a change in
    habit, and this is where that shows up.
    """
    n = root_count()
    assert n < 60, (
        f"the repository root is back to {n} markdown files. It was 98 before "
        "the triage and 41 after. New documents belong in docs/ unless a "
        "newcomer needs them in the first place they look."
    )
