"""Kind `compose`: `caterva compose DESCRIPTION [...]`, as a run (owner: sci-kinetics).

WHY IT CALLS `compose_report` AND NOT THE PIPELINE PIECES
---------------------------------------------------------
`caterva compose` is not one library call. It normalises the organism,
composes, searches the literature when a subject is named, runs the two
checks the verdict reads (validate, robustness) BEFORE the dossier, prints
the dossier, runs the analysis sections, counts the refusals on stderr and
prints the footer, and the exit code comes out of that order. An adapter
that re-assembled the steps would be a second copy of that order, and the
first reordering in the CLI (there have been two: the verdict once
contradicted its own sections) would make the studio's verdict disagree
with the terminal's. So `caterva/compose/__main__.py` exposes the whole run
as `compose_report(args, stream, err, progress)`, `main` calls it with the
terminal's streams, and this module calls it with two string buffers. What
the terminal prints is `report_markdown`, byte for byte, and every
structured field below is read from the object that text was printed from:
the dossier's stability report, trajectory, influence ranking, sweeps and
verdict, and each section's own report objects (`SectionRecord.data`).

THE EXPORTS
-----------
The CLI writes exports in a separate run (`--export` refuses the analysis
flags, because it owns stdout). The studio writes all four from the one
searched model, through the same two functions `--export` uses
(`provenanced_for_export`, `export_texts`), so each artefact is byte for
byte what `caterva compose ... --export FORMAT` prints, and a format that
cannot be written (no SBML toolchain) is recorded as refused with the
exporter's own message. The markdown report is an artefact too.

WHERE A NUMBER'S CITATION COMES FROM
------------------------------------
`export.provenance_of` decides every number's origin and
`contract.from_parameter_origin` transcribes it. A measured value's
citation text is the Measurement's, verbatim ("BRENDA ref 286469"). The
search behind it is `agents.scouts.brenda_resolver`, whose only found
outcomes are BRENDA's (`agents.adapters.FOUND_SOURCES`), so a value the
search resolved (`Measurement.source == "literature"`) is marked registry
BRENDA, its reference is read with compose's own rule for which row a
Measurement names (`ki_mode._reference`, the one `narrowed` and `ki_mode`
use), and its link is the literature layer's `brenda_reference_url`: the
enzyme page the row was read from, because BRENDA has no page per
reference. Nothing here parses a registry or builds a link of its own.

A placeholder's reason is the resolver's own words when the search left
them (`ComposedModel.not_found`), with the origin's sentence as its note;
otherwise the origin's sentence, which the exports print too.

WHAT IS REFUSED
---------------
`--export`, `--antimony` and `--shapes` are never produced (exports are
artefacts; the shapes are an endpoint). A section's report object that
holds code (a design observation's evaluator) is sent without that field,
because a function is how a number is computed, not a number. A stochastic
trajectory longer than contract.SERIES_ROW_LIMIT rows is sent as every
n-th row plus the last, with `rows` and `every` saying so: the rows sent
are rows the run held, never interpolated, and the full run is the CLI's.
"""
from __future__ import annotations

import dataclasses
import inspect
import io
from typing import Any, Dict, List, Mapping, Optional, Tuple

from caterva.studio import contract
from caterva.studio.adapters import (
    AdapterOutcome, AdapterSpec, Artifact, EndpointRequest, RunContext, cli_parser,
)

KIND = "compose"
PROG = "caterva compose"

#: Artefact name, media type and description per export format.
EXPORT_ARTIFACTS: Mapping[str, Tuple[str, str, str]] = {
    "sbml": ("model.xml", "application/xml",
             "SBML Level 3, every value's origin in its notes (caterva compose --export sbml)"),
    "antimony": ("model.ant", "text/plain; charset=utf-8",
                 "Antimony source, every value's origin beside it (caterva compose --export antimony)"),
    "csv": ("parameters.csv", "text/csv; charset=utf-8",
            "every number, its origin and its citation (caterva compose --export csv)"),
    "methods": ("methods.md", "text/markdown; charset=utf-8",
                "a methods paragraph grouped by origin (caterva compose --export methods)"),
}
REPORT_ARTIFACT = ("report.md", "text/markdown; charset=utf-8",
                   "the report caterva compose prints for this request")

_STRINGS = ("subject", "organism", "substrate", "inhibitor", "product", "isoform", "rank_against")
_FLAGS = ("any_mode", "no_analysis", "no_simulate", "no_ranking")
_ANALYSIS_FLAGS = ("scale", "predictions", "crnt", "reduction", "identifiability",
                   "design", "validate", "screen")
_REQUEST_KEYS = frozenset(("description", "compounds", "sweep", "analyses") + _STRINGS + _FLAGS)
_ANALYSIS_KEYS = frozenset(_ANALYSIS_FLAGS + ("knockout", "overexpress", "robustness", "stochastic"))


# ---------------------------------------------------------------------------
# Request -> argv
# ---------------------------------------------------------------------------


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _string(request: Mapping[str, Any], key: str, where: str = "") -> Optional[str]:
    value = request.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise contract.Malformed(f"{where}{key} must be a string", field=f"{where}{key}")
    return value


def _flag(value: Any, name: str) -> bool:
    if value is None:
        return False
    if not isinstance(value, bool):
        raise contract.Malformed(f"{name} must be true or false", field=name)
    return value


def _option(flag: str, value: str) -> List[str]:
    """`--flag value`, or `--flag=value` when the value starts with a dash
    (argparse would read `--subject -x` as two flags)."""
    return [f"{flag}={value}"] if value.startswith("-") else [flag, value]


def _number(value: Any) -> str:
    """A JSON number as the CLI would receive it: repr, which float()
    reads back to the same float."""
    return repr(value) if isinstance(value, float) else str(int(value))


def _unknown(keys: Any, allowed: frozenset, where: str) -> None:
    for key in keys:
        if key not in allowed:
            raise contract.Malformed(f"{where}{key} is not a compose request key", field=f"{where}{key}")


def argv_of(request: Mapping[str, Any]) -> List[str]:
    """The argv `caterva compose` would receive for this request.

    Only the mapping of CONTRACT.md section 13: every key one flag, except
    compounds (repeated --compound PORT=NAME, in key order), sweep, and the
    analyses. The CLI's own parser and checks run over it in `argv`.
    """
    if not isinstance(request, Mapping):
        raise contract.Malformed("a compose request is a JSON object")
    _unknown(request, _REQUEST_KEYS, "")
    description = request.get("description")
    if not isinstance(description, str) or not description.strip():
        raise contract.Malformed("description is required: the mechanism to build, "
                                 "e.g. 'Michaelis Menten'", field="description")
    out: List[str] = []
    for key in _STRINGS:
        value = _string(request, key)
        if value is not None:
            out += _option("--" + key.replace("_", "-"), value)
    for key in _FLAGS:
        if _flag(request.get(key), key):
            out.append("--" + key.replace("_", "-"))

    compounds = request.get("compounds")
    if compounds is not None:
        if not isinstance(compounds, Mapping):
            raise contract.Malformed("compounds maps a port to a compound name", field="compounds")
        for port, name in compounds.items():
            if (not isinstance(name, str) or not name.strip() or not str(port).strip()
                    or "=" in str(port)):
                raise contract.Malformed(
                    f"compounds.{port}: a port name without '=' and a compound name are both needed",
                    field=f"compounds.{port}")
            out += _option("--compound", f"{port}={name}")

    sweep = request.get("sweep")
    if sweep is not None:
        if not isinstance(sweep, Mapping):
            raise contract.Malformed("sweep is an object with parameters", field="sweep")
        _unknown(sweep, frozenset(("parameters", "low", "high", "steps")), "sweep.")
        parameters = sweep.get("parameters")
        if (not isinstance(parameters, list) or not parameters
                or not all(isinstance(p, str) and p for p in parameters)):
            raise contract.Malformed("sweep.parameters is a list of parameter names",
                                     field="sweep.parameters")
        for name in parameters:
            out += _option("--sweep", name)
        for key, flag in (("low", "--sweep-from"), ("high", "--sweep-to")):
            if sweep.get(key) is not None:
                if not _is_number(sweep[key]):
                    raise contract.Malformed(f"sweep.{key} must be a number", field=f"sweep.{key}")
                out += _option(flag, _number(float(sweep[key])))
        if sweep.get("steps") is not None:
            if not isinstance(sweep["steps"], int) or isinstance(sweep["steps"], bool):
                raise contract.Malformed("sweep.steps must be an integer", field="sweep.steps")
            out += _option("--sweep-steps", _number(sweep["steps"]))

    analyses = request.get("analyses")
    if analyses is not None:
        if not isinstance(analyses, Mapping):
            raise contract.Malformed("analyses is an object of flags", field="analyses")
        _unknown(analyses, _ANALYSIS_KEYS, "analyses.")
        for key in _ANALYSIS_FLAGS:
            if _flag(analyses.get(key), f"analyses.{key}"):
                out.append("--" + key)
        for key in ("knockout", "overexpress"):
            names = analyses.get(key)
            if names is None:
                continue
            if not isinstance(names, list) or not all(isinstance(n, str) and n for n in names):
                raise contract.Malformed(f"analyses.{key} is a list of species",
                                         field=f"analyses.{key}")
            for name in names:
                out += _option("--" + key, name)
        robustness = analyses.get("robustness")
        if robustness is not None:
            if not isinstance(robustness, Mapping) or "samples" not in robustness:
                raise contract.Malformed("analyses.robustness is {samples: N or null}",
                                         field="analyses.robustness")
            _unknown(robustness, frozenset(("samples",)), "analyses.robustness.")
            samples = robustness["samples"]
            if samples is None:
                out.append("--robustness")
            elif isinstance(samples, int) and not isinstance(samples, bool):
                out += _option("--robustness", _number(samples))
            else:
                raise contract.Malformed("analyses.robustness.samples must be an integer or null",
                                         field="analyses.robustness.samples")
        stochastic = analyses.get("stochastic")
        if stochastic is not None:
            if not isinstance(stochastic, Mapping) or not _is_number(stochastic.get("volume_l")):
                raise contract.Malformed("analyses.stochastic needs volume_l, in litres",
                                         field="analyses.stochastic.volume_l")
            _unknown(stochastic, frozenset(("volume_l", "end_s", "seed")), "analyses.stochastic.")
            out += _option("--stochastic", _number(float(stochastic["volume_l"])))
            if stochastic.get("end_s") is not None:
                if not _is_number(stochastic["end_s"]):
                    raise contract.Malformed("analyses.stochastic.end_s must be a number",
                                             field="analyses.stochastic.end_s")
                out += _option("--stochastic-end", _number(float(stochastic["end_s"])))
            if stochastic.get("seed") is not None:
                seed = stochastic["seed"]
                if not isinstance(seed, int) or isinstance(seed, bool):
                    raise contract.Malformed("analyses.stochastic.seed must be an integer",
                                             field="analyses.stochastic.seed")
                out += _option("--stochastic-seed", _number(seed))

    # The positional first, so a bare `--robustness` (nargs '?') cannot take
    # it as its sample count; behind `--` at the end when it could be read
    # as a flag.
    return out + ["--", description] if description.startswith("-") else [description] + out


def _parsed(argv: List[str]) -> Any:
    from caterva.compose.__main__ import build_parser, check_request

    parser = cli_parser(build_parser, PROG)
    args = parser.parse_args(argv)
    check_request(parser, args)
    return args


def argv(request: Mapping[str, Any]) -> List[str]:
    """The argv, after the CLI's own parser and its post-parse checks have
    accepted it; a refusal from either is contract.Malformed with the
    CLI's words."""
    out = argv_of(request)
    _parsed(out)
    return out


def describe(request: Mapping[str, Any]) -> str:
    parts = [str(request.get("description", "")).strip()]
    for key, label in (("subject", "EC " if _looks_like_ec(request.get("subject")) else ""),
                       ("organism", ""), ("substrate", ""), ("inhibitor", "inhibitor ")):
        value = request.get(key)
        if isinstance(value, str) and value.strip():
            parts.append(label + value.strip())
    return ", ".join(p for p in parts if p)


def _looks_like_ec(value: Any) -> bool:
    return isinstance(value, str) and value.strip()[:1].isdigit()


# ---------------------------------------------------------------------------
# The run
# ---------------------------------------------------------------------------


def run(request: Mapping[str, Any], ctx: RunContext) -> AdapterOutcome:
    from caterva.compose.__main__ import (
        EXPORT_FORMATS, compose_report, export_texts, provenanced_for_export,
    )
    from caterva.compose.export import ExportRefused
    from caterva.compose.grammar import UnrecognisedShape
    from caterva.compose.organisms import normalise_organism

    args = _parsed(argv_of(request))
    args.organism, organism_note = normalise_organism(args.organism)
    out, err = io.StringIO(), io.StringIO()
    try:
        composed = compose_report(args, organism_note=organism_note, stream=out, err=err,
                                  progress=ctx.progress)
    except UnrecognisedShape as exc:
        # What main prints to stderr, without print's newline. Nothing was
        # built, so there is no result: the page shows this reason.
        reason = f"Not built.\n\n{exc}"
        return AdapterOutcome(exit_code=3, result=None, summary=_first_line(str(exc)),
                              refusal=reason)
    stderr = err.getvalue()
    for line in stderr.splitlines():
        if line.strip():
            ctx.progress.log(line)

    ctx.progress.check_cancelled()
    ctx.progress.stage("exports", "Writing the SBML, Antimony, CSV and methods exports", None)
    provenanced = provenanced_for_export(composed.model)
    try:
        texts = export_texts(provenanced, EXPORT_FORMATS)
    except ExportRefused as exc:  # export_texts refuses per format; this is belt only
        texts = {fmt: (None, str(exc)) for fmt in EXPORT_FORMATS}

    markdown = out.getvalue()
    artifacts: List[Artifact] = [Artifact(REPORT_ARTIFACT[0], markdown.encode("utf-8"),
                                          REPORT_ARTIFACT[1], REPORT_ARTIFACT[2])]
    exports: Dict[str, contract.ExportInfo] = {}
    for fmt in EXPORT_FORMATS:
        text, refused = texts[fmt]
        name, media, description = EXPORT_ARTIFACTS[fmt]
        if text is None:
            exports[fmt] = {"available": False, "artifact": None, "refused": refused}
            continue
        # print() adds the newline: the artefact is the file `> model.xml` writes.
        artifacts.append(Artifact(name, (text + "\n").encode("utf-8"), media, description))
        exports[fmt] = {"available": True, "artifact": name, "refused": None}

    result = compose_result(composed, provenanced, markdown=markdown, exports=exports,
                            subject=args.subject)
    code = composed.code
    name_refusal = None
    if code == 3:
        refusal = stderr.rstrip("\n")
        summary = _first_line(refusal)
        if composed.name_refusal is not None:
            from caterva.enzymes.policy import refusal_view

            name_refusal = refusal_view(composed.name_refusal)
    else:
        refusal = None
        verdict = result["verdict"]
        summary = _first_line(verdict["text"]) if verdict else _first_line(markdown)
    return AdapterOutcome(exit_code=code, result=result, summary=summary, refusal=refusal,
                          artifacts=tuple(artifacts), name_refusal=name_refusal)


def _first_line(text: str) -> str:
    for line in text.splitlines():
        if line.strip():
            return line.strip().lstrip("# ").strip()
    return ""


# ---------------------------------------------------------------------------
# Serialising what the run printed from
# ---------------------------------------------------------------------------


def compose_result(composed: Any, provenanced: Any, *, markdown: str,
                   exports: Mapping[str, contract.ExportInfo],
                   subject: Optional[str]) -> contract.ComposeResult:
    """The ComposeResult for one `compose_report` run: every field read from
    the object the markdown was printed from."""
    model = composed.model
    report = composed.dossier
    return {
        "query": model.query,
        "recognition": {"rule": model.recognition.rule, "reading": model.recognition.reading},
        "model": model_structure(model, provenanced),
        "search": search_summary(composed, subject),
        "verdict": verdict_view(report.verdict),
        "stability": stability_view(report.stability),
        "trajectory": trajectory_view(report.trajectory),
        "sensitivity": sensitivity_view(report.sensitivity),
        "sweeps": [contract.jsonable(sweep) for sweep in report.sweeps],
        "sections": [section_view(record) for record in composed.sections.records],
        "notes": [str(note) for note in model.recognition.composition.notes],
        "report_markdown": markdown,
        "exports": dict(exports),
    }


def model_structure(model: Any, provenanced: Any) -> contract.ModelStructure:
    from caterva.compose.pipeline import _conservation_laws, _unconserved_species

    laws = _conservation_laws(model.network)
    values = {origin.identifier: parameter_value(origin, model) for origin in provenanced.origins}
    return {
        "species": [
            {"id": origin.identifier, "initial": values[origin.identifier]}
            for origin in provenanced.origins if origin.role != "parameter"
        ],
        "reactions": [{"id": r.id, "rate_law": str(r.rate_law)} for r in model.network.reactions],
        "parameters": [values[o.identifier] for o in provenanced.origins if o.role == "parameter"],
        "conservation_laws": list(laws),
        "unconserved": list(_unconserved_species(model.network, laws)),
        "concentration_unit": str(provenanced.concentration_unit),
        "motifs": [{"name": name, "basis": basis, "copies": copies}
                   for name, basis, copies in provenanced.motifs_used],
    }


def parameter_value(origin: Any, model: Any) -> contract.SourcedValue:
    """One number of the model, with the origin `export.provenance_of`
    decided (see the module docstring for the citation fields)."""
    registry = url = reference = None
    measurement = getattr(origin, "measurement", None)
    if measurement is not None and getattr(measurement, "source", None) == "literature":
        from caterva.checkout import literature_module
        from caterva.compose.ki_mode import _reference

        reference = _reference(measurement)
        registry = "BRENDA"
        url = literature_module("citation").brenda_reference_url(reference, model.ec_number)
    not_found = dict(getattr(model, "not_found", {}) or {})
    reason = not_found.get(origin.identifier) if origin.origin == "placeholder" else None
    value = contract.from_parameter_origin(origin, reason=reason, registry=registry, url=url)
    if reference is not None:
        value["provenance"]["citation"]["reference_id"] = reference
    if reason is not None:
        value["provenance"]["note"] = origin.sentence()
    return value


def search_summary(composed: Any, subject: Optional[str]) -> contract.SearchSummary:
    model = composed.model
    return {
        "asked": bool(subject),
        "refused": bool(composed.search_refused),
        "note": composed.search_note,
        "subject": subject,
        "ec": model.ec_number,
        "organism": model.organism,
        "substrate": model.substrate,
        "isoform": model.isoform,
        "compounds": {str(k): str(v) for k, v in (model.compounds or {}).items()},
        "measured": len(model.measured),
        "placeholders": len(model.unmeasured),
    }


def verdict_view(verdict: Any) -> Optional[contract.VerdictView]:
    if verdict is None:
        return None
    from caterva.compose.verdict import LICENCE

    return {
        "verdict": verdict.verdict,
        "licence": LICENCE[verdict.verdict],
        "behaviour": verdict.behaviour,
        "conclusion": verdict.conclusion,
        "concerns": [dict({"source": c.source, "severity": c.severity, "detail": c.detail,
                           "remedy": c.remedy}, **({"qualifier": c.qualifier} if c.qualifier else {}))
                     for c in verdict.concerns],
        "next_step": verdict.next_step(),
        "consulted": {str(k): str(v) for k, v in verdict.consulted.items()},
        "unavailable": {str(k): str(v) for k, v in verdict.unavailable.items()},
        "text": verdict.summary(),
    }


def _complex(value: complex) -> contract.ComplexNumber:
    number = contract.jsonable(complex(value))
    return {"re": number["re"], "im": number["im"]}


def stability_view(stability: Any) -> Optional[contract.StabilityView]:
    if stability is None:
        return None
    return {
        "starts_tried": int(stability.starts_tried),
        "species": list(stability.species),
        "notes": [str(n) for n in stability.notes],
        "fixed_points": [
            {
                "state": {str(k): contract.jsonable(v) for k, v in point.state.items()},
                "residual": contract.jsonable(point.residual),
                "eigenvalues": [_complex(e) for e in point.eigenvalues],
                "classification": point.classification,
                "physical": bool(point.physical),
                "stable": bool(point.stable),
                "oscillatory": bool(point.oscillatory),
                "slowest_timescale": contract.jsonable(point.slowest_timescale),
                "description": point.describe(),
            }
            for point in stability.fixed_points
        ],
        "text": stability.summary(),
    }


def trajectory_view(trajectory: Any) -> Optional[contract.TrajectoryView]:
    if trajectory is None:
        return None
    return {
        "times": contract.jsonable(list(trajectory.times)),
        "columns": {str(k): contract.jsonable(list(v)) for k, v in trajectory.columns.items()},
        "end": contract.jsonable(trajectory.end),
        "points": int(trajectory.points),
        "window_basis": trajectory.window_basis,
        "invariants": [
            {"law": check.law, "initial": contract.jsonable(check.initial),
             "final": contract.jsonable(check.final),
             "worst_drift": contract.jsonable(check.worst_drift), "held": bool(check.held)}
            for check in trajectory.invariants
        ],
        "checked": bool(trajectory.checked),
        "sound": bool(trajectory.sound),
        "unmeasured": list(trajectory.unmeasured),
        "text": trajectory.summary(),
    }


def sensitivity_view(sensitivity: Any) -> Optional[contract.SensitivityView]:
    if sensitivity is None:
        return None
    return {
        "quantity": str(sensitivity.quantity),
        "base_value": contract.jsonable(sensitivity.base_value),
        "sensitivities": [
            {"parameter": s.parameter, "value": contract.jsonable(s.value),
             "relative": contract.jsonable(s.relative), "absolute": contract.jsonable(s.absolute),
             "negligible": bool(s.negligible), "unresolvable": bool(s.unresolvable)}
            for s in sensitivity.sensitivities
        ],
        "skipped": {str(k): str(v) for k, v in (sensitivity.skipped or {}).items()},
        "conserved_by": sensitivity.conserved_by,
        "resolution": contract.jsonable(sensitivity.resolution),
    }


def section_view(record: Any) -> contract.StructuredSection:
    return {
        "key": record.key,
        "title": record.title,
        "status": record.status,
        "text": record.text,
        "refusals": list(record.refusals),
        "data": {name: section_data(obj) for name, obj in record.data.items()},
    }


def section_data(obj: Any) -> Any:
    """A section's report object as JSON. A stochastic trajectory is thinned
    (module docstring); an object holding code is sent without it."""
    from caterva.compose.stochastic import Trajectory as StochasticTrajectory

    if isinstance(obj, StochasticTrajectory):
        return stochastic_run(obj)
    try:
        return contract.jsonable(obj)
    except TypeError:
        return contract.jsonable(_without_code(obj))


def stochastic_run(run: Any) -> Dict[str, Any]:
    """One SSA realisation: what the section printed from, with the event
    table thinned to at most SERIES_ROW_LIMIT rows (every n-th, and the last)."""
    rows = len(run.times)
    indices = thinned_indices(rows)
    return {
        "system": contract.jsonable(run.system),
        "species": list(run.species),
        "events": int(run.events),
        "end": contract.jsonable(run.end),
        "seed": int(run.seed),
        "ended": str(run.ended),
        "final_counts": {str(k): int(v) for k, v in run.final_counts().items()},
        "rows": rows,
        "every": every_for(rows),
        "times": [contract.jsonable(run.times[i]) for i in indices],
        "counts": {name: [int(run.counts[i][j]) for i in indices]
                   for j, name in enumerate(run.species)},
    }


def every_for(rows: int) -> int:
    """The stride that keeps a table of `rows` rows within SERIES_ROW_LIMIT
    (1 when it already is)."""
    limit = contract.SERIES_ROW_LIMIT
    return 1 if rows <= limit else -(-rows // (limit - 1))


def thinned_indices(rows: int) -> List[int]:
    """Row indices to send: all of them up to SERIES_ROW_LIMIT, else every
    n-th row and the last, so the final state is always among them."""
    every = every_for(rows)
    indices = list(range(0, rows, every))
    if rows and indices[-1] != rows - 1:
        indices.append(rows - 1)
    return indices


def _without_code(obj: Any, _depth: int = 0) -> Any:
    """`obj` with every field that holds a function set to None, recursively
    through dataclasses, tuples, lists and mappings. The dataclass itself is
    kept (dataclasses.replace) so jsonable still reads its judgements."""
    if _depth > contract.MAX_DEPTH:
        return obj
    if isinstance(obj, list):
        return [_without_code(v, _depth + 1) for v in obj]
    if isinstance(obj, tuple):
        return tuple(_without_code(v, _depth + 1) for v in obj)
    if isinstance(obj, Mapping):
        return {k: _without_code(v, _depth + 1) for k, v in obj.items()}
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        changes = {}
        for f in dataclasses.fields(obj):
            value = getattr(obj, f.name)
            if inspect.isroutine(value) or (callable(value) and not dataclasses.is_dataclass(value)
                                            and not isinstance(value, type)):
                changes[f.name] = None
            elif isinstance(value, (list, tuple, Mapping)) or dataclasses.is_dataclass(value):
                changes[f.name] = _without_code(value, _depth + 1)
        return dataclasses.replace(obj, **changes) if changes else obj
    return obj


# ---------------------------------------------------------------------------
# The two endpoints this module owns
# ---------------------------------------------------------------------------


def shapes_endpoint(request: EndpointRequest) -> contract.ShapesResponse:
    """GET /api/compose/shapes: exactly `grammar.shapes()`."""
    if request.query:
        raise contract.Malformed("this endpoint takes no query parameters",
                                 field=sorted(request.query)[0])
    from caterva.compose.grammar import shapes

    return {"shapes": list(shapes())}


def normalise_endpoint(request: EndpointRequest) -> contract.NormaliseOrganismResponse:
    """POST /api/organisms/normalise {name}: exactly `normalise_organism(name)`."""
    body = request.body
    if not isinstance(body, Mapping) or set(body) != {"name"}:
        raise contract.Malformed("the body is {\"name\": \"...\"}", field="name")
    if not isinstance(body["name"], str):
        raise contract.Malformed("name must be a string", field="name")
    from caterva.compose.organisms import normalise_organism

    organism, note = normalise_organism(body["name"])
    return {"organism": organism, "note": note}


SPEC = AdapterSpec(
    kind=KIND,
    title="Compose a model",
    command="compose",
    needs=("network", "literature"),
    argv=argv,
    run=run,
    describe=describe,
    cli_prefix=("caterva", "compose"),
    serial=True,
    # Only a subject sends compose to the literature (contract section 13).
    needs_for=lambda request: ("network", "literature") if request.get("subject") else (),
)


def register(registry: Any) -> None:
    registry.register(SPEC)
    registry.add_endpoint("compose_shapes", shapes_endpoint, owner="compose")
    registry.add_endpoint("normalise_organism", normalise_endpoint, owner="compose")
    from caterva.studio.adapters.enzymes import register_endpoints

    register_endpoints(registry, "compose")
