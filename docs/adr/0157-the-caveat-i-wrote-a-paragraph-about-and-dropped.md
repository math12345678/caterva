# ADR 0157 — The caveat I wrote a paragraph about, and dropped

**Date:** 2026-08-22
**Status:** Accepted
**Completes:** [ADR 0149](0149-using-the-tool-as-a-student.md) — the four
dead dropdown options

## Context

The dashboard offered five kinetic models and the API accepted one (ADR
0149). Three of the four rejects — competitive, non-competitive and product
inhibition — were disabled with a label, then left as "named, not built"
through two passes.

They are built now. `INHIBITION_MODELS` and `runInhibitionModel` already
implemented all three for the CLI: competitive through the engine's
first-class `mm_competitive_inhibition` domain, the other two assembled as
SBML and run through the same solver. The pipeline calls that function
rather than reimplementing it — a fifth notion of "which models exist"
would be hard to justify two ADRs after deleting the third and fourth.

Measured over HTTP, all three now complete:

| query | engine domain | via SBML |
|---|---|---|
| `competitive-inhibition` | `mm_competitive_inhibition` | no |
| `non-competitive-inhibition` | `sbml` | yes |
| `product-inhibition` | `sbml` | yes |

## The part worth recording

`runInhibition` attaches `PRODUCT_INHIBITION_CAVEAT` to its result, under a
docstring I wrote in the same change:

> The CLI states that. An HTTP surface that ran the same model and returned
> only a trajectory would be making the assumption silently, which is worse
> than not offering the model: the caller cannot check an assumption nobody
> told them about. So the caveat travels on the result.

The response builder one layer up then copied three fields — `trajectory`,
`finalValue`, `computedMetrics` — and dropped everything else.

Measured on the running server: the string `caveat` appeared **nowhere** in
the job payload.

So the caveat was computed, returned, and thrown away, in the same commit as
the paragraph forbidding exactly that. *Computed and not delivered* (ADR
0027, 0038, 0039, 0047, 0113, 0155) is this repository's most-repeated
defect, and knowing its name in that much detail did not prevent writing it.
That is the finding, and it is more useful than the feature.

The fields are now named individually in the response rather than spread. A
spread would have prevented this bug and hidden the next decision: adding
something to a run's result should still require saying it belongs in the
response.

### What the caveat says, and why it must reach the caller

Product inhibition needs **Kp**, the inhibition constant of the reaction's
own product. The value a user brings is typically a **Ki** from BRENDA's
inhibitor table, which records a constant for some named inhibitor — not
necessarily this reaction's product. Using one as the other is a modelling
assumption, and the whole claim of this project is that a number carries
where it came from.

## A gap my own test found before shipping

`dispatches nothing it cannot classify` failed on `product`.

The alias list was `['product-inhibition', 'product inhibition']` — the bare
key was missing, so `product` was in `DISPATCHABLE_DOMAINS` and
unclassifiable, and `requiredParametersFor('product')` fell through to the
Michaelis-Menten list. That list has no `ki` in it: **the parameter that
makes it an inhibition model at all.**

Written last pass as "the mirrored drift" and speculative at the time. It
caught a real one on its second run.

## Also guarded

`non-competitive-inhibition` **contains** `competitive-inhibition` as a
substring. The classifier sorts aliases longest-first, so the shorter cannot
claim the longer query — but a test now says so, because the failure mode is
running the wrong model on the right parameters with no error.

## Verification

18 jest cases in `requiredParametersFollowTheDomain.test.ts`.

- All three models driven end to end against the running server, with the
  routing checked per model: `viaSbml` false for competitive, true for the
  other two.
- The caveat asserted present in the job payload, having been absent before.
- `takes its required parameters from INHIBITION_MODELS, not a copy` uses
  `toBe`, not `toEqual` — identity, so a second copy cannot pass by having
  equal contents.
- `requires ki for every one of them`: if `ki` became optional, all three
  would silently degrade to the model they exist to differ from.

## Consequences

- Four of the five dashboard options work. The label came off because the
  model runs, not because the label was inconvenient.
- `results.trajectory` is now typed as `Array<Record<string, number>>`,
  since the three shapes genuinely differ. The one existing consumer that
  assumed `{time, value}` now narrows explicitly and **throws** on a point
  without them, rather than casting.
- Test count +6 (18 in the file).
- **Still disabled, deliberately:** `allosteric`. `kinematicModels`
  implements "Allosteric (Hill)"; the pipeline has no domain for it and this
  pass did not build one. Offering a control that cannot work is the UI form
  of a check that cannot fail.

## Related

- [ADR 0149](0149-using-the-tool-as-a-student.md) — where the four dead
  options were measured
- [ADR 0155](0155-the-domain-that-never-reached-the-engine.md),
  [ADR 0156](0156-an-epidemic-reported-as-an-epidemic.md) — the two ADRs
  spent deleting duplicate notions of "which models exist"
