"""Kinds `fep.status` and `complex.check`: where a free-energy run stands (owner: sci-structure).

WHAT THE STUDIO DOES NOT DO HERE
--------------------------------
It does not set up or run a binding free-energy calculation. `caterva
complex` (building the complex from your ligand topology) and `caterva fep`
(writing the alchemical legs) take files only you can supply, and running
the legs takes hours to days of GROMACS on a workstation or cluster. The
page says so and shows the commands. What the studio reads is a finished
or half-finished run, as the two commands' own status modes read it.

WHAT IT CALLS
-------------
`caterva fep --summarise DIR` through caterva/fep/__main__.py
`read_summary` (each replica's two legs from Caterva's MBAR on the raw
dhdl files, or `gmx bar`'s log for runs set up before the estimator
existed; the cycle closed with the Boresch correction the setup recorded;
with two or more replicas the mean, its sigma and the verdict against the
measured band, `bind.core.judge`) and `summary_lines` (what it prints).

`caterva complex --check DIR --ligand RES` through caterva/fep/complex.py
`check_pose` (the ligand's heavy-atom RMSD from the crystal pose after
equilibration, symmetry-equivalent poses counted as the same, the worst
frame of npt.xtc when it exists, and the "kept" judgement) and
`pose_lines`. The command accepts --ligand-itp beside --check and ignores
it; the request has no such field (contract.ComplexCheckRequest).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Mapping

from caterva.studio import contract
from caterva.studio.adapters import AdapterOutcome, AdapterSpec, RunContext, cli_parser
from caterva.studio.adapters.md import DIRECTORY_KEYS, computed_value, checked, first_line, user_directory
from caterva.studio.adapters.structure import method_citation

FEP_PROG = "caterva fep"
COMPLEX_PROG = "caterva complex"

COMPLEX_KEYS: Mapping[str, type] = {"directory": str, "ligand": str}


# ---------------------------------------------------------------------------
# fep.status
# ---------------------------------------------------------------------------


def status_argv(request: Mapping[str, Any]) -> List[str]:
    from caterva.fep.__main__ import build_parser

    r = checked(request, DIRECTORY_KEYS, required=("directory",))
    argv = ["--summarise", str(user_directory(r["directory"], "directory"))]
    cli_parser(build_parser, FEP_PROG).parse_args(argv)
    return argv


def _brenda_refs(references: List[str]) -> str:
    return ", ".join(f"BRENDA ref {r}" for r in references)


def _temperature(rec: Mapping[str, Any]) -> contract.SourcedValue:
    """The temperature the legs ran at, with the origin the setup recorded.
    A measured one is the Ki rows' common assay temperature (caterva fep's
    `temperature_for`), cited by the same references."""
    refs = list(rec["target"]["references"])
    if rec.get("temperature_origin") == "measured":
        prov: contract.Provenance = {
            "kind": "measured",
            "citation": {"text": _brenda_refs(refs), "registry": "BRENDA", "url": None},
            "organism": rec["target"]["organism"], "cross_species": False,
            "conditions": {"ph": None, "temperature_c": rec["temperature_k"] - 273.15, "buffer": None,
                           "unreported": []},
            "commentary": None, "scope": [],
            "note": "the assay temperature of the Ki rows behind the target band",
        }
    else:
        prov = contract.chosen("default", "chosen by the setup, not measured; PROVENANCE.md in the run says why")
    return contract.sourced(rec["temperature_k"], "K", prov, label="temperature")


def _verdict(s: Any, computed: contract.SourcedValue) -> contract.BindVerdict:
    v = s.verdict
    inputs = ["computed ΔG°bind", "target band"]
    return {"word": v.word,
            "gap_kcal": computed_value(v.gap_kcal, "kcal/mol", "distance of computed ± 2σ from the band's edge, 0 inside "
                                  "it (bind.core.judge)", inputs, label="gap"),
            "ki_fold": computed_value(v.ki_fold, "", "the same gap as a fold error in Ki (bind.core.judge)", inputs,
                                 label="Ki fold"),
            "detail": v.detail, "computed": computed}


def status_run(request: Mapping[str, Any], ctx: RunContext) -> AdapterOutcome:
    from caterva.fep.__main__ import KJ_PER_KCAL, build_parser, read_summary, summary_lines

    args = cli_parser(build_parser, FEP_PROG).parse_args(status_argv(request))
    d = Path(args.summarise)
    ctx.progress.stage("read", f"Reading each leg's free energy under {d.name}")
    ctx.progress.check_cancelled()
    s, refusal = read_summary(d)
    if s is None:
        return AdapterOutcome(3, None, first_line(refusal), refusal)
    ctx.progress.stage("judge", "Closing the cycle and judging it against the measured band")
    rec, t = s.record, s.record["target"]
    refs = list(t["references"])
    lo, hi = t["band_kcal"]
    band_method = "ΔG = RT ln Ki over the Ki rows that fit the simulated state (bind.core.target)"
    correction = computed_value(rec["restraint"]["correction_kj"] / KJ_PER_KCAL, "kcal/mol",
                           "Boresch standard-state correction for the orientational restraints, "
                           + method_citation("boresch")["text"], ["restraint"], label="restraint correction")
    rows: List[contract.FepReplicaRow] = []
    for r in s.replicas:
        rep = f"rep{r.rep}"
        rows.append({
            "rep": r.rep,
            "complex_kj": computed_value(r.complex_kj, "kJ/mol", r.complex_estimator, [f"{rep} complex"],
                                    label=f"{rep} complex leg"),
            "solvent_kj": computed_value(r.solvent_kj, "kJ/mol", r.solvent_estimator, [f"{rep} solvent"],
                                    label=f"{rep} solvent leg"),
            "dg_kcal": computed_value(r.dg_kcal, "kcal/mol", "ΔG°bind = ΔG_solvent + restraint correction - ΔG_complex",
                                 [f"{rep} complex leg", f"{rep} solvent leg", "restraint correction"],
                                 label=f"{rep} ΔG°bind"),
            "complex_err_kj": computed_value(r.complex_err_kj, "kJ/mol", f"statistical error of the complex leg, {r.complex_estimator}",
                                        [f"{rep} complex"], label=f"{rep} complex leg error"),
            "solvent_err_kj": computed_value(r.solvent_err_kj, "kJ/mol", f"statistical error of the solvent leg, {r.solvent_estimator}",
                                        [f"{rep} solvent"], label=f"{rep} solvent leg error"),
            "complex_estimator": r.complex_estimator,
            "solvent_estimator": r.solvent_estimator,
        })
    computed = None
    sigma = sem = None
    if s.mean is not None:
        names = [f"rep{r.rep} ΔG°bind" for r in s.replicas]
        computed = computed_value(s.mean, "kcal/mol", "mean of the replicas' ΔG°bind", names, label="computed ΔG°bind")
        sigma = computed_value(s.sigma, "kcal/mol", "the larger of the SEM and the propagated BAR error", names,
                          label="σ")
        sem = computed_value(s.sem, "kcal/mol", "standard error of the mean across replicas", names, label="SEM")
    lines = summary_lines(s)
    report = "".join(line + "\n" for line in lines)
    result: contract.FepStatusResult = {
        "compound": t["compound"],
        "organism": t["organism"],
        "temperature_k": _temperature(rec),
        "restraint_correction": correction,
        "replicas": rows,
        "band_low": computed_value(lo, "kcal/mol", band_method, refs, label="band low"),
        "band_high": computed_value(hi, "kcal/mol", band_method, refs, label="band high"),
        "computed": computed,
        "verdict": None if s.verdict is None else _verdict(s, computed),
        "not_a_result": next((line for line in lines if line.startswith("NOT A RESULT")), None),
        "warnings": list(s.warnings),
        "report_text": report,
        "replicas_planned": int(rec.get("replicas", len(rows))),
        "lines": [line for line in s.lines],
        "references": [f"BRENDA ref {r}" for r in refs],
        "caveats": list(t["caveats"]),
        "state": t["state"],
        "sigma": sigma,
        "sem": sem,
    }
    word = s.verdict.word if s.verdict is not None else "not a result"
    summary = f"{t['compound']} -> {t['organism']}: {len(rows)} of {result['replicas_planned']} replicas, {word}"
    return AdapterOutcome(s.code, result, summary)


# ---------------------------------------------------------------------------
# complex.check
# ---------------------------------------------------------------------------


def check_argv(request: Mapping[str, Any]) -> List[str]:
    from caterva.fep.complex import build_parser

    r = checked(request, COMPLEX_KEYS, required=("directory", "ligand"))
    ligand = r["ligand"].strip()
    if not ligand or len(ligand) > 5 or any(ch.isspace() for ch in ligand):
        raise contract.Malformed(f"ligand must be a residue name (at most five characters, no spaces), "
                                 f"not {ligand!r}", field="ligand")
    argv = ["--check", str(user_directory(r["directory"], "directory")), "--ligand", ligand]
    cli_parser(build_parser, COMPLEX_PROG).parse_args(argv)
    return argv


def check_run(request: Mapping[str, Any], ctx: RunContext) -> AdapterOutcome:
    from caterva.fep.complex import POSE_KEPT_NM, build_parser, check_pose, pose_lines

    args = cli_parser(build_parser, COMPLEX_PROG).parse_args(check_argv(request))
    d = Path(args.check)
    ctx.progress.stage("check", f"Superposing npt.gro on the crystal pose of {args.ligand}")
    ctx.progress.check_cancelled()
    try:
        c = check_pose(d, args.ligand)
    except (OSError, ValueError) as e:
        refusal = f"{COMPLEX_PROG}: {e}"
        return AdapterOutcome(3, None, first_line(refusal), refusal)
    if c.series is not None:
        ctx.progress.stage("trajectory", f"Read {len(c.series)} frames of npt.xtc")
    kabsch = method_citation("kabsch")["text"]
    values: Dict[str, contract.SourcedValue] = {
        "ligand_rmsd": computed_value(c.rmsd_nm, "nm", "ligand heavy-atom RMSD from the crystal pose in npt.gro, protein "
                                 f"superposed on its C-alpha atoms ({kabsch}); symmetry-equivalent poses counted "
                                 "as the same pose", ["boxed.gro", "npt.gro"], label="ligand RMSD"),
        "ca_rmsd": computed_value(c.ca_rmsd_nm, "nm", f"protein C-alpha RMSD after superposition ({kabsch})",
                             ["boxed.gro", "npt.gro"], label="C-alpha RMSD"),
        "centroid_shift": computed_value(c.centroid_shift_nm, "nm", "distance the ligand's heavy-atom centroid moved, "
                                    "protein superposed", ["boxed.gro", "npt.gro"], label="centroid shift"),
        "kept_threshold": contract.sourced(POSE_KEPT_NM, "nm", contract.chosen(
            "default", "a pose within this RMSD of the crystal's is kept (caterva complex)"), label="kept within"),
    }
    worst = c.worst
    if worst is not None:
        values["worst_rmsd"] = computed_value(worst[1], "nm", "largest ligand RMSD over the frames of npt.xtc",
                                         ["npt.xtc"], label="worst frame RMSD")
        values["worst_time"] = computed_value(worst[0], "ps", "time of that frame in npt.xtc", ["npt.xtc"],
                                         label="worst frame at")
        values["max_centroid_shift"] = computed_value(max(r[2] for r in c.series), "nm",
                                                 "largest centroid shift over the frames of npt.xtc", ["npt.xtc"],
                                                 label="largest centroid shift")
    report = "".join(line + "\n" for line in pose_lines(c))
    result: contract.ComplexCheckResult = {
        "kept": c.kept, "values": values, "report_text": report, "ligand": c.ligand, "ca_atoms": c.ca_atoms,
        "frames": None if c.series is None else len(c.series),
    }
    summary = f"{c.ligand} in {d.name}: " + ("kept its pose" if c.kept else "left its pose")
    return AdapterOutcome(0 if c.kept else 4, result, summary)


def register(registry) -> None:
    registry.register(AdapterSpec(
        kind="fep.status",
        title="FEP status",
        command="fep",
        needs=(),
        argv=status_argv,
        run=status_run,
        describe=lambda r: f"FEP status of {Path(str(r.get('directory', '?'))).name}",
        cli_prefix=("caterva", "fep"),
    ))
    registry.register(AdapterSpec(
        kind="complex.check",
        title="Check the complex's pose",
        command="complex",
        needs=(),
        argv=check_argv,
        run=check_run,
        describe=lambda r: f"Pose of {r.get('ligand', '?')} in {Path(str(r.get('directory', '?'))).name}",
        cli_prefix=("caterva", "complex"),
    ))


__all__ = ["COMPLEX_PROG", "FEP_PROG", "check_argv", "check_run", "register", "status_argv", "status_run"]
