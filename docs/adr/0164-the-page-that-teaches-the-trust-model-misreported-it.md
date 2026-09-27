# ADR 0164 — The page that teaches the trust model misreported it

**Date:** 2026-08-22
**Status:** Accepted
**Follows:** [ADR 0163](0163-run-the-tool-instead-of-matching-the-string.md)

## Context

ADR 0163 closed the fourth way a documented citation can be wrong and named
`docs/DESIGN.md`'s separate example as not yet covered. Extending the same
technique to it — resolve against the committed fixture, compare — found a
fifth layer, and the worst one so far.

The value was right. The reference was right. **Everything about how much to
trust them was invented.**

## What DESIGN.md said, and what the tool says

`docs/DESIGN.md` is the page that explains what Caterva's three trust grades
mean, using `ref 740253` as its worked example.

| DESIGN.md said | the resolver, on the committed fixture |
|---|---|
| measured at **pH 7.5, 25 °C** | pH **8.0**; temperature **not reported** |
| assay completeness **complete** | **partial** |
| conditions: pH and temperature **both reported** | *"The source states it did not report: temperature."* |
| organism: exact match | exact match ✓ |

Three claims, three wrong, **every one in the direction of more confidence.**

All four earlier layers pass this example: the reference exists (0144), it
is a lactate dehydrogenase reference (0161), `10.73` is on that page (0162),
and the value/reference pair is exactly what the resolver returns (0163).

The document explaining the trust model was the thing misreporting the trust
model.

## Why this is the worst instance in the sequence

A wrong Km is a wrong number, and a reader who checks finds it. A wrong
*grade* teaches the reader what the grades mean. Somebody learning that
`complete` is what you get when the source omits the temperature has
learned the opposite of the rule, from the page written to teach it — and
will read every future `complete` that way.

`grade_assay_completeness` returns, for this row:

> Assay reports pH 8.0 but no temperature. Weak evidence rather than none:
> the value constrains a plausible range, and cannot be reproduced exactly.
> The source states it did not report: temperature.

That sentence is careful, correct, and was contradicted three lines away in
the design document.

## Decision

DESIGN.md now states what the resolver returns, and four tests hold it
there. The completeness grade is not hardcoded in the test either — it is
obtained by calling `grade_assay_completeness` with the resolver's own
fields, so a change to how completeness is decided fails here rather than
leaving the design document describing a rule the code stopped following.

## A guard of mine that cried wolf, and the narrowing

The first version of `test_the_design_example_does_not_invent_assay_conditions`
asserted `pH 7.5` appeared **nowhere** in DESIGN.md. It failed — on line 65,
an unrelated hypothetical about combining a Km at pH 7.5 with a Ki at pH 6,
which is a correct sentence illustrating a different problem.

A guard that fires on a correct sentence gets suppressed (ADR 0028). The fix
is to narrow the claim, not to soften it: the assertion is about one worked
example, so `_worked_example()` reads one worked example — the block between
`ANSWER` and `RESULT` — and nothing else.

## Verification

- 8 tests in the file, up from 4.
- **Mutation, twice.** Restoring `assay completeness complete` fails
  `test_the_design_example_states_the_grade_the_grader_gives`; restoring
  `pH 7.5, 25 °C` fails `test_the_design_example_does_not_invent_assay_conditions`.
  Both restores verified by `diff`.
- The invented conditions are asserted **absent** rather than the correct
  ones present: a replacement that happened to contain "8.0" somewhere would
  satisfy a positive check while leaving `pH 7.5, 25 °C` in place.

## Consequences

- Five layers of citation correctness are now checked, and the deepest one
  is about the tool's own confidence rather than its numbers.
- Test count +4.
- Every claim in that block is now derived from a run. If the fixture, the
  parser or the grading changes, the design document fails rather than
  quietly describing a former version of the tool.

## The pattern across five ADRs

| | what was wrong | caught by |
|---|---|---|
| 0144 | the reference does not exist | a string check |
| 0161 | the reference is another enzyme's | a string check |
| 0162 | the page does not report the value | a string check |
| 0163 | the value and reference are not each other's | running the resolver |
| 0164 | the confidence in them was invented | running the grader |

Each was invisible to every check built before it, and the last two were
only reachable by **running the thing rather than reading about it**. That
is the transferable lesson, and it is cheaper to write here than to
rediscover a sixth time.

## Related

- [ADR 0163](0163-run-the-tool-instead-of-matching-the-string.md) — which
  named this example as uncovered
- [ADR 0010](0010-strenda-assay-conditions.md) — why assay conditions are
  load-bearing rather than decoration
