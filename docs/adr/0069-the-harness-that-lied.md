# ADR 0069: The harness that lied

**Status:** Accepted, implemented

**Date:** 2026-08-15

**Context:** `scripts/mutate.py`, `docs/mutations/`

## Why this matters more than any single finding

Mutation testing is how this project distinguishes a check that works from a
check that cannot fail. Six "checks that cannot fail" have been found that
way, along with the boundary drops of ADR 0039, the crashed sweep point of
ADR 0058, and the model-selection defect of ADR 0060. Roughly every
substantive finding in the last ten passes rests on a mutation result.

**Every one of those mutations was run by hand**, with a shell heredoc that
patched a file, ran a suite, and copied a backup back. That worked, and it
also produced a *wrong answer* in three distinct ways:

1. **The patch never applied.** A search string that spanned a source line
   break, or used four-space indentation against two-space source, matched
   nothing. The suite ran against unmutated source, passed, and the mutation
   was recorded as "not caught" — a false accusation against a test that was
   fine. ADR 0051 and ADR 0056 record two agents hitting this independently
   on the same day.

2. **The suite never ran.** A mutation that made a block unreachable broke
   the build and jest printed `Tests: 0 total`. `0 total` is not `0 failed`:
   a suite that cannot compile has judged nothing. Reading it as "not
   caught" credits the tests with a verdict they never gave (ADR 0065).

3. **The restore silently failed.** `/tmp` was not writable, so every `cp`
   restore did nothing and five mutations accumulated in the tree. The tell
   was a run labelled "RESTORED" reporting 14 failures.

All three have one shape: **the harness reported a result it had not
established.** That is precisely the defect class this codebase spends its
time finding in its own product — a check that cannot fail, a refusal that
cannot say what it refused, an absence rendering as a fact. The instrument
had the disease it was built to diagnose.

A wrong mutation result is worse than no mutation testing, for exactly the
reason stated in the governing rule: *a check that cannot fail is worse than
no check, because it is trusted.* An ADR's mutation table is the evidence a
reader is asked to accept. Three of those tables were partly wrong.

## Decision

`scripts/mutate.py`. Before reporting anything, it establishes:

- the baseline suite is **green** — a mutation judged against a red baseline
  says nothing, because an already-failing test "catches" everything
- the baseline **ran tests** (a nonzero count)
- the search string occurs **exactly once** — zero is a no-op, many is
  ambiguous
- the file content **changed on disk**
- the mutated suite **ran tests**
- the restore put the file back **byte-for-byte**

If any of those cannot be established the verdict is **INDETERMINATE**,
never "not caught". Three states, not two — the same discipline the resolver
uses for `resolved` / `unresolvable` / `not_reported`, and for the same
reason: *"could not check" must never render as "checked, and it was fine"*.

Exit code 2 for indeterminate, so a set with a stale spec fails a build
rather than quietly reporting fewer results.

### `tests_run` returns `None`, not `0`

A suite that failed to compile prints no count at all. `None` and `0` are
different facts, and collapsing them is the ADR 0065 misreading encoded into
a data type. `ran` is `count is not None and count > 0`.

## The harness reproduced the bug it was written to prevent

The first version restored in a `finally` block. It was then run under
`timeout`, exceeded the sandbox's per-call ceiling mid-mutation, and was
killed. **`finally` does not run on SIGKILL.** The mutation stayed in the
working tree, and the next test run reported a failure that looked like a
real regression.

That is failure mode 3 again — five mutations left in the tree by a cleanup
that did not happen — reproduced by the tool written to prevent it, within
an hour of writing it.

The lesson is not "be more careful". It is that **a cleanup path which may
not run is not a guarantee**, and no amount of care in the dying process
fixes that. So recovery was moved to the only participant guaranteed to be
alive: the next run.

- Original bytes are written to `.mutate-journal/` **before** the mutation.
- Every run calls `recover_journal()` first, restores anything left behind,
  and says so loudly — including the sentence a reader most needs: *"the
  failure you saw was this, not your code."*
- SIGTERM and SIGINT are turned into exceptions so `finally` still runs for
  the common `timeout` case. The journal covers SIGKILL, which cannot be
  caught at all.

Verified end to end, not assumed: a `timeout -s KILL 45` run left the tree
mutated (confirmed by checksum), and the next invocation printed `RECOVERED`
and restored the file to its original digest.

## Mutation-testing the harness

Per the standing rule — *mutation-test every guard against the specific
historical failure it claims to prevent* — `--selftest` reproduces all
three:

| historical failure | expected | result |
|---|---|---|
| search string absent (ADR 0051, 0056) | INDETERMINATE | ok |
| replacement identical to original | INDETERMINATE | ok |
| suite reports no test count (ADR 0065) | INDETERMINATE | ok |
| file restored after every case | clean | ok |
| a real mutation against a passing suite | **NOT CAUGHT** | ok |

The last row is the one that keeps this from being a check that cannot fail.
Without it, a harness that returned INDETERMINATE unconditionally would pass
every other case — the same trap as a citation guard that parses zero
entries and prints OK.

Wired into `verify_build.py` and `EXPECTED_WIRING` (45 guards).

## Mutation sets

`docs/mutations/adr-0058-sweep.json` records ADR 0058's table as a
re-runnable artifact:

```
python3 scripts/mutate.py --set docs/mutations/adr-0058-sweep.json
```

The table in an ADR is a claim about the past. The set file is a claim that
can be re-checked, and each entry carries a `_note` recording whether it was
originally caught and what closed it if not.

If the source is later refactored, the spec stops matching and the harness
reports INDETERMINATE — a finding about the *record* going stale, which is
useful, and which the old approach reported as "not caught", which was a
false alarm about the tests.

## Consequences

- Mutation results in future ADRs are reproducible rather than testimonial.
- A set of four mutations runs four suites plus a baseline, which exceeds
  the sandbox's per-call ceiling. That is what killed the first run. Sets
  should be small, or run outside the ceiling; the journal makes an
  interrupted run recoverable rather than damaging.
- `.mutate-journal/` is gitignored.
- The existing ADR mutation tables were **not** retroactively re-run. They
  were established by hand, some of them twice; re-deriving them all is a
  larger job than this pass, and claiming they had been re-verified when
  they had not is the exact dishonesty this file exists to remove.

## Related

- [ADR 0051](0051-the-evidence-did-not-choose-the-value.md) and
  [ADR 0056](0056-a-column-that-claimed-a-source.md) — the no-op patches
- [ADR 0065](0065-object-object.md) — `Tests: 0 total` is not `0 failed`
- [ADR 0058](0058-the-crashed-point-won-the-sweep.md) — the table now
  recorded as a set file
