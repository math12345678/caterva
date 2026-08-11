# Stage 10, Part 9 — the tree stops pretending and runs the real engine

Stage: 10 · Part: 9 · 2026-08-10

## 1. The decision, and why it went this way

Parts 6–8 left one question open: wire the root `src/` tree to the real
resolvers, or delete it. It is wired.

The deciding fact is that the wiring turned out to be small. Production
already reaches the engine one way — `spawn(python, [tellurium_runner.py])`
with JSON over stdin/stdout — so the tree did not need a new mechanism, it
needed to stop having its own.

## 2. `runSimulation` was not running a simulation

```ts
let s = parameters.s0?.value || 1.0;
const km = parameters.km?.value || 5.0;
const vmax = parameters.vmax?.value || 10.0;
for (let t = 0; t <= t_end; t += dt) {
  const v = (vmax * s) / (km + s);
  s = Math.max(0, s - v * dt);
}
```

Three problems, worst last:

1. A duplicate implementation of a model the Python engine already has,
   integrated with fixed-step explicit Euler rather than the engine's
   adaptive solver. Two implementations of one model guarantee results that
   disagree with the product's own answer.
2. `Math.max(0, ...)` clamps negative substrate instead of reporting that
   the step was too large — so it produced a plausible curve in exactly the
   regime where it was wrong.
3. `|| 5.0`, `|| 10.0`, `|| 1.0`. A missing Km silently became 5.0 and the
   run continued, emitting a trajectory and a provenance record for a
   number no literature, user or resolver ever supplied. This is the exact
   thing Terrium exists to refuse, and the engine's own ParameterOrigin
   rule forbids.

Replaced by `src/engine/telluriumBridge.ts`, which spawns the same runner
the api-server uses. Missing parameters raise `MissingParameterError`
*before* the process starts. Physical validity stays the engine's call —
Rule 1 rejections are surfaced verbatim, Rule 2 flags are preserved on the
result.

Verified against the real engine, not a mock: mass conservation
(`[S] + [P] = s0` to 6 dp), monotonic substrate decay, byte-identical
determinism across runs, and a negative-Km rejection. The suite skips
*loudly* if Python is unavailable, because a green tick from a suite that
silently skipped its only real assertion is worse than a red one.

## 3. The unit fabrication, a third time — and the actual fix

The hardcoded `vmax / 1000` ("convert μM/min to mM/min") came back a third
time, moved to the call site in `execute()`, now with `|| 0` — so a missing
Vmax became zero, which reads as "no substrate consumed" and passes every
depletion check.

Constants were never going to hold, because the real information was
present the whole time: parameters carry a declared `unit` string, and
`ParameterMetadata.unit` is part of the public shape. `src/units.ts` now
does the conversion from those strings. An unrecognised unit raises; it is
never passed through and never defaulted.

Two things this exposed that a constant could not have:

- **`convertRate` converts the time component too.** `60 mM/min` is
  `1 mM/s`. A divisor that only touches the concentration half leaves the
  rate wrong by 60×.
- **Specific activity is rejected outright.** `umol/min/mg` is amount per
  time per mass of protein, not concentration per time; converting needs
  [E] and molecular weight. BRENDA reports turnover in exactly this form —
  this tree's own fixtures contain it — so silently reading it as
  `umol/min` would produce a physically meaningless number from real data.

### The bug underneath the bug

`ParameterRecommender.recommend` took a weighted mean of `p.value` across
sources **without ever reading `p.unit`**. If one source reported Km in mM
and another in μM — routine; BRENDA carries both — the "recommended value"
was the average of quantities in different units, which is not a quantity.

It was undetectable downstream because `getDefaultUnit` then labelled the
result with a unit guessed from the parameter's *name*, so the label always
agreed with the assumption and never with the data. Recommendations now
carry the unit their sources reported, values are converted onto a common
basis before averaging, and incompatible units raise with both DOIs named.

`getDefaultUnit` survives only for user-supplied bare numbers, renamed
`getAssumedUnitForUserInput` and logging a warning on every use, so the
assumption appears in the run record instead of being implicit.

## 4. A guard that catches silently-ignored parameters

The bridge first sent `t_end` and `n_points`. `tellurium_runner.py` reads
`end` and `points`. The mistake was nearly invisible: the runner's default
`end` is also 10.0, so the window looked right while resolution silently
stayed at the default 51 instead of the requested 101.

The engine echoes the parameters it used, so the bridge now compares
requested against echoed and rejects any key the engine dropped. It caught
the tree's own tests on the next run, which is the correct outcome.

## 5. Every TypeScript file in the repository is now type-checked

- `@types/react` installed, so `landing/tsconfig.json` covers
  `src/components/VerificationConsole.tsx` rather than only `src/lib`.
- `tsconfig.node.json` added to five workspaces for their build-tool
  configs, and the guard extended to discover `tsconfig*.json` rather than
  only the exact name — without which correctly-wired configs would still
  have reported as uncovered.

**Type-checking `orval.config.ts` for the first time found a live bug.**
`prettier: true` is not an option in orval 8; the key is
`formatter: "prettier"`. Unknown keys in a config object are not runtime
errors, so orval had been silently ignoring it and the generated API client
was never formatted, despite the config saying it was. Fixed in both
places.

`check_typescript_compiles.py` now reports zero uncovered files and zero
notes.

## 6. Verification

- `tsc --noEmit -p .` (root tree): **0 errors.**
- Root tree tests: **113 of 113 passing.** At the start of Part 7 this tree
  had never compiled, and its 59 tests had never run; 22 failed the first
  time they did.
- `python scripts/verify_build.py --quick`: **ALL CHECKS PASSED**, 15
  guards, 79.3s.
- api-server `tsc --noEmit`: 0 errors. Engine suite unchanged (the 9
  `test_popgen_resolver` failures are `stdpopsim` not installable in the
  review sandbox and predate this work).

## 7. What is genuinely left

- **`literatureService.ts` is still an in-memory `Map`.** The simulation
  path is now real; the literature path is not. A caller must still hand it
  `Literature` objects. Connecting it to the resolvers that already exist
  (`Tests/fallback_logic.py` for BRENDA, `popgen_resolver.py`,
  `epidemiology_resolver.py`) is the remaining piece, and it is now the
  only thing between this tree and being fully wired.
- `AssumptionValidator`'s steady-state check needs `e0`, which the pipeline
  does not yet resolve — so it reports `notEvaluated` on every real run.
  Honest, but it means Layer 3's first check is inert until enzyme
  concentration is resolved like the other parameters.
- The 5% depletion convention still has no primary source and is still
  reported as a convention (Part 8 §4).
