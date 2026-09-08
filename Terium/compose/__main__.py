"""`python -m Terium.compose "three step phosphorylation cascade"`.

A capability nobody can reach is not a capability (ADR 0090). The
compositional builder is reachable from the API runner and from Python;
this is the surface a researcher at a terminal actually uses, and it needs
no server, no key and no network.
"""

from __future__ import annotations

import argparse
import sys
from typing import List, Optional, Sequence


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m Terium.compose",
        description=(
            "Build a mechanistic model from a description of its mechanism. "
            "Recognises shapes -- a cascade, a toggle switch, competition "
            "for a substrate -- deterministically, with no language model."
        ),
        epilog=(
            "Examples:\n"
            "  python -m Terium.compose 'three step phosphorylation cascade'\n"
            "  python -m Terium.compose 'a toggle switch between two repressors' --sweep geneA_n\n"
            "  python -m Terium.compose 'three step phosphorylation cascade' --rank-against tier2_Xp\n"
            "  python -m Terium.compose --shapes\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("description", nargs="?",
                        help="the mechanism to build")
    parser.add_argument("--subject",
                        help="the enzyme these constants belong to, if named")
    parser.add_argument("--shapes", action="store_true",
                        help="list every shape this can build, and exit")
    parser.add_argument("--antimony", action="store_true",
                        help="emit Antimony source instead of a report")
    parser.add_argument("--no-analysis", action="store_true",
                        help="skip the steady-state analysis (much faster)")
    parser.add_argument("--no-simulate", action="store_true",
                        help="skip the time course")
    parser.add_argument("--no-ranking", action="store_true",
                        help=("skip the influence ranking of the unmeasured "
                              "constants (it re-solves the steady state twice "
                              "per constant)"))
    parser.add_argument("--rank-against", metavar="SPECIES",
                        help=("rank influence on this species instead of the "
                              "one the last motif declares it produces"))
    parser.add_argument("--sweep", action="append", default=[], metavar="PARAM",
                        help="sweep this parameter and report bifurcations; repeatable")
    parser.add_argument("--sweep-from", type=float, default=0.1)
    parser.add_argument("--sweep-to", type=float, default=10.0)
    parser.add_argument("--sweep-steps", type=int, default=15)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    from Terium.compose.grammar import UnrecognisedShape, shapes

    if args.shapes:
        print("Shapes this builds:\n")
        for shape in shapes():
            print(f"  {shape}")
        print(
            "\nIt recognises a SHAPE, never a SUBJECT. 'three step "
            "phosphorylation cascade' builds; 'glycolysis' does not, and "
            "says why."
        )
        return 0

    if not args.description:
        parser.print_help()
        return 2

    try:
        if args.antimony:
            from Terium.compose.pipeline import compose
            from Terium.core.network import compile_to_antimony

            model = compose(args.description, subject=args.subject)
            print(compile_to_antimony(model.network))
            return 0

        from Terium.compose.report import dossier

        report = dossier(
            args.description,
            subject=args.subject,
            analyse_stability=not args.no_analysis,
            simulate=not args.no_simulate,
            sweep_parameters=args.sweep,
            sweep_range=(args.sweep_from, args.sweep_to),
            sweep_steps=args.sweep_steps,
            rank_unmeasured=not args.no_ranking,
            rank_against=args.rank_against,
        )
        print(report.markdown())
        return 0

    except UnrecognisedShape as exc:
        # Exit 3, not 1: this is a REFUSAL with information in it, not a
        # crash, and a script should be able to tell the two apart.
        print(f"Not built.\n\n{exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
