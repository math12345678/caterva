# ADR 0125: A score that could only be zero

**Status:** Accepted

**Date:** 2026-08-18

## Context

Run the first example in `help` and the pipeline logs:

```
✓ All validation layers passed
```

Four lines later the CLI prints:

```
Quality:
  Validation confidence: 0.0%
  Overall confidence: 0.0%
```

Both are true. Read together they say the simulation is worthless, which is
not true, and it is the most common output in the product.

The cause is one line in `scientificPipeline.ts`:

```ts
confidence: literatureSources.length > 1 ? 0.95
          : (literatureSources.length > 0 ? 0.92 : 0)
```

**Confidence is a function of how many papers back the parameters, and of
nothing else.** It does not move when the numbers are dimensionally sound,
when they sit inside plausibility bounds, or when every model assumption
held. On the hand-typed path there are no papers, so it is 0 — not because
the run was poor, but because the quantity has exactly one reachable value
there.

A number that can take exactly one value on a path is not a score, and
presenting it as one under the heading **Quality** tells a student their
correct simulation failed.

### The dashboard was worse

`dashboard.html` rendered the same number as a percentage in the results
table, and used the literal `'0'` for two other outcomes:

| what happened | cell |
|---|---|
| the run failed | `0%` |
| the run threw an error | `0%` |
| the run was correct and made no literature claim | `0%` |

One cell, three outcomes, identical text — and the third is the common case.
The `<td>${result.confidence}%</td>` template forced every value into a
percentage, so no non-numeric state could be expressed even if the branch
above it had wanted to.

## Decision

**Three states, not a zero standing in for the middle one** — the same
discipline as `resolved` / `unresolvable` / `not_reported` elsewhere in this
codebase, and as `reviewed` / `hashed` / `absent` in the image register.

A literature score, no literature claim to score, or a failure:

```
Quality:
  Literature agreement: not applicable — this run made no
                        literature claim to check.
  What was checked:     units and dimensions, plausibility
                        bounds, and the model assumptions
                        listed above. All passed.
```

The second line matters as much as the first. Removing the misleading number
without saying what *was* verified would leave a student thinking nothing
had been — which is the opposite error and just as wrong.

It closes by naming the command that would make a literature claim, because
"not applicable" should point at what would make it applicable.

**The label says what the number measures.** Where literature exists it is
now `Literature agreement`, not `Validation confidence`. The old label
described the value's position in the pipeline rather than its meaning.

**The percentage sign travels with the number, not the cell.** Otherwise
`n/a` renders as `n/a%` the moment anyone puts it back.

## Consequences

- A student supplying three correct parameters is told what was checked and
  what was not, instead of `0.0%`.
- The dashboard's results table distinguishes a failure (`—`) from a
  correct unsourced run (`n/a`) from a sourced one (`92.0%`).
- Nothing about the underlying score changed. This is a reporting fix, and
  the number remains available and honest where it means something.

### What this does not fix

`confidence` still measures only source count. Whether a run's *numerical*
quality deserves a score of its own — dimensional soundness, assumption
satisfaction, how far the parameters sit from their plausibility bounds — is
a real question and is not answered here. Inventing an aggregate would
repeat the mistake Bakker's feedback already corrected once: her three axes
are reported separately with a `noAggregateReason`, precisely so a client
looking for a total finds an explanation rather than an absence it papers
over with an average of its own (ADR 0024).

The same reasoning applies to a "simulation quality" number, so none is
introduced.

## Verification

`src/web/__tests__/confidenceIsNotAZero.test.ts` — 6 tests against the
shipped `dashboard.html`, replayed in both directions:

| mutation | result |
|---|---|
| the cell forces a percentage again | caught |
| the `n/a` branch is removed | caught |
| a failure path reuses `'0'` | caught |

`dashboardParameterGate.test.ts` (35 tests) still passes, so the VM harness
sees no behavioural regression.

One test pins the premise: if `validationConfidence` ever starts reflecting
dimensional or assumption checks, *"not applicable"* becomes the wrong label,
and that change should force a decision here rather than silently invalidate
this ADR.

**What the tests cannot do** is render the page. They check the shape of the
three branches in the file that actually ships, which is what the defect
was — one literal reused across three outcomes — and the file says so.

## Related

- ADR 0024 — three axes reported separately, with `noAggregateReason`
- ADR 0044 — the dashboard's pre-filled `5.2`, and the green tick it bought
