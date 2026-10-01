# Kinetics fixtures

Real API responses for the kinetics screens' component tests (Compose,
Constants, Sim, Bind). Nothing here is typed by hand, and no number in them
was written by a person: each file is what the studio server answered.

Produced 2026-10-01 in the `studio/sci-kinetics` worktree. Each request went
through `caterva.studio.dispatch.App.dispatch` (the core server's pure
dispatch layer, `studio/core` at e9f768f, copied beside this branch's
adapters in a scratch tree, since core is not merged here yet) exactly as
the socket layer hands a request over: `POST /api/runs`, then polling
`GET /api/runs/{id}` until the run finished, then `GET /api/runs/{id}`,
`GET /api/runs/{id}/result` and `GET /api/runs/{id}/events`. Each file
holds:

- `captured`: the kind and request posted;
- `run`: the RunRecord (`cli` is the command that reproduces the run);
- `result_status` and `result` (the kind's Result) or `error` (the 404 body
  for a run that finished without a result);
- `events`: every Server-Sent Event of the run, in order.

The only edit made after capture: the scratch data directory's path was
replaced by `<data dir>`.

Literature answers were the committed recordings, through
`caterva/tests/studio_kinetics_offline.py` (the same context managers the
parity tests use), so the numbers are BRENDA's as recorded:

| file | request | where its answers came from |
|---|---|---|
| `compose-ldh-gossypol.json` | `caterva compose "Michaelis-Menten with a competitive inhibitor" --subject 1.1.1.27 --organism human --substrate pyruvate --inhibitor gossypol` (the README example): Km 0.03 mM (BRENDA ref 286469), Ki 0.0014 mM (ref 711801), kcat a placeholder | `Tests/fixtures/ki_mode/brenda_1.1.1.27.html.gz`, `caterva/tests/fixtures/studio_kinetics/http/` |
| `compose-ldh-noncompetitive.json` | the same with a noncompetitive inhibitor and the quinoline sulfonamide of ref 739793: Ki 0.00252 mM, the row stating noncompetitive inhibition versus pyruvate | the same |
| `compose-binding-analyses.json` | `caterva compose "reversible binding of a ligand to a receptor" --crnt --scale --validate --reduction --robustness 5`: exit 3, timescale separation refused, the other sections answered | no search |
| `compose-unrecognised.json` | `caterva compose glycolysis`: refused, no result (404) | no search |
| `compose-shapes.json` | `GET /api/compose/shapes` | |
| `organisms-normalise-human.json` | `POST /api/organisms/normalise {"name": "human"}` | |
| `compose-malformed.json` | `POST /api/runs` with `--robustness 0`: 400 in the CLI's words | |
| `constants-hexokinase.json` | `python3 scripts/cite.py --ec 2.7.1.1 --organism human --substrate glucose`: Km 6.0 mM, BRENDA ref 641068 | `Tests/fixtures/recorded/` |
| `constants-refused.json` | the same without an organism: refused in report_lab's words | |
| `sim-decay.json` | `caterva sim ssa --a0=200 --k=0.3 --end=10.0 --seed=42` | the engine |
| `sim-association.json` | `caterva sim ssa --bimolecular --a0=120 --b0=80 --k=0.005 --end=5.0 --seed=7` | the engine |
| `bind-quinoline-disagrees.json` | `caterva bind --ec 1.1.1.27 --organism human --inhibitor <ref 739793's quinoline> --computed=-10.5±0.3`: exit 4, disagrees | `Tests/fixtures/brenda_ldh_ki_fixture.html` |
| `bind-gossypol.json` | `caterva bind ... --inhibitor gossypol` | the same |
| `bind-survey.json` | `caterva bind ... --survey` | the same |
| `bind-list.json` | `caterva bind ... --list` | the same |
| `bind-no-rows.json` | `caterva bind ... --inhibitor NADH`: refused, no result | the same |

To regenerate: build the same scratch tree (this branch's `caterva/`,
`Tests/` and `scripts/`, with core's `caterva/studio/{dispatch, jobs,
workspace, security, server, capabilities, static_files, __main__}.py` and
its contract amendment), create
`App(workspace=Workspace(<empty dir>), port=..., token=...)`, and make the
calls above inside the matching `studio_kinetics_offline` context manager.
Once core is merged this needs no scratch tree. The JSON must not be edited
by hand.
