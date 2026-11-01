# ADR 0035: A pool that mixes enzyme forms

**Status:** Accepted, implemented

**Date:** 2026-08-14

**Relates to:** ADR 0029 (protein variants), ADR 0031 (commentary coverage,
which recorded this as an open finding), ADR 0033 (contrast detection across
a pool — same structural move), ADR 0028 / 0032 (PubChem identity)

## Context

ADR 0029 taught Caterva to spot a variant row. Its `_ISOZYME_RE` matches the
**word** "isozyme"/"isoform", so `"pH 8.5, 25°C, isozyme H4"` is caught.

BRENDA also names forms **positionally**, and those were not:

```
"LDHB, in the presence of 0.125 mM NADH"
"pH 7.5, ..., LDH-1, with 3 mM fructose-1,6-bisphosphate"
"pH 7.5, ..., wild-type LDH-2, with 3 mM fructose-1,6-bisphosphate"
"hexokinase Ia"
```

`classify()` returns `unstated` for every one.

ADR 0031's coverage guard surfaced these as the largest remaining group of
unread commentary, and recorded the reason for not fixing it then: knowing
that "B" is a form designator after "LDH" and is not one after "NAD" means
knowing what LDH and NADH *are*, and hardcoding "LDH means lactate
dehydrogenase" is what this project refuses to do.

## The measurement

The LDH turnover pool contains three forms at once:

| form | values |
|---|---|
| LDHB | 142 – 350 |
| LDH-1 | 1500 – 1600 |
| LDH-2 | 1300 – 1800 |

Selection is `min()`. It takes **142.0 from LDHB** and reports it as the
turnover number of "lactate dehydrogenase" — an order of magnitude below the
LDH-1 and LDH-2 rows sitting in the same pool. The hexokinase Km pool does
the same across forms I, Ia and Ib.

## Decision

### Ask a different question

Not *"is this row an isoform?"* — which needs domain knowledge — but
**"do these rows name different forms of the same thing?"**

That is a pool-level question, the same reshape ADR 0033 made for effectors,
and it needs no domain knowledge at all. Group rows by `(base, designator)`;
if one base carries several designators, the pool mixes named forms. Nothing
in `form_mixture.py` knows or needs to know what LDH stands for.

### Compounds are excluded by PubChem, not by a list

The obvious false positive is `"NADH"`: base NAD, designator H, by shape
alone. A pool holding NADH and NADP would report two cofactors as two forms
of one enzyme.

The fix is not an exclusion list. A candidate is dropped when
`buffer_identity.resolve_identity` resolves it to a compound — the same
API-backed identity used for buffers (ADR 0028) and effectors (ADR 0032).
NADH resolves; LDH does not. A claim with a source, made by the mechanism
already carrying every other chemical claim here.

**Both the base and the full tokens are checked.** Checking only the base
passes today by luck: PubChem happens to know "NAD". For an acronym whose
stem is not itself catalogued, the base check alone would let the compound
through. Found by mutating it and watching the tests stay green.

### It reports; it does not withhold or choose

A request for "lactate dehydrogenase" genuinely is ambiguous between its
isoforms, and resolving that ambiguity belongs to the user. Reporting is what
makes the choice available.

The network call is skipped entirely when no base carries two designators —
the common case — so a pool naming no form costs nothing.

## Verification

`test_form_mixture.py`, 24 tests. Six mutations; four caught immediately,
**two required tests to be written before they could fail**:

| Mutation | Failures |
|---|---|
| compound filter removed (NAD reads as an enzyme) | 1 |
| one designator counts as a mixture | 2 |
| the reason stops naming the values | 1 |
| network hit when there is no mixture | 1 |
| only the base is checked, not the full tokens | **0 → 1** |
| a resolver exception counts as "is a compound" | **0 → 1** |

### The fourth and fifth unreachable branch

Both misses were defensive paths the fixtures could not reach:

- **Full-token check.** Redundant while PubChem knows "NAD". Tested by
  constructing the case luck covers — a base that does not resolve, full
  tokens that do.
- **`_is_compound`'s exception guard.** `resolve_identity` swallows provider
  failures itself and returns `status="unresolvable"`, so the `except` never
  fires through the provider arguments. Tested by making the resolver itself
  raise.

This is the fourth and fifth time: ADR 0026's origin filter, ADR 0031's
never-matched input, ADR 0033's `unstated` filter, and now these two.

The pattern has earned a name. **Mutation testing proves a check can fail on
the inputs it receives. It says nothing about inputs it never receives, and a
guard's most dangerous state is one no current caller can produce** — because
an untestable branch is one somebody deletes as dead code, and the deletion
looks like cleanup.

It is worth noticing that the count keeps rising *because* the mutation pass
is run. These branches exist in code that was never mutation-tested too; they
are simply invisible there.

## Consequences

- `KineticResult.form_mixtures` is new, populated on found results.
- The resolver logs mixtures before selection, so the search log records that
  several forms were seen.
- `protein_variant.py` is unchanged. Positional forms are deliberately not
  folded into `classify()`: it answers a per-row question and this is not
  one.

## What this does not claim

A mixture is a fact about the candidate pool, not about the enzyme. Two forms
may also differ in assay conditions, and `fold_difference` is the span a
reader is asked to look at — not an effect size.

It also cannot see a pool where every row names the **same** form.
Homogeneous and unlabelled are indistinguishable here, and both read as no
finding. A pool of nothing but LDH-1 rows is still not a measurement of
"lactate dehydrogenase", and nothing in this module will say so.
