# ADR 0177: Ask before you tell

**Status:** Accepted

**Date:** 2026-08-24

## Context

The owner wants Terrium to teach, not only to compute — a tutor that shows a
student how to think about a simulation rather than handing them a document.

The starting observation is that **the lesson is already in the report**, and
it is phrased as a lecture:

> The evidence ranked 2 values of km equal: 0.03 to 0.398. Running the model
> at each … the substrate remaining at t=10 ranges from 7.509 to 7.609. **A
> factor of 1.01.**

A **thirteen-fold** disagreement in a textbook constant, producing a **one per
cent** difference in the answer. Most courses teach students to code the
Michaelis-Menten equation. Almost none teach that Km has a 13× range in the
literature, and fewer still that the size of that range says little on its own
about whether it matters.

Terrium has already run both values. The only missing part is the asking.

## Decision

**A lesson layer that turns the report into a question, and refuses when it
cannot.**

`release/app/lesson.js` reads the document the builder produced and returns
either a lesson or a reason there is none:

1. **Predict.** *"The literature reports 2 values for km, and they differ by a
   factor of 13.3. Before you look: how different will the two runs' answers
   be?"* Four choices.
2. **Reveal.** The report's own numbers: a factor of 1.01.
3. **Explain.** Derived from the figures, not written about this enzyme in
   advance — both values sit below the s0 the student chose, so in
   `v = Vmax·S/(Km+S)` the enzyme is near saturation either way (96.2% of Vmax
   at the larger Km), the rate is set by Vmax, and Km barely gets a say.
4. **Caution.** Carried through verbatim in spirit: this is the spread of
   published measurements, not an uncertainty estimate.

**It invents no numbers.** Every figure is read out of the markdown. The
choices are generated from the actual parameter spread, so the correct answer
is not always in the same position and "the small one" is not always right —
a quiz whose answer can be guessed from the shape of its options teaches the
shape.

**And it refuses.** If the literature reported one value there is nothing to
predict, and it says so rather than manufacturing a question. That refusal is
the load-bearing part: a teaching tool that always has a lesson ready will
eventually invent one, and a fabricated lesson *about provenance* would be a
worse failure than no lesson at all.

The app shows the question first, then the full report beneath the answered
panel. "Skip to the report" is always available.

## Verification

`release/test_lesson.mjs`, run against **that build's** report rather than a
stored sample, and wired into `build_dmg.sh` so no DMG ships without it:

```
  ok    a lesson is produced from the real report
  ok    the parameter value 0.03 is in the report
  ok    the result 7.60877 is in the report
  ok    exactly one choice is marked correct
  ok    no disagreement section -> refuses, with a reason
  ok    fewer than two values -> refuses rather than comparing one thing
  ok    a bigger outcome spread moves the correct answer
  ok    a Km above s0 changes the explanation
  13 checks, lesson OK
```

The last two are the ones that mean anything. Every figure being present in
the document would still pass if `correctId` were hardcoded — so the tests
**sabotage the report**: widening the outcome spread must move the correct
answer, and pushing a Km above s0 must change the explanation. Both do.

The derived claim was checked by hand as well: at s0 = 10 mM, `10/(10+0.398)`
is 96.2% of Vmax and `10/(10+0.03)` is 99.7%, a rate ratio of 1.037 — which is
the order of the 1.01 spread the report reports over the whole run.

Parsing was wrong on the first attempt and refused rather than guessing:
slicing from the heading and splitting on `^## ` leaves an **empty** first
element, so the section came back blank and the lesson reported "fewer than
two values". It refused correctly on a real report, which is how the bug
surfaced at all.

Full build: SELFTEST OK, viewer OK, lesson OK, signature verifies, 85 MB DMG
with `lesson.js` inside it.

## Consequences

The first genuinely *pedagogical* surface in Terrium, and it teaches the one
thing the tool uniquely knows: where a number came from, how much its sources
disagree, and whether that disagreement reaches the answer.

**What this does not check.**

- **Nobody has taken the lesson.** The panel has never been seen by a human —
  screen recording is unavailable here, so the flow is verified by unit tests
  and the app's headless selftest, not by clicking it. Whether the question
  reads well, whether four choices is right, whether the reveal lands: all
  unknown.
- **One lesson, one shape.** It teaches parameter disagreement and nothing
  else. The refusal path, the assay-condition grading, and the twelve other
  domains are all equally teachable and untouched.
- ~~**The mechanism sentence assumes Michaelis-Menten.**~~ **Closed by
  [ADR 0180](0180-the-equation-the-document-never-named.md).** The report
  now states the rate law it ran, and the lesson reads it instead of
  assuming: a run under Hill kinetics gets an honest refusal rather than a
  saturation argument that does not apply to it. Listed here as a
  limitation, which 0180 corrects — it was a defect.
- **No notion of a learner.** No progress, no second question, no record of
  what was answered. `queryLog.ts` (ADR 0171) could carry that and does not.
- **The four bands are chosen, not derived.** 1.2×, 2×, and 0.6 of the
  parameter spread are judgement calls about what "noticeably different"
  means. Nothing measures whether they are the right cuts.