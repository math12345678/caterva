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

THE CLAIMS BUNDLE
-----------------
Every run writes the claims bundle `caterva compose --claims DIR` writes
(caterva/evidence/compose_claims.py, ADR 0179), into `<run dir>/claims/`
(CONTRACT.md 11): the parsed request gets `claims` set to that directory
before `compose_report` runs, so the pages the search reads are pinned as
it reads them and the report ends with the command's own `## Claims`
section. The recorded `cli` leaves `--claims` out, because the directory
is the studio's and not the person's; `claims.text` in the result says
where it is. The bundle is served two ways, both artefacts: `claims.zip`,
the bundle directory (not the store beside it) for `caterva verify`, and
`claims.json`, its manifest and records without the pinned bytes. And
every number's claim is transcribed onto its provenance (`claim_infos`:
the claim, the row, the pinned page, the paper's title and PMID from the
literature page pinned beside it, the certificates, or the refusal), read
from the bundle's files with the evidence layer's own readers, nothing
decided here. The `## Claims` section is not among `sections`: it is
`claims`, so a page draws the analyses as sections and the bundle once.

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
import json
import shutil
import zipfile
from typing import TYPE_CHECKING, Any, Dict, List, Mapping, Optional, Tuple

from caterva.studio import contract
from caterva.studio.adapters import (
    AdapterOutcome, AdapterSpec, Artifact, EndpointRequest, RunContext, cli_parser,
)

if TYPE_CHECKING:
    from pathlib import Path

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
#: The claims bundle, as two artefacts (module docstring): the bundle
#: directory zipped, and its records without the pinned bytes.
CLAIMS_ZIP = ("claims.zip", "application/zip",
              "the run's claims bundle (manifest.json, claims.jsonl, rows.jsonl, snapshots.jsonl, "
              "snapshots/<hex>.gz): unzip it and run `caterva verify DIR` to re-check it offline "
              "(caterva compose --claims DIR)")
CLAIMS_JSON = ("claims.json", "application/json",
               "the bundle's manifest and its claim, row and snapshot records, without the pinned bytes")
#: The bundle's files, in the order the zip lists them; the store beside
#: them (`store/`) is the run's own index and is not an artefact.
BUNDLE_FILES = ("manifest.json", "claims.jsonl", "rows.jsonl", "snapshots.jsonl")
BUNDLE_BLOBS = "snapshots"

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
    # The claims bundle goes where CONTRACT.md 11 says, as `--claims DIR`
    # would put it (module docstring, "The claims bundle").
    claims_dir = ctx.run_dir / contract.CLAIMS_DIR
    args.claims = str(claims_dir)
    out, err = io.StringIO(), io.StringIO()
    try:
        composed = compose_report(args, organism_note=organism_note, stream=out, err=err,
                                  progress=ctx.progress)
    except UnrecognisedShape as exc:
        # What main prints to stderr, without print's newline. Nothing was
        # built, so there is no result: the page shows this reason. The
        # claims run had opened its store before composing; no claim was
        # made and no bundle written, so the folder is not left to look
        # like one.
        shutil.rmtree(claims_dir, ignore_errors=True)
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
    claim_set = composed.claims
    # The ids in each artefact are the ids in the bundle, as `--export
    # FORMAT --claims DIR` writes them: one ClaimSet, built from the same
    # ProvenancedModel the artefacts are written from.
    claim_ids = dict(claim_set.by_identifier) if claim_set is not None else None
    try:
        texts = export_texts(provenanced, EXPORT_FORMATS, claim_ids=claim_ids)
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

    claims: Optional[Dict[str, contract.ClaimInfo]] = None
    summary_of_claims: Optional[contract.ClaimsSummary] = None
    if claim_set is not None:
        artifacts += claims_artifacts(claims_dir)
        claims = claim_infos(claims_dir)
        summary_of_claims = claims_summary(composed)

    result = compose_result(composed, provenanced, markdown=markdown, exports=exports,
                            subject=args.subject, claims=claims, claims_summary=summary_of_claims)
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


#: The key of the report's `## Claims` section among `Sections.records`
#: (caterva/compose/__main__.py): kept out of `sections` (module docstring).
CLAIMS_SECTION = "claims"


def compose_result(composed: Any, provenanced: Any, *, markdown: str,
                   exports: Mapping[str, contract.ExportInfo],
                   subject: Optional[str],
                   claims: Optional[Mapping[str, contract.ClaimInfo]] = None,
                   claims_summary: Optional[contract.ClaimsSummary] = None) -> contract.ComposeResult:
    """The ComposeResult for one `compose_report` run: every field read from
    the object the markdown was printed from. `claims` maps each quantity's
    identifier to its claim transcribed from the run's bundle (`claim_infos`)
    and `claims_summary` is the bundle's summary (`claims_summary`); both
    None for a run that wrote no bundle."""
    model = composed.model
    report = composed.dossier
    result: contract.ComposeResult = {
        "query": model.query,
        "recognition": {"rule": model.recognition.rule, "reading": model.recognition.reading},
        "model": model_structure(model, provenanced, claims=claims),
        "search": search_summary(composed, subject),
        "verdict": verdict_view(report.verdict),
        "stability": stability_view(report.stability),
        "trajectory": trajectory_view(report.trajectory),
        "sensitivity": sensitivity_view(report.sensitivity),
        "sweeps": [contract.jsonable(sweep) for sweep in report.sweeps],
        "sections": [section_view(record) for record in composed.sections.records
                     if record.key != CLAIMS_SECTION],
        "notes": [str(note) for note in model.recognition.composition.notes],
        "report_markdown": markdown,
        "exports": dict(exports),
        "claims": claims_summary,
    }
    return result


def model_structure(model: Any, provenanced: Any, *,
                    claims: Optional[Mapping[str, contract.ClaimInfo]] = None) -> contract.ModelStructure:
    from caterva.compose.pipeline import _conservation_laws, _unconserved_species

    laws = _conservation_laws(model.network)
    values = {origin.identifier: parameter_value(origin, model, claim=(claims or {}).get(origin.identifier))
              for origin in provenanced.origins}
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


def parameter_value(origin: Any, model: Any, *,
                    claim: Optional[contract.ClaimInfo] = None) -> contract.SourcedValue:
    """One number of the model, with the origin `export.provenance_of`
    decided (see the module docstring for the citation fields) and, when
    the run wrote a bundle, its claim from that bundle (`claim_infos`: the
    claim whose subject starts with the origin's identifier)."""
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
    value = contract.from_parameter_origin(origin, reason=reason, registry=registry, url=url, claim=claim)
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
        "compounds": {str(k): str(v) for k, v in model.used_compounds().items()},
        "unused_compounds": {str(k): str(v) for k, v in model.unused_compounds().items()},
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
    from caterva.compose.analysis import CONTINUUM_COUNT_CAVEAT, STATE_DISTINCT_TOLERANCE

    on_a_line = bool(getattr(stability, "on_a_continuum", False))
    return {
        "rounding_tolerance": float(STATE_DISTINCT_TOLERANCE),
        "count_caveat": CONTINUUM_COUNT_CAVEAT if on_a_line else None,
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
# The claims bundle: its artefacts, and each number's claim from it
# ---------------------------------------------------------------------------


def bundle_files(directory: Path) -> List[Path]:
    """The bundle's files under `directory`, in zip order: the four records
    files, then the pinned bytes by name. The store beside them is not one."""
    out = [directory / name for name in BUNDLE_FILES if (directory / name).is_file()]
    blobs = directory / BUNDLE_BLOBS
    if blobs.is_dir():
        out += sorted(p for p in blobs.iterdir() if p.is_file() and p.suffix == ".gz")
    return out


def claims_artifacts(directory: Path) -> List[Artifact]:
    """`claims.zip` and `claims.json` for the bundle at `directory`.

    The zip holds the bundle's files under their own names, each dated
    1980-01-01 so that one bundle zips to one sequence of bytes; the pinned
    pages are already gzipped and are stored as they are. The JSON is the
    manifest and the three record files, each line parsed and nothing else
    done to it.
    """
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for path in bundle_files(directory):
            info = zipfile.ZipInfo(path.relative_to(directory).as_posix(), date_time=(1980, 1, 1, 0, 0, 0))
            info.external_attr = 0o600 << 16
            info.compress_type = zipfile.ZIP_STORED if path.suffix == ".gz" else zipfile.ZIP_DEFLATED
            archive.writestr(info, path.read_bytes())
    listing = {"manifest": json.loads((directory / BUNDLE_FILES[0]).read_text(encoding="utf-8"))}
    for key, name in (("claims", BUNDLE_FILES[1]), ("rows", BUNDLE_FILES[2]), ("snapshots", BUNDLE_FILES[3])):
        lines = (directory / name).read_text(encoding="utf-8").splitlines()
        listing[key] = [json.loads(line) for line in lines if line.strip()]
    text = json.dumps(listing, indent=1, ensure_ascii=False, allow_nan=False) + "\n"
    return [Artifact(CLAIMS_ZIP[0], buffer.getvalue(), CLAIMS_ZIP[1], CLAIMS_ZIP[2]),
            Artifact(CLAIMS_JSON[0], text.encode("utf-8"), CLAIMS_JSON[1], CLAIMS_JSON[2])]


def claims_summary(composed: Any) -> Optional[contract.ClaimsSummary]:
    """The ClaimsSummary of a `compose_report` run that wrote a bundle: the
    ClaimSet's root and counts, and the `## Claims` section's text from
    the record it was printed under; None without a bundle."""
    claim_set = composed.claims
    if claim_set is None:
        return None
    record = next((r for r in composed.sections.records if r.key == CLAIMS_SECTION), None)
    return {
        "root": str(claim_set.root),
        "counts": {str(k): int(v) for k, v in claim_set.counts().items()},
        "rows": int(claim_set.rows),
        "snapshots": int(claim_set.snapshots),
        "notes": [str(n) for n in claim_set.notes],
        "bundle": CLAIMS_ZIP[0],
        "listing": CLAIMS_JSON[0],
        "text": record.text if record is not None else "",
    }


def claim_infos(directory: Path) -> Dict[str, contract.ClaimInfo]:
    """Every claim in the bundle at `directory`, transcribed, keyed by the
    quantity its subject names (`reaction_Km = Km(2.7.1.1, ...)`: the
    text before ` = `, the identifier the exports and `ClaimSet.by_identifier`
    use; the model claim is under `model`).

    Read with the evidence layer's own readers (`bundle.read_bundle`, which
    recomputes every id; `references.parse_reference_page`, the parser
    `caterva why` prints the paper from) and transcribed field by field.
    """
    from caterva.evidence.bundle import read_bundle

    bundle = read_bundle(directory)
    papers = {s.locator: s for s in bundle.snapshots.values() if s.source == "brenda_reference"}
    return {claim.subject.split(" = ", 1)[0]: claim_info(claim, bundle, papers)
            for claim in bundle.claims.values()}


def claim_info(claim: Any, bundle: Any, papers: Mapping[str, Any]) -> contract.ClaimInfo:
    """One claim as the contract's ClaimInfo (contract.py says each field)."""
    rule = claim.derivation.rule
    row = snapshot = reference = None
    rows = claim.derivation.row_inputs()
    if claim.kind == "cited" and rows:
        record = bundle.get(rows[0])
        row = {"locator": record.locator, "value_text": record.value_text, "unit": record.unit,
               "substrate": record.substrate, "organism": record.organism,
               "commentary": record.commentary, "reference": record.reference}
        page = bundle.get(record.snapshot)
        snapshot = {"id": page.id, "locator": page.locator, "retrieved_at": page.retrieved_at,
                    "licence": page.licence, "served_from": page.served_from}
        reference = reference_view(record, bundle, papers)
    refusal = None
    if claim.refusal is not None:
        refusal = {"kind": claim.refusal.kind, "requested": claim.refusal.requested,
                   "candidates": [str(c) for c in claim.refusal.candidates]}
    return {
        "id": claim.ref,
        "kind": claim.kind,
        "rule": {"rule_id": rule.rule_id, "version": int(rule.version), "adr": rule.adr},
        "row": row,
        "snapshot": snapshot,
        "reference": reference,
        "certificates": [{"matched": c.matched} for c in claim.derivation.certificates],
        "refusal": refusal,
    }


def reference_view(row: Any, bundle: Any, papers: Mapping[str, Any]) -> Optional[contract.ClaimReference]:
    """The paper behind `row`'s reference id, from the literature page
    pinned for it (`capture_reference` pins it under `reference_url(ec,
    ref)`), as `caterva why` reads it; None when the bundle has no such
    page or it holds no reference block (the run's notes say why)."""
    from caterva.evidence.claims import EvidenceRefused
    from caterva.evidence.references import parse_reference_page, reference_url
    from caterva.evidence.rows import locator_ec

    ec = locator_ec(row.locator)
    if not ec or not row.reference:
        return None
    page = papers.get(reference_url(ec, row.reference))
    if page is None:
        return None
    try:
        found = parse_reference_page(bundle.snapshot_bytes(page.ref).decode("utf-8", errors="replace"))
    except EvidenceRefused:
        return None
    return {
        "title": found.title,
        "pmid": found.pmid,
        "journal": found.journal,
        "year": found.year,
        "url": f"https://pubmed.ncbi.nlm.nih.gov/{found.pmid}/" if found.pmid else None,
    }


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
