# First tasks

Real open gaps, not exercises. Every one was verified against the tree on
2026-08-15 by running the command listed under it.

Each task gives you three things: **the file to open**, **a command that
shows the gap**, and **how you know you are done**. If a task turns out to
be already fixed when you get to it, that is a finding — say so and take
another.

Before starting anything here, get through
[`START_HERE.md`](../START_HERE.md) as far as a passing `make check`.

---

## Warm-up — an hour or two

### 1. Try to break the resolver, and report it precisely

No file to open. The most valuable thing a new person does is find something
everyone else stopped seeing.

```bash
npx ts-node src/cli/scientificCLI.ts resolve "made up enzyme" \
  --substrate nonsense --organism "Homo sapiens"
```

Then try: nonsense units, a negative concentration, an enzyme with a Unicode
name, a substrate with an apostrophe, an organism that is a typo of a real
one, and the whole thing with no network.

**Done when:** you have filed at least one report with *what you ran*, *what
happened*, *what you expected*. You do not need to know the fix. A crash
with a stack trace is a finding. So is a refusal that does not say why.

### 2. Read a document against the code

Pick any file in `docs/` and check its claims against the source. If it says
a command exists, run it. If it quotes output, produce that output and
compare.

This is not busywork. A sweep like this found a 725-line API reference
describing endpoints that had never existed, and — while this list was being
written — three onboarding documents claiming "22 guards and 1,291 tests"
when the real figures were 35 and 1,684.

(Those figures are quoted because they are the defect, not a claim about
today. `check_documented_counts.py` reads a plainly-written count as an
assertion and a quoted one as an example — so citing a stale number in
prose needs the quotes, or the guard is right to object.)

```bash
python scripts/check_documented_counts.py
```

**Done when:** either you have filed a mismatch, or you can say which
document you checked and which specific claims you verified. "Looked fine"
is not a result.

---

## Real work — a day or two

### 3. Nothing renders the conditions a simulation ran at — ~~open~~ **DONE, dashboard half**

> **Half of this was completed on 2026-08-16 and this entry did not say so.**
> `src/web/dashboard.html` now has a `runConditionsCard`, a `runConditions`
> panel, reads `result.runConditions` and renders it. A newcomer who picked
> this task, ran the "never rendered" grep below and found five hits would
> reasonably conclude the task list lies.
>
> **The CLI half is still open**: `grep -c runConditions
> src/cli/commandResolve.ts` returns 0. That is the remaining task, and it
> is smaller than what is described below.
>
> `Tests/test_first_tasks_are_still_open.py` now runs the diagnostic
> commands in this file so a task cannot close silently again. A task list
> that goes stale is a trap for exactly the person you most want to help:
> they spend their first day on something already finished.

It is the gap
[ADR 0055](adr/0055-a-simulation-has-no-temperature-of-its-own.md) names in
its own "what it does not do" section.

The pipeline computes `runConditions` — the temperature and pH the
parameters were *measured* at, with a verdict of `agreed` / `conflicting` /
`not_reported`. The response carries it. `examples/scientificPipelineExample.ts`
prints it. **The dashboard does not, and neither does the CLI.**

```bash
# computed and returned:
grep -n "runConditions" src/integration/scientificPipeline.ts
# never rendered:
grep -n "runConditions" src/web/dashboard.html src/cli/commandResolve.ts
```

Files: `src/web/dashboard.html` (`renderProvenance`), and/or
`src/cli/commandSimulateResolved.ts`.

**Done when:** a run whose parameters disagree about temperature says so on
screen, and a run whose parameters never reported one says *that* instead —
distinctly. Those are different facts and the display must not collapse them.
Add a test to `src/web/__tests__/dashboardParameterGate.test.ts`, then
**mutation-test it**: make the `conflicting` branch render the
`not_reported` text and confirm your test goes red.

Read `src/validation/runConditions.ts` first. Its module docstring explains
why a conflict deliberately carries no value.

### 4. The assumption checks that could not be evaluated reach nobody

`AssumptionValidator` returns three lists: `violations`, `warnings`, and
`notEvaluated` — checks it could not run, for example the steady-state
criterion when no enzyme concentration was supplied.

```bash
grep -rn "notEvaluated" src/validation/scientificValidator.ts | head
grep -rn "notEvaluated" src/cli/ src/web/dashboard.html   # nothing
```

`notEvaluated` exists precisely so an unevaluated assumption is not reported
as a satisfied one. Then nothing shows it to anyone, which restores the
problem it was built to solve.

**Done when:** a user can see which assumptions were not checked and why.
Same shape as task 3, and the same warning applies: an unevaluated check
must not look like a passed one.

### 5. Three fields the resolver returns and the dashboard drops

`/api/resolve` returns `assayConditions` and `poolFindings`; the dashboard's
provenance panel renders neither.

```bash
grep -oE "^  (assayConditions|poolFindings)" src/literature/literatureResolver.ts
# NOTE 2026-08-16: `selectionTie` was listed here too and is not in
# src/literature/ at all -- it lives on the Python/api-server path
# (ADR 0051). Two of the three fields are real; the third sent
# readers looking for something that was never there.
# `assayConditions` now reaches the dashboard (line 877); poolFindings
# still does not, and that is the live part of this task.
grep -c "poolFindings" src/web/dashboard.html    # 0
```

`poolFindings` are facts about the *candidate pool* rather than the winning
value — including whether the evidence ranked several rows equal, and whether
the pool mixed named forms of one enzyme. On the LDH turnover table six
non-dominated rows span 21.1 to 6467.

**Done when:** a student can see that the number they were given was one of
six the evidence rated equally. Start with `renderProvenance` in
`src/web/dashboard.html`.

---

## Harder — a week, and worth it

### 6. Nobody has ever run this on Windows

`CONTRIBUTING.md` says so in as many words:

> Nobody has run them on a Windows machine, so treat that as untested rather
> than promised; if they fail, report it — a setup that only works for the
> person who wrote it is a defect.

The Makefile is POSIX shell — `command -v`, shell functions, `.venv/bin/...`
where Windows spells it `.venv\Scripts\`. The documented PowerShell fallback
is a guess.

**Done when:** either the PowerShell path in `CONTRIBUTING.md` is confirmed
working and marked as verified with the date and Python version, or it is
corrected to what actually works. Both outcomes are equally valuable. If you
have a Windows machine, this is the single most useful thing you can do for
every contributor after you.

### 7. Write a test for something already true, and prove it can fail

Find behaviour that works and is untested, and pin it.

The rule, and it is the whole point: **break it deliberately and confirm
your test goes red.** A test that passes before and after your change tested
nothing.

```bash
python scripts/check_no_vacuous_tests.py    # catches assertions that can never run
```

That guard found twelve on its first pass. It cannot find every kind — the
ones that hurt most in this codebase were assertions matching explanatory
prose instead of the clause under test, which reads fine and passes forever.

**Done when:** you can state the mutation you made, and paste the failure it
produced. Not "I tested it" — the actual red output.

---

## Before you open the PR

```bash
make pr
```

The guards CI runs, in CI's order, then the suites. A green `make pr` means
a green PR.

## 8. `sweep` throws away the unit you declared, and the README example proves it

**Severity: this one produces a wrong scientific answer, silently.**
**Files:** `src/integration/scientificPipeline.ts` (~line 1102),
`src/cli/commandSweep.ts`, `src/integration/__tests__/declaredUnitsReachTheEngine.test.ts`

Run the example printed in `README.md` and in `sweep`'s own `help`:

```bash
npx ts-node src/cli/scientificCLI.ts sweep mm \
  --parameter s0 --range 2:10:2 --km 0.5mM --vmax 0.1mM/s
```

You get:

```
      2  0.1000
      4  0.2000
      6  0.3000
      8  0.4000
     10  0.5000
  trend  increasing  (slope 1.00e-1)
```

Exactly `s0 / 20`, a straight line. Michaelis-Menten saturates; this does not.

**The kinetic parameters have no effect at all.** Verified on a settled tree
(HEAD `4fadc2d`, every file in the sweep path clean), three runs, output
identical to four decimals each time:

```bash
--km 0.5mM --vmax 0.1mM/s     # documented        -> 0.1 0.2 0.3 0.4 0.5
--km 0.5mM --vmax 6000mM/s    # vmax x 60,000     -> 0.1 0.2 0.3 0.4 0.5
--km 500mM --vmax 0.1mM/s     # km   x 1,000      -> 0.1 0.2 0.3 0.4 0.5
```

`parameterSweep` in `src/cli/advanced-features.ts` does pass them on —
`parameters: { ...baseParameters, [parameter]: value }` — so the pipeline
receives km and vmax and `response.results.finalValue` is independent of both.
`finalValue` is `points[points.length - 1].value`
(`scientificPipeline.ts:1081`), so the trajectory itself is not responding to
the rate law. Start there, not at the CLI.

> **An earlier version of this entry described different numbers** — outputs
> equal to their inputs, fixed by a 60,000x vmax. That reproduced at the time
> and does not now; the file was being edited while it was written, and the
> behaviour changed twice in ten minutes. If what you see matches neither,
> re-measure before trusting any of this. The invariant worth testing is not a
> specific number, it is: **changing km or vmax must change the output.**

The declared `mM/s` is discarded and re-read as `μM/min` by
`getAssumedUnitForUserInput()`, a table keyed on the parameter *name*:

```ts
const units: Record<string, string> = { km: 'mM', vmax: 'μM/min', ... };
```

It even logs `"User supplied a bare number; unit was ASSUMED, not declared"` —
which is false, the user declared `mM/s` — and logs it as JSON on stdout where
no student will read it.

**Why this survived.** `parseQuantity.ts` was written to kill exactly this
table; its docstring says so: *"The old CLI assigned vmax -> uM/min from a name
table... reinterpreted by a factor of 60,000 and the run continued."* And
`declaredUnitsReachTheEngine.test.ts` pins the fix — for `simulate` only. Its
own header names the `simulate` dispatcher. `sweep` reaches the pipeline by
another route and kept the original bug. A correct fix and a correct test,
both scoped to one of the two commands that needed them.

**Definition of done.** The README example consumes substrate. A declared unit
is never replaced by a table lookup on any path. The "ASSUMED" warning fires
only when the unit really was omitted. A test drives `sweep`, not just
`simulate`, and you have watched it go red by restoring the table.

**Note:** `scientificPipeline.ts` was being actively edited when this was
written, which is why it is a task here rather than a fix. Check with whoever
is in that file before starting.

### Where the unit is actually lost — read this before fixing anything

Not in the pipeline. In `scientificCLI.ts`, at the sweep case:

```ts
const baseParameters: Record<string, number> = {};   // <- the defect is this type
...
const quantity = parseQuantity(key, raw);            // correct: {value, unit, unitDeclared}
baseParameters[key] = quantity.value;                // the unit is dropped here
provenance.push({ ..., unit: quantity.unit, unitAssumed: !quantity.unitDeclared });
```

`parseQuantity` does its job. The unit is captured — into `provenance`, which
is for *display*. `baseParameters` is `Record<string, number>` and structurally
cannot carry a unit, so a bare number reaches the pipeline, and the pipeline
does the only thing it can with a bare number: looks the unit up by name.

The engine is not being lied to by the pipeline. It is being told the truth by
a type that has nowhere to put it. This is the shape this repository keeps
finding — a fact computed correctly, recorded correctly, and not reaching the
one place that needed it.

### URGENT if you are refactoring this area right now

An in-progress change in `scientificCLI.ts` adds:

```ts
function readQuantities(params?: Record<string, string>): {
  parameters: Record<string, number>;                            // same defect
  provenance: Record<string, { source: string; unit: string }>;  // unit lives here
}
```

That is the identical split, in a helper that other commands will call. It
centralises the bug instead of removing it: today only `sweep` drops declared
units, and after that helper lands, every command routed through it does.

**Fix the type, not the call sites.** Something like
`Record<string, { value: number; unit: string }>`, or convert to the engine's
canonical unit at that boundary and record that the conversion happened. Either
way the unit must travel with the number, because any pair of parallel
structures — one with the value, one with the unit — will drift again.

## What makes a task finished here

Not "the code works". The bar is:

1. You reproduced the problem before fixing it.
2. You broke your own fix on purpose and watched your test go red.
3. Your PR says what you verified and how.

If step 2 is uncomfortable, that is the correct reaction and you should do
it anyway. It has caught more real defects in this project than any other
practice, including several inside checks that were themselves written to
catch defects.
