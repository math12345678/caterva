"""`caterva analyze`: the enzyme's own questions, answered only when the runs allow it.

No GROMACS here: a finished run is faked with the files GROMACS would have
written (protein.pdb, repN/md.xtc placeholders, repN/catalytic.xvg,
repN/rmsf.xvg), and `--no-run` reads them. The real pipeline -- `caterva
md`, run.sh, then this -- was run end to end with GROMACS 2021 on 1AKI.
"""
from __future__ import annotations

import json
import math
import random

import pytest

from caterva.analyze.__main__ import (EXIT_NOT_A_RESULT, MOVED_NM, AnalyzeError, commands, main,
                                      read_columns, setup_info)
from caterva.analyze.plan import FUNCTIONAL_ATOMS, plan, read_pdb


def _atom(serial, name, resname, resnr, x, y, z, chain="A", alt=" "):
    return (f"ATOM  {serial:5d} {name:<4}{alt}{resname:>3} {chain}{resnr:4d}    "
            f"{x:8.3f}{y:8.3f}{z:8.3f}  1.00 20.00           {name[0]}")


def _protein():
    """Four residues on a line: His10 and Asp20 (catalytic), Gly30 near, Leu90 far."""
    lines = [
        _atom(1, "CA", "HIS", 10, 0.0, 0, 0), _atom(2, "ND1", "HIS", 10, 1.0, 0, 0),
        _atom(3, "NE2", "HIS", 10, 1.0, 2.0, 0),
        _atom(4, "CA", "ASP", 20, 6.0, 0, 0), _atom(5, "OD1", "ASP", 20, 5.0, 0, 0),
        _atom(6, "OD2", "ASP", 20, 5.0, 2.0, 0),
        _atom(7, "CA", "GLY", 30, 9.0, 0, 0),
        _atom(8, "CA", "LEU", 90, 40.0, 0, 0),
        _atom(9, "CA", "TRP", 10, 0.0, 0, 0, chain="B"),
    ]
    return "\n".join(lines) + "\nEND\n"


# --- planning ---------------------------------------------------------------------

def test_read_pdb_keeps_one_chain_and_the_first_conformer():
    text = _protein() + _atom(10, "CA", "HIS", 10, 99, 99, 99, alt="B") + "\n"
    atoms = read_pdb(text, "A")
    assert {a.chain for a in atoms} == {"A"}
    assert not any(a.xyz[0] == 99 for a in atoms)


def test_functional_group_centres_give_the_crystal_distance():
    p = plan(read_pdb(_protein(), "A"), [(10, "HIS"), (20, "ASP")])
    (pair,) = p.pairs
    # His ring N centre (1, 1, 0); Asp carboxylate O centre (5, 1, 0): 4 A = 0.4 nm.
    assert pair.crystal_nm == pytest.approx(0.4)
    assert pair.selection() == ("cog of (resnr 10 and name ND1 NE2) plus "
                                "cog of (resnr 20 and name OD1 OD2)")


def test_the_pocket_is_residues_near_a_catalytic_one():
    p = plan(read_pdb(_protein(), "A"), [(10, "HIS"), (20, "ASP")])
    assert p.pocket == [10, 20, 30] and p.rest == [90]


def test_a_residue_without_functional_atoms_falls_back_to_ca_and_says_so():
    p = plan(read_pdb(_protein(), "A"), [(30, "GLY"), (10, "HIS")])
    gly = next(s for s in p.sites if s.resnr == 30)
    assert gly.atoms == ("CA",) and not gly.functional
    assert any("Gly30" in n and "backbone" in n for n in p.notes)


def test_a_catalytic_residue_absent_from_the_structure_is_left_out_and_named():
    p = plan(read_pdb(_protein(), "A"), [(10, "HIS"), (77, "SER")])
    assert [s.resnr for s in p.sites] == [10] and p.pairs == []
    assert any("Ser77" in n for n in p.notes)


def test_histidine_protonation_variants_keep_their_ring_nitrogens():
    assert FUNCTIONAL_ATOMS["HIE"] == FUNCTIONAL_ATOMS["HIS"] == ("ND1", "NE2")


def test_one_gromacs_call_per_replica_measures_every_pair():
    p = plan(read_pdb(_protein(), "A"), [(10, "HIS"), (20, "ASP")])
    lines = commands(p, ["rep1", "rep2"])
    assert sum("distance" in l for l in lines) == 2
    assert sum(" rmsf " in l for l in lines) == 2
    assert "-oall rep1/catalytic.xvg" in lines[0]


def test_gmx_rmsf_fits_to_a_whole_reference_not_the_wrapped_tpr():
    # A tpr stores coordinates wrapped into the box. gmx rmsf fits to -s as
    # stored, so on 1AKI residues 66-74 (split a box length from their
    # neighbours) came out ~10% high. Measured against the native route:
    # 0.0063 nm apart with -s md.tpr, 0.00007 nm with a whole reference.
    p = plan(read_pdb(_protein(), "A"), [(10, "HIS"), (20, "ASP")])
    lines = commands(p, ["rep1"])
    rmsf = next(l for l in lines if " rmsf " in l)
    assert "-s rep1/rmsf_reference.pdb" in rmsf and "-f rep1/md_whole.xtc" in rmsf
    assert "-s rep1/md.tpr" not in rmsf
    made_whole = [l for l in lines if "trjconv" in l]
    assert any("-f em.gro -pbc mol" in l for l in made_whole)
    assert any("-f rep1/md.xtc -pbc mol" in l for l in made_whole)


# --- the setup directory -------------------------------------------------------------

def test_setup_info_from_the_json_md_now_writes(tmp_path):
    from caterva.md.setup import Conditions, MdSetup

    files = MdSetup(pdb_id="1i10", chain="A", conditions=Conditions()).files()
    (tmp_path / "caterva-setup.json").write_text(files["caterva-setup.json"])
    assert setup_info(tmp_path) == ("1I10", "A")
    assert json.loads(files["caterva-setup.json"])["seeds"] == [20260927, 20260928, 20260929]


def test_setup_info_falls_back_to_the_run_script_header(tmp_path):
    (tmp_path / "run.sh").write_text("#!/bin/bash\n# Caterva MD setup: PDB 1AKI. Read PROVENANCE.md first.\n")
    assert setup_info(tmp_path) == ("1AKI", None)


def test_a_directory_that_is_not_a_setup_is_refused(tmp_path):
    with pytest.raises(AnalyzeError):
        setup_info(tmp_path)


# --- the report --------------------------------------------------------------------------

def _ar1(rng, n, phi, mu, sd):
    x, out = mu, []
    for _ in range(n):
        x = mu + phi * (x - mu) + rng.gauss(0, sd * math.sqrt(1 - phi * phi))
        out.append(x)
    return out


def _fake_run(tmp_path, means, n=4000, phi=0.5, sd=0.005, seed=0):
    rng = random.Random(seed)
    (tmp_path / "caterva-setup.json").write_text(json.dumps({"pdb": "9XYZ", "chain": "A"}))
    (tmp_path / "protein.pdb").write_text(_protein())
    for r, mu in enumerate(means, start=1):
        d = tmp_path / f"rep{r}"
        d.mkdir()
        (d / "md.xtc").write_text("")
        (d / "md.tpr").write_text("")
        series = _ar1(rng, n, phi, mu, sd)
        (d / "catalytic.xvg").write_text(
            "@ title\n" + "".join(f"{i * 0.001:.3f} {v:.5f}\n" for i, v in enumerate(series)))
        (d / "rmsf.xvg").write_text("# rmsf\n10 0.05\n20 0.05\n30 0.06\n90 0.20\n")
    return tmp_path


def _catalytic(pdb, chain):
    return [(10, "HIS"), (20, "ASP")], "a test mapping"


def test_consistent_replicas_that_keep_the_crystal_geometry(tmp_path, capsys):
    d = _fake_run(tmp_path, [0.40, 0.40, 0.40])
    assert main([str(d), "--no-run"], catalytic=_catalytic) == 0
    out = capsys.readouterr().out
    assert "| His10–Asp20 | 0.400 |" in out and ", held |" in out
    assert "Pocket / rest: 0.27" in out and "more rigid" in out
    assert (d / "ANALYSIS.md").exists() and (d / "analyze.sh").exists()


def test_a_consistent_change_is_called_moved(tmp_path, capsys):
    d = _fake_run(tmp_path, [0.40 + 2 * MOVED_NM] * 3)
    assert main([str(d), "--no-run"], catalytic=_catalytic) == 0
    assert "moved**" in capsys.readouterr().out


def test_unconverged_runs_answer_nothing(tmp_path, capsys):
    d = _fake_run(tmp_path, [0.40, 0.40], n=400, phi=0.995, sd=0.05)
    assert main([str(d), "--no-run"], catalytic=_catalytic) == EXIT_NOT_A_RESULT
    out = capsys.readouterr().out
    assert "not yet a result" in out and "Not yet a result: pocket / rest" in out
    assert "more rigid than" not in out.split("Not yet a result: pocket")[0]


def test_script_only_writes_the_commands_and_runs_nothing(tmp_path, capsys):
    d = _fake_run(tmp_path, [0.4])
    assert main([str(d), "--script-only"], catalytic=_catalytic) == 0
    assert "gmx" in (d / "analyze.sh").read_text().lower()
    assert not (d / "ANALYSIS.md").exists()


def test_no_finished_replicas_is_refused(tmp_path):
    (tmp_path / "caterva-setup.json").write_text(json.dumps({"pdb": "9XYZ", "chain": "A"}))
    (tmp_path / "protein.pdb").write_text(_protein())
    assert main([str(tmp_path), "--no-run"], catalytic=_catalytic) == 3


def test_read_columns_skips_gromacs_headers(tmp_path):
    p = tmp_path / "x.xvg"
    p.write_text("# c\n@ t\n0 1 2\n1 3 4\n")
    assert read_columns(p) == [[0.0, 1.0], [1.0, 3.0], [2.0, 4.0]]


def test_native_distances_match_gmx_distance_on_a_real_trajectory(tmp_path):
    """T4 lysozyme's catalytic Glu11 and Asp20 carboxylates, three frames of
    a real run: `gmx distance` printed 0.818, 0.806, 0.825 nm."""
    import gzip
    from caterva.analyze.__main__ import _gro_index, distance_series
    from caterva.md import xtc
    from pathlib import Path
    fix = Path(__file__).parent / "fixtures" / "md"
    gro = tmp_path / "first6000.gro"
    gro.write_bytes(gzip.decompress((fix / "t4l_bnz_first6000.gro.gz").read_bytes()))
    idx = _gro_index(gro)
    glu = [idx[(11, "OE1")], idx[(11, "OE2")]]
    asp = [idx[(20, "OD1")], idx[(20, "OD2")]]
    got = distance_series(xtc.read(fix / "t4l_bnz_first6000.xtc"), glu, asp)
    assert [round(x, 3) for x in got] == [0.818, 0.806, 0.825]
