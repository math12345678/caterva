"""Command-line interface for the Tellurium simulation engine.

Usage:
    python -m Tellurium.cli scenarios
    python -m Tellurium.cli wf --population-size 100 --generations 200 --seed 42
    python -m Tellurium.cli wf --scenario bottleneck --out results.csv
    python -m Tellurium.cli kimura --p0 0.3 --s 0.03 --population-size 50
"""

import argparse
import json
import sys
from typing import Optional, Sequence

from Tellurium.tellurium_engine import (
    ModelBuildError,
    kimura_fixation_probability,
    list_scenarios,
    simulate_wright_fisher,
    wright_fisher_scenario,
)


def _build_wf_parser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("wf", help="run a Wright-Fisher simulation")
    p.add_argument("--scenario", metavar="NAME",
                   help="named scenario preset (see 'scenarios' command); "
                        "any of the options below override the preset")
    p.add_argument("--population-size", type=int, metavar="N",
                   help="diploid census size per deme")
    p.add_argument("--starting-frequency", type=float, metavar="P",
                   help="initial frequency of allele A (default 0.5)")
    p.add_argument("--generations", type=int, metavar="G",
                   help="number of generations")
    p.add_argument("--replicate-runs", type=int, metavar="R",
                   help="number of replicate metapopulations (default 50)")
    p.add_argument("--mutation-rate", type=float, metavar="U",
                   help="per-generation symmetric mutation rate (default 0)")
    p.add_argument("--selection-coefficient", type=float, metavar="S",
                   help="selective advantage of allele A (default 0)")
    p.add_argument("--dominance", type=float, metavar="H",
                   help="dominance coefficient in [0,1]; omit for haploid "
                        "selection")
    p.add_argument("--n-demes", type=int, metavar="D",
                   help="number of demes per replicate (default 1)")
    p.add_argument("--migration-rate", type=float, metavar="M",
                   help="fraction of alleles exchanged per generation "
                        "(default 0)")
    p.add_argument("--migration-model", metavar="MODEL",
                   help="'island' (global pool, default) or "
                        "'stepping-stone' (ring of neighbours)")
    p.add_argument("--seed", type=int, metavar="N",
                   help="RNG seed for reproducibility")
    p.add_argument("--out", metavar="FILE",
                   help="write the result table to CSV")
    p.add_argument("--json", dest="json_out", metavar="FILE",
                   help="write the full result (incl. parameters, fixation "
                        "analysis) to JSON")
    p.add_argument("--replicate-data", action="store_true",
                   help="record per-replicate trajectories")
    p.add_argument("--verbose", action="store_true",
                   help="print progress every 10 % of generations")
    p.add_argument("--quiet", action="store_true",
                   help="suppress the summary output")
    p.set_defaults(func=_cmd_wf)


def _cmd_wf(args: argparse.Namespace) -> int:
    if args.scenario:
        params = {"name": args.scenario}
    else:
        missing = []
        if args.population_size is None:
            missing.append("--population-size")
        if args.generations is None:
            missing.append("--generations")
        if missing:
            print(f"error: missing required arguments: {', '.join(missing)} "
                  f"(or use --scenario)", file=sys.stderr)
            return 2
        params = {
            "population_size": args.population_size,
            "starting_frequency": (args.starting_frequency
                                   if args.starting_frequency is not None
                                   else 0.5),
            "generations": args.generations,
        }

    overrides: dict = {}
    for dest, attr in (
        ("population_size", "population_size"),
        ("starting_frequency", "starting_frequency"),
        ("generations", "generations"),
        ("replicate_runs", "replicate_runs"),
        ("mutation_rate", "mutation_rate"),
        ("selection_coefficient", "selection_coefficient"),
        ("dominance", "dominance"),
        ("n_demes", "n_demes"),
        ("migration_rate", "migration_rate"),
        ("migration_model", "migration_model"),
    ):
        value = getattr(args, attr)
        if value is not None:
            overrides[dest] = value

    try:
        if args.scenario:
            result = wright_fisher_scenario(
                name=args.scenario,
                seed=args.seed,
                return_replicate_data=args.replicate_data,
                **overrides)
        else:
            for key in ("population_size", "starting_frequency",
                        "generations"):
                overrides.pop(key, None)
            result = simulate_wright_fisher(
                **params, seed=args.seed,
                return_replicate_data=args.replicate_data,
                verbose=args.verbose, **overrides)
    except (ModelBuildError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if not args.quiet:
        print(result.describe())

    if args.out:
        result.to_csv(args.out, include_replicate_data=args.replicate_data)
        print(f"wrote {args.out}")
    if args.json_out:
        result.to_json(args.json_out,
                       include_replicate_data=args.replicate_data)
        print(f"wrote {args.json_out}")
    return 0


def _build_kimura_parser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser(
        "kimura",
        help="compute Kimura's fixation probability under selection")
    p.add_argument("--p0", type=float, required=True,
                   help="initial frequency of allele A")
    p.add_argument("--s", type=float,
                   help="selection coefficient (single value)")
    p.add_argument("--population-size", type=int, required=True,
                   help="diploid census size N")
    p.add_argument("--h", type=float, metavar="H",
                   help="dominance coefficient in [0,1]; omit for haploid")
    p.add_argument("--s-start", type=float, metavar="S",
                   help="sweep start (with --s-end/--s-steps)")
    p.add_argument("--s-end", type=float, metavar="S",
                   help="sweep end (inclusive)")
    p.add_argument("--s-steps", type=int, metavar="K", default=10,
                   help="number of sweep steps (default 10)")
    p.set_defaults(func=_cmd_kimura)


def _cmd_kimura(args: argparse.Namespace) -> int:
    try:
        if args.s is not None:
            p = kimura_fixation_probability(
                args.p0, args.s, args.population_size, args.h)
            print(f"P_fix = {p:.6f}")
        elif args.s_start is not None and args.s_end is not None:
            print(f"{'s':>10} {'P_fix':>10}")
            for i in range(args.s_steps):
                s = args.s_start + (args.s_end - args.s_start) * i / max(
                    1, args.s_steps - 1)
                p = kimura_fixation_probability(
                    args.p0, s, args.population_size, args.h)
                print(f"{s:>10.4f} {p:>10.6f}")
        else:
            print("error: give --s OR --s-start/--s-end", file=sys.stderr)
            return 2
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


def _cmd_scenarios(args: argparse.Namespace) -> int:
    from Tellurium.tellurium_engine import _SCENARIO_REGISTRY
    for name in list_scenarios():
        desc = _SCENARIO_REGISTRY[name].get("description", "")
        print(f"{name:<22} {desc}")
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="Tellurium.cli",
        description="Tellurium simulation engine command line")
    sub = parser.add_subparsers(dest="command", required=True,
                                metavar="{wf,kimura,scenarios}")
    _build_wf_parser(sub)
    _build_kimura_parser(sub)
    sub.add_parser("scenarios", help="list WF scenario presets").set_defaults(
        func=_cmd_scenarios)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
