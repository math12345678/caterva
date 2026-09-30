"""Angles between catalytic groups (caterva/analyze/angles.py, plan.contact_angles).

The anchor is real: `gmx gangle -g1 angle -group1 'cog of (A) plus cog of
(V) plus cog of (B)'` (GROMACS 2026.1) on the 24 angles lysozyme's six
catalytic groups make under the contact cutoff, all 21 frames of a `caterva
md` replica (fixtures/md/lyso_1aki_rep1_gmx_angles.txt, made on
lyso_1aki_res1-59.xtc with lyso_1aki_res1-59.gro.gz as the structure). No
group straddles the periodic box in those frames, so the same comparison
is made again on them translated so that the active site does
(lyso_1aki_rep1_gmx_angles_wrapped.txt, gangle with the run's md.tpr); that
is what checks make_whole and the nearest-image arms on real frames. The
rest is constructed geometry whose answer can be worked by hand.
"""
from __future__ import annotations

import gzip
import json
import math
import random
from pathlib import Path

import numpy as np
import pytest

from caterva.analyze.__main__ import (EXIT_NOT_A_RESULT, MOVED_NM, AnalyzeError, _gro_index, commands,
                                      gromacs_angles, main)
from caterva.analyze.angles import MOVED_DEG, RESOLVE_DEG, AngleResult, angle_deg, angle_series
from caterva.analyze.plan import CONTACT_NM, plan, read_pdb
from caterva.md import xtc
from caterva.md.convergence import summarise

MD = Path(__file__).parent / "fixtures" / "md"
#: The six M-CSA catalytic residues of hen lysozyme and their functional atoms.
LYSOZYME = {35: ("OE1", "OE2"), 46: ("OD1", "ND2"), 48: ("OD1", "OD2"), 50: ("OG",),
            52: ("OD1", "OD2"), 59: ("OD1", "ND2")}


def gmx_angles():
    """(a, v, b) -> the 21 per-frame angles gmx gangle printed."""
    out = {}
    for line in (MD / "lyso_1aki_rep1_gmx_angles.txt").read_text().splitlines():
        parts = line.split()
        out[tuple(int(v) for v in parts[:3])] = [float(v) for v in parts[3:]]
    return out


@pytest.fixture(scope="module")
def lysozyme(tmp_path_factory):
    gro = tmp_path_factory.mktemp("lyso") / "res1-59.gro"
    gro.write_bytes(gzip.decompress((MD / "lyso_1aki_res1-59.gro.gz").read_bytes()))
    return _gro_index(gro), xtc.read(MD / "lyso_1aki_res1-59.xtc")


def test_every_angle_equals_gmx_gangle_on_every_frame(lysozyme):
    index, traj = lysozyme
    reference = gmx_angles()
    assert len(reference) == 24 and all(len(v) == 21 for v in reference.values())
    for (a, v, b), expected in reference.items():
        groups = [[index[(r, n)] for n in LYSOZYME[r]] for r in (a, v, b)]
        got = angle_series(traj, *groups)
        worst = max(abs(g - e) for g, e in zip(got, expected))
        # gmx prints three decimals; 0.001 is one unit of the last digit.
        assert worst < 0.001, f"{a}-{v}-{b}: {worst:.4f} degrees from gmx gangle"


def _wrapped():
    """The water fixture's atoms and frames translated so that the active
    site straddles the periodic box (fixtures/md/README.md), its structure,
    and what gmx gangle printed for it with the full system's md.tpr."""
    import tempfile
    gro = Path(tempfile.mkdtemp()) / "wrapped.gro"
    gro.write_bytes(gzip.decompress((MD / "lyso_1aki_res1-59_water_wrapped.gro.gz").read_bytes()))
    reference = {}
    for line in (MD / "lyso_1aki_rep1_gmx_angles_wrapped.txt").read_text().splitlines():
        parts = line.split()
        reference[tuple(int(v) for v in parts[:3])] = [float(v) for v in parts[3:]]
    return _gro_index(gro), xtc.read(MD / "lyso_1aki_res1-59_water_wrapped.xtc"), reference


@pytest.fixture(scope="module")
def wrapped():
    return _wrapped()


def test_every_angle_equals_gmx_gangle_across_the_periodic_boundary(wrapped):
    """The fixture above never crosses the box, so it would pass with the
    periodic handling broken. Here four of the five groups in angles are
    split across it and most arms cross it, and every angle still equals
    gmx gangle's; the same angles taken without periodic handling are far
    off, which is what makes this a test of that handling."""
    index, traj, reference = wrapped
    assert len(reference) == 24 and all(len(v) == 21 for v in reference.values())
    g = {r: [index[(r, n)] for n in LYSOZYME[r]] for r in LYSOZYME}
    # Asn46 and Asp48 have their two atoms on opposite sides of the cell in every frame.
    for r in (46, 48):
        assert all(np.ptp(f.x[g[r]], 0).max() > f.box[2, 2] / 2 for f in traj)
    off = 0
    for (a, v, b), expected in reference.items():
        got = angle_series(traj, g[a], g[v], g[b])
        worst = max(abs(x - e) for x, e in zip(got, expected))
        assert worst < 0.001, f"{a}-{v}-{b}: {worst:.4f} degrees from gmx gangle"
        off += sum(1 for f, e in zip(traj, expected)
                   if abs(angle_deg(*(f.x[g[r]].mean(0) for r in (a, v, b))) - e) > 1.0)
    # 494 of the 504 angle-frames, when this fixture was made.
    assert off > 400


def test_an_angle_is_fixed_by_the_three_distances_the_report_already_has(wrapped):
    """Why an angle adds no information about where the groups are: the
    report measures every pair of catalytic groups, so the three sides of
    each angle's triangle are in its distance table, and the angle follows
    from them by the law of cosines, frame by frame, through the periodic
    box as well (caterva/analyze/angles.py says what the angle is for)."""
    from caterva.analyze.__main__ import distance_series
    index, traj, reference = wrapped
    g = {r: [index[(r, n)] for n in LYSOZYME[r]] for r in LYSOZYME}
    for a, v, b in reference:
        va, vb = distance_series(traj, g[v], g[a]), distance_series(traj, g[v], g[b])
        ab = distance_series(traj, g[a], g[b])
        from_distances = [math.degrees(math.acos((x * x + y * y - z * z) / (2 * x * y)))
                          for x, y, z in zip(va, vb, ab)]
        assert angle_series(traj, g[a], g[v], g[b]) == pytest.approx(from_distances, abs=1e-9)


def test_an_angle_cannot_tell_which_side_of_the_vertex_a_partner_is_on():
    # a turned half a circle about the line through v and b: the other face
    # of the vertex, the same arms, the same angle.
    v, b, a = np.zeros(3), np.array([0.5, 0.0, 0.0]), np.array([0.2, 0.3, 0.1])
    turned = np.array([a[0], -a[1], -a[2]])
    assert angle_deg(turned, v, b) == pytest.approx(angle_deg(a, v, b), abs=1e-12)
    assert np.linalg.norm(turned - b) == pytest.approx(np.linalg.norm(a - b))


def test_the_angle_is_at_the_middle_group(lysozyme):
    """Swapping the ends leaves the angle; moving the vertex does not."""
    index, traj = lysozyme
    g = {r: [index[(r, n)] for n in LYSOZYME[r]] for r in LYSOZYME}
    at_48 = angle_series(traj[:3], g[50], g[48], g[46])
    assert angle_series(traj[:3], g[46], g[48], g[50]) == pytest.approx(at_48, abs=1e-9)
    at_50 = gmx_angles()[(48, 50, 46)][:3]
    assert all(abs(x - y) > 30 for x, y in zip(at_48, at_50))


# --- geometry ----------------------------------------------------------------------

def test_right_angle_and_straight_line():
    o = np.zeros(3)
    assert angle_deg(np.array([1.0, 0, 0]), o, np.array([0, 2.0, 0])) == pytest.approx(90.0)
    assert angle_deg(np.array([1.0, 0, 0]), o, np.array([-3.0, 0, 0])) == pytest.approx(180.0)
    assert angle_deg(np.array([1.0, 0, 0]), o, np.array([5.0, 0, 0])) == pytest.approx(0.0)


def test_atan2_keeps_a_nearly_straight_angle_that_arccos_would_round_off():
    # 1e-9 rad off straight: arccos of the dot product returns exactly 180,
    # atan2 of |cross| and dot keeps the difference.
    eps = 1e-9
    a, v, b = np.array([-1.0, 0, 0]), np.zeros(3), np.array([math.cos(eps), math.sin(eps), 0])
    via_acos = math.degrees(math.acos(float(np.dot(a, b)) / (np.linalg.norm(a) * np.linalg.norm(b))))
    assert via_acos == 180.0
    assert 180.0 - angle_deg(a, v, b) == pytest.approx(math.degrees(eps), rel=1e-6)


def test_arms_are_taken_to_their_nearest_periodic_image():
    box = np.diag([3.0, 3.0, 3.0])
    v = np.zeros(3)
    a = np.array([0.3, 0, 0])
    b = 0.4 * np.array([math.cos(math.radians(60)), math.sin(math.radians(60)), 0])
    assert angle_deg(a, v, b, box) == pytest.approx(60.0)
    # b stored one box length away, as an .xtc may store it: through the
    # boundary it is still 60 degrees; taken as stored it is nearly straight.
    shifted = b - np.array([3.0, 0, 0])
    assert angle_deg(a, v, shifted, box) == pytest.approx(60.0)
    assert angle_deg(a, v, shifted) > 170.0


def test_a_group_split_across_the_boundary_is_made_whole_before_its_centre():
    """A carboxylate with one oxygen wrapped to the far side of a 3 nm box:
    the centre of the raw coordinates is mid-box, the whole group's is at
    the group. The native route takes the second, as gmx does from a tpr."""
    class F:
        pass
    f = F()
    f.box = np.diag([3.0, 3.0, 3.0])
    f.x = np.array([[0.0, 0, 0],      # the vertex
                    [0.05, 0.3, 0],   # a's first oxygen
                    [2.95, 0.3, 0],   # a's second, at x = -0.05, wrapped to the far side
                    [0.4, 0, 0]])     # b
    (angle,) = angle_series([f], [1, 2], [0], [3])
    assert angle == pytest.approx(90.0, abs=1e-9)
    # The raw centre, (1.5, 0.3, 0), would have given about 11 degrees.
    assert angle_deg(f.x[1:3].mean(0), f.x[0], f.x[3]) == pytest.approx(math.degrees(math.atan2(0.3, 1.5)))


# --- which triples -------------------------------------------------------------------

def _atom(serial, name, resname, resnr, x, y, z):
    return (f"ATOM  {serial:5d} {name:<4} {resname:>3} A{resnr:4d}    "
            f"{x:8.3f}{y:8.3f}{z:8.3f}  1.00 20.00           {name[0]}")


def _triad(ser_y=6.0, extra=()):
    """His10 ring centre (1, 1, 0), Asp20 carboxylate centre (5, 1, 0), Ser30
    OG at (1, ser_y, 0), in Angstrom: His-Asp 0.4 nm, His-Ser (ser_y - 1)/10
    nm, Asp-Ser beyond 0.6 nm unless Ser is brought in."""
    lines = [
        _atom(1, "CA", "HIS", 10, 0.0, 0, 0), _atom(2, "ND1", "HIS", 10, 1.0, 0, 0),
        _atom(3, "NE2", "HIS", 10, 1.0, 2.0, 0),
        _atom(4, "CA", "ASP", 20, 6.0, 0, 0), _atom(5, "OD1", "ASP", 20, 5.0, 0, 0),
        _atom(6, "OD2", "ASP", 20, 5.0, 2.0, 0),
        _atom(7, "CA", "SER", 30, 0.0, ser_y + 1.5, 0), _atom(8, "OG", "SER", 30, 1.0, ser_y, 0),
        _atom(9, "CA", "GLY", 40, 1.0, -3.0, 0),
        *extra,
    ]
    return "\n".join(lines) + "\nEND\n"


CATALYTIC = [(10, "HIS"), (20, "ASP"), (30, "SER")]


def test_an_angle_needs_both_arms_in_contact_in_the_crystal():
    p = plan(read_pdb(_triad()), CATALYTIC)
    # His-Asp 0.40 nm and His-Ser 0.50 nm are contacts; Asp-Ser is
    # sqrt(4^2 + 5^2) = 6.4 A, beyond 0.6 nm. One vertex has two partners.
    (angle,) = p.angles
    assert angle.label == "Asp20–His10–Ser30"
    assert angle.crystal_deg == pytest.approx(90.0)
    assert angle.selection() == ("cog of (resnr 20 and name OD1 OD2) plus cog of (resnr 10 and name ND1 NE2) "
                                 "plus cog of (resnr 30 and name OG)")


def test_three_groups_all_in_contact_give_an_angle_at_each():
    p = plan(read_pdb(_triad(ser_y=4.0)), CATALYTIC)
    # Asp-Ser is now 5.0 A: every pair is a contact, so there are three
    # angles, and a triangle's angles sum to 180.
    assert [t.v.resnr for t in p.angles] == [10, 20, 30]
    assert sum(t.crystal_deg for t in p.angles) == pytest.approx(180.0)


def test_the_cutoff_is_inclusive_at_0_6_nm():
    at = plan(read_pdb(_triad(ser_y=1.0 + 10 * CONTACT_NM)), CATALYTIC)
    past = plan(read_pdb(_triad(ser_y=1.0 + 10 * CONTACT_NM + 0.01)), CATALYTIC)
    assert len(at.angles) == 1 and past.angles == []


def test_a_residue_standing_in_with_its_ca_takes_no_part():
    # Gly40's CA is 0.4 nm from His10's ring centre: a contact by distance,
    # but a CA says where the backbone is, not the chemistry.
    p = plan(read_pdb(_triad()), CATALYTIC + [(40, "GLY")])
    assert not next(s for s in p.sites if s.resnr == 40).functional
    assert all(40 not in (t.a.resnr, t.v.resnr, t.b.resnr) for t in p.angles)
    assert len(p.angles) == 1


def test_the_moved_threshold_is_the_distance_threshold_turned_into_an_angle():
    # A group 0.4 nm from the vertex turning MOVED_DEG moves about MOVED_NM.
    chord = 2 * 0.4 * math.sin(math.radians(MOVED_DEG / 2))
    assert chord == pytest.approx(MOVED_NM, abs=0.005)
    assert RESOLVE_DEG == MOVED_DEG / 2


def test_moved_is_strictly_beyond_the_threshold():
    s = summarise([("rep1", [100.0] * 20), ("rep2", [100.0] * 20)], "x", "degrees")
    assert AngleResult("x", 100.0 - MOVED_DEG, s).change_deg == pytest.approx(MOVED_DEG)
    assert not AngleResult("x", 100.0 - MOVED_DEG, s).moved
    assert AngleResult("x", 100.0 - MOVED_DEG - 0.1, s).moved
    assert AngleResult("x", 100.0 + MOVED_DEG + 0.1, s).moved


# --- the GROMACS route ----------------------------------------------------------------

def test_one_gangle_call_per_replica_measures_every_angle():
    p = plan(read_pdb(_triad(ser_y=4.0)), CATALYTIC)
    lines = commands(p, ["rep1", "rep2"])
    # The other gangle call per replica, -g1 plane, is the faces' (test_faces.py).
    gangle = [l for l in lines if " gangle " in l and " -g1 angle " in l]
    assert len(gangle) == 2
    assert gangle[0].startswith("$GMX gangle -s rep1/md.tpr -f rep1/md.xtc -g1 angle -group1 ")
    assert gangle[0].endswith("-oav rep1/angles.xvg")
    assert all(f"'{t.selection()}'" in gangle[0] for t in p.angles)


def test_no_angle_means_no_gangle_call():
    p = plan(read_pdb(_triad(ser_y=9.0)), CATALYTIC)
    assert p.angles == [] and not any(" gangle " in l for l in commands(p, ["rep1"]))


def test_gangle_output_is_read_column_by_column_and_a_stale_one_is_refused(tmp_path):
    p = plan(read_pdb(_triad(ser_y=4.0)), CATALYTIC)
    rep = tmp_path / "rep1"
    rep.mkdir()
    (rep / "angles.xvg").write_text("@ title\n0.0 60.0 50.0 70.0\n0.5 62.0 49.0 69.0\n")
    got = gromacs_angles(p, [rep])
    assert [r.summary.replicas[0].frames for r in got] == [2, 2, 2]
    assert [r.label for r in got] == [t.label for t in p.angles]
    (rep / "angles.xvg").write_text("0.0 60.0\n")
    with pytest.raises(AnalyzeError, match="1 columns of angles"):
        gromacs_angles(p, [rep])
    (rep / "angles.xvg").unlink()
    with pytest.raises(AnalyzeError, match="run analyze.sh again"):
        gromacs_angles(p, [rep])


# --- the report and the exit code --------------------------------------------------------

def _ar1(rng, n, mu, sd, phi=0.5):
    x, out = mu, []
    for _ in range(n):
        x = mu + phi * (x - mu) + rng.gauss(0, sd * math.sqrt(1 - phi * phi))
        out.append(x)
    return out


def _fake_run(tmp_path, angle_means, distance_sd=0.005, angle_phi=0.5, n=4000):
    """A finished run as analyze.sh leaves it, for the one-angle triad.
    Distances hold at their crystal values; the angle's replicas are drawn
    around `angle_means`."""
    rng = random.Random(1)
    (tmp_path / "caterva-setup.json").write_text(json.dumps({"pdb": "9XYZ", "chain": "A"}))
    (tmp_path / "protein.pdb").write_text(_triad())
    p = plan(read_pdb(_triad()), CATALYTIC)
    for r, mu in enumerate(angle_means, start=1):
        d = tmp_path / f"rep{r}"
        d.mkdir()
        (d / "md.xtc").write_text("")
        (d / "md.tpr").write_text("")
        cols = [_ar1(rng, n, q.crystal_nm, distance_sd) for q in p.pairs]
        (d / "catalytic.xvg").write_text("".join(
            f"{i * 0.001:.3f} " + " ".join(f"{c[i]:.5f}" for c in cols) + "\n" for i in range(n)))
        ang = _ar1(rng, n, mu, 0.5, phi=angle_phi)
        (d / "angles.xvg").write_text("".join(f"{i * 0.5:.1f} {v:.3f}\n" for i, v in enumerate(ang)))
        # gmx gangle -g1 plane -g2 vector for the angle's face: the triad
        # lies in one plane, so its Calpha arms are in the plane of the angle
        # (90 degrees from its normal) and the crystal has no face to keep.
        (d / "faces.xvg").write_text("".join(f"{i * 0.5:.1f} 90.000\n" for i in range(n)))
        (d / "rmsf.xvg").write_text("10 0.05\n20 0.05\n30 0.06\n40 0.20\n")
        (d / "water.xvg").write_text("0.0 1 0 2\n0.5 1 1 2\n")
    (tmp_path / "water_start.xvg").write_text("0.0 1 0 2\n")
    return tmp_path


def _catalytic(pdb, chain):
    return CATALYTIC, "a test mapping"


def test_consistent_replicas_that_keep_the_crystal_angle(tmp_path, capsys):
    d = _fake_run(tmp_path, [90.0, 90.0, 90.0])
    assert main([str(d), "--no-run"], catalytic=_catalytic) == 0
    out = capsys.readouterr().out
    assert "| Asp20–His10–Ser30 | 90.0 |" in out
    row = next(l for l in out.splitlines() if l.startswith("| Asp20–His10–Ser30"))
    assert row.endswith("held | consistent |")
    # After the rotamers, before the flexibility; and no longer "not measured".
    assert out.index("## Catalytic side-chain rotamers") < out.index("## Angles between catalytic groups") \
        < out.index("## Active-site flexibility")
    assert "angles between catalytic groups (next)" not in out
    assert f"`{MOVED_DEG:g}°` is the chosen threshold" in out


def test_a_consistent_turn_is_called_moved(tmp_path, capsys):
    d = _fake_run(tmp_path, [90.0 + 2 * MOVED_DEG] * 3)
    assert main([str(d), "--no-run"], catalytic=_catalytic) == 0
    assert "moved**" in capsys.readouterr().out.split("## Angles between catalytic groups")[1]


def test_an_unconverged_angle_is_not_a_result_even_when_every_distance_is(tmp_path, capsys):
    # The exit code promises 0 only when every quantity is a result.
    d = _fake_run(tmp_path, [80.0, 100.0], angle_phi=0.995, n=400)
    assert main([str(d), "--no-run"], catalytic=_catalytic) == EXIT_NOT_A_RESULT
    out = capsys.readouterr().out
    assert "not yet a result" in out.split("## Angles between catalytic groups")[1].split("## Water")[0]
    assert all(l.endswith("| consistent |") for l in out.split("## Catalytic geometry")[1]
               .split("\n## ")[0].splitlines() if l.startswith("| His10"))


def test_an_unconverged_angle_leaves_the_other_sections_to_the_distances(tmp_path, capsys):
    """The angle still makes the exit code 4, but it does not mark the other
    sections as not a result: they rest on the distances, which the angle
    is a function of. An earlier version gated them on the angles too."""
    d = _fake_run(tmp_path, [80.0, 100.0], angle_phi=0.995, n=400)
    assert main([str(d), "--no-run"], catalytic=_catalytic) == EXIT_NOT_A_RESULT
    water = capsys.readouterr().out.split("## Water at the catalytic residues")[1].split("\n## ")[0]
    rows = [l for l in water.splitlines() if l.startswith("| His10") or l.startswith("| Asp20")]
    assert rows and not any("not yet a result" in l for l in rows)
    assert rows[0].endswith("| hydrated |") and rows[1].endswith("| intermittent |")


def test_the_report_says_what_an_angle_adds_and_what_it_cannot_see(tmp_path, capsys):
    d = _fake_run(tmp_path, [90.0, 90.0, 90.0])
    main([str(d), "--no-run"], catalytic=_catalytic)
    out = capsys.readouterr().out
    section = out.split("## Angles between catalytic groups")[1].split("\n## ")[0]
    assert "fixed, frame by frame, by three distances in the table above" in section
    assert "swings round" not in out and "this sees that" not in out
    assert "It is an upper bound, not a test for a bond" in section
    # Which face a partner is on is measured now (caterva/analyze/faces.py),
    # so the angle section points to it and "Not measured" no longer lists it.
    assert "the next section does" in section
    assert "## Which face of the vertex its partners are on" in out
    assert "signed dihedral" not in out.split("## Not measured")[1]


def test_no_angle_is_said_rather_than_left_blank(tmp_path, capsys):
    d = _fake_run(tmp_path, [90.0, 90.0])
    (d / "protein.pdb").write_text(_triad(ser_y=9.0))
    for rep in ("rep1", "rep2"):
        (d / rep / "angles.xvg").unlink()
    main([str(d), "--no-run"], catalytic=_catalytic)
    section = capsys.readouterr().out.split("## Angles between catalytic groups")[1].split("\n## ")[0]
    assert "None measured" in section and f"{CONTACT_NM:g} nm" in section
