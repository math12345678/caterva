"""`caterva complex`: your ligand, in the crystal's pose, or a refusal that says why.

The superposition is checked on a case with a known answer: a ligand
rotated and moved by a known transform must come back onto the original to
numerical precision, hydrogens included, and never as a mirror image.
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest

from caterva.fep import complex as cx


def _rot(axis, theta):
    x, y, z = np.asarray(axis, float) / np.linalg.norm(axis)
    c, s = math.cos(theta), math.sin(theta)
    return np.array([[c + x * x * (1 - c), x * y * (1 - c) - z * s, x * z * (1 - c) + y * s],
                     [y * x * (1 - c) + z * s, c + y * y * (1 - c), y * z * (1 - c) - x * s],
                     [z * x * (1 - c) - y * s, z * y * (1 - c) + x * s, c + z * z * (1 - c)]])


# A chiral, non-planar heavy-atom set (so a reflection would be detectable).
HEAVY = {"C1": (0.0, 0.0, 0.0), "C2": (0.15, 0.0, 0.0), "N3": (0.2, 0.13, 0.0),
         "O4": (0.1, 0.2, 0.08), "C5": (-0.05, 0.12, -0.1)}


def _crystal():
    return [cx.LigandAtom(n, cx._element(n), np.array(v)) for n, v in HEAVY.items()]


def _yours(R, t, with_h=True):
    atoms = [cx.LigandAtom(n, cx._element(n), np.array(v) @ R + t) for n, v in HEAVY.items()]
    if with_h:
        atoms.append(cx.LigandAtom("H1", "H", np.array([0.0, -0.1, 0.0]) @ R + t))
    return atoms


def test_a_known_transform_is_undone_exactly():
    R, t = _rot([1, 2, 3], 1.3), np.array([3.0, -1.0, 2.0])
    pose = cx.pose_onto_crystal(_yours(R, t), _crystal())
    assert pose.rmsd_nm < 1e-9
    placed = {a.name: a.xyz for a in pose.atoms}
    for n, v in HEAVY.items():
        assert np.allclose(placed[n], v, atol=1e-9)
    # The hydrogen travels with its molecule.
    assert np.allclose(placed["H1"], [0.0, -0.1, 0.0], atol=1e-9)


def test_a_mirror_image_is_refused_even_when_its_rmsd_passes():
    """Found writing this test: the enantiomer of this five-atom ligand fits
    the crystal at 0.86 A, under the 1 A threshold. A Ki belongs to one
    stereoisomer, so handedness is checked directly, not through RMSD."""
    mirror = np.diag([1.0, 1.0, -1.0])
    yours = [cx.LigandAtom(n, cx._element(n), np.array(v) @ mirror) for n, v in HEAVY.items()]
    P = np.array([a.xyz for a in yours])
    Q = np.array([a.xyz for a in _crystal()])
    R, t = cx.kabsch(P, Q)
    assert np.sqrt(((P @ R + t - Q) ** 2).sum(1).mean()) < cx.MAX_RMSD_NM  # RMSD alone would accept it
    with pytest.raises(ValueError, match="stereoisomer"):
        cx.pose_onto_crystal(yours, _crystal())


def test_a_flat_ligand_has_no_handedness_to_get_wrong():
    ring = {f"C{k + 1}": (0.139 * math.cos(math.radians(60 * k)), 0.139 * math.sin(math.radians(60 * k)), 0.0)
            for k in range(6)}
    crystal = [cx.LigandAtom(n, "C", np.array(v)) for n, v in ring.items()]
    flipped = [cx.LigandAtom(n, "C", np.array(v) @ np.diag([1.0, 1.0, -1.0])) for n, v in ring.items()]
    assert cx.pose_onto_crystal(flipped, crystal).rmsd_nm < 1e-9


def test_fewer_than_three_shared_names_is_refused_with_both_lists():
    yours = [cx.LigandAtom(n, "C", np.zeros(3)) for n in ("CA", "CB", "C1")]
    with pytest.raises(ValueError) as e:
        cx.pose_onto_crystal(yours, _crystal())
    assert "C1" in str(e.value) and "CB" in str(e.value) and "only 1" in str(e.value)


def test_a_different_conformer_is_refused():
    bent = dict(HEAVY, O4=(0.1, 0.2, 0.45))  # 0.37 nm away: not the crystal's shape
    yours = [cx.LigandAtom(n, cx._element(n), np.array(v)) for n, v in bent.items()]
    with pytest.raises(ValueError, match="RMSD"):
        cx.pose_onto_crystal(yours, _crystal())


PDB = """\
ATOM      1  N   ALA A   1      10.000  10.000  10.000  1.00  0.00           N
ATOM      2  CA  ALA A   1      11.000  10.000  10.000  1.00  0.00           C
TER
ATOM      3  N   GLY B   1      20.000  10.000  10.000  1.00  0.00           N
HETATM    4  C1  LIG A 400       1.000   2.000   3.000  1.00  0.00           C
HETATM    5  C1  LIG A 401       9.000   9.000   9.000  1.00  0.00           C
HETATM    6  O   HOH A 500       0.000   0.000   0.000  1.00  0.00           O
HETATM    7  C1  EDO A 600       0.000   0.000   0.000  1.00  0.00           C
"""


def test_the_first_copy_of_the_ligand_is_taken_in_nm():
    atoms, where = cx.crystal_ligand(PDB, "LIG")
    assert len(atoms) == 1 and where == "chain A residue 400"
    assert np.allclose(atoms[0].xyz, [0.1, 0.2, 0.3])


def test_a_missing_ligand_names_what_the_entry_has():
    with pytest.raises(ValueError) as e:
        cx.crystal_ligand(PDB, "BNZ")
    assert "EDO" in str(e.value) and "LIG" in str(e.value) and "HOH" not in str(e.value)


def test_the_protein_keeps_its_chain_and_drops_every_hetatm():
    text, dropped = cx.protein_pdb(PDB, "A")
    assert "GLY B" not in text and "ALA A" in text and "HETATM" not in text
    assert dropped == {"LIG": 2, "HOH": 1, "EDO": 1}


def test_the_command_writes_a_build_from_a_local_entry(tmp_path, capsys):
    (tmp_path / "1abc.pdb").write_text("".join(
        f"HETATM{i:5d}  {n:<3} LIG A 400    {x * 10:8.3f}{y * 10:8.3f}{z * 10:8.3f}  1.00  0.00           {n[0]}\n"
        for i, (n, (x, y, z)) in enumerate(HEAVY.items(), 1)) + PDB.split("HETATM")[0])
    R, t = _rot([0, 1, 1], 0.7), np.array([2.0, 2.0, 2.0])
    lines = ["tool output", f"{len(HEAVY) + 1:5d}"]
    for i, a in enumerate(_yours(R, t), 1):
        lines.append(f"{1:5d}{'LIG':<5}{a.name:>5}{i:5d}{a.xyz[0]:8.3f}{a.xyz[1]:8.3f}{a.xyz[2]:8.3f}")
    (tmp_path / "lig.gro").write_text("\n".join(lines) + "\n   5.0 5.0 5.0\n")
    (tmp_path / "lig.itp").write_text("[ moleculetype ]\nLIG 3\n")
    out = tmp_path / "out"
    code = cx.main(["--pdb", str(tmp_path / "1abc.pdb"), "--ligand", "LIG", "--ligand-itp", str(tmp_path / "lig.itp"),
                    "--ligand-coords", str(tmp_path / "lig.gro"), "--out", str(out)])
    assert code == 0
    for f in ("protein.pdb", "ligand.gro", "lig.itp", "build.sh", "BUILD.md", "em.mdp", "nvt.mdp", "npt.mdp"):
        assert (out / f).is_file(), f
    build = (out / "build.sh").read_text()
    assert "'#include \"lig.itp\"'" in build and "genion" in build and "npt" in build
    assert "10.1107/S0567739476001873" in (out / "BUILD.md").read_text()
    # The gro rounds to 1e-3 nm, so the fit is exact to that, not to 1e-9.
    assert "RMSD 0.00" in capsys.readouterr().out


def test_a_local_entry_not_named_by_a_pdb_id_is_refused_and_says_so(tmp_path, capsys):
    (tmp_path / "e.pdb").write_text(PDB)
    (tmp_path / "i.itp").write_text("[ moleculetype ]\nLIG 3\n")
    (tmp_path / "l.gro").write_text("t\n    0\n   1.0 1.0 1.0\n")
    code = cx.main(["--pdb", str(tmp_path / "e.pdb"), "--ligand", "LIG", "--ligand-itp", str(tmp_path / "i.itp"),
                    "--ligand-coords", str(tmp_path / "l.gro"), "--out", str(tmp_path / "out")])
    assert code == cx.EXIT_REFUSED
    assert "is not a PDB id" in capsys.readouterr().err


# --- did the ligand keep its pose through equilibration ------------------------

def _write_gro(path, atoms):
    lines = ["t", f"{len(atoms):5d}"]
    for i, (res, name, xyz) in enumerate(atoms, 1):
        lines.append(f"{1:5d}{res:<5}{name:>5}{i:5d}{xyz[0]:8.3f}{xyz[1]:8.3f}{xyz[2]:8.3f}")
    path.write_text("\n".join(lines) + "\n   6.0 6.0 6.0\n")


def _system():
    ca = [("ALA", "CA", np.array(v)) for v in ((1, 1, 1), (1.4, 1, 1), (1, 1.5, 1.2), (1.3, 1.3, 1.8))]
    lig = [("LIG", n, np.array(v) + 1.2) for n, v in HEAVY.items()] + [("LIG", "H1", np.array([1.2, 1.1, 1.2]))]
    return ca + lig


def test_a_rigidly_moved_system_has_kept_its_pose(tmp_path, capsys):
    start = _system()
    R, t = _rot([1, 1, 0], 0.4), np.array([0.5, -0.2, 0.3])
    _write_gro(tmp_path / "boxed.gro", start)
    _write_gro(tmp_path / "npt.gro", [(r, n, x @ R + t) for r, n, x in start] + [("SOL", "OW", np.zeros(3))])
    assert cx.main(["--check", str(tmp_path), "--ligand", "LIG"]) == 0
    assert "KEPT" in capsys.readouterr().out
    lig, ca, n = cx.check(tmp_path, "LIG")
    assert lig < 1e-2 and ca < 1e-2 and n == 4  # gro precision is 1e-3 nm


def test_a_ligand_that_drifted_out_is_reported(tmp_path, capsys):
    start = _system()
    moved = [(r, n, x + (np.array([0.3, 0, 0]) if r == "LIG" else 0)) for r, n, x in start]
    _write_gro(tmp_path / "boxed.gro", start)
    _write_gro(tmp_path / "npt.gro", moved)
    assert cx.main(["--check", str(tmp_path), "--ligand", "LIG"]) == 4
    assert "LEFT its pose" in capsys.readouterr().out
    assert cx.check(tmp_path, "LIG")[0] == pytest.approx(0.3, abs=2e-3)


def test_check_refuses_output_from_another_build(tmp_path, capsys):
    _write_gro(tmp_path / "boxed.gro", _system())
    _write_gro(tmp_path / "npt.gro", [("GLY", "N", np.zeros(3))] * 10)
    assert cx.main(["--check", str(tmp_path), "--ligand", "LIG"]) == 3
    assert "not this build" in capsys.readouterr().err


# --- symmetry: a ring that turned in place has not left ---------------------------

RING = [(0.139 * math.cos(math.radians(60 * k)), 0.139 * math.sin(math.radians(60 * k)), 0.0) for k in range(6)]
RING_BONDS = [(k, (k + 1) % 6) for k in range(6)]


def test_benzene_has_twelve_graph_symmetries_and_an_asymmetric_chain_one():
    assert len(cx.automorphisms(["C"] * 6, RING_BONDS)) == 12
    assert len(cx.automorphisms(["C", "N", "O"], [(0, 1), (1, 2)])) == 1


def test_a_ring_rotated_sixty_degrees_is_the_same_pose():
    """Found on 181L: benzene rotated in its cavity read 2.70 A by atom name;
    counting its symmetric poses it was 0.77 A, centroid 0.29 A."""
    A = np.array(RING)
    B = A @ _rot([0, 0, 1], math.radians(60))
    assert np.sqrt(((A - B) ** 2).sum(1).mean()) > 0.13  # by name: every atom moved a bond length
    assert cx.symmetric_rmsd(A, B, cx.automorphisms(["C"] * 6, RING_BONDS)) < 1e-9
