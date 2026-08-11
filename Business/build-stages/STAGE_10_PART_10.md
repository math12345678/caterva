# Stage 10, Part 10 — the literature service finally reaches literature

Stage: 10 · Part: 10 · 2026-08-11

## 1. The last gap

Part 9 left one thing: `literatureService.ts` was an in-memory `Map`. A
caller had to hand it `Literature` objects before it could recommend
anything, and it reached no database, registry or API of its own — despite
the name, and despite `LITERATURE_INTEGRATION_GUIDE.md` describing a
literature integration. Everything it "recommended" was something the
caller already had.

Terrium's real literature layer is `Tests/fallback_logic.py`
(`resolve_kinetic_value`): BRENDA exact match → BRENDA cross-species →
PubMed candidates, returning a value, its unit, the organism it was
measured in, a citation, and STRENDA assay conditions — or an honest
`found: false`. It never fabricates a number.

Production already reaches it through `science_agent_runner.py`, spawned by
`lib/scienceAgent.ts`. `src/literature/literatureResolver.ts` spawns the
**same script over the same protocol**. A third path to the same data would
be a third thing to keep in sync, and this repository has been bitten by
duplicate sources of truth repeatedly.

## 2. Two distinctions the bridge is built around

**`found: false` is an answer; "could not look" is not.** BRENDA saying it
has no Km for this system is information. A 403, a missing script or a
timeout is not, and returning `found: false` for either would let an
unchecked value look checked. The former returns `null`; the latter throws
`ResolverUnavailableError`.

**A value without its unit is not a measurement.** The resolver rejects a
`found: true` result that arrives with no unit rather than labelling it
from the parameter's name. Km in mM and Km in μM differ by 1000×, and this
tree has now been bitten by assumed units twice (Parts 8 and 9).

A cross-species match — real, citable, but measured in a *different*
organism than the one asked about — is flagged rather than presented as an
exact match, and carries reduced confidence with the substitute organism
named in the warning.

## 3. A bug the first live call found immediately

Pointing the bridge at real BRENDA returned:

```
ResolverUnavailableError | Literature resolver exited with code 1
```

The runner had actually printed `{"ok": false, "error": "403 Forbidden"}`
**and** exited 1. Treating a non-zero exit as fatal before parsing stdout
replaced a precise cause with an exit code. Now stdout is parsed whenever
there is any, and the same call reports:

```
ResolverUnavailableError | 403 Forbidden
```

That is the difference between "BRENDA refused the request" and no
information at all.

## 4. Tests that spawn a real subprocess

`literatureResolver.test.ts` (10 tests) runs an actual Python subprocess
against a stub runner via a `TERRIUM_LITERATURE_RUNNER` seam, rather than
mocking the module. The subprocess boundary is precisely where this
module's bugs were — mocking `resolveKinetic` would have tested nothing
that broke. Mutation-verified: restoring the "non-zero exit discards
stdout" behaviour fails the corresponding test, and reverting restores it.

Covered: the unit travelling with the value; reading the value from the key
matching the quantity (a Ki emitted under `ki` must never be read as a Km —
ADR 0008); cross-species flagging; `found: false` as an answer; refusal of
an unlabelled value; the structured-error-on-non-zero-exit regression;
empty output; invalid JSON; and a missing script not being mistaken for
"no literature".

## 5. The pipeline uses it

`SimulationRequest` gained an optional `system` — enzyme, substrate,
organism, EC number. When present, `resolveParameters` resolves missing
constants through the real chain. When absent, it does **not** infer them
from the free-text `query`: guessing an enzyme or organism out of prose
would attach a real citation to a system the user never named, which is
provenance for the wrong measurement and worse than none.

A parameter the literature has nothing for is now left *unresolved* and
logged, rather than dropped silently. Downstream, validation reports it and
`runTellurium` refuses to start without it — the same hard rule the engine
enforces via ParameterOrigin.

## 6. Verification

- `tsc --noEmit -p .`: **0 errors.**
- Root tree: **123 of 123 tests passing**, across 7 suites. This tree had
  never compiled and had never run a test four parts ago.
- Guards individually: TypeScript Compile, Engine Contract, Guard Wiring,
  Documented Counts, Plausibility Constants, RNG Convention, Domain Parity,
  Literature Inventory — all pass. (The aggregate `verify_build.py --quick`
  exceeds the review sandbox's 120s tool ceiling on wall-clock; it passed
  end-to-end in Part 9 at 79.3s and no guard has regressed since.)
- Engine suite unchanged: 280 passed, the same 9 `test_popgen_resolver`
  failures from `stdpopsim` being uninstallable here.

## 7. Honest state of the tree

It is wired. Simulation runs in the real engine; literature resolves
against the real BRENDA/PubMed chain; units come from the data; missing
parameters stop the run.

What remains true and should not be overstated:

- **The live path is unproven from this sandbox.** BRENDA returns 403 here,
  so the end-to-end resolve has been verified as far as "the request is
  correctly formed and the error is correctly surfaced". The first thing to
  do on a networked machine is run a real resolve and confirm a value and
  citation come back.
- **`AssumptionValidator`'s steady-state check is still inert.** It needs
  `e0`, which nothing resolves yet, so it reports `notEvaluated` on every
  run. Honest, but Layer 3's first check does no work until enzyme
  concentration is resolved like the other parameters. `kcat` is resolvable
  and `Vmax = kcat·[E]0`, so resolving `e0` would close both this and
  ADR 0019's gap at once.
- **The Literature Inventory guard still reports 25%.** 10 of 40
  scientific numbers trace to a source; 30 remain teaching defaults. None
  of this stage's work changed that figure, and it should not be described
  as improved.
