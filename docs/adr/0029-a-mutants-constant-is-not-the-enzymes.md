# ADR 0029: A point mutant's constant is not the enzyme's

**Status:** Accepted, implemented

**Date:** 2026-08-14

**Relates to:** ADR 0024 (cross-species is opt-in — this is the same rule
applied to the same failure), ADR 0010 (STRENDA assay conditions, which
parsed half of the string this reads), ADR 0012/0013, ADR 0026, ADR 0028

## Context

BRENDA's commentary cell carries more than assay conditions. The distinct
commentaries in this repository's own acetylcholinesterase turnover fixture
include:

```
"pH 8.0, 30°C, native enzyme"
"wild-type enzyme"
"Y124C mutant"
"F295A/Y337A mutant, pH 7, 22°C"
"pH 7.0, 25°C, mutant G122H/Y124Q/S125T"
"pH 8.5, 25°C, isozyme H4"
```

ADR 0010 taught the parser to mine that string for pH, temperature and
buffer. **Everything else in it was discarded** — including the part saying
the number was measured on a different protein.

### The numbers

| | |
|---|---|
| AChE turnover rows in the fixture | 72 |
| ...classified as variants | **35** |
| *Mus musculus* rows | 37 |
| ...classified as variants | **32** |
| lowest mutant kcat | 0.017 |
| lowest wild-type kcat | 0.2 |

Selection is `min(entries, key=km_value)`. Active-site substitutions are
chosen *because* they change the kinetics, so they populate the tail a
minimum reaches into — twelve times below the lowest wild-type value here.

It was luck, not design, that the fixtures did not already select a mutant
for the exact-match tier. They did on the cross-species tier: **the golden
set's G3 tuple — the hand-verified record of what the resolver *should*
return — had `pH 8.5, 25°C, isozyme H4` pinned as the expected answer at
0.0026 mM, and every test passed.** With variant rows excluded the same
query resolves to 10.73 mM. A factor of four thousand.

## This is the cross-species problem again

Lisa Jeske's objection to cross-species substitution was that the value is a
real, correctly parsed, correctly cited measurement **of something else**. A
Y337A mutant is a different protein in exactly that sense, and a sharper
case than a rabbit standing in for a human: nobody makes a rabbit in order
to change its Km.

ADR 0024 made cross-species opt-in. This applies the identical rule:

- variant rows are **excluded from selection** by default
- the refusal **names what it withheld**, so the opt-in is exercisable
- `allowVariants` re-admits them

## Decision

### Removed before selection, not flagged after it

The ordering is the whole point. Flagging afterwards would attach a warning
to a value that had already been chosen *for being* a mutant — the warning
would be true and the number would still be wrong.

### Four states, and `unstated` is the dangerous one

```
wild_type   the commentary says so
variant     mutant, a point-substitution code, or a named isozyme
unstated    the commentary says nothing either way
absent      there is no commentary at all
```

`unstated` is the majority of the corpus and **it is not wild-type**. BRENDA
does not require curators to write "wild-type" when the paper measured
wild-type, so silence is genuinely ambiguous.

`unstated` rows are therefore **usable but not certified**. Withholding them
would refuse most of the literature over an absence of words; treating them
as wild-type would quietly re-admit every unlabelled mutant. `is_wild_type`
is written `status == "wild_type"` and never `status != "variant"`, because
the negative form makes every unlabelled row certify itself.

**This is the limit of the check and it is stated rather than implied: an
unlabelled mutant still passes.** The fix for that is better BRENDA
commentary, not a more aggressive regex here.

### The verdict rides on found results, not only withheld ones

`KineticResult.variant` is populated whenever a value is returned, not just
when one is refused.

`unstated` is the majority case, and a reader who saw no variant field at
all would reasonably assume the row was the enzyme as found — which is the
assumption this whole mechanism exists to stop being made silently. Absence
of a warning is not the same as a statement, and only one of those is
something a reader can check.

### An isozyme is a variant, and is not a mutant

An isozyme is a distinct gene product, wild-type in its own right. It is
grouped with variants because LDH's H4 and M4 have genuinely different
kinetics and a request for "lactate dehydrogenase" did not ask for one of
them. The verdict carries `kind` so the two remain distinguishable.

### Recombinant expression is *not* a variant

A recombinant wild-type is the same sequence in a different host. It can
differ in glycosylation and folding, which is worth knowing, but it is not a
sequence change — and 28 fixture rows say "recombinant". Treating it as a
variant would withhold a large and legitimate part of the corpus. It is
reported on the verdict and never acted on.

### Why a lexicon here is not a hardcoded fact

`buffer_identity.py` goes to PubChem because *"Tris-HCl and Tris are one
buffer"* is a claim about the world that needs a source. *"The word 'mutant'
means this row is a mutant"* is a claim about English and about BRENDA's
writing conventions, and the source is the corpus quoted above.

The point-substitution regex is restricted to the twenty proteinogenic
one-letter codes with a 1–4 digit position, so `H4` (an isozyme name) and
`B12` do not match.

## Verification

`Tests/test_protein_variant.py` (41) — every string is real, taken from the
fixtures. `Tests/test_fallback_logic.py` (+4) and `Tests/test_golden_set.py`
(+2) cover selection. TypeScript: `variantWithheld.test.ts` (9) on the
thrown error, which is the only surface a user sees.

Eleven mutations. Nine caught immediately:

| Mutation | Failures |
|---|---|
| cross-species-tier filter never runs | 1 |
| `unstated` rows withheld too (over-aggressive) | 26 |
| `is_wild_type` becomes the negative test | 8 |
| `unstated` classified as `wild_type` | 9 |
| isozymes stop counting as variants | 3 |
| the withheld result stops naming what it withheld | 1 |
| the filter excludes everything | 18 |
| `variant_withheld` collapses into `not_found` | 6 |
| `allowVariants` stops being forwarded / defaults true | 2, 1 |

**One was not caught, and it is the finding worth keeping.** Disabling the
filter on the **exact-match** tier broke nothing — every test still passed.
The golden case exercised the cross-species tier, and no test reached the
other one. A filter no test can break is a filter someone removes as dead
code, and the day after that a mutant's constant is the enzyme's again.

`test_exact_tier_excludes_variant_rows_from_selection` closes it, using
*Mus musculus* (37 rows, 32 variants, all one organism so the exact tier
fires). With it, the mutation fails.

That is the third time in this project that a test claimed coverage of a
line it could not reach, and the third time only a mutation run revealed it.

### A tooling failure worth recording

The first mutation run backed up to `/tmp`, which is not writable in this
sandbox. `cp` failed, the harness ignored the exit status, and every
mutation after the first landed **on top of the previous one** — six results
were meaningless and the working tree was left mutated.

A mutation harness that cannot tell whether it restored is the same defect
class it exists to find. The harness now verifies the backup with `cmp`
before relying on it and aborts if the restore does not round-trip.

## Consequences

- `BRENDAKmEntry.variant`, `KineticResult.variant` and
  `KineticResult.variant_candidates_available` are new.
- `resolve_kinetic_value` gains `allow_variants` (default **False**).
- The wire gains `variant`, `variantCandidatesAvailable`, and accepts
  `allowVariants`.
- `ParameterProvenance.unresolvedReason` gains `"variant_withheld"`.
- Four exact-equality contract tests needed updating. They were right to
  fail.
- **The golden set changed.** G3 now carries `allow_variants: True` and a
  companion test asserts the default resolves to a different row. The golden
  value is still a true fact about BRENDA; what changed is that reaching an
  isozyme now requires asking.
- `allowVariants` is **not yet exposed over HTTP.** `allowCrossSpecies` and
  `physiologicalReference` are; this needs the same `openapi.yaml` +
  cache-key treatment (ADR 0027), and the zod/orval drift recorded there is
  still unresolved and still blocks a clean regeneration.

**Some queries that previously returned a value now refuse.** That is the
intended effect, and it is the second time this project has deliberately
reduced its own hit rate — the first was ADR 0024. A tool that answers more
questions by answering some of them wrongly is not more useful.

Concretely: the LDH fixture's previously-selected row is `isozyme H4`, so
LDH resolution changes behaviour where an isozyme was being returned
unlabelled.

## What this does not claim

Variant detection is not variant *understanding*. This knows that a row said
"Y124C" and nothing about what Y124C does. It removes measurements that
announce themselves as being of a different protein, and claims nothing
about the rest — including every unlabelled mutant in BRENDA.
