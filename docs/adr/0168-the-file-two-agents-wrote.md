# ADR 0168: The file two agents wrote, and the draft one of them destroyed

**Status:** Accepted

**Date:** 2026-08-29

## Context

ADR 0150's index row claims unit declarations took the exported SBML's
libSBML consistency findings from 15 to 0; ADRs 0165–0167 established the
row was written and the work was not. This session set out to build it —
and so, unknown to me, had another agent, in the same worktree, with no
claim system to arbitrate (the worktree brief's `make claim` targets do
not exist; ADR 0165's report noted exactly that and called the
consequence "could-not-determine, not all-clear").

**What I did wrong, stated first because it is the unrecoverable part.**
The other author had an uncommitted draft of `caterva/core/sbml_units.py`.
I wrote mine over it with an unchecked `cat >`. The file was untracked,
so no git object ever existed: their draft is gone, not recovered. The
owner's protective commit message had even flagged the in-flight work
("caterva/core/sbml_units.py + unstaged exporter edits, neither included")
— evidence on the shelf that I did not read before writing. Rule: an
untracked file you did not create is somebody's only copy.

**Then the boundary thrashed.** Each of us, finding the pair broken,
conformed our half to the other's just-replaced half — three times, in
opposite directions, including once more by me *after* the other author
had ceded the module API to my design. For the duration of each cycle,
every units-bearing export raised `TypeError`: a broken tree produced by
two agents each acting reasonably on a stale read.

**How it settled.** The other author used the only channel there is —
the filesystem — leaving `docs/COORDINATION-sbml-units.txt`: a claim on
the exporter and CLI paths, an explicit cession ("your module is the
better half and I am keeping it verbatim"), and a request to answer in
the file. Nine hours later I read it, restored the module to the settled
signature, answered in the file, and stopped editing their paths.

**One defect found and fixed after settlement.** The exporter's
unit-agreement pre-check looked up `vmax` in a `Vmax`-keyed table, so a
rate row's `mM/s` was read as a concentration voice and every
rate-bearing export refused as self-disagreeing — the third occurrence of
the same case-fold defect at this one boundary (`annotate_sbml` and
`declare_units` each carry the fold already). We fixed it independently
within a minute of each other; theirs landed, mine aborted safely on an
anchor mismatch, and their fix is the one in the tree.

## Decision

- The module signature is frozen as settled: `declare_units(sbml_text,
  parameter_units, *, domain)` returning itemised `refusals`. The
  docstring names the three files that must move together if it ever
  changes.
- The exporter, its `units:` payload handling and the seconds-only time
  base are the other author's; this session does not edit them again.
- The coordination file protocol — claim by path, answer in the file,
  delete as ack — is recorded here as the working substitute for the
  absent `make claim`, so the next collision starts from a protocol
  instead of a thrash.

## Verification

On the settled pair, all measured this morning:

| check | result |
|---|---|
| the other author's `test_sbml_units_declared.py` | **7/7** |
| mm export, `LIBSBML_CAT_UNITS_CONSISTENCY` | **15 → 0** |
| engine suite (`caterva`) | all pass |
| root jest `cliEndToEnd` (COMBINE archive, exports) | 32/32 |
| root `type-check` (my `ExportProvenance.unit` change) | clean |

One jest flake observed under load — `refuses to run, rather than
defaulting` failed at 429s in a full run while both agents' processes
shared the machine, then passed in 3.9s in isolation and in a clean full
re-run. Recorded as contention, not defect, and not papered over with a
raised timeout.

No mutation table in this record: the units tests are the other author's,
and their set file is theirs to write (agreed in the channel). What I
verified by hand is listed above and re-runnable as written.

## Consequences

- ADR 0150's *subject* is now true in the tree; its missing document, and
  0146's, remain the other author's per the channel agreement, and the
  two doc-link/Rule-8 reds stay red until those documents exist.
- The destroyed draft is a real loss and stays lost. Its surviving ideas
  — the time-base refusal, the payload `units:` reading, UNIT_KINDS-style
  explicitness — are in the exporter and credited in the module docstring.
- **Not checked:** whether the settled pair behaves under the live CLI's
  full `report --fixture` path end-to-end (only the exporter and jest e2e
  paths were driven); and sir/seir units remain deliberately refused, the
  gap named in the module rather than filled.
