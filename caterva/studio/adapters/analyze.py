"""Kind `analyze`: `caterva analyze`, catalytic geometry across replicas (owner: sci-structure).

WHAT IT CALLS
-------------
`caterva analyze DIR [--gromacs | --no-run | --script-only]` through the
command's own pieces (caterva/analyze/__main__.py): `analyse` (plan the
measurements from the catalytic residues `caterva prepare` places, write
analyze.sh and chi1.ndx into the run, and measure: natively by default,
with GROMACS for `gromacs`, from analyze.sh's .xvg files for `no_run`),
`write_report` (the report, printed and written to DIR/ANALYSIS.md) and
`script_line` (what --script-only prints). The adapter writes into the
run's directory exactly what the command writes there, and nothing else.

Every verdict on the page is the one the report prints: the replica
verdict of each distance and angle (convergence.Summary.verdict), "held"
or "moved" only once it is a consistent result (`change_word`), and each
later section's verdict with "not yet a result" where the report adds it
(`as_reported`, `water_reported`). Nothing is re-judged here.

WHICH GROMACS
-------------
The command reads $GMX, else `gmx` on PATH. An app started from the Finder
has a short PATH that holds neither Homebrew's nor /usr/local's bin, so the
gromacs route looks there too before it gives up, and records which one it
called; without one it is the command's own refusal (exit 3), in the
command's words. The native route needs no GROMACS.

RMSF ALONG THE CHAIN
--------------------
The flexibility section's two means (pocket, rest) are taken over the
per-residue Calpha RMSF the library measures for every replica. Those
values are sent too (`flexibility.rmsf`), as one column per replica over
the residue numbers, with one provenance for the whole series (they are
all the same measurement), so the page can draw where along the chain a
replica moved, and the pocket residues the means were split by. A residue
a replica has no value for (a NaN from the GROMACS route) is null, never
interpolated.

THE THRESHOLDS BEHIND EACH VERDICT
----------------------------------
Every verdict word is a comparison with a number the library chose and
prints with its table (the hydrogen bonds' 0.8 and 0.2, a distance's 0.1 nm
"moved", the half of each run discarded as relaxation). `thresholds` sends
those numbers, read from the library's own constants, each as a value
chosen by the command with the sentence that says what it decides, so the
page can put each verdict beside the number it was judged against. None is
re-stated here as a literal.

SOLVENT EXPOSURE AND PRINCIPAL MOTIONS
--------------------------------------
`exposure` is the solvent-accessible area of each catalytic residue (the
Analysis's `sasa`): at the start and per replica with its SD and middle-95%
range, each with the relative area where the residue type has a maximum,
the verdict and the verdict as the report prints it (`exposure_reported`).
`exposure_not_measured` is the reason it was not measured, when it was not.
`motions` is the principal-motion analysis: eigenvalues and shares per
replica and pooled, the RMSIP of each pair of replicas, each replica's
cosine content, and the library's own verdict for each (`pca.rmsip_verdict`,
`pca.cosine_verdict`); `consistent` is the part of the exit code it owns.

SECTIONS ADDED LATER
--------------------
An Analysis may carry sections this adapter does not name. They are passed
through `extra`, by field name, with `contract.jsonable`, rather than
dropped: the report still prints them, and the page can show that it has
more than it draws.
"""
from __future__ import annotations

import dataclasses
import math
import os
import shutil
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from caterva.studio import contract
from caterva.studio.adapters import AdapterOutcome, AdapterSpec, RunContext, cli_parser
from caterva.studio.adapters.md import computed_value, checked, convergence_values, first_line, user_directory

PROG = "caterva analyze"

REQUEST_KEYS: Mapping[str, type] = {"directory": str, "mode": str}

#: request mode -> the command's flag.
MODES: Mapping[str, Optional[str]] = {"native": None, "gromacs": "--gromacs", "no_run": "--no-run",
                                      "script_only": "--script-only"}

#: Where GROMACS is installed when it is not on a GUI app's PATH.
GMX_FALLBACKS = ("/opt/homebrew/bin/gmx", "/usr/local/bin/gmx")

#: The Analysis fields this adapter draws; any other is passed through `extra`.
NAMED_FIELDS = ("pdb", "chain", "source", "plan", "distances", "flexibility", "hbonds", "rotamers", "angles",
                "water", "faces", "sasa", "sasa_route", "sasa_not_measured", "motions")


def find_gmx() -> Optional[str]:
    """$GMX if set, else `gmx` on PATH, else a usual install location."""
    env = os.environ.get("GMX")
    if env:
        return env
    found = shutil.which("gmx")
    if found:
        return found
    return next((p for p in GMX_FALLBACKS if Path(p).is_file() and os.access(p, os.X_OK)), None)


def analyze_argv(request: Mapping[str, Any]) -> List[str]:
    from caterva.analyze.__main__ import build_parser

    r = checked(request, REQUEST_KEYS, required=("directory",))
    mode = r.get("mode", "native")
    if mode not in MODES:
        raise contract.Malformed(f"mode must be one of {', '.join(MODES)}, not {mode!r}", field="mode")
    argv = [str(user_directory(r["directory"], "directory"))]
    if MODES[mode]:
        argv.append(MODES[mode])
    cli_parser(build_parser, PROG).parse_args(argv)
    return argv


def _describe(request: Mapping[str, Any]) -> str:
    mode = request.get("mode", "native")
    return f"Analysis of {Path(str(request.get('directory', '?'))).name}" + ("" if mode == "native" else f" ({mode})")


# ---------------------------------------------------------------------------
# Serialising the Analysis
# ---------------------------------------------------------------------------

CRYSTAL_METHOD = ("in protein.pdb, the structure the run started from, between the same functional-group "
                  "centres")


def _summary(s: Any, label: str) -> Dict[str, Any]:
    """A convergence.Summary of one quantity across replicas."""
    rows, extra = convergence_values(s)
    for row in rows:
        row["mean"]["label"] = f"{label}, {row['name']}"
    return {"mean": extra["mean"], "spread": extra["spread"], "ci95": extra["ci95"], "verdict": s.verdict,
            "reasons": list(s.reasons), "per_replica": rows}


def distance_row(d: Any) -> contract.DistanceRow:
    from caterva.analyze.__main__ import MOVED_NM, change_word

    view = _summary(d.summary, d.label)
    crystal = None if d.crystal_nm is None else computed_value(d.crystal_nm, "nm", "distance " + CRYSTAL_METHOD,
                                                          ["protein.pdb"], label=f"{d.label}, crystal")
    drift = None if d.drift_nm is None else computed_value(
        d.drift_nm, "nm", "simulated mean minus the crystal distance", [f"{d.label}, crystal", f"{d.label}, mean"],
        label=f"{d.label}, change", note=f"moved when larger than {MOVED_NM:g} nm (a chosen threshold)")
    view["mean"]["label"] = f"{d.label}, mean"
    return {"label": d.label, "crystal": crystal, "mean": view["mean"], "drift": drift, "moved": d.moved,
            "verdict": d.summary.verdict, "spread": view["spread"], "ci95": view["ci95"],
            "change": change_word(d.summary.verdict, d.moved), "reasons": view["reasons"],
            "per_replica": view["per_replica"]}


def angle_row(t: Any) -> Dict[str, Any]:
    from caterva.analyze.__main__ import change_word
    from caterva.analyze.angles import MOVED_DEG

    view = _summary(t.summary, t.label)
    view["mean"]["label"] = f"{t.label}, mean"
    return {"label": t.label,
            "crystal": computed_value(t.crystal_deg, t.summary.unit, "angle at the middle group " + CRYSTAL_METHOD, ["protein.pdb"],
                                 label=f"{t.label}, crystal"),
            "change": computed_value(t.change_deg, t.summary.unit, "simulated mean minus the crystal angle",
                                [f"{t.label}, crystal", f"{t.label}, mean"], label=f"{t.label}, change",
                                note=f"moved when larger than {MOVED_DEG:g}° (a chosen threshold)"),
            "moved": t.moved, "change_word": change_word(t.summary.verdict, t.moved), **view}


def _fraction(value: float, method: str, replica: str, label: str) -> contract.SourcedValue:
    return computed_value(value, "", method, [replica], label=label)


def flexibility_view(a: Any) -> Optional[Dict[str, Any]]:
    from caterva.analyze.plan import POCKET_RADIUS

    f = a.flexibility
    if f is None:
        return None
    method = "mean of the per-residue Cα RMSF over the {} residues, per replica (the report's flexibility table)"
    rows = []
    for name, pv, rv in f.per_replica:
        rows.append({
            "replica": name,
            "pocket": computed_value(pv, "nm", method.format(f"{len(a.plan.pocket)} pocket"), [name],
                                label=f"pocket RMSF, {name}"),
            "rest": computed_value(rv, "nm", method.format(f"{len(a.plan.rest)} other"), [name],
                              label=f"rest RMSF, {name}"),
            "ratio": None if rv <= 0 else computed_value(pv / rv, "", "pocket RMSF / rest RMSF",
                                                    [f"pocket RMSF, {name}", f"rest RMSF, {name}"],
                                                    label=f"pocket / rest, {name}"),
        })
    spread = f.spread
    names = [r["replica"] for r in rows]
    residues = sorted({k for _, per in f.per_residue for k in per})
    profile = None
    if residues:
        profile = {
            "unit": "nm",
            "residues": residues,
            "replicas": {name: [None if k not in per or math.isnan(per[k]) else float(per[k]) for k in residues]
                         for name, per in f.per_residue},
            "pocket": sorted(a.plan.pocket),
            "catalytic": sorted({site.resnr for site in a.plan.sites}),
            "provenance": contract.computed(
                "Calpha RMSF of each residue about its mean over a replica's frames, each frame superposed on the "
                "starting structure "
                "(the values the report's pocket and rest means are taken over)", [n for n, _ in f.per_residue]),
        }
    return {
        "pocket_residues": len(a.plan.pocket), "rest_residues": len(a.plan.rest),
        "pocket_radius": contract.sourced(POCKET_RADIUS, "Å", contract.chosen(
            "default", "residues within this distance of a catalytic residue are the pocket (caterva analyze)"),
            label="pocket radius"),
        "per_replica": rows,
        "measurable": bool(f.per_replica and f.ratios),
        "ratio_mean": None if spread is None else computed_value(spread[0], "", "mean of the replicas' pocket / rest",
                                                            names, label="pocket / rest"),
        "ratio_sd": None if spread is None else computed_value(spread[1], "", "SD of the replicas' pocket / rest",
                                                          names, label="pocket / rest SD"),
        "is_result": a.distances_consistent,
        "rmsf": profile,
    }


def hbond_rows(a: Any) -> Optional[List[Dict[str, Any]]]:
    from caterva.analyze.__main__ import HBOND_STANDS, as_reported, hbond_verdict

    if a.hbonds is None:
        return None
    rows = []
    for o in a.hbonds:
        verdict = hbond_verdict(o)
        rows.append({"label": o.label, "at_start": o.at_start,
                     "bonded": bool(o.at_start or any(f > 0 for f in o.fractions)),
                     "per_replica": [{"replica": n,
                                      "fraction": _fraction(fr, "fraction of frames hydrogen-bonded (donor-acceptor "
                                                            "at most 0.35 nm, angle at most 30°)", n,
                                                            f"{o.label}, {n}"),
                                      "mean_bonds": computed_value(m, "", "mean hydrogen bonds per frame", [n],
                                                              label=f"{o.label} bonds per frame, {n}")}
                                     for n, fr, m in o.per_replica],
                     "verdict": verdict, "reported": as_reported(verdict, a, HBOND_STANDS)})
    return rows


def rotamer_rows(a: Any) -> Optional[List[Dict[str, Any]]]:
    from caterva.analyze.__main__ import ROTAMER_STANDS, as_reported
    from caterva.analyze.rotamers import WELLS, rotamer_verdict

    if a.rotamers is None:
        return None
    rows = []
    for r in a.rotamers:
        verdict = rotamer_verdict(r)
        rows.append({
            "label": r.label,
            "at_start": computed_value(r.at_start, "°", "chi1 (N-CA-CB-gamma) in em.gro", ["em.gro"],
                                  label=f"{r.label} chi1 at start"),
            "start_well": r.start_well,
            "per_replica": [{"replica": n,
                             "wells": {w: _fraction(p[w], f"fraction of frames with chi1 nearest {w}°", n,
                                                    f"{r.label} {w}, {n}") for w in WELLS if w in p},
                             "kept": _fraction(p[r.start_well], "fraction of frames in the starting well", n,
                                               f"{r.label} kept, {n}")}
                            for n, p in r.per_replica],
            "verdict": verdict, "reported": as_reported(verdict, a, ROTAMER_STANDS)})
    return rows


def face_rows(a: Any) -> Optional[List[Dict[str, Any]]]:
    from caterva.analyze.__main__ import face_reported
    from caterva.analyze.faces import face_name, face_verdict

    if a.faces is None:
        return None
    rows = []
    for f in a.faces:
        verdict = face_verdict(f)
        rows.append({
            "label": f.label,
            "crystal_out_of_flat": computed_value(f.crystal_out_of_flat_deg, "°",
                                             "arcsin(sin(angle) × sin(elevation)) in the crystal", ["protein.pdb"],
                                             label=f"{f.label} out of flat"),
            "crystal_face": face_name(f.crystal_side),
            "per_replica": [{"replica": n,
                             "kept": None if f.crystal_side == 0 or math.isnan(k) else
                             _fraction(k, "fraction of frames on the crystal's face", n, f"{f.label} kept, {n}"),
                             "other": None if f.crystal_side == 0 or math.isnan(o) else
                             _fraction(o, "fraction of frames on the other face", n, f"{f.label} other, {n}")}
                            for n, k, o in f.per_replica],
            "verdict": verdict, "reported": face_reported(f, a)})
    return rows


def water_rows(a: Any) -> Optional[List[Dict[str, Any]]]:
    from caterva.analyze.__main__ import water_reported
    from caterva.analyze.water import STAND_IN, hydration_verdict

    if a.water is None:
        return None
    rows = []
    for h, site in zip(a.water, a.plan.sites):
        reported = water_reported(h, site, a)
        rows.append({
            "label": h.label, "atoms": list(site.atoms), "stand_in": reported == STAND_IN, "at_start": h.at_start,
            "per_replica": [{"replica": n,
                             "mean": None if math.isnan(f) else computed_value(m, "", "mean water oxygens within "
                                                                          "0.35 nm per frame", [n],
                                                                          label=f"{h.label} waters, {n}"),
                             "fraction": None if math.isnan(f) else _fraction(f, "fraction of frames with at least "
                                                                              "one water", n,
                                                                              f"{h.label} wet, {n}")}
                            for n, m, f in h.per_replica],
            "verdict": hydration_verdict(h), "reported": reported})
    return rows


def _number(value: float, unit: str, method: str, inputs: Sequence[str], label: str
            ) -> Optional[contract.SourcedValue]:
    """A computed value; None for a NaN (a replica with no frames), never a number made up."""
    return None if value is None or math.isnan(value) else computed_value(value, unit, method, inputs, label=label)


def exposure_rows(a: Any) -> Optional[List[Dict[str, Any]]]:
    from caterva.analyze.__main__ import exposure_reported
    from caterva.analyze.sasa import BURIED, EXPOSED, PROBE_NM, exposure_verdict, state

    if a.sasa is None:
        return None
    method = (f"solvent-accessible area of the residue, whole protein as the surface, {PROBE_NM:g} nm probe "
              f"({a.sasa_route} route)")
    rows = []
    for e in a.sasa:
        rel = e.relative(e.at_start)
        per = []
        for n, mean, sd, low, high in e.per_replica:
            r = e.relative(mean)
            per.append({
                "replica": n,
                "mean": _number(mean, "nm²", method + ", mean over frames", [n], f"{e.label} area, {n}"),
                "sd": _number(sd, "nm²", method + ", SD over frames", [n], f"{e.label} area SD, {n}"),
                "low": _number(low, "nm²", method + ", 2.5th percentile of frames", [n], f"{e.label} area low, {n}"),
                "high": _number(high, "nm²", method + ", 97.5th percentile of frames", [n],
                                f"{e.label} area high, {n}"),
                "relative": None if r is None else _number(
                    r, "", "mean area / the largest area the residue type can have (Tien et al. 2013)", [n],
                    f"{e.label} relative area, {n}"),
            })
        rows.append({
            "label": e.label, "resname": e.resname, "in_chain": e.in_chain,
            "max_area": None if e.max_area is None else computed_value(
                e.max_area, "nm²", "largest possible area of the residue type, Tien et al. (2013) Table 1 "
                "(theoretical, ALLOWED)", [], label=f"{e.label} largest possible area"),
            "at_start": _number(e.at_start, "nm²", method + ", in em.gro", ["em.gro"], f"{e.label} area at start"),
            "relative_at_start": None if rel is None else _number(
                rel, "", "area at start / the largest area the residue type can have", ["em.gro"],
                f"{e.label} relative area at start"),
            "state_at_start": None if rel is None else state(round(rel, 2)),
            "per_replica": per,
            "verdict": exposure_verdict(e), "reported": exposure_reported(e, a)})
    return rows


def _modes_row(r: Any, k: int) -> Dict[str, Any]:
    from caterva.analyze import pca

    return {
        "name": r.name, "frames": r.frames, "moved": r.moved,
        "eigenvalues": [computed_value(v, "nm²", "eigenvalue of the covariance of the superposed frames "
                                       "(mean-square fluctuation along the mode)", [r.name],
                                       label=f"{r.name} PC{i + 1}") for i, v in enumerate(r.eigenvalues)],
        "total": computed_value(r.trace, "nm²", "sum of every eigenvalue", [r.name], label=f"{r.name} total"),
        "share_pc1": _number(r.share(1), "", "PC1 eigenvalue / total", [r.name], f"{r.name} share in PC1"),
        "share_modes": _number(r.share(k), "", f"sum of the first {k} eigenvalues / total", [r.name],
                               f"{r.name} share in PC1-{k}"),
        "cosine": None if r.cosine is None else [
            _number(c, "", f"cosine content of the projection on PC{i + 1}", [r.name], f"{r.name} PC{i + 1} cosine")
            for i, c in enumerate(r.cosine)],
        "cosine_verdict": None if r.cosine is None else pca.cosine_verdict(r)}


def motions_view(a: Any) -> Optional[Dict[str, Any]]:
    from caterva.analyze import pca

    m = a.motions
    if m is None:
        return None
    k = pca.RMSIP_MODES
    view: Dict[str, Any] = {
        "atoms": m.atoms, "residues": list(m.residues), "not_measured": m.not_measured,
        "too_short": [{"replica": n, "frames": f} for n, f in m.too_short],
        "min_frames": pca.MIN_PCA_FRAMES, "modes_compared": k, "consistent": m.consistent,
        "replicas": [_modes_row(r, k) for r in m.replicas],
        "pooled": None if m.pooled is None else _modes_row(m.pooled, k),
        "between": None if m.between is None else _number(
            m.between, "", "share of the pooled total that is the spread of the replicas' mean structures",
            [r.name for r in m.replicas], "between replicas"),
        "overlaps": [], "diffusive_at": pca.DIFFUSIVE,
    }
    if m.dim > 0:
        view["dim"] = m.dim
    for x, y, v in m.overlaps:
        view["overlaps"].append({
            "a": x, "b": y,
            "rmsip": _number(v, "", f"RMSIP of the first {k} modes of the two replicas", [x, y], f"RMSIP {x}-{y}"),
            "rmsip2": _number(v * v, "", "RMSIP squared", [x, y], f"RMSIP² {x}-{y}"),
            "verdict": pca.rmsip_verdict(v, m.dim)})
    return view


def thresholds() -> Dict[str, List[contract.SourcedValue]]:
    """The library's verdict thresholds, by the section they judge."""
    from caterva.analyze import faces, hbonds, pca, rotamers, sasa, water
    from caterva.analyze.__main__ import KEPT, LOST, FORMED, MOVED_NM, SPLIT
    from caterva.analyze.angles import MOVED_DEG
    from caterva.md import convergence as conv

    def t(value: float, unit: str, label: str, decides: str) -> contract.SourcedValue:
        return contract.sourced(value, unit, contract.chosen("default", decides), label=label)

    return {
        "replicas": [
            t(conv.DISCARD, "", "discarded as relaxation",
              "the fraction at the start of each replica left out of its mean (caterva/md/convergence.py)"),
            t(conv.MIN_BLOCKS, "", "fewest blocks", "a block level is trusted only with at least this many blocks"),
            t(conv.MIN_EFFECTIVE_SAMPLES, "", "fewest independent samples",
              "a replica with fewer effectively independent samples than this is not converged"),
            t(conv.DISAGREEMENT_FACTOR, "", "disagreement factor",
              "replicas disagree when their spread exceeds this multiple of the typical within-replica error"),
            t(conv.CONFIDENCE, "", "confidence level", "the two-sided confidence of the interval for the mean"),
        ],
        "distances": [t(MOVED_NM, "nm", "moved beyond",
                        "a consistent mean this far from the crystal distance is reported as moved, else held")],
        "angles": [t(MOVED_DEG, "°", "moved beyond",
                     "a consistent mean this far from the crystal angle is reported as moved, else held")],
        "hbonds": [
            t(hbonds.MAX_DA_NM, "nm", "donor-acceptor at most", "a frame counts as bonded within this distance"),
            t(hbonds.MAX_ANGLE_DEG, "°", "angle at most", "and within this hydrogen-donor-acceptor angle"),
            t(KEPT, "", "kept at least", "bonded at the start and at least this fraction of frames in every replica"),
            t(LOST, "", "lost at most", "bonded at the start and at most this fraction in every replica"),
            t(FORMED, "", "formed at least", "not bonded at the start and at least this fraction in every replica"),
            t(SPLIT, "", "replicas disagree beyond", "the replicas' fractions differ by more than this"),
        ],
        "rotamers": [
            t(rotamers.KEPT, "", "kept at least", "at least this fraction of frames in the starting well, every replica"),
            t(rotamers.FLIPPED, "", "flipped at most", "at most this fraction in the starting well, every replica"),
            t(rotamers.SPLIT, "", "replicas disagree beyond", "the replicas' fractions differ by more than this"),
        ],
        "faces": [
            t(faces.FLAT_DEG, "°", "out of flat at least",
              "a frame is on a face when every arm stands this far out of the plane of the other two"),
            t(faces.KEPT, "", "kept at least", "at least this fraction of frames on one face, every replica"),
            t(faces.SPLIT, "", "replicas disagree beyond", "the replicas' fractions differ by more than this"),
        ],
        "water": [
            t(water.WATER_NM, "nm", "within", "a water oxygen this close to the residue's atoms counts"),
            t(water.WET, "", "hydrated at least", "at least this fraction of frames with a water, every replica"),
            t(water.DRY, "", "dry at most", "at most this fraction of frames with a water, every replica"),
            t(water.SPLIT, "", "replicas disagree beyond", "the replicas' fractions differ by more than this"),
        ],
        "exposure": [
            t(sasa.BURIED, "", "buried below", "a share of the largest possible area below this is buried"),
            t(sasa.EXPOSED, "", "exposed at least", "a share of the largest possible area at or above this is exposed"),
        ],
        "motions": [
            t(pca.SAME_RMSIP2, "", "same motions, RMSIP² at least", "two replicas' first modes span the same directions"),
            t(pca.CHANCE_SD, "", "chance, within this many SD", "RMSIP² this close to the random-subspace value is no more alike than chance"),
            t(pca.DIFFUSIVE, "", "diffusion-like at", "PC1 or PC2 cosine content this high looks like random diffusion"),
        ],
    }


def extra_sections(a: Any) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for f in dataclasses.fields(a):
        if f.name in NAMED_FIELDS:
            continue
        try:
            out[f.name] = contract.jsonable(getattr(a, f.name))
        except TypeError as e:
            out[f.name] = {"unserialised": str(e)}
    return out


def _written(d: Path, measured: bool) -> List[str]:
    names = ["analyze.sh"] + [n for n in ("chi1.ndx", "pca.ndx") if (d / n).exists()]
    if measured:
        names.append("ANALYSIS.md")
    return [str(d / n) for n in names]


def analyze_run(request: Mapping[str, Any], ctx: RunContext) -> AdapterOutcome:
    from caterva.analyze import __main__ as cli

    args = cli_parser(cli.build_parser, PROG).parse_args(analyze_argv(request))
    d = Path(args.directory)
    mode = request.get("mode", "native")
    gmx = find_gmx() if args.gromacs else None
    ctx.progress.stage("plan", f"Placing the catalytic residues of the run in {d.name} and planning the measurements")
    ctx.progress.check_cancelled()
    ctx.progress.stage("measure", {"native": "Reading every replica's trajectory",
                                   "gromacs": f"Measuring with GROMACS ({gmx or 'gmx'})",
                                   "no_run": "Reading the .xvg files analyze.sh wrote",
                                   "script_only": "Writing analyze.sh"}[mode])
    try:
        done = cli.analyse(d, script_only=args.script_only, no_run=args.no_run, gromacs=args.gromacs,
                           catalytic=cli.catalytic_residues, gmx=gmx)
    except cli.AnalyzeError as e:
        refusal = f"caterva analyze: {e}"
        return AdapterOutcome(3, None, first_line(refusal), refusal)
    ctx.progress.check_cancelled()
    p = done.plan
    base: Dict[str, Any] = {
        "pdb": done.pdb, "chain": done.chain, "source": done.source, "mode": mode,
        "replicas": [r.name for r in done.replicas],
        "catalytic": [{"resnr": s.resnr, "label": s.label, "atoms": list(s.atoms), "functional": s.functional}
                      for s in p.sites],
        "notes": list(p.notes),
        "counts": {"distances": len(p.pairs), "angles": len(p.angles), "faces": len(p.faces),
                   "water_sites": len(p.sites), "pocket": len(p.pocket), "rest": len(p.rest)},
        "gmx": gmx,
    }
    if done.analysis is None:
        text = cli.script_line(d, p, done.pca_atoms) + "\n"
        result: contract.AnalyzeResult = {
            **base, "all_consistent": False, "distances_consistent": False, "distances": [],
            "flexibility": None, "hbonds": None, "rotamers": None, "angles": [], "water": None, "faces": None,
            "exposure": None, "motions": None, "script_written": True, "report_markdown": text, "measured": False, "written": _written(d, False),
            "extra": {},
        }
        return AdapterOutcome(0, result, first_line(text))
    ctx.progress.stage("report", f"Writing {d.name}/ANALYSIS.md")
    a = done.analysis
    text = cli.write_report(d, a)
    result = {
        **base,
        "all_consistent": a.all_consistent,
        "distances_consistent": a.distances_consistent,
        "distances": [distance_row(x) for x in a.distances],
        "flexibility": flexibility_view(a),
        "hbonds": hbond_rows(a),
        "rotamers": rotamer_rows(a),
        "angles": [angle_row(t) for t in a.angles],
        "water": water_rows(a),
        "faces": face_rows(a),
        "exposure": exposure_rows(a),
        "exposure_not_measured": a.sasa_not_measured,
        "motions": motions_view(a),
        "script_written": True,
        "report_markdown": text,
        "measured": True,
        "written": _written(d, True),
        "extra": extra_sections(a),
        "thresholds": thresholds(),
    }
    verdicts = [x.summary.verdict for x in a.distances]
    summary = (f"{a.pdb}{' chain ' + a.chain if a.chain else ''}: {len(done.replicas)} replica"
               f"{'s' if len(done.replicas) != 1 else ''}, {verdicts.count('consistent')} of {len(verdicts)} "
               f"distances consistent" + ("" if a.all_consistent else "; not yet a result"))
    return AdapterOutcome(0 if a.all_consistent else cli.EXIT_NOT_A_RESULT, result, summary)


def register(registry) -> None:
    registry.register(AdapterSpec(
        kind="analyze",
        title="Analyse replicas",
        command="analyze",
        needs=("network", "gromacs"),
        argv=analyze_argv,
        run=analyze_run,
        describe=_describe,
        cli_prefix=("caterva", "analyze"),
    ))


__all__ = ["GMX_FALLBACKS", "MODES", "PROG", "analyze_argv", "analyze_run", "angle_row", "distance_row",
           "exposure_rows", "extra_sections", "find_gmx", "motions_view", "thresholds", "flexibility_view",
           "register"]
