# ADR 0091: The root was ninety-eight files deep

**Status:** Accepted

**Date:** 2026-08-16

**Related:** `docs/ARCHIVE_TRIAGE.md`, `docs/archive/README.md`,
`DOCUMENTATION_INDEX.md`

## The gap

`docs/ARCHIVE_TRIAGE.md` read all 81 root markdown files, classified each
by content rather than by filename, and recorded a one-line reason for
every verdict: 14 KEEP, 3 WIRING, 6 MISC, **58 ARCHIVE**.

It was thorough, it was right, and **nobody executed it.** Every one of the
58 stayed at the root.

Meanwhile the root kept growing. 81 files when the triage was written; 98
by the time this ran. A newcomer opening the repository saw ninety-eight
files at the top level, nine of which called themselves the "complete" or
"final" description of the system, and no way to tell which was true.

A classification nobody acts on is a more elaborate version of the problem
it describes.

## Decision

All 57 movable ARCHIVE files are now under `docs/archive/`, moved with
`git mv` so `git log --follow` still works on each. **Root: 98 → 41.**

Nothing was deleted. Several are worth keeping precisely because their
mistakes are instructive — `COMPLETE_BUILD_REPORT.md` claiming 400+ lines
where the real figure was 217, a test transcript that appears synthesised,
`WIRING_VERIFICATION_REPORT.md`'s "ZERO STRUCTURAL ERRORS" disproved by the
next two build stages.

`docs/archive/README.md` opens with **"Nothing here is current. Do not cite
a number from these files"** so the directory cannot be mistaken for a
second documentation set.

### The one exception

`DOCUMENTATION_INDEX.md` was classified ARCHIVE and stays at the root. That
classification was correct when written — a 424-line index of a dispersed
document set, whose "I'm a new developer, where do I start?" section
pointed at three archived files, one describing files that never existed.
It has since been rewritten as the live routing table.

Archiving it now would file the signpost under the things it points away
from. Recorded explicitly, because a classification that was right when
written and wrong when executed is exactly what a later reader would
otherwise assume was an oversight.

## The mistake that delayed this by two passes

The move was offered twice and deferred twice, on the grounds that
concurrent agents had uncommitted edits to some of the files, and moving a
file somebody is mid-save on turns their next write into a new file at the
old path.

That hazard is real. The diagnosis was not. **Nothing in this working tree
is ever committed** — 162 tracked files differ from HEAD — so `git status`
reporting a file as modified says only that it differs from a commit made
days ago. It carries no information about whether anyone is working on it.

mtime carried the information. The four files held back were last written
on 2026-08-12 at 22:05–22:20; a file genuinely under active edit had been
written the same afternoon this ran. Four days apart, and one `stat` would
have shown it.

Two things follow, and the second is the one worth keeping:

1. When the check was finally run, 5 of 58 files were flagged and 53 were
   plainly safe. The risk had been overestimated by an order of magnitude.
2. **A proxy that measures the wrong thing is worse than no proxy.** With
   no signal at all, the move would have been done carefully by hand. With
   a signal that felt authoritative and meant nothing, it produced a
   confident reason to defer — twice, in a repository whose entire premise
   is that unverified claims should not be trusted.

That is the same defect this project keeps finding, turned on the process
rather than the code: an indicator nobody checked, believed because it was
mechanical.

## The closing sentence of this ADR was wrong within a pass

The first version ended:

> No guard covers those two numbers; if the archive grows again, they will
> need updating by hand.

That named an unchecked number and left it. One pass later
`docs/archive/README.md` still opened with **"53 documents"** — the figure
from the first batch, before four more moved. The number went stale in the
time it took to write the sentence predicting it might.

`Tests/test_archive_counts_are_current.py` now pins it, and caught a second
drift on its first real run: the root had gone 41 → 42 because another
agent added a document while this was being written.

That second failure was the test over-reaching rather than a defect, and
the distinction is worth keeping. **"57 files are archived" is a live fact
about a directory** and is asserted against it. **"The root went from 98 to
41" is a dated statement about what the move achieved** — the root moves
whenever anyone adds a document, and pinning history to a live count fails
for a reason that is not a defect.

So the index now dates that sentence, the test requires it to stay dated,
and the trend is checked separately: if the root climbs back above 60, the
archive was a one-off tidy rather than a change in habit, and that is where
it shows up.

This is the same distinction `check_investor_claims.py` draws between a
number carrying "as of this session" and one that does not. It took three
separate encounters — the pitch deck, the MVP timeline, and now this ADR's
own closing paragraph — before it was applied here.
