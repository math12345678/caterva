"""Run a `caterva md` setup through every GROMACS stage, capped to seconds.

    make md-smoke                      # gmx on PATH
    make md-smoke GMX=/path/to/gmx

Writes a setup for hen lysozyme (PDB 1AKI: small, one chain, the standard
GROMACS test protein), caps minimisation at 500 steps and each dynamics
stage at 200, runs run.sh with two replicas, and fails unless every stage of
every replica wrote coordinates and `--summarise` reads the result.
The inputs and topology are the real ones; only the lengths are cut. CI
runs exactly this, so a failure there reproduces here.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "md-smoke"
if str(ROOT) not in sys.path:  # run as scripts/md_smoke.py, the checkout is not on the path
    sys.path.insert(0, str(ROOT))

from caterva.analyze.sasa import routes_agree_nm2, state  # noqa: E402


def _distance_rows(text: str) -> dict:
    """pair -> simulated mean (nm) from an ANALYSIS.md catalytic-geometry table.

    Only that section is read. The hydrogen-bond table below it has rows of
    the same shape (`| Asp48-Ser50 | 1 | 1.00 |`), and reading the whole file
    let an occupancy of 1.00 overwrite a 0.30 nm distance: the "0.697 nm
    disagreement" CI reported on 2026-09-29 was this parser, not the geometry.
    """
    section = text.split("## Catalytic geometry", 1)[-1].split("\n## ", 1)[0]
    rows = {}
    for line in section.splitlines():
        m = re.match(r"\|\s*([A-Z][a-z]{2}\d+\S*[A-Z][a-z]{2}\d+)\s*\|\s*[\d.]+\s*\|\s*([\d.]+)", line)
        if m:
            rows[m.group(1)] = float(m.group(2))
    return rows


def _flexibility_rows(text: str) -> dict:
    """replica -> (pocket, rest) mean Calpha RMSF (nm) from the flexibility table.

    Compared across the two routes since 2026-09-29. Before then the GROMACS
    route fitted to the wrapped tpr coordinates and, on lysozyme, put the
    RMSF of residues 66-74 about 10% above the native route's; nothing
    compared them, so the gap was recorded as unexplained rather than caught.
    """
    section = text.split("## Active-site flexibility", 1)[-1].split("\n## ", 1)[0]
    rows = {}
    for line in section.splitlines():
        m = re.match(r"\|\s*(rep\w+)\s*\|\s*([\d.]+)\s*\|\s*([\d.]+)\s*\|", line)
        if m:
            rows[m.group(1)] = (float(m.group(2)), float(m.group(3)))
    return rows


def _rotamer_rows(text: str) -> dict:
    """residue -> per-replica fractions in the starting chi1 well."""
    section = text.split("## Catalytic side-chain rotamers", 1)[-1].split("\n## ", 1)[0]
    rows = {}
    for line in section.splitlines():
        m = re.match(r"\|\s*([A-Z][a-z]{2}\d+)\s*\|\s*-?\d+ \([^)]*\)\s*\|(.*)\|[^|]*\|\s*$", line)
        if m:
            rows[m.group(1)] = tuple(float(v) for v in m.group(2).split("|") if v.strip())
    return rows


def _table_rows(text: str, heading: str) -> dict:
    """First cell -> the other cells, for every body row of the table under
    one heading. Only that section is read, for the reason _distance_rows
    gives: tables further down have rows of the same shape."""
    section = text.split(heading, 1)[-1].split("\n## ", 1)[0]
    rows = {}
    for line in section.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if line.startswith("|") and cells and re.match(r"[A-Z][a-z]{2}\d+", cells[0]):
            rows[cells[0]] = cells[1:]
    return rows


def _angle_rows(text: str) -> dict:
    """angle -> (crystal, each replica's mean, mean across replicas), degrees.

    Compared across the routes since angles were added (2026-09-29): gmx
    gangle and the native reader agreed to 0.0006 degrees per frame on both
    10 ps lysozyme replicas, so the printed means (0.1 degree) may differ by
    one unit of their last digit and no more.
    """
    out = {}
    for label, cells in _table_rows(text, "## Angles between catalytic groups").items():
        numbers = []
        for c in cells:
            m = re.match(r"-?\d+\.\d", c)
            if not m:  # the confidence interval ("± 35.0") ends the numbers compared
                break
            numbers.append(float(m.group(0)))
        out[label] = tuple(numbers)
    return out


def _face_rows(text: str) -> dict:
    """angle -> every cell of its row in the face table: how far the crystal
    is from flat, the crystal's face, each replica's fractions on it and on
    the other face, and the verdict. The two routes measure the same
    elevation (gmx gangle -g1 plane -g2 vector against the native one, to
    0.00061 degrees per frame on both 10 ps lysozyme replicas, 2026-09-29)
    and decide each frame's face the same way, so the rows must be
    identical. A frame whose polar sine sat within gangle's rounding of the
    band edge could split them; on those replicas the nearest was 0.00099
    from it, a hundred times the rounding."""
    return _table_rows(text, "## Which face of the vertex its partners are on")


#: Frames the smoke run keeps per replica: 200 steps, one every 50.
SMOKE_FRAMES = 5


def _faces_agree(native: dict, gromacs: dict) -> tuple:
    """(agree, rows that differed by one edge frame).

    The GROMACS route rebuilds each frame's polar sine from gmx gangle's
    output, printed to 0.001 degree, so it differs from the native value by
    about 1e-5. A frame whose polar sine sits that close to the band edge
    lands on opposite sides on the two routes. On the 10 ps lysozyme
    replicas the nearest frame was 0.00099 from the edge, but CI makes a new
    trajectory every run, and with about 1.3 frames per unit of polar sine
    near the edges a split is expected in well under 1% of runs (the review
    of this check, 2026-09-30). So: every row identical, except at most one
    row in which the fractions differ by one frame and no more. A real
    disagreement between the routes moves more than one frame or more than
    one row."""
    if not native or native.keys() != gromacs.keys():
        return False, 0
    differing = [k for k in native if native[k] != gromacs[k]]
    if len(differing) > 1:
        return False, len(differing)
    for k in differing:
        for x, y in zip(native[k], gromacs[k]):
            if x == y:
                continue
            try:
                if abs(float(x) - float(y)) > 1 / SMOKE_FRAMES + 0.006:
                    return False, 1
            except ValueError:
                continue  # the verdict may follow the one frame
    return True, len(differing)


def _water_rows(text: str) -> dict:
    """residue -> every cell of its row: atoms, count at start, per replica
    mean and fraction, verdict. Water counts are integers on both routes, so
    the rows must be identical, not close."""
    return _table_rows(text, "## Water at the catalytic residues")


#: What the table's rounding can add to the difference between two printed
#: areas (nm^2): each is printed to 0.01, so each can be up to 0.005 from
#: the area it stands for.
SASA_ROUNDING_NM2 = 0.01


def sasa_allowed(a: float, b: float) -> float:
    """How far apart two printed areas (nm^2) of the same residue may be:
    the routes' own difference for a residue that size
    (caterva/analyze/sasa.py routes_agree_nm2, which grows with the area:
    set from 11,514 measured residue areas, not picked), taken at the larger
    of the two areas it could stand for, plus the rounding."""
    return routes_agree_nm2(max(a, b) + SASA_ROUNDING_NM2 / 2) + SASA_ROUNDING_NM2


def _sasa_rows(text: str) -> dict:
    """residue -> (area at start, then per replica its mean and the two
    ends of its middle-95% range), nm^2, from the solvent-exposure table.

    Those are the numbers a single frame bounds: a mean or a percentile of
    frames moves no further than the largest frame does. The SD is not
    read; it is not bounded that way. A cell that is not an area (n/a)
    ends the row, so the two routes' rows then differ in length."""
    out = {}
    for label, cells in _table_rows(text, "## Solvent exposure of the catalytic residues").items():
        numbers = []
        start = re.match(r"(\d+\.\d+)", cells[1]) if len(cells) > 2 else None
        if start:
            numbers.append(float(start.group(1)))
            for c in cells[2:-1]:
                m = re.match(r"(\d+\.\d+) ± (?:\d+\.\d+|n/a) \[(\d+\.\d+), (\d+\.\d+)\]", c)
                if not m:
                    break
                numbers += [float(v) for v in m.groups()]
        out[label] = tuple(numbers)
    return out


def _sasa_verdicts(text: str) -> dict:
    """residue -> (largest possible area as printed, or None, and the
    verdict cell), from the solvent-exposure table."""
    out = {}
    for label, cells in _table_rows(text, "## Solvent exposure of the catalytic residues").items():
        largest = re.match(r"(\d+\.\d+)$", cells[0]) if cells else None
        out[label] = (float(largest.group(1)) if largest else None, cells[-1] if cells else "")
    return out


def _verdicts_differ(native: dict, gromacs: dict, rows_n: dict, rows_g: dict) -> tuple:
    """(explained, unexplained) residues whose verdicts differ between the
    routes. The areas agree only to a tolerance, so a share near 20% or 40%
    can round into a different state on each route, and the verdict with
    it: that difference is explained when some pair of the routes' areas
    (the start, a replica's mean or an end of its middle-95% range, all of
    which the verdict reads) fall in different states. A difference in the
    verdicts with every pair in the same state is the verdict logic
    disagreeing with itself, which is a failure."""
    explained, unexplained = [], []
    for label in native:
        if native[label][1] == gromacs.get(label, (None, None))[1]:
            continue
        largest = native[label][0]
        pairs = list(zip(rows_n.get(label, ()), rows_g.get(label, ())))
        near = largest is not None and any(state(round(a / largest, 2)) != state(round(b / largest, 2))
                                           for a, b in pairs)
        (explained if near else unexplained).append(label)
    return explained, unexplained


def _sasa_agree(native: dict, gromacs: dict) -> tuple:
    """(agree, largest difference, its allowance) between two routes'
    solvent-exposure rows: the same residues, rows of the same shape, and
    every pair of areas within sasa_allowed. The difference reported is the
    one nearest its allowance. An empty table is not agreement."""
    nan = float("nan")
    if not native or native.keys() != gromacs.keys():
        return False, nan, nan
    if any(len(native[k]) != len(gromacs[k]) or not native[k] for k in native):
        return False, nan, nan
    pairs = [(abs(a - b), sasa_allowed(a, b)) for k in native for a, b in zip(native[k], gromacs[k])]
    worst, allowed = max(pairs, key=lambda p: p[0] / p[1])
    return all(d <= limit + 1e-9 for d, limit in pairs), worst, allowed


def main() -> int:
    gmx = os.environ.get("GMX", "gmx")
    if shutil.which(gmx) is None and not Path(gmx).exists():
        print(f"GROMACS not found ({gmx!r}): set GMX=/path/to/gmx. Could not run -- not a pass.")
        return 2
    shutil.rmtree(OUT, ignore_errors=True)
    subprocess.run([sys.executable, "-m", "caterva.app", "md", "--pdb", "1AKI",
                    "--out", str(OUT), "--ns", "0.001", "--replicas", "2"], check=True, cwd=ROOT)
    em = OUT / "em.mdp"
    em.write_text(re.sub(r"^nsteps\s*=\s*50000$", "nsteps          = 500", em.read_text(), flags=re.M))
    # A frame every 50 steps, so the 200-step production run keeps five and
    # RMSF has something to fluctuate over. At the setup's own interval it
    # kept only frame 0, where the native route rightly measures no RMSF and
    # gmx rmsf printed 0.0001 nm of rounding; nothing compared the two.
    md = OUT / "md.mdp"
    md.write_text(re.sub(r"^nstxout-compressed\s*=\s*\d+$", "nstxout-compressed = 50",
                         md.read_text(), flags=re.M))
    run = OUT / "run.sh"
    run.write_text(re.sub(r'(mdrun -deffnm "\$d/(?:nvt|npt|md)") \$MDRUN_FLAGS$',
                          r"\1 $MDRUN_FLAGS -nsteps 200", run.read_text(), flags=re.M))
    subprocess.run(["bash", str(run)], check=True, env={**os.environ, "GMX": gmx})
    stages = ["em.gro"] + [f"rep{r}/{s}.gro" for r in (1, 2) for s in ("nvt", "npt", "md")] \
        + ["rep1/rmsd.xvg", "rep2/rmsd.xvg"]
    missing = [s for s in stages if not (OUT / s).exists() or not (OUT / s).stat().st_size]
    if missing:
        print(f"FAIL: no coordinates from {missing}")
        return 1
    # The summary must run on real GROMACS output. 200 steps cannot converge,
    # so the expected verdict is "not a result" -- which is the point.
    code = subprocess.run([sys.executable, "-m", "caterva.app", "md", "--summarise", str(OUT)],
                          cwd=ROOT).returncode
    if code not in (0, 4):
        print(f"FAIL: --summarise exited {code} on real output")
        return 1
    # And the enzyme analysis, which fetches lysozyme's catalytic residues
    # (M-CSA via `caterva prepare`), twice: measured by Caterva from the
    # trajectories it reads itself, and by gmx distance, rmsf, angle, gangle,
    # select and sasa. The distance, flexibility, rotamer, angle, face, water
    # and solvent-exposure tables must agree, so this job checks the native
    # reader and geometry against GROMACS on every run.
    tables, flex, rot, ang, wet, face, area, exposed = {}, {}, {}, {}, {}, {}, {}, {}
    for route, extra in (("native", []), ("gromacs", ["--gromacs"])):
        code = subprocess.run([sys.executable, "-m", "caterva.app", "analyze", str(OUT), *extra],
                              cwd=ROOT, env={**os.environ, "GMX": gmx}).returncode
        if code not in (0, 4):
            print(f"FAIL: caterva analyze ({route}) exited {code} on real output")
            return 1
        text = (OUT / "ANALYSIS.md").read_text()
        tables[route] = _distance_rows(text)
        flex[route] = _flexibility_rows(text)
        rot[route] = _rotamer_rows(text)
        ang[route] = _angle_rows(text)
        wet[route] = _water_rows(text)
        face[route] = _face_rows(text)
        area[route] = _sasa_rows(text)
        exposed[route] = _sasa_verdicts(text)
    if not (OUT / "rep2" / "catalytic.xvg").exists():
        print("FAIL: caterva analyze --gromacs wrote no catalytic.xvg")
        return 1
    if not tables["native"] or tables["native"].keys() != tables["gromacs"].keys():
        print(f"FAIL: native and GROMACS analyses list different pairs: "
              f"{sorted(tables['native'])} vs {sorted(tables['gromacs'])}")
        return 1
    worst = max(abs(tables["native"][k] - tables["gromacs"][k]) for k in tables["native"])
    if worst > 0.002:
        print(f"FAIL: native and GROMACS catalytic distances differ by up to {worst:.4f} nm")
        return 1
    print(f"OK: native and GROMACS agree on {len(tables['native'])} catalytic distances "
          f"(largest difference {worst:.4f} nm).")
    if not flex["native"] or flex["native"].keys() != flex["gromacs"].keys():
        print(f"FAIL: native and GROMACS flexibility tables list different replicas: "
              f"{sorted(flex['native'])} vs {sorted(flex['gromacs'])}")
        return 1
    worst_f = max(abs(a - b) for k in flex["native"]
                  for a, b in zip(flex["native"][k], flex["gromacs"][k]))
    if worst_f > 0.0005:
        print(f"FAIL: native and GROMACS mean RMSF differ by up to {worst_f:.4f} nm")
        return 1
    print(f"OK: native and GROMACS agree on mean Calpha RMSF for {len(flex['native'])} replicas "
          f"(largest difference {worst_f:.4f} nm).")
    if not rot["native"] or rot["native"] != rot["gromacs"]:
        print(f"FAIL: native and GROMACS chi1 rotamer tables differ: {rot['native']} vs {rot['gromacs']}")
        return 1
    print(f"OK: native and GROMACS agree on the chi1 rotamers of {len(rot['native'])} catalytic residues.")
    # Angles between catalytic groups: gmx gangle against the native
    # centres and nearest-image arms. Lysozyme's six catalytic groups give
    # 24 angles under the contact cutoff, so an empty table is a failure.
    if not ang["native"] or ang["native"].keys() != ang["gromacs"].keys():
        print(f"FAIL: native and GROMACS angle tables list different angles: "
              f"{sorted(ang['native'])} vs {sorted(ang['gromacs'])}")
        return 1
    if any(len(ang["native"][k]) != len(ang["gromacs"][k]) for k in ang["native"]):
        print(f"FAIL: native and GROMACS angle rows have different shapes: {ang['native']} vs {ang['gromacs']}")
        return 1
    worst_a = max(abs(a - b) for k in ang["native"] for a, b in zip(ang["native"][k], ang["gromacs"][k]))
    if worst_a > 0.1 + 1e-9:
        print(f"FAIL: native and GROMACS angles between catalytic groups differ by up to {worst_a:.1f} degrees")
        return 1
    print(f"OK: native and GROMACS agree on {len(ang['native'])} angles between catalytic groups "
          f"(largest difference in the printed means {worst_a:.1f} degrees; the table prints 0.1).")
    # Which face of each angle's vertex its partners are on: gmx gangle's
    # plane-vector angle against the native elevation. One row per angle,
    # so an empty table is a failure here too.
    faces_ok, edge_rows = _faces_agree(face["native"], face["gromacs"])
    if not faces_ok:
        print(f"FAIL: native and GROMACS face tables differ: {face['native']} vs {face['gromacs']}")
        return 1
    print(f"OK: native and GROMACS agree on which face of the vertex the partners of {len(face['native'])} "
          "angles are on, row for row"
          + (f", except one frame on the band edge in {edge_rows} row (gangle prints 0.001 degree)."
             if edge_rows else "."))
    # Water at each catalytic residue: gmx select against the native count.
    if not wet["native"] or wet["native"] != wet["gromacs"]:
        print(f"FAIL: native and GROMACS water tables differ: {wet['native']} vs {wet['gromacs']}")
        return 1
    print(f"OK: native and GROMACS agree on the water at {len(wet['native'])} catalytic residues, "
          "count for count.")
    # Solvent-accessible area of each catalytic residue: gmx sasa (double
    # cubic lattice) against Caterva's Shrake-Rupley points. The two point
    # sets differ, so the areas agree to a tolerance, not exactly.
    if not (OUT / "rep2" / "sasa.xvg").exists():
        print("FAIL: caterva analyze --gromacs wrote no rep2/sasa.xvg")
        return 1
    areas_ok, worst_s, allowed_s = _sasa_agree(area["native"], area["gromacs"])
    if not areas_ok:
        print(f"FAIL: native and GROMACS solvent-accessible areas differ (the difference nearest its "
              f"allowance is {worst_s:.2f} nm², allowed {allowed_s:.3f}): {area['native']} vs {area['gromacs']}")
        return 1
    print(f"OK: native and GROMACS agree on the solvent-accessible area of {len(area['native'])} catalytic "
          f"residues, at the start and per replica (the difference in the printed areas nearest its "
          f"allowance: {worst_s:.2f} nm², allowed {allowed_s:.3f}, which grows with the area).")
    near, wrong = _verdicts_differ(exposed["native"], exposed["gromacs"], area["native"], area["gromacs"])
    if wrong:
        print(f"FAIL: native and GROMACS exposure verdicts differ on {', '.join(wrong)} although every area "
              f"falls in the same state on both routes: {exposed['native']} vs {exposed['gromacs']}")
        return 1
    print(f"OK: native and GROMACS give the same exposure verdict for {len(exposed['native']) - len(near)} "
          "catalytic residues" + (f"; {', '.join(near)} differ because an area sits within the routes' "
                                  "tolerance of a threshold (20% or 40%) and rounds into another state on "
                                  "each, as the areas are allowed to" if near else "") + ".")
    print("OK: minimisation, then NVT, NPT, production and RMSD for two replicas, the summary, "
          "and the enzyme analysis.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
