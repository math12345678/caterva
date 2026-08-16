# ADR 0038: Effectors reach the API response

**Status:** Accepted, implemented

**Date:** 2026-08-14

**Relates to:** ADR 0032 (cofactors and the presence/absence pair — this is
its missing last mile), ADR 0026 (coherence across a set), ADR 0028
(buffers, whose wiring this mirrors), ADR 0027 (the call-site defect this
nearly repeated)

## Context

ADR 0032 closed the fourth of the four things Lisa Jeske named. Effectors
were extracted from BRENDA's commentary, resolved to PubChem compounds,
compared with presence as a first-class field, and emitted by the runner.

Its own consequences section said what it had not done:

> **Not yet wired into the TypeScript coherence report.** `assayCoherence.ts`
> compares pH, temperature and buffer; adding effectors there is the next
> step and is not done here.

So a user of the API saw none of it. The Python side knew that a Km measured
with fructose 1,6-bisphosphate and one measured without it were different
conditions, and the response said nothing.

## Decision

`CoherenceReport.effectors` is a new section, mirroring `buffer` exactly:
`same` / `different` / `unknown` / `not_reported`, reported **alongside**
`verdict` and never folded into it.

The reasoning is ADR 0028's and is not re-derived: `verdict` answers "same pH
and temperature", a question with a clean answer, while effector
comparability's most common honest answer is "the sources did not say".
Merging them would let an unmentioned cofactor downgrade a temperature
finding that *was* established.

The comparison key is `(compound identity, presence)`. A key on compound
alone reports `same` for the exact pair ADR 0032 was written about — a
wild-type LDH measured with and without its allosteric activator, at the
same pH and temperature, from the same paper, where every other axis agrees.

## Two wiring defects, one caught by checking and one by mutation

**The first was caught before it shipped.** The natural place for
`effectors` on `ScienceAgentResult` is inside `assayConditions`, beside
`bufferIdentity` — it reads better and it is where a reader would look. The
runner emits it at the **top level**, beside `variant`.

Put in the natural place, the field would have type-checked, compiled, and
been `undefined` forever. That is precisely ADR 0027's defect, and it was
avoided only by grepping the emitter instead of trusting the shape. The
field's doc comment records this, because the next person will have the same
instinct.

**The second was caught by mutation, after the tests were written.**
Severing the resolver — making `toAssayConditions` stop receiving
`agentResult.effectors` — broke **nothing**. All 35 tests in
`assayCoherence.test.ts` still passed.

They build `ParameterUnderTest` objects by hand and never call
`resolveQuery`. The judgement was intact and the wiring was cut, and no test
could tell the difference.

This is the third occurrence of one shape:

| ADR | What was severed | What still passed |
|---|---|---|
| 0026 | the `origin === "resolved"` filter | every end-to-end test |
| 0027 | the reliability call site's `reference` argument | the parity test |
| 0038 | the resolver's `effectors` argument | all 35 unit tests |

**A test that constructs its own input cannot verify how the input is
produced.** Four tests in `coherenceEndToEnd.test.ts` now go through
`resolveQuery`, and both wiring mutations fail three of them.

## Verification

`assayCoherence.test.ts` (+9, 35 total) and `coherenceEndToEnd.test.ts`
(+4, 12 total).

| Mutation | Failures |
|---|---|
| the comparison key drops presence (*the motivating pair collapses*) | 3 |
| an effector difference downgrades the conditions verdict | 1 |
| unresolved compounds report `same` instead of `unknown` | 1 |
| one side reporting nothing reads as agreement | 1 |
| the resolver stops forwarding effectors | 3 *(0 before the e2e tests)* |
| `toAssayConditions` drops the effectors it was handed | 3 |

Backups verified with `cmp` before starting and after restoring, following
ADR 0029. One batch hit the tool timeout mid-run; the `cmp` check confirmed
both files had been restored before the cut, which is the reason that
discipline exists.

559 Python tests pass, 169 TypeScript tests across the provenance and
resolution suites pass, `tsc --noEmit` is clean in both trees.

## Consequences

- `CoherenceReport.effectors`, `AssayConditions.effectors`, the TypeScript
  `Effector` type, and `ScienceAgentResult.effectors` are new.
- `toAssayConditions` takes effectors as a second argument, and builds a
  conditions object from them even when `assayConditions` is absent — a row
  can name a cofactor and report neither pH nor temperature, and dropping it
  would lose the one thing the commentary did say.
- All four of Jeske's items — pH, temperature, buffers, cofactors — are now
  compared **and visible in the API response**. That sentence is worth
  writing once, carefully: it is true of the coherence report, and it is not
  a claim that the comparisons are complete. Concentration is still not
  compared, and ADR 0032's limits all still stand.

## What this does not claim

The full TypeScript suite was not run to completion here — it spawns Python
subprocesses per engine test and outruns the sandbox's tool timeout. Eight
suites covering provenance, schemas, STRENDA, the withheld paths and both
coherence surfaces were run and pass; the engine-simulation suites were not
re-run, and nothing in this change touches them.

Stated rather than implied, because "the tests pass" and "the tests I ran
pass" are different claims and only one of them is true here.
