# Structure fixtures

Real output of the structure owner's adapters (caterva/studio/adapters/
structure.py, prepare.py, md.py, analyze.py, fep.py) over the real engine
and committed real inputs, for the structure screens' component tests
(src/screens/structure/structure.test.tsx). Nothing here is typed by hand,
and none of it may be edited by hand.

Produced 2026-10-01 in the `studio/str` worktree (after the adapters began
sending the per-residue RMSF, the verdict thresholds, each setup
parameter's chooser and citation, the coordinates' findings and the
structure search by name) with the script below, run from the repository root as
`PYTHONPATH=$PWD python capture.py` (the venv of the CLI tests: numpy 2.2.6,
scipy 1.15.3). Each JSON file holds `kind`, `request`, `cli` (the command
line that reproduces it), `outcome` (contract.outcome_for over the
adapter's exit code) and `result`, except `coordinates-1L63.json`, which is
the `GET /api/structure/1L63/coordinates` response body.

What each one read:

- `structure-ldha-oxamate.json`, `structure-ldh-several-proteins.json`:
  `caterva structure --subject 1.1.1.27 --organism human [--gene LDHA
  --ligand oxamate --top 8]`, the UniProt and RCSB answers replayed from
  `caterva/tests/fixtures/structure/ldh_human.json` (recorded 2026-09-27,
  the recording test_structure_search.py uses). The second is the command's
  refusal (exit 3): EC 1.1.1.27 in human is several proteins.
- `coordinates-1L63.json`: T4 lysozyme 1L63's real mmCIF, trimmed as
  `caterva/tests/fixtures/prepare/` keeps it, and UniProt P00720, through
  `caterva prepare`'s own fetch and audit.
- `prepare-1I10-ph7.4.json` (exit 0) and `prepare-1L63.json` (exit 4, every
  chain blocked): `caterva prepare 1I10 --ph 7.4` and `caterva prepare 1L63`
  over the same committed entries and sequences.
- `structure-by-name-ldha.json`, `structure-name-several-enzymes.json`:
  `caterva structure --subject 'L-lactate dehydrogenase A chain' --organism
  human --gene LDHA --top 8 --chimerax ...` and `--subject 'lactate
  dehydrogenase'`, the name looked up through the literature layer's
  `enzyme_lookup` with UniProt's answers replayed from
  `caterva/tests/fixtures/structure/uniprot_ec_by_name.json` (recorded
  2026-10-01, the recording test_studio_structure.py uses). The second is
  the refusal of a name that is six EC numbers, with the candidates.
  Both were captured again on 2026-10-03 by
  `caterva/tests/capture_studio_enzyme_fixtures.py` (see `../enzymes/README.md`),
  because the one name policy (`caterva.enzymes.policy`, the enzyme finder's)
  now reads the name before UniProt does: the first prints "Read '...' as EC
  1.1.1.27" and carries `subject_notes`; the second is a refusal with no
  `result` and an `outcome.name_refusal` naming each candidate.
- `md-setup-1AKI.json`: `caterva md --pdb 1AKI --chain A --replicas 3 --out
  <run dir>/md-setup`; no network (no `--subject`). The paths in it are the
  temporary folder the script wrote into. `md-setup-1I10-chosen.json` is
  `caterva md --pdb 1I10 --chain A --temperature 310 --ph 7.4 --ns 20
  --replicas 4` into the same folder: every one of those labelled chosen
  by you.
- `analyze-lysozyme-native.json`: `caterva analyze DIR` (native route) on
  the 21 real frames of replica 1 of a 10 ps `caterva md` run on hen
  lysozyme 1AKI (`caterva/tests/fixtures/md/lyso_1aki_res1-59_water.xtc`,
  whose README says how they were cut), with that run's em.gro and a
  protein.pdb written from the same atoms. Replica 2 is a copy of replica
  1, only so the run has two replicas, exactly as
  caterva/tests/test_studio_analyze.py builds it; the verdicts are what the
  library makes of that. The catalytic residues are hen lysozyme's M-CSA
  residues given directly (as test_faces.py gives them), so no network was
  asked.
- `analyze-lysozyme-script-only.json`: the same folder with
  `--script-only`.
- `md-summarise-not-run.json`, `fep-status-not-fep.json`: the commands'
  refusals (exit 3) on that same folder, which has no rmsd.xvg and was not
  written by `caterva fep`.

There is no `fep.status` or `complex.check` result here: the only finished
free-energy runs and pose checks in the repository's tests are constructed
by those tests, not measured, and a constructed number is not a fixture.

```python
"""Capture the structure screens' UI fixtures: the adapters' real output over the committed inputs."""
import gzip, hashlib, json, os, shutil, sys, tempfile
from pathlib import Path

ROOT = Path.cwd()
FIX = ROOT / "caterva" / "tests" / "fixtures"
OUT = ROOT / "Science-Agent-Pipeline/artifacts/caterva-studio/src/__fixtures__/api/structure"
OUT.mkdir(parents=True, exist_ok=True)
work = Path(tempfile.mkdtemp(prefix="caterva-fixtures-"))
os.environ["XDG_CACHE_HOME"] = str(work / "cache")

from caterva.studio import contract
from caterva.studio.adapters import EndpointRequest, RunContext, load_registry
from caterva.structure import search
from caterva.prepare import __main__ as prepare
from caterva.analyze import __main__ as analyze_cli

class Progress:
    def stage(self, *a, **k): pass
    def log(self, line): pass
    def check_cancelled(self): pass

calls = json.loads((FIX / "structure" / "ldh_human.json").read_text())["calls"]
def replay(url, payload):
    return calls[hashlib.sha256((url + json.dumps(payload, sort_keys=True)).encode()).hexdigest()[:16]]["response"]
search.live_http = lambda timeout=30.0: search.Http(replay, replay)

def cif(pid):
    with gzip.open(FIX / "prepare" / f"{pid}.trimmed.cif.gz", "rt") as fh:
        return fh.read()
def fetch(url):
    name = url.rsplit("/", 1)[-1]
    return cif(name[:-4]) if name.endswith(".cif") else (FIX / "prepare" / name).read_text()
prepare.live_fetch = lambda timeout=60.0: fetch

LYSO = [(48, "ASP"), (50, "SER"), (46, "ASN"), (59, "ASN"), (52, "ASP"), (35, "GLU")]
analyze_cli.catalytic_residues = lambda pdb, chain: (list(LYSO), "hen lysozyme's M-CSA catalytic residues, given directly as caterva/tests/test_faces.py gives them")

from caterva.checkout import literature_module
names = json.loads((FIX / "structure" / "uniprot_ec_by_name.json").read_text())["answers"]
lookup = literature_module("enzyme_lookup")
lookup.fetch_ec_numbers_by_name = lambda name, taxon_id=None, timeout=15: lookup.parse_ec_number_candidates(names[name])

registry = load_registry()
def run(kind, request, name):
    spec = registry.get(kind)
    argv = spec.argv(request)
    d = work / "runs" / f"20260930-120000-{kind.replace('.', '-')}-0badc0de"
    d.mkdir(parents=True, exist_ok=True)
    argv = [a.replace("@RUN_DIR@", str(d)) for a in argv]
    got = spec.run(request, RunContext(d.name, d, work, Progress()))
    body = {"kind": kind, "request": request, "cli": [*spec.cli_prefix, *argv],
            "outcome": contract.outcome_for(kind, got.exit_code, got.summary, got.refusal),
            "result": got.result}
    (OUT / f"{name}.json").write_text(json.dumps(body, indent=1, ensure_ascii=False, allow_nan=False) + "\n")
    print(name, got.exit_code, got.summary)

run("structure", {"subject": "1.1.1.27", "organism": "human", "gene": "LDHA", "ligand": "oxamate", "top": 8}, "structure-ldha-oxamate")
run("structure", {"subject": "1.1.1.27", "organism": "human"}, "structure-ldh-several-proteins")
run("structure", {"subject": "L-lactate dehydrogenase A chain", "organism": "human", "gene": "LDHA", "top": 8, "chimerax": True}, "structure-by-name-ldha")
run("structure", {"subject": "lactate dehydrogenase"}, "structure-name-several-enzymes")
coords = registry.endpoint("structure_coordinates")(EndpointRequest({"pdb_id": "1L63"}, {}, None, work))
(OUT / "coordinates-1L63.json").write_text(json.dumps(coords, ensure_ascii=False, allow_nan=False) + "\n")
print("coordinates", coords["count"])
run("prepare", {"entry": "1I10", "ph": 7.4}, "prepare-1I10-ph7.4")
run("prepare", {"entry": "1L63"}, "prepare-1L63")
run("md.setup", {"pdb": "1AKI", "chain": "A", "replicas": 3}, "md-setup-1AKI")
run("md.setup", {"pdb": "1I10", "chain": "A", "temperature_k": 310.0, "ph": 7.4, "ns": 20.0, "replicas": 4}, "md-setup-1I10-chosen")

lyso = work / "lyso-md"; lyso.mkdir()
(lyso / "caterva-setup.json").write_text(json.dumps({"pdb": "1AKI", "chain": "A"}))
(lyso / "em.gro").write_bytes(gzip.decompress((FIX / "md" / "lyso_1aki_res1-59_water.gro.gz").read_bytes()))
lines = []
for i, (resnr, resname, nm, xyz) in enumerate(analyze_cli._gro_atoms(lyso / "em.gro"), start=1):
    if resname == "SOL": continue
    x, y, z = (float(c) * 10 for c in xyz)
    lines.append(f"ATOM  {i:5d} {nm:<4} {resname:>3} A{resnr:4d}    {x:8.3f}{y:8.3f}{z:8.3f}  1.00  0.00           {nm[0]}")
(lyso / "protein.pdb").write_text("\n".join(lines) + "\nEND\n")
for rep in ("rep1", "rep2"):
    (lyso / rep).mkdir()
    shutil.copyfile(FIX / "md" / "lyso_1aki_res1-59_water.xtc", lyso / rep / "md.xtc")
    (lyso / rep / "md.tpr").write_text("")
run("analyze", {"directory": str(lyso)}, "analyze-lysozyme-native")
run("analyze", {"directory": str(lyso), "mode": "script_only"}, "analyze-lysozyme-script-only")
run("md.summarise", {"directory": str(lyso)}, "md-summarise-not-run")
run("fep.status", {"directory": str(lyso)}, "fep-status-not-fep")
print("work dir", work)
```

## Paths

A response that names a directory on the machine it was captured on carried a
throwaway scratch or worktree path. After capture, only that prefix was
rewritten, to `/tmp/caterva-fixtures`, so that no file in the repository names a person's
home or scratch folder; every other byte is what the server answered.
