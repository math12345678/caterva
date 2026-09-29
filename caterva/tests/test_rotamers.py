"""chi1 rotamers of catalytic residues (caterva/analyze/rotamers.py).

The anchor is real: `gmx angle -type dihedral` on six catalytic residues of
hen lysozyme (Glu35, Asn46, Asp48, Ser50, Asp52, Asn59), all 21 frames of a
`caterva md` replica (fixtures/md/lyso_1aki_rep1_gmx_chi1.txt). Asn59 sits
at the +/-180 wrap, which is where a sign or binning error would show.
"""
from __future__ import annotations

import gzip
from pathlib import Path

import numpy as np
import pytest

from caterva.analyze.rotamers import (
    Rotamer, chi1_atoms, chi1_series, dihedral, populations, rotamer_verdict, well,
)
from caterva.md import xtc

MD = Path(__file__).parent / "fixtures" / "md"


@pytest.fixture(scope="module")
def lysozyme():
    lines = gzip.decompress((MD / "lyso_1aki_res1-59.gro.gz").read_bytes()).decode().splitlines()
    n = int(lines[1])
    atoms = [(int(l[0:5]), l[5:10].strip(), l[10:15].strip(),
              np.array([float(l[20 + 8 * k:28 + 8 * k]) for k in range(3)])) for l in lines[2:2 + n]]
    return atoms, xtc.read(MD / "lyso_1aki_res1-59.xtc")


def gmx_chi1():
    out = {}
    for line in (MD / "lyso_1aki_rep1_gmx_chi1.txt").read_text().splitlines():
        parts = line.split()
        out[int(parts[0])] = [float(v) for v in parts[2:]]
    return out


def test_chi1_equals_gmx_angle_on_every_frame(lysozyme):
    atoms, traj = lysozyme
    reference = gmx_chi1()
    assert len(reference) == 6 and all(len(v) == 21 for v in reference.values())
    for resnr, expected in reference.items():
        got = chi1_series(traj, chi1_atoms(atoms, resnr))
        worst = max(abs((g - e + 180) % 360 - 180) for g, e in zip(got, expected))
        assert worst < 0.001, f"residue {resnr}: {worst:.4f} degrees from gmx angle"


def test_the_residue_at_the_wrap_is_in_one_well_not_two(lysozyme):
    atoms, traj = lysozyme
    series = chi1_series(traj, chi1_atoms(atoms, 59))
    assert any(v > 170 for v in series) and any(v < -170 for v in series)
    assert populations(series) == {"+60": 0.0, "180": 1.0, "-60": 0.0}


def test_the_gamma_atom_follows_iupac(lysozyme):
    atoms, _ = lysozyme
    names = lambda idx: [atoms[i][2] for i in idx]
    assert names(chi1_atoms(atoms, 50)) == ["N", "CA", "CB", "OG"]      # Ser50
    assert names(chi1_atoms(atoms, 35)) == ["N", "CA", "CB", "CG"]      # Glu35
    glycine = next(a[0] for a in atoms if a[1] == "GLY")
    assert chi1_atoms(atoms, glycine) is None


@pytest.mark.parametrize("chi,expected", [
    (0.0, "+60"), (60.0, "+60"), (119.9, "+60"), (120.0, "180"), (180.0, "180"),
    (-179.9, "180"), (-120.0, "-60"), (-60.0, "-60"), (-0.1, "-60"),
])
def test_wells(chi, expected):
    assert well(chi) == expected


def test_a_side_chain_split_across_the_boundary_reads_the_same():
    box = np.diag([3.0, 3.0, 3.0])
    p = [np.array(v) for v in ([0.0, 0.1, 0.0], [0.0, 0.0, 0.0], [0.15, 0.0, 0.0], [0.2, 0.0, 0.14])]
    whole = dihedral(*p, box)
    split = dihedral(p[0], p[1], p[2], p[3] + np.array([3.0, 0.0, 0.0]), box)
    assert split == pytest.approx(whole, abs=1e-9)
    # Looking from CA to CB (along +x), the front bond points along +y and
    # the back bond along +z: a clockwise quarter turn, +90 by IUPAC's rule.
    assert whole == pytest.approx(90.0, abs=1e-6)


def _rot(start, *kept_per_replica, dominant="-60"):
    reps = []
    for i, k in enumerate(kept_per_replica):
        rest = {w: 0.0 for w in ("+60", "180", "-60")}
        rest[well(start)] = k
        if dominant != well(start):
            rest[dominant] = 1.0 - k
        reps.append((f"rep{i + 1}", rest))
    return Rotamer("Ser50", start, reps)


@pytest.mark.parametrize("rotamer,verdict", [
    (_rot(60.0, 1.0), "one replica"),
    (_rot(60.0, 0.95, 0.9), "kept"),
    (_rot(60.0, 0.05, 0.1, dominant="-60"), "flipped to -60"),
    (_rot(60.0, 1.0, 0.1), "replicas disagree"),
    (_rot(60.0, 0.6, 0.5), "partial"),
])
def test_verdicts(rotamer, verdict):
    assert rotamer_verdict(rotamer) == verdict
