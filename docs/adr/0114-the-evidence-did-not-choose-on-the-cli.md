# ADR 0114: The evidence did not choose, on the CLI

**Status:** Accepted, implemented

**Date:** 2026-08-17

**Context:** `src/literature/literatureResolver.ts`, `src/cli/commandResolve.ts`,
`Tests/fixtures/offline_runner/stub_literature_runner.py`

**Follows:** [ADR 0112](0112-the-input-where-the-refusals-fire.md), which
wired the guard that counted this. First of its 24 debts paid.

## Bakker's finding, on the front end that never said it

Barbara Bakker's advice was that a parameter's reliability should drive
which value gets used. `evidence_rank.py` implemented the half that needs no
weights: candidates are narrowed to the non-dominated frontier, where a row
is dropped only when another beats it on **every** axis. Among the
survivors nothing is beaten outright, so `min()` chooses — and that choice is
arbitrary. `selection_tie.py` exists to say so:

> Reporting the minimum silently presents literature disagreement as a
> measurement.

The API path has printed that since ADR 0051. **The CLI printed the number
alone.** On the LDH turnover table that means a student ran `scientific
resolve`, was handed `21.1`, and was not told the evidence had also ranked
`6467` equally credible — six rows, every one wild-type with pH and
temperature reported, spanning 306-fold.

The finding was computed, serialised, and emitted. `literatureResolver.ts`
did not read it.

## Found by the guard, not by luck

The two previous instances of this defect class were found by hand, and the
second only by accident (ADR 0106, ADR 0109).
`check_both_front_ends_read_it.py` counted **24** keys the runner emits that
one front end reads and the other does not. `selectionTie` was the
highest-value entry on that list, and it is the first paid off.

The count is now **22**: `fold_range` cleared with it, because it travels
inside the same object. A reminder that these entries are not independent
and the debt can drop by more than one per fix.

## What the student sees

```
⚠ The evidence did not choose this value.
  2 rows were ranked equally well evidenced, spanning 21.1 to 6467, a 306-fold range.
  2 rows were equally well evidenced … The value returned was chosen by
  taking the lowest, which the evidence does not justify.

  → 21.1 1/s  [ref 684519]  (returned)
        pH 6.0, 25C, recombinant wild-type enzyme, with FBP
    6467 1/s  [ref 761568]
        wild-type, presence of D-fructose-1,6-diphosphate
```

Printed high, beside the cross-species warning, because it is the same class
of caveat: something about the **answer** a reader would otherwise assume
away. A value shown alone reads as *the* value.

The alternatives are named with their reference ids and their commentary,
because *"a named alternative is checkable; a bare number is not"* — and the
commentary is what a reader needs to make the judgement the ranking declined
to make. `reason` is printed **verbatim**: rewording it in the client would
make this a second place the finding's wording can drift, and the Python
module is where it was argued over.

## Fewer than two candidates is not a tie

`parseSelectionTie` repeats the two-candidate check rather than trusting the
Python side, and drops candidates carrying no value. `SelectionTie()` with an
empty list is also what an unpopulated field looks like — which is exactly
why `selection_tie.py` makes `is_tied` a **positive** test — and a check on
mere presence would inherit the ambiguity it was written to remove.

A warning about nothing is worse than no warning: it teaches readers to skip
warnings, which this project can least afford given how many it prints.

## Mutations

| # | mutation | result |
|---|---|---|
| S1 | the tie dropped at the boundary (the original defect) | caught |
| S2 | parsed but never rendered | caught |
| S3 | a one-candidate "tie" announced as a tie | caught |
| S4 | the alternatives lose their reference ids | caught |

`python3 scripts/mutate.py --set docs/mutations/adr-0114-selection-tie-cli.json`

Run with `--only` one at a time: the two-file suite costs ~25s and a baseline
plus four mutations exceeds the sandbox ceiling. That flag exists for this
(ADR 0083) — it splits the run without splitting the record.

**Both files are in the test command**, and that is not padding. The
rendering test mocks the resolver, so it cannot see a parsing regression —
which is precisely how ADR 0109's first set produced two confident NOT
CAUGHTs. One file proves the CLI renders what it is handed; the other proves
anything hands it over.

## The stub runner learned to answer under any quantity

The tie fixture initially carried its value under `kcat` while being
requested as `kcat_tied`, and the resolver — which reads `parsed[quantity]` —
raised *"found=true but no usable value"*. Rather than work around it, the
stub now moves a `_value` key onto whatever quantity was asked for, which
keeps it honest about the contract it exists to exercise: the real runner
emits the value under the quantity's own name.

## Consequences

- One-sided debt: **24 → 22**.
- `ResolvedKinetic.selectionTie` and the `SelectionTie`/`TiedCandidate`
  types are new on the CLI side.
- Next on the list: `selectedForm` (which named form the value IS), then
  `column_taxon`/`commentary_taxon`, the only two read by **neither** front
  end.

## Related

- [ADR 0110](0110-the-finding-that-reached-half-the-users.md),
  [ADR 0112](0112-the-input-where-the-refusals-fire.md) — the guard that
  found it
- [ADR 0051](0051-the-evidence-did-not-choose-the-value.md) — the finding,
  and its first front end
- [ADR 0109](0109-the-second-front-end.md) — why a mocked test alone would
  have proved nothing
