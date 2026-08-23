# ADR 0162 — A real reference for a number it does not report

**Date:** 2026-08-22
**Status:** Accepted
**Follows:** [ADR 0161](0161-the-subtle-half-was-decidable-after-all.md)

## Context

ADR 0161 closed the second of three ways a citation can be wrong and named
the third as open:

> **Still genuinely open:** whether a ref describes the *value* it is
> attached to — that 0.14 mM is the Km on that page — which needs the row,
> not just the reference.

It took one pass to find out that the example used to describe the open
question **was itself the defect.**

## What was on the front page

```
km    0.14 mM    brenda_exact  BRENDA ref 286469
```

— as it reads now. Until this ADR it read:

```
km    0.14 mM    brenda_exact  BRENDA ref 740253
```

Measured against the committed fixture:

- `740253` is a **real** reference. It exists, it is on the lactate
  dehydrogenase page, and it is the right enzyme. Both existing guards pass
  it.
- The string `0.14` **does not occur anywhere in that fixture.** The rows
  under `740253` read **10.73** and **21.78** mM, for `(S)-lactate`.
- The fixture's own note says the human rows are *"all ref 740253 except
  pyruvate"* — and the example is a **pyruvate** query, so the pairing was
  contradicted by the file it claimed to come from.

Running the resolver over that fixture gives the truthful answer for
pyruvate in *Homo sapiens*: **0.03 mM, BRENDA ref 286469**. That is what all
three surfaces now show, and it is also what `make demo` prints — the front
page and the tool finally agree.

A reader who followed that citation — **the entire behaviour this tool
exists to make possible** — would have found a different number and no way
to tell which was wrong. Three surfaces carried it.

## Three layers, and the third is the quietest

| how a citation is wrong | closed by |
|---|---|
| the reference does not exist | ADR 0144 |
| the reference is for another enzyme | ADR 0161 |
| the page does not report that value | **here** |

Each is quieter than the last, and each survived the guard built for the one
above it. `ref 12345` was visibly fake. `ref 649716` needed somebody to know
AChE from LDH. This one needs somebody to open the page and read the row —
which is exactly the work a provenance tool is supposed to have already done
for you.

## Decision

`value_mismatches()` in `check_citations_match_their_enzyme.py`: a value
printed beside a reference must occur on a page that reference appears on.

### A derived value is not a quoted one

```
vmax  0.25 mM/s  brenda_cross_species → kcat x [E]0  BRENDA ref 741355
```

is honest. The reference supports the **kcat**; the Vmax is that kcat times
an enzyme concentration the student chose (ADR 0142). Demanding that `0.25`
appear on the BRENDA page would fail a line that is telling the truth, and a
guard that fires on the correct case gets suppressed (ADR 0028).

So lines carrying a derivation marker — `→`, `->`, `kcat x` — are counted
and skipped, and the count is printed. Three checked, three derived, and the
reader can see both.

## Verification

- **Mutation on the real tree:** restoring `0.14 mM ... ref 740253`
  reproduces this morning's front page and the guard names it — *"0.14 does
  not occur on the page(s) that reference appears on"*. Restored, verified
  by `diff`.
- The derived Vmax line is not flagged, before or after.
- The two existing citation guards still pass, which is the point: both were
  green on `0.14 / 740253` for as long as it stood.

## Consequences

- All three ways a documented citation can be wrong are now checked.
- The README's provenance example shows what the tool actually produces from
  the committed fixture, so `make demo` and the front page can no longer
  disagree.
- No new guard file and no new guard count: this is a second function in the
  guard whose subject it shares. Two files reading the same surfaces would
  be the duplication these three ADRs keep deleting.

## What is still not checked

That a value on the page is the value *for the substrate and organism the
example names*. `0.03` occurs on the LDH page; this guard does not confirm
it is the pyruvate row rather than some other row. Closing that means
comparing parsed rows rather than strings, and the resolver already does it
— wiring the two together is the next layer down, and it is named here
rather than left to be discovered by the next person who trusts this guard
past its limits.

## Related

- [ADR 0144](0144-the-guard-that-could-not-see-an-indented-table.md),
  [ADR 0161](0161-the-subtle-half-was-decidable-after-all.md) — layers one
  and two
- [ADR 0142](0142-vmax-is-derived-not-demanded.md) — why the Vmax line is
  correct and must not be flagged
