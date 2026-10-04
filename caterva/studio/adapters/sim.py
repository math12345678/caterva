"""Kind `sim`: `caterva sim ssa`, exact Gillespie SSA, seeded (owner: sci-kinetics).

WHAT IT CALLS
    `caterva.cli.simulate(args)` (the engine's simulate_gillespie_ssa or
    simulate_gillespie_ssa_bimolecular, chosen as the command chooses),
    `caterva.cli.expectation(args, result)` for the event count and the ODE
    expectation printed under the table, and `caterva.cli.report(args,
    result)` for the text the command prints. The expectation used to be
    computed inside the printing code; it is now a function the printer and
    this adapter both read, so the number on the page is the number the
    terminal shows.

WHY THE SEED IS REQUIRED HERE
    The command runs unseeded when --seed is absent. A trajectory whose seed
    is not recorded cannot be produced again (ADR 0005), and History exists
    to reopen and rerun runs, so a studio request without a seed is
    malformed. The page prefills one and shows it.

WHAT EACH NUMBER IS
    The inputs are `chosen`: by the user when the request names them, by the
    command's argparse default otherwise. A CLI defect is carried, not
    copied: --k defaults to 0.5 for the bimolecular reaction too, while its
    help says 0.005, so a default k is labelled with the default the parser
    really applied and the page always sends k. The final counts and the
    expectation are `computed`, each naming how. The trajectory rows are
    the engine's own rows; past contract.SERIES_ROW_LIMIT they are thinned
    to every n-th row plus the last (`rows`, `every` say so) and the whole
    table is the CSV artefact.

WHAT IS REFUSED
    --out (the table is the result and an artefact). Parameters the engine
    refuses (a negative k, a zero population) are refused at submission with
    the engine's own message, through the same validation the engine runs.
    A request expected to make more than contract.MAX_SSA_EVENTS reaction
    events is refused too, with that number in the message: the table holds
    a row per event in memory, and a library call cannot be killed.

HOW A CANCEL REACHES THE LOOP
    The SSA loop polls `should_stop` every few hundred events; the adapter
    passes `ctx.progress.is_cancelled`, so a cancelled run stops inside the
    simulation within milliseconds, not at the end of it. The loop is also
    given a hard event bound (a little above the limit) so a trajectory that
    runs away from its expectation stops by itself.
"""
from __future__ import annotations

import argparse
import csv
import io
import math
from typing import Any, Dict, List, Mapping

from caterva.studio import contract
from caterva.studio.adapters import AdapterOutcome, AdapterSpec, Artifact, Cancelled, RunContext, cli_parser
from caterva.studio.adapters.compose import every_for, thinned_indices

KIND = "sim"
PROG = "caterva sim"
_KEYS = frozenset(("seed", "bimolecular", "a0", "b0", "k", "end"))
_INTEGERS = ("seed", "a0", "b0")
_NUMBERS = ("k", "end")

#: What each input is, for the page: unit and what the command's help calls it.
_UNITS = {"a0": "molecules", "b0": "molecules", "end": "time units"}


def _k_unit(bimolecular: bool) -> str:
    return "per molecule pair per time unit" if bimolecular else "per molecule per time unit"


def _integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def argv_of(request: Mapping[str, Any]) -> List[str]:
    """`ssa` first, then one flag per key; never --out."""
    if not isinstance(request, Mapping):
        raise contract.Malformed("a sim request is a JSON object")
    for key in request:
        if key not in _KEYS:
            raise contract.Malformed(f"{key} is not a sim request key", field=key)
    if "seed" not in request or request["seed"] is None:
        raise contract.Malformed(
            "seed is required: a trajectory whose seed is not recorded cannot be "
            "reproduced (ADR 0005)", field="seed")
    out = ["ssa"]
    bimolecular = request.get("bimolecular")
    if bimolecular is not None and not isinstance(bimolecular, bool):
        raise contract.Malformed("bimolecular must be true or false", field="bimolecular")
    if bimolecular:
        out.append("--bimolecular")
    for key in ("a0", "b0", "k", "end", "seed"):
        value = request.get(key)
        if value is None:
            continue
        if key in _INTEGERS and not _integer(value):
            raise contract.Malformed(f"{key} must be an integer", field=key)
        if key in _NUMBERS and (isinstance(value, bool) or not isinstance(value, (int, float))):
            raise contract.Malformed(f"{key} must be a number", field=key)
        text = repr(float(value)) if key in _NUMBERS else str(int(value))
        out.append(f"--{key}={text}")
    return out


def _parsed(argv: List[str]) -> argparse.Namespace:
    from caterva.cli import build_parser

    return cli_parser(build_parser, PROG).parse_args(argv)


def argv(request: Mapping[str, Any]) -> List[str]:
    """The argv, accepted by the command's parser and by the engine's own
    parameter validation (what the command reports as `error: ...`)."""
    out = argv_of(request)
    args = _parsed(out)
    from caterva.caterva_engine import ModelBuildError
    from caterva.core.validation import validate_ssa_bimolecular_params, validate_ssa_params

    validation = (validate_ssa_bimolecular_params(args.a0, args.b0, args.k, args.end)
                  if args.bimolecular else validate_ssa_params(args.a0, args.k, args.end))
    try:
        validation.raise_if_invalid()
    except ModelBuildError as exc:
        raise contract.Malformed(f"error: {exc}") from exc
    refuse_if_too_long(args)
    return out


def expected_events(a0: float, b0: float, k: float, end: float, bimolecular: bool) -> float:
    """How many reaction events the run is expected to make: the molecules the
    deterministic solution consumes by `end` (never more than the molecules
    there are to react). The loop's work, and the table's rows, scale with it."""
    if not bimolecular:
        return a0 * (1.0 - math.exp(-k * end))
    limit = float(min(a0, b0))
    try:
        if a0 == b0:
            left = a0 / (1.0 + k * a0 * end)
        else:
            left = (a0 - b0) / (1.0 - (b0 / a0) * math.exp(-k * (a0 - b0) * end))
        consumed = a0 - left
    except (OverflowError, ZeroDivisionError):
        return limit
    if math.isnan(consumed):
        return limit
    return max(0.0, min(consumed, limit))


def refuse_if_too_long(args: argparse.Namespace) -> None:
    """Malformed, naming the limit, when the run would make too many events."""
    events = expected_events(args.a0, args.b0 if args.bimolecular else 0, args.k, args.end,
                             bool(args.bimolecular))
    if events > contract.MAX_SSA_EVENTS:
        raise contract.Malformed(
            f"this run is expected to make about {events:,.0f} reaction events (a0 {args.a0:,}, k {args.k:g}, "
            f"end {args.end:g}); a run is limited to {contract.MAX_SSA_EVENTS:,}. Lower a0, k or end.",
            field="a0")


def describe(request: Mapping[str, Any]) -> str:
    reaction = "A + B -> C" if request.get("bimolecular") else "A -> B"
    return f"Gillespie SSA, {reaction}, seed {request.get('seed')}"


def run(request: Mapping[str, Any], ctx: RunContext) -> AdapterOutcome:
    from caterva.caterva_engine import ModelBuildError
    from caterva.cli import expectation, report, simulate
    from caterva.discrete.gillespie_ssa import SimulationCancelled, SimulationTooLong

    args = _parsed(argv_of(request))
    refuse_if_too_long(args)
    ctx.progress.check_cancelled()
    ctx.progress.stage("simulate", "Running the exact stochastic simulation", None)
    try:
        result = simulate(args, should_stop=getattr(ctx.progress, "is_cancelled", None),
                          max_events=int(contract.MAX_SSA_EVENTS * 1.25))
    except ModelBuildError as exc:
        raise contract.Malformed(f"error: {exc}") from exc
    except SimulationCancelled:
        raise Cancelled(ctx.run_id) from None
    except SimulationTooLong as exc:
        raise contract.Malformed(f"{exc}; a run is limited to {contract.MAX_SSA_EVENTS:,} expected events",
                                 field="a0") from None
    summary = expectation(args, result)
    text = report(args, result)
    out = sim_result(request, args, result, summary, text)
    table = io.StringIO(newline="")
    writer = csv.writer(table)
    writer.writerow(result.colnames)
    writer.writerows(result.data)
    artifact = Artifact("trajectory.csv", table.getvalue().encode("utf-8"),
                        "text/csv; charset=utf-8",
                        "every row of the event table (caterva sim ssa --out FILE)")
    line = (f"{out['events']} events, seed {args.seed}; expected {summary['quantity'].upper()}(end) "
            f"(ODE) {summary['expected']:.1f}")
    return AdapterOutcome(exit_code=0, result=out, summary=line, artifacts=(artifact,))


def sim_result(request: Mapping[str, Any], args: argparse.Namespace, result: Any,
               summary: Mapping[str, Any], text: str) -> contract.SimResult:
    """The SimResult for one run: the engine's rows, the inputs as chosen,
    and the summary the printer prints."""
    columns = list(result.colnames)
    rows = len(result.data)
    indices = thinned_indices(rows)
    series: Dict[str, List[Any]] = {
        name: [contract.jsonable(result.data[i][j]) for i in indices]
        for j, name in enumerate(columns)
    }
    names = ["a0", "b0", "k", "end"] if args.bimolecular else ["a0", "k", "end"]
    parameters: Dict[str, contract.SourcedValue] = {}
    for name in names:
        given = request.get(name) is not None
        reason = None if given else f"the default of caterva sim ssa --{name}"
        unit = _k_unit(bool(args.bimolecular)) if name == "k" else _UNITS[name]
        parameters[name] = contract.sourced(
            getattr(args, name), unit, contract.chosen("user" if given else "default", reason),
            ident=name)
    method = f"exact stochastic simulation (Gillespie SSA), seed {args.seed}"
    final = {
        name: contract.sourced(result.final(name), "molecules",
                               contract.computed(method, inputs=names), ident=f"final_{name}")
        for name in columns if name != "time"
    }
    quantity = summary["quantity"]
    expected = contract.sourced(
        summary["expected"], "molecules",
        contract.computed(f"ODE expectation {quantity.upper()}(end) = {summary['formula']}",
                          inputs=names),
        ident=f"expected_{quantity}", label=f"expected {quantity.upper()}(end) (ODE)")
    return {
        "columns": columns,
        "series": series,
        "events": int(summary["events"]),
        "seed": int(args.seed),
        "parameters": parameters,
        "final": final,
        "expected": expected,
        "report_text": text,
        "rows": rows,
        "every": every_for(rows),
    }


SPEC = AdapterSpec(
    kind=KIND,
    title="Stochastic simulation",
    command="sim",
    needs=(),
    argv=argv,
    run=run,
    describe=describe,
    cli_prefix=("caterva", "sim"),
    serial=True,
)


def register(registry: Any) -> None:
    registry.register(SPEC)
