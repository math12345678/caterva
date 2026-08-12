# backend-main

Part of [**Terrium**](https://github.com/Terrium-sim/main) — scientific computing for teaching labs.

The TypeScript library, CLI and web server. 52 source files.

```bash
npx ts-node src/cli/scientificCLI.ts help
npm run web        # the dashboard server on :3000
```

## Layout

| path | what |
|---|---|
| `cli/` | the command-line tool — `resolve`, `simulate --resolve`, `sweep`, `history` |
| `engine/` | the bridge to the Python engine, and the SBML builder |
| `literature/` | the resolver client |
| `validation/` | request and scientific validators |
| `storage/` | job database, CSV export, query builder, result comparator |
| `integration/` | the four-layer pipeline |
| `reproducibility/` | execution records and reproduction verification |
| `web/server.ts` | the raw-http API server |

## The point of the CLI

Every number it reports says where it came from, and anything it cannot
source it refuses to invent:

```
Parameters and where they came from
  s0    10 mM      user
  km    0.14 mM    brenda_exact  BRENDA ref 12345
  vmax  0.25 mM/s  brenda_cross_species → kcat x [E]0  BRENDA ref 649716
        ⚠ measured in Oryctolagus cuniculus, not the organism requested
```

Three exit codes, because "the literature has nothing" and "the lookup
failed" are different facts: `0` found, `2` genuinely absent, `1` could not
check.

The dashboard this server serves lives in
[`frontend-main`](https://github.com/Terrium-sim/frontend-main).

---

This repository is a submodule of [`Terrium-sim/main`](https://github.com/Terrium-sim/main). Clone the whole system with:

```bash
git clone --recursive https://github.com/Terrium-sim/main.git
```
