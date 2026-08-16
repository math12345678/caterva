# ADR 0039: Computed, and never delivered

**Status:** Accepted, implemented

**Date:** 2026-08-14

**Relates to:** ADR 0027 (**this is the same defect, four times over**),
ADR 0033 / 0035 / 0037 (the detectors that were not delivered), ADR 0026

## Context

Four passes built four pool-level detectors:

| ADR | detects |
|---|---|
| 0033 | a compound the pool reports both with and without |
| 0035 | one enzyme base named with several form designators |
| 0037 | a row whose commentary contradicts its organism column |
| 0037 | one organism measured from several biological sources |

Every one was mutation-tested. Every test passed. The Python suite was green
at 585 tests.

**None of them reached a user.**

The resolver computed each finding and attached it to `KineticResult`. The
runner never emitted the fields. They were dropped at the process boundary,
and the only thing that crossed was a prose line in the diagnostic `logs` —
which is not `provenance.flags`, the list the CLI and web UI actually render.

This is ADR 0027's defect exactly: a thing computed correctly and discarded
at a boundary, invisible because every test on the computation passed. That
ADR was written six days ago, about a score the API server threw away. I read
it, cited it in three subsequent ADRs, and then built the same defect four
times.

It was found by asking, before writing a fifth detector, whether the first
four had ever been seen by anyone.

## Decision

### The findings cross the wire

`science_agent_runner.py` emits `poolFindings`, a single object holding all
four groups. `ScienceAgentResult` receives it.

Emitted **unconditionally**, empty when the pool held nothing, so a consumer
never has to distinguish "absent" from "empty" — and so the exact-equality
contract test keeps failing if the shape changes again.

### They become flags, not logs

`queryResolver.ts` turns each finding into an entry in `provenance.flags`.
That is the list the front ends render; the diagnostic log is not.

**Nothing is reworded.** Each finding already carries a `reason` written for
a human and argued over in the Python module. A client that paraphrases
becomes a second place the wording can drift, which is ADR 0027's shape
applied to prose.

### Both front ends, not one

The CLI consumes `poolFindings` too, rendered under the existing
cross-species and variant warnings.

ADR 0027 exists *because* two front ends disagreed about a third of Bakker's
score while a parity test asserted they agreed. Shipping a finding to one of
them would have rebuilt that divergence from scratch, and this time
deliberately.

## Two things found by running the real path

Writing the wiring test was not enough. Resolving an actual query through
`fallback_logic` surfaced two problems no fixture had.

### 1. A claim in ADR 0037 was overstated

That ADR said *Gallus gallus* heart 60.0 against muscle 1.1 was "a factor of
fifty-four, and `min()` takes 1.1". The span is real **across the table** and
wrong about the code path: substrate filtering runs first, and those two rows
are different substrates.

The competing pool is `(Gallus gallus, NAD+)` — **muscle 3.3 against heart
60.0, eighteen fold, and the resolver does return 3.3.** The finding holds;
the number and the substrate were wrong. Corrected in ADR 0037 in place,
marked as a correction rather than edited away.

A figure measured across a table and reported as if measured on a code path
is a true-sounding wrong claim, which is the defect class this project is
built around.

### 2. "Nothing found" and "nothing checked" were the same value

Running that query with the network blocked, the source-mixture detector
reported **no mixture at all** — on a pool genuinely holding heart 60.0 and
muscle 3.3.

Every token classified `unresolved` (NCBI unreachable), every one was
skipped, and the result was indistinguishable from a clean pool.

`SourceCheckUnavailable` now distinguishes them: tokens were extracted, none
could be classified, so the pool was **not checked**. Reported on the result
and in the log.

This is the same conflation as `not_found` versus `cross_species_withheld`
(ADR 0024) and `unstated` versus `wild_type` (ADR 0029) — and it had shipped
inside a module written to avoid exactly that.

## Verification

`poolFindingsReachTheUser.test.ts`, 9 tests, asserting on **flags** rather
than on the field. A field that arrives and is never rendered is the same
failure one layer along.

Five mutations, all caught:

| Mutation | Failures |
|---|---|
| the findings are never pushed (*the original defect*) | 5 |
| only effector contrasts survive, the other three dropped | 3 |
| the reason is paraphrased away | 2 |
| the parameter name is dropped from the flag | 1 |
| flags emitted when the pool was clean | 1 |

Plus `test_pool_findings_cross_the_boundary_populated` in the Python contract
tests — paired with the empty-shape case, because an empty assertion cannot
distinguish "transmitted" from "dropped and defaulted to empty", which is
precisely what hid this for four ADRs.

## Consequences

- `poolFindings` on the wire; `PoolFindings` in TypeScript; rendered by both
  front ends.
- `KineticResult.source_check_unavailable` is new.
- ADR 0037's fifty-four-fold claim is corrected to eighteen-fold on the real
  path.

## Independently confirmed, seventeen minutes apart

While this was being written, a concurrent agent wrote
[ADR 0038](0038-effectors-reach-the-api-response.md) — the same defect class,
found independently, for the effector fields of ADR 0032. Their file predates
this one by seventeen minutes.

Two agents on one tree, neither aware of the other, both arriving at "the
thing we computed never reached the response". That is worth recording as
evidence about the **defect** rather than about either agent: a boundary that
drops a field is invisible from both sides, and the only thing that finds it
is deliberately walking across.

The ADR-number guard caught the collision, as it has caught the three before
it.

## The lesson, stated plainly

A detector is not delivered when its tests pass. It is delivered when
something a user looks at changes.

This project has now hit the boundary-drop defect twice — ADR 0027 and here —
and the second time was in full knowledge of the first. Reading an ADR about
a class of mistake does not prevent it. What prevented it was the specific
act of tracing one finding from the module that computes it to the surface a
person reads, and that trace is cheap enough to be routine.
