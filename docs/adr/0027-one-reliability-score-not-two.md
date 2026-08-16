# ADR 0027: One reliability score, not two

**Status:** Accepted, implemented

**Date:** 2026-08-13

**Relates to:** ADR 0024 Decision 3 (Bakker's axes, adopted), ADR 0008
(parameter provenance), ADR 0012/0013 (never default a parameter), ADR 0016
(cached results lose provenance)

## Context

ADR 0024 Decision 3 adopted Barbara Bakker's three reliability axes. It was
implemented twice — `Tests/reliability.py` and
`Science-Agent-Pipeline/artifacts/api-server/src/lib/reliabilityScore.ts` —
and a parity test asserted the two agreed on a shared 16-case fixture.

They did agree. It did not help.

`science_agent_runner.py` has always graded every resolved value and emitted
the score in its JSON. `ScienceAgentResult` had no field to receive it, so
the API server **discarded** the score it had just been handed and ran the
TypeScript grader instead — with no `PhysiologicalReference` argument,
because none was reachable from an HTTP request.

The result: `conditionProximity` returned `not_assessed` on every response
the API server ever produced. Not intermittently. Always. Meanwhile the CLI,
consuming the Python score, reported real grades.

One third of Bakker's score was structurally unreachable through one of the
two front ends, and a documentation comment in `literatureResolver.ts` said
the opposite — that the CLI and the API "report identical grades for
identical inputs."

## Why the parity test could not see it

This is the part worth keeping.

**A parity test pins two implementations against a shared fixture. It says
nothing about a call site that hands one of them different arguments.**

Both graders return `not_assessed` when given no reference. They agreed
perfectly on a question neither was being asked. The test was true,
maintained, passing, and blind — the same shape as the false-green guards
catalogued in ADR 0024's verification note, arriving from a new direction.

The defect was also symmetric on the wire, which is what let it survive: a
response computed without a reference and a response where the reference was
dropped in transit look identical, because the runner returns `not_assessed`
rather than an error when it has none. Nothing downstream could tell "nobody
stated what this model represents" from "we forgot to ask."

## Decision

### 1. The runner's score is the score

`ScienceAgentResult` gains `reliability`. `queryResolver.ts` assigns it
through and does not recompute.

**A fallback to a TypeScript grader when the runner sends nothing was
considered and rejected.** A second implementation kept "just in case" is
how this drift started, and a score produced by the fallback would be
indistinguishable in the response from one produced by the resolver. Absent
is reported as absent — the same rule ADR 0012/0013 apply to parameters,
applied to the description of a parameter.

### 2. The TypeScript grader is deleted, not bypassed

Merely stopping the call would leave a dead duplicate alive in its own test:
the state this repository's orphan guard calls *harder to notice than an
untested one*. The guard could not have flagged it either, because the
module is still imported for its types — a blind spot worth noting on its
own.

`reliabilityScore.ts` keeps the types (they are the wire contract) and
exports no callable. `reliabilityScore.test.ts` now guards the deletion
rather than the code: it asserts the module exports **no function at all**,
not merely that the four old names are gone. A duplicate reintroduced as
`computeReliabilityAxes` is still a duplicate, and the name was never what
made it one.

No coverage was lost. The behaviour is pinned by
`Tests/reliability_cases.json` (16 cases) with
`test_case_file_is_not_empty_and_covers_every_grade` asserting the fixture
exercises every grade of every axis.

### 3. The reference becomes a real input

`ResolveQueryOptions` gains `physiologicalReference`, threaded through
`applyKineticResolution` to the runner — exactly as `allowCrossSpecies` was
in ADR 0024, and for the same reason recorded there: *an input reachable
only from an internal subprocess payload is not an input, it is a constant.*

It is never defaulted. pH 7.4 and 37 °C describe a mammal and misdescribe
*Thermus thermophilus*, whose enzymes are measured near 70 °C; defaulting
would report a confident `far` for a thermophile assay that was in fact
ideal. All five fields are required and a partial reference is refused
rather than completed — half a reference plus an assumed 37 °C is an assumed
mammal.

## Verification

`reliabilityFromRunner.test.ts` (4) — pass-through, using a mocked grade
(`conditionProximity: "near"`) that recomputation at that call site *cannot
produce*, since producing it requires a reference. Choosing a grade the
wrong implementation is incapable of returning is what makes a pass-through
testable at all; asserting on `not_assessed` would have been satisfied by
the bug.

`reliabilitySingleSource.test.ts` (5) — the argument's journey. These assert
on the **call**, not the response, because the response is identical either
way. Includes the tolerances, whose loss is not a smaller version of the
same bug: the runner refuses a reference missing any of the five fields, so
a reference stripped of its tolerances is silently equivalent to no
reference at all.

`reliabilityScore.test.ts` (6) — the deletion holds.

Six mutations, all caught:

| Mutation | Failures |
|---|---|
| recompute in TypeScript with no reference (*the original bug*) | 3 |
| fall back to the TS grader when the runner sends nothing | 1 |
| stop forwarding the reference to the runner | 1 |
| default the reference to human when the caller omits one | 2 |
| reintroduce a grader under a different name | 1 |
| un-export a wire-contract type | 1 |

## Consequences

- `ScienceAgentResult.reliability` and `EntityExtraction.physiologicalReference` are new.
- `ResolveQueryOptions.physiologicalReference` is new.
- `reliabilityScore.ts` is types-only; its grading functions are gone.
- The CLI path is unchanged — it already consumed the Python score.
- **Reachable over HTTP.** `SimulationRequest` gains an optional
  `physiologicalReference` with all five fields required when present, and
  `normalizeQuery` includes it in the cache key.

  The cache key is not optional politeness. Two callers stating different
  modelled conditions are asking different questions, and the answers differ
  in the `conditionProximity` grade of every resolved parameter. Without it,
  a result graded `near` against a thermophile's 70 °C would be served to a
  caller who stated 37 °C, carrying a grade computed against conditions they
  never described — ADR 0016's failure with a new field, and every guard
  downstream would pass, because the value really was resolved and really
  was cited.

> **Superseded in part by [ADR 0030](0030-codegen-emitted-a-contract-that-could-not-load.md).**
> The section below calls the codegen difference a version *drift* and treats
> it as a formatting-level risk. It was worse than that: `zod.iso` is
> `undefined` on the installed zod, so a full regeneration produced a
> contract that **threw on import**. The hand-patching described here was
> load-bearing for a reason this ADR did not know. Fixed and guarded in ADR
> 0030; the original assessment is left standing because a finding judged
> cosmetic staying open for a day while being a crash is part of the record.

### A correction, and a drift found while making it

An earlier draft of this ADR said no orval config was checked in and the
generated client therefore could not be regenerated. **That was wrong.**
`lib/api-spec/orval.config.ts` exists, with a `codegen` script, and orval
runs. The claim was made from a `grep` that missed the file, and it would
have justified leaving the feature unreachable — a wrong fact producing a
wrong decision, which is the failure mode this project is built around. It
is corrected here rather than quietly edited away.

Running codegen surfaced a real problem. A full regeneration today produces
the new field **and** rewrites every date field in the contract from
`zod.coerce.date()` to `zod.iso.datetime({ offset: true })` — a zod/orval
version drift between the toolchain that produced the committed files and
the one installed now. Those are not equivalent: one coerces, the other
validates a string, and the difference reaches every timestamp the API
accepts or returns.

Shipping that as a side effect of adding one property would be an invisible
behaviour change across the whole contract. So the field was applied to the
generated files by hand, matching their existing idiom, with a comment at
the splice naming why. The blocks regenerate identically once the drift is
resolved.

**The drift is a separate, unfixed finding.** It should be resolved before
the next full `pnpm --filter @workspace/api-spec run codegen`, or that
regeneration will make the change silently, in a diff that looks like
generated noise.

Boundary tests (`physiologicalReferenceRoute.test.ts`, 9) exist because zod
strips unknown keys by default: a field present in the spec, present in the
types, and absent from the schema would compile, type-check, and vanish in
transit with no error. Mutations confirm — removing the field from the
schema fails 8 of 9; making the tolerances optional fails 2.

## What this says about the codebase

Two agents working the same tree found this defect independently, within a
minute of each other, and wrote nearly the same reasoning. That is a signal
about the defect, not about the agents: a duplicated implementation whose
copies receive different arguments is a recognisable shape, and this
repository has now hit it in the endpoint guard (half a route table), the
cross-species branch (two standards in neighbouring branches), and here.

The recurring lesson is not "avoid duplication." It is that **the test which
pins a component tells you nothing about the wiring**, and this project has
now been bitten by that four times in three days.
