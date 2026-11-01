"""A task offered to a newcomer must still be open.

WHAT THIS COMES FROM
--------------------
`START_HERE.md` sends a new contributor to `docs/FIRST_TASKS.md` with a
specific promise:

    Every entry there is a real open gap with a file to open, a command
    that shows it failing, and a way to know when you are done. None of
    them are made-up exercises.

On 2026-08-16 that promise was false for the entry it calls **"the
highest-value task on the list."** Task 3 said *"Nothing renders the
conditions a simulation ran at"* and gave a grep to prove it. The dashboard
by then had a `runConditionsCard`, a `runConditions` panel, and render
logic. Somebody had done half the task and the list did not know.

Task 5 had a second problem: it named `selectionTie` as one of three fields
`src/literature/literatureResolver.ts` returns and the dashboard drops. That
field is not in `src/literature/` at all — it is on the Python/api-server
path. A reader would grep for it and find nothing, with no way to tell
whether they had misunderstood or the document had.

**A stale task list is a worse failure than no task list.** Someone with no
context spends their first day on finished work, and the conclusion they
draw is not "this entry is out of date" — it is "the documentation here
cannot be trusted", which is expensive and hard to reverse.

WHAT THIS CHECKS
----------------
Each entry in `_TASKS` names a symptom that must still hold. The checks are
the same greps the document tells the reader to run, so the test and the
instructions cannot disagree: if the code changes, this fails, and whoever
closed the gap updates the entry.

WHAT IT DOES NOT CHECK
----------------------
Whether the task is *worth doing*, or whether the prose describing it is
accurate beyond the symptom. A person judges that. This catches the
mechanical half — the half that goes stale silently while nobody is
looking.
"""
from __future__ import annotations

import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
FIRST_TASKS = ROOT / "docs" / "FIRST_TASKS.md"


def _count(rel: str, needle: str) -> int:
    path = ROOT / rel
    if not path.exists():
        return -1
    return path.read_text(encoding="utf-8", errors="replace").count(needle)


def test_the_task_list_exists_and_start_here_points_at_it() -> None:
    """The promise and the file it refers to must both be there."""
    assert FIRST_TASKS.exists(), "docs/FIRST_TASKS.md is gone; START_HERE.md sends people to it"
    start_here = (ROOT / "START_HERE.md").read_text(encoding="utf-8")
    assert "FIRST_TASKS.md" in start_here, (
        "START_HERE.md no longer routes newcomers to the task list"
    )


def test_task_4_is_still_open() -> None:
    """"The assumption checks that could not be evaluated reach nobody."

    Symptom: `notEvaluated` is produced by the validator and consumed by no
    user-facing surface.
    """
    produced = _count("src/validation/scientificValidator.ts", "notEvaluated")
    assert produced > 0, (
        "the validator no longer produces `notEvaluated`; task 4 describes a "
        "field that no longer exists and needs rewriting or removing"
    )
    rendered = _count("src/web/dashboard.html", "notEvaluated")
    assert rendered == 0, (
        "the dashboard now renders `notEvaluated`. Task 4 is done or partly "
        "done — say so in docs/FIRST_TASKS.md rather than leaving a newcomer "
        "to discover it after they have started."
    )


def test_task_5_is_still_open_for_the_field_it_still_applies_to() -> None:
    """"Three fields the resolver returns and the dashboard drops."

    Two of the three were wrong by 2026-08-16: `assayConditions` now
    reaches the dashboard, and `selectionTie` was never in
    `src/literature/`. `poolFindings` is the live part.
    """
    assert _count("src/literature/literatureResolver.ts", "poolFindings") > 0, (
        "the resolver no longer returns `poolFindings`; task 5 needs rewriting"
    )
    assert _count("src/web/dashboard.html", "poolFindings") == 0, (
        "the dashboard now uses `poolFindings`. That was the remaining third "
        "of task 5 — mark it done in docs/FIRST_TASKS.md."
    )


def test_the_corrections_already_found_are_recorded() -> None:
    """Task 3 and task 5 were found stale. The record must say so.

    Without this, a later edit could tidy the notes away and the list would
    silently claim to be current again.
    """
    text = FIRST_TASKS.read_text(encoding="utf-8")
    assert "DONE, dashboard half" in text, (
        "task 3's half-completed state is no longer recorded in "
        "docs/FIRST_TASKS.md"
    )
    assert "selectionTie" in text and "never there" in text, (
        "the note explaining that `selectionTie` is not in src/literature/ "
        "has been removed; a reader will grep for it and find nothing"
    )


def test_task_3_cli_half_is_the_part_still_open() -> None:
    """The dashboard half is done; the CLI half is what remains.

    This is the assertion that would have caught the original defect, and
    it is written the way round that keeps working: it fails when the
    remaining half is finished, which is the moment the entry needs
    updating again.
    """
    assert _count("src/web/dashboard.html", "runConditions") > 0, (
        "the dashboard no longer renders runConditions — either it regressed "
        "or task 3's note is now wrong"
    )
    cli = _count("src/cli/commandResolve.ts", "runConditions")
    assert cli == 0, (
        "the CLI now handles `runConditions`, so task 3 is fully done. "
        "Remove it from docs/FIRST_TASKS.md — an offered task that is "
        "finished wastes the time of the person least able to spare it."
    )
