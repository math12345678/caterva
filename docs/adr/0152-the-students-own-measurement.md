# ADR 0152 — The student's own measurement

**Date:** 2026-08-21
**Status:** Accepted
**Answers:** Herbert Sauro, 2026-08-21 — *"Under what circumstances can an
ensemble not be created? If you refuse to run what does the user do?"*

## Context

Sauro's opening advice (2026-08-13) was to default a missing Km to 0.5 and
write a warning into the Antimony. Told that two other people disagreed, he
went further: *"Barbara Bakker's approach is better. With Jessie's approach
you don't get any simulation, with Barbara's you can sample and get an
ensemble distribution. **That is the right way to do it.**"* That was built
(ADR 0129, 0131, 0132, 0134).

The thread then reopened the default-versus-refuse question anyway, and he
replied: *"I thought you'd decided to build an ensemble when values are
unknown?"* — followed, when the answer deflected again, by the two questions
above.

He was right to be short about it. The decision had been made, and the
question being re-asked was asking him to arbitrate something already
settled.

## The first question, answered by reading the code

**Under what circumstances can an ensemble not be created?** Three, and only
one of them is the case he means:

1. **The substrate label did not match.** BRENDA calls lactate
   `(S)-lactate`, so a reasonable guess returns nothing. This is not missing
   data — it is a lookup that never happened. Terrium answers with the
   labels the enzyme *does* report and the student re-runs.

2. **The lookup could not be performed.** BRENDA or NCBI unreachable. Kept
   distinct from "no data" throughout, because collapsing them teaches a
   reader to take an absence of evidence for evidence of absence.

3. **Genuinely zero published values.** Nothing to sample. No ensemble.

Cases 1 and 2 have obvious next actions. **Case 3 is his question, and the
honest answer was that the student had nowhere to go.**

## The second question, and why the answer is not a default

**If you refuse to run, what does the user do?**

The objection to defaulting 0.5 has never been that 0.5 is a bad guess. It
is that **nobody chose it**, so there is no one to ask about it, and nothing
in the document a teacher can challenge. The number has no author.

But refusing outright has the same shape from the other side: the student
also ends up with nothing they can defend.

There is a third option, and it was missing. `report` accepted `--s0` and
`--vmax` from the student and had no way to accept a `km`. So:

```
--km 5.2mM --km-basis "measured in our lab, 14 Mar 2026"
```

The value is theirs, it is labelled theirs, and the basis prints beside it.
That is a human source, not an invented one — and the model runs.

## Why the basis is required, and required only here

A bare `--km 5.2` is refused.

`s0` is an experimental **condition**: the student chose how much substrate
to put in, and asking them to cite that is the category error START_HERE
records as having broken this codebase twice. `km` is a **measurement**:
somebody stood at a bench. Accepting one bare would erase the distinction
the entire project rests on, and would make `--km` a default with extra
steps.

`--km-basis ""` is refused too. A flag satisfied by saying nothing is a
formality, and a requirement that can be met without meeting it is the
"check that cannot fail" rule applied to an argument.

Not extended to `vmax`: ADR 0142 settled that Vmax is a property of the
student's own tube, which no database reports.

## Two defects this surfaced immediately

- **km appeared twice in the Parameters table** — once as `not sourced`,
  once as the supplied value. Both rows were accurate and the table was not.
  A document handed to a teacher cannot list one parameter twice, once as
  absent. The empty row is dropped; the failed lookup is still reported
  under *What Terrium would not do*, so nothing is hidden — it is just not
  said twice in contradictory ways.

- **The caveat under the table became false.** *"A value marked yours
  describes the experiment, not the enzyme"* is right for `s0`. For a km
  measured at a bench it is the opposite of what the number is. The caveat
  now follows what was actually supplied.

## Verification

- 5 jest cases in `reportQuantities.test.ts`, 5 pytest cases in
  `test_report_runs_offline.py`.
- The duplicate-row test **counts** rows rather than matching one, because a
  `contains` on either row passes while both are present — which is the
  state it exists to forbid. That counting caught a bug in the test itself:
  slicing the section on the first blank line returned nothing, so it read
  zero rows and would have passed for "no table at all".
- `test_vmax_is_not_described_as_a_measurement_the_literature_lacked` exists
  because the first version of `_MEASURED` included `vmax`, and the document
  then told a reader the literature had failed to supply something no
  database holds.
- `test_the_model_actually_ran_on_the_supplied_value` — a number printed and
  not used is this repository's most-repeated defect.

## Consequences

- Case 3 now has an answer that is neither a fabricated default nor a dead
  end, and the answer is auditable: the basis is the thing to question.
- Test count +10.
- **Still open, and Sauro's point stands:** if a student has no measurement
  either, there is genuinely nothing. Terrium says so and stops. Whether
  that is right for model *development*, as opposed to a teaching lab,
  remains his open disagreement and is not claimed as settled here.

## Related

- [ADR 0134](0134-two-ensembles-built-in-parallel.md) — the ensemble he
  called the right way to do it
- [ADR 0142](0142-vmax-is-derived-not-demanded.md) — why `vmax` is not on
  this list
