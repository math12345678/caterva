"""The "not built" notice must stop being true the day it stops being true.

WHY THIS FILE EXISTS
--------------------
`advanced_analysis/README.md` describes a four-component system. Three of
the four are plans written in the present tense, and the eleven paths in
its *Directory Structure* section do not exist -- checked one by one on
2026-08-23. A notice at the top of that file now says so.

That notice has the failure mode ADR 0145 is about, and 0145's argument is
worth restating because it is not the obvious one: **nothing in this tree
fires when a TRUE sentence stops being true.** Every other guard catches a
claim that was wrong when written. This one is right today and becomes
wrong on the day somebody builds `validation/run_validation_pipeline.py`
-- at which point the README tells a reader that real, working code does
not exist, and the people positioned to notice are the ones who cannot,
because they are the ones who just built it.

That is the same defect as the "Not public yet" notice this repository
carried on a repository that had become public, which sat there until a
guard written for exactly that day went red.

WHAT THIS ASSERTS
-----------------
Both directions, because only checking one is how the notice rots:

  * every path the README calls unbuilt is in fact absent -- otherwise the
    notice is lying in the direction that costs a contributor their work;
  * the notice is still present while they are absent -- otherwise the
    warning has been deleted while its subject is unchanged, and the next
    reader is back to discovering it with `cd architecture`.

THE THIRD STATE
---------------
If the README cannot be read at all, that is neither pass nor fail: it is
"could not check", and it fails loudly rather than passing quietly.
"""

from __future__ import annotations

import pathlib

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent.parent
AA = REPO / "advanced_analysis"
README = AA / "README.md"

#: The paths the README's structure diagram names and the notice calls
#: absent. Listed here rather than parsed out of the fenced diagram: the
#: diagram is drawn with box characters and comment columns, and a matcher
#: for it would be one more thing that can silently stop matching. These
#: eleven were verified absent by hand when the notice was written.
CLAIMED_ABSENT: tuple[str, ...] = (
    "architecture",
    "architecture/architecture_diagram.excalidraw",
    "architecture/architecture_guide.md",
    "performance",
    "performance/performance_analysis.ipynb",
    "performance/requirements.txt",
    "provenance_visualization",
    "provenance_visualization/dashboard.py",
    "validation",
    "validation/validation_analysis.ipynb",
    "validation/run_validation_pipeline.py",
)

#: The sentence that carries the claim. Matched on the substantive words,
#: not on the whole paragraph: a reworded notice that still says the same
#: thing should not fail, and a deleted one must.
NOTICE_MARKER = "do not exist"
NOTICE_HEADLINE = "describes work that has not been built"


def _readme() -> str:
    if not README.exists():
        pytest.fail(
            f"{README.relative_to(REPO)} is missing. This test cannot say "
            "whether the notice is accurate, and 'could not check' is not "
            "a pass. If the directory was removed, remove this test with it."
        )
    return README.read_text(encoding="utf-8")


def test_the_paths_called_unbuilt_are_actually_absent() -> None:
    text = _readme()
    built = [rel for rel in CLAIMED_ABSENT if (AA / rel).exists()]

    assert not built, (
        "advanced_analysis/README.md says these paths do not exist, and "
        f"they now do:\n\n  " + "\n  ".join(built) + "\n\n"
        "This is the good failure. Somebody built part of the system the "
        "README describes, and the notice at the top of that file is now "
        "telling readers their work is not there. Update the notice -- and "
        "the `(planned)` heading on Directory Structure -- to match what "
        "exists, and remove the built paths from CLAIMED_ABSENT here.\n\n"
        "See ADR 0145: nothing else in this tree fires when a true sentence "
        "stops being true."
    )


def test_the_notice_is_still_there_while_it_is_still_true() -> None:
    text = _readme()

    still_absent = [rel for rel in CLAIMED_ABSENT if not (AA / rel).exists()]
    if not still_absent:
        pytest.skip(
            "every claimed-absent path now exists; the other test owns this "
            "case and will fail with the instructions"
        )

    assert NOTICE_MARKER in text and NOTICE_HEADLINE in text, (
        f"{len(still_absent)} of the {len(CLAIMED_ABSENT)} paths the README "
        "describes are still absent, but the notice saying so has been "
        "removed or reworded past recognition.\n\n"
        "Deleting the warning does not build the directories. It returns "
        "the reader to finding out with `cd architecture`, which is the "
        "cost the notice exists to prevent."
    )


def test_the_path_list_is_not_empty() -> None:
    """A list that emptied would make both tests above vacuous.

    `built` would be empty and `still_absent` would be empty, so the first
    passes and the second skips -- a clean run over nothing at all.
    """
    assert len(CLAIMED_ABSENT) >= 10, (
        "CLAIMED_ABSENT has been trimmed below the eleven paths the README "
        "names. If components were built, the failure message in the first "
        "test says to remove them from this list -- but removing all of "
        "them turns this file into a check of nothing."
    )
