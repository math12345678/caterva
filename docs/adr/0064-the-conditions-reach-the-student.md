# ADR 0064: The conditions reach the student

**Status:** Accepted, implemented

**Date:** 2026-08-15

**Relates to:** ADR 0055 (which computed this and displayed none of it),
ADR 0027 / 0040 (the same shape, twice before), ADR 0048 (the harness),
ADR 0053

## Context

ADR 0055 established that a simulation has no temperature of its own — the
Michaelis-Menten ODE takes none, so a run is at whatever conditions its
parameters were *measured* at. It built `deriveRunConditions`, returning a
three-state verdict per condition: `agreed` / `conflicting` / `not_reported`.

It closed by naming what it had not done:

> Nothing renders `runConditions` yet. The pipeline computes it, the
> response carries it, `examples/` prints it — and the dashboard does not.
> That is the same gap ADR 0027 and ADR 0040 were about, named here in
> advance rather than discovered later, and it is the next thing to build.

This is that.

## Decision

`renderRunConditions()` in `dashboard.html`, called after a completed
simulation, with a card that stays hidden until a run produces conditions.

The three states render three different ways, and the differences are the
whole point:

| state | rendered as |
|---|---|
| `agreed` | the value, tagged as measured |
| `conflicting` | a warning naming **both** values, and **no** single figure |
| `not_reported` | the words "not reported", plainly — **not** a warning |

### Why `conflicting` and `not_reported` must look different

Both end with no usable number. They are entirely different facts: one is a
gap in BRENDA's record, the other is a defect in the model being built. A
display that collapsed them would undo ADR 0055 at the last step — the
distinction would be computed correctly, carried across two layers, and then
erased by the thing a student actually reads.

### Why a silent record is not styled as a warning

Most BRENDA rows do not report both a temperature and a pH, so
`not_reported` is the common case. Styling it as an alert would train the
reader to skim past alerts, which is precisely when the `conflicting` one
stops working.

### Why the conflict names both values and no mean

`km at 25 °C, vmax at 37 °C` — never `31 °C`. The mean of two assay
temperatures is not an assay temperature. Rendering it would state a
condition no experiment used, in the panel that exists to say what the
experiments were.

### `silent` is carried onto an `agreed` verdict

One parameter reporting is not a conflict. It is also not a consensus. A
student who sees "25 °C" is told which parameters said nothing, so they can
tell one report from three agreeing.

## Verification, and the mutation that says the most

Five mutations against the eight display tests:

| Mutation | Result |
|---|---|
| `conflicting` falls through to the `not_reported` branch | 2 failures |
| a conflict renders the mean instead of both values | 1 failure |
| the silent-parameter list is dropped | 1 failure |
| the card is shown even with no conditions | 1 failure |
| **delete the CALL from `runSimulation`** | **all 33 passed** |

The fifth is the one worth keeping.

Every one of those eight tests calls `renderRunConditions` directly. Not one
of them ran a simulation. So the renderer was thoroughly tested and nothing
checked that anything ever *called* it — delete the call site and the feature
is gone, silently, with a green suite.

**That is the defect ADR 0055 is about, repeated by the feature built to
finish ADR 0055.** That ADR's own tests covered `deriveRunConditions`
exhaustively while a mutation restoring `temperature: 37` across nine call
sites passed. Its guard script opens with the sentence *"testing a function
is not testing the call site."*

I wrote that sentence. Then I did it again, in the work that cites it.

Fixed by two tests that drive `runSimulation` end to end against canned
`/api/simulate` and `/api/jobs/:id` responses — one with conditions, one
without. Under the mutation, the first fails.

35 tests. `tsc --noEmit` clean. `check_no_unsourced_ui_numbers.py` green: the
rendered values are written at run time, which is the distinction that guard
encodes.

## Consequences

- A trajectory now says what it is a trajectory *of*. Before this, a run
  whose papers disagreed about temperature looked identical to one where
  they agreed, which looked identical to one where nobody recorded anything.
- "Not reported" will appear often, and that is the honest output rather
  than a gap in the feature.
- The panel restates that the simulation has no temperature of its own. Left
  in deliberately: it is counter-intuitive, and a student who does not read
  it will assume the number is a setting they chose.

## What it does not do

The CLI still does not render `runConditions` — `commandSimulateResolved`
prints a trajectory and no conditions. Same gap, one surface over, named
here rather than left to be found.

Nothing renders `notEvaluated` either. `AssumptionValidator` returns
assumptions it could not check, and no surface shows them, which restores in
miniature the problem `notEvaluated` was built to solve. It is task 4 in
`docs/FIRST_TASKS.md`.
