"""Command-line interface for Caterva's stochastic kinetics.

Usage:
    python -m caterva.cli ssa --a0 200 --k 0.5 --end 5 --seed 9
    python -m caterva.cli ssa --bimolecular --a0 60 --b0 40 --k 0.01 \
        --end 5 --seed 12345

The population-genetics commands (wf, kimura, ne, sweep, scenarios, ld)
were archived on 2026-09-27 with that domain; see archive/legacy_domains/.
"""

from __future__ import annotations

import argparse
import csv
import pathlib
import sys
from typing import Sequence

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


def _cmd_ssa(args: argparse.Namespace) -> int:
    try:
        if args.bimolecular:
            result = simulate_gillespie_ssa_bimolecular(
                a0=args.a0, b0=args.b0, k=args.k, end=args.end, seed=args.seed)
        else:
            result = simulate_gillespie_ssa(
                a0=args.a0, k=args.k, end=args.end, seed=args.seed)
    except ModelBuildError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if args.out:
        result.to_csv(args.out)
        print(f"wrote {args.out}")
        return 0
    header = list(result.colnames)
    print("  ".join(h.rjust(12) for h in header))
    step = max(1, len(result.data) // 12)
    for row in result.data[::step]:
        print("  ".join(f"{v:12.6f}" for v in row[:len(header)]))
    a0, k, end = args.a0, args.k, args.end
    n_events = len(result.data) - 2
    if args.bimolecular:
        print(f"\nA(0) = {a0}   B(0) = {args.b0}   events = {n_events}   "
              f"final A = {result.final('a'):.0f}   final B = "
              f"{result.final('b'):.0f}   final C = {result.final('c'):.0f}")
        a_end = result.final("a")
        if a0 == args.b0:
            expected = a0 / (1.0 + k * a0 * end)
        else:
            expected = (a0 - args.b0) / (
                1.0 - (args.b0 / a0) *
                __import__("math").exp(-k * (a0 - args.b0) * end))
        print(f"expected A(end) (ODE) = {expected:.1f}   observed = {a_end:.0f}")
    else:
        print(f"\nA(0) = {a0}   events = {n_events}   "
              f"final A = {result.final('a'):.0f}")
        expected = a0 * (1.0 - __import__("math").exp(-k * end))
        print(f"expected B(end) = a0*(1-e^(-k*end)) = {expected:.1f}")
    return 0


def main(argv: Sequence[str] | None = None, prog: str | None = None) -> int:
    """Run the Caterva CLI. `prog` is how the caller is invoked (`caterva`
    from the wheel, `caterva sim` from the app folder); default is the
    module form."""
    parser = argparse.ArgumentParser(
        prog=prog or "caterva.cli",
        description="Caterva stochastic chemical kinetics (exact Gillespie SSA)")
    sub = parser.add_subparsers(dest="command", required=True, metavar="{ssa}")
    _build_ssa_parser(sub)

    args = parser.parse_args(argv)
    return args.func(args)  # type: ignore[return-value]


def console_main() -> int:
    """Entry point of the `caterva` console script; `--help` says `caterva`."""
    return main(prog="caterva")


if __name__ == "__main__":
    sys.exit(main())

