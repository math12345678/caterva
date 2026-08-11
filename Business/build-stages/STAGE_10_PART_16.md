# Stage 10, Part 16 — wiring the orphans instead of deleting them

Stage: 10 · Part: 16 · 2026-08-11

## 1. The instruction, and why it was the better call

Part 15 ended with a diagnosis: one commit had added 2,009 lines across
seven modules that nothing imported, and my recommendation was to delete
them. The instruction back was *"Nothing will be deleted if it is of no
use. Make it useful. If there are some flowers that are doing nothing,
make them do something."*

That is the better call, and the reason is not sentiment. Deleting
`advanced-features.ts` would have thrown away a working sensitivity
analysis; deleting `job-manager.ts` would have thrown away the answer to a
gap this project had already documented twice. The orphan problem was never
that the code was bad — it was that nobody had connected it to anything.

Two of seven are now wired, and both closed real gaps.

## 2. `advanced-features.ts` → `simulate --sensitivity`

Sensitivity analysis on its own is ordinary. What makes it worth having
here is that Terrium already knows the **provenance** of every parameter,
so the two can be printed in one table:

```
Parameters and where they came from
  km    0.14 mM    brenda_cross_species  BRENDA ref 12345
        ⚠ measured in Oryctolagus cuniculus, not the organism requested

Sensitivity  (±10% on each parameter)
  s0      13.2%   user
  vmax     3.3%   brenda_exact → kcat x [E]0
  km       0.1%   brenda_cross_species
```

The cross-species Km looks alarming on its own. Sensitivity says the answer
barely moves with it — **0.1%** — while the substrate concentration the
user chose moves it **13.2%**. That is a real conclusion, and neither
number produces it alone: a sensitivity table without provenance cannot say
which parameters are shaky, and a provenance table without sensitivity
cannot say which shakiness matters.

Three defects were fixed in the module before wiring it:

- **A `catch` that dropped failures.** A parameter whose analysis threw was
  logged and skipped, so it vanished from the results — indistinguishable
  from one measured to have *no* influence, which is the opposite
  conclusion. Failures are now recorded with their reason.
- **No baseline validity check.** A run that fails validation returns
  `finalValue: 0`, and every sensitivity was then computed by dividing by
  it, producing `Infinity`/`NaN` rendered as a confident-looking table for
  a simulation that never executed. It now refuses with the validation
  errors.
- **No divide-by-zero guard** on a legitimately-zero baseline.

### The category distinction, again

The first working version flagged `s0` as *"load-bearing and not solid — no
literature citation"*. Wrong, and wrong in a way this codebase has now hit
three times: **s0 is an experimental condition, not a measurement.** Nobody
measures "the initial substrate concentration of this enzyme"; the
experimenter picks it, so "no citation" is not a defect there.

The report now separates them, because the remedies differ:

- *load-bearing and weakly sourced* → **measure this for your own system**
- *load-bearing and chosen by you* → **state it precisely in your methods;
  another lab picking a different value will not reproduce your numbers**

## 3. `job-manager.ts` → `history`, and two commands that finally work

369 lines with a queue, a status model and statistics — all held **in
memory**, which is precisely the wrong lifetime for a CLI. A CLI process
exits after each command, so the store is empty on the next invocation.

That is why `scientific verify <jobId>` and `check-integrity <jobId>` could
never work: `simulate` printed a job id, the process exited, and no later
command could resolve it. The gap was named in Parts 14 and 15 as "jobs do
not survive the process".

The module was given the one thing that made it useful — persistence — and
`simulate --resolve` now records each completed run, with its full
provenance, to `~/.terrium/history.json`:

```
$ scientific history

Past runs  ~/.terrium/history.json

  job_1786482315116_nhof2pfdv  2026-08-11 21:05:16  ldh / pyruvate
                               final 7.5395 · 2/4 parameters cited
```

Design decisions worth naming:

- **Best-effort, but reported.** A CLI must not fail a valid simulation
  because it could not write a convenience file — but the failure is
  printed. A user told a job id who then finds `verify` cannot see it has
  no way to diagnose that from silence.
- **A corrupt file cannot break the CLI.** Unreadable JSON is treated as
  empty history, not an exception.
- **Bounded to 200 runs.** History is a convenience, not an archive, and an
  unbounded file read on every invocation gets slow.

## 4. Verification

- `tsc --noEmit -p .`: 0 errors.
- New: 9 `jobHistory` tests (all passing, no subprocess), covering the
  round trip, `findRun`, append-not-overwrite, directory creation,
  bounding, provenance preservation, corrupt files, and a reported write
  failure.
- Orphan Module Guard: **7 orphans (2,016 lines) → 5 (1,401 lines)**. It is
  now a live worklist rather than a wall of red.
- `simulate --resolve --sensitivity` verified end to end against a stub
  runner: resolves, runs the real engine five times, and reports.

**Honest limitation:** the CLI end-to-end suite spawns `ts-node` per test
and each now takes ~33s on this sandbox's filesystem, so the full 17-test
file exceeds the 120s tool ceiling here. Individual tests pass when run
alone. The whole suite passed at 205/205 before this part, and nothing in
these changes touches the tested paths — but that is an inference, and it
should be confirmed with a local `npx jest`.

## 5. The five orphans still to wire

| module | lines | the honest plan |
|---|---|---|
| `advanced-analytics.ts` | 363 | correlation/trend/outlier detection — belongs behind a `sweep` command that runs a parameter range and reports where the behaviour changes |
| `kinetic-models.ts` | 218 | **must not** be wired as a simulator; it would be a 5th implementation of Michaelis-Menten. Its catalogue of inhibition models should instead power a *model advisor*: "you supplied a Ki — you want `mm_competitive_inhibition`, not `mm`" |
| `brenda-real.ts` | 235 | duplicates the working BRENDA path; either fold its useful parsing into the real resolver or retire it |
| `real-literature-service.ts` | 330 | same — a second literature service |
| `tellurium-real.py` | 255 | a second Python engine bridge next to `tellurium_runner.py` |

The last three are the ones where "make it useful" and "one source of
truth" genuinely pull against each other. Wiring a second BRENDA client
would recreate exactly the duplicate-source problem that produced a kcat
labelled "mM" and a `verifyDOI` that returned true for anything. The useful
move there is to harvest whatever they do *better* than the incumbent and
fold it in — not to give them a second entry point.
