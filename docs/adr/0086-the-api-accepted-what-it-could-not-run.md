# ADR 0086: The API accepted three queries it could not run, and refused two it could

**Status:** Accepted, implemented

**Date:** 2026-08-16

**Relates to:** ADR 0084 (found in the same pass, running the API as a
client), ADR 0020 (wired the `sir` domain the API then refused), ADR 0003 and
0027 (the same duplicate-source-of-truth defect elsewhere)

## What was found

POSTing to `/api/simulate` with each model name the product mentions.

`src/validation/request-validator.ts` held a hardcoded list of four valid
queries. It had drifted from the pipeline **in both directions at once**:

| | |
|---|---|
| accepted, but unrunnable | `competitive-inhibition`, `non-competitive-inhibition`, `product-inhibition` |
| runnable, but rejected | `sir` — the whole epidemiology domain — and `mm` |

### The accepted-but-unrunnable half is the dangerous one

```
$ curl -X POST /api/simulate -d '{"query":"competitive-inhibition",...}'
{"jobId":"job_1786904592318_...","status":"queued"}          <- 200

$ curl /api/jobs/job_1786904592318_...
{"status":"complete","progress":100,
 "result":{"validated":false,
           "validationErrors":["Query 'competitive-inhibition' does not name
                               a domain this pipeline knows (mm, sir)"]}}
```

The request passed validation, was queued, returned a job id, and the job
finished reporting **`status: "complete"`** — the same status a successful run
gets — with the refusal buried inside `result.validationErrors` twelve
seconds later.

### The rejected-but-runnable half

`sir` was wired end to end by ADR 0020 and was **unreachable over HTTP for as
long as both existed**, because a list written before the domain never
learned about it. `mm` is the CLI's own documented spelling — `sweep mm
--parameter ...` is in `help` — so a student who learned it at the terminal
got a 400 for the same word from the API.

There were three separate notions of "which models exist", all disagreeing:
this validator's list, `ScientificPipeline.DOMAINS` (`mm`, `sir`), and the
engine's `kinematicModels` registry (five models, including an `allosteric`
the pipeline cannot place).

## Decision

**The validator asks instead of remembering.**
`ScientificPipeline.namesAKnownDomain(query)` is now public and static, and
delegates to the same `classifyDomain` matcher the pipeline uses to decide
what it will actually run. The hardcoded list is gone.

Acceptance and runnability are now the *same predicate*, not two lists that
happen to agree today. A validator that keeps its own copy of what the engine
supports validates the copy — the defect this repository has now found in a
plausibility table (ADR 0003), a reliability score (ADR 0027), a codegen
probe config (ADR 0036), and here.

The error message is derived too, from `knownDomainAliases()`, so it can
never advertise a query the matcher would reject:

```
query must name a model this pipeline can run: michaelis, michaelis-menten,
michaelis menten, enzyme kinetics, enzyme, mm, sir, epidemic, infection,
outbreak, susceptible
```

**`allosteric` stays rejected, and that is now correct rather than
accidental.** The engine registry implements it, but the pipeline cannot
place it on a domain, so accepting it would produce exactly the "queued then
complete-but-unvalidated" outcome this ADR removes. Making it runnable is a
separate change to the pipeline, not to a validator.

## Not fixed here, and recorded deliberately

**`status: "complete"` is still set unconditionally**, for validated and
unvalidated runs alike, in both the in-memory job map and the persisted
record. The metrics collector already gets this right — it records
`success: response.validated === true` — so two records of the same run
disagree, and the job status is the one that is wrong.

This ADR does not change it because the published contract
(`SimulationJobStatus`) enumerates `pending | resolving | validating |
running | completed | failed`, and adding a state is a wire-contract change
needing codegen and a dashboard update. Worth noting while here: the server
emits `complete`, the contract says `completed` — they do not currently
match either.

Refusing unrunnable queries at request time removes the *common* way a job
reached that state, which is why it was worth doing first.

## Consequences

- `src/validation/__tests__/queriesTheEngineCanRun.test.ts` asserts the
  property rather than a list: for every probe, `accepts(query) ===
  namesAKnownDomain(query)`. Probes include `summary` and `desire`, which
  must not match `mm` and `sir` — the word-boundary behaviour the matcher
  already had and which a looser check would silently lose.
- Mutation-tested: restoring the hardcoded list fails five of six tests.
  The sixth, "still rejects a missing or non-string query", correctly
  survives — it tests a different rule.
- Verified against the running server: `michaelis-menten`, `mm` and `sir`
  return 200; `competitive-inhibition`, `product-inhibition` and
  `allosteric` return 400 at request time; the server stays up.
- 113 validation tests pass, including the 107 that existed before.

## Addendum: `/api/sweep` and `/api/batch` had no such check at all

`validateSweepRequest` and `validateBatchRequest` only asserted that `query`
was a non-empty string. So the same word was a 400 on `/api/simulate` and an
accepted job on the other two — one API, three answers.

Batch is the worst place to leave it: one unrunnable query becomes N failed
jobs, each recorded, each reporting `complete`.

Both now apply the same `namesAKnownDomain` check. Verified against the
running server:

```
sweep  competitive-inhibition -> 400      batch  competitive-inhibition -> 400
sweep  mm                     -> 200      batch  mm                     -> 200
```
