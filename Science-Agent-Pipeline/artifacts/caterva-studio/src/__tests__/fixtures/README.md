# Foundation test fixtures

Real answers and real engine output, for the foundation's component tests.
Nothing here is typed by hand; regenerate with the commands below rather
than editing a file.

## `api/*.json`: answers from the studio server's dispatch layer

Captured 2026-09-30 from core's dispatch layer (`caterva/studio/dispatch.py`,
`App.dispatch`, branch `studio/core`, worktree `/tmp/claude-501/wt-core`, its
uncommitted state at that time), in-process, with no socket, a fresh
temporary data directory, port 18740 and the server's own session token.
Each file is `{"status": <HTTP status>, "body": <the JSON body>}`:

| file | request |
|---|---|
| `health.json` | `GET /api/health` |
| `capabilities.json` | `GET /api/capabilities` (no probe) |
| `settings.json` | `GET /api/settings` |
| `runs_empty.json` | `GET /api/runs?limit=8` on an empty workspace |
| `settings_bad.json` | `PUT /api/settings` with `theme: "sepia"` |
| `create_sim.json` | `POST /api/runs` `{kind: "sim", request: {seed: 7}}` while no adapter was registered |
| `run_missing.json` | `GET /api/runs/20260930-141502-sim-3f9a0c1d` |
| `no_token.json` | `GET /api/health` without the session header |
| `wrong_host.json` | `GET /api/health` with `Host: evil.example:18740` |

The capture script, run from the core worktree with the studio's venv:

```python
from caterva.studio.dispatch import App, Request
from caterva.studio.workspace import Workspace
app = App(workspace=Workspace(tmp_dir), port=18740)
app.start(apply_environment=False)
response = app.dispatch(Request(method, target, [("Host", "127.0.0.1:18740"),
                                                 ("X-Caterva-Session", app.token)], body))
```

`capabilities.json` describes the machine it ran on (GROMACS 2026.1 from
Homebrew, the literature layer present, no kind registered yet). Its paths are
temporary directories of that run.

## `api/coordinates-1L63.json`, `api/coordinates-1I10.json`

The `CoordinatesResponse` shape (docs/studio/CONTRACT.md section 7) of two
committed, unmodified mmCIF fixtures, `caterva/tests/fixtures/prepare/1L63.trimmed.cif.gz`
(T4 lysozyme, 1,292 atoms) and `1I10.trimmed.cif.gz` (human LDH, chains A, D
and G, 7,657 atoms), parsed with `caterva/prepare/cif.py` and
`caterva.prepare.audit._first_model`, exactly as the structure endpoint is
specified to: coordinates in angstroms as the file gives them, element from
`type_symbol`, names and numbers from the `auth_*` columns, `hetero` from
`group_PDB`. The citation is the file's `primary` citation (title, journal,
year, PubMed id and DOI verbatim) with the RCSB entry page as its link; the
structure owner's endpoint decides its own citation text, so tests read only
the atoms and the link. Produced by:

```sh
PYTHONPATH=<worktree> python coords.py 1L63 caterva/tests/fixtures/prepare/1L63.trimmed.cif.gz coordinates-1L63.json
```

where `coords.py` reads `cif.parse(...)["atom_site"]` through `_first_model`
and writes the columns above.

## `sim-ssa-a0-200-k-0.5-end-10-seed-7.csv`

The CSV `caterva sim ssa` writes, unmodified:

```sh
python -m caterva.app sim ssa --a0 200 --k 0.5 --end 10 --seed 7 --out sim-ssa-a0-200-k-0.5-end-10-seed-7.csv
```

A first-order decay A -> B simulated with Gillespie's direct method: 198
events, the time course the chart tests draw.
