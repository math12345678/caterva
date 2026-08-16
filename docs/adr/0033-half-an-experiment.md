# ADR 0033: Reporting half an experiment

**Status:** Accepted, implemented

**Date:** 2026-08-14

**Relates to:** ADR 0032 (cofactors and the presence/absence pair — this
builds directly on it), ADR 0026 (coherence across a set), ADR 0029 (protein
variants), ADR 0031 (commentary coverage, which surfaced this)

## Context

ADR 0032 taught Terrium to read what an assay contained: which compounds,
present or absent, resolved to a PubChem identity. It answers a question
about **one row**, and compares **two rows** against each other.

There is a third question neither can reach.

The LDH turnover table contains these four rows, from one paper, at the same
pH 6.0 and 25 °C:

```
  21.1   recombinant wild-type enzyme  IN PRESENCE of fructose 1,6-bisphosphate
 327.2   recombinant wild-type enzyme  IN ABSENCE  of fructose 1,6-bisphosphate
 178.4   recombinant mutant D38R       IN PRESENCE of fructose 1,6-bisphosphate
 194.9   recombinant mutant D38R       IN ABSENCE  of fructose 1,6-bisphosphate
```

That is a controlled experiment. The authors measured with and without an
allosteric activator deliberately, and the wild-type arms differ by a factor
of **15.5** — larger than the twelvefold mutant span that motivated ADR 0029.

Terrium selects `min()`. It takes 21.1 — the activated arm — and reports it
as the enzyme's turnover number, with a real citation, having no idea it
picked one side of a comparison whose other side sat in the same pool.

**Every individual row here is perfectly well-formed.** Each has a value, a
citation, assay conditions, and now an effector profile. Per-row extraction
cannot see the problem by construction, and neither can a pairwise
comparison unless something already suspected which pair to compare. The
defect is in the *set* — the same structural point as ADR 0026, arriving
through a different door.

## Decision

`effector_presence.find_contrasts(rows)` takes the candidate pool the
resolver is about to minimise over, and reports every compound that appears
as **present in some rows and absent in others**.

### It decides one thing, and it is not a biochemical claim

The pool contains both arms. That requires knowing nothing about fructose
1,6-bisphosphate except that a curator wrote "presence" beside one row and
"absence" beside another.

It does **not** decide which arm is right, and it does not withhold. Choosing
would mean separating "allosteric effector someone added" from "cosubstrate
the reaction requires" — a claim about each enzyme's mechanism that Terrium
has no source for. ADR 0032 makes the same point about the NADH rows in this
corpus, where "present" describes the assay working as intended.

### Extraction is not duplicated

This module calls `effector.extract_effectors` and
`effector.resolve_effectors`. Compound identity therefore comes from the same
PubChem parent-CID matching, which is why `"fructose 1,6-bisphosphate"` pairs
with `"D-fructose-1,6-diphosphate"`.

**It was briefly a second implementation.** The first draft of this module
carried its own regexes and its own string-normalisation heuristic for
compound names, written in parallel with `effector.py` by two agents on the
same tree, neither aware of the other. That is exactly what ADR 0027 was
written about, and it was rewritten to sit on top rather than beside.

The heuristic that went with it is worth noting as a loss avoided: it
compared compound names by stripping stereochemistry prefixes and the bis/di
distinction with a regex. PubChem's parent CID does the same job with a
source.

### `unstated` is not `absent`

Most papers do not enumerate what they did not add. Reading silence as
absence would pair every unlabelled row in the pool with every "presence of
X" row, and the warning would fire constantly and be ignored — the
false-positive direction, and the one ADR 0028 was careful about for buffers.

### The magnitude is reported, and is not an effect size

`fold_difference` is the ratio of the extremes across both arms. It is the
size of the thing a reader is being asked to look at, **not** a claim that
the compound caused it: in the rows above, the arms differ in genotype as
well. Saying so in the docstring matters, because a number labelled
"fold difference" beside a compound name reads as an effect size to anyone
skimming.

## Verification

`test_effector_presence.py`, 11 tests. Five mutations, all caught after the
sixth was made catchable:

| Mutation | Failures |
|---|---|
| identity ignored, compounds compared by raw text | 1 |
| intersection becomes union (one arm reported as a contrast) | 4 |
| the reason stops naming the values | 1 |
| fold difference always None | 2 |
| `unstated` counted as `absent` | **0 → 1** |

### A filter that could not fail, again

The `unstated` mutation initially changed nothing. `effector._presence_of`
returns only `"present"` or `"absent"` — the third state its own
`Effector.presence` docstring promises is never produced today — so the
filter was unreachable and the mutation was a no-op.

An unreachable filter is one somebody deletes as dead code, and the day after
that a future extractor emits `unstated` and every silent row pairs with
every "presence of X" row. **This is the third time in this codebase:** ADR
0026's origin filter and ADR 0031's coverage of never-matched input were the
first two.

It is now tested by construction, with the state the type permits and the
extractor does not yet emit. With that test, the mutation fails.

The pattern is worth naming because it keeps recurring in a new disguise:
**mutation testing proves a check can fail on the inputs it receives. It says
nothing about inputs it never receives, and a guard's most dangerous state is
one no current caller can produce.**

## Consequences

- `KineticResult.effector_contrasts` is new, populated on **found** results
  rather than withheld ones: the point is that a value was returned while
  its counterpart sat unmentioned in the same pool.
- The resolver logs contrasts before selection, so the search log records
  that both arms were seen.
- Commentary coverage rose to **79%** once ADR 0032's extractors were
  registered with the ADR 0031 guard.
- `Effector.presence` documents three states and can produce two. Left as
  found — narrowing the type is `effector.py`'s call, not this module's — but
  recorded here so the discrepancy is not discovered a third time.

## What this does not claim

A contrast is a fact about the candidate pool, not about the enzyme. Two
arms may differ for reasons the commentary never stated, and the absence of
a detected contrast means only that no curator wrote "absence of" — not that
the values are comparable.

It also only sees pairs BRENDA labelled. An experiment run with and without
an effector, where the curator recorded only the conditions and not the
contrast, is invisible here and will stay invisible.
