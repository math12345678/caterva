# ADR 0180: The equation the document never named

**Status:** Accepted, implemented

**Date:** 2026-08-25

**Context:** `Tests/lab_report.py`, `scripts/report_lab.py`,
`release/app/lesson.js`, `release/test_lesson.mjs`, `Tests/test_lab_report.py`

**Closes a gap named in:** [ADR 0177](0177-ask-before-you-tell.md)

## Context

ADR 0177 built the lesson layer and listed, among the things it did not
check:

> **The mechanism sentence assumes Michaelis-Menten.** It is only reached
> when the report has a `km` disagreement and an `s0`, but nothing checks
> that the run actually used the MM model — a future domain with a `km` and a
> different rate law would get a sentence that does not apply to it.

That was written as a limitation. It is a defect, and the difference matters:
the lesson tells a student *why* a thirteen-fold disagreement in Km produces
a one per cent difference in the answer, and the reason it gives —

> In v = Vmax·S/(Km+S), that puts the enzyme near saturation for either one

— is a fact about **one rate law**. Hill kinetics, ping-pong, or competitive
inhibition all have a Km and none of them make that argument true.

The root cause was upstream of the lesson. **The report never said what the
model was.** It said *"running the model at each"*, and every figure in it —
the band, the disagreement spread, the trajectory — is one equation's output
with the equation unnamed. The lesson was not guessing carelessly; it had
nothing to read.

A wrong explanation is worse here than no explanation, because this layer
exists to teach someone where a claim comes from.

## Decision

**The document states its rate law, and the lesson reads it.**

`_provenance_lines` emits a `| Rate law |` row. `report_lab.py` names it at
the one place that chooses the simulator — beside the
`simulate_michaelis_menten` import — rather than as a constant elsewhere that
could go on saying "Michaelis-Menten" after the choice moved.

**Unstated is not Michaelis-Menten.** A caller who does not name a rate law
gets a row saying so, not a default. "Assume Michaelis-Menten" is exactly the
substitution this project exists to refuse, and it would have been invisible:
every number still present, described by an equation nobody chose.

`lesson.js` produces the saturation explanation only when the document says
Michaelis-Menten. Otherwise it names what the run did use and says the reason
is not derivable — **while still reporting the measured outcome**, which was
measured and stands. A lesson that withheld the result along with the reason
would be refusing more than it must.

## Verification

Sabotage on both sides, each caught by the test that should catch it:

| sabotage | result |
|---|---|
| default the unstated row to `Michaelis-Menten` | `test_an_unstated_rate_law_is_reported_as_unstated` fails |
| drop the row entirely | `test_the_report_states_the_rate_law_it_actually_ran` fails |
| report states Hill kinetics | no saturation explanation; outcome still reported |
| rate law row absent | no saturation explanation; outcome still reported |
| whole provenance section removed | no saturation explanation |

`Tests/test_lab_report.py`: 25 passed. `release/test_lesson.mjs`: 23 checks,
lesson OK, run against a freshly built report rather than a stored sample.

**The assertion was wrong on the first attempt, in the way this repository
keeps recording.** The check for "does it still claim Michaelis-Menten" was
`/saturation/`, and the refusal sentence says *"the saturation argument does
not apply"* — so the test matched the refusal it was written to detect and
reported a pass as a failure. It now asserts on `% of Vmax`, the derived
saturation figure, which is computed only in the Michaelis-Menten branch and
cannot appear in a refusal. That is ADR 0128's finding — prose written to
teach a reader gives a test something to match on for free — made again by
the person who wrote it down, and the note is in the test file because the
next person will make it too.

## Consequences

- Every report now carries the equation its numbers came out of, which a
  reader needs before they can check a single one of them.
- The teaching layer's explanation follows the document instead of its
  author.

**What this does not check.**

- **That the stated rate law is the one that ran.** `RATE_LAW` is a string
  beside the simulator import, not derived from the simulate function. If
  someone changes the simulator and not the string, the document lies and
  nothing here notices. Naming the function object would close it; that is a
  larger change to `_band_for`'s shape and is not made here.
- **Only Michaelis-Menten has an explanation.** Every other rate law gets an
  honest refusal, not a lesson. Hill kinetics has a perfectly good story
  about cooperativity and nothing tells it.
- **Still nobody has taken the lesson.** ADR 0177's first named gap is
  unchanged: screen recording is unavailable here, so the panel is verified
  by tests and never by a human reading it.
