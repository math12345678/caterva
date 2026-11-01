"""Kind `bind`: `caterva bind`, the measured binding free energy a simulation is held to (owner: sci-kinetics).

WHAT IT CALLS (caterva/bind/__main__.py, caterva/bind/core.py)
    read_page(ec)                              the BRENDA page, fetched as the command fetches it
    compound_names / survey_targets / _rows    the Ki rows, parsed as the command parses them
    assess(rows, state, computed, unit, iso)   the band and, with a computed value, the verdict
    render(assessment)                         the text the command prints, and its exit code
    render_survey(survey(...))                 the --survey text

The command's judgement used to be one function that computed and printed
in one pass, and its survey rounded each band to two decimals before
anything else could read it. Both are split now (`assess` beside `render`,
`survey_targets` beside `survey`), so every number here is the unrounded
one the printed text was formatted from, and the text is the command's.

WHAT EACH NUMBER IS
    A Ki is `measured`: BRENDA's row, its reference, its organism, its
    assay pH and temperature, and its commentary verbatim. Its link is the
    enzyme page the row was read from (BRENDA has no page per reference),
    from the literature layer's `brenda_reference_url`. The ΔG°bind of a
    row is `computed` from that Ki at the row's own temperature; a row that
    states none has a ΔG range over bind.core.UNSTATED_T_RANGE_C, sent as
    an interval rather than a guessed point. The band's edges, the gap and
    the Ki fold are `computed`. The value being judged is `chosen` by the
    user. The judging temperature is `computed` (the mean stated assay
    temperature of the rows used) or the command's 25 °C default.

EXIT CODES
    0 a target (and, with a computed value, agreement); 4 the computed value
    disagrees, a result; 3 refused and said why: the page could not be read,
    no Ki rows, no row fits the state. The refusal is the command's words.

WHAT IS REFUSED
    --html and --json are never produced: the page is BRENDA's, fetched,
    and the result is the structured form of what --json prints.
"""
from __future__ import annotations

import functools
from typing import Any, Dict, List, Mapping, Optional

from caterva.studio import contract
from caterva.studio.adapters import AdapterOutcome, AdapterSpec, RunContext, cli_parser

KIND = "bind"
PROG = "caterva bind"
_KEYS = frozenset(("ec", "mode", "organism", "inhibitor", "state", "isoform", "computed"))
_MODES = ("inhibitor", "list", "survey")
KCAL = "kcal/mol"


def _string(request: Mapping[str, Any], key: str) -> Optional[str]:
    value = request.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise contract.Malformed(f"{key} must be a non-empty string", field=key)
    return value


def _number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def argv_of(request: Mapping[str, Any]) -> List[str]:
    """The argv `caterva bind` would receive (CONTRACT.md section 13):
    mode -> --inhibitor NAME | --list | --survey; computed -> the
    `--computed=VALUE±ERROR` form and --unit. Never --html or --json."""
    if not isinstance(request, Mapping):
        raise contract.Malformed("a bind request is a JSON object")
    for key in request:
        if key not in _KEYS:
            raise contract.Malformed(f"{key} is not a bind request key", field=key)
    ec = _string(request, "ec")
    if ec is None:
        raise contract.Malformed("ec is required, e.g. 1.1.1.27", field="ec")
    mode = request.get("mode")
    if mode not in _MODES:
        raise contract.Malformed(f"mode is one of {', '.join(_MODES)}", field="mode")
    out = [f"--ec={ec}"]
    organism = _string(request, "organism")
    if organism is not None:
        out.append(f"--organism={organism}")
    inhibitor = _string(request, "inhibitor")
    if mode == "inhibitor":
        if inhibitor is None:
            raise contract.Malformed("inhibitor is required in mode inhibitor (see mode list)",
                                     field="inhibitor")
        out.append(f"--inhibitor={inhibitor}")
    elif inhibitor is not None:
        raise contract.Malformed(f"inhibitor is only read in mode inhibitor, not {mode}",
                                 field="inhibitor")
    else:
        out.append(f"--{mode}")
    state = _string(request, "state")
    if state is not None:
        out.append(f"--state={state}")
    isoform = _string(request, "isoform")
    if isoform is not None:
        out.append(f"--isoform={isoform}")
    computed = request.get("computed")
    if computed is not None:
        if not isinstance(computed, Mapping) or not _number(computed.get("value")):
            raise contract.Malformed("computed is {value, error?, unit?} in kcal/mol or kJ/mol",
                                     field="computed.value")
        for key in computed:
            if key not in ("value", "error", "unit"):
                raise contract.Malformed(f"computed.{key} is not a key of computed",
                                         field=f"computed.{key}")
        text = repr(float(computed["value"]))
        error = computed.get("error")
        if error is not None:
            if not _number(error):
                raise contract.Malformed("computed.error must be a number", field="computed.error")
            text += "±" + repr(float(error))
        out.append(f"--computed={text}")
        unit = computed.get("unit")
        if unit is not None:
            if not isinstance(unit, str):
                raise contract.Malformed("computed.unit is kcal or kj", field="computed.unit")
            out.append(f"--unit={unit}")
    return out


def _parsed(argv: List[str]) -> Any:
    from caterva.bind.__main__ import build_parser

    return cli_parser(build_parser, PROG).parse_args(argv)


def argv(request: Mapping[str, Any]) -> List[str]:
    """The argv, accepted by the command's parser and by its reading of
    --computed (what the command reports as `caterva bind: ...`, exit 2)."""
    out = argv_of(request)
    args = _parsed(out)
    if args.computed:
        from caterva.bind.core import parse_computed

        try:
            parse_computed(args.computed)
        except ValueError as exc:
            raise contract.Malformed(f"caterva bind: {exc}", field="computed") from exc
    return out


def describe(request: Mapping[str, Any]) -> str:
    mode = request.get("mode")
    what = request.get("inhibitor") if mode == "inhibitor" else {
        "list": "compounds with a Ki", "survey": "every inhibitor's target"}.get(str(mode), "")
    parts = [f"EC {request.get('ec')}", str(what or "")]
    if request.get("organism"):
        parts.append(str(request["organism"]))
    return ", ".join(p for p in parts if p)


@functools.lru_cache(maxsize=1)
def _literature_missing() -> Optional[str]:
    from caterva.checkout import LiteratureLayerUnavailable, literature_module

    try:
        literature_module("brenda_client")
    except LiteratureLayerUnavailable as exc:
        return str(exc)
    return None


def unavailable() -> Optional[str]:
    return _literature_missing()


# ---------------------------------------------------------------------------
# The run
# ---------------------------------------------------------------------------


def run(request: Mapping[str, Any], ctx: RunContext) -> AdapterOutcome:
    from caterva.bind import __main__ as cli
    from caterva.bind.core import parse_computed

    args = _parsed(argv_of(request))
    organism = cli.organism_of(args.organism)
    computed = parse_computed(args.computed) if args.computed else None

    ctx.progress.check_cancelled()
    ctx.progress.stage("fetch", f"Reading BRENDA's page for EC {args.ec}", None)
    try:
        html = cli.read_page(args.ec)
    except Exception as exc:  # noqa: BLE001 - the command's own refusal: network, missing layer
        reason = f"caterva bind: could not read BRENDA for {args.ec}: {exc}"
        return AdapterOutcome(exit_code=3, result=None, summary=reason, refusal=reason)

    ctx.progress.check_cancelled()
    ctx.progress.stage("rows", f"Reading the Ki rows for EC {args.ec} in {organism or 'every organism'}",
                       None)
    base: Dict[str, Any] = {"mode": request["mode"], "compounds": [], "survey": [],
                            "target": None, "verdict": None}

    if args.survey:
        targets = cli.survey_targets(html, args.ec, organism, args.state)
        if not targets:
            reason = f"No Ki rows for EC {args.ec} in {organism}."
            return AdapterOutcome(exit_code=3, result=dict(base, report_text=reason),
                                  summary=reason, refusal=reason)
        text = cli.render_survey(cli.survey(html, args.ec, organism, args.state),
                                 args.ec, organism, args.state)
        rows = [survey_row(t) for t in targets]
        return AdapterOutcome(exit_code=0, result=dict(base, survey=rows, report_text=text),
                              summary=text.splitlines()[0])

    if args.list:
        names = cli.compound_names(html, args.ec, organism)
        if not names:
            reason = f"No Ki rows for EC {args.ec} in {organism}."
            return AdapterOutcome(exit_code=3, result=dict(base, report_text=reason),
                                  summary=reason, refusal=reason)
        text = cli.render_list(names, args.ec, organism)
        return AdapterOutcome(exit_code=0, result=dict(base, compounds=names, report_text=text),
                              summary=text.splitlines()[0])

    measured = cli._rows(html, args.ec, organism, args.inhibitor)
    if not measured:
        reason = cli.no_rows_for(args.inhibitor, args.ec, organism,
                                 cli.compound_names(html, args.ec, organism))
        return AdapterOutcome(exit_code=3, result=None, summary=reason.splitlines()[0],
                              refusal=reason)

    ctx.progress.check_cancelled()
    ctx.progress.stage("target", f"Building the {args.state}-state band for {args.inhibitor}", None)
    assessment = cli.assess(measured, args.state, computed, args.unit, args.isoform)
    if assessment.verdict is not None:
        ctx.progress.stage("judge", "Judging the computed value against the band at 2σ", None)
    text, code, _payload = cli.render(assessment)
    result = dict(base, compounds=[assessment.target.compound],
                  target=target_view(assessment.target, args.ec),
                  verdict=verdict_view(assessment, args.unit, request), report_text=text)
    if code == 3:
        refused = [line for line in text.splitlines() if line.startswith("REFUSED") or "Try --state" in line]
        reason = "\n".join(line.strip() for line in refused)
        return AdapterOutcome(exit_code=3, result=result, summary=refused[0], refusal=reason)
    first = next((line for line in text.splitlines() if line.startswith("VERDICT")), None)
    target_line = next(line for line in text.splitlines() if line.startswith("TARGET"))
    return AdapterOutcome(exit_code=code, result=result, summary=(first or target_line).strip())


def _reference_url(reference: Optional[str], ec: str) -> Optional[str]:
    """The literature layer's link for a BRENDA reference: the enzyme page
    the row was read from, or None for a row that names no reference."""
    from caterva.checkout import literature_module

    return literature_module("citation").brenda_reference_url(reference, ec)


# ---------------------------------------------------------------------------
# Serialising the command's objects
# ---------------------------------------------------------------------------


def _ki_id(index: int, m: Any) -> str:
    return f"ki:{index}:{m.reference or 'unreferenced'}"


def ki_row(index: int, m: Any, ec: str) -> contract.KiRow:
    """One bind.core.Measurement: the Ki as measured, its ΔG°bind as computed."""
    from caterva.bind.core import UNSTATED_T_RANGE_C

    ident = _ki_id(index, m)
    citation: contract.Citation = {
        "text": f"BRENDA ref {m.reference or '?'}", "registry": "BRENDA",
        "reference_id": m.reference, "url": _reference_url(m.reference, ec), "via": "brenda/ki",
    }
    unreported = [name for name, value in (("pH", m.ph), ("temperature", m.temperature_c))
                  if value is None]
    ki = contract.sourced(m.ki_mM, "mM", {
        "kind": "measured", "citation": citation, "organism": m.organism, "cross_species": False,
        "conditions": {"ph": m.ph, "temperature_c": m.temperature_c, "buffer": None,
                       "unreported": unreported},
        "commentary": m.commentary, "scope": [], "chosen_because": None, "spread": None,
    }, ident=ident, label="Ki")
    method = "ΔG°bind = RT ln(Ki / 1 M) at the row's assay temperature (bind.core.dg_kj)"
    if len(m.dg_kcal) == 1:
        dg = contract.sourced(m.dg_kcal[0], KCAL, contract.computed(method, [ident]),
                              ident=f"dg:{index}", label="ΔG°bind")
    else:
        low, high = UNSTATED_T_RANGE_C
        dg = contract.sourced(None, KCAL, contract.computed(method, [ident]), ident=f"dg:{index}",
                              label="ΔG°bind", interval={
                                  "low": m.dg_lo, "high": m.dg_hi,
                                  "meaning": f"the row states no assay temperature; ΔG°bind over "
                                             f"{low:g}-{high:g} °C instead of at a guessed one"})
    return {
        "ki": ki, "dg": dg, "compound": m.compound, "organism": m.organism,
        "reference": m.reference, "commentary": m.commentary, "mode": m.mode,
        "versus": m.versus, "preparation": m.preparation, "isoform": m.isoform,
        "excluded": m.excluded,
    }


def _edge(value: Optional[float], which: str, inputs: List[str]) -> Optional[contract.SourcedValue]:
    if value is None:
        return None
    method = (f"the {which} ΔG°bind of the rows that fit the state, "
              f"each row's whole range when its temperature is unstated (bind.core.target)")
    return contract.sourced(value, KCAL, contract.computed(method, inputs), ident=f"band_{which}")


def target_view(t: Any, ec: str) -> contract.BindTarget:
    used = [ki_row(i, m, ec) for i, m in enumerate(t.used)]
    excluded = [ki_row(len(used) + i, m, ec) for i, m in enumerate(t.excluded)]
    inputs = [row["dg"]["id"] for row in used]  # type: ignore[index]
    return {
        "compound": t.compound, "organism": t.organism, "state": t.state,
        "used": used, "excluded": excluded,
        "band_low": _edge(t.lo, "lowest", inputs), "band_high": _edge(t.hi, "highest", inputs),
        "references": list(t.references), "caveats": list(t.caveats),
    }


def verdict_view(a: Any, unit: str, request: Mapping[str, Any]) -> Optional[contract.BindVerdict]:
    if a.verdict is None or a.computed is None:
        return None
    value, err = a.computed
    v = a.verdict
    converted = "given in kJ/mol and divided by 4.184 (bind.core.KJ_PER_KCAL)" if unit == "kj" else None
    given_error = isinstance(request.get("computed"), Mapping) and request["computed"].get("error") is not None
    temps_used = [m.temperature_c for m in a.target.used if m.temperature_c is not None]
    if temps_used:
        temperature = contract.sourced(a.temperature_c, "°C", contract.computed(
            "the mean stated assay temperature of the rows used", []), ident="judged_at")
    else:
        temperature = contract.sourced(a.temperature_c, "°C", contract.chosen(
            "default", "no row used states its assay temperature; caterva bind judges at 25 °C"),
            ident="judged_at")
    gap_method = "distance from the computed value ± 2σ to the band's nearer edge (bind.core.judge)"
    return {
        "word": v.word,
        "gap_kcal": contract.sourced(v.gap_kcal, KCAL, contract.computed(
            gap_method, ["computed", "computed_error", "band_lowest", "band_highest"]), ident="gap"),
        "ki_fold": contract.sourced(v.ki_fold, "fold", contract.computed(
            "exp(gap / RT) at the judging temperature (bind.core.judge)", ["gap", "judged_at"]),
            ident="ki_fold"),
        "detail": v.detail,
        "computed": contract.sourced(value, KCAL, contract.chosen("user", converted), ident="computed"),
        "computed_error": contract.sourced(err, KCAL, contract.chosen(
            "user" if given_error else "default",
            converted if given_error else "no uncertainty was given, so caterva bind takes 0"),
            ident="computed_error"),
        "temperature_c": temperature,
    }


def survey_row(s: Any) -> contract.BindSurveyRow:
    """One bind.__main__.SurveyTarget: the band unrounded (the survey's text
    and --json round it to two decimals)."""
    inputs: List[str] = []
    return {
        "compound": s.compound, "organism": s.organism, "isoform": s.isoform,
        "rows": len(s.rows), "used": len(s.target.used), "references": list(s.target.references),
        "band_low": _edge(s.target.lo, "lowest", inputs),
        "band_high": _edge(s.target.hi, "highest", inputs),
        "benchmark": not s.why_not, "why_not": list(s.why_not),
    }


SPEC = AdapterSpec(
    kind=KIND,
    title="Binding free energy target",
    command="bind",
    needs=("network", "literature"),
    argv=argv,
    run=run,
    unavailable=unavailable,
    describe=describe,
    cli_prefix=("caterva", "bind"),
)


def register(registry: Any) -> None:
    registry.register(SPEC)
