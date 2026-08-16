# ADR 0045: A guard for the boundary

**Status:** Accepted, implemented

**Date:** 2026-08-14

**Relates to:** ADR 0043 (claimed with `scripts/claim_adr.py`, after this
ADR collided at 0040 — the fifth such collision), ADR 0027 and ADR 0039 (the two occurrences), ADR 0038 (a
concurrent agent's independent third), ADR 0031 (the coverage guard, same
shape of answer)

## Context

The same defect has now landed three times, twice by me and once by a
concurrent agent working the same hour:

| | what was computed | where it stopped |
|---|---|---|
| ADR 0027 | Bakker's reliability score | no field to receive it |
| ADR 0038 | effector identities | never emitted |
| ADR 0039 | four pool-level detectors | never emitted |

Every producer's tests passed, because it produced. No consumer had anything
to test, because it never knew. **A boundary that drops a field is invisible
from both sides.**

ADR 0039 closed by saying the fix is "tracing one finding from the module
that computes it to the surface a person reads, and that trace is cheap
enough to be routine." A lesson written in an ADR is a lesson read once. This
makes the trace automatic.

## Decision

`scripts/check_findings_reach_a_surface.py` walks every field on
`KineticResult` along the delivery chain:

```
resolver  ->  runner emits  ->  TypeScript receives  ->  a reader sees
```

The field list comes from `KineticResult.model_fields`, not from a list in
the guard. A guard holding its own copy keeps passing after a new field is
added — the failure mode, one level up.

### The runner hop is EXECUTED, not read

This is the part that matters, and it took three attempts.

**Attempt one** asked whether each field's name appeared anywhere in the
runner's source. Mutation-tested by deleting the emission of `poolFindings`
— the literal defect of ADR 0039 — **it passed**, because the list
comprehensions under the deleted key still mentioned
`result.effector_contrasts`. The word was present; the field was not
delivered.

A check answering "is this word written in this file" while claiming to
answer "does this field travel" is the false-green shape this repository has
now catalogued six times. It was worse than no guard, because it was about
to be trusted.

**Attempt two** ran the runner for real and read its emitted JSON. Better,
and still wrong: it collected every key at every depth, so renaming the
container from `poolFindings` to `_disabled` left every inner key present and
the guard passed on the same defect again.

**Attempt three** records key *paths*. `poolFindings.effectorContrasts` is a
different string from `_disabled.effectorContrasts`, so a container rename
fails. The path pins the wire shape; the leaf (`effectorContrasts`) pins what
TypeScript and the renderers name, since neither writes the dotted path.

### The probe walks every branch

The runner emits a different dict for a found result, a `cross_species_withheld`
one, and a `variant_withheld` one. The first probe exercised only the found
path and reported two fields as undelivered that live on the other branches.
That was the probe's gap, not the runner's. It now runs all three and unions
the result.

### Aliases redirect, they do not excuse

Six fields are renamed at the boundary — `assay_ph` travels as
`assayConditions.ph`, `search_log` as `logs`. The guard's first run reported
all six as undelivered.

Baselining them would have been wrong and instructively so: the baseline
means *internal, does not need to reach anyone*, and all six reach a reader.
Recording a true thing under a false heading is how a decision file stops
being read.

So `docs/field-wire-names.txt` maps field → wire path, and the aliased name
must still appear at every hop. **Point an alias at a name nothing emits and
the guard fails exactly as before** — verified by mutation.

## What it caught immediately

`source_check_unavailable`, added one pass earlier in ADR 0039 and never
wired to the runner. The guard written to stop fields being dropped found one
that had already been dropped, on its first run.

## What it does NOT catch, stated plainly

**It would not have caught ADR 0027.** `reliability` is computed inside the
runner and is not a field on `KineticResult`, so it is outside what is
walked. Mutating the runner to stop emitting it leaves this guard green —
verified, not assumed.

An earlier draft of the guard's own docstring claimed otherwise. A guard
advertised as covering a defect it does not cover is worse than one with a
stated scope, because the claim is what stops anyone looking further.

The TypeScript and rendering hops are still name matching. A field named in
`queryResolver.ts` but rendered into a string nobody displays would pass.
That hop is covered by tests instead (`poolFindingsReachTheUser.test.ts`),
and the division is deliberate: execution where it is cheap, names where it
is not, and the difference written down.

## Verification

Seven mutations. Five caught by the final version; two of those five defeated
earlier versions and drove the rewrites:

| Mutation | Final | Earlier |
|---|---|---|
| stop emitting `poolFindings` (ADR 0039) | fails | **passed** (v1, v2) |
| drop one group from `poolFindings` | fails | passed (v1) |
| alias points at a name nothing emits | fails | fails |
| chain files missing → must not report zero | fails | fails |
| probe fails → must not fall back to name matching | fails | n/a |
| guard uses its own field list | visible (2 fields, not 23) | — |
| stop emitting `reliability` (ADR 0027) | **passes — out of scope** | passes |

## Consequences

- Wired into `verify_build.py`. `check_guard_wiring.py` is right that an
  unrun guard "passes only when someone thinks to run it".
- `docs/field-wire-names.txt` is new and is a reviewed contract, not config.
- Two contract tests needed updating for `sourceCheckUnavailable` — the
  exact-equality wire tests earning their place twice in one pass.

## A note on how this got its number

This ADR was written as 0040 and collided with a concurrent agent's
`0040-the-findings-never-reached-the-student.md` — **the fifth ADR-number
collision in this codebase**, and the third time that agent and I
independently found the same boundary-drop defect within an hour.

They had already built the fix: `scripts/claim_adr.py`, which reserves a
number by writing a stub and then re-reading the directory, so two agents
racing can both see both files and apply the same rule about who yields. I
renumbered by using their tool rather than picking 0044 by hand, which is
what would have produced collision six.

Worth recording because it is the same lesson as the rest of this ADR: the
careful-manual-procedure answer to a race is not a fix, and neither of us
stopped hand-picking numbers until one of us wrote the thing that makes
hand-picking unnecessary.

## The honest summary

Three attempts were needed to build a guard against a defect I had already
written two ADRs about, and the first two attempts failed the mutation that
reproduces that exact defect.

That is not an argument against the guard. It is the argument for mutation
testing every guard against the specific historical failure it claims to
prevent — because a guard that merely *looks* like it checks the right thing
is the most expensive kind, and both earlier versions looked fine.
