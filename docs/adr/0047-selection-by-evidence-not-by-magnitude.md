# ADR 0047: Selection by evidence, not by magnitude

**Status:** Accepted, implemented

**Date:** 2026-08-14

**Relates to:** ADR 0024 Decision 3 (Bakker's axes — adopted, then unused),
ADR 0010 (STRENDA conditions), ADR 0029 (the variant filter that runs
first), and the tie-reporting built on this one

## Context

Barbara Bakker, asked how to handle values with missing assay conditions,
described what her group does:

> We gave each parameter a score based on its reliability and applicability,
> such as physiological pH and T, species […] and completeness of assay
> description. **These scores were then used to give the parameter a weight
> in the sampling.**

ADR 0024 Decision 3 adopted the scoring. `Tests/reliability.py` computes it,
the runner emits it, the API returns it, the CLI prints it.

**Nothing used it to choose.** `fallback_logic.py` contained no reference to
reliability at all. After every filter this project has added — implausible
rows, cross-species gating, taxonomic relatedness, protein variants — the
final selection among survivors was:

```python
best = min(entries, key=lambda e: e.km_value)
```

Take the smallest number.

### That is not a neutral tie-break

It is anti-correlated with evidence quality. A poorly-described measurement
is more likely to sit in the tail of the distribution, and a minimum seeks
the tail. The filters removed *categories* of bad row; nothing stopped the
final pick from landing on the worst-evidenced survivor.

Measured on this repository's own fixture — human lactate dehydrogenase,
after ADR 0029's variant filter leaves seven rows:

| value | STRENDA | commentary |
|---|---|---|
| **0.03** | **incomplete** | **none at all** ← `min()` picked this |
| 0.045 | **complete** | `inhibition assay, pH 7.4, 37°C` |
| 0.398 | incomplete | none at all |
| 0.5 | incomplete | `pH 8.0, temperature not specified…` |

The resolver discarded **the only row in the pool meeting the reporting
standard this project is built on**, for one where BRENDA reported nothing
whatsoever about the measurement, because `0.03 < 0.045`.

The score that would have said so was computed, emitted, and displayed to the
reader — and ignored by the one decision it exists to inform. The same
"computed and never delivered" shape as ADR 0027 and ADR 0039, except here
it *is* delivered; it just changes nothing.

## Decision

`Tests/evidence_rank.py` narrows candidates to the **non-dominated set**
before the tie-break runs.

Row A dominates row B when A is at least as good as B on *every* axis and
strictly better on at least one. Dominated rows are discarded.

### Why dominance and not a weighted score

The obvious implementation sums the axes and sorts. That needs weights: how
much is a complete assay description worth against an exact organism match?

**Bakker was asked and has not answered.** `reliabilityScore.ts` already
refuses to produce a total for exactly this reason (ADR 0024, Decision 3) —
inventing the weights here while refusing them there would be incoherent, and
the invented number would govern which value a student sees.

Dominance needs no weights. "A beats B on every axis" is a fact about the two
rows, not a judgement about their relative importance.

### The axes

Each is a total order requiring no calibration against the others:

| axis | order | why |
|---|---|---|
| assay completeness | complete > partial > absent | STRENDA requires pH and temperature (ADR 0010); a row with neither is a number without an experiment |
| variant statement | wild_type > unstated > absent | a curator writing "wild-type" is strictly more informative than silence, and silence than no commentary at all |
| relatedness depth | deeper shared rank > shallower | `taxonomy.RANK_ORDER` already orders these; ADR 0024 used it as a threshold and discarded the degree |
| organism match | exact > cross-species = not assessed | ADR 0024's gate refuses distant organisms; this orders what survives. An unasked question shares an ordinal with a known mismatch, so it can neither beat nor lose to a fact |

The ordinals are **ordinal**. The gaps between them mean nothing, and a test
asserts the module never sums them — because summing is precisely how the
invented weighting would arrive, and it would look like a refactor.

None of the axes compares a *value* to another value. This ranks evidence,
and a number is not evidence about itself.

### What stays arbitrary, and where it went

Among the non-dominated frontier no row is beaten outright, and something
must still choose. That remains `min()`, and it remains arbitrary.

The arbitrariness has been *confined*: it can no longer pick a row that
another row beats on every axis. It has not been eliminated, and this ADR
does not claim otherwise.

**A concurrent agent read that admission and built on it.** `selection_tie.py`
surfaces the tie to the user, on the grounds that saying so in a docstring is
not saying so to a student — on the LDH turnover table six non-dominated rows
span 21.1 to 6467, and the response previously showed one number with no
indication the evidence found the other five equally credible. That is the
right criticism of this ADR and the right response to it.

## Verification

`Tests/test_evidence_rank.py` (30). Six mutations on the ranking, all
caught:

| Mutation | Failures |
|---|---|
| dominance loses its strictness requirement | 3 |
| the frontier narrows nothing | 4 |
| the completeness axis collapses | 3 |
| the variant-statement axis collapses | 2 |
| a single-row pool returns empty | 1 |
| discards stop naming what beat them | 1 |

Two tests exist specifically to catch a plausible wrong implementation:

- **`test_the_frontier_does_not_simply_prefer_larger_numbers`** — the LDH
  case alone would pass if `frontier` were `max()` in disguise, because there
  the better-evidenced row is also the larger one. So a second case is
  constructed where the best-evidenced row is the *smallest*, and a bias in
  either direction fails.
- **`test_identical_profiles_do_not_dominate_each_other`** — without the
  `!=` guard, dominance returns True both ways, the frontier empties, and the
  resolver reports nothing found for a system that had candidates.

### A test whose premise this change killed

`test_exact_tier_excludes_variant_rows_from_selection` (ADR 0029) asserted
that excluding variants *changes the returned value*. It no longer does: the
frontier ranks a `wild_type` commentary above a `variant` one on its own, so
both paths converge on the same row.

Rewritten rather than deleted. Two mechanisms agreeing is not one of them
being unnecessary — the frontier prefers wild-type only when nothing beats
that row on another axis, and the ADR 0029 filter is what *guarantees* a
variant is never returned by default. The test now asserts the property (the
returned row is not a variant, and the exclusion reached the log) rather than
a difference in outcome.

### The organism axis shipped dead

The third axis originally read `entry._organism_exact` — **an attribute
nothing anywhere sets.** It was the constant `True`.

On the exact-match tier that was right by accident: every row there *is* an
exact match. On the cross-species tier, the only tier where organism varies,
it discriminated nothing and did something worse — `profile().summary` wrote
**"organism exact"** into the search log for rows measured in a different
organism than the caller asked about. A false line in the audit trail is
worse than a missing one, and this project treats that as the defect class
above all others.

The row does not know what was requested; the caller does. `profile()`,
`frontier()` and `describe_discards()` now take `requested_organism` as an
argument, and the axis has three states — `exact`, `cross_species`,
`not_assessed`.

`not_assessed` shares an ordinal with `cross_species` rather than getting its
own rank. When the requested organism is unknown every row scores identically
and the axis drops out of the comparison, which is the honest behaviour for a
question nobody asked.

**That ordinal choice was itself untested.** Raising `not_assessed` above
`cross_species` passed every test in the file, because the only test covering
it compared two `not_assessed` rows against each other — they tie either way.
The mixed case is reachable: a row whose own organism cell is blank is
`not_assessed` even when the request is known, and under the mutation it
would have outranked a row naming *Homo sapiens*. Silence beating a fact.
`test_a_row_with_no_organism_does_not_outrank_one_that_names_a_different_organism`
closes it.

Four more mutations, three caught immediately and one after that test was
added:

| Mutation | Failures |
|---|---|
| the axis reads the magic attribute again (*the original defect*) | 5 |
| `not_assessed` outranks `cross_species` | 0, then 1 |
| the organism comparison becomes case-sensitive | 3 |
| the summary always says "exact" | 3 |

### Relatedness was a gate, and the degree behind it was thrown away

ADR 0024 asks `assess_relatedness` one question — *shares a class?* — and
refuses anything that does not. Everything surviving that gate was then
treated as equally related.

Measured against the fixture lineages, for a *Mus musculus* query:

| candidate | shared rank | depth |
|---|---|---|
| *Homo sapiens* | superorder (Euarchontoglires) | 10 |
| *Sus scrofa* | class (Mammalia) | 7 |

Both pass. Selection ranked them level. `taxonomy.py` had already computed
which was closer, `RANK_ORDER` already ordered the ranks, and the gate threw
the number away after comparing it to a threshold. The same shape as the
score itself: computed, and not used by the decision it exists to inform.

Relatedness depth is now a fourth axis, using the project's own existing rank
ordering — so no ordering is invented here either.

#### Correction: that worked example does not happen, and the axis fires on nothing

**The table above was measured by calling `assess_relatedness` directly, not
by running the resolver.** Measured afterwards through
`resolve_kinetic_value`, both of its claims fail:

1. **The pair never meets.** On the mouse LDH query both depths *do* pass the
   gate — the search log shows `Sus scrofa … close_enough (shared class
   Mammalia)` alongside the human rows. But ADR 0029's variant filter removes
   the *Sus scrofa* row (`isozyme H4`) before selection runs, so the pool
   reaching `frontier` is single-organism. Across every cross-species query
   in the corpus, **every pool that reaches the frontier has one depth**, and
   the axis drops out of every comparison.

2. **Even hand-built, depth does not break the tie.** Constructing the pool
   the table describes, from the real fixture rows:

   | candidate | assay | depth |
   |---|---|---|
   | *Homo sapiens* | pH 8.0, no temperature → **partial** | **10** |
   | *Sus scrofa* | pH 8.5, 25 °C → **complete** | 7 |

   The closer organism is the worse-described measurement. Each beats the
   other on an axis, neither dominates, and both stay on the frontier. The
   ADR's "selection ranked them level" is what dominance *should* do here —
   adding depth does not change it and was never going to.

   A weighted score would have picked one, by inventing the exchange rate
   between "better described" and "more closely related" that Bakker was
   asked for and has not supplied. That this pair is *unrankable* is the
   honest answer, not a gap.

So the fourth axis is correct, tested, and **reaches no current fixture.**
This is stated rather than quietly dropped, following the precedent set for
`selectedForm` — null in every fixture today, pinned by a test so a BRENDA
update that changes it fails loudly. Two tests hold it:

- `test_depth_does_not_break_the_tie_the_adr_said_it_would` — runs the ADR's
  own example on real parsed rows and asserts both survive, so a future
  change that "fixes" it into a ranking fails.
- `test_no_fixture_pool_reaches_the_frontier_with_two_different_depths` — a
  canary that wraps `evidence_rank.frontier` and inspects the pools the
  resolver actually passes it.

**The canary's first version was wrong in the same way this section is
correcting.** It asserted on `result.relatedness` — the gate's verdicts —
and failed immediately, because two depths do pass the gate; the row
carrying the second one is filtered out afterwards. It was measuring a copy
of the pool rather than the pool. That is the third instance this session of
a verification artifact checking something adjacent to the thing it names,
and the first one caught by the test failing rather than by mutation.

This correction is written into the ADR rather than the ADR being edited to
match, for the reason ADR 0035's retraction gives: a claim measured off the
real path and a claim measured off a reconstruction are different claims,
and the record should show which one was made.

### `None` means incomparable, not zero

A row whose lineage could not be resolved has **no** depth. Scoring that as
zero would make a failed lookup lose to a row that merely shares a class —
turning an outage into evidence about biology.

So `dominates` skips any axis where either side is `None`, requiring
`>=` across the comparable axes and a strict win on at least one. When no
axis is comparable, nothing dominates.

Four more mutations, three caught immediately:

| Mutation | Failures |
|---|---|
| `None` depth scored as 0 | 1 |
| the depth axis is never populated | 4 |
| dominance drops its strict-win requirement | 8 |
| incomparable axes are compared anyway | 15 |

And on the two tests pinning the axis's reach:

| Mutation | Failures |
|---|---|
| the depth axis is never populated | 5 |
| the completeness axis collapses | 4 |
| the cross-species variant filter is disabled | 1 (the canary) |

The last one is the scenario the canary exists for: with the ADR 0029 filter
off, the *Sus scrofa* row survives to the frontier, a second depth appears in
a real pool, and the canary fires — naming the golden values to re-verify.

### A second unreachable branch, and a second test that claimed to cover it

`if not pairs: return False` guards the all-incomparable case. Mutating it to
`return True` **passed all 29 tests.**

The test meant to cover it built two profiles differing only in
`relatedness_depth=None` — but the other three axes always produce a value,
so `pairs` was never empty and the branch never ran. Unreachable defensive
code with a test asserting it worked.

It now forces every axis to `None` so the branch executes, paired with a
counterpart asserting a partially-comparable pair still ranks — because a
`dominates` that always returned `False` would otherwise pass the first.

That is the second time in this ADR alone, and the fourth this session, that
a test of mine claimed coverage of a line it could not reach. Every one was
found by mutation and none by reading.

## Consequences

- `Tests/evidence_rank.py` is new; `fallback_logic.py` routes both the
  exact-match and cross-species tiers through `_best_evidenced`.
- Discarded rows are named in the search log with what beat them. A selection
  that narrowed the pool silently is indistinguishable from a pool that never
  held the row.
- **Existing golden values can change.** They did not here — the frontier
  changes the LDH *human* selection, which no golden tuple pins — but any
  future golden that encodes a `min()` outcome should be re-verified rather
  than adjusted to match.
- This does not implement Bakker's sampling. It implements the half that
  needs no weights. The ensemble remains declined (ADR 0024, Decision 3) for
  the stated reason: a teaching lab has no flux data to validate an ensemble
  against.
