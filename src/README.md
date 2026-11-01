# `src/` — the TypeScript surface

Everything a person or another program touches. The science is in
[`caterva/`](../caterva/README.md) and [`Tests/`](../Tests/README.md); this
directory is how it reaches anyone.

## Layout

| path | what it holds |
|---|---|
| `cli/` | `scientificCLI.ts` and the subcommands — `commandResolve`, `commandSimulateResolved`, `commandSweep` |
| `web/` | `server.ts` (the HTTP surface) and `dashboard.html` (the page a student actually opens) |
| `engine/` | `catervaBridge.ts` — spawns the Python engine. Also batch, sweep and model-comparison drivers |
| `literature/` | `literatureResolver.ts`, `literatureService.ts` — the TypeScript side of the resolution chain |
| `validation/` | `scientificValidator.ts` (assumption checks), `runConditions.ts` (what conditions a run is at) |
| `integration/` | `scientificPipeline.ts` — orchestrates resolve → validate → simulate → record |
| `execution/` | job management and history |
| `storage/`, `reproducibility/`, `analysis/`, `integrations/` | persistence, replay records, analysis helpers, external API clients |

## The rule this directory keeps breaking

**A value that is computed, correct, and never reaches anyone is a value
that does not exist.**

Five separate defects of exactly this shape have been found here, each one a
boundary whose receiving type had no field for something the sender
computed:

| ADR | what was dropped |
|---|---|
| 0027 | the API server discarded the runner's reliability score and recomputed a worse one |
| 0038 / 0039 | the runner dropped four pool-finding detectors' output |
| 0040 | `literatureResolver` dropped variant, effectors and buffer identity |
| 0055 | `ParameterRecommendation` had no field for assay conditions, so a hardcoded 37 °C looked like the only option |

Every one had passing tests throughout, because each test covered the
computation and none covered the boundary.

**So: when you add a field, follow it to a surface.** If nothing renders it,
it is not done. `scripts/check_findings_reach_a_surface.py` catches some of
this; it does not catch all of it.

## Running it

```bash
npx tsc --noEmit -p .              # must be clean; CI enforces it
npx jest src/validation            # one area
npx jest                           # all TypeScript suites
npx ts-node src/cli/scientificCLI.ts --help
```

## Things that will bite you

**The dashboard has no build step.** `dashboard.html` ships its JavaScript
inline, and `server.ts` serves that one file and 404s everything else. There
is no bundler and no `<script src>`; adding one is a security-relevant change
to static file serving, not a refactor
([ADR 0048](../docs/adr/0048-the-dashboard-gets-a-test-harness.md)).

Its tests read the real HTML, extract the inline script and evaluate it in a
Node `vm` against a stub DOM — `src/web/__tests__/dashboardParameterGate.test.ts`.
That is deliberate: it exercises the code that actually runs rather than a
copy, and a copy is the defect this project has hit repeatedly.

**No numbers in the markup.** `scripts/check_no_unsourced_ui_numbers.py`
fails the build if a displayed metric is written as static HTML, or if a
measured-parameter input carries a `value`. Its allowlist is empty on
purpose.

**Do not reimplement a Python check in TypeScript.** The engine is the
contract. `vmax_from_kcat()` and `beta_gamma_from_r0()` are called *through*
the bridge for this reason.
