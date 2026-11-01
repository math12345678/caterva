"""`caterva fep`: an absolute binding free energy, held to the Ki it should reproduce.

    caterva fep --ec 1.1.1.27 --organism human --inhibitor gossypol --isoform LDH-A \\
        --complex complex.gro --topology topol.top --ligand GSP --ligand-itp gossypol.itp \\
        --out ldha-gossypol && bash ldha-gossypol/run.sh
    caterva fep --summarise ldha-gossypol

The target is the band `caterva bind` builds from the cited Ki rows (same
flags: --state, --isoform, --html). The calculation runs at those rows'
assay temperature, with Boresch restraints chosen from your complex and
their standard-state correction computed analytically; PROVENANCE.md says
where every setting came from. You supply an equilibrated complex and the
ligand's topology: neither is invented here.

--summarise combines the legs per replica, ΔG°bind = ΔG_solvent +
ΔG_restraints_on - ΔG_complex, reports mean ± SEM across replicas, and
judges it against the band at 2σ.

Exit codes: 0 written (or: agrees), 4 disagrees or not yet a result (one
replica, missing legs), 3 refused and said why, 2 malformed question, 1 a crash.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from caterva.bind.core import Target, Verdict, judge

EXIT_OK, EXIT_CRASH, EXIT_USAGE, EXIT_REFUSED, EXIT_NOT_A_RESULT = 0, 1, 2, 3, 4
KJ_PER_KCAL = 4.184


def _target(a) -> Optional[Target]:
    from caterva.bind.__main__ import COMMON, _rows, _compound_names
    from caterva.bind.core import target
    organism = COMMON.get(a.organism.strip().lower(), a.organism.strip())
    if a.html:
        html = a.html.read_text(encoding="utf-8")
    else:
        from caterva.checkout import literature_module
        html = literature_module("brenda_client").fetch_brenda_html(a.ec)
    rows = _rows(html, a.ec, organism, a.inhibitor)
    if not rows:
        names = _compound_names(html, a.ec, organism)
        print(f"caterva fep: no Ki for {a.inhibitor!r} with EC {a.ec} in {organism}; nothing to hold "
              f"a calculation to." + (f" Compounds with one: {'; '.join(names)}" if names else ""), file=sys.stderr)
        return None
    t = target(rows, a.state, a.isoform)
    if t.lo is None:
        print(f"caterva fep: none of the {len(rows)} Ki row(s) measured the {a.state} state:", file=sys.stderr)
        for m in t.excluded:
            print(f"  Ki {m.ki_mM:g} mM (ref {m.reference}): {m.excluded}", file=sys.stderr)
        return None
    return t


def setup(a) -> int:
    from caterva.fep.setup import FepSetup, temperature_for
    missing = [f for f in ("complex", "topology", "ligand", "ligand_itp", "inhibitor", "ec", "out")
               if getattr(a, f) is None]
    if missing:
        print("caterva fep: missing " + ", ".join("--" + m.replace("_", "-") for m in missing), file=sys.stderr)
        return EXIT_USAGE
    for p in (a.complex, a.topology, a.ligand_itp):
        if not p.is_file():
            print(f"caterva fep: {p} does not exist", file=sys.stderr)
            return EXIT_REFUSED
    try:
        t = _target(a)
    except Exception as e:
        print(f"caterva fep: could not read BRENDA for {a.ec}: {e}", file=sys.stderr)
        return EXIT_REFUSED
    if t is None:
        return EXIT_REFUSED
    phs = sorted({m.ph for m in t.used if m.ph is not None})
    try:
        s = FepSetup(t, a.complex, a.topology, a.ligand, a.ligand_itp, temperature_for(t, a.temperature),
                     ph=phs[0] if len(phs) == 1 else None, replicas=a.replicas, ns=a.ns,
                     trajectory=a.trajectory)
    except ValueError as e:
        print(f"caterva fep: {e}", file=sys.stderr)
        return EXIT_REFUSED
    s.write(a.out)
    r = s.restraint
    from caterva.fep.core import schedule
    print(f"Wrote {a.out}/: {t.compound} -> {t.organism}, {s.replicas} replica(s), "
          f"{len(schedule('complex'))} complex + {len(schedule('solvent'))} solvent windows each.")
    print(f"  target     ΔG°bind {t.lo:.2f} to {t.hi:.2f} kcal/mol "
          f"({', '.join('BRENDA ref ' + x for x in t.references)})")
    print(f"  run at     {s.temperature.kelvin:.2f} K ({s.temperature.origin}: {s.temperature.source})")
    print(f"  restraint  |P1 L1| {r.r:.3f} nm, smallest sine {r.quality:.2f}, "
          f"correction +{s.restraint_kj() / KJ_PER_KCAL:.2f} kcal/mol at 1 M")
    if r.anchor_rmsf:
        print(f"  anchors    RMSF {', '.join(f'{x * 10:.2f}' for x in r.anchor_rmsf)} A over {a.trajectory.name}")
    for c in t.caveats:
        print(f"  caveat     {c}")
    if s.replicas < 2:
        print("  ONE REPLICA: the result will have no spread; --summarise will not call it a result.")
    print(f"Then: bash {a.out}/run.sh && caterva fep --summarise {a.out}")
    return EXIT_OK


def _leg(directory: Path, leg: str, rep: int, n_windows: int, lines: List[str], warnings: List[str]):
    """(ΔG, σ, estimator) kJ/mol for one leg of one replica, from Caterva's
    own MBAR on the raw dhdl files when every window wrote every state's
    energy; from `gmx bar`'s log otherwise (runs set up before the
    estimator existed). `estimator` says which: ESTIMATOR_MBAR or ESTIMATOR_GMX_BAR."""
    from caterva.fep.core import read_bar
    from caterva.fep.estimators import analyse_leg
    d = directory / leg / f"rep{rep}"
    xvgs = [d / f"lambda{i}" / "prod.xvg" for i in range(n_windows)]
    if all(x.is_file() and x.stat().st_size > 0 for x in xvgs):
        try:
            a = analyse_leg(xvgs)
        except ValueError as e:
            if "calc-lambda-neighbors" not in str(e):
                lines.append(f"  rep{rep}: {leg} leg unreadable: {e}")
                return None
        else:
            gmx = ""
            if (d / "bar.log").is_file():
                g, ge = read_bar((d / "bar.log").read_text())
                gmx = f"; gmx bar {g:.2f} ± {ge:.2f}"
            lines.append(
                f"  rep{rep} {leg:<7} MBAR {a.dg_mbar:8.2f} ± {a.err_mbar:.2f} kJ/mol (BAR {a.dg_bar:.2f} ± "
                f"{a.err_bar:.2f}" + (f", TI {a.dg_ti:.2f} ± {a.err_ti:.2f}" if a.dg_ti is not None else "")
                + f"{gmx}); {sum(a.samples_used)} independent of {sum(a.samples_raw)} samples, "
                f"min overlap {a.min_overlap:.3f} ({a.min_overlap_pair[0]}-{a.min_overlap_pair[1]})")
            warnings.extend(f"rep{rep} {leg}: {w}" for w in a.warnings)
            return a.dg_mbar, a.err_mbar, ESTIMATOR_MBAR
    log = d / "bar.log"
    if not log.is_file():
        lines.append(f"  rep{rep}: {leg} leg not finished (no prod.xvg for every window, no bar.log)")
        return None
    g, ge = read_bar(log.read_text())
    lines.append(f"  rep{rep} {leg:<7} gmx bar {g:8.2f} ± {ge:.2f} kJ/mol (no all-state energies for MBAR)")
    return g, ge, ESTIMATOR_GMX_BAR


#: How a leg's free energy was estimated, as `_leg` reports it.
ESTIMATOR_MBAR = "MBAR on the raw dhdl files (Caterva's own estimator)"
ESTIMATOR_GMX_BAR = "gmx bar (no all-state energies for MBAR)"


@dataclass
class ReplicaDG:
    """One finished replica: both legs and the binding free energy they close to."""

    rep: int
    complex_kj: float
    complex_err_kj: float
    complex_estimator: str
    solvent_kj: float
    solvent_err_kj: float
    solvent_estimator: str
    dg_kcal: float


@dataclass
class FepSummary:
    """What `--summarise DIR` read and decided, before it is printed."""

    #: caterva-fep.json as written by the setup.
    record: dict
    #: The per-leg and per-replica lines, as printed.
    lines: List[str]
    warnings: List[str]
    replicas: List[ReplicaDG]
    #: Per-replica propagated BAR errors, kcal/mol, in replica order.
    bar_errs: List[float]
    #: Set once two or more replicas finished; None before.
    mean: Optional[float] = None
    sem: Optional[float] = None
    sigma: Optional[float] = None
    verdict: Optional[Verdict] = None

    @property
    def code(self) -> int:
        """0 agrees; 4 disagrees, or not yet a result (fewer than two replicas)."""
        return EXIT_OK if self.verdict is not None and self.verdict.word == "agrees" else EXIT_NOT_A_RESULT


def read_summary(directory: Path) -> Tuple[Optional[FepSummary], Optional[str]]:
    """(summary, None), or (None, the refusal `summarise` prints, exit 3):
    each replica's legs combined, ΔG°bind = ΔG_solvent + ΔG_restraints_on -
    ΔG_complex, and with two or more replicas the mean, its σ (the larger of
    the SEM and the propagated BAR error) and the verdict against the band."""
    rec_path = directory / "caterva-fep.json"
    if not rec_path.is_file():
        return None, f"caterva fep: {directory} has no caterva-fep.json; it was not written by caterva fep"
    rec = json.loads(rec_path.read_text())
    reps: List[ReplicaDG] = []
    bar_errs: List[float] = []
    lines: List[str] = []
    warnings: List[str] = []
    for rep in range(1, rec["replicas"] + 1):
        legs = {}
        for leg in ("complex", "solvent"):
            got = _leg(directory, leg, rep, rec["windows"][leg], lines, warnings)
            if got is None:
                legs = None
                break
            legs[leg] = got
        if legs is None:
            continue
        (gc, ec, how_c), (gs, es, how_s) = legs["complex"], legs["solvent"]
        dg = gs + rec["restraint"]["correction_kj"] - gc
        reps.append(ReplicaDG(rep, gc, ec, how_c, gs, es, how_s, dg / KJ_PER_KCAL))
        bar_errs.append(math.hypot(ec, es) / KJ_PER_KCAL)
        lines.append(f"  rep{rep}: complex {gc:.2f} ± {ec:.2f}, solvent {gs:.2f} ± {es:.2f} kJ/mol "
                     f"-> ΔG°bind {dg / KJ_PER_KCAL:.2f} kcal/mol")
    s = FepSummary(rec, lines, warnings, reps, bar_errs)
    per_rep = [r.dg_kcal for r in reps]
    if len(per_rep) < 2:
        return s, None
    t = rec["target"]
    n = len(per_rep)
    s.mean = sum(per_rep) / n
    s.sem = math.sqrt(sum((x - s.mean) ** 2 for x in per_rep) / (n - 1) / n)
    s.sigma = max(s.sem, math.sqrt(sum(e * e for e in bar_errs)) / n)
    lo, hi = t["band_kcal"]
    tt = Target(t["compound"], t["organism"], t["state"], [], [], lo, hi, t["references"], t["caveats"])
    s.verdict = judge(tt, s.mean, s.sigma, temperature_c=rec["temperature_k"] - 273.15)
    return s, None


def summary_lines(s: FepSummary) -> List[str]:
    """What `--summarise` prints for a summary, one print() per item."""
    rec, t = s.record, s.record["target"]
    lo, hi = t["band_kcal"]
    out = [f"{t['compound']} -> {t['organism']} at {rec['temperature_k']:.2f} K; "
           f"restraint correction +{rec['restraint']['correction_kj'] / KJ_PER_KCAL:.2f} kcal/mol",
           "\n".join(s.lines),
           f"TARGET  {lo:.2f} to {hi:.2f} kcal/mol ({', '.join('BRENDA ref ' + r for r in t['references'])})"]
    out += [f"  caveat: {c}" for c in t["caveats"]]
    out += [f"  WARNING {w}" for w in s.warnings]
    if s.verdict is None:
        out.append(f"NOT A RESULT: {len(s.replicas)} finished replica(s). One run's BAR error is its "
                   f"statistical error, not the spread between independent runs.")
        return out
    v = s.verdict
    out.append(f"COMPUTED  {s.mean:.2f} ± {s.sigma:.2f} kcal/mol ({len(s.replicas)} replicas; σ = the larger "
               f"of SEM and propagated BAR error)")
    out.append(f"VERDICT   {v.word.upper()}: {v.detail}.")
    if v.word == "agrees" and len(t["references"]) < 2:
        out.append("  Agreement with one publication is consistency, not validation.")
    return out


def summarise(directory: Path) -> int:
    s, refusal = read_summary(directory)
    if s is None:
        print(refusal, file=sys.stderr)
        return EXIT_REFUSED
    for line in summary_lines(s):
        print(line)
    return s.code


def optimise(directory: Path, leg: str, rep: int) -> int:
    """Where the windows of a leg should go, from a pilot run of it."""
    import numpy as np
    from caterva.fep.estimators import TARGET_STEP_KT, analyse_leg, redistribute
    rec_path = directory / "caterva-fep.json"
    n = json.loads(rec_path.read_text())["windows"][leg] if rec_path.is_file() else None
    d = directory / leg / f"rep{rep}"
    xvgs = sorted(d.glob("lambda*/prod.xvg"), key=lambda p: int(p.parent.name[6:]))
    if not xvgs or (n and len(xvgs) != n):
        print(f"caterva fep: {d} has {len(xvgs)} finished window(s)" + (f" of {n}" if n else "")
              + "; optimising needs the whole pilot leg", file=sys.stderr)
        return EXIT_REFUSED
    try:
        a = analyse_leg(xvgs)
    except ValueError as e:
        print(f"caterva fep: {e}", file=sys.stderr)
        return EXIT_REFUSED
    if a.lambdas is None:
        print("caterva fep: the dhdl files carry no lambda vectors", file=sys.stderr)
        return EXIT_REFUSED
    lam = np.array(a.lambdas)
    L = np.array(a.lengths)
    total = float(L.sum())
    need = max(2, int(math.ceil(total / TARGET_STEP_KT)) + 1)
    same = redistribute(lam, L, len(lam))
    print(f"{leg} leg, replica {rep}: {len(lam)} windows, thermodynamic length {total:.2f} kT "
          f"(Shenfeld et al. 2009, doi:10.1103/PhysRevE.80.046705)")
    print("  step lengths (kT): " + " ".join(f"{x:.2f}" for x in L))
    print(f"  longest step {L.max():.2f} kT ({int(L.argmax())}-{int(L.argmax()) + 1}), "
          f"shortest {L.min():.2f} kT ({int(L.argmin())}-{int(L.argmin()) + 1})")
    print(f"  equal-length schedule, same {len(lam)} windows: every step {total / (len(lam) - 1):.2f} kT")
    print(f"  windows needed for every step <= {TARGET_STEP_KT:g} kT: {need}")
    print("  for the mdp files (equal length, same count):")
    for c, name in enumerate(a.components):
        print(f"    {name + '-lambdas':<23} = " + " ".join(f"{x:g}" for x in same[:, c]))
    return EXIT_OK


def build_parser(prog: str = "caterva fep") -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog=prog, description=__doc__.split("\n\n")[0],
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--summarise", type=Path, metavar="DIR", help="combine a finished run and judge it")
    p.add_argument("--optimise", type=Path, metavar="DIR",
                   help="from a finished pilot leg: where its lambda windows should go")
    p.add_argument("--leg", choices=("complex", "solvent"), default="solvent")
    p.add_argument("--rep", type=int, default=1)
    p.add_argument("--ec"); p.add_argument("--organism", default="Homo sapiens")
    p.add_argument("--inhibitor"); p.add_argument("--isoform")
    p.add_argument("--state", choices=("free", "ternary"), default="free")
    p.add_argument("--html", type=Path, help="a saved BRENDA page, instead of fetching one")
    p.add_argument("--complex", type=Path, help="equilibrated, solvated complex (.gro)")
    p.add_argument("--topology", type=Path, help="its topology (.top); local #includes are copied")
    p.add_argument("--ligand", help="the ligand's residue name in the .gro")
    p.add_argument("--ligand-itp", type=Path, help="the ligand's topology (.itp): yours, not generated")
    p.add_argument("--trajectory", type=Path,
                   help="the complex's equilibration (.xtc): restraint anchors are chosen among C-alpha atoms that stay still")
    p.add_argument("--temperature", type=float, help="°C; default: the Ki's assay temperature")
    p.add_argument("--replicas", type=int, default=3)
    p.add_argument("--ns", type=float, default=5.0, help="production per window, ns")
    p.add_argument("--out", type=Path)
    return p


def main(argv: Optional[Sequence[str]] = None, prog: str = "caterva fep") -> int:
    p = build_parser(prog)
    try:
        a = p.parse_args(argv)
    except SystemExit as e:
        return EXIT_USAGE if e.code else EXIT_OK
    if a.summarise:
        return summarise(a.summarise)
    if a.optimise:
        return optimise(a.optimise, a.leg, a.rep)
    return setup(a)


if __name__ == "__main__":
    sys.exit(main())
