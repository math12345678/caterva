# ADR 0163 — Run the tool instead of matching the string

**Date:** 2026-08-22
**Status:** Accepted
**Closes:** the layer named as open in
[ADR 0162](0162-a-real-reference-for-a-number-it-does-not-report.md)

## Context

Four ADRs have now been spent on ways a documented citation can be wrong,
each quieter than the last:

| | |
|---|---|
| ADR 0144 | the reference does not exist — `ref 12345` |
| ADR 0161 | the reference is for another enzyme — an AChE ref under LDH |
| ADR 0162 | the page does not report that value — `0.14` under ref 740253 |
| **here** | the value and the reference are both on the page, and are not each other's |

Every guard so far reads **strings**: does this id occur in a fixture, does
that fixture's EC match the prose, does that number appear on the page. ADR
0162 said plainly what that cannot do:

> That the value is the row for the substrate and organism the example
> names. `0.03` occurs on the LDH page; this guard does not confirm it is
> the pyruvate row rather than some other row.

## Decision

Stop matching strings and run the resolver.

`Tests/test_front_page_example_is_what_the_tool_produces.py` resolves
pyruvate / *Homo sapiens* / EC 1.1.1.27 against the committed fixture, with
every auxiliary lookup refused, and asserts the three surfaces carrying the
provenance example show that value, that reference and that unit.

The claim being checked stops being *"these characters appear somewhere on
that page"* and becomes **"this is what the tool does"**. A README example is
a promise about behaviour; every check short of running the thing tests a
proxy for that promise, and this project's history is proxies passing while
the thing they stood for was broken.

## The two mutations, and why the second one is the argument

**A. wrong value, right reference.** `0.03` → `0.398`.

`0.398` is a **real value on that page** — the other candidate row, under
the same reference. So:

```
check_citations_match_their_enzyme    OK   (0.398 does occur on the page)
this test                             FAIL (the resolver returns 0.03)
```

**B. right value, a real reference for the other row.** `286469` → `286442`.

```
check_citations_match_their_enzyme    OK   (286442 is a real LDH reference)
this test                             FAIL (the resolver cites 286469)
```

Both restores verified by `diff`.

That is the layer demonstrated rather than asserted: **only the pair was
wrong, and only running the resolver can check a pair.** Every string guard
in the tree passes both mutations, and each of those guards is correct — the
information simply is not in the strings.

## Why the premise is asserted too

`test_all_three_surfaces_carry_the_example` exists because the other three
tests iterate a list. Reword the block and that list is empty, every
assertion passes over nothing, and the suite reports green on a check that
stopped checking. That is the most-recorded shape in this repository, and it
would have arrived in the test written to close the last gap in it.

## Consequences

- The front page cannot drift from the product without a named failure
  giving both numbers.
- Test count +4. No new guard: the resolver lives in `Tests/`, and this
  needs the resolver.
- If a parser fix or ranking change moves the resolved value, this fails.
  **That is the feature.** The README is then wrong and somebody is told,
  rather than the two diverging quietly for weeks — which is exactly how
  `0.14 / 740253` survived.
- `evidence_table.py`'s docstring, which still listed citation-enzyme
  attribution as needing credentials, is corrected. The correction is left
  visible in the file whose whole point is not asserting more than was
  measured.

## What is still not checked

The other examples. This covers the km line on three surfaces; the derived
Vmax line is exempt for the reason ADR 0142 gives, and `docs/DESIGN.md`'s
`Km = 10.73 mM` block is a different example against a different row and is
not resolved here. Named rather than left for whoever assumes this test
covers every number on the front page.

## Related

- [ADR 0162](0162-a-real-reference-for-a-number-it-does-not-report.md) — the
  layer above, and the open item this closes
- [ADR 0142](0142-vmax-is-derived-not-demanded.md) — why the Vmax line is
  not resolved against a page
