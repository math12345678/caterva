# Stage 10, Part 17 — inhibition models, and a tested orphan

Stage: 10 · Part: 17 · 2026-08-11

## 1. A new capability, built entirely from orphaned code

```
$ scientific simulate x --resolve --model noncompetitive \
    --enzyme ldh --substrate pyruvate --organism "Homo sapiens" \
    --s0 10mM --i0 0.1mM --enzyme-conc 0.001mM

Parameters and where they came from
  s0    10 mM     user
  i0    0.1 mM    user
  km    0.5 mM    brenda_exact           BRENDA ref 111
  vmax  0.1 mM/s  brenda_exact → kcat x [E]0   BRENDA ref 333
  ki    0.02 mM   brenda_cross_species   BRENDA ref 222
        ⚠ measured in Oryctolagus cuniculus, not the organism requested

Result  Non-competitive inhibition — inhibitor binds elsewhere, lowering
        apparent Vmax without changing Km
  engine     sbml  (via SBML — no first-class domain for this model)
  initial    10.0000
  final      9.8413
```

**The engine has no domain for non-competitive inhibition.** Before this,
there was no way to simulate it here at all. It now runs — and every
parameter, including the Ki, is literature-resolved with its own citation.

That closes the task that has been open since the start of this session:
*wire Ki resolution end-to-end.*

## 2. Why this is not a fifth simulator

Two orphans covered the same ground, and only one of them could be wired
safely:

- `kinetic-models.ts` (218 lines) contains **rate equations** for
  competitive, non-competitive and product inhibition. Wiring those would
  have made a fifth implementation of enzyme kinetics in this repository.
  Every serious defect this project has found lived in a duplicate
  implementation nobody was watching — the `verifyDOI` that returned true
  for anything, the reproducibility verifier that could not fail, the kcat
  labelled "mM".
- `sbml-builder.ts` (424 lines) emits **SBML**, and the Python engine has
  an `sbml` escape-hatch domain that runs it with the same solver as every
  first-class domain.

So the model definition lives in TypeScript and the *integration* stays
where it has always been. One simulator, more models. Where the engine
already has a domain — `mm_competitive_inhibition` — that is used directly;
SBML is only for what the engine cannot otherwise do.

`kinetic-models.ts`'s remaining useful idea, knowing which model fits which
parameters, became `suggestModel` instead of a rate equation:

```
• Did you mean --model competitive? you supplied both a Ki and an inhibitor
  concentration, so plain Michaelis-Menten would ignore the inhibitor entirely.
```

That prevents a real error. Running `mm` with a Ki silently discards the
inhibitor: the run succeeds, the numbers look reasonable, and the
inhibition being studied is simply absent from the result.

## 3. A tested orphan is harder to spot than an untested one

`sbml-builder.ts` shipped with a full test file and **nothing in the
product called it**. The orphan guard missed it, because a test counts as a
reference.

The guard now distinguishes them, on the same principle that fixed
`check_plausibility_constants` in Part 12: **tests are not users.** A test
proves a module works; it says nothing about whether the product uses it.
The message says so explicitly, because a tested orphan *looks* covered,
which makes it harder to notice than a bare one.

## 4. An honest caveat, surfaced rather than buried

`buildProductInhibition` takes **Kp** — the inhibition constant of the
reaction's own product. The resolver returns **Ki** from BRENDA's Ki table,
which records a constant for a *named inhibitor*, not necessarily this
reaction's product.

Passing one as the other is a modelling assumption. The CLI prints it
whenever `--model product` is used rather than silently equating them:

> Product inhibition uses Kp… The resolved value comes from BRENDA's Ki
> table, which records a constant for a named inhibitor — confirm that
> inhibitor IS the product of this reaction before relying on the result.

## 5. Two of my own mistakes, recorded

**The echo guard fired a false positive.** The bridge rejects any parameter
the engine does not echo back, which is how `t_end`/`n_points` being
silently dropped was caught in Part 9. But the `sbml` domain echoes only
`{start, end, points}` — omitting a multi-kilobyte XML document from its
response is sensible, not a bug. Rather than weaken the check, `runTellurium`
gained an explicit `notEchoed` option, declared at the one call site that
needs it so an exemption cannot quietly cover a parameter that really was
dropped.

**A bug in my verification script nearly sent me chasing a nonexistent SBML
defect.** The assertion "inhibitor must slow the reaction" failed, which
would mean the generated SBML was wrong. It wasn't: I had passed the result
object to a helper expecting the trajectory array, so it read `NaN`. The
physics was correct throughout — 9.05 → 9.84 → 9.99 mM of substrate
remaining as inhibitor rises. The test file had it right; the throwaway
script did not.

## 6. Verification

- `tsc --noEmit -p .`: 0 errors.
- Orphan Module Guard: **6 (1,825 lines) → 4 (1,183 lines)**.
- Verified against the real Python engine: non-competitive runs via SBML
  with mass conserved to 6 dp; competitive uses the first-class domain
  (`viaSbml: false`); more inhibitor leaves more substrate, monotonically.
- New `inhibitionModels.test.ts` (12 tests) covering all of the above plus
  the refusal paths and the advisor.
- `express` and `@types/express` installed: a concurrent agent added
  `src/web/server.ts` importing a package that was not a dependency, which
  broke `tsc` for the whole tree.

**Honest limitation:** this sandbox's filesystem has degraded over the
session — a single `ts-node` spawn now takes ~33s, so jest suites that
spawn subprocesses exceed the 120s tool ceiling and could not be run to
completion here. Every assertion in the new test file was instead executed
directly against the real engine via a script, and passed. Run
`npx jest` locally to confirm the suite.

## 7. The four orphans left

| module | lines | plan |
|---|---|---|
| `advanced-analytics.ts` | 363 | correlation/trend/outlier detection — belongs behind a `sweep` command that runs a parameter range and reports where behaviour changes |
| `brenda-real.ts` | 235 | duplicates the working BRENDA path |
| `real-literature-service.ts` | 330 | a second literature service |
| `tellurium-real.py` | 255 | a second Python engine bridge |

The last three are where "make it useful" and "one source of truth" pull
against each other. Wiring a second BRENDA client would recreate exactly
the duplicate-source problem that produced a kcat labelled "mM". The useful
move is to harvest whatever they do *better* than the incumbent and fold it
in — not to give them a second entry point.
