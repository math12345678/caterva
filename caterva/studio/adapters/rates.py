"""Kind `rates`: `caterva rates`, a laboratory's own initial rates fitted (owner: sci-kinetics).

WHAT IT CALLS
    `caterva.rates.ingest.inspect`, which reads the table the page sends as
    text (delimiter, header, decimal mark, units, shape) into the canonical CSV
    that `caterva rates` reads; `caterva.rates.table.read_table` on that text;
    `caterva.rates.run.execute`, the one function the command's `main` also
    calls (the fit, the tests, the verdict, the literature comparison); and
    `caterva.rates.report` and `caterva.rates.view` for the report, the JSON
    and the figure and tables drawn from the same `Analysis`. Nothing is
    computed here and nothing is shelled out.

WHY THE REQUEST CARRIES TEXT
    The browser reads a dropped or pasted table and sends it in the body; a
    filesystem path from the page is never accepted. The request is the text,
    the mapping the person confirmed (columns, units, decimal mark) and the
    fitting choices, so a run reopened from History restores the table and the
    mapping exactly. The run's own `dataset.csv` artifact is the canonical
    table, and `argv` names it: `caterva rates dataset.csv ...` in the folder
    that holds it gives the same numbers to the last digit.

WHAT EACH NUMBER IS
    A constant is `fitted`: the law, the method and the number of rates it
    was fitted to; the profile interval and standard error are the engine's.
    A constant the data do not determine has no value, and the table carries
    the engine's one-sided statement instead. A kcat is `computed` from the
    fitted Vmax and the enzyme concentration the person gave. A cited Km or
    Ki is `measured`, with BRENDA's reference.

WHAT IS REFUSED
    A table the ingest cannot read, or that has no unit on a column (a 400
    under `dataset`, with the line and column in the message). The engine's
    own refusals (no uncertainty chosen, two sources of it, a group of one
    rate, a law that needs an inhibitor the table has none of) are exit 3 with
    the command's words. A literature comparison that is declined is exit 3
    with the report kept, as the command does.

HOW CANCEL AND THE TIME LIMIT REACH THE FIT
    `analyse` calls a step callback before every law is fitted; the adapter's
    checks for a cancel, so a cancelled run stops between laws (a few seconds
    at the longest) and the job runner's per-kind limit (contract section
    12) stops one that never returns.
"""
from __future__ import annotations

import csv
import io
import json
from typing import Any, Dict, List, Mapping, Optional

from caterva.studio import contract
from caterva.studio.adapters import AdapterOutcome, AdapterSpec, Artifact, Cancelled, EndpointRequest, RunContext, cli_parser

KIND = "rates"
PROG = "caterva rates"
DATASET_FILE = "dataset.csv"
SIGMA_SOURCES = ("column", "replicates", "residuals")
REPOSITORY = "https://github.com/math12345678/caterva"

_KEYS = frozenset((
    "dataset", "sigma_from", "error_model", "model", "level", "significance", "ec", "organism", "substrate",
    "inhibitor", "isoform", "enzyme_concentration", "enzyme_unit"))
_TEXT_KEYS = ("error_model", "model", "ec", "organism", "substrate", "inhibitor", "isoform", "enzyme_unit")
_WHY = {
    "column": "Your table's own error bars are taken as known, so every interval and test is expressed in "
              "them: if they are too small, the intervals are too narrow.",
    "replicates": "The scatter between repeats of the same condition sets the error bar, so it does not "
                  "assume the rate law is right, and the lack-of-fit test can ask whether it is.",
    "residuals": "The scatter of your points about the fitted curve sets the error bar, which assumes the "
                 "rate law is right: a law of the wrong shape widens every interval instead of failing a test.",
}


def _dataset(request: Mapping[str, Any]) -> Dict[str, Any]:
    """The ingest's reading of the request's dataset, or Malformed saying why not."""
    from caterva.rates import ingest

    dataset = request.get("dataset")
    if not isinstance(dataset, Mapping):
        raise contract.Malformed("dataset is required: {\"text\": the table, \"mapping\": ...}", field="dataset")
    extra = sorted(set(dataset) - {"text", "filename", "mapping"})
    if extra:
        raise contract.Malformed(f"{extra[0]} is not a dataset key (text, filename, mapping)", field="dataset")
    if "text" not in dataset or not isinstance(dataset["text"], str):
        raise contract.Malformed("dataset.text must be the table as a string", field="dataset")
    filename = dataset.get("filename")
    if filename is not None and not isinstance(filename, str):
        raise contract.Malformed("dataset.filename must be text", field="dataset")
    try:
        read = ingest.inspect(dataset["text"], filename=filename, mapping=dataset.get("mapping"))
    except ingest.IngestRefused as exc:
        raise contract.Malformed(str(exc), field="dataset") from exc
    if not read["ready"]:
        raise contract.Malformed(read["refusal"] or "the table cannot be used yet", field="dataset")
    return read


def argv_of(request: Mapping[str, Any]) -> List[str]:
    """`dataset.csv` first, then one flag per fitting choice; never --json or --export."""
    if not isinstance(request, Mapping):
        raise contract.Malformed("a rates request is a JSON object")
    for key in request:
        if key not in _KEYS:
            raise contract.Malformed(f"{key} is not a rates request key", field=key)
    read = _dataset(request)
    source = request.get("sigma_from")
    if source not in SIGMA_SOURCES:
        raise contract.Malformed(
            "sigma_from is required, and is column (the table's own standard deviations), replicates or "
            "residuals: this fit will not invent an uncertainty, and the page cannot choose which one you "
            "mean", field="sigma_from")
    for key in _TEXT_KEYS:
        if key in request and (not isinstance(request[key], str) or not request[key].strip()):
            raise contract.Malformed(f"{key} must be non-empty text", field=key)
    for key in ("level", "significance", "enzyme_concentration"):
        value = request.get(key)
        if key in request and (isinstance(value, bool) or not isinstance(value, (int, float))):
            raise contract.Malformed(f"{key} must be a number", field=key)
    out = [DATASET_FILE]
    if source != "column":
        out += ["--sigma-from", source]
    elif not (read["sigma_options"] or {}).get("column"):
        raise contract.Malformed("sigma_from is column, and the table has no standard-deviation column: "
                                 "choose replicates or residuals, or map a sigma column", field="sigma_from")
    for role in ("substrate", "rate", "sigma", "inhibitor"):
        name = read["column_names"].get(role)
        if name and name != role:
            out += [f"--{role}-column", name]
    if read["group_column"]:
        out += ["--group", read["group_column"]]
    for key, flag in (("error_model", "--error-model"), ("model", "--model")):
        if key in request:
            out += [flag, request[key]]
    for key, flag in (("level", "--level"), ("significance", "--significance")):
        if key in request:
            out.append(f"{flag}={float(request[key])!r}")
    for key in ("ec", "organism", "substrate", "inhibitor", "isoform"):
        if key in request:
            out += [f"--{key}", request[key].strip()]
    if "enzyme_concentration" in request or "enzyme_unit" in request:
        from caterva.rates import turnover

        if "enzyme_concentration" not in request or "enzyme_unit" not in request:
            raise contract.Malformed("an enzyme concentration needs its unit, and a unit needs its "
                                     "concentration", field="enzyme_concentration")
        try:
            turnover.enzyme_scale(float(request["enzyme_concentration"]), request["enzyme_unit"])
        except turnover.TurnoverRefused as exc:
            raise contract.Malformed(str(exc), field="enzyme_concentration") from exc
    return out


def _parsed(argv: List[str]) -> Any:
    from caterva.rates.__main__ import build_parser

    return cli_parser(build_parser, PROG).parse_args(argv)


def argv(request: Mapping[str, Any]) -> List[str]:
    """The argv, accepted by the command's parser and by its own checks of the question."""
    from caterva.rates.run import QuestionError, validate_question

    out = argv_of(request)
    args = _parsed(out)
    try:
        validate_question(level=args.level, significance=args.significance, ec=args.ec,
                          organism=args.organism, substrate=args.substrate,
                          inhibitor=args.inhibitor, isoform=args.isoform)
    except QuestionError as exc:
        raise contract.Malformed(f"{PROG}: error: {exc}") from exc
    return out


def describe(request: Mapping[str, Any]) -> str:
    dataset = request.get("dataset") if isinstance(request.get("dataset"), Mapping) else {}
    name = dataset.get("filename") or "pasted table"
    model = request.get("model") or "auto"
    return f"Initial rates, {name}, {model} laws, uncertainty from {request.get('sigma_from')}"


def needs_for(request: Mapping[str, Any]) -> tuple:
    return ("network", "literature") if request.get("ec") else ()


# ---------------------------------------------------------------------------
# The endpoint: how a table is read
# ---------------------------------------------------------------------------


def preview_endpoint(request: EndpointRequest) -> Dict[str, Any]:
    """POST /api/rates/preview {text, filename?, mapping?}: `ingest.inspect`, unchanged."""
    from caterva.rates import ingest

    body = request.body
    if not isinstance(body, Mapping) or "text" not in body or set(body) - {"text", "filename", "mapping"}:
        raise contract.Malformed("the body is {\"text\": the table, \"filename\": optional, \"mapping\": optional}",
                                 field="text")
    if not isinstance(body["text"], str):
        raise contract.Malformed("text must be a string", field="text")
    if body.get("filename") is not None and not isinstance(body["filename"], str):
        raise contract.Malformed("filename must be text", field="filename")
    try:
        return ingest.inspect(body["text"], filename=body.get("filename"), mapping=body.get("mapping"))
    except ingest.IngestRefused as exc:
        raise contract.Malformed(str(exc), field="mapping") from exc


# ---------------------------------------------------------------------------
# The run
# ---------------------------------------------------------------------------


def _fitted_value(row: Mapping[str, Any]) -> Optional[contract.SourcedValue]:
    if not row["determined"] or row["estimate"] is None:
        return None
    method = (f"{row['law_title']} law, nonlinear least squares on your data; "
              f"{row['level'] * 100:g}% profile-likelihood interval {row['interval']}"
              + (f" {row['unit']}" if row["unit"] else ""))
    ident = f"{row['law']}.{row['constant']}" + (f"[{row['group']}]" if row["group"] else "")
    return contract.sourced(
        row["estimate"], row["unit"],
        contract.fitted(method, n_points=row["n"], stderr=row["standard_error"]),
        ident=ident, label=row["constant"])


def _turnover_value(row: Mapping[str, Any]) -> Optional[contract.SourcedValue]:
    if not row["determined"] or row["estimate"] is None:
        return None
    return contract.sourced(
        row["estimate"], row["unit"],
        contract.computed("kcat = Vmax / [E]: the fitted Vmax divided by the enzyme concentration you gave "
                          f"({row['enzyme']['concentration']:g} {row['enzyme']['unit']}), taken as exact",
                          inputs=[f"{row['law']}.Vmax"]),
        ident=f"{row['law']}.kcat" + (f"[{row['group']}]" if row["group"] else "") + f".{row['unit']}",
        label="kcat")


def _literature_rows(analysis: Any, ec: Optional[str]) -> List[Dict[str, Any]]:
    from caterva.rates import report

    out: List[Dict[str, Any]] = []
    for c in analysis.literature:
        cited = None
        if c.found and c.cited is not None:
            citation: Dict[str, Any] = {"text": f"BRENDA ref {c.reference}" if c.reference else "BRENDA",
                                        "registry": "BRENDA", "via": c.source}
            if c.reference:
                citation["reference_id"] = str(c.reference)
            if ec:
                citation["url"] = f"https://www.brenda-enzymes.org/enzyme.php?ecno={ec}"
            cited = contract.sourced(
                c.cited, c.cited_unit or "",
                {"kind": "measured", "citation": citation, "organism": c.organism, "cross_species": False,
                 "commentary": c.commentary, "scope": list(c.concerns), "spread": None,
                 "chosen_because": c.tie},
                ident=f"cited.{c.constant}", label=c.constant)
        determined = c.determined
        conv = c.converted
        out.append({
            "constant": c.constant, "law": c.law, "group": c.group, "asked_under": c.compound,
            "mode": c.mode, "found": bool(c.found), "cited": cited, "cited_unit": c.cited_unit,
            "organism": c.organism, "sentence": report.literature_sentence(c), "refused": c.refused,
            "determined": bool(determined),
            "fitted_estimate": contract.finite(conv.estimate)[0] if conv is not None and determined else None,
            "fitted_low": conv.low if conv is not None else None,
            "fitted_high": conv.high if conv is not None else None,
            "contains_cited": c.contains, "ratio": c.ratio if determined else None,
            "concerns": list(c.concerns), "evidence_against": c.evidence_against,
            "conditional": c.conditional, "commentary": c.commentary, "tie": c.tie,
            "spread_text": (f"The resolver found {c.spread_rows} equally well evidenced rows, "
                            f"{report.g(c.spread[0])} to {report.g(c.spread[1])} {c.cited_unit}; that spread "
                            f"is disagreement between papers, not measurement error.")
            if c.spread and c.spread_rows > 1 else None,
        })
    return out


def neutralised_csv(text: str) -> str:
    """The engine's CSV with every text cell a spreadsheet would run as a
    formula made inert (a leading apostrophe); numbers are left alone."""
    from caterva.rates.ingest import neutralise_cell

    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    for row in csv.reader(io.StringIO(text)):
        writer.writerow([neutralise_cell(c) for c in row])
    return out.getvalue()


def cite_line(version: str) -> str:
    return (f"Caterva {version}, `caterva rates`, Apache-2.0, {REPOSITORY}. Cite the version you used; "
            f"the run's bundle records it.")


def run(request: Mapping[str, Any], ctx: RunContext) -> AdapterOutcome:
    from caterva.rates import ingest, report, turnover, view
    from caterva.rates.analysis import Refused
    from caterva.rates.fit import FitRefused
    from caterva.rates.run import LiteratureQuery, execute
    from caterva.rates.table import TableError, UnitRefused, read_table
    from caterva.rates.uncertainty import NoUncertainty

    args = _parsed(argv_of(request))
    ctx.progress.check_cancelled()
    ctx.progress.stage("read", "Reading your table", 0.0)
    read = _dataset(request)
    canonical = read["canonical"]
    try:
        data = read_table(DATASET_FILE, text=canonical, group=read["group_column"],
                          names=dict(read["column_names"]))
    except TableError as exc:
        raise contract.Malformed(str(exc), field="dataset") from exc
    except UnitRefused as exc:
        reason = f"{PROG}: {exc}"
        return AdapterOutcome(exit_code=3, result=None, summary=str(exc).splitlines()[0], refusal=reason)

    def on_step(key: str, label: str, done: int, total: int) -> None:
        ctx.progress.check_cancelled()
        ctx.progress.stage(key, label, done / total if total else None)

    literature = (LiteratureQuery(args.ec, args.organism, args.substrate, args.inhibitor, args.isoform)
                  if args.ec else None)
    try:
        execution = execute(
            data, sigma_from=args.sigma_from, error_model=args.error_model, model=args.model,
            level=args.level, significance=args.significance, linearizations=False, literature=literature,
            on_step=on_step)
    except (NoUncertainty, Refused, FitRefused) as exc:
        reason = f"{PROG}: {exc}"
        return AdapterOutcome(exit_code=3, result=None, summary=str(exc).splitlines()[0], refusal=reason)
    analysis = execution.analysis
    ctx.progress.check_cancelled()
    ctx.progress.stage("report", "Drawing the figure and the tables", 0.95)

    source = request["sigma_from"]
    uncertainty = analysis.uncertainty
    sigma = {"source": uncertainty.source,
             "description": uncertainty.describe(analysis.unit_of("rate")),
             "why": _WHY[source]}
    parameters = view.parameter_rows(analysis)
    for row in parameters:
        row["value"] = _fitted_value(row)
    kcat: List[Dict[str, Any]] = []
    kcat_refused: Optional[str] = None
    methods_text = report.methods(analysis).rstrip("\n")
    head, software, tail = methods_text.rpartition(" Software: ")
    if software:
        methods_text = f"{head} {ingest.methods_sentence(read)}{software}{tail}"
    else:
        methods_text += " " + ingest.methods_sentence(read)
    if request.get("enzyme_concentration") is not None:
        try:
            kcat = turnover.turnover(analysis, float(request["enzyme_concentration"]), request["enzyme_unit"])
            for row in kcat:
                row["value"] = _turnover_value(row)
            methods_text += " " + turnover.sentence(float(request["enzyme_concentration"]), request["enzyme_unit"])
        except turnover.TurnoverRefused as exc:
            kcat_refused = str(exc)
    version = report._version()
    cautions = view.cautions(analysis)
    summary_text = analysis_summary(analysis)
    result: Dict[str, Any] = {
        "analysis": json.loads(report.to_json(analysis)),
        "report_text": report.render(analysis),
        "methods": methods_text + "\n",
        "cite": cite_line(version),
        "sigma": sigma,
        "dataset": {"filename": read["filename"], "shape": read["shape"], "summary": read["summary"],
                    "decisions": read["decisions"], "problems": read["problems"],
                    "mapping": read["mapping"], "group_column": read["group_column"]},
        "figure": view.figure(analysis),
        "parameters": parameters,
        "interval_basis": view.interval_basis(analysis),
        "comparison": view.comparison(analysis),
        "lack_of_fit": view.lack_of_fit(analysis),
        "cautions": cautions["cautions"],
        "better": cautions["better"],
        "groups": view.groups(analysis),
        "turnover": kcat,
        "turnover_refused": kcat_refused,
        "literature": _literature_rows(analysis, args.ec),
        "literature_refused": analysis.literature_refused,
    }
    artifacts = (
        Artifact(DATASET_FILE, canonical.encode("utf-8"), "text/csv; charset=utf-8",
                 "the table that was fitted, as `caterva rates` reads it (every parse decision is a comment)"),
        Artifact("parameters.csv", neutralised_csv(report.parameters_csv(analysis)).encode("utf-8"),
                 "text/csv; charset=utf-8", "every constant of every law fitted, with its profile interval "
                 "(caterva rates --export csv; text cells that a spreadsheet would run are made inert)"),
        Artifact("curves.csv", neutralised_csv(report.curves_csv(analysis)).encode("utf-8"),
                 "text/csv; charset=utf-8", "the fitted curves and the measured rates, for plotting "
                 "(caterva rates --export curves)"),
        Artifact("report.md", report.render(analysis).encode("utf-8"), "text/markdown; charset=utf-8",
                 "the engine's report (caterva rates, stdout)"),
        Artifact("methods.txt", result["methods"].encode("utf-8"), "text/plain; charset=utf-8",
                 "a methods paragraph generated from this run"),
    )
    code = 3 if execution.refused else 0
    refusal = None
    if execution.refused:
        refusal = (f"{PROG}: a literature comparison was not made: " + "; ".join(execution.refusal_reasons))
    return AdapterOutcome(exit_code=code, result=result, summary=summary_text, refusal=refusal,
                          artifacts=artifacts)


def analysis_summary(analysis: Any) -> str:
    """One line for History: the first thing the verdict says."""
    from caterva.rates import report

    lines = report.verdict_lines(analysis)
    for line in lines:
        if "profile intervals" in line:
            return line
    return lines[0] if lines else f"{len(analysis.data)} rates fitted"


SPEC = AdapterSpec(
    kind=KIND,
    title="Fit your own rates",
    command="rates",
    needs=("network", "literature"),
    argv=argv,
    run=run,
    describe=describe,
    cli_prefix=("caterva", "rates"),
    needs_for=needs_for,
)


def register(registry: Any) -> None:
    registry.register(SPEC)
    registry.add_endpoint("rates_preview", preview_endpoint, owner="rates")
