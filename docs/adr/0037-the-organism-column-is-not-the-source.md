# ADR 0037: The organism column is not the source

**Status:** Accepted, implemented

**Date:** 2026-08-14

**Relates to:** ADR 0024 (cross-species opt-in — **this finds a way around
it**), ADR 0031 (coverage guard, which recorded this as the last open
finding), ADR 0033 / 0035 (pool-level detection, same shape)

## Context

ADR 0031's coverage guard left three groups of unread commentary. Two are now
read — effectors (ADR 0032) and named forms (ADR 0035). This is the third,
and it holds the sharpest finding of the set.

BRENDA names the biological source in prose:

```
"enzyme from heart"
"enzyme from muscle"
"enzyme from adult" / "from pupa" / "from larva"
"healthy breast tissue enzyme"
"breast cancer tissue enzyme"
"from human"          <- on a row whose ORGANISM COLUMN says Drosophila
```

## Two findings

### 1. The commentary contradicts the organism column

Three acetylcholinesterase turnover rows carry
`organism = "Drosophila melanogaster"` while the commentary says the enzyme
came `from human` (6670) and `from eel` (13700).

This matters more than it first appears. ADR 0024 made cross-species
substitution opt-in on Lisa Jeske's recommendation, and **the entire gate
reads the organism column**. A row whose column says Drosophila and whose
commentary says human passes that gate as a Drosophila measurement. The
protection is intact and the data walks around it.

Four ADRs went into making sure a rabbit's Km is not offered as a human's.
None of them looked at whether the column was telling the truth.

### 2. Tissue changes the value more than species does

Within one organism, in the LDH turnover table:

| | |
|---|---|
| *Gallus gallus*, heart | 60.0 |
| *Gallus gallus*, muscle | 1.1 – 3.3 |

*Bactrocera dorsalis* spans 587 (adult), 1079 (pupa) and 1820 (larva) the
same way, and the human LDH Km rows differ by a factor of two between
healthy and cancerous breast tissue.

> **Correction (ADR 0039).** This section first said "a factor of
> fifty-four, and `min()` takes 1.1". That span is real **across the whole
> table** and overstates what happens on the resolution path, because
> substrate filtering runs first and 60.0 and 1.1 are different substrates.
>
> The claim was checked by running the real resolver, and the competing pool
> is `(Gallus gallus, NAD+)`: **muscle 3.3 against heart 60.0, eighteen
> fold, and the resolver does return 3.3.** The finding holds; the number
> and the substrate were wrong.
>
> Recorded here rather than edited away. A figure measured across a table
> and reported as if measured on a code path is exactly the kind of
> true-sounding wrong claim this project treats as a defect.

Every one of these rows **is** the organism that was asked for. The
cross-species gate cannot see any of it.

## Decision

`source_context.py` extracts what the commentary says the enzyme came from,
and reports two things: rows whose named organism contradicts their column,
and organisms measured from several sources within one candidate pool.

### Organism and tissue are told apart by NCBI, not by a list

`"from human"` and `"from heart"` are the same shape. Distinguishing them
means knowing one is an organism and the other an anatomical part.

The authority answers it: a token that **resolves to an NCBI taxon** is an
organism claim; one that does not is a source claim. The same move
`form_mixture.py` makes by asking PubChem whether "NAD" is a compound, and
for the same reason — a hardcoded tissue vocabulary would be unsourced
biology in a file nobody reviews as biology.

### A second taxon lookup, and why it is acceptable here

`enzyme_lookup.fetch_taxon_id` restricts its search to `[Scientific Name]`
deliberately: BRENDA's organism *column* is binomial, and an unrestricted
search risks resolving an ambiguous string to the wrong taxon.

Commentary is prose and says "human", not "Homo sapiens", so this module
needs an unrestricted lookup and inherits the ambiguity the other function
avoids. That is acceptable **here** and would not be acceptable there,
because the output is a discrepancy to check rather than a value to use: a
spuriously resolved token produces a flag a reader dismisses, where a
spuriously resolved organism would produce a number they trust.

### A genus is not a contradiction of its own species

`"from Drosophila"` on a `Drosophila melanogaster` row is agreement written
less precisely. NCBI gives them different taxon ids (7215 and 7227), so an id
comparison alone flags every such row — and BRENDA writes them constantly.

Compared on leading word tokens rather than by fetching two lineages, because
this is a question about the *names*. **Limitation, stated rather than
discovered later:** it does not catch `"D. melanogaster"`, and it does not
catch a common name denoting the same clade. Both would be reported — a flag
a reader dismisses, the safe direction.

### Mixtures are grouped BY organism

Heart in a chicken and muscle in a duck is two ordinary cross-species rows,
already governed by ADR 0024. Grouping across organisms would report that
gate's normal operation as a finding, and the warning would fire on every
multi-species pool. Within one species it is a difference the gate cannot
see, and here it is fifty-four fold.

### Reported, not withheld

Consistent with ADR 0033 and 0035. Deciding which tissue the user wanted is
the user's call, and Caterva cannot tell which side of an organism
contradiction is the error.

## Verification

`test_source_context.py`, 26 tests. **Seven mutations, all caught first
time** — the first pass in several ADRs where none needed a test written
before it could fail:

| Mutation | Failures |
|---|---|
| an unresolved token is called a source | 1 |
| genus/species refinement treated as a contradiction | 1 |
| mixtures grouped across organisms | 5 |
| one source counts as a mixture | 2 |
| a discrepancy claimed when the column organism does not resolve | 1 |
| the disease state dropped from the label | 1 |
| the reason stops naming the values | 1 |

### Two bugs the tests found while being written

- **`fro?m` does not match "form".** The corpus contains `"enzyme form heart
  and muscle"` — a curator's transposition. `fro?m` matches "from" and "frm";
  the letters are transposed, not dropped. Found only because the test named
  the real corpus string instead of an imagined one.
- **Genus/species false positive.** Caught by the test asserting that the
  *matching* row is not flagged — the counterpart written to stop the main
  test passing because everything was flagged.

Both argue the same thing: tests written from the corpus, and a
counterpart-test for every positive one.

## Consequences

- `KineticResult.organism_discrepancies` and `.source_mixtures` are new.
- The resolver logs both before selection.
- ADR 0024's cross-species machinery is unchanged. This does not fix the
  gate; it reports when the gate's input is suspect, which is the honest
  thing available without deciding which of two sources is wrong.

## What this does not claim

A discrepancy is not proof the row is wrong — it is proof that two fields
disagree, and Caterva cannot tell which is the error. The row may describe a
human enzyme expressed in Drosophila, which is a real and common experiment
that BRENDA has no column for.

A source mixture is a fact about the candidate pool. Sources may differ in
assay conditions too, and `fold_difference` is the span a reader is asked to
look at, not an effect size.

And the module only sees sources a curator wrote down. An enzyme purified
from heart, with no commentary saying so, is invisible here and stays
invisible.
