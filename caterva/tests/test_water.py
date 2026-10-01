"""Water at the catalytic residues (caterva/analyze/water.py), against gmx select.

The anchor is a real trajectory with its water: residues 1-59 of hen
lysozyme and the 272 waters that came within 1.0 nm of a catalytic group in
any frame of replica 1 or in em.gro (fixtures/md/lyso_1aki_res1-59_water.*;
fixtures/md/README.md says how it was cut). `gmx select -os` counted the
water oxygens within 0.35 nm of each of the six catalytic residues' functional
atoms on that fixture, and on the full 23,873-atom system: the same counts
in every frame, so the fixture holds every water that matters. Those counts
are fixtures/md/lyso_1aki_rep1_gmx_water.txt. No water reaches a catalytic
atom only through the periodic box in those frames, so they are checked
again translated so that the active site straddles it
(lyso_1aki_res1-59_water_wrapped.*), where gmx select printed the same
counts on the full system.
"""
from __future__ import annotations

import gzip
import json
from pathlib import Path

import numpy as np
import pytest

from caterva.analyze.__main__ import (AnalyzeError, Analysis, _gro_atoms, _gro_box, _gro_index, angle_section,
                                      commands, gromacs_angles, gromacs_water, measure_native, water_section)
from caterva.analyze.plan import Atom, plan
from caterva.analyze import water as wat
from caterva.md import xtc

MD = Path(__file__).parent / "fixtures" / "md"
LYSOZYME = {35: ("OE1", "OE2"), 46: ("OD1", "ND2"), 48: ("OD1", "OD2"), 50: ("OG",),
            52: ("OD1", "OD2"), 59: ("OD1", "ND2")}


def gmx_water():
    """resnr -> (count in em.gro, the 21 per-frame counts gmx select printed)."""
    out = {}
    for line in (MD / "lyso_1aki_rep1_gmx_water.txt").read_text().splitlines():
        parts = line.split()
        out[int(parts[0])] = (int(parts[2]), [int(v) for v in parts[3:]])
    return out


@pytest.fixture(scope="module")
def solvated(tmp_path_factory):
    gro = tmp_path_factory.mktemp("lyso") / "em.gro"
    gro.write_bytes(gzip.decompress((MD / "lyso_1aki_res1-59_water.gro.gz").read_bytes()))
    return gro, xtc.read(MD / "lyso_1aki_res1-59_water.xtc")


def test_every_count_equals_gmx_select_on_real_lysozyme(solvated):
    gro, traj = solvated
    atoms, index = _gro_atoms(gro), _gro_index(gro)
    oxygens = np.array(wat.water_oxygens(atoms))
    box = _gro_box(gro.read_text().splitlines()[-1])
    start_x = np.array([a[3] for a in atoms])
    reference = gmx_water()
    assert sorted(reference) == sorted(LYSOZYME) and all(len(v) == 21 for _, v in reference.values())
    for resnr, (at_start, per_frame) in reference.items():
        site = [index[(resnr, n)] for n in LYSOZYME[resnr]]
        assert wat.counts(traj, site, oxygens) == per_frame, resnr
        assert wat.count_frame(start_x, box, site, oxygens) == at_start, resnr


@pytest.fixture(scope="module")
def wrapped(tmp_path_factory):
    gro = tmp_path_factory.mktemp("wrapped") / "em.gro"
    gro.write_bytes(gzip.decompress((MD / "lyso_1aki_res1-59_water_wrapped.gro.gz").read_bytes()))
    return gro, xtc.read(MD / "lyso_1aki_res1-59_water_wrapped.xtc")


def test_every_count_equals_gmx_select_across_the_periodic_boundary(wrapped):
    """The same frames translated so that the active site straddles the
    periodic box (fixtures/md/README.md). On the fixture above no water is
    near a catalytic atom only through the boundary, so a count without
    nearest images would pass there. Here it would be wrong in most
    residue-frames, and the count still equals gmx select's in every frame
    and at the start. gmx select printed the same counts on the wrapped full
    system as on the unwrapped one, so the reference is the same file."""
    gro, traj = wrapped
    atoms, index = _gro_atoms(gro), _gro_index(gro)
    oxygens = np.array(wat.water_oxygens(atoms))
    box = _gro_box(gro.read_text().splitlines()[-1])
    start_x = np.array([a[3] for a in atoms])
    wrong_without_images = 0
    for resnr, (at_start, per_frame) in gmx_water().items():
        site = [index[(resnr, n)] for n in LYSOZYME[resnr]]
        assert wat.counts(traj, site, oxygens) == per_frame, resnr
        assert wat.count_frame(start_x, box, site, oxygens) == at_start, resnr
        for f, expected in zip(traj, per_frame):
            d = np.linalg.norm(f.x[oxygens][:, None, :] - f.x[site][None, :, :], axis=-1)
            wrong_without_images += int((d.min(1) <= wat.WATER_NM).sum()) != expected
    # 103 of the 126 residue-frames, when this fixture was made.
    assert wrong_without_images > 80


def test_the_fixture_is_what_its_readme_says(solvated):
    gro, traj = solvated
    atoms = _gro_atoms(gro)
    assert len(atoms) == 1716 and len(traj) == 21 and all(f.x.shape == (1716, 3) for f in traj)
    assert {a[0] for a in atoms[:900]} == set(range(1, 60))
    water = atoms[900:]
    assert [a[2] for a in water[:3]] == ["OW", "HW1", "HW2"] and {a[1] for a in water} == {"SOL"}
    assert len(wat.water_oxygens(atoms)) == 272


def test_water_is_sol_ow_as_caterva_md_writes_it():
    x = np.zeros(3)
    atoms = [(1, "SER", "OG", x), (2, "SOL", "OW", x), (2, "SOL", "HW1", x), (2, "SOL", "HW2", x),
             (3, "CL", "CL", x), (4, "NA", "NA", x), (5, "SOL", "OW", x)]
    assert wat.water_oxygens(atoms) == [1, 6]


def _frame(*points):
    return np.array(points, dtype=float)


def test_the_cutoff_and_the_periodic_image():
    box = np.diag([3.0, 3.0, 3.0])
    x = _frame([1.0, 1.0, 1.0],            # the functional atom
               [1.0, 1.0, 1.34],           # 0.34 nm: counted
               [1.0, 1.0, 1.36],           # 0.36 nm: not
               [2.7, 1.0, 1.0])            # 1.7 nm as stored, 1.3 nm through the boundary: not
    assert wat.count_frame(x, box, [0], np.array([1, 2, 3])) == 1
    x[0] = [0.1, 1.0, 1.0]                 # the atom moves to the near side of the box:
    x[3] = [2.8, 1.0, 1.0]                 # 2.7 nm as stored, 0.3 nm through the boundary
    assert wat.count_frame(x, box, [0], np.array([3])) == 1


def test_a_water_near_two_functional_atoms_counts_once():
    box = np.diag([5.0, 5.0, 5.0])
    x = _frame([1.0, 1.0, 1.0], [1.22, 1.0, 1.0],   # a carboxylate's two oxygens
               [1.11, 1.25, 1.0])                   # a water 0.27 nm from each
    assert wat.count_frame(x, box, [0, 1], np.array([2])) == 1


def test_no_water_is_a_count_of_zero_not_an_error():
    assert wat.counts([], [0], []) == []
    assert wat.count_frame(_frame([0, 0, 0]), np.eye(3) * 3, [0], np.array([], dtype=int)) == 0
    name, mean, fraction = wat.summarise_counts("rep1", [])
    assert name == "rep1" and np.isnan(mean) and np.isnan(fraction)


def test_mean_and_fraction_with_water():
    assert wat.summarise_counts("rep1", [0, 2, 1, 0]) == ("rep1", 0.75, 0.5)


def _h(start, *fractions):
    return wat.Hydration("Ser50", start, [(f"rep{i}", f, f) for i, f in enumerate(fractions)])


@pytest.mark.parametrize("h,verdict", [
    (_h(1, 0.95), "one replica"),
    (_h(1, 0.9, 1.0), "hydrated"),
    (_h(0, 0.0, 0.1), "dry"),
    (_h(1, 0.5, 0.6), "intermittent"),
    (_h(1, 1.0, 0.3), "replicas disagree"),
])
def test_verdicts(h, verdict):
    assert wat.hydration_verdict(h) == verdict


def test_a_replica_with_no_frames_is_not_called_intermittent():
    # summarise_counts gives NaN for an empty series, and every comparison
    # with NaN is False, so it used to fall through to "intermittent".
    empty = wat.summarise_counts("rep1", [])
    h = wat.Hydration("Ser50", 1, [empty, wat.summarise_counts("rep2", [1, 1, 1])])
    assert wat.hydration_verdict(h) == "no frames"
    p = _three_sites()
    rows = [wat.Hydration(s.label, 1, [empty, ("rep2", 1.0, 1.0)]) for s in p.sites]
    section = water_section(Analysis("9XYZ", "A", "test", p, [], None, None, None, [], rows))
    row = next(l for l in section if l.startswith("| His10"))
    assert row == "| His10 | ND1 NE2 | 1 | n/a | 1.00 (1.00) | no frames |"


def test_a_ca_stand_in_is_counted_but_named_as_one_and_given_no_verdict():
    """Water at a CA is backbone exposure, not the hydration of a catalytic
    group; the angles leave stand-ins out for the same reason."""
    p = _three_sites(gly=True)
    gly = next(s for s in p.sites if s.resnr == 40)
    assert not gly.functional and gly.atoms == ("CA",)
    rows = [wat.Hydration(s.label, 1, [("rep1", 1.0, 1.0), ("rep2", 1.0, 1.0)]) for s in p.sites]
    section = water_section(Analysis("9XYZ", "A", "test", p, [], None, None, None, [], rows))
    assert f"| Gly40 | CA (stand-in) | 1 | 1.00 (1.00) | 1.00 (1.00) | {wat.STAND_IN} |" in section
    assert any(l.startswith("Gly40: no functional atoms defined") for l in section)
    assert all("stand-in" not in l for l in section if l.startswith("| His10"))


def test_the_selection_is_the_one_gmx_select_was_checked_with():
    assert wat.selection(35, ("OE1", "OE2")) == \
        "resname SOL and name OW and within 0.35 of (resnr 35 and name OE1 OE2)"


# --- both routes, on the real frames ------------------------------------------------------

def _setup(tmp_path, gro_text: str, xtc_path: Path):
    """A `caterva md` directory with one replica, from a fixture: em.gro the
    fixture's structure, protein.pdb its protein atoms (in Angstrom), and
    rep1/md.xtc its frames."""
    (tmp_path / "em.gro").write_text(gro_text)
    atoms = _gro_atoms(tmp_path / "em.gro")
    protein = [Atom("A", r, n, name, tuple(float(v) * 10 for v in xyz))
               for r, n, name, xyz in atoms if n != "SOL"]
    rep = tmp_path / "rep1"
    rep.mkdir()
    (rep / "md.xtc").write_bytes(xtc_path.read_bytes())
    return protein, rep


def test_both_routes_give_the_same_water_and_angles_on_real_frames(tmp_path):
    """The native route measured from the fixture's frames, against the
    GROMACS route reading what gmx select and gmx gangle printed for them."""
    gro_text = gzip.decompress((MD / "lyso_1aki_res1-59_water.gro.gz").read_bytes()).decode()
    protein, rep = _setup(tmp_path, gro_text, MD / "lyso_1aki_res1-59_water.xtc")
    order = [48, 50, 46, 59, 52, 35]      # M-CSA's order, as the lysozyme run had it
    p = plan(protein, [(r, next(a.resname for a in protein if a.resnr == r)) for r in order])
    assert len(p.angles) == 24
    angles, water = measure_native(tmp_path, p, [rep])[4:6]

    reference = gmx_water()
    (tmp_path / "water_start.xvg").write_text(
        "0.0 " + " ".join(str(reference[s.resnr][0]) for s in p.sites) + "\n")
    (rep / "water.xvg").write_text("".join(
        f"{t * 0.5:.1f} " + " ".join(str(reference[s.resnr][1][t]) for s in p.sites) + "\n" for t in range(21)))
    printed = {}
    for line in (MD / "lyso_1aki_rep1_gmx_angles.txt").read_text().splitlines():
        parts = line.split()
        printed[tuple(int(v) for v in parts[:3])] = parts[3:]
    (rep / "angles.xvg").write_text("".join(
        f"{t * 0.5:.1f} " + " ".join(printed[(a.a.resnr, a.v.resnr, a.b.resnr)][t] for a in p.angles) + "\n"
        for t in range(21)))

    assert gromacs_water(tmp_path, p, [rep]) == water
    via_gmx = gromacs_angles(p, [rep])
    assert [a.label for a in via_gmx] == [a.label for a in angles]
    assert max(abs(g.summary.mean - n.summary.mean) for g, n in zip(via_gmx, angles)) < 0.001
    assert [g.summary.verdict for g in via_gmx] == [n.summary.verdict for n in angles] == ["one sample"] * 24

    # The water table a reader sees is the same text from either route.
    native = Analysis("1AKI", None, "test", p, [], None, None, None, angles, water)
    gromacs = Analysis("1AKI", None, "test", p, [], None, None, None, via_gmx, gromacs_water(tmp_path, p, [rep]))
    assert water_section(native) == water_section(gromacs)
    assert "| Asp48 | OD1 OD2 | 2 | 2.00 (1.00) | one replica |" in water_section(native)
    assert "| Ser50 | OG | 1 | 0.90 (0.90) | one replica |" in water_section(native)
    assert len([l for l in angle_section(native) if l.startswith("| ") and "–" in l]) == 24


def _three_sites(gly: bool = False):
    """His10, Asp20 and Ser30, each with its functional atoms (Angstrom);
    with `gly`, also Gly40, which has none and stands in with its CA."""
    rows = [(1, "ND1", "HIS", 10, 1.0, 0.0), (2, "NE2", "HIS", 10, 1.0, 2.0), (3, "OD1", "ASP", 20, 5.0, 0.0),
            (4, "OD2", "ASP", 20, 5.0, 2.0), (5, "OG", "SER", 30, 1.0, 6.0)]
    if gly:
        rows.append((6, "CA", "GLY", 40, 1.0, -3.0))
    atoms = [Atom("A", r, n, name, (x, y, 0.0)) for _, name, n, r, x, y in rows]
    return plan(atoms, [(10, "HIS"), (20, "ASP"), (30, "SER")] + ([(40, "GLY")] if gly else []))


def test_one_catalytic_residue_says_why_no_verdict_can_be_a_result(tmp_path, capsys):
    """With one catalytic group there is no distance, and the distances are
    what the other sections' verdicts rest on. That is said once, under the
    empty distance table, rather than left for the reader to infer from a
    column of "not yet a result"."""
    from caterva.analyze.__main__ import EXIT_NOT_A_RESULT, main
    (tmp_path / "caterva-setup.json").write_text(json.dumps({"pdb": "9XYZ", "chain": "A"}))
    (tmp_path / "protein.pdb").write_text(
        "ATOM      1  CA  SER A  30       0.000   7.500   0.000  1.00 20.00           C\n"
        "ATOM      2  OG  SER A  30       1.000   6.000   0.000  1.00 20.00           O\n"
        "ATOM      3  CA  ALA A  90      30.000   0.000   0.000  1.00 20.00           C\nEND\n")
    for r in ("rep1", "rep2"):
        d = tmp_path / r
        d.mkdir()
        (d / "md.xtc").write_text("")
        (d / "md.tpr").write_text("")
        (d / "rmsf.xvg").write_text("30 0.05\n90 0.20\n")
        (d / "water.xvg").write_text("0.0 1\n0.5 2\n")
        (d / "sasa.xvg").write_text("0.0 9.0 0.4\n0.5 9.0 0.5\n")  # gmx sasa -o; made-up areas
    (tmp_path / "water_start.xvg").write_text("0.0 1\n")
    (tmp_path / "sasa_start.xvg").write_text("0.0 9.0 0.4\n")
    code = main([str(tmp_path), "--no-run"], catalytic=lambda pdb, chain: ([(30, "SER")], "a test mapping"))
    out = capsys.readouterr().out
    assert code == EXIT_NOT_A_RESULT
    assert "- No catalytic distance: fewer than two catalytic groups" in out.split("## Hydrogen bonds")[0]
    assert "| Ser30 | OG | 1 | 1.50 (1.00) | 1.50 (1.00) | (hydrated, not yet a result) |" in out


def test_one_select_call_per_replica_and_one_for_the_start():
    p = _three_sites()
    lines = commands(p, ["rep1", "rep2"])
    select = [l for l in lines if " select " in l]
    assert [l.split(" -os ")[1] for l in select] == ["rep1/water.xvg", "rep2/water.xvg", "water_start.xvg"]
    assert select[0].startswith("$GMX select -s rep1/md.tpr -f rep1/md.xtc -select ")
    assert select[-1].startswith("$GMX select -s rep1/md.tpr -f em.gro -select ")
    assert all(f"'{wat.selection(s.resnr, s.atoms)}'" in select[0] for s in p.sites)


def test_a_missing_or_stale_select_output_is_refused(tmp_path):
    p = _three_sites()
    rep = tmp_path / "rep1"
    rep.mkdir()
    (rep / "water.xvg").write_text("0.0 1 2 3\n")
    with pytest.raises(AnalyzeError, match="water_start.xvg does not exist"):
        gromacs_water(tmp_path, p, [rep])
    (tmp_path / "water_start.xvg").write_text("0.0 1 2\n")
    with pytest.raises(AnalyzeError, match="2 columns of water"):
        gromacs_water(tmp_path, p, [rep])
