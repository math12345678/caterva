# ADR 0074: A journal that crossed sandboxes

**Status:** Accepted, implemented

**Date:** 2026-08-15

**Context:** `scripts/mutate.py`

**Follows:** [ADR 0069](0069-the-harness-that-lied.md), which added the
journal, and [ADR 0072](0072-evidence-that-can-be-re-derived.md), which wired
`mutate.py --selftest` into `verify_build.py`.

## The defect

The first time `mutate.py` was run in a fresh session it died before doing
any work:

```
PermissionError: [Errno 13] Permission denied:
  '/sessions/stoic-sweet-euler/tmp/tmp5r6_29kj/subject.txt'
```

`stoic-sweet-euler` is **another agent's sandbox**. The journal in
`.mutate-journal/` named a temporary file belonging to a different process,
in a directory this process cannot stat.

The chain that produced it is entirely self-inflicted, across two passes:

1. ADR 0069 added the journal so a run killed mid-mutation could be repaired
   by the next run.
2. `--selftest` mutates files inside a `TemporaryDirectory`, and the journal
   was opened for those too.
3. ADR 0072 wired `--selftest` into `verify_build.py`.
4. So **every agent running the build** wrote a journal naming a temp path
   under their own sandbox, and the next agent to invoke `mutate.py`
   inherited it and crashed.

A repository this project's own documentation describes as having several
agents working in it at once, and the tool assumed one machine and one
process.

### Why the earlier fix did not cover it

A concurrent agent had already hardened `recover_journal` against the
adjacent case — the target's directory being *gone*, which is what happens
when a `TemporaryDirectory` is cleaned up in the same sandbox. Their guard
is `if not target.parent.is_dir()`.

That handles "gone". It does not handle **"unreadable"**: `is_dir()` itself
raises `PermissionError` on a path in another sandbox, so the check meant to
prevent the crash was the line that crashed.

Two agents fixing the same function from different symptoms, each covering
the case they had seen. Worth recording because it is an argument for
guarding the whole recovery block rather than enumerating failure modes:
recovery runs before any real work, so *anything* it cannot do must degrade
to a message, never to a traceback.

## The second defect, which had not fired yet

The journal is a single shared path in a repository multiple agents write
to. Two `mutate.py` runs at once would clobber each other's journal, and a
recovery could restore a file that a **live** run was mid-way through
mutating — corrupting its result and leaving the tree in a state neither
process expects.

Nothing had hit this. It was found by asking what else follows from
"several agents, one shared path", having just been bitten by the first
consequence of that sentence.

## Decision

1. **Journals are only written for files inside the repository.**
   `--selftest` mutates temp files, which need no protection: if the process
   dies the directory dies with it. This removes the cause rather than
   handling the symptom, and means the build no longer scatters journals
   across sandboxes.

2. **Every step of recovery is guarded.** Reading the record, stating the
   target, hashing it and restoring it are each wrapped; any `OSError`,
   malformed JSON or missing key produces a `NOTE:` and clears the journal.
   Recovery that cannot fail safely turns a stale record into a permanently
   unusable tool.

3. **A journal naming a path outside the repository is discarded** with an
   explanation, rather than treated as something to repair.

4. **The journal records the writing process's PID.** If that process is
   still alive, the run **refuses** (exit 3) rather than clobbering a
   concurrent run. `pid_is_alive` treats `PermissionError` from `kill(pid, 0)`
   as alive — the process exists and belongs to someone else, which is
   precisely when not to interfere.

## Verification

Replayed against the exact journal that caused the crash:

```
NOTE: discarding a mutation journal for
      /sessions/stoic-sweet-euler/tmp/tmp5r6_29kj/subject.txt, which is
      outside this repository (another sandbox's temporary file).
...
OK: the harness reports INDETERMINATE where it cannot establish a verdict.
exit=0
```

And a synthetic journal naming a live PID against a real repository file:

```
REFUSING: a mutation run (pid 17) appears to be in progress
exit=3
```

`--selftest` now leaves no journal behind at all, confirmed by inspecting
`.mutate-journal/` after a run.

## Consequences

- The failure was silent for exactly one pass and then hit an unrelated
  agent. A tool that writes shared state has to assume concurrency in this
  repository; the assumption should be explicit in anything else that does.
- `.mutate-journal/` is gitignored, so this state was invisible to review.
  That is correct for the content and a reason the defect was easy to miss.

## What this cost, and what it bought

The crash landed while re-deriving ADR 0029's table — Jeske's variant
finding — and delayed it by one detour. Both of that table's mutations then
came back `caught`, including the one originally recorded as **not** caught
and closed by an added test. Three tables re-derived so far (0029, 0060,
0065); all three match what was recorded by hand.

## Related

- [ADR 0069](0069-the-harness-that-lied.md) — the journal, and the SIGKILL
  case it was built for
- [ADR 0072](0072-evidence-that-can-be-re-derived.md) — the wiring that
  turned a local quirk into everyone's crash
