# Stage 9, Part 2 — kcat → Vmax bridge, epidemiology wired to RESOLVABLE_FIELDS, two more concurrent-agent build breaks repaired

Stage: 9 · Part: 2 · 2026-08-09

## 0. What this part does

Part 1 closed Ki resolution and repaired a broken TypeScript build. This
part closes the two carried-forward items Part 1 named — kcat → Vmax (ADR
0019) and epidemiology's `RESOLVABLE_FIELDS` wiring (ADR 0020) — and
repairs two further build breaks introduced by the same concurrent
"verifiable metrics" feature work landing mid-session.

## 1. kcat → Vmax bridge (ADR 0019, closed)

A resolved kcat literature value now combines with a caller-supplied
`enzyme_conc` override into a `vmax` the SIR engine can run, via
`applyVmaxFromKcatResolution()` in `queryResolver.ts`. The arithmetic and
its Rule 2 bounds live in exactly one place — `bridge_vmax_from_kcat()` in
`science_agent_runner.py`, which calls
`Tellurium.core.validation.vmax_from_kcat()` directly (imported as
`core.validation` with only `Tellurium/`, not the package root, on
`sys.path` — reaches the pure-arithmetic module without pulling in
antimony). `ParameterOrigin` is not extended: `vmax`'s provenance stays
`origin: "resolved"` with the kcat citation, plus a `note` that names the
caller-supplied `enzyme_conc` value explicitly as never resolved or
defaulted (ADR 0013).

Real, independently re-verified case: acetylcholinesterase + acetyl
thiocholine + *Homo sapiens*, kcat = 6500 s⁻¹ (BRENDA ref 649716) ×
enzyme_conc = 0.001 mM → Vmax = 6.5 mM/s. 4 new tests in
`vmaxFromKcatProvenance.test.ts`, mutation-tested (inverted the
`vmaxValidation.ok` guard, confirmed the happy-path test failed, reverted).

## 2. Epidemiology wired to RESOLVABLE_FIELDS (ADR 0020, closed)

A recognized disease name (currently just COVID-19 — the sole ADR 0017
registry entry) now bridges its literature (R0, infectious period) into
the SIR engine's own (beta, gamma), via `applyBetaGammaFromR0Resolution()`.
Unlike kcat, this needs no caller-supplied half — R0 and infectious period
are both intrinsic disease properties — so the gate is simpler: fires when
neither `beta` nor `gamma` is already supplied; if either is present, the
bridge is skipped entirely rather than mixing a literature rate with an
arbitrary caller-chosen one.

Caught and fixed during this part, not after: `buildResolvedKineticProvenance()`
(the helper Ki/Km/kcat provenance uses) unconditionally runs the STRENDA
pH/temperature check and silently downgrades `citationStatus` from
`"verified"` to `"flagged"` when assay conditions are absent — correct for
kinetic constants, meaningless for an epidemiological R0 (a disease has no
pH). `beta`/`gamma`'s provenance is built directly instead. The same latent
issue exists, unfixed, in the already-shipped `mutation_rate` resolution
path — named as a carried-forward item rather than touched, since fixing it
would disturb already-tested, shipped behavior outside this part's scope.

4 new tests in `betaGammaFromR0Provenance.test.ts` — **deliberately not
mocked at the science-agent boundary**, unlike every other provenance test
in this codebase: they spawn the real Python process and read the real
ADR 0017 registry, so a pass is a genuine unmocked end-to-end proof, not a
fixture replay. Mutation-tested (flipped the `||` gate to `&&`, confirmed
the no-mixed-sourcing test failed, reverted).

## 3. Two more concurrent-agent build breaks (found and repaired)

The same "verifiable metrics" feature work from Part 1 continued landing
mid-session, twice more, each time breaking the TypeScript build the same
way as before: a caller (`queryResolver.ts`) called a
`VerifiableMetricsCollector` method that did not exist yet.

1. **`recordStageExecution(stageName, durationMs, success)`** — missing
   entirely; the class already had unused private `stageMetrics` state
   declared for exactly this. Implemented against it.
2. **`reset()` and `getSnapshot()`** — needed by a new test file,
   `literature-backed-e2e.test.ts`. `getSnapshot()`'s domain-metrics
   section initially assumed the WRONG internal shape
   (`{attempts, successes, latencies}`, from Part 1's own earlier
   `recordDomainUsage` implementation) — a concurrent edit had silently
   replaced that implementation with a different shape
   (`{count, avgResolutionMs, parameterSuccessRate, samples}`) without
   notice. Caught by running the test, not assumed from reading the code;
   fixed to match the actual current shape.

The same new test file also had the two familiar recurring defects: `pH`
instead of the canonical `ph` (3 occurrences, fixed), and 7 of its 12
initial test queries omitted required parameters (`s0`, `end`, `points`,
etc.) that the project's own hard-block rule (no simulation runs on an
`origin: "default"` parameter) has always required explicitly — not a code
bug, a test-authoring gap; fixed by adding the missing values to each
query. One assertion (`avgLatencyMs > 0`) was also flaky by construction
(a fast deterministic resolution can genuinely complete in under 1ms) and
loosened to `>= 0`, matching how sibling assertions in the same file
already handle this metric.

After all four fixes: `tsc --noEmit -p .` clean, 26 test files, 374/374
tests passing.

## 4. Carried forward

1. **The `mutation_rate` STRENDA-downgrade issue** (§2 above) — latent,
   pre-existing, unfixed. `applyPopgenResolution` uses
   `buildResolvedKineticProvenance` for a field STRENDA does not govern,
   silently marking resolved mutation-rate citations `"flagged"` instead of
   `"verified"`. Low priority (cosmetic — the value itself is still
   correct and still resolved) but worth a dedicated small fix later.
2. **The 8 self-narrated root-level `.md` "session summary" files** —
   still present, still unevaluated for keep-vs-remove.
3. **Git commits still cannot be sealed from the review sandbox** — same
   fuse-mount `unlink` restriction as Part 1. All fixes in this part are on
   disk and staged; sealing the commit requires running `git commit` from
   a real terminal on the actual development machine.
4. **SEIR has no epidemiology bridge.** Deliberately out of scope for ADR
   0020 — see the ADR for why SIR's peak-condition verification doesn't
   transfer to SEIR's extra exposed compartment without separate checking.

## 5. References

- ADR 0019 — kcat → Vmax bridge, full decision record.
- ADR 0020 — epidemiology → beta/gamma bridge, full decision record.
- Golden case: AChE + acetyl thiocholine, kcat = 6500 s⁻¹, ref 649716.
- Golden case: COVID-19, R0 = 3.14, infectious period = 5.45 days, PMID
  33214421 (Hussein et al. 2021).
