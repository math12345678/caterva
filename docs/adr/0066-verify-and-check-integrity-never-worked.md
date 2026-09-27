# ADR 0066: `verify` and `check-integrity` never worked, and `verify` called failure success

**Status:** Accepted, implemented

**Date:** 2026-08-15

**Relates to:** ADR 0059 and 0049 (the previous two defects found by running
the product), ADR 0039/0040/0041 (values computed and dropped at a boundary —
`differences` is another)

## Two defects, and the second is the serious one

### 1. Both commands were structurally incapable of succeeding

`ReproducibilityService.records` was a bare in-memory `Map`. The CLI is a
fresh process per invocation, so:

```
$ scientific history          # lists job_1786801904853_05dxr6m4f
$ scientific verify job_1786801904853_05dxr6m4f
✗ Verification failed: Record not found for job job_1786801904853_05dxr6m4f
```

The Map was constructed empty microseconds earlier. **Every job id, always,
since the commands existed.**

Both are advertised in `help`. A completed simulation prints *"Saved. Re-check
it later with: `scientific check-integrity <jobId>`"* — a promise the tool
could not keep. And `history` persists to `~/.caterva/history.json`, its help
text reading: *"The run id printed at the end of a simulation is only useful
if something can resolve it later; this is that something."*

So the tool printed an id, listed it, and denied it existed. The two stores
never agreed because only one of them was a store.

**No unit test could have caught this.** A test that calls `recordExecution`
and then `checkIntegrity` on one service instance passes — the Map is
populated. The defect exists only *across* processes, which is the only way a
user ever meets it.

### 2. `verify` reported a failed verification as success

```ts
if (result.reproduced) success('FULLY REPRODUCIBLE');
else warning('NUMERICALLY EQUIVALENT (within floating-point precision)');
...
process.exit(0);
```

`reproduced` is `verification.passed`, which **already accounts for the
solver's declared tolerance**. So the `else` was the failure branch, and it
announced failure as agreement within floating-point precision, then exited
`0`.

Measured, by perturbing one recorded trajectory point:

```
⚠ NUMERICALLY EQUIVALENT (within floating-point precision)
Max relative error: 3.33e-1
Summary: ✗ NOT REPRODUCIBLE (max relative error: 3.33e-1 exceeds the solver's
         declared tolerance (atol 1.00e-8, rtol 1.00e-6))
EXIT=0
```

A 33% divergence, described as floating-point noise, two lines above the
engine's own verdict contradicting it — and a success exit code, so a script
checking `$?` saw a pass. The engine was right the entire time. The reporting
layer inverted it.

This is worse than a check that cannot fail: the check *did* fail, correctly,
and the interface converted the failure into reassurance.

## Decision

### Records persist

`recordExecution` writes to `~/.caterva/records/<jobId>.json`; lookups check
the Map, then disk. Failure to persist never throws — a simulation that
produced a correct result did produce it, and an unwritable home directory
must not make the exit code mean two things. The consequence is logged.

A damaged record is not a missing one. An unreadable file raises *"this is a
damaged record, not a missing one"* rather than "no such job", which would
send someone looking for a run they know they performed. Same
could-not-look / found-nothing distinction the rest of the tool keeps.

`addPhase` deliberately still consults the Map only: a phase is appended to a
run in flight, and reviving a finished record from disk to mutate a copy that
is never written back is the silent-discard pattern this repository has spent
several passes removing.

### `verify` reports three outcomes with three exit codes

| | |
|---|---|
| `outputsIdentical` | **FULLY REPRODUCIBLE** — bit-for-bit. Exit 0 |
| `passed && !identical` | **REPRODUCIBLE** — within the solver's declared tolerance. Exit 0 |
| `!passed` | **NOT REPRODUCIBLE**. Exit 2 |
| threw | could not be performed. Exit 1 |

The middle state is real and common for floating point — summation order is
not guaranteed across runs. The phrase "numerically equivalent" existed
because that state exists; it was simply attached to the wrong branch.

Exit codes follow `resolve`: 0 answered, 2 a real negative answer, 1 could not
perform the check.

### `differences` reaches the user

`ReproductionAttempt.differences` — the verifier's `possibleCauses` and
`conclusion` — was computed and dropped at the pipeline boundary, so a failing
verification had nothing to say about why. It is now returned and printed:

```
Possible causes:
  • Unseeded randomness in the model or solver
  • Adaptive step sizing not pinned by the recorded solver settings
  • A parameter read from live state rather than the recorded inputs
  • Genuine non-determinism in the simulation code

Results DIFFER: max relative error 3.33e-1 exceeds the solver's declared
tolerance by 3.33e+5x. This is not floating-point noise.
```

That last sentence was being computed while the CLI printed the opposite.

## Consequences

- Both commands work across processes for the first time. Verified by hand:
  run a simulation, then `check-integrity` and `verify` it from separate
  invocations.
- **The integrity check can fail.** Doubling a stored `s0` from 10 to 20 on
  disk, leaving the hash untouched, produces `DATA CORRUPTION DETECTED —
  Input data corrupted - hash mismatch`, exit 1.
- **The reproducibility check can fail.** Perturbing a recorded trajectory
  point produces `NOT REPRODUCIBLE`, exit 2, with causes. The untampered
  record gives bit-for-bit identical, exit 0.
- `recordsSurviveTheProcess.test.ts` uses a **second service instance** for
  every assertion, standing in for the second process — a test that reuses one
  instance is the test that missed this. Mutation-tested: removing the disk
  lookup fails five of seven, and the two that survive are exactly the two
  that never touch disk.
- The unwritable-home test points `HOME` at a regular file so `mkdirSync`
  fails with ENOTDIR, rather than mocking `fs.writeFileSync` — which would
  have tested that jest can mock `fs`, a fact not in question.
