# Workspace fixtures

Real API responses for Home, History, Settings and About, and for the
kinetics screens' reopen tests. Nothing here is typed by hand.

Captured 2026-10-01 on branch `studio/kin` (from `studio/integrate` at
f8c7cc9) through `caterva.studio.dispatch.App`, the server's pure dispatch
layer, exactly as the socket layer hands requests over:
`App(workspace=Workspace(<empty dir>), port=18720, token=...)`, `start()`,
then for each run `POST /api/runs`, polling `GET /api/runs/{id}` until it
finished, `GET /api/runs/{id}`, `GET /api/runs/{id}/result` and the run's
`events.jsonl`. Literature answers came from the committed recordings,
through `caterva/tests/studio_kinetics_offline.py` (`ldh_offline`,
`ldh_ki_page_offline`), so no database was contacted.

| file | what |
|---|---|
| `compose.json` | `caterva compose "Michaelis-Menten with a competitive inhibitor" --subject 1.1.1.27 --organism human --substrate pyruvate --inhibitor gossypol` |
| `sim.json` | `caterva sim ssa --a0=200 --k=0.3 --end=10.0 --seed=42` |
| `refused.json` | `caterva compose glycolysis`: refused, no result |
| `negative.json` | `caterva bind --ec 1.1.1.27 --organism human --inhibitor <ref 739793's quinoline> --computed=-10.5±0.3`: exit 4 |
| `runs.json` | `GET /api/runs` after those four and `../kinetics/compose-binding-charts.json` |
| `capabilities.json` | `GET /api/capabilities` from that server (no network probe) |
| `health.json`, `settings.json`, `shapes.json` | `GET /api/health`, `/api/settings`, `/api/compose/shapes` |

The only edit after capture: the scratch data directory's path was replaced
by `<data dir>`. `capabilities.json` keeps the paths of the checkout it ran
in (`ui.static_dir`), as the server reported them.
