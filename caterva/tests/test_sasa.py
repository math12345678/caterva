"""Solvent exposure of the catalytic residues (caterva/analyze/sasa.py).

Three kinds of check. Geometry that has an answer on paper: one atom alone
has the whole area of its grown sphere, and two overlapping atoms each lose
the spherical cap the other covers. The shortcuts against the plain method:
the cell grid finds exactly the overlapping pairs a comparison of every
pair finds, and the patches decide exactly the points that testing each
point alone decides, on a real protein. And `gmx sasa` itself, which uses
a different set of points (the double cubic lattice), on two committed
structures (fixtures/md/README.md): every residue of T4 lysozyme against
`gmx sasa -ndots 10000` and `-ndots 2000`, and the six catalytic residues
of hen lysozyme in 21 real frames against the command analyze.sh runs.
"""
from __future__ import annotations

import gzip
import importlib.util
import math
import struct
from pathlib import Path

import numpy as np
import pytest
from scipy.spatial.distance import cdist

from caterva.analyze import sasa
from caterva.analyze.__main__ import (AnalyzeError, Analysis, _exposures, _gro_atoms, _gro_box, commands,
                                      gromacs_sasa, main, measure_native, sasa_section, sasa_unmeasurable)
from caterva.analyze.plan import Atom, plan
from caterva.md import xtc

MD = Path(__file__).parent / "fixtures" / "md"
REPO = Path(__file__).resolve().parents[2]
CATALYTIC = [48, 50, 46, 59, 52, 35]  # lysozyme's, in M-CSA's order, as the lysozyme run had them


def _gro(tmp_path_factory, name: str) -> Path:
    path = tmp_path_factory.mktemp(name.replace(".", "_")) / "em.gro"
    path.write_bytes(gzip.decompress((MD / f"{name}.gro.gz").read_bytes()))
    return path


def _brute(x: np.ndarray, radii: np.ndarray, dots: int) -> np.ndarray:
    """Shrake & Rupley with nothing left out: every point of every atom
    tested against every other atom whose grown sphere overlaps it."""
    R = radii + sasa.PROBE_NM
    u = sasa.sphere(dots)
    out = np.zeros(len(x))
    for i in range(len(x)):
        d = x - x[i]
        dist2 = (d * d).sum(1)
        near = np.flatnonzero((dist2 < (R + R[i]) ** 2) & (np.arange(len(x)) != i))
        t = (R[i] ** 2 + dist2[near] - R[near] ** 2) / (2.0 * R[i])
        with np.errstate(all="ignore"):
            buried = (u @ d[near].T > t).any(1)
        out[i] = 4.0 * math.pi * R[i] * R[i] * (dots - buried.sum()) / dots
    return out


# --- radii and points ----------------------------------------------------------------------

@pytest.mark.parametrize("name,r", [("CA", 0.17), ("C", 0.17), ("HB1", 0.12), ("H", 0.12), ("N", 0.155),
                                    ("NZ", 0.155), ("OD1", 0.152), ("OC2", 0.152), ("SG", 0.18),
                                    ("SD", 0.18), ("Cl", 0.175), ("CL", 0.17)])
def test_radii_are_the_ones_vdwradii_dat_lists(name, r):
    """By the longest entry the name starts with, as GROMACS reads the
    file. "CL" is not "Cl": the file is case-sensitive, and GROMACS gives a
    chloride named CL a carbon's radius too (only "C" is a prefix of it)."""
    assert sasa.radius(name) == r


@pytest.mark.parametrize("name", ["1HB", "ZN", "MW", ""])
def test_an_atom_name_no_radius_starts_is_refused(name):
    with pytest.raises(ValueError, match="no van der Waals radius"):
        sasa.radius(name)


def test_the_points_are_on_the_sphere_in_bands_of_equal_area():
    """Point k sits at z = 1 - (2k + 1)/n, so a band of the sphere holds
    its share of the points to within half a point, whatever the band."""
    n = 2000
    u = sasa.sphere(n)
    assert u.shape == (n, 3) and np.allclose((u * u).sum(1), 1.0)
    assert np.array_equal(u, sasa.sphere(n))
    for low, high in [(-1.0, 1.0), (0.0, 1.0), (-0.37, 0.52), (0.9, 1.0), (-1.0, -0.999)]:
        inside = int(((u[:, 2] > low) & (u[:, 2] <= high)).sum())
        assert abs(inside - n * (high - low) / 2) <= 1.0


# --- geometry with an answer on paper ------------------------------------------------------

@pytest.mark.parametrize("name", ["H", "C", "N", "O", "S"])
def test_an_isolated_atom_has_the_whole_area_of_its_grown_sphere(name):
    r = sasa.radius(name)
    area = sasa.atom_areas(np.array([[1.0, 2.0, 3.0]]), np.array([r]))
    assert area[0] == pytest.approx(4 * math.pi * (r + sasa.PROBE_NM) ** 2, rel=1e-12)
    assert sasa.atom_areas(np.zeros((1, 3)), np.array([r]), probe=0.0)[0] == pytest.approx(4 * math.pi * r * r)


def _cap_exposed(Ri: float, Rj: float, d: float) -> float:
    """The area of sphere i (radius Ri) outside sphere j (radius Rj) at
    distance d: the whole sphere less the cap inside j, 2 pi Ri^2 (1 - c),
    where c is the cosine of the cap's half-angle seen from i's centre."""
    c = (Ri * Ri + d * d - Rj * Rj) / (2 * Ri * d)
    return 2 * math.pi * Ri * Ri * (1 + min(max(c, -1.0), 1.0))


#: Two atoms at bonded and non-bonded distances (nm), along directions that
#: are not the points' own axis, where the bands would make it exact.
PAIRS = [("C", "C", 0.153), ("C", "O", 0.123), ("N", "H", 0.101), ("S", "S", 0.204), ("C", "H", 0.109),
         ("C", "O", 0.300), ("C", "N", 0.500), ("H", "H", 0.300)]
DIRECTIONS = [np.array(v) / np.linalg.norm(v) for v in ([1.0, 2.0, 3.0], [-0.3, 0.8, 0.52], [0.9, -0.1, -0.4])]


@pytest.mark.parametrize("a,b,d", PAIRS)
def test_two_atoms_each_lose_the_cap_the_other_covers(a, b, d):
    """At DOTS points the area is within 0.5% of the grown sphere of the
    answer (on these pairs the error was at most 0.39% when this was
    written), and at 32,000 points within 0.1% (0.057%): a cap's edge
    crosses the points, so the error falls as the points get denser."""
    ra, rb = sasa.radius(a), sasa.radius(b)
    Ra, Rb = ra + sasa.PROBE_NM, rb + sasa.PROBE_NM
    want = (_cap_exposed(Ra, Rb, d), _cap_exposed(Rb, Ra, d))
    for u in DIRECTIONS:
        x = np.array([[0.3, -0.2, 0.1], [0.3, -0.2, 0.1] + d * u])
        for dots, share in ((sasa.DOTS, 0.005), (32000, 0.001)):
            got = sasa.atom_areas(x, np.array([ra, rb]), dots=dots)
            for g, w, R in zip(got, want, (Ra, Rb)):
                assert abs(g - w) <= share * 4 * math.pi * R * R, (a, b, d, dots)


def test_atoms_out_of_reach_keep_their_area_and_a_swallowed_atom_has_none():
    rc, rh = sasa.radius("C"), sasa.radius("H")
    Rc, Rh = rc + sasa.PROBE_NM, rh + sasa.PROBE_NM
    far = sasa.atom_areas(np.array([[0.0, 0.0, 0.0], [Rc + Rh + 1e-6, 0.0, 0.0]]), np.array([rc, rh]))
    assert far == pytest.approx([4 * math.pi * Rc * Rc, 4 * math.pi * Rh * Rh], rel=1e-12)
    # The hydrogen's grown sphere (0.26 nm) lies wholly inside the carbon's
    # (0.31 nm) when their centres are 0.01 nm apart: no point of it is
    # left, and every point of the carbon's is outside the hydrogen's.
    inside = sasa.atom_areas(np.array([[0.0, 0.0, 0.0], [0.006, 0.008, 0.0]]), np.array([rc, rh]))
    assert inside[1] == 0.0 and inside[0] == pytest.approx(4 * math.pi * Rc * Rc, rel=1e-12)
    # At one point, the larger buries all of the smaller and loses nothing.
    same = sasa.atom_areas(np.zeros((2, 3)), np.array([rc, rh]))
    assert same[1] == 0.0 and same[0] == pytest.approx(4 * math.pi * Rc * Rc, rel=1e-12)


def test_no_atoms_and_one_atom_need_no_neighbours():
    assert sasa.atom_areas(np.zeros((0, 3)), np.zeros(0)).shape == (0,)
    i, j = sasa.neighbour_pairs(np.zeros((1, 3)), np.array([0.3]))
    assert len(i) == len(j) == 0


def test_a_coordinate_that_is_not_a_number_is_refused():
    """A NaN atom would fall in no cell of the grid and keep, with its
    neighbours, its whole area, with nothing said."""
    x = np.array([[math.nan, 0.0, 0.0], [0.0, 0.0, 0.0]])
    with pytest.raises(ValueError, match="1 of 2 atoms have a coordinate that is not a finite number"):
        sasa.atom_areas(x, np.array([0.17, 0.17]))


# --- the shortcuts, against the plain method on a real protein -----------------------------

@pytest.fixture(scope="module")
def t4l_atoms(tmp_path_factory):
    """Every atom of the T4 lysozyme fixture, and its periodic box."""
    gro = _gro(tmp_path_factory, "t4l_bnz_first6000")
    return _gro_atoms(gro), _gro_box(gro.read_text().splitlines()[-1])


@pytest.fixture(scope="module")
def t4l(t4l_atoms):
    """T4 lysozyme's protein from a real `caterva complex` em.gro: 2,603
    atoms with hydrogens, residues 1-162 (the benzene and water after them
    are not part of the surface)."""
    atoms = t4l_atoms[0]
    index = sasa.surface_atoms(atoms, range(1, 163))
    x = np.array([atoms[i][3] for i in index])
    radii = np.array([sasa.radius(atoms[i][2]) for i in index])
    resnr = np.array([atoms[i][0] for i in index])
    return x, radii, resnr, {atoms[i][0]: atoms[i][1] for i in index}


def test_the_fixture_is_the_protein_the_readme_describes(t4l):
    x, _, resnr, names = t4l
    assert len(x) == 2603 and set(resnr) == set(range(1, 163)) and names[1] == "MET"


def test_the_cell_grid_finds_exactly_the_overlapping_pairs(t4l):
    x, radii, _, _ = t4l
    reach = radii + sasa.PROBE_NM
    i, j = sasa.neighbour_pairs(x, reach)
    d = cdist(x, x)
    want_i, want_j = np.nonzero((d < reach[:, None] + reach[None, :]) & ~np.eye(len(x), dtype=bool))
    assert np.array_equal(i, want_i) and np.array_equal(j, want_j)
    assert len(i) > 100_000  # a real neighbour list, not a trivial one


@pytest.mark.parametrize("dots", [sasa.DOTS, 777])
def test_the_patches_decide_every_point_as_testing_it_alone_would(t4l, dots):
    x, radii, _, _ = t4l
    assert np.array_equal(sasa.atom_areas(x, radii, dots=dots), _brute(x, radii, dots))


def test_the_areas_converge_as_points_are_added(t4l):
    """Against 20,000 points: the root-mean-square error of an atom's area
    falls as the points are made denser (0.0029 nm^2 at 250, 0.0010 at
    1,000, 0.00037 at 4,000 when this was written), and at DOTS no atom of
    this structure is off by more than 0.005 nm^2 (0.0036) and no residue
    by more than 0.01 (0.0065). On eight lysozyme runs the largest residue
    error at DOTS was 0.0098 to 0.0157 (sasa.py, THE POINTS), so 0.01 is this
    structure's bound, not every structure's."""
    x, radii, resnr, _ = t4l
    ref = sasa.atom_areas(x, radii, dots=20000)
    rms = []
    for dots in (250, 1000, 4000):
        err = sasa.atom_areas(x, radii, dots=dots) - ref
        rms.append(float(np.sqrt((err * err).mean())))
    assert all(a > b for a, b in zip(rms, rms[1:])), rms
    at = sasa.atom_areas(x, radii) - ref
    assert np.abs(at).max() <= 0.005
    assert np.abs(np.bincount(resnr, weights=at)).max() <= 0.01


def _gmx_t4l(name: str, names) -> np.ndarray:
    """Per-residue areas gmx sasa printed for the T4 lysozyme fixture."""
    printed = [line.split() for line in (MD / name).read_text().splitlines()]
    assert [int(r) for r, _, _ in printed] == list(range(1, 163))
    assert all(names[int(r)] == n for r, n, _ in printed)
    return np.array([float(a) for _, _, a in printed])


def _within_routes_bound(mine: np.ndarray, gmx: np.ndarray) -> np.ndarray:
    """Each difference as a share of sasa.routes_agree_nm2 at the larger of
    the two areas: at most 1 where the routes agree as they are held to."""
    bound = np.array([sasa.routes_agree_nm2(a) for a in np.maximum(mine, gmx)])
    return np.abs(mine - gmx) / bound


def test_the_routes_bound_grows_with_the_area():
    assert sasa.routes_agree_nm2(0.0) == sasa.routes_agree_nm2(0.05) == sasa.ROUTES_AGREE_FLOOR_NM2
    assert sasa.routes_agree_nm2(1.0) == pytest.approx(sasa.ROUTES_AGREE_NM)
    assert sasa.routes_agree_nm2(1.7965) == pytest.approx(0.0402, abs=5e-5)  # sasa.py's largest measured case


def test_every_residue_of_t4_lysozyme_matches_gmx_sasa(t4l):
    """`gmx sasa -ndots 10000` on the same atoms: every residue within the
    routes' bound at DOTS points (0.0088 nm^2 at most when this was
    written, 0.0024 root mean square), and closer as Caterva's points are
    made denser (0.0044 at 10,000), because the two converge on the same
    surface."""
    x, radii, resnr, names = t4l
    gmx = _gmx_t4l("t4l_bnz_first6000_gmx_sasa.txt", names)
    mine = np.bincount(resnr, weights=sasa.atom_areas(x, radii))[1:]
    assert _within_routes_bound(mine, gmx).max() <= 1.0
    assert float(np.sqrt(((mine - gmx) ** 2).mean())) <= 0.004
    dense = np.bincount(resnr, weights=sasa.atom_areas(x, radii, dots=10000))[1:]
    assert np.abs(dense - gmx).max() <= 0.006 and float(np.sqrt(((dense - gmx) ** 2).mean())) <= 0.002


def test_every_residue_of_t4_lysozyme_matches_gmx_sasa_at_the_same_points(t4l):
    """`gmx sasa -ndots 2000` against DOTS points, as the two routes run:
    each residue within sasa.routes_agree_nm2 of its area. When this was
    written the largest difference was 0.0138 nm^2 (Ala93, 0.87 nm^2), 0.49
    of its bound, and the root mean square 0.0033."""
    assert sasa.DOTS == 2000  # the fixture is gmx sasa at -ndots 2000
    x, radii, resnr, names = t4l
    gmx = _gmx_t4l("t4l_bnz_first6000_gmx_sasa_ndots2000.txt", names)
    mine = np.bincount(resnr, weights=sasa.atom_areas(x, radii))[1:]
    share = _within_routes_bound(mine, gmx)
    assert share.max() <= 1.0
    assert share.max() > 0.3  # two point sets: the bound is approached, not idle
    assert float(np.sqrt(((mine - gmx) ** 2).mean())) <= 0.005


# --- the catalytic residues of lysozyme, frame by frame -----------------------------------

def _gmx_lysozyme():
    """resnr (or "total") -> (area in the .gro, the 21 per-frame areas)."""
    out = {}
    for line in (MD / "lyso_1aki_rep1_gmx_sasa.txt").read_text().splitlines():
        parts = line.split()
        key = parts[0] if parts[0] == "total" else int(parts[0])
        out[key] = (float(parts[2]), [float(v) for v in parts[3:]])
    return out


@pytest.fixture(scope="module")
def lysozyme(tmp_path_factory):
    gro = _gro(tmp_path_factory, "lyso_1aki_res1-59")
    return gro, xtc.read(MD / "lyso_1aki_res1-59.xtc")


def test_catalytic_areas_match_gmx_sasa_in_every_frame(lysozyme):
    """The command analyze.sh runs, on 21 real frames: every catalytic
    residue in every frame, and at the start, within sasa.routes_agree_nm2
    of its area (at most 0.0096 nm^2 apart when this was written)."""
    gro, traj = lysozyme
    atoms = _gro_atoms(gro)
    order = sorted(CATALYTIC)
    surface = sasa.Surface(atoms, order)
    assert len(surface.index) == 900
    reference = _gmx_lysozyme()
    per_frame = surface.series(traj)
    start = surface.areas(np.array([a[3] for a in atoms]), _gro_box(gro.read_text().splitlines()[-1]))
    worst, share = 0.0, 0.0
    for k, resnr in enumerate(order):
        at_start, frames = reference[resnr]
        assert len(frames) == len(per_frame[k]) == 21
        for a, b in [(start[k], at_start), *zip(per_frame[k], frames)]:
            worst = max(worst, abs(a - b))
            share = max(share, abs(a - b) / sasa.routes_agree_nm2(max(a, b)))
    assert share <= 1.0
    assert worst > 0.001  # two point sets: close, not identical


def test_the_area_survives_the_periodic_boundary(tmp_path_factory):
    """The same frames with the active site across the periodic box
    (fixtures/md/README.md): the protein is made whole first, so every area
    equals the unwrapped one to within the 0.001 nm re-rounding of putting
    atoms back in the box (0.0027 nm^2 at most over all 21 frames when this
    was written). Taken as stored, not one residue-frame would be right.
    Every third frame, to keep the test quick; the fixture is split across
    the box in all of them."""
    series = {}
    for name in ("lyso_1aki_res1-59_water", "lyso_1aki_res1-59_water_wrapped"):
        atoms = _gro_atoms(_gro(tmp_path_factory, name))
        surface = sasa.Surface(atoms, CATALYTIC)
        traj = xtc.read(MD / f"{name}.xtc")[::3]
        series[name] = np.array(surface.series(traj))
    unwrapped, wrapped = series["lyso_1aki_res1-59_water"], series["lyso_1aki_res1-59_water_wrapped"]
    assert not any(np.allclose(xtc.make_whole(f.x[surface.index], f.box), f.x[surface.index]) for f in traj)
    raw = np.array([[a[m].sum() for m in surface.members]
                    for a in (sasa.atom_areas(f.x[surface.index], surface.radii) for f in traj)]).T
    assert len(traj) == 7 and np.abs(wrapped - unwrapped).max() <= 0.005
    assert int((np.abs(raw - unwrapped) > 0.05).sum()) == raw.size == 42


# --- which atoms, and which residue ---------------------------------------------------------

def test_the_surface_is_the_protein_without_water_ions_or_ligand():
    x = np.zeros(3)
    atoms = [(1, "MET", "N", x), (1, "MET", "CA", x), (2, "GLU", "OE1", x), (163, "BNZ", "C1", x),
             (164, "SOL", "OW", x), (165, "NA", "NA", x), (166, "CL", "CL", x)]
    assert sasa.surface_atoms(atoms) == [0, 1, 2, 3]
    assert sasa.surface_atoms(atoms, protein={1, 2}) == [0, 1, 2]


def test_a_residue_numbered_in_two_chains_or_absent_is_refused():
    x = np.zeros(3)
    atoms = [(35, "GLU", "N", x), (35, "GLU", "CA", x), (36, "SER", "N", x), (35, "GLU", "N", x)]
    surface = sasa.surface_atoms(atoms)
    assert list(sasa.residue_members(atoms, surface, 36)) == [2]
    with pytest.raises(ValueError, match="more than one place"):
        sasa.residue_members(atoms, surface, 35)
    with pytest.raises(ValueError, match="no atoms"):
        sasa.residue_members(atoms, surface, 99)


def test_two_residues_under_one_number_are_refused():
    """52 and 52A of a PDB file are both 52 in a .gro file, side by side, so
    the number does not appear in two places; their atom names repeat."""
    x = np.zeros(3)
    atoms = [(51, "ALA", "C", x), (52, "GLY", "N", x), (52, "GLY", "CA", x), (52, "GLY", "C", x),
             (52, "SER", "N", x), (52, "SER", "CA", x), (52, "SER", "OG", x), (52, "SER", "C", x)]
    with pytest.raises(ValueError, match="residue number 52 has two atoms named C, CA, N"):
        sasa.residue_members(atoms, sasa.surface_atoms(atoms), 52)


def _backbone(gap_after=None, without=()):
    """Five residues' N, CA and C on a line (nm), each C 0.133 nm from the
    next N, a peptide bond, except after residue `gap_after`, where the rest
    of the chain is moved 0.5 nm on."""
    atoms = []
    for k in range(1, 6):
        at = 0.4 * k + (0.5 if gap_after is not None and k > gap_after else 0.0)
        for name, dx in (("N", 0.0), ("CA", 0.15), ("C", 0.267)):
            if (k, name) not in without:
                atoms.append((k, "ALA", name, np.array([at + dx, 0.0, 0.0])))
    return atoms


def test_a_residue_is_inside_the_chain_when_bonded_on_both_sides():
    whole = _backbone()
    assert sasa.Surface(whole, [1, 2, 3, 4, 5]).in_chain == [False, True, True, True, False]
    broken = _backbone(gap_after=3)
    assert sasa.Surface(broken, [2, 3, 4]).in_chain == [True, False, False]
    # Residue 3 without its C has no bond to 4, so neither 3 nor 4 counts.
    assert sasa.Surface(_backbone(without=[(3, "C")]), [2, 3, 4]).in_chain == [True, False, False]
    # Across the periodic box the bond is measured to the nearest image.
    box = np.diag([2.0, 2.0, 2.0])
    moved = [(r, n, name, xyz + (np.array([2.0, 0.0, 0.0]) if r >= 3 else 0.0)) for r, n, name, xyz in whole]
    assert sasa.Surface(moved, [2, 3], box=box).in_chain == [True, True]
    assert sasa.Surface(moved, [2, 3]).in_chain == [False, False]


def test_on_a_real_protein_only_the_first_and_last_residues_are_chain_ends(t4l_atoms):
    atoms, box = t4l_atoms
    surface = sasa.Surface(atoms, list(range(1, 163)), protein=range(1, 163), box=box)
    assert [r for r, inside in zip(range(1, 163), surface.in_chain) if not inside] == [1, 162]


# --- what is reported -----------------------------------------------------------------------

def test_mean_sd_and_middle_95_percent_of_frames():
    name, mean, sd, low, high = sasa.summarise_areas("rep1", [0.1, 0.2, 0.3, 0.4, 0.5])
    assert name == "rep1" and mean == pytest.approx(0.3) and sd == pytest.approx(math.sqrt(0.025))
    # Linear interpolation between frames: 2.5% of the way along 4 gaps.
    assert low == pytest.approx(0.11) and high == pytest.approx(0.49)
    _, mean, sd, low, high = sasa.summarise_areas("rep1", [0.7])
    assert mean == low == high == 0.7 and math.isnan(sd)  # one frame has no spread
    assert all(math.isnan(v) for v in sasa.summarise_areas("rep1", [])[1:])


def _e(start, *means, resname="SER", in_chain=True):
    """An Exposure of a serine (largest possible area 1.55 nm^2)."""
    return sasa.Exposure("Ser50", resname, start, [(f"rep{i + 1}", m, 0.01, m, m) for i, m in enumerate(means)],
                         in_chain)


@pytest.mark.parametrize("e,verdict", [
    (_e(0.10, 0.12, 0.08), "buried throughout"),
    (_e(0.40, 0.45, 0.50), "partly exposed throughout"),
    (_e(0.90, 0.80, 0.70), "exposed throughout"),
    (_e(0.10, 0.80, 0.90), "buried at the start, exposed in every replica"),
    (_e(0.90, 0.10, 0.12), "exposed at the start, buried in every replica"),
    (_e(0.10, 0.12, 0.80), "buried at the start, exposed in rep2; replicas disagree"),
    (_e(0.10, 0.50, 0.80, 0.10), "buried at the start, partly exposed in rep1, exposed in rep2; replicas disagree"),
    (_e(0.10, 0.12, 0.13, resname="MSE"), sasa.no_maximum("MSE")),
    (_e(0.10, 0.12, 0.13, in_chain=False), sasa.CHAIN_END),
    (_e(0.10, 0.12, float("nan")), sasa.NO_FRAMES),
    (_e(0.10, 0.12), sasa.ONE_REPLICA),
])
def test_verdicts(e, verdict):
    assert sasa.exposure_verdict(e) == verdict


def _r(name, mean, low, high):
    return (name, mean, 0.03, low, high)


def test_a_mean_across_a_threshold_with_frames_still_in_the_starting_state_has_not_clearly_left_it():
    """The case of lysozyme's Asn46 (largest possible area 1.95 nm^2) in one
    md_smoke run: partly exposed at the start (23%), rep1 at 22% and rep2's
    mean at 19% with its middle 95% of frames from 17% to 23%. Rep2's mean
    is under the 20% line, its frames are on both sides of it, and the same
    protocol run again put it at 20%: that is not "replicas disagree"."""
    asn46 = sasa.Exposure("Asn46", "ASN", 0.46, [_r("rep1", 0.43, 0.41, 0.44), _r("rep2", 0.37, 0.34, 0.44)])
    assert sasa.exposure_verdict(asn46) == ("partly exposed at the start, buried in rep2 by its mean, with "
                                            "frames still partly exposed")
    # The same mean with every frame under the line has left the state.
    left = sasa.Exposure("Asn46", "ASN", 0.46, [_r("rep1", 0.43, 0.41, 0.44), _r("rep2", 0.30, 0.25, 0.36)])
    assert sasa.exposure_verdict(left) == "partly exposed at the start, buried in rep2; replicas disagree"
    # Both replicas near the line, on the same side: still not "in every replica".
    both = sasa.Exposure("Asn46", "ASN", 0.46, [_r("rep1", 0.37, 0.33, 0.42), _r("rep2", 0.37, 0.34, 0.44)])
    assert sasa.exposure_verdict(both) == ("partly exposed at the start, buried in rep1 by its mean, with frames "
                                           "still partly exposed, buried in rep2 by its mean, with frames still "
                                           "partly exposed")
    # One replica clearly left, the other near the line: no disagreement claimed.
    mixed = sasa.Exposure("Asn46", "ASN", 0.46, [_r("rep1", 0.20, 0.15, 0.25), _r("rep2", 0.37, 0.34, 0.44)])
    assert sasa.exposure_verdict(mixed) == ("partly exposed at the start, buried in rep1, buried in rep2 by its "
                                            "mean, with frames still partly exposed")
    # Frames that span the start's state from buried to exposed reach back too.
    wide = sasa.Exposure("Asn46", "ASN", 0.46, [_r("rep1", 0.43, 0.41, 0.44), _r("rep2", 0.80, 0.30, 1.00)])
    assert sasa.exposure_verdict(wide).endswith("exposed in rep2 by its mean, with frames still partly exposed")


def test_the_verdict_reads_the_share_as_printed():
    """0.3099 nm^2 of a serine's 1.55 is 19.99%, printed as 20%: partly
    exposed, as the printed number says, not buried by a hundredth of a
    per cent."""
    e = _e(0.3099, 0.3099, 0.3099)
    assert f"{e.relative(0.3099):.0%}" == "20%"
    assert sasa.exposure_verdict(e) == "partly exposed throughout"


def _two_sites():
    """His10 and Ser30 with their functional atoms, and Ala1 and Ala90 at
    the chain's ends (Angstrom)."""
    rows = [(1, "CA", "ALA"), (10, "ND1", "HIS"), (10, "NE2", "HIS"), (30, "OG", "SER"), (90, "CA", "ALA")]
    atoms = [Atom("A", r, n, name, (float(r), 0.0, 0.0)) for r, name, n in rows]
    return plan(atoms, [(10, "HIS"), (30, "SER")])


def test_the_section_prints_areas_shares_ranges_and_verdicts():
    p = _two_sites()
    nan = float("nan")
    rows = _exposures(p, [0.10, 0.50], {0: [("rep1", 0.80, 0.05, 0.70, 0.90), ("rep2", 0.85, 0.04, 0.78, 0.92)],
                                        1: [("rep1", 0.20, nan, 0.20, 0.20), ("rep2", nan, nan, nan, nan)]})
    section = sasa_section(Analysis("9XYZ", "A", "test", p, [], None, None, None, [], None, None, rows))
    assert section[1] == "## Solvent exposure of the catalytic residues"
    assert "| residue | largest possible (nm²) | at start | rep1 | rep2 | verdict |" in section
    # No distance, so nothing is converged: the exposure verdict waits.
    assert ("| His10 | 2.24 | 0.10 (4%) | 0.80 ± 0.05 [0.70, 0.90] (36%) | 0.85 ± 0.04 [0.78, 0.92] (38%) | "
            "(buried at the start, partly exposed in every replica, not yet a result) |") in section
    assert f"| Ser30 | 1.55 | 0.50 (32%) | 0.20 ± n/a [0.20, 0.20] (13%) | n/a | {sasa.NO_FRAMES} |" in section
    text = "\n".join(section)
    assert "below 20% of the largest possible area" in text and "at 40% or above" in text
    assert "Tien et al. (2013) PLoS ONE 8:e80635" in text
    assert "Shrake & Rupley's method, 2,000 points per atom" in text and "lattice" not in text


def test_the_gromacs_route_names_its_own_points():
    """gmx sasa places its points on Eisenhaber et al.'s double cubic
    lattice, and -ndots 2000 gives 2,252 of them per atom (sasa.GMX_DOTS):
    the section measured that way says so, not the native route's method."""
    p = _two_sites()
    rows = _exposures(p, [0.10, 0.50], {0: [("rep1", 0.8, 0.05, 0.7, 0.9)], 1: [("rep1", 0.2, 0.01, 0.2, 0.2)]})
    text = "\n".join(sasa_section(Analysis("9XYZ", "A", "t", p, [], None, None, None, [], None, None, rows,
                                           sasa_route="gromacs")))
    assert "double cubic lattice of Eisenhaber et al. (1995)" in text
    assert f"-ndots {sasa.DOTS}, which it rounds up to 2,252 per atom" in text
    assert "Shrake & Rupley's method" not in text


def test_a_chain_end_has_no_share_and_no_verdict():
    p = _two_sites()
    rows = [sasa.Exposure("Ala1", "ALA", 0.9, [("rep1", 0.9, 0.1, 0.8, 1.0), ("rep2", 0.9, 0.1, 0.8, 1.0)],
                          in_chain=False)]
    section = sasa_section(Analysis("9XYZ", "A", "test", p, [], None, None, None, [], None, None, rows))
    assert f"| Ala1 | n/a | 0.90 | 0.90 ± 0.10 [0.80, 1.00] | 0.90 ± 0.10 [0.80, 1.00] | {sasa.CHAIN_END} |" in section


def test_without_em_gro_the_chain_ends_are_the_first_and_last_residues_of_protein_pdb():
    """Both routes take the chain's ends from em.gro's peptide bonds
    (sasa.Surface.in_chain); a directory analyze.sh has not run in, which
    has no em.gro, falls back to protein.pdb's numbering."""
    p = _two_sites()
    assert [e.in_chain for e in _exposures(p, [0.1, 0.1], {0: [], 1: []})] == [True, True]
    ends = plan([Atom("A", r, n, "CA", (float(r), 0.0, 0.0)) for r, n in ((1, "GLY"), (5, "ALA"), (9, "GLY"))],
                [(1, "GLY"), (5, "ALA"), (9, "GLY")])
    assert [e.in_chain for e in _exposures(ends, [0.1] * 3, {0: [], 1: [], 2: []})] == [False, True, False]


def test_not_measured_and_nothing_to_measure_are_said():
    p = _two_sites()
    assert sasa_section(Analysis("9XYZ", "A", "t", p, [], None, None, None, [], None, None, None))[-1] == \
        "Not measured."
    why = sasa_section(Analysis("9XYZ", "A", "t", p, [], None, None, None, [], None, None, None,
                                sasa_not_measured="residue number 10 appears in more than one place"))
    assert why[-1] == "Not measured: residue number 10 appears in more than one place."
    assert sasa_section(Analysis("9XYZ", "A", "t", p, [], None, None, None, [], None, None, []))[-1] == \
        "No catalytic residue to measure."


# --- the GROMACS route ------------------------------------------------------------------------

def test_one_sasa_call_per_replica_and_one_for_the_start():
    p = _two_sites()
    lines = [l for l in commands(p, ["rep1", "rep2"]) if " sasa " in l]
    assert len(lines) == 3
    options = f"-surface Protein -probe 0.14 -ndots {sasa.DOTS} -nopbc"
    outputs = "-output 'group Protein and resnr 10' 'group Protein and resnr 30'"
    assert lines[0] == f"$GMX sasa -s rep1/md.tpr -f rep1/md.xtc {options} {outputs} -o rep1/sasa.xvg " \
                       "-or rep1/sasa_residues.xvg"
    assert lines[1].startswith("$GMX sasa -s rep2/md.tpr -f rep2/md.xtc ") and "-o rep2/sasa.xvg" in lines[1]
    assert lines[2] == f"$GMX sasa -s rep1/md.tpr -f em.gro {options} {outputs} -o sasa_start.xvg"


def test_a_missing_or_stale_sasa_output_is_refused(tmp_path):
    p = _two_sites()
    rep = tmp_path / "rep1"
    rep.mkdir()
    (rep / "sasa.xvg").write_text("0.0 9.0 0.1 0.2\n")
    with pytest.raises(AnalyzeError, match="sasa_start.xvg does not exist"):
        gromacs_sasa(tmp_path, p, [rep])
    (tmp_path / "sasa_start.xvg").write_text("0.0 9.0 0.1\n")  # an older plan: one residue
    with pytest.raises(AnalyzeError, match=r"has 2 columns of solvent-accessible area \(one column for the "
                                           r"whole protein, then one per catalytic residue\), the plan has 3"):
        gromacs_sasa(tmp_path, p, [rep])
    # A run of gmx that stopped before its first frame leaves the headers.
    (tmp_path / "sasa_start.xvg").write_text("@ title \"Solvent Accessible Surface\"\n")
    with pytest.raises(AnalyzeError, match=r"sasa_start.xvg has no frames of solvent-accessible area"):
        gromacs_sasa(tmp_path, p, [rep])


def test_a_nan_area_from_gmx_is_refused_not_read_as_no_frames(tmp_path):
    """One damaged cell would otherwise print the replica as n/a with the
    verdict "no frames", over frames that are valid."""
    p = _two_sites()
    rep = tmp_path / "rep1"
    rep.mkdir()
    (tmp_path / "sasa_start.xvg").write_text("0.0 9.0 0.1 0.2\n")
    (rep / "sasa.xvg").write_text("0.0 9.0 0.1 0.2\n1.0 9.0 nan 0.2\n2.0 9.0 0.1 0.2\n")
    with pytest.raises(AnalyzeError, match=r"rep1/sasa.xvg has an area that is not a number"):
        gromacs_sasa(tmp_path, p, [rep])


def _two_chain_em_gro(directory: Path):
    """An em.gro in which His10 is numbered twice, as when two chains are
    simulated with the same numbering (`caterva md`'s default is every
    chain), with Asp20, Gly30 and Leu90 once."""
    rows = [(10, "HIS", "CA"), (10, "HIS", "ND1"), (10, "HIS", "NE2"), (20, "ASP", "CA"), (20, "ASP", "OD1"),
            (20, "ASP", "OD2"), (30, "GLY", "CA"), (90, "LEU", "CA"), (10, "HIS", "CA"), (10, "HIS", "ND1"),
            (10, "HIS", "NE2")]
    lines = ["two chains", str(len(rows))]
    for k, (r, n, name) in enumerate(rows, start=1):
        lines.append(f"{r:5d}{n:<5s}{name:>5s}{k:5d}{0.5 * k:8.3f}{1.0:8.3f}{1.0:8.3f}")
    lines.append("  10.00000  10.00000  10.00000")
    (directory / "em.gro").write_text("\n".join(lines) + "\n")


def test_a_residue_numbered_in_two_chains_drops_only_this_section(tmp_path, capsys):
    """The distances and the rest are still reported, as they were before
    this section existed; the section says why it has no areas, and the
    exit code is the distances' and angles' as before."""
    from caterva.tests import test_analyze
    d = test_analyze._fake_run(tmp_path, [0.40, 0.40, 0.40])
    _two_chain_em_gro(d)
    p = plan(test_analyze.read_pdb(test_analyze._protein(), "A"), [(10, "HIS"), (20, "ASP")])
    assert "residue number 10 appears in more than one place" in sasa_unmeasurable(d, p)
    assert main([str(d), "--no-run"], catalytic=test_analyze._catalytic) == 0
    out = capsys.readouterr().out
    assert "| His10–Asp20 | 0.400 |" in out
    assert ("## Solvent exposure of the catalytic residues\n\nNot measured: residue number 10 appears in more "
            "than one place in the protein (more than one chain simulated?)") in out


def _smoke():
    spec = importlib.util.spec_from_file_location("md_smoke", REPO / "scripts" / "md_smoke.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _split_xtc(path: Path, at: int):
    """The bytes of an .xtc before frame `at` and from it on. Each frame is
    a record of its own (a 52-byte header, then its coordinates), so a
    trajectory cut between two frames is two trajectories."""
    data = path.read_bytes()
    pos = 0
    for _ in range(at):
        natoms = struct.unpack_from(">3i", data, pos)[1]
        pos = xtc._coords(data, pos + 52, natoms)[2]
    return data[:pos], data[pos:]


def test_both_routes_give_the_same_section_on_real_frames(tmp_path, lysozyme):
    """The native route measured on the committed lysozyme frames, against
    the GROMACS route reading what gmx sasa printed for them; judged by the
    helper the CI smoke run uses, and with the same verdicts. The 21 frames
    are cut into two replicas (0-10 and 11-20), so each residue gets a
    verdict from its areas: with one replica every verdict would be "one
    replica" whatever the areas were."""
    gro, _ = lysozyme
    (tmp_path / "em.gro").write_bytes(gro.read_bytes())
    atoms = _gro_atoms(tmp_path / "em.gro")
    protein = [Atom("A", r, n, name, tuple(float(v) * 10 for v in xyz)) for r, n, name, xyz in atoms]
    reps = [tmp_path / "rep1", tmp_path / "rep2"]
    for rep, part in zip(reps, _split_xtc(MD / "lyso_1aki_res1-59.xtc", 11)):
        rep.mkdir()
        (rep / "md.xtc").write_bytes(part)
    assert [len(xtc.read(r / "md.xtc")) for r in reps] == [11, 10]
    p = plan(protein, [(r, next(a.resname for a in protein if a.resnr == r)) for r in CATALYTIC])
    native = measure_native(tmp_path, p, reps)[7]
    assert measure_native(tmp_path, p, reps, sasa=False)[7] is None  # sasa_unmeasurable gave a reason

    reference = _gmx_lysozyme()
    columns = ["total"] + [s.resnr for s in p.sites]
    (tmp_path / "sasa_start.xvg").write_text("0.0 " + " ".join(f"{reference[c][0]:.3f}" for c in columns) + "\n")
    for rep, frames in zip(reps, (range(0, 11), range(11, 21))):
        (rep / "sasa.xvg").write_text("".join(
            f"{t * 0.5:.1f} " + " ".join(f"{reference[c][1][t]:.3f}" for c in columns) + "\n" for t in frames))
    via_gmx = gromacs_sasa(tmp_path, p, reps)
    assert [e.label for e in via_gmx] == [e.label for e in native] == [s.label for s in p.sites]

    one = "\n".join(sasa_section(Analysis("1AKI", None, "t", p, [], None, None, None, [], None, None, native)))
    other = "\n".join(sasa_section(Analysis("1AKI", None, "t", p, [], None, None, None, [], None, None, via_gmx)))
    smoke = _smoke()
    rows_native, rows_gmx = smoke._sasa_rows(one), smoke._sasa_rows(other)
    assert len(rows_native) == 6 and all(len(v) == 7 for v in rows_native.values())
    agree, worst, allowed = smoke._sasa_agree(rows_native, rows_gmx)
    assert agree and worst <= allowed
    # Asn59 is the last residue of this 59-residue fragment: no peptide bond
    # after it in em.gro, so it is a chain end on both routes.
    assert "| Asn59 | n/a |" in one and "| Asn59 | n/a |" in other and sasa.CHAIN_END in one
    verdicts = [sasa.exposure_verdict(e) for e in native]
    assert verdicts == [sasa.exposure_verdict(e) for e in via_gmx]
    assert smoke._verdicts_differ(smoke._sasa_verdicts(one), smoke._sasa_verdicts(other),
                                  rows_native, rows_gmx) == ([], [])
    # What the areas say on this fragment (Asp48, Ser50, Asn46, Asn59, Asp52,
    # Glu35); Ser50 sits at 21-22% of its maximum, near the 20% threshold.
    assert verdicts == ["exposed throughout", "partly exposed throughout", "partly exposed throughout",
                        sasa.CHAIN_END, "buried throughout", "exposed throughout"]


def test_the_smoke_comparison_holds_areas_to_the_measured_tolerance():
    """The allowance is the routes' bound for the larger area the printed
    value could stand for, plus 0.01 for the rounding of two printed
    values: 0.0175 near zero, about 0.027 at 0.3 nm^2 and 0.050 at 1.8."""
    smoke = _smoke()
    assert smoke.sasa_allowed(0.00, 0.00) == pytest.approx(sasa.ROUTES_AGREE_FLOOR_NM2 + 0.01)
    assert smoke.sasa_allowed(0.30, 0.31) == pytest.approx(sasa.ROUTES_AGREE_NM * math.sqrt(0.315) + 0.01)
    assert smoke.sasa_allowed(1.80, 1.78) > smoke.sasa_allowed(0.30, 0.31)
    base = {"Glu35": (0.34, 0.29, 0.24, 0.31), "Ser50": (0.00, 0.01, 0.00, 0.02)}
    near = {"Glu35": (0.33, 0.30, 0.25, 0.33), "Ser50": (0.00, 0.01, 0.00, 0.02)}
    agree, worst, allowed = smoke._sasa_agree(base, near)
    assert agree and worst == pytest.approx(0.02) and allowed == pytest.approx(smoke.sasa_allowed(0.31, 0.33))
    # 0.03 apart at 0.34 nm^2 is beyond the 0.028 allowed there; 0.02 apart
    # near zero is beyond the 0.0175 allowed there.
    assert smoke._sasa_agree(base, {**base, "Glu35": (0.34, 0.29, 0.24, 0.34)})[0] is False
    assert smoke._sasa_agree(base, {**base, "Ser50": (0.00, 0.01, 0.00, 0.04)})[0] is False
    # A difference that would pass at 1.8 nm^2 does not at 0.3.
    assert smoke._sasa_agree({"Arg45": (1.80,)}, {"Arg45": (1.77,)})[0] is True
    assert smoke._sasa_agree({"Asn46": (0.30,)}, {"Asn46": (0.27,)})[0] is False
    assert smoke._sasa_agree(base, {"Glu35": base["Glu35"]})[0] is False     # a residue missing
    assert smoke._sasa_agree(base, {**base, "Ser50": (0.00,)})[0] is False    # a row cut short (n/a)
    assert smoke._sasa_agree({}, {})[0] is False                               # nothing measured


def test_the_smoke_run_tells_a_verdict_near_a_threshold_from_one_that_should_not_differ():
    """md_smoke compares the verdict columns too. A share near 20% can round
    into a different state on each route, which the area tolerance allows;
    a different verdict with every area in the same state on both routes is
    a failure."""
    smoke = _smoke()
    native = {"Asn46": (1.95, "partly exposed throughout"), "Glu35": (2.23, "buried throughout")}
    # Asn46's rep2 mean 0.40 (21%) on one route and 0.38 (19%) on the other.
    gromacs = {"Asn46": (1.95, "partly exposed at the start, buried in rep2; replicas disagree"),
               "Glu35": (2.23, "buried throughout")}
    rows_n = {"Asn46": (0.46, 0.43, 0.41, 0.44, 0.40, 0.39, 0.42), "Glu35": (0.34, 0.29, 0.25, 0.32)}
    rows_g = {"Asn46": (0.46, 0.43, 0.41, 0.44, 0.38, 0.37, 0.41), "Glu35": (0.33, 0.29, 0.25, 0.32)}
    assert smoke._verdicts_differ(native, gromacs, rows_n, rows_g) == (["Asn46"], [])
    # The same areas on both routes, and different verdicts: not explained.
    assert smoke._verdicts_differ(native, gromacs, rows_n, rows_n) == ([], ["Asn46"])
    # A residue without a maximum (chain end) has no share to be near a threshold with.
    assert smoke._verdicts_differ({"Asn59": (None, "x")}, {"Asn59": (None, "y")}, rows_n, rows_g) == \
        ([], ["Asn59"])
    text = ("## Solvent exposure of the catalytic residues\n\n| residue | largest possible (nm²) | at start | rep1 "
            "| verdict |\n|---|---|---|---|---|\n| Asn59 | n/a | 0.24 | 0.21 ± 0.02 [0.18, 0.23] | one replica |\n"
            "| Glu35 | 2.23 | 0.34 (15%) | 0.29 ± 0.03 [0.25, 0.32] (13%) | one replica |\n")
    assert smoke._sasa_verdicts(text) == {"Asn59": (None, "one replica"), "Glu35": (2.23, "one replica")}
