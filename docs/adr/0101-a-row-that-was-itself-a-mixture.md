# ADR 0101: A row that was itself a mixture

**Status:** Accepted, implemented

**Date:** 2026-08-17

**Context:** `Tests/source_context.py`, `docs/commentary-residue-baseline.txt`,
ADR 0037 (a tissue is not an organism)

## How this was found

Not by a guard. By following a note I had written to myself.

`docs/commentary-residue-baseline.txt` records every BRENDA commentary
fragment Terrium cannot parse. Most entries are accepted with a reason. One
of the accepted ones read:

> `muscle` survives here as a bare token in a row whose phrasing ADR 0037's
> `from` pattern does not reach.

That is a true statement and a comfortable one. The word is read elsewhere,
the parser is imperfect, nothing is broken. It sat in the *accepted* tail,
which is to say the group nobody re-reads.

The row it refers to is:

```
Gallus gallus   16.0   "enzyme form heart and muscle"
```

**`form`, not `from`.** BRENDA's own typo. And `extract_source_claims` takes
the first token after `from` and stops.

## What that cost

ADR 0037 exists because a *Gallus gallus* LDH pool mixes heart and skeletal
muscle, whose values differ by a factor of 54, and reporting a single number
for "chicken" hides that. The mixture detector reports:

```
heart = 16.0-60.0, muscle = 1.1-3.3
```

The 16.0 is not a heart measurement. It is material pooled from *both*
tissues — the two whose divergence is ADR 0037's entire subject — and it was
being filed as a clean member of one side, widening the reported heart range
by nearly four-fold in the direction of the other tissue.

A row that is itself a mixture, sitting inside the mixture report, counted as
if it were unmixed. The detector was right that the pool was mixed and wrong
about how.

## Decision

`find_source_mixtures` runs a second pass over the claimed rows. A row is
reported as unattributable when its commentary names a source **that another
row in the same organism states outright**.

The pool is the vocabulary. That is the load-bearing choice.

Two alternatives were tried and rejected against the corpus:

- **Read the word after `and`.** `_classify_token` returns `"source"` for
  everything it does not recognise as an organism — `stored`, `purified`,
  `pH` and `25` all classify as sources. This invents claims. Measured, not
  assumed: those four tokens are real corpus fragments.
- **A tissue list.** `{heart, muscle, liver, kidney, ...}` works today and
  fails silently on the first tissue nobody thought of, which is the failure
  mode this project treats as worse than no check at all.

Using the pool means `muscle` counts on the 16.0 row **because another row in
the same organism says `enzyme from muscle`** — evidence from the data rather
than a guess, and no list to maintain. It is deliberately conservative: a
source named only on the ambiguous row is not read, because nothing
corroborates it.

The pooled row is then counted under *each* source it names, and the report
says so:

> One or more rows name SEVERAL of these sources at once and cannot be
> attributed to any single one: 16.0 (commentary names heart and muscle).
> Such a row is counted under each source it names, so the ranges above
> overlap by construction.

Overlapping ranges are the honest output. Silently assigning the row to one
side produced two clean ranges, and one of them was wrong.

## The mistake worth recording

The reason sentence above — *"counted under each source it names"* — was
written **before the code did it**. My first implementation recorded the fact
for the sentence and never added the value to the second group. The prose was
false against the code beneath it.

It was caught because the test was written from what the change is *for*
rather than from what the code does. That is now the second occurrence this
session of documentation asserting unimplemented behaviour (ADR 0081 was the
first, where the ADR described a filter the code did not have), and both were
caught the same way. Neither was caught by a guard.

## Consequences

- The *Gallus gallus* heart range narrows to the rows that are actually
  heart, and the ambiguous row is named rather than absorbed.
- Rows whose only source token is uncorroborated stay unread. The residue
  baseline keeps `muscle` in its tail for that reason — the token is still
  not parsed as a claim in its own right; what changed is that the row is no
  longer misattributed.
- The residue baseline's accepted tail is now known to be capable of hiding a
  live defect. It is a record of what was looked at, not of what is harmless,
  and this is the first demonstration that the distinction has teeth.
