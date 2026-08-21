# ADR 0138: The weights reach both front ends

**Status:** Accepted, implemented

**Date:** 2026-08-20

**Context:** `science_agent_runner.py`, `queryResolver.ts`,
`literatureResolver.ts`, `commandResolve.ts`

**Completes:** [ADR 0137](0137-the-fixture-a-student-does-not-have.md), which
made the resolver carry the scored frontier and left it visible only inside
`scientific ensemble`.

## The gap the guard was built for, arriving on my own work

`check_both_front_ends_read_it.py` exists because a finding built for one
front end reaches half the users — recorded four times (ADR 0106, 0109, 0110,
0114). This pass emitted `ensembleCandidates` from the runner, wired it into
the API, and the guard immediately said:

```
Findings that reach one front end and not the other (1):
  ensembleCandidates
      read by the API only
```

Correct, and worth stating plainly: the `ensemble` command shells out to
Python and never passes through `literatureResolver.ts`, so the ordinary
`scientific resolve` path — the command a student runs first — knew nothing
about the weights. Baselining it would have been recording the defect the
guard was written to prevent, on the pass that introduced it.

Both sides now read it, and the guard is green without a new baseline entry.

## What each side shows

The **API** renders into `provenance.flags`, the list the CLI and web UI both
consume:

> `KM — 2 published values survive the evidence ranking, each graded on assay
> completeness / condition proximity / organism match: 0.03 mM [ref 286469]
> (absent/not_assessed/exact); 0.398 mM [ref 286442] (complete/near/exact).
> These grades are the weights an ensemble samples by; `scientific ensemble`
> runs the model once per draw and shows whether the disagreement changes the
> answer.`

The **CLI** renders the same facts in its own layout:

```
2 published values survive the evidence ranking:
    10.73 mM  [ref 740253]
        complete / not_assessed / exact
    0.398 mM  [ref 286442]
        absent / not_assessed / exact
  These grades are the weights an ensemble samples by. To see
  whether the disagreement changes the answer:
    scientific ensemble --enzyme ... --substrate ... --seed 1 --simulate michaelis_menten
```

Both **name the command**. A reader shown a spread with no way to act on it is
left exactly where [ADR 0115](0115-the-question-that-named-the-system.md)
found them: holding a finding and no next step.

## What it stays quiet about

Fewer than two surviving values is not a disagreement, and a flag about one
row would be noise. This project prints a lot of flags and cannot afford ones
that carry no decision — three tests pin the silence (one candidate, absent
field, nothing resolved).

The list caps at four with an explicit remainder, for the reason
`selectionTieFlags` already gives. The **count** is still the true one, so
the cap can never understate the disagreement — asserted, because a cap that
also truncated the count would quietly shrink the finding.

## Two parsers, not a cast

`literatureResolver.ts` reads the field through `parseEnsembleCandidates`
rather than casting it. A row needs a finite value and all three grades;
anything else is dropped. A row missing a grade would either crash the
sampler or render as a blank line where a measurement should be, and the
count shown to a reader comes from the filtered list so it can never promise
more values than it names.

## The contract test caught the new key, which is the system working

`test_runner_contract.py::test_golden_found_output_shape` asserts the emitted
shape **exactly**, and failed the moment `ensembleCandidates` appeared. The
expectation now names it — with `[]`, because the hand-built golden result
carries no frontier — and the comment says why it is asserted rather than
omitted: a key left out of the expectation would let the field disappear
later without anyone noticing.

The offline stub gained the field too, with **two rows carrying different
grades**. A fixture where every row scores alike cannot distinguish "the
grades were rendered" from "something was rendered", which is the same trap
as a mutation that is a no-op against its input.

## Verification

- **99 Python tests** across the five affected suites, including the 36
  pre-existing `fallback_logic` tests and the 21 runner-contract tests that
  guard the emitted shape.
- **9 API tests** on `provenance.flags`, asserting on the flag rather than
  the response field — ADR 0040 is the record of findings that reached the
  API and never reached the student.
- The CLI rendering verified end to end against the offline stub.
- `check_both_front_ends_read_it.py` green, 23 listed, **0 new**.

## Consequences

- The ensemble's inputs are visible from the first command a student runs,
  not only from the one they have to know exists.
- `ensembleCandidates` is emitted on every resolution whether or not anybody
  samples. It is a handful of dicts, and requiring a second resolution to
  obtain the weights would be the duplicate-resolution defect ADR 0137
  refused one layer down.
- Still one-sided and listed as debt: 23 other keys, unchanged this pass.

## Related

- [ADR 0137](0137-the-fixture-a-student-does-not-have.md) — the resolver
  carrying the scored frontier
- [ADR 0110](0110-the-finding-that-reached-half-the-users.md) — the guard
  that caught this
- [ADR 0040](0040-the-findings-never-reached-the-student.md) — why the tests
  assert on flags rather than fields
