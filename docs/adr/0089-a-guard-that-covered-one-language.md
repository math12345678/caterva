# ADR 0089: A guard that covered one language, and said "every test"

**Status:** Accepted, implemented

**Date:** 2026-08-15

**Relates to:** the vacuous-test guard's own three recorded findings, ADR
0081 (the test that asserted a JSON field instead of calling the function),
and the guard-selftest wiring

## Context

`scripts/check_no_vacuous_tests.py` catches the shape where every assertion
in a test sits behind a conditional, so the test passes having verified
nothing. Its docstring records three real instances, one a regression test
that passed against the very bug it was written for.

Its file filter was:

```python
TEST_FILE = re.compile(r".*\.(test|spec)\.tsx?$")
```

**TypeScript only.** On every run it printed:

> OK: every test has at least one assertion that always runs.

over **1,574 Python test functions it had never opened** — roughly two
thirds of the suite.

That is the guard's own defect class applied to its own scope. Not an
assertion behind a conditional, but a scan behind a file filter: a check
reporting more than it checked, in the words most likely to be believed.

It surfaced because the guard had just caught a vacuous test of mine (ADR
0081's `cite` obligation test, every assertion inside
`if (requirement === "cite")`). Asking what else that guard covered is what
found the gap. A guard being *right* is the best moment to ask what it
cannot see.

## Decision

The guard reads Python too, via AST rather than the brace-counting used for
TypeScript, and its success message names both root sets.

### Loops are not judged, in either language

The TypeScript half's docstring already says it "will not catch every
vacuous test (a `for` over an empty array has the same effect)". The Python
half matches that rather than being stricter.

This is not a small choice. A first pass treating loops as conditional
reported **109** candidates; the guard's actual rule reports **8**. The 109
would have been mostly correct code, and a guard that cries wolf gets
suppressed and then catches nothing — the reasoning ADR 0028 used for buffer
strings. Two halves of one guard meaning different things by the same
message would also be worse than the gap either leaves.

### A recorded baseline, and every entry needs a reason

Eight existing tests matched. They belong to several agents' modules, and
fixing them blind would have been worse than recording them.

`PYTHON_BASELINE` may **shrink, never grow**. Anything not listed fails.

Every entry must carry a reason, because a bare key says only "this is
known" — which is how an exemption outlives the thing that justified it. A
reason says whether a test is conditional **by design** or merely
conditional and awaiting a fix.

## What the baseline found: 8 → 4

Four were fixed rather than excused, each with the mutation that proves it:

| test | why it could not fail | mutation |
|---|---|---|
| `test_bibtex_specials_in_a_title_are_escaped` | two of six parameters contained none of `&%#$_`, and they were the **two hardest cases** — `{braces}` and `back\slash` escape to macros, not a backslash prefix | dropping backslash or brace escaping: the old test could not catch either; the new one fails on both |
| `test_the_commentary_is_never_the_substrate` | would go green if the parser stopped capturing commentary — **which is the regression it names** | force `conditions=None` at every construction site: now fails |
| `test_trypsin_classic_substrates_are_typed_classic` | would go green if no classic substrate parsed at all | retype `"classic"`→`"other"`, and filter the substrates out so the premise fires: both caught |
| `test_effective_size_harmonic_mean_never_exceeds_arithmetic` | branch was on the **input**, not an unknown outcome, so it *could* still fail — but `harmonic ≤ arithmetic` holds for every series and saying so unconditionally is stronger | — |

The first row is the one worth remembering: the coverage was exactly
inverted from the risk. The five characters the loop checked are the easy
ones.

The four that remain are decisions rather than debt. Two turnover tests are
conditional by name — BRENDA often reports no pH, so "assert it where
reported" is the claim — and are protected from the empty-parse case by a
sibling `test_the_fixture_parses_to_at_least_one_entry` over the same
`fixture` parameter. Two popgen tests sit behind a module-level skip.

### A claim measured and withdrawn

Two of the eight are `if result.found:` in `test_popgen_resolver.py`, and
ADR 0061 had just moved `stdpopsim` out of the default install. That looked
like "two tests now pass vacuously for everyone" — a good finding. Running
them showed `1 skipped`: the module carries a skip when stdpopsim is absent,
so the bodies never run and the skip is visible. Recorded here because the
version I nearly wrote was more alarming and wrong.

## Verification

`--selftest` proves the Python half fires: negative case first, then
conditional-assert, loop, `pytest.raises`, baseline suppression, empty scan,
and a no-assertion test. The guard-selftest wrapper discovered it
automatically — 20 selftests now run on every push.

`Tests/test_vacuous_test_guard_python.py` covers the seam a selftest cannot:
that the scan is wired into `check()` and reaches real files under the real
roots, and that **every baseline entry still exists** — a stale exemption is
a permission nobody granted.

## Consequences

- Two thirds of the suite is now scanned by a guard that claimed to cover it
  all along.
- The success message names its scope, so `OK` is a report rather than a
  reassurance.
- Adding a Python test whose every assertion is behind an `if` fails CI
  unless it is added to the baseline with a reason — which is a decision
  someone makes, in writing.
- The baseline is a debt with a stated size. It should be zero, and the four
  remaining entries say why they are not yet.
