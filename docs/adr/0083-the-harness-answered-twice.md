# ADR 0083: The harness answered twice

**Status:** Accepted, implemented — with one claim explicitly unverified

**Date:** 2026-08-15

**Context:** `scripts/mutate.py`

**Follows:** [ADR 0069](0069-the-harness-that-lied.md), which built this
harness because the hand-run one had given a wrong answer three ways.

## The defect

Running ADR 0056's set, mutation J3 reported:

```
NOT CAUGHT -- J3: `finalValue` read from the flat path only
  all 27 tests passed with the mutation applied.
```

ADR 0056 claims 2 failures. A disagreement — the first in thirty verdicts,
and exactly what this whole exercise was looking for.

It was not a disagreement. Applying J3 by hand fails 2 tests. Running the
set file's own command through `subprocess` fails 2 tests. Re-running the
identical harness invocation minutes later:

```
J3: `finalValue` read from the flat path only ... caught
```

**Same set file, same mutation, same tree, two different verdicts.**

A harness that answers differently on two runs is worse than no harness. A
false NOT CAUGHT reads as a real gap in the tests, and would have been
written up as one — here, as a claim that ADR 0056's record was wrong. That
is the failure class ADR 0069 exists to remove, reappearing inside the tool
written to remove it.

## What it looks like, and the fix

The runs that disagreed were the **third rapid mutation of one file within a
few seconds** (J1, J2, J3 in succession, each writing and restoring
`csv-exporter.ts`).

Test runners cache transformed modules. A cache keyed on `(path, mtime)`
rather than on content will serve the pre-mutation transform when two writes
land inside one mtime tick. The suite then runs **unmutated source**, passes,
and that is indistinguishable from a mutation nothing catches.

`apply_one` now pushes the mutated file's mtime ten seconds forward. It is
cheap, needs no knowledge of which runner is in use, and makes a stale cache
entry impossible rather than unlikely.

### What is established, and what is not

The question splits in two, and only one half is answerable here.

**Half one — the harness's own logic — is deterministic.** Write, run, read
the verdict, restore: five consecutive runs of one mutation against a pytest
suite, five `caught`. pytest costs ~5s per invocation, so repetition is
cheap.

```
... caught   ... caught   ... caught   ... caught   ... caught
```

**Half two — a JavaScript runner's transform cache — is not tested, and
cannot be here.** A single jest invocation of the eight-test file this
defect appeared in costs **70.7 seconds**, measured. Baseline plus mutation
is 141s against a 178s per-call ceiling, which leaves no room for a second
repetition; and running the repetitions in separate calls destroys the rapid
succession that produced the disagreement in the first place.

So the mtime fix remains **reasoned, not demonstrated**, for the case it was
written for. It is cheap, cannot make anything worse, and addresses a
mechanism that fits the evidence — but "fits the evidence" is not the same
as "shown", and recording it as fixed would be the same shape as the defect:
a verdict the harness had not established.

The exact command and what to look for are in
`docs/mutations/NOT-YET-REPRODUCIBLE.txt`, for an environment without the
ceiling.

## Why the earlier results still stand

The failure mode is **asymmetric**, and this is the load-bearing argument.

A stale cache makes the runner execute **unmutated** source. Against a
baseline the harness has already required to be green, unmutated source
**passes**. So the artifact can only ever manufacture a **NOT CAUGHT**.

It cannot manufacture a CAUGHT: a `caught` verdict means tests actually
failed, and unmutated source on a green baseline does not fail.

Of the roughly thirty verdicts produced across the re-derivation passes,
twenty-nine were `caught` and are therefore unaffected. Exactly one reported
NOT CAUGHT — J3 — and it was the artifact, found because a single
disagreement was investigated rather than believed.

That is a narrower claim than "the results are fine", and it is the one the
evidence supports.

## The near-miss worth keeping

The instinct on seeing NOT CAUGHT was that ADR 0056's table was wrong. It
would have been written up that way — a record corrected, a "finding"
announced, and the real defect (in the harness) left in place and now
harder to see, because the anomaly it produced had been explained away as
somebody else's error.

What stopped it was the rule from ADR 0026's own near-miss: **check the spec
before doubting the record.** That check ran three ways — by hand, by
subprocess, and by re-running the harness — and the third one disagreed with
the first harness run, which is what exposed the non-determinism.

A disagreement between the tool and the record is evidence about *one of
them*, and which one is not known until it has been reproduced.

## Consequences

- Mutation verdicts are now expected to be stable across runs. Any future
  NOT CAUGHT should be re-run before it is believed, and this ADR is the
  reason.
- The triple-run confirmation is outstanding, recorded in
  `docs/mutations/NOT-YET-REPRODUCIBLE.txt` alongside the table debt so it
  is not lost.
- Two runs were killed by the per-call ceiling during this pass. Both left
  the tree mutated and **both were recovered from the journal** —
  ADR 0074's mechanism working twice under real conditions rather than in a
  synthetic test.

## Related

- [ADR 0069](0069-the-harness-that-lied.md) — the three original failure
  modes; this is a fourth
- [ADR 0074](0074-a-journal-that-crossed-sandboxes.md) — the journal that
  recovered the tree twice this pass
- [ADR 0026](0026-cross-parameter-assay-coherence.md) — the near-miss whose
  rule prevented a false accusation here
