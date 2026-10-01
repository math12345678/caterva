"""Kinds `md.setup` and `md.summarise`: `caterva md` (owner: sci-structure).

WHAT A SETUP RUN DOES, AND WHAT IT DOES NOT
-------------------------------------------
`md.setup` writes the GROMACS inputs `caterva md --pdb ... --out ...` writes
(the mdp files, run.sh, PROVENANCE.md, caterva-setup.json) into a folder:
the one the request names, or `md-setup` inside the run's directory by default. It runs no
simulation. GROMACS runs them (`bash <folder>/run.sh`), for hours, outside
the studio; the page says so and shows the command. `md.summarise` then
reads the replicas' rmsd.xvg under a finished folder, as `--summarise DIR`
does, and writes CONVERGENCE.md there.

Both go through the command's own pieces (caterva/md/__main__.py): `check`
(the refusals argparse cannot express, raised through `parser.error`, so
a malformed request is a 400 before any run exists), `plan` (the
conditions, from the literature when --subject and --substrate ask for
measured ones), `write`, `written_lines` (what the command prints), and
`summarise_run`. Nothing is recomputed here: the temperature's citation is
the Measurement `plan` kept beside its sentence, never parsed out of it.

WHY THE USER-PATH RULES LIVE HERE
---------------------------------
A folder to write and a finished run to read are the only paths the
structure kinds accept from a request (docs/studio/CONTRACT.md, "User
paths"), and they are checked the same way for prepare, analyze, fep and
complex, so the rules are written once, below, and the other adapters of
this owner import them. Every check is in `argv`, so a path that breaks
one is a 400 naming its field, and nothing is read or written. A request
cannot name a file for the server to send back: these kinds return
structured results and the files they write stay where they were written.

The server calls `argv(request)` before the run's directory exists, so the
default output folder is written as RUN_DIR_PLACEHOLDER + "/md-setup" and
the server puts the run directory's absolute path in its place before it
parses and records the command line (caterva/studio/jobs.py names the same
string). `argv` cannot see the data directory either, so the rule that a
folder the request names is not inside it is checked again by `run`, with
the real directories, before anything is written; a breach found there is
the same Malformed, and the run fails without writing.
"""
from __future__ import annotations

import io
import math
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from caterva.studio import contract
from caterva.studio.adapters import AdapterOutcome, AdapterSpec, RunContext, cli_parser

PROG = "caterva md"

#: Paths longer than this are refused (CONTRACT.md, "User paths").
MAX_PATH_CHARS = 4096

#: What an argv writes where the run's own directory goes (md.setup's
#: default --out, structure's --chimerax). The server replaces it with the
#: run directory's absolute path; it must equal
#: caterva.studio.jobs.RUN_DIR_PLACEHOLDER (owner: core).
RUN_DIR_PLACEHOLDER = "@RUN_DIR@"

#: The default output folder, inside the run's directory.
DEFAULT_OUT = "md-setup"


# ---------------------------------------------------------------------------
# Requests and user paths, shared by this owner's adapters
# ---------------------------------------------------------------------------


def checked(request: Mapping[str, Any], keys: Mapping[str, type], required: Sequence[str] = ()) -> Dict[str, Any]:
    """The request as a dict, refused (contract.Malformed, naming the field)
    when it has a key the kind does not take, lacks a required one, or has
    a value of the wrong JSON type. A bool is not a number here, and an
    integer is accepted where a float is."""
    if not isinstance(request, Mapping):
        raise contract.Malformed("the request must be a JSON object")
    for key in request:
        if key not in keys:
            raise contract.Malformed(f"{key!r} is not a key this kind takes; it takes {', '.join(sorted(keys))}",
                                     field=str(key))
    for key in required:
        if key not in request or request[key] is None:
            raise contract.Malformed(f"{key!r} is required", field=key)
    out: Dict[str, Any] = {}
    for key, value in request.items():
        want = keys[key]
        if value is None:
            raise contract.Malformed(f"{key!r} may be left out but not null", field=key)
        if want is bool:
            ok = isinstance(value, bool)
        elif want is int:
            ok = isinstance(value, int) and not isinstance(value, bool)
        elif want is float:
            ok = isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
            value = float(value) if ok else value
        else:
            ok = isinstance(value, want)
        if not ok:
            raise contract.Malformed(f"{key!r} must be {_json_type(want)}", field=key)
        out[key] = value
    return out


def _json_type(t: type) -> str:
    return {bool: "true or false", int: "a whole number", float: "a finite number", str: "a string"}.get(t, t.__name__)


def _path_text(value: Any, field: str) -> Path:
    if not isinstance(value, str) or not value:
        raise contract.Malformed(f"{field} must be a non-empty string: an absolute path", field=field)
    if "\x00" in value:
        raise contract.Malformed(f"{field} contains a NUL character", field=field)
    if len(value) > MAX_PATH_CHARS:
        raise contract.Malformed(f"{field} is longer than {MAX_PATH_CHARS} characters", field=field)
    path = Path(value)
    if not path.is_absolute():
        raise contract.Malformed(f"{field} must be an absolute path, not {value!r}", field=field)
    return path


def user_file(value: Any, field: str, suffixes: Sequence[str]) -> Path:
    """An input file named by the request: absolute, existing (symlinks
    followed once, the resolved path returned), a regular file, with one
    of `suffixes`."""
    path = _path_text(value, field)
    try:
        resolved = path.resolve(strict=True)
    except (OSError, RuntimeError):
        raise contract.Malformed(f"{field}: {value} does not exist", field=field) from None
    if not resolved.is_file():
        raise contract.Malformed(f"{field}: {value} is not a regular file", field=field)
    if resolved.suffix.lower() not in suffixes:
        raise contract.Malformed(f"{field}: {value} is not a {' or '.join(suffixes)} file", field=field)
    return resolved


def user_directory(value: Any, field: str) -> Path:
    """An input directory named by the request: absolute, existing, a
    directory. Whether it is the right kind of directory (a finished md
    run, a caterva fep setup) is the command's decision and its refusal."""
    path = _path_text(value, field)
    try:
        resolved = path.resolve(strict=True)
    except (OSError, RuntimeError):
        raise contract.Malformed(f"{field}: {value} does not exist", field=field) from None
    if not resolved.is_dir():
        raise contract.Malformed(f"{field}: {value} is not a directory", field=field)
    return resolved


def output_directory(value: Any, field: str, data_dir: Optional[Path] = None) -> Path:
    """A folder to write into: absolute; its parent exists (resolved
    strictly); it does not exist yet, or is an empty directory, or holds a
    previous `caterva md` setup (its PROVENANCE.md); and it is not inside
    the studio's data directory, whose layout the server owns."""
    path = _path_text(value, field)
    if not path.name:
        raise contract.Malformed(f"{field}: {value} names no folder", field=field)
    try:
        parent = path.parent.resolve(strict=True)
    except (OSError, RuntimeError):
        raise contract.Malformed(f"{field}: the folder {path.parent} does not exist", field=field) from None
    if not parent.is_dir():
        raise contract.Malformed(f"{field}: {path.parent} is not a directory", field=field)
    target = parent / path.name
    if target.exists() or target.is_symlink():
        try:
            target = target.resolve(strict=True)
        except (OSError, RuntimeError):
            raise contract.Malformed(f"{field}: {value} is a link to nothing", field=field) from None
        if not target.is_dir():
            raise contract.Malformed(f"{field}: {value} exists and is not a directory", field=field)
        if any(target.iterdir()) and not (target / "PROVENANCE.md").is_file():
            raise contract.Malformed(
                f"{field}: {value} holds files and no previous `caterva md` setup (no PROVENANCE.md); "
                "choose an empty or new folder", field=field)
    if data_dir is not None and _inside(target, data_dir):
        raise contract.Malformed(f"{field}: {value} is inside the studio's workspace ({data_dir}); "
                                 "leave it out to write into the run's own folder", field=field)
    return target


def _inside(path: Path, directory: Path) -> bool:
    try:
        path.relative_to(directory.resolve())
    except ValueError:
        return False
    return True


def text_of(stream: io.StringIO) -> str:
    return stream.getvalue()


def first_line(text: Optional[str]) -> str:
    return (text or "").strip().splitlines()[0] if (text or "").strip() else ""


# ---------------------------------------------------------------------------
# md.setup
# ---------------------------------------------------------------------------

SETUP_KEYS: Mapping[str, type] = {
    "pdb": str, "chain": str, "out": str, "subject": str, "organism": str, "substrate": str,
    "temperature_k": float, "ph": float, "ns": float, "ionic_strength_m": float, "seed": int, "replicas": int,
}
#: request key -> the command's flag, where they differ in more than dashes.
SETUP_FLAGS = {"temperature_k": "--temperature", "ionic_strength_m": "--ionic-strength"}


def _default_out(run_dir: Optional[Path]) -> str:
    return str(run_dir / DEFAULT_OUT) if run_dir is not None else f"{RUN_DIR_PLACEHOLDER}/{DEFAULT_OUT}"


def setup_argv(request: Mapping[str, Any], *, run_dir: Optional[Path] = None,
               data_dir: Optional[Path] = None) -> List[str]:
    from caterva.md.__main__ import build_parser, check

    r = checked(request, SETUP_KEYS, required=("pdb",))
    out = str(output_directory(r["out"], "out", data_dir)) if "out" in r else _default_out(run_dir)
    argv = ["--pdb", r["pdb"]]
    for key in ("chain", "subject", "organism", "substrate", "temperature_k", "ph", "ns", "ionic_strength_m",
                "seed", "replicas"):
        if key in r:
            argv += [SETUP_FLAGS.get(key, "--" + key.replace("_", "-")), _arg(r[key])]
    argv += ["--out", out]
    parser = cli_parser(build_parser, PROG)
    check(parser, parser.parse_args(argv))
    return argv


def _arg(value: Any) -> str:
    return repr(value) if isinstance(value, float) else str(value)


def _setup_describe(request: Mapping[str, Any]) -> str:
    what = f"MD setup for PDB {str(request.get('pdb', '?')).upper()}"
    if request.get("chain"):
        what += f" chain {request['chain']}"
    if request.get("subject"):
        what += f", conditions from EC {request['subject']}"
    return what


def _brenda_url(measurement: Any, ec: Optional[str]) -> Optional[str]:
    source = str(getattr(measurement, "source", "") or "")
    if ec and source.lower().startswith("brenda"):
        return f"https://www.brenda-enzymes.org/enzyme.php?ecno={ec}"
    return None


def _condition(value: Optional[float], unit: str, measurement: Any, sentence: str, by_user: bool,
               ec: Optional[str], label: str) -> Optional[contract.SourcedValue]:
    """A temperature or pH of the setup, with the provenance the setup's own
    record gives it: the cited constant's assay, the person, or the default."""
    if value is None:
        return None
    if measurement is not None:
        prov = contract.measured_from_measurement(measurement, url=_brenda_url(measurement, ec))
        prov["note"] = sentence
    elif by_user:
        prov = contract.chosen("user", sentence)
    else:
        prov = contract.chosen("default", sentence)
    return contract.sourced(value, unit, prov, label=label)


def _parameter(setup: Any, name: str) -> Any:
    return next(p for p in setup.parameters if p.name == name)


def setup_run(request: Mapping[str, Any], ctx: RunContext) -> AdapterOutcome:
    from caterva.md.__main__ import build_parser, plan, write, written_lines

    argv = setup_argv(request, run_dir=ctx.run_dir, data_dir=ctx.data_dir)
    args = cli_parser(build_parser, PROG).parse_args(argv)
    ctx.progress.stage("conditions", f"Taking the conditions from the measured kinetics of EC {args.subject}"
                       if args.subject else "Using the stated default conditions (no kinetics named)")
    ctx.progress.check_cancelled()
    printed = io.StringIO()
    planned = plan(args, out=printed)
    ctx.progress.check_cancelled()
    out = Path(args.out)
    ctx.progress.stage("write", f"Writing the GROMACS setup into {out}")
    names = write(planned.setup, out)
    for line in written_lines(planned, out, PROG):
        print(line, file=printed)
    setup, c = planned.setup, planned.setup.conditions
    ns_row, ionic_row = _parameter(setup, "production length"), _parameter(setup, "ionic strength")
    result: contract.MdSetupResult = {
        "out_dir": str(out),
        "pdb": setup.pdb_id,
        "chain": setup.chain,
        "temperature": _condition(c.temperature_k, "K", c.temperature_measurement, c.temperature_source,
                                  args.temperature is not None, args.subject, "temperature"),
        "ph": _condition(c.ph, "", c.ph_measurement, c.ph_source, args.ph is not None, args.subject, "pH"),
        "parameters": [{"name": p.name, "value": p.value, "origin": p.origin, "source": p.source}
                       for p in setup.parameters],
        "files": names,
        "note": planned.note,
        "report_text": text_of(printed),
        "ns": contract.sourced(setup.ns, "ns", contract.chosen("user" if "ns" in request else "default",
                                                               ns_row.source), label="production length"),
        "ionic_strength": contract.sourced(setup.ionic_strength_m, "M",
                                           contract.chosen("user" if "ionic_strength_m" in request else "default",
                                                           ionic_row.source), label="ionic strength (NaCl)"),
        "replicas": setup.replicas,
        "seeds": setup.seeds(),
        "provenance_markdown": (out / "PROVENANCE.md").read_text(encoding="utf-8"),
    }
    summary = (f"PDB {setup.pdb_id}{', chain ' + setup.chain if setup.chain else ''}: {len(names)} files written "
               f"to {out}, {c.temperature_k:.2f} K, {setup.replicas} replica{'s' if setup.replicas > 1 else ''}")
    refusal = planned.note if planned.exit_code == 3 else None
    return AdapterOutcome(planned.exit_code, result, summary, refusal)


# ---------------------------------------------------------------------------
# md.summarise
# ---------------------------------------------------------------------------

DIRECTORY_KEYS: Mapping[str, type] = {"directory": str}


def summarise_argv(request: Mapping[str, Any], **_: Any) -> List[str]:
    from caterva.md.__main__ import build_parser, check

    r = checked(request, DIRECTORY_KEYS, required=("directory",))
    argv = ["--summarise", str(user_directory(r["directory"], "directory"))]
    parser = cli_parser(build_parser, PROG)
    check(parser, parser.parse_args(argv))
    return argv


def computed_value(value: float, unit: str, method: str, inputs: Sequence[str] = (), label: Optional[str] = None,
              note: Optional[str] = None) -> contract.SourcedValue:
    return contract.sourced(value, unit, contract.computed(method, inputs, note), label=label)


def convergence_values(s: Any) -> Tuple[List[contract.ReplicaRow], Dict[str, Any]]:
    """A convergence.Summary's numbers, each with how it was computed, in the
    library's own terms (caterva/md/convergence.py)."""
    from caterva.md.convergence import CONFIDENCE, DISCARD

    kept_method = f"mean over the frames kept, the first {DISCARD:.0%} of the run discarded as relaxation (a choice)"
    error_method = ("block-averaged standard error of that mean, Flyvbjerg & Petersen (1989) J. Chem. Phys. "
                    "91:461, doi:10.1063/1.457480")
    rows: List[contract.ReplicaRow] = []
    for r in s.replicas:
        verdict = ("error plateaued" if r.result.plateaued
                   else "no error estimate" if not r.result.levels else "error still rising")
        rows.append({
            "name": r.name,
            "mean": computed_value(r.result.mean, s.unit, kept_method, [r.name], label=f"{r.name} mean"),
            "error": computed_value(r.result.sem, s.unit, error_method, [r.name], label=f"{r.name} error"),
            "verdict": verdict,
            "frames": r.frames,
            "kept": r.kept,
            "plateaued": r.result.plateaued,
            "effective_samples": computed_value(r.result.effective_samples, "",
                                           "n (naive error / block-averaged error)^2: independent frames the "
                                           "run is worth", [r.name], label="independent samples"),
        })
    names = [r.name for r in s.replicas]
    extra: Dict[str, Any] = {
        "mean": computed_value(s.mean, s.unit, "mean of the replica means", names, label="mean"),
        "spread": None if s.spread is None else computed_value(s.spread, s.unit, "SD of the replica means", names,
                                                           label="spread"),
        "ci95": None if s.spread is None else computed_value(
            s.ci95, s.unit, f"half-width of the {CONFIDENCE:.0%} confidence interval of the mean, Student's t with "
            f"{len(s.replicas) - 1} degree(s) of freedom", names, label="95% CI"),
    }
    return rows, extra


def summarise_run(request: Mapping[str, Any], ctx: RunContext) -> AdapterOutcome:
    from caterva.md.__main__ import build_parser, summarise_run as summarise_directory

    args = cli_parser(build_parser, PROG).parse_args(summarise_argv(request))
    directory = Path(args.summarise)
    ctx.progress.stage("read", f"Reading each replica's rmsd.xvg under {directory}")
    ctx.progress.check_cancelled()
    out, err = io.StringIO(), io.StringIO()
    done = summarise_directory(directory, out, err)
    if done.summary is None:
        return AdapterOutcome(3, None, first_line(done.refusal), done.refusal)
    ctx.progress.stage("summarise", "Block-averaging each replica and comparing them")
    s = done.summary
    rows, extra = convergence_values(s)
    result: contract.ConvergenceResult = {
        "quantity": s.quantity,
        "unit": s.unit,
        "verdict": s.verdict,
        "replicas": rows,
        "report_markdown": text_of(out),
        "summary": contract.jsonable(s),
        "mean": extra["mean"],
        "spread": extra["spread"],
        "ci95": extra["ci95"],
        "reasons": list(s.reasons),
        "written": str(done.written) if done.written else None,
    }
    summary = f"{s.quantity}: {s.verdict}, {len(s.replicas)} replica{'s' if len(s.replicas) != 1 else ''}"
    return AdapterOutcome(done.code, result, summary)


def _setup_paths(request: Mapping[str, Any], data_dir: Path) -> None:
    """A user `out` must not be inside the studio's workspace (section 15)."""
    if "out" in request:
        output_directory(request["out"], "out", data_dir)


def _directory_describe(what: str) -> Any:
    def describe(request: Mapping[str, Any]) -> str:
        return f"{what} {Path(str(request.get('directory', '?'))).name}"
    return describe


def register(registry) -> None:
    registry.register(AdapterSpec(
        kind="md.setup",
        title="Write a GROMACS setup",
        command="md",
        needs=("network", "literature"),
        argv=setup_argv,
        run=setup_run,
        describe=_setup_describe,
        cli_prefix=("caterva", "md"),
        # With --subject the conditions come from a compose search, which
        # builds a model through the simulation engine.
        serial=True,
        needs_for=lambda request: ("network", "literature") if request.get("subject") else (),
        check_paths=_setup_paths,
    ))
    registry.register(AdapterSpec(
        kind="md.summarise",
        title="Summarise replicas",
        command="md",
        needs=(),
        argv=summarise_argv,
        run=summarise_run,
        describe=_directory_describe("Convergence of"),
        cli_prefix=("caterva", "md"),
    ))


__all__ = ["DEFAULT_OUT", "DIRECTORY_KEYS", "PROG", "RUN_DIR_PLACEHOLDER", "checked", "computed_value",
           "convergence_values", "first_line", "output_directory", "register", "setup_argv", "setup_run",
           "summarise_argv", "summarise_run", "user_directory", "user_file"]
