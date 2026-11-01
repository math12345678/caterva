"""The native .xtc reader, against GROMACS's own decoding of a real file."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from caterva.md import xtc

FIX = Path(__file__).parent / "fixtures" / "md"


def test_every_coordinate_matches_gmx_trjconv_exactly():
    frames = xtc.read(FIX / "t4l_bnz_first6000.xtc")
    ref = np.load(FIX / "t4l_bnz_first6000_gmx.npz")["milli_nm"]
    assert len(frames) == ref.shape[0] == 3
    for f, r in zip(frames, ref):
        assert f.precision == 1000.0
        assert np.array_equal(np.rint(f.x * 1000).astype(np.int64), r.astype(np.int64))
    assert [f.time for f in frames] == [0.0, 10.0, 20.0]


def test_a_non_xtc_file_is_refused(tmp_path):
    p = tmp_path / "x.xtc"
    p.write_bytes(b"\x00\x00\x07\xe7" + b"\x00" * 60)  # magic 2023, not read
    with pytest.raises(ValueError, match="magic"):
        xtc.read(p)


def _dodecahedron(a):
    """GROMACS's rhombic dodecahedron (xy-square) box vectors, as rows."""
    return np.array([[a, 0, 0], [0, a, 0], [a / 2, a / 2, a * np.sqrt(2) / 2]])


def test_nearest_image_in_a_triclinic_box():
    box = _dodecahedron(6.0)
    d = np.array([[5.8, 0.1, 0.0]])
    assert np.allclose(xtc.nearest_image(d, box), [[-0.2, 0.1, 0.0]])
    far = np.array([[3.2, 3.2, 4.3]])  # nearly one box vector away
    assert np.linalg.norm(xtc.nearest_image(far, box)) < 1.0


def test_a_molecule_split_by_the_box_is_made_whole():
    box = _dodecahedron(5.0)
    mol = np.array([[4.9, 1.0, 1.0], [0.05, 1.0, 1.0], [0.2, 1.1, 1.0]])  # wrapped across x
    whole = xtc.make_whole(mol, box)
    assert np.all(np.linalg.norm(np.diff(whole, axis=0), axis=1) < 0.3)


def test_rmsf_is_zero_for_a_rigid_motion_and_measures_a_wobble():
    rng = np.random.default_rng(0)
    base = rng.normal(size=(20, 3))
    box = np.eye(3) * 50
    def rot(t):
        c, s = np.cos(t), np.sin(t)
        return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])
    rigid = [xtc.Frame(0, 0.0, box, base @ rot(t) + [1, 2, 3], 1000.0) for t in (0, 0.3, 1.1)]
    assert np.allclose(xtc.rmsf(rigid, range(20), base), 0.0, atol=1e-9)
    wobble = [xtc.Frame(0, 0.0, box, base + np.where(np.arange(20)[:, None] == 5, s, 0.0), 1000.0)
              for s in (-0.1, 0.1)]
    f = xtc.rmsf(wobble, range(20), base)
    assert f[5] > 5 * np.median(f)
