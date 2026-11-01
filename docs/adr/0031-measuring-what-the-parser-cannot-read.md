# ADR 0031: Measuring what the parser cannot read

**Status:** Accepted, implemented

**Date:** 2026-08-14

**Relates to:** ADR 0010 (STRENDA assay conditions), ADR 0024 (the
correspondence), ADR 0026 (coherence), ADR 0028 (buffer identity — **a claim
in it is corrected here**), ADR 0029 (protein variants)

## Context

BRENDA puts one free-text cell beside every kinetic value. Caterva mines it
for pH, temperature, buffer, and — since ADR 0029 — whether the row measured
a sequence variant. Everything else in that string is discarded.

Discarded *silently*, which is the problem. A parser that ignores text does
not report how much it ignored, so "we read the commentary" and "we read
two-thirds of the commentary" look identical from outside.

Two defects had already lived in that silence:

- **ADR 0029.** `"F295A/Y337A mutant"` sat in 35 of 72 rows of the AChE
  turnover fixture, unread, while selection took the minimum — and
  active-site substitutions sit in the tail a minimum reaches into.

- **ADR 0028** stated the fixtures contained no cofactor mentions. **They
  do.** Trypsin rows read `"in 10 mM Tris, 20 mM CaCl2, pH 7.4, at 37°C"`,
  and calcium is not incidental to trypsin. That claim came from a grep for
  NAD/NADH/Mg2+ that missed CaCl2 — a search that found nothing, reported as
  an absence. Corrected below.

Both were found by looking, not by any check. The point of this ADR is that
looking should not have been necessary.

## Decision

`scripts/check_commentary_coverage.py` removes from every commentary the
spans the pipeline's own extractors match, and reports what is left. The
leftovers are, precisely, what Caterva cannot read.

**Coverage at introduction: 73% of 263 commentaries fully understood.**

### The patterns are imported, not re-listed

Every regex the guard subtracts is imported from the module that uses it in
production — `assay_conditions._PH_RE`, `protein_variant._ISOZYME_RE`, and so
on. A guard that re-declared them would be a second source of truth for what
"understood" means, and would keep reporting full coverage after the real
parser regressed. That is the false-green shape catalogued in ADR 0024 and
again in ADR 0027, and this guard exists specifically to catch that class, so
it must not commit it.

The coupling is the feature: change an extractor's pattern and this number
moves with it.

### Zero rows is a failure, not perfection

If no fixture parses, the guard exits non-zero rather than reporting 100%.
Zero divided by zero is the most reassuring possible wrong answer, and a
guard whose denominator can silently vanish is the exact defect the endpoint
guard shipped with (ADR 0024's verification note).

### A baseline entry is a decision, not a mute button

`docs/commentary-residue-baseline.txt` records reviewed fragments, grouped
with the reasoning. **Four of its five groups are open findings, not
acceptances** — recorded so the guard can go green on a *reviewed* state
while the findings stay visible. The file says so at the top, because a
baseline read as "resolved" inverts its purpose.

## What it found immediately

### 1. Cofactors and allosteric effectors are in the corpus

~24 rows. `20 mM CaCl2` (trypsin). `NADH` concentration series. And most
sharply:

```
"...in the presence of fructose 1,6-bisphosphate"
"...in the absence of fructose 1,6-bisphosphate"
```

FBP is an allosteric activator of LDH. Those two rows are a **designed
contrast** — the values are *meant* to differ — and Caterva reads neither,
so it would treat them as two measurements of one thing and take the lower.

This is Jeske's fourth item, present and unread. ADR 0028's claim to the
contrary is withdrawn.

### 2. A concentration the buffer parser dropped

`_BUFFER_RE` matched `m[MK]` — "mM" and "mK" — but not a bare "M". So
`"0.5 M Tris-HCl buffer"` captured as `"Tris-HCl buffer"`.

The consequence was quiet and exact: `BufferIdentity.concentration_text`
exists (ADR 0028) so a reader can see that 0.5 M and 10 mM were treated as
the same buffer, and it was **empty for precisely the molar strings that
motivated it**. A disclosure mechanism, blind to the case it was written for.

Fixed; coverage rose 70% → 73%.

### 3. A double mutant the variant regex never saw

BRENDA writes `"D38SC81S"` — two substitutions, no separator. The
single-code pattern `\b[AA]\d{1,4}[AA]\b` misses it, because `\b` requires a
boundary between the S and the C and there is none. A row that says it is a
double mutant, classified `unstated`.

**ADR 0029's mutation-testing pass did not find this**, and that is the
lesson worth keeping:

> Every mutation asked whether the regex could be **broken**. None asked what
> it had **never matched**. Mutation testing proves a check can fail; it says
> nothing about a case the check never sees.

Fixed with `(?:[AA]\d{1,4}[AA])+`, with a test asserting the widening did not
widen the false positives (`isozyme H4`, `vitamin B12`, `LDH B` still do not
match).

### 4. Two axes of "measured on a different thing", still unbuilt

- **Isoform names given positionally.** `"LDH B"`, `"hexokinase Ia"` are
  distinct gene products; `classify()` returns `unstated`. Fixing it needs
  the enzyme's name as context — "B" is only an isoform designator next to
  "LDH" — which the classifier does not receive. Named rather than patched
  with a regex that would match a capital after any word.

- **Tissue and developmental provenance.** `"healthy breast tissue enzyme"`
  and `"breast cancer tissue enzyme"` are two LDH rows differing only in
  tissue source, with Km 10.73 and 21.78 — a factor of two. Not a sequence
  variant, so folding it into `protein_variant.py` would be wrong. It is a
  **third axis** alongside organism (ADR 0024) and sequence (ADR 0029), and
  it needs its own design.

## Consequences

- Coverage is now a number that can regress, in CI, rather than a property
  nobody measured.
- ADR 0028's cofactor claim is corrected. The correction is recorded here
  rather than edited into that file, so the mistake stays legible.
- Four open findings are on the record with their evidence, instead of being
  absent from it.
- The guard measures **fixtures**, not live BRENDA. A commentary form that
  appears only in the live corpus is still invisible. The fixtures are a
  sample, and the number is a claim about that sample.

## What this does not do

It does not read the commentary. It measures how much of it goes unread, and
the two are easy to confuse when the number goes up.

Nor does a high coverage figure mean the understood parts are understood
*correctly* — the buffer parser scored as "understood" for eight rows while
silently dropping their molarity. Coverage counts what was consumed, not
whether consuming it was right.
