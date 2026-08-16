# ADR 0044: The simulation form pre-filled the forbidden default

**Status:** Accepted, implemented

**Date:** 2026-08-14

**Relates to:** ADR 0012/0013 (never default a parameter — this is that rule
broken on the product's own front page), ADR 0024, ADR 0042 (the same page,
its displayed numbers)

## Context

ADR 0042 removed seven fabricated numbers from the dashboard's *displays* and
closed by noting the page still showed none of the resolver's findings. That
was the wrong next question. The sharper one was upstream: what does the page
put **into** a simulation?

`src/web/dashboard.html` shipped its Run Simulation form as:

```html
<input type="text"   id="enzyme"    value="lactate dehydrogenase">
<input type="text"   id="substrate" value="lactate">
<input type="number" id="km"        value="5.2">
<input type="number" id="vmax"      value="12.8">
<input type="number" id="s0"        value="10">
```

ADR 0024, stating the rule the entire project rests on:

> a parameter that cannot be sourced stops the run. **No `km = 5.2`
> fallback**, no plausible-looking default.

**The form was pre-filled with the exact number the constitution uses as its
example of the forbidden thing.** `5.2` matches no lactate dehydrogenase
measurement in the corpus — the fixtures carry 10.73 for lactate and the
README's worked example is 2.5 for pyruvate.

Because the enzyme and substrate were pre-filled too, the complete path was:
open the page, press **Run Simulation**, receive a trajectory, a confidence
percentage and a green ✓ — for a model built on a Km that came from nowhere.

## Why this is worse than ADR 0042's version

A fabricated *display* misinforms whoever reads it.

A fabricated *input* gets **used**. It enters the engine, comes out the other
side as a trajectory, and returns wearing the authority of a computation and
a validation tick. Everything downstream behaves correctly on it — the
numerics are right, the confidence is real, the tick is honestly earned by
the arithmetic. None of that machinery has any way to know the number at the
front was typed by a web designer.

The resolver refuses to emit an unsourced Km. The form beside it handed one
over, pre-typed, in the field labelled Km.

## Decision

### Nothing is pre-filled

`km`, `vmax` and `s0` ship empty with placeholders. The existing guard clause
— `if (!km || !vmax || !s0)` — was already there and was **unreachable in
practice**, because the form was never empty. A refusal behind a default is a
refusal nothing exercises.

Its message now explains rather than scolds: it names which parameters are
missing, says Km and Vmax are measurements the page will not invent, and
gives the `scientific resolve` command that produces one with its citation.

### The distinction is on the page, not just in the ADRs

Km and Vmax are tagged **measured**. S0 is tagged **your choice**, in a
different colour.

That is the measured-quantity versus experimental-condition distinction ADR
0012/0013 rest on, and until now it existed only in code and prose. A
teaching tool should show it rather than assume the student arrives knowing
it — and the reason nothing is pre-filled follows directly from which side of
the line a parameter falls on.

### The guard covers inputs, not only displays

`check_no_unsourced_ui_numbers.py` gains a second check: any `<input>` whose
id is a measured quantity (`km`, `vmax`, `ki`, `kcat`, `enzymeConc`) must not
carry a numeric `value`.

Matched on **id**, not label, because a label can be reworded and the id is
what the code reads.

**S0 is deliberately not in that set.** A pre-filled experimental condition is
a UI convenience for something the student chooses; a pre-filled measurement
is a fabrication. The guard must not blur the two, and a mutation confirms it
does not: pre-filling `s0` produces no finding.

## Verification

| Mutation | Result |
|---|---|
| reintroduce `km value="5.2"` (*the original defect*) | caught, named |
| pre-fill `vmax value="12.8"` | caught, named |
| pre-fill `s0 value="10"` (a chosen quantity) | **correctly not flagged** |

The third matters as much as the first two. A guard that flagged everything
would be discovered wrong the first time someone set a sensible default for a
condition, and would then be disabled for the cases that matter.

## Consequences

- The dashboard cannot be run without the student supplying every parameter.
  That is less convenient and it is the point: the convenience was a lie.
- `check_no_unsourced_ui_numbers.py` now covers displays *and* inputs.
- The measured/chosen tags are new UI vocabulary. They should appear anywhere
  else parameters are entered; today only this page has them.
- `mule/` remains unchecked, as recorded in ADR 0042.

## What this does not fix

The dashboard still shows none of the resolver's findings — no citation, no
assay conditions, no variant, no reliability grades — and still asks the
student to paste a number in by hand rather than resolving it in the page.
The honest sequence is: stop inventing numbers (ADR 0042), stop offering
invented ones (this), then show where real ones came from. The third is the
largest and is not done.

There is also no test that the refusal fires. The guard proves the form is
not pre-filled; nothing proves the alert appears when a field is empty. The
dashboard has no test harness at all, which is a gap worth naming rather than
quietly tolerating — every other surface in this project has one.
