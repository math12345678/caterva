# ADR 0052: Say when the form-mixture warning already came true

**Status:** Accepted

**Date:** 2026-08-14

**Related:** ADR 0035 (form mixtures), ADR 0029 (variants), ADR 0039 (pool
findings crossing the boundary), ADR 0046 (the boundary guard), ADR 0051
(selection ties)

## The gap

`Tests/form_mixture.py` (ADR 0035, written by a concurrent agent) detects when
one candidate pool holds several *forms* of the same enzyme — hexokinase I, Ia,
Ib; LDH-1, LDH-2, LDHB — and attaches a `FormMixture` whose reason ends:

> Returning the lowest would pick a form rather than answer the question.

That sentence is a conditional. It says what *would* happen. Nothing anywhere
said whether it *did*. A reader holding a Km of 0.5 mM and a warning that some
value in the pool belongs to hexokinase I cannot tell whether the number in
their hand is that value.

This is Jeske's objection one level up. She warned that mixing rows measured
under different conditions produces "fantasy numbers." A form mixture is the
same failure with the enzyme rather than the buffer: hexokinase I and hexokinase
IV are different proteins with different kinetics, and averaging or minimising
across them answers a question nobody asked.

## Decision

`name_selected_form(mixtures, selected_value)` returns a `SelectedForm` naming
which form the returned value *is*, or `None` when it is not one of them.

It is deliberately narrow:

- **A value appearing under two forms yields `None`.** Two forms reporting the
  same number is a coincidence the data cannot resolve. Naming one would invent
  the distinction the module exists to preserve.
- **A value from no named form yields `None`.** That is the outcome the warning
  hoped for; reporting it would invert the finding.
- **Siblings are listed by name**, so "one of three forms" is checkable rather
  than asserted.

The field is wired end to end: `KineticResult.selected_form` →
`"selectedForm"` on the wire → `ScienceAgentResult.selectedForm` →
`selectedFormFlags()` in `queryResolver.ts` → `provenance.flags`.

`selectedFormFlags` is a **separate flag** from the existing pool-findings
mixture warning rather than a merged sentence. The mixture is a fact about the
pool and is worth saying whichever row won; this is a fact about the answer.
Merging them would make the stronger claim disappear into the weaker one.

## What the corpus test established, and it is not what I expected

I wrote `test_selected_form.py`'s corpus test to prove that the pipeline's
`min()` returns hexokinase I (0.5 mM) out of a pool of three forms — the defect,
caught in the act.

**It does not.** The raw minimum is 2.3e-07, from a row carrying no designator,
and the full pipeline selects that same row. The LDH turnover pool behaves the
same way: LDHB sits at 142 s⁻¹ and the pipeline returns 21.1.

So the defect this function was built for does not currently manifest. The
claim I built it on was wrong, and the test is what found that.

The test now asserts the true state — `found is None` for both pools — with a
message that says, if it ever fails, that the defect has *started* manifesting
and the finding should be surfaced rather than the test relaxed. It also asserts
`checked`, so a fixture rename cannot make it vacuously green.

What survives is ADR 0029's argument: this is luck, not design. Nothing in the
resolver prefers undesignated rows. A BRENDA update that shifts one number turns
the good outcome into the bad one silently. Now it fails loudly.

## A withheld design, and why

I considered withholding form-designated rows from selection outright, the way
variants are withheld under ADR 0029. I measured the current behaviour first:

```
variant    -> WITHHELD from selection  | pH 8.5, 25°C, isozyme H4
unstated   -> selectable               | LDHB, in the presence of 0.125 mM NADH
unstated   -> selectable               | ... LDH-1, with 3 mM fructose-1,6-bisP
wild_type  -> selectable               | ... wild-type LDH-2, with 3 mM ...
```

Whether a form is withheld today depends on how the commentary happens to be
spelled, which is not a principle.

I did not implement the withholding, because `extract_forms` over-matches:
`"Y124C-SO3- mutant"` yields a form `SO/3`. The `_is_compound()` PubChem filter
that catches that returns `False` when the network is unavailable — which it is
in this sandbox, and may be in a classroom. Withholding on an over-matching
detector whose corrective filter fails open would drop real rows for a reason
nobody could see. Reporting is safe in a way that withholding is not.

## Verification

Re-derivable as a set file — `docs/mutations/adr-0052-selected-form.json`:

```
python3 scripts/mutate.py --set docs/mutations/adr-0052-selected-form.json
```

All five come back `caught` under the harness. Original run:

Five mutations to `name_selected_form`, each caught by
`Tests/test_selected_form.py` (10 tests, 10 passing at baseline and after
restore, file verified byte-identical with `cmp`):

| Mutation | Caught |
| --- | --- |
| A value under two forms names one anyway | 1 failed |
| A value from no named form is reported anyway | 4 failed |
| The reason drops "not hypothetical" | 1 failed |
| Siblings not listed | 1 failed |
| A one-form mixture claims a sibling gene product | 1 failed |

Both boundary guards pass: `check_runner_boundary.py` (25/25 fields with a
recorded decision, every mapped field emitted, every emitted key received) and
`check_findings_reach_a_surface.py` (25/25 reaching a rendering surface).

Both fired on this field before it was finished — the boundary guard when the
Python field existed with no `EMITTED_AS` entry, the surface guard when the
field crossed to TypeScript and stopped there. That is the second consecutive
field they have caught mid-flight, and it is the ADR 0051 lesson restated:
**crossing the process boundary is not the same as reaching a reader.**
