# `examples/` — runnable, and kept that way

Three end-to-end examples, one per way of calling Caterva.

| file | shows |
|---|---|
| `scientificPipelineExample.ts` | the TypeScript pipeline: resolve → validate → simulate, and how to read the provenance that comes back |
| `python_integration.py` | driving the engine directly from Python |
| `nodejs_integration.js` | calling the HTTP API from plain Node |

```bash
npx ts-node examples/scientificPipelineExample.ts
python examples/python_integration.py
node examples/nodejs_integration.js
```

`runs.csv` is sample output, not an example to run: what `caterva ssa`
writes with `--out`, for the catalogue's replicates line
(`src/cli/domainCatalogue.ts`). Columns `time,a,b`, one row per event plus
the initial row and the final row snapped to `--end`. It is byte-identical to

```bash
python -m caterva.cli ssa --a0 100 --k 0.1 --end 50 --seed 1 --out runs.csv
```

## These are checked, not decorative

`scripts/check_commands_runnable.py` and
`scripts/check_example_endpoints.py` run in the build. The second one exists
because a 725-line API reference was found describing endpoints that had
never existed — every endpoint an example calls is resolved against the
servers' actual route tables.

So an example that stops working fails the build. That is the point of
keeping them small.

## What a good example looks like here

It prints the **provenance**, not just the number.

`scientificPipelineExample.ts` prints the assay conditions the parameters
were measured at and any warnings, including when the answer is *"nobody
recorded them"*. A run whose conditions are unknown looks exactly like a run
at 37 °C unless it says so — which is the defect
[ADR 0055](../docs/adr/0055-a-simulation-has-no-temperature-of-its-own.md)
records.

An example that prints a trajectory and nothing else teaches the wrong
lesson about this project.
