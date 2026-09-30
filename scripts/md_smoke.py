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


#: Frames the smoke run keeps per replica: 200 steps, one every 10. The
#: principal motions need 21 (caterva/analyze/pca.py, MIN_PCA_FRAMES), and
#: the smoke run is there to compare them across the two routes.
SMOKE_FRAMES = 21
SMOKE_NSTXOUT = 10


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


# -- principal motions of the active site (caterva/analyze/pca.py) ---------------------

def _pca_tables(text: str) -> dict:
    """The principal-motions section as {"eigen": {replica: cells},
    "rmsip": {pair: cells}, "cosine": {replica: cells}, "between": value or
    None, "chance_edge": the largest RMSIP^2 called chance, or None}. Tables
    are told apart by their header row; the section is cut out first, for
    the reason _distance_rows gives."""
    section = text.split("## Principal motions of the active site", 1)[-1].split("\n## ", 1)[0]
    out: dict = {"eigen": {}, "rmsip": {}, "cosine": {}, "between": None, "chance_edge": None}
    table = None
    for line in section.splitlines():
        if not line.startswith("|"):
            table = None
            m = re.match(r"Pooled: .*Between replicas: ([\d.]+) ", line)
            if m:
                out["between"] = float(m.group(1))
            m = re.search(r"standard deviations of the chance value \(at most ([\d.]+)\)", line)
            if m:
                out["chance_edge"] = float(m.group(1))
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if cells[0] in ("replica", "replicas"):
            table = "eigen" if "PC1 (nm²)" in cells else "rmsip" if cells[0] == "replicas" else "cosine"
        elif table and not cells[0].startswith("---"):
            out[table][cells[0]] = cells[1:]
    return out


def _close(a: str, b: str, tol: float, relative: bool = False) -> float:
    """How far over `tol` two printed numbers are (<= 0 when within it)."""
    x, y = float(a), float(b)
    diff = abs(x - y) / max(abs(x), abs(y)) if relative and max(abs(x), abs(y)) > 0 else abs(x - y)
    return diff - tol


def _pca_agree(native: dict, gromacs: dict) -> tuple:
    """(problems, largest differences) between the two routes' tables.

    Tolerances, from how each route prints and what each GROMACS tool
    rounds to:
    - eigenvalues and totals (4 significant digits in the report): gmx
      covar prints 6 and does the same linear algebra in single precision,
      so the two agree to about 1e-5 relative (6e-6 on the lysozyme
      fixture, test_pca.py; 8.2e-6 on a smoke run, 2026-09-30), and their
      printed values may differ by one unit in the 4th digit, 1e-3
      relative, and no more;
    - shares and the between-replica share (2 decimals): one unit, 0.01;
    - RMSIP (3 decimals): gmx anaeig -over prints RMSIP^2 to 0.001, which
      puts the GROMACS RMSIP within 0.0005 / (2 RMSIP) of the exact one,
      and each printed value adds 0.0005 of rounding;
    - cosine content (3 decimals): gmx analyze works from projections gmx
      anaeig printed to 1e-5 nm, and lands within 2e-5 of the native value
      on the fixture (4e-6 on a smoke run), so one unit of the printed
      digit, 0.001, and a little over.
    A verdict may differ only where the value it rests on lies within that
    tolerance of the threshold."""
    worst = {"eigenvalue": 0.0, "share": 0.0, "rmsip": 0.0, "cosine": 0.0}
    problems = [f"{table} rows differ: {sorted(native[table])} vs {sorted(gromacs[table])}"
                for table in ("eigen", "rmsip", "cosine") if native[table].keys() != gromacs[table].keys()]
    if problems:
        return problems, worst
    for name, n in native["eigen"].items():
        g = gromacs["eigen"][name]
        if n[0] != g[0]:
            problems.append(f"{name}: {n[0]} frames natively, {g[0]} by gmx covar")
        for a, b in zip(n[1:5], g[1:5]):     # PC1-3 and the total
            over = _close(a, b, 1.001e-3, relative=True)
            worst["eigenvalue"] = max(worst["eigenvalue"], over + 1.001e-3)
            if over > 0:
                problems.append(f"{name}: eigenvalue {a} natively, {b} by gmx covar")
        for a, b in zip(n[5:7], g[5:7]):
            over = _close(a, b, 0.01 + 1e-9)
            worst["share"] = max(worst["share"], over + 0.01)
            if over > 0:
                problems.append(f"{name}: share {a} natively, {b} by gmx covar")
    b_n, b_g = native["between"], gromacs["between"]
    if (b_n is None) != (b_g is None) or (b_n is not None and abs(b_n - b_g) > 0.01 + 1e-9):
        problems.append(f"between-replica share {b_n} natively, {b_g} by gmx")
    for pair, n in native["rmsip"].items():
        g = gromacs["rmsip"][pair]
        tol = 0.001 + 0.0005 / (2 * max(float(g[0]), 0.05))
        over = _close(n[0], g[0], tol)
        worst["rmsip"] = max(worst["rmsip"], over + tol)
        if over > 0:
            problems.append(f"{pair}: RMSIP {n[0]} natively, {g[0]} by gmx anaeig -over")
        edges = [e for e in (0.5, native["chance_edge"]) if e is not None]
        if n[2] != g[2] and all(abs(float(n[1]) - e) > 0.0015 for e in edges):
            problems.append(f"{pair}: verdict {n[2]!r} natively, {g[2]!r} by gmx")
    for name, n in native["cosine"].items():
        g = gromacs["cosine"][name]
        for a, b in zip(n[1:3], g[1:3]):
            over = _close(a, b, 0.0011)
            worst["cosine"] = max(worst["cosine"], over + 0.0011)
            if over > 0:
                problems.append(f"{name}: cosine content {a} natively, {b} by gmx analyze")
        if n[3] != g[3] and min(abs(float(v) - 0.5) for v in n[1:3]) > 0.0011:
            problems.append(f"{name}: verdict {n[3]!r} natively, {g[3]!r} by gmx")
    return problems, worst


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
    # A frame every SMOKE_NSTXOUT steps, so the 200-step production run
    # keeps SMOKE_FRAMES and RMSF has something to fluctuate over. At the
    # setup's own interval it kept only frame 0, where the native route
    # rightly measures no RMSF and gmx rmsf printed 0.0001 nm of rounding;
    # nothing compared the two. Five frames (one every 50) sufficed for the
    # RMSF; the principal motions refuse fewer than 21.
    md = OUT / "md.mdp"
    md.write_text(re.sub(r"^nstxout-compressed\s*=\s*\d+$", f"nstxout-compressed = {SMOKE_NSTXOUT}",
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
    # select, covar, anaeig and analyze. The distance, flexibility, rotamer,
    # angle, face, water and principal-motion tables must agree, so this job
    # checks the native reader and geometry against GROMACS on every run.
    tables, flex, rot, ang, wet, face = {}, {}, {}, {}, {}, {}
    motions = {}
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
        motions[route] = _pca_tables(text)
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
    # The principal motions of the catalytic heavy atoms: gmx covar, anaeig
    # and analyze against the native fit and decomposition. Every replica
    # has SMOKE_FRAMES frames, enough for them, so an empty table (the
    # section refusing) is a failure too.
    pm_n, pm_g = motions["native"], motions["gromacs"]
    reps = sorted(k for k in pm_n["eigen"] if k != "pooled")
    if len(reps) < 2 or "pooled" not in pm_n["eigen"] or not pm_n["rmsip"] or not pm_n["cosine"]:
        print(f"FAIL: the native route did not measure the principal motions of two replicas: {pm_n}")
        return 1
    if any(pm_n["eigen"][r][0] != str(SMOKE_FRAMES) for r in reps):
        print(f"FAIL: principal motions over {[pm_n['eigen'][r][0] for r in reps]} frames, "
              f"the smoke run writes {SMOKE_FRAMES}")
        return 1
    problems, worst = _pca_agree(pm_n, pm_g)
    if problems:
        print("FAIL: native and GROMACS principal motions differ:\n  " + "\n  ".join(problems))
        return 1
    print(f"OK: native and GROMACS agree on the principal motions of the active site for {len(reps)} "
          f"replicas and the pooled frames: eigenvalues and totals to {worst['eigenvalue']:.1e} relative, "
          f"shares to {worst['share']:.2f}, RMSIP to {worst['rmsip']:.3f} "
          f"({', '.join(f'{k} {v[0]}' for k, v in pm_n['rmsip'].items())}), cosine content to "
          f"{worst['cosine']:.3f}.")
    print("   (200 steps are 0.4 ps: these modes are the thermal motion of the minimised structure over "
          "a fraction of a picosecond, and every replica is expected to look diffusion-like. The comparison "
          "checks that the two routes compute the same thing; it says nothing about the enzyme or about "
          "sampling at production length.)")
    print("OK: minimisation, then NVT, NPT, production and RMSD for two replicas, the summary, "
          "and the enzyme analysis.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
