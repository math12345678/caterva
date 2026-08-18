# ADR 0111: What the tie does to the model

**Status:** Accepted, implemented

**Date:** 2026-08-17

**Context:** `Tests/spread_consequence.py`,
`scripts/report_spread_consequence.py`, `src/cli/exportArtifacts.ts`

**Relates to:** ADR 0024 Decision 3 (Bakker's ensemble, declined — and it
stays declined), ADR 0047 (the non-dominated set), ADR 0051 (the tie among
the survivors)

## The gap

ADR 0047 narrowed selection to the values no other value beats on every
axis. ADR 0051 reported the tie among the survivors, and stated plainly:

> ### This is not an ensemble

It is not, and it should not be. But the consequence is that a reader is now
told, correctly, that the evidence found several values equally credible —
and given no way to see what turns on it. Through the real resolution path:

```
170.7 1/s   immobiized recombinant enzyme, pH 7.0, 25°C   (returned)
276.5 1/s   soluble recombinant enzyme, pH 7.0, 25°C
```

Both from BRENDA reference 741355. A student receives 170.7 and a sentence
saying 276.5 was equally well evidenced. Whether a 1.6-fold spread matters
for *their* experiment is a question about the model, and every layer of
this system stopped one step short of asking it.

ADR 0051 says the reader is "equipped to make" that judgement. They are —
if they are shown the model under each value, which required running it.

## What was declined, and still is

Bakker's recommendation was to score parameters and use the scores as
**weights in sampling** an ensemble. ADR 0024 declined the ensemble:

> Sampling needs a distribution per parameter and a flux dataset to
> validate the resulting models against. A teaching lab has neither.
> Without the validation step, ensemble sampling produces spread with no
> reason to trust any part of it — which is worse than a single flagged
> value, because it *looks* like a rigorous uncertainty estimate.

Every word of that still holds, and this ADR does not weaken it. The
distinction is exact:

| Declined | Built here |
|---|---|
| Sample a distribution | Enumerate the observed values, and no others |
| Weight by reliability score | No weights — Bakker has not answered how she weighted hers |
| Report spread as uncertainty | Report spread as disagreement among sources |
| Reject at model level after flux validation | Nothing is rejected; nothing is validated against |

Running the model at a value nobody measured is the fabrication this project
exists to refuse, so no interpolation happens between candidates.
`test_it_runs_only_at_values_that_were_measured` pins it.

## Decision

`consequence_of(candidates, parameter=..., vmax=..., km=..., s0=...)` runs
the model once per candidate and reports the outcomes side by side, with the
selected one marked and each row carrying the commentary that produced it —
so a reader sees that one value came from an immobilised preparation and one
from soluble enzyme before deciding which to believe.

**The observable is `substrate remaining at t=end`**: a direct model output,
read off the final row. Half-conversion time is the more familiar teaching
quantity and is deliberately not used — it needs interpolation between time
points and a rule for trajectories that never reach half, and both are
judgements this module would be making on the reader's behalf.

The column is found by **name**, not index. `data[-1][1]` keeps returning a
number after a reorder and answers with the product instead of the
substrate.

### Three refusals

1. **A missing `vmax`, `km` or `s0` is `not_assessed`, naming it.** These
   are experimental settings, not properties of the enzyme. This is the
   refusal `reliabilityScore.ts` already makes for "physiological pH and
   T" — 7.4 and 37 °C describe a mammal and misdescribe *Thermus
   thermophilus*. A guessed `s0` would be worse than a mis-scored axis: it
   changes the trajectory the reader is shown while looking like a result.

2. **A kcat tie is refused.** `vmax = kcat · [E]` needs the assay's enzyme
   concentration, which BRENDA does not report. This is not a limitation
   worked around; it is the actual tie the module was built looking at, and
   it is answered with "supply that concentration" rather than by treating
   a turnover number as a rate.

3. **No aggregate.** No mean outcome, ever — the same refusal
   `reliabilityScore.ts` makes via `noAggregateReason`. A mean over values
   whose weights are unknown would be Bakker's unanswered weighting
   question, silently given an answer.

## Two defects found while building it

**Attempts are not results.** Two candidates that both failed to simulate
produced `status="assessed"`, two entries in `outcomes`, and
`is_assessed=True` — while the model had said nothing at all.
`len(outcomes) > 1` counted attempts. Found by running it, not by reasoning
about it. A comparison needs two *results*, and `status` and `is_assessed`
now derive from the same count so they cannot disagree.

**Computed and not delivered, in the delivery code.** The reason string was
built as `headline if ran else other + suffix`, which Python parses as
`headline if ran else (other + suffix)`. On the branch that matters, the
failure note and the "NOT an uncertainty estimate" disclaimer were both
dropped. Two tests caught it. The house defect, in three lines written to
prevent it.

## Consequences

- A candidate that cannot be simulated is **kept and named**. Dropping it
  would narrow the reported spread — the one direction this must never
  move in, since it would make the literature look more agreed than it is.
- Reachable: `scripts/report_spread_consequence.py`, spawned from
  `exportSpreadConsequence` in the CLI's export module.
  `check_scripts_reachable.py` refused the script until a non-test caller
  named it, which is the guard doing exactly what ADR 0107 asked of it.
- The TypeScript side forwards `vmax`/`km`/`s0` **undefined included**. The
  CLI usually has plausible values to hand, which makes filling one in the
  easy, helpful-looking mistake; a test asserts the refusal survives the
  boundary.
- Bakker's outstanding question — how the axes were weighted — is untouched
  and still open. Nothing here needs an answer to it, which is why it could
  be built while that remains unanswered.
