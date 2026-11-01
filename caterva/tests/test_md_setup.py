"""`caterva md`: every mdp setting is accounted for, and conditions are carried.

No GROMACS is needed here; the end-to-end run is a separate CI job. These
check the claim PROVENANCE.md makes: that every setting in the mdp files
has a row saying where it came from.
"""
from __future__ import annotations

import re

import pytest

from caterva.md.setup import ORIGINS, Conditions, MdSetup

#: Each mdp key, to the PROVENANCE row that accounts for it. A key missing
#: here fails the test: an mdp setting nobody accounted for is exactly an
#: unsourced number.
KEY_TO_ROW = {
    "integrator": "minimisation", "emtol": "minimisation", "emstep": "minimisation",
    "nsteps": "production length", "dt": "constraints",
    "define": "equilibration", "refcoord_scaling": "equilibration",
    "continuation": "equilibration", "gen_vel": "velocity seed", "gen_temp": "temperature",
    "gen_seed": "velocity seed",
    "nstxout-compressed": "output", "nstenergy": "output", "nstlog": "output",
    "constraint_algorithm": "constraints", "constraints": "constraints",
    "lincs_iter": "constraints", "lincs_order": "constraints",
    "cutoff-scheme": "neighbour list", "nstlist": "neighbour list", "pbc": "neighbour list",
    "coulombtype": "electrostatics", "rcoulomb": "electrostatics",
    "fourierspacing": "PME grid", "pme_order": "PME grid",
    "rvdw": "van der Waals", "DispCorr": "van der Waals",
    "tcoupl": "thermostat", "tc-grps": "thermostat", "tau_t": "thermostat", "ref_t": "temperature",
    "pcoupl": "barostat (production)", "pcoupltype": "barostat (production)",
    "tau_p": "barostat (production)", "ref_p": "pressure", "compressibility": "compressibility",
}


def _setup(**kw):
    return MdSetup(pdb_id="1I10", chain="A", conditions=kw.pop("conditions", Conditions()), **kw)


def _keys(mdp: str):
    return {line.split("=")[0].strip() for line in mdp.splitlines()
            if "=" in line and not line.lstrip().startswith(";")}


def test_every_mdp_setting_has_a_provenance_row():
    setup = _setup()
    rows = {p.name for p in setup.parameters}
    for name, text in setup.files().items():
        if not name.endswith(".mdp"):
            continue
        for key in _keys(text):
            assert key in KEY_TO_ROW, f"{name}: `{key}` is not accounted for in PROVENANCE.md"
            assert KEY_TO_ROW[key] in rows, (name, key)


def test_every_parameter_says_where_it_came_from():
    for p in _setup().parameters:
        assert p.origin in ORIGINS and p.source.strip(), p
        if p.origin == "method":
            assert "doi:" in p.source, p


def test_measured_conditions_reach_every_stage():
    c = Conditions(temperature_k=310.15, temperature_source="measured: 37 C in BRENDA ref 1",
                   ph=7.5, ph_source="measured: pH 7.5 in BRENDA ref 1", measured_temperature=True)
    files = _setup(conditions=c).files()
    for stage in ("rep1/nvt.mdp", "npt.mdp", "md.mdp"):
        assert "ref_t           = 310.15 310.15" in files[stage]
    assert "gen_temp        = 310.15" in files["rep1/nvt.mdp"]
    temp = next(p for p in _setup(conditions=c).parameters if p.name == "temperature")
    assert temp.origin == "measured" and "BRENDA ref 1" in temp.source
    assert "PROPKA" in files["PROVENANCE.md"] or "Olsson" in files["PROVENANCE.md"]


def test_without_measured_conditions_the_temperature_is_labelled_a_choice():
    temp = next(p for p in _setup().parameters if p.name == "temperature")
    assert temp.origin == "chosen" and temp.value == "298.15 K"


def test_production_length_and_seed_are_what_was_asked():
    files = _setup(ns=2.5, seed=7).files()
    assert "nsteps          = 1250000" in files["md.mdp"]
    assert "gen_seed        = 7" in files["rep1/nvt.mdp"]


def test_equilibration_restrains_and_production_does_not():
    files = _setup().files()
    assert "-DPOSRES" in files["rep1/nvt.mdp"] and "-DPOSRES" in files["npt.mdp"]
    assert "-DPOSRES" not in files["md.mdp"]
    assert "pcoupl          = C-rescale" in files["npt.mdp"]
    assert "pcoupl          = Parrinello-Rahman" in files["md.mdp"]


def test_the_script_strips_small_molecules_and_says_so():
    run = _setup().files()["run.sh"]
    assert "stripped:" in run and "set -euo pipefail" in run
    assert "-ff amber99sb-ildn -water tip3p" in run
    assert re.search(r"substr\(\$0,22,1\) == chain", run)


@pytest.mark.parametrize("bad", ["LDHA", "12345", "abcd", "1i1"])
def test_a_malformed_pdb_id_is_refused(bad, tmp_path, capsys):
    from caterva.md.__main__ import main

    assert main(["--pdb", bad, "--out", str(tmp_path / "x")]) == 2


# --- replicas (MD roadmap M2) ---------------------------------------------------

def test_three_replicas_by_default_differing_only_in_their_seed():
    files = _setup(seed=7).files()
    nvts = [files[f"rep{r}/nvt.mdp"] for r in (1, 2, 3)]
    assert [re.search(r"gen_seed\s*=\s*(\d+)", t).group(1) for t in nvts] == ["7", "8", "9"]
    strip = [re.sub(r"gen_seed.*", "", t) for t in nvts]
    assert strip[0] == strip[1] == strip[2]
    assert "for r in $(seq 1 3)" in files["run.sh"]
    assert 'rms -s "$d/md.tpr"' in files["run.sh"]


def test_every_seed_is_recorded():
    seeds = next(p for p in _setup(seed=7).parameters if p.name == "velocity seed")
    assert seeds.value == "rep1: 7, rep2: 8, rep3: 9"


def test_one_replica_is_labelled_one_sample():
    row = next(p for p in _setup(replicas=1).parameters if p.name == "replicas")
    assert "ONE SAMPLE" in row.source
    assert "one sample" in _setup(replicas=1).files()["PROVENANCE.md"]


def test_zero_replicas_is_refused(tmp_path):
    from caterva.md.__main__ import main

    assert main(["--pdb", "1AKI", "--out", str(tmp_path / "x"), "--replicas", "0"]) == 2
