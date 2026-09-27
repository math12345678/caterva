# Caterva — site

Marketing site for Caterva, a scientific verification engine.

The premise: a page arguing that scientific claims must be independently
checked should not itself be a wall of unchecked claims. So it computes. The
background is a live Lennard-Jones molecular dynamics simulation. The console
runs two thousand Wright-Fisher populations and plots them against an exact
closed form. The shell reproduces a global-minimum energy published in 1971.

## Run it

```bash
npm install
npm run dev        # http://localhost:5173
npm run build      # production build into dist/
npm run typecheck  # tsc --noEmit
```

## What's actually live

| Element | What it really does |
|---|---|
| Background lattice | Lennard-Jones MD, velocity Verlet, cursor acts as a repulsive body |
| Verification console | 2000 seeded Wright-Fisher replicates vs. the exact closed form |
| Inject bug button | applies the real `2N → N` diploid error and re-plots the divergence |
| Shell | `run`, `verify`, `mutate`, `ledger`, `pipeline`, `agents`, `cite` |
| `verify md` | golden-section search reproducing LJ13 = −44.326801 |

## Verified numbers

Recomputed in TypeScript and cross-checked against Caterva's Python engine
and an independent numpy implementation. All three agree:

```
LJ2   -1.000000000000   published -1.000000   diff 0.00e+00
LJ3   -3.000000000000   published -3.000000   diff 0.00e+00
LJ4   -6.000000000000   published -6.000000   diff 0.00e+00
LJ13 -44.326801419534   published -44.326801  diff 4.20e-07
```

The LJ13 residual is the published table's six-decimal rounding, not error.
Source: Hoare & Pal, *Adv. Phys.* **20**, 161 (1971), via the Cambridge
Cluster Database.

`LJ2/3/4` are exact by two independent routes — derivable by hand (a regular
tetrahedron places all six pairs at `r_min` simultaneously) and independently
tabulated. `LJ5` is the first size where geometric frustration makes this
impossible: `−9.103852`, not `−10`.

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
│   ├── md.ts          LJ molecular dynamics + cluster geometry
│   ├── drift.ts       Wright-Fisher + closed form
│   ├── terminal.ts    command registry; every command computes
│   ├── pipeline.ts    build architecture + evidence ledger, as data
│   └── motion.ts      reveal / count-up / typewriter, one reduced-motion check
└── components/
    ├── AmbientLattice.tsx      background simulation
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
