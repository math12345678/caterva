# Caterva — site

Marketing site for Caterva, a scientific verification engine.

The premise: a page arguing that scientific claims must be independently
checked should not itself be a wall of unchecked claims. So it computes. The
shell evaluates the Michaelis-Menten rate law on two cited BRENDA constants
and runs exact Gillespie simulations against their closed forms, in the
browser, when you press enter.

## Run it

```bash
npm install
npm run dev        # http://localhost:5173
npm run build      # production build into dist/
npm run typecheck  # tsc --noEmit
npm test           # node --test tests/ (Node >= 23.6, which runs the .ts it imports)
```

## What's actually live

| Element | What it really does |
|---|---|
| Background lattice | decoration: a clamped, damped Lennard-Jones-shaped pair force. Not molecular dynamics, and not described as such |
| Verification console | 2000 seeded Wright-Fisher replicates vs. the exact closed form (an archived domain, labelled so) |
| Inject bug button | applies the `2N → N` diploid error and re-plots the divergence |
| Shell | `run`, `verify`, `mutate`, `domains`, `ledger`, `pipeline`, `agents`, `cite` |
| `run mm` | v/[E] = kcat·S/(Km+S) for human hexokinase on D-glucose: Km 6 mM (BRENDA ref 641068), kcat 40.1 1/s (ref 739603), the rows of `caterva/evidence/showcase.py` |
| `verify gillespie_ssa` | mean of 50 exact SSA runs within 3 standard errors of a0·e^(−kt), the rule of `caterva/tests/test_gillespie_ssa_correctness.py` |
| `mutate gillespie_ssa` | drops the parentheses from the waiting time and shows the same check fail |

The shell runs only the five live domains (`src/cli/domainCatalogue.ts`).
A domain archived on 2026-09-27 (epidemiology, PCR, Monte Carlo, population
genetics, Lennard-Jones MD; `archive/legacy_domains/README.md`) answers that
it is archived and that v0.4.0 is the last release that runs it. The LJ
cluster checks that used to be listed here (`verify md`, LJ13 = −44.326801)
left with that domain; v0.4.0's copy of this site still has them.

`tests/terminal.test.mjs` holds the shell to this: its domain table must equal
the catalogue, every name the v0.4.0 shell accepted must be live or answer
archived, and the hexokinase constants must equal `showcase.py`'s rows.

## One constant that must not be lowered

`CONFIG.replicates` in `src/lib/drift.ts` is `2000`. Sampling noise on mean
heterozygosity by replicate count:

```
 200 -> 0.0294     500 -> 0.0234    1000 -> 0.0140    2000 -> 0.0054
```

The displayed tolerance is `0.02`. **At 200 replicates the correct
implementation displays FAIL** — the demo inverts and the page argues against
itself. 2000 is the first value with real margin (3.7×).

## Structure

```
src/
├── lib/
│   ├── md.ts          the background's pair force (decoration)
│   ├── ssa.ts         exact Gillespie SSA + its ensemble checks
│   ├── drift.ts       Wright-Fisher + closed form
│   ├── terminal.ts    command registry; every command computes
│   ├── pipeline.ts    build architecture + evidence ledger, as data
│   └── motion.ts      reveal / count-up / typewriter, one reduced-motion check
└── components/
    ├── AmbientLattice.tsx      background (decoration)
    ├── Hero.tsx
    ├── VerificationConsole.tsx full-bleed instrument panel
    ├── Terminal.tsx            interactive shell
    ├── PipelineFlow.tsx        animated SVG architecture
    └── Sections.tsx            ledger, contract, constitution, audit, close
```

## House rules

- Never hard-code a number the code can compute.
- No test-count claim anywhere on the page. It has gone stale three times.
- Accessibility: all motion is gated on `prefers-reduced-motion`.
- The force clamp in `md.ts` is a rendering decision and is never presented
  as physics.
