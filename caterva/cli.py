"""Command-line interface for Caterva's stochastic kinetics.

Usage:
    python -m caterva.cli ssa --a0 200 --k 0.5 --end 5 --seed 9
    python -m caterva.cli ssa --bimolecular --a0 60 --b0 40 --k 0.01 \
        --end 5 --seed 12345

The population-genetics commands (wf, kimura, ne, sweep, scenarios, ld)
were archived on 2026-09-27 with that domain; see archive/legacy_domains/.

The run, the numbers printed under the table (the event count and the ODE
expectation) and the printed text are three functions, `simulate`,
`expectation` and `report`. The expectation used to be computed inside the
print statements, so Caterva Studio (caterva/studio/adapters/sim.py) could
only have shown it by computing it again; it reads these instead, and the
command's output is byte for byte what it was.
"""

from __future__ import annotations

import argparse
import csv
import math
import pathlib
import sys
from typing import Any, Dict, Sequence

from caterva.caterva_engine import (
    ModelBuildError,
    simulate_gillespie_ssa,
    simulate_gillespie_ssa_bimolecular,
)


def _build_ssa_parser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser(
        "ssa", help="Gillespie SSA: exact stochastic A -> B decay "
                    "(or A + B -> C association with --bimolecular)")
    p.add_argument("--bimolecular", action="store_true",
                   help="simulate the bimolecular association A + B -> C "
                        "instead of first-order decay")
    p.add_argument("--a0", type=int, metavar="A0", default=1000,
                   help="initial A molecules (default 1000)")
    p.add_argument("--b0", type=int, metavar="B0", default=100,
                   help="initial B molecules (bimolecular only, default 100)")
    p.add_argument("--k", type=float, metavar="K", default=0.5,
                   help="rate constant: per-molecule decay (default 0.5) or "
                        "per-molecule-pair association (default 0.005)")
    p.add_argument("--end", type=float, metavar="T", default=10.0,
                   help="simulation time (default 10)")
    p.add_argument("--seed", type=int, metavar="N",
                   help="RNG seed for reproducibility")
    p.add_argument("--out", metavar="FILE",
                   help="write the result table to CSV")
    p.set_defaults(func=_cmd_ssa)


def simulate(args: argparse.Namespace):
    """The SSA run `args` asks for: the engine's SimulationResult.

    Raises ModelBuildError for parameters the engine refuses."""
    if args.bimolecular:
        return simulate_gillespie_ssa_bimolecular(
            a0=args.a0, b0=args.b0, k=args.k, end=args.end, seed=args.seed)
    return simulate_gillespie_ssa(a0=args.a0, k=args.k, end=args.end, seed=args.seed)


def expectation(args: argparse.Namespace, result) -> Dict[str, Any]:
    """What the summary lines under the table report, as numbers.

    `events` is the event count (the table holds the initial row, one row
    per event and the final row snapped to `end`). `expected` is the
    deterministic (ODE) value printed beside the run: A(end) for the
    bimolecular association, B(end) for first-order decay; `quantity`
    names which, and `formula` is the expression printed or used. The
    printer reads these; nothing else computes them.
    """
    a0, k, end = args.a0, args.k, args.end
    n_events = len(result.data) - 2
    if args.bimolecular:
        if a0 == args.b0:
            expected = a0 / (1.0 + k * a0 * end)
            formula = "a0/(1+k*a0*end)"
        else:
            expected = (a0 - args.b0) / (
                1.0 - (args.b0 / a0) * math.exp(-k * (a0 - args.b0) * end))
            formula = "(a0-b0)/(1-(b0/a0)*e^(-k*(a0-b0)*end))"
        return {"events": n_events, "quantity": "a", "expected": expected,
                "formula": formula}
    expected = a0 * (1.0 - math.exp(-k * end))
    return {"events": n_events, "quantity": "b", "expected": expected,
            "formula": "a0*(1-e^(-k*end))"}


def report(args: argparse.Namespace, result) -> str:
    """The text `caterva sim ssa` prints without --out: every 12th row of
    the table, then the counts and the ODE expectation."""
    lines = []
    header = list(result.colnames)
    lines.append("  ".join(h.rjust(12) for h in header))
    step = max(1, len(result.data) // 12)
    for row in result.data[::step]:
        lines.append("  ".join(f"{v:12.6f}" for v in row[:len(header)]))
    summary = expectation(args, result)
    a0, n_events, expected = args.a0, summary["events"], summary["expected"]
    if args.bimolecular:
        lines.append(f"\nA(0) = {a0}   B(0) = {args.b0}   events = {n_events}   "
                     f"final A = {result.final('a'):.0f}   final B = "
                     f"{result.final('b'):.0f}   final C = {result.final('c'):.0f}")
        lines.append(f"expected A(end) (ODE) = {expected:.1f}   "
                     f"observed = {result.final('a'):.0f}")
    else:
        lines.append(f"\nA(0) = {a0}   events = {n_events}   "
                     f"final A = {result.final('a'):.0f}")
        lines.append(f"expected B(end) = a0*(1-e^(-k*end)) = {expected:.1f}")
    return "\n".join(lines)


def _cmd_ssa(args: argparse.Namespace) -> int:
    try:
        result = simulate(args)
    except ModelBuildError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if args.out:
        result.to_csv(args.out)
        print(f"wrote {args.out}")
        return 0
    print(report(args, result))
    return 0


def build_parser(prog: str | None = None) -> argparse.ArgumentParser:
    """The `sim` parser. `prog` is how the caller is invoked (`caterva`
    from the wheel, `caterva sim` from the app folder); default is the
    module form."""
    parser = argparse.ArgumentParser(
        prog=prog or "caterva.cli",
        description="Caterva stochastic chemical kinetics (exact Gillespie SSA)")
    sub = parser.add_subparsers(dest="command", required=True, metavar="{ssa}")
    _build_ssa_parser(sub)
    return parser


def main(argv: Sequence[str] | None = None, prog: str | None = None) -> int:
    """Run the Caterva CLI. `prog` is how the caller is invoked (`caterva`
    from the wheel, `caterva sim` from the app folder); default is the
    module form."""
    args = build_parser(prog).parse_args(argv)
    return args.func(args)  # type: ignore[return-value]


def console_main() -> int:
    """Entry point of the `caterva` console script; `--help` says `caterva`."""
    return main(prog="caterva")


if __name__ == "__main__":
    sys.exit(main())

