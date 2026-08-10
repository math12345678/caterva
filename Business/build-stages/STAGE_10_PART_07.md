# Stage 10, Part 7 — a reproducibility verifier that could not fail, and a guard that could not fire

Stage: 10 · Part: 7 · 2026-08-10

## 1. The guard that started it

Part 6 ended with a recommendation: the root `src/` tree has no
`tsconfig.json`, so `check_typescript_compiles.py` — which discovers
workspaces *by* their tsconfig — could not see it. Extending the guard to
report any unguarded `.ts` region was the obvious next step.

The first implementation used `REPO_ROOT.rglob("*.ts")` and filtered
`SKIP_PARTS` afterwards, so it enumerated `node_modules` before discarding
it. It timed out at 120s, twice. Fixed by pruning during traversal
(`os.walk` with in-place `dirnames` mutation) and adding `.venv`,
`.pytest_cache`, `.mypy_cache` and friends to `SKIP_PARTS`: 120s+ → 8s.

It then reported three unguarded trees — `src/`, `examples/`, `landing/` —
which was correct.

**And then adding a root `tsconfig.json` to fix `src/` made the guard
vacuous.** Its test was "does a tsconfig.json exist at or above this
directory". Once one existed at the repository root, *every* directory in
the repo found it by walking up, so the function could never return
anything again. It reported "no unguarded trees" because it was
structurally incapable of reporting anything else.

That is the same defect as the health endpoint in Part 5 that could never
say `degraded`, and the `verifyDOI` in Part 6 that could never say `false`.
I introduced it while fixing the thing it was built to find.

Rewritten to ask the compiler instead of guessing: each project is run
with `tsc --noEmit --listFiles`, and any first-party `.ts` not in the union
of those file lists is unguarded. Membership is now decided by tsc's own
resolution — includes, excludes, `extends`, `references` and all — rather
than by a heuristic that reimplements it badly.

Result on the current tree: **304 of 312 files covered, 8 not.**

## 2. What "never type-checked" was hiding

`src/` shipped with a `package.json` advertising

```json
"type-check": "tsc --noEmit",
"build": "tsc",
"verify-all": "npm run type-check && npm run lint && npm test",
"bin": { "scientific": "src/cli/scientificCLI.ts" }
```

and no `tsconfig.json` for any of it to use. With no config and no file
arguments, `tsc --noEmit` prints its own help text and exits 1 — so
`verify-all` died at step one having checked zero files, and never reached
`npm test`.

Given a tsconfig, the tree produced **8 errors**, the first of which was
fatal to all of it:

```
src/integration/scientificPipeline.ts(15,24): error TS2307:
  Cannot find module '../logger' or its corresponding type declarations.
```

`src/logger.ts` **did not exist**. Four of the tree's five modules opened
with `import { logger } from '../logger'`. The advertised `bin` entry
crashes on startup. Nothing in this "Production-ready scientific validation
and reproducibility framework" had ever run.

Written as a dependency-free pino-compatible logger (`src/logger.ts`):
the tree's `dependencies` are `{}` and there is no network in review, so
un-breaking the import by adding pino would have made the tree
unbuildable rather than buildable.

Remaining 7 errors, all real:

| Error | Reality |
|---|---|
| `SimulationRequest` not exported by `literatureService` | It is declared in `scientificPipeline.ts`. The integration test imported it from the wrong module — 9 usages, never compiled. |
| `.code`/`.message` on `string` | `validate()` returns `errors: string[]`. Every validation failure would have rendered `"undefined: undefined"`. |
| `runSimulation` arity | The verifier calls its reproducer with one object; `runSimulation` takes two positional args, so `conditions` arrived `undefined` on every replay. |

`tsc --noEmit -p .` on the root tree: **8 errors → 0.**

## 3. The reproducibility verifier could not fail

With the tree compiling, its tests could run for the first time: **59
tests, 22 failing.** The reproducibility engine held six compounding
defects.

```ts
const reproduced = await reproducer({...});

const comparison = this.compareOutputs(
  originalRecord.output,
  reproducer            // <- the FUNCTION, not `reproduced`
);
```

and inside `compareOutputs`:

```ts
const repro = reproduced?.trajectory?.[i]?.value || orig;  // <- missing point
                                                           //    scores as a match
```

A function has no `.trajectory`, so every point fell through to `|| orig`
and compared `orig` against itself. **`maxRelativeError` was always exactly
0.** `passed` reduced to `inputHashMatch`, and the summary always read
`✓ FULLY REPRODUCIBLE (max error: 0.00e+0)`.

`inputHashMatch` was itself always false for any record carrying real
parameters: `createRecord` hashed the raw `parameters` argument while
storing `serializeParameters(parameters)`, a different object.
`outputHash` had the identical flaw against the stored
`{ trajectory, metrics }` projection — and since the real
`runSimulation` returns `{ trajectory, finalValue, computedMetrics }`,
**every record the pipeline ever produced was reported "Output data
corrupted"** by `DataIntegrityChecker`.

The rest:

- An empty original trajectory returned `maxRelativeError: 0` — a perfect
  score on no evidence, which sailed past the tolerance test.
- Points where `orig === 0` were `continue`d, so a reproduction returning
  500 where the original was 0 contributed nothing.
- `meanRelativeError` divided by the full trajectory length including
  skipped points, diluting itself toward 0.
- `differences.conclusion` was the constant string *"Results numerically
  equivalent within expected precision"* for **any** non-zero error — a
  400% disagreement reported as equivalent.
- An empty `executionTrace` (which every freshly created record has) counted
  as *data corruption*, so `checkIntegrity` returned `intact: false` for
  healthy records and `scientificCLI.ts` — `process.exit(result.intact ? 0 : 1)`
  — exited nonzero on them. Now separated into a `warnings` channel.

### The tolerance is no longer a constant

`passed` used a hardcoded `< 1e-6`. It now uses the standard mixed
absolute–relative criterion

```
|original − reproduced|  ≤  atol + rtol · |original|
```

with **both tolerances read from the record's own `solver` block**. This is
the criterion used by SUNDIALS/CVODE's weighted error norm,
`scipy.integrate.solve_ivp` and `numpy.allclose`. Two reasons it is the
right one here: a bare relative test is undefined at 0 and explodes near
it, so trajectories that decay to zero — most of them — fail on values the
solver never claimed to resolve; and the record stores `absoluteTolerance`
alongside `relativeTolerance`, so using only the relative one discarded
half the solver's accuracy contract. A run integrated to a tighter
tolerance is now held to a tighter reproducibility standard automatically.

## 4. Verification

`src/reproducibility/__tests__/reproducibilityRegressions.test.ts` — 14
tests, none of which the existing suite covered. Each was **mutation-tested
by restoring the original defect and confirming failure**:

| Mutation restored | Tests failed |
|---|---|
| `compareOutputs` receives the reproducer function | 3 |
| `\|\| orig` fallback | 1 |
| `inputHash` over raw parameters | 1 |
| `outputHash` over raw output | 1 |
| empty original scores 0 | 1 |
| empty trace counts as corruption | 7 |

**Two of those mutations initially passed against my own new tests.** The
fixtures happened to dodge the defect: `serializeParameters` projects onto
exactly `{value, unit, source, confidence}`, and my test parameter already
had precisely that shape, so serialization was an identity and the raw-vs-
stored hash difference never manifested. Same for the output fixture,
which was already exactly `{trajectory, metrics}`. Both fixtures were
rewritten to be lossy — carrying provenance fields the projection drops,
which is what real resolved parameters look like. Tests that look right and
prove nothing are the reason mutation testing is not optional here.

Test counts: reproducibility suite **19 → 33 passing, 0 failing**. Root
tree overall: **22 failures → 16.**

## 5. Still open, stated plainly

- **16 tests still fail** in the validation and integration suites. Most
  are network-dependent: `verifyDOI` now genuinely calls CrossRef and
  PubMed (Part 6), and the review sandbox blocks outbound HTTPS. But at
  least one is not — `AssumptionValidator › should PASS when assumptions
  hold` fails because `calculateSubstrateDepletion(s0=100, vmax=10, t=10)`
  correctly returns 100% depletion, and the test asserts those physically
  inconsistent numbers should pass. The *test* is wrong.
- **`AssumptionValidator`'s thresholds are hardcoded and unsourced**: a 5%
  depletion limit, a 4–45 °C "typical range", a pH 5–9 range, and
  `steadyStateTime = (km/vmax) * 5`. None carries a citation. This violates
  the project's core rule directly and is the next thing to fix in this
  tree — or the reason to delete it.
- **The tree is still unwired.** `literatureService.ts` is an in-memory
  `Map`; `runSimulation` is a hardcoded Michaelis–Menten toy with
  `parameters.km?.value || 5.0` fallbacks and no connection to the
  Tellurium engine. Part 6's recommendation stands: wire it to the real
  resolvers or delete it. It now compiles and runs, which makes either
  choice cheaper, but does not make it real.
- **`landing/src/components/VerificationConsole.tsx` is not type-checked.**
  It imports `react`, and neither `react` nor `@types/react` is installed
  anywhere in the repo. `landing/tsconfig.json` covers `src/lib` only — so
  the Wright-Fisher drift code is checked and the JSX shell is not. The
  guard reports this every run.
- **`probe_tmp.ts` must be deleted** (`rm probe_tmp.ts`). A scratch file I
  created while probing this behaviour; the review sandbox permits writes
  but not deletes, so it could not be removed from where it was made. The
  TypeScript guard fails on it deliberately until it is gone.
- **Six build-tool configs** (`vite.config.ts`, `vitest.config.ts`,
  `drizzle.config.ts`, `orval.config.ts`) are type-checked by nothing.
  Reported every run but not failing the build, for a reason written down
  in the guard: a broken build config fails loudly and immediately, whereas
  an unchecked application module ships. Remedy is a `tsconfig.node.json`
  per workspace.

`verify_build.py --quick`: every other guard passes; the TypeScript Compile
Guard fails on the two items above. That red is correct — it is the guard
telling the truth about a repository that contains a stray scratch file and
an uncompiled component.
