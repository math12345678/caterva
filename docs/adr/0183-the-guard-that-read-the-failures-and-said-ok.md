# ADR 0183: The guard that read the failures and said OK

**Status:** Accepted, implemented

**Date:** 2026-08-25

**Context:** `scripts/check_no_silent_skips.py`,
`Terium/tests/test_sbml_provenance.py`

**Follows:** [ADR 0182](0182-the-provenance-that-did-not-survive-being-used.md),
which is how this was found

## Context

ADR 0182 was committed after a full local guard sweep reported **41 ok, 0
failed**. CI then failed on the engine suite.

The failure was real and useful — an existing test,
`test_antimony_comments_do_not_survive_translation_to_sbml`, asserting the
premise ADR 0182 had just altered. It was written to fire on exactly this,
and its docstring says what to do:

> If a future Antimony gains comment-preserving translation this test fails,
> and the right response is to re-examine whether the SBML annotator is
> still needed — not to delete the test.

**The re-examination.** The premise is intact and the annotator is still
needed. Comments are still discarded; the module was never built on
"provenance cannot reach SBML from Antimony" but on "*comments* cannot". And
a note is prose — `annotate_sbml` writes CVTerms, a PubMed identifier as a
resolvable URI under `bqbiol:isDescribedBy`, which is what lets a consumer
*follow* a citation rather than read one. That is Bergmann's split exactly
(ADR 0181): identifiers in CVTerms, prose in notes.

So the test now asserts its stated claim using a plain comment, instead of
the annotator's output — which measures a by-product of how the annotator
happens to be written today. A second test asserts the other half, that a
*note* does reach SBML. Without it the first would pass on a translator that
dropped everything, and would keep passing if ADR 0182's notes silently
stopped being emitted.

## The finding that matters more

**Why did a full local sweep say 41/41 green with a failing test in the
suite?**

`check_no_silent_skips.py` runs both suites in full and parses the JUnit
report. Its counting loop read:

```python
elif case.find("failure") is None and case.find("error") is None:
    passed += 1
```

A failing test is neither passed nor skipped. It left the totals entirely.
The guard printed `1,222 passed, 0 skipped` and exited 0 while holding a
report that said otherwise.

This is the file's own docstring turned inward:

> A green suite cannot distinguish "ran and passed" from "declined to run".

Here it could distinguish and did not say. The one guard that runs the whole
test suite had the failure in its hands and reported success — which is why
"41/41 guards green" was stated in a commit message for a commit that broke
the build.

## Decision

Failing tests are counted, listed by name, and the suite is reported as not
having run cleanly. `run_suite` returns `None`, which routes into the
existing `unrun` path, so the guard says the suite's skip count is unknown
rather than publishing a total about a suite that was already broken.

It does not try to diagnose them — that is what running the suite is for —
but it will not print OK while holding a report that says they failed.

## Verification

A deliberate `assert False` planted in the engine suite:

```
  ! 1 failing test(s) in tests:
      tests.test_model_provenance::test_zz_deliberate_failure...
FAIL: 1 of 2 suite(s) did not run: engine.
exit=1
```

Removed, it returns to `OK: 2/2 suites ran, 2344 tests, 0 unexplained
skip(s)`, exit 0. The exact failure that reached CI this morning is now
caught before a push.

41/41 guards green.

## Consequences

- A local guard sweep now means the test suites pass, which is what everyone
  including me already believed it meant.
- The premise test is measuring its stated claim rather than an artifact of
  the annotator.

**What this does not check.**

- **It reports failures; it does not replace running the suite.** No
  tracebacks, no assertion text — a name and a count, and a refusal to say
  OK.
- **`verify_build --quick` still skips the long tests**, so the *quick* path
  remains what its name says. This closes the gap in the full sweep only.
- ~~**Nothing checks that a guard reporting on a suite reports everything
  the suite told it.**~~ **Done in
  [ADR 0184](0184-the-audit-adr-0183-asked-for.md).** It audited the three
  scripts that parse test outcomes and found one more: `mutate.py` counted
  a pytest collection `error` as zero failures, turning a mutation the
  suite had caught into a false NOT CAUGHT.