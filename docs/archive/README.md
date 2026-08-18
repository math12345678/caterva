# Archive

**Nothing here is current. Do not cite a number from these files.**

57 documents, moved out of the repository root on 2026-08-15 and
2026-08-16. They were
classified one by one in `../ARCHIVE_TRIAGE.md`, which records a reason for
each — read that, not this, if you want to know why a particular file is
here.

## Why they moved

The triage was written weeks earlier and executed by nobody. Meanwhile the
root kept growing: 81 markdown files when it was written, **98** by the
time these moved. A newcomer opening the repository saw ninety-eight files
at the top level, nine of which called themselves the "complete" or "final"
description of the system, and no way to tell which one was true.

Moving them is the cheap half of the fix. The other half already happened:
`../../DOCUMENTATION_INDEX.md` is now a short routing table to the
documents that are accurate.

## Why they were kept rather than deleted

Several are worth having precisely because their mistakes are instructive:

- inflated line counts (`COMPLETE_BUILD_REPORT.md` claimed 400+ where the
  real figure was 217, and 12,000 where it was 9,600)
- a test transcript that appears to have been synthesised
  (`FEATURE_SWEEP_COMPLETE.md`)
- three separate documents each claiming to be the final one
- `WIRING_VERIFICATION_REPORT.md`'s "ZERO STRUCTURAL ERRORS", disproved by
  the next two build stages

`git mv` was used throughout, so `git log --follow` still works on every
file.

## What did not move, and why

**One ARCHIVE-classified file stayed at the root.** Four others were held
back for a pass and have since moved; the reason they were held is worth
recording because it was wrong.

`git status` showed them as modified, which was read as "a concurrent agent
is mid-edit — moving the file would turn their next save into a new file at
the old path." That is a real hazard and the wrong diagnosis. **Nothing in
this working tree is ever committed**: 162 tracked files differ from HEAD,
so "modified" is the default state and carries no information about whether
anyone is working on a file.

The signal that did carry information was mtime. Those four were last
written on 2026-08-12 at 22:05–22:20; a file genuinely under active edit
had been written the same afternoon. Four days apart, and the check that
would have shown it took one command.

A proxy measuring the wrong thing is worse than no proxy: it produced a
confident reason to defer, twice.

**`DOCUMENTATION_INDEX.md` stayed deliberately.** The triage classified it
ARCHIVE — correctly, at the time, when it was a 424-line index of a
dispersed document set whose "I'm a new developer, where do I start?"
section pointed at three archived files. It has since been rewritten as the
live routing table. Archiving it now would file the signpost under the
things it points away from.

That exception is recorded rather than silently applied, because a
classification that was right when written and wrong when executed is
exactly the kind of thing a later reader would otherwise assume was an
oversight.
