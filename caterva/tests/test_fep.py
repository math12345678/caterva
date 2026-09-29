"""`caterva fep`: double decoupling held to a cited Ki.

The restraint correction is checked against a hand calculation of Boresch
eq. 32 for r = 0.5 nm, both angles 90 degrees, 298.15 K, K_r = 4184
kJ/mol/nm^2 and K_angle = 41.84 kJ/mol/rad^2:

    sqrt(4184 * 41.84^5) = 7.324e5;  8 pi^2 V° = 131.11 nm^3
    (2 pi kT)^3 = 15.565^3 = 3771;   r^2 = 0.25
    ln(131.11 * 7.324e5 / (0.25 * 3771)) = ln(1.0186e5) = 11.531
    kT * 11.531 = 2.4790 * 11.531 = 28.59 kJ/mol = 6.83 kcal/mol
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from caterva.fep import core
from caterva.fep.__main__ import main

ROOT = Path(__file__).resolve().parents[2]
KI_PAGE = ROOT / "Tests" / "fixtures" / "brenda_ldh_ki_fixture.html"
QUINOLINE = "3-[7-(2,4-dimethoxypyrimidin-5-yl)-3-sulfamoylquinolin-4-yl]aminobenzoic acid"

# The solvent leg of replica 1 of the T4 lysozyme L99A + benzene smoke run
# (PDB 181L, GROMACS 2026.1, 0.5 ps windows), excerpted verbatim: the first
# two points and the total. Only the total line is read.
BAR_TAIL = """
Final results in kJ/mol:

point      0 -      1,   DG  2.11 +/-  0.62
point      1 -      2,   DG  0.39 +/-  0.34

total      0 -     24,   DG  3.05 +/-  1.46
"""


def _atom(i, resnr, resname, name, xyz):
    return core.Atom(i, resnr, resname, name, xyz)


# --- geometry and the closed form ---------------------------------------------

def test_angle_and_dihedral_on_known_points():
    a, b, c = (_atom(1, 1, "X", "A", (1, 0, 0)), _atom(2, 1, "X", "B", (0, 0, 0)),
               _atom(3, 1, "X", "C", (0, 1, 0)))
    assert math.degrees(core.angle(a, b, c)) == pytest.approx(90.0)
    d = _atom(4, 1, "X", "D", (0, 1, 1))
    # a-b-c-d: a along x, d above c along z: +90 or -90 by the IUPAC sign.
    assert abs(math.degrees(core.dihedral(a, b, c, d))) == pytest.approx(90.0)


def _restraint(r=0.5, ta=math.pi / 2, tb=math.pi / 2):
    dummy = _atom(1, 1, "X", "X", (0, 0, 0))
    return core.Restraint((dummy,) * 3, (dummy,) * 3, r, ta, tb, 0, 0, 0, 1.0)


def test_standard_state_volume_is_one_molar():
    assert core.V_STANDARD_NM3 == pytest.approx(1.66054, abs=1e-5)


def test_boresch_correction_matches_the_hand_calculation():
    assert core.restraint_cost_kj(_restraint(), 298.15) == pytest.approx(28.59, abs=0.02)


def test_the_correction_grows_as_the_anchor_nears_collinear():
    """sin(theta) in the denominator: the failure the atom picker avoids."""
    ok = core.restraint_cost_kj(_restraint(ta=math.radians(90)), 298.15)
    bad = core.restraint_cost_kj(_restraint(ta=math.radians(170)), 298.15)
    assert bad - ok == pytest.approx(-298.15 * core.R_KJ * math.log(math.sin(math.radians(170))), abs=1e-6)


# --- the lambda schedule --------------------------------------------------------

def test_complex_leg_restrains_first_then_charges_then_vdw():
    s = core.schedule("complex")
    assert len(s) == 34
    assert (s.restraint[0], s.coul[0], s.vdw[0]) == (0.0, 0.0, 0.0)
    first_coul = next(i for i, c in enumerate(s.coul) if c > 0)
    assert all(r == 1.0 for r in s.restraint[first_coul:])
    first_vdw = next(i for i, v in enumerate(s.vdw) if v > 0)
    assert all(c == 1.0 for c in s.coul[first_vdw:])  # no bare charges without repulsion
    for xs in (s.restraint, s.coul, s.vdw):
        assert xs == sorted(xs)
    assert (s.coul[-1], s.vdw[-1]) == (1.0, 1.0)


def test_solvent_leg_has_no_restraints():
    s = core.schedule("solvent")
    assert len(s) == 25 and not any(s.restraint)
    assert "restraint-lambdas" not in s.mdp()


# --- choosing the anchors ---------------------------------------------------------

def _pocket():
    """Eight C-alpha atoms around a flat six-carbon ligand at the origin."""
    atoms, i = [], 1
    for k in range(8):
        th = 2 * math.pi * k / 8
        atoms.append(_atom(i, k + 1, "ALA", "CA", (0.6 * math.cos(th), 0.6 * math.sin(th), 0.3 * (-1) ** k)))
        i += 1
    for k in range(6):
        th = 2 * math.pi * k / 6
        atoms.append(_atom(i, 99, "LIG", f"C{k + 1}", (0.14 * math.cos(th), 0.14 * math.sin(th), 0.0)))
        i += 1
    return atoms


def test_anchors_keep_every_angle_well_away_from_collinear():
    r = core.choose_restraint(_pocket(), "LIG")
    assert r.quality > 0.7
    for th in (r.theta_a, r.theta_b):
        assert 30 < math.degrees(th) < 150
    assert all(a.name == "CA" for a in r.protein)
    assert all(a.resname == "LIG" for a in r.ligand)
    assert 0.3 <= r.r <= 1.2


def test_the_gromacs_block_is_off_in_A_and_on_in_B():
    block = core.choose_restraint(_pocket(), "LIG").gromacs()
    assert "[ intermolecular_interactions ]" in block
    bond = next(l for l in block.splitlines() if l.strip() and l.split()[2:3] == ["6"])
    f = bond.split()
    assert float(f[4]) == 0.0 and float(f[6]) == core.K_DISTANCE


def test_a_missing_ligand_names_what_is_there():
    with pytest.raises(ValueError, match="LIG"):
        core.ligand_atoms(_pocket(), "BNZ")


def test_bar_total_is_read_from_the_final_results():
    assert core.read_bar(BAR_TAIL) == (3.05, 1.46)


# --- the command ------------------------------------------------------------------

def _inputs(tmp_path: Path):
    atoms = _pocket()
    gro = tmp_path / "complex.gro"
    lines = ["test complex", f"{len(atoms):5d}"]
    for a in atoms:
        x, y, z = a.xyz
        lines.append(f"{a.resnr:5d}{a.resname:<5}{a.name:>5}{a.index:5d}{x + 2:8.3f}{y + 2:8.3f}{z + 2:8.3f}")
    gro.write_text("\n".join(lines) + "\n   4.00000   4.00000   4.00000\n")
    itp = tmp_path / "lig.itp"
    itp.write_text("[ moleculetype ]\n; name nrexcl\nLIG  3\n[ atoms ]\n")
    top = tmp_path / "topol.top"
    top.write_text('#include "amber99sb-ildn.ff/forcefield.itp"\n#include "lig.itp"\n\n'
                   "[ system ]\ntest\n\n[ molecules ]\nLIG 1\n")
    return gro, top, itp


def run(tmp_path, *extra, inhibitor=QUINOLINE):
    gro, top, itp = _inputs(tmp_path)
    return main(["--ec", "1.1.1.27", "--organism", "human", "--html", str(KI_PAGE),
                 "--inhibitor", inhibitor, "--complex", str(gro), "--topology", str(top),
                 "--ligand", "LIG", "--ligand-itp", str(itp), "--out", str(tmp_path / "out"), *extra])


def test_it_runs_at_the_kis_measured_temperature(tmp_path, capsys):
    assert run(tmp_path) == 0
    out = tmp_path / "out"
    rec = json.loads((out / "caterva-fep.json").read_text())
    assert rec["temperature_k"] == pytest.approx(310.15)
    assert rec["temperature_origin"] == "measured"
    assert rec["target"]["band_kcal"] == pytest.approx([-8.84, -7.95], abs=0.005)
    assert "ref-t                   = 310.15" in (out / "complex" / "prod.mdp").read_text()
    assert "measured" in capsys.readouterr().out


def test_the_legs_are_what_double_decoupling_needs(tmp_path):
    run(tmp_path)
    out = tmp_path / "out"
    cplx = (out / "complex" / "prod.mdp").read_text()
    solv = (out / "solvent" / "prod.mdp").read_text()
    assert "couple-moltype          = LIG" in cplx
    assert "restraint-lambdas" in cplx and "restraint-lambdas" not in solv
    assert "[ intermolecular_interactions ]" in (out / "complex" / "topol.top").read_text()
    stop = (out / "solvent" / "topol.base.top").read_text()
    assert '#include "lig.itp"' in stop and "[ intermolecular_interactions ]" not in stop
    assert (out / "solvent" / "ligand.gro").read_text().count("LIG") == 7  # title + 6 atoms
    script = (out / "run.sh").read_text()
    assert "SEEDS=(20260928 20260929 20260930)" in script and "bar -f" in script


def test_provenance_cites_every_method_by_doi(tmp_path):
    run(tmp_path)
    text = (tmp_path / "out" / "PROVENANCE.md").read_text()
    for doi in ("10.1016/S0006-3495(97)78756-3", "10.1021/jp0217839", "10.1016/0021-9991(76)90078-4",
                "10.1016/0009-2614(94)00397-1", "10.1080/08927028808080941"):
        assert doi in text
    assert "YOURS" in text  # the ligand topology is the user's, and says so


def test_an_inhibitor_without_a_ki_is_refused(tmp_path, capsys):
    assert run(tmp_path, inhibitor="oxamate") == 3
    assert "gossypol" in capsys.readouterr().err


def test_a_wrong_ligand_name_is_refused_with_what_exists(tmp_path, capsys):
    gro, top, itp = _inputs(tmp_path)
    code = main(["--ec", "1.1.1.27", "--html", str(KI_PAGE), "--inhibitor", QUINOLINE,
                 "--complex", str(gro), "--topology", str(top), "--ligand", "BNZ",
                 "--ligand-itp", str(itp), "--out", str(tmp_path / "o")])
    assert code == 3 and "LIG" in capsys.readouterr().err


# --- summarising a finished run ------------------------------------------------------

def _finish(out: Path, complex_dg, solvent_dg, err=0.3):
    for leg, values in (("complex", complex_dg), ("solvent", solvent_dg)):
        for rep, dg in enumerate(values, start=1):
            d = out / leg / f"rep{rep}"
            d.mkdir(parents=True, exist_ok=True)
            (d / "bar.log").write_text(f"Final results in kJ/mol:\n\ntotal      0 -     33,   DG {dg} +/- {err}\n")


def test_summarise_closes_the_cycle_and_judges_it(tmp_path, capsys):
    run(tmp_path)
    out = tmp_path / "out"
    corr = json.loads((out / "caterva-fep.json").read_text())["restraint"]["correction_kj"]
    # Choose legs so each replica lands at -8.4 kcal/mol, inside the band.
    target_kj = -8.4 * 4.184
    solv = 20.0
    cplx = [solv + corr - target_kj + d for d in (-0.4, 0.0, 0.4)]
    _finish(out, cplx, [solv] * 3)
    capsys.readouterr()
    assert main(["--summarise", str(out)]) == 0
    text = capsys.readouterr().out
    assert "AGREES" in text and "-8.40" in text


def test_one_replica_is_not_a_result(tmp_path, capsys):
    run(tmp_path)
    out = tmp_path / "out"
    _finish(out, [40.0], [20.0])
    assert main(["--summarise", str(out)]) == 4
    assert "NOT A RESULT" in capsys.readouterr().out


def test_no_two_windows_or_stages_share_a_noise_seed(tmp_path):
    """SD's random forces come from ld-seed; a shared seed correlates windows
    that BAR treats as independent. Found by grompp on the first real run."""
    import re
    import subprocess
    run(tmp_path, "--replicas", "3")
    script = (tmp_path / "out" / "run.sh").read_text()
    expr = re.search(r'\$\(\((seed \+ 1000 \* lam \+ 100 \* i)\)\)', script).group(1)
    seen = set()
    for base in (20260928, 20260929, 20260930):
        for lam in range(34):
            for i in range(4):
                v = int(subprocess.run(["bash", "-c", f"seed={base}; lam={lam}; i={i}; echo $(({expr}))"],
                                       capture_output=True, text=True).stdout)
                assert v not in seen
                seen.add(v)


def test_the_solvent_build_can_be_rerun(tmp_path):
    """solvate and genion append to topol.top; a re-run must start clean."""
    run(tmp_path)
    script = (tmp_path / "out" / "run.sh").read_text()
    assert script.index("cp topol.base.top topol.top") < script.index("solvate")
