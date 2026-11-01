"""Hydrogen bonds between catalytic side chains, against gmx hbond on a real run."""
from __future__ import annotations

import gzip
import math
from pathlib import Path

import numpy as np
import pytest

from caterva.analyze import hbonds as hb
from caterva.analyze.__main__ import _gro_atoms, _gro_box, hbond_verdict
from caterva.md import xtc

FIX = Path(__file__).parent / "fixtures" / "md"


def _atoms(tmp_path):
    p = tmp_path / "lyso.gro"
    p.write_bytes(gzip.decompress((FIX / "lyso_1aki_res1-59.gro.gz").read_bytes()))
    return _gro_atoms(p)


def test_every_frame_matches_gmx_hbond_on_real_lysozyme(tmp_path):
    """Six catalytic pairs x 21 frames: the counts gmx hbond printed."""
    atoms = _atoms(tmp_path)
    traj = xtc.read(FIX / "lyso_1aki_res1-59.xtc")
    for line in (FIX / "lyso_1aki_rep1_gmx_hbond.txt").read_text().splitlines():
        a, b, *ref = (int(v) for v in line.split())
        _, _, mine = hb.occupancy(traj, hb.side_chain_group(atoms, a), hb.side_chain_group(atoms, b))
        assert mine == ref, (a, b)


def test_side_chain_groups_find_the_polar_hydrogens(tmp_path):
    atoms = _atoms(tmp_path)
    ser = hb.side_chain_group(atoms, 50)  # Ser: OG donates through HG
    names = {i: atoms[i][2] for i in range(len(atoms))}
    assert [(names[d], [names[h] for h in hs]) for d, hs in ser.donors] == [("OG", ["HG"])]
    asp = hb.side_chain_group(atoms, 52)  # Asp: two acceptors, no donor at pH 7
    assert sorted(names[i] for i in asp.acceptors) == ["OD1", "OD2"] and asp.donors == []
    with pytest.raises(ValueError):
        hb.side_chain_group(atoms, 54)  # Gly54: no side chain


def _geometry(angle_deg, da_nm=0.28):
    """Donor at the origin, H 0.1 nm along x, acceptor at angle_deg from D-H."""
    t = math.radians(angle_deg)
    x = np.array([[0, 0, 0], [0.1, 0, 0], [da_nm * math.cos(t), da_nm * math.sin(t), 0]], float)
    a = hb.Group(1, "SER", donors=[(0, [1])], acceptors=[0])
    b = hb.Group(2, "ASP", donors=[], acceptors=[2])
    return x, a, b


@pytest.mark.parametrize("angle,expect", [(0, 1), (29.5, 1), (30.5, 0), (90, 0)])
def test_the_angle_criterion_is_gmx_hbonds(angle, expect):
    x, a, b = _geometry(angle)
    assert hb.count_frame(x, np.eye(3) * 5, a, b) == expect


def test_the_distance_criterion_and_the_periodic_image():
    x, a, b = _geometry(0, da_nm=0.36)
    assert hb.count_frame(x, np.eye(3) * 5, a, b) == 0
    x, a, b = _geometry(0, da_nm=0.30)
    x[2] += [5.0, 0, 0]  # the acceptor one box length away: still 0.30 nm through the boundary
    assert hb.count_frame(x, np.eye(3) * 5, a, b) == 1


def test_a_triclinic_gro_box_is_read_whole():
    box = _gro_box("   7.01008   7.01008   4.95687   0.00000   0.00000   0.00000   0.00000   3.50504   3.50504")
    assert np.allclose(box[2], [3.50504, 3.50504, 4.95687]) and np.allclose(box[0], [7.01008, 0, 0])


@pytest.mark.parametrize("start,fr,verdict", [
    (1, [1.0, 0.95], "kept"), (1, [0.1, 0.0], "lost"), (0, [0.6, 0.9], "formed"),
    (0, [0.0, 0.05], "rarely formed"), (1, [1.0, 0.3], "replicas disagree"), (1, [0.5], "one replica"),
    (1, [0.5, 0.6], "partial"),
])
def test_verdicts(start, fr, verdict):
    o = hb.Occupancy("X–Y", [(f"rep{i}", f, f) for i, f in enumerate(fr)], start)
    assert hbond_verdict(o) == verdict
