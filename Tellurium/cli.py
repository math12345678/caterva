"""Command-line interface for the Tellurium simulation engine.

Usage:
    python -m Tellurium.cli scenarios
    python -m Tellurium.cli wf --population-size 100 --generations 200 --seed 42
    python -m Tellurium.cli wf --scenario bottleneck --out results.csv
    python -m Tellurium.cli kimura --p0 0.3 --s 0.03 --population-size 50
    python -m Tellurium.cli ne --file results.csv
    python -m Tellurium.cli ld --population-size 100 --generations 30 \
        --recombination-rate 0.1 --replicate-runs 3000 --seed 42
    python -m Tellurium.cli ssa --a0 200 --k 0.5 --end 5 --seed 9
"""

import argparse
import csv
import pathlib
import sys
from typing import Optional, Sequence

from Tellurium.tellurium_engine import (
    ModelBuildError,
    estimate_ne_from_heterozygosity,
    expected_fixation_time,
    kimura_fixation_probability,
    list_scenarios,
    simulate_gillespie_ssa,
    simulate_two_locus_wright_fisher,
    simulate_wright_fisher,
    theoretical_ld_decay,
    wright_fisher_expected_fixation_time,
    wright_fisher_fixation_probability,
    wright_fisher_scenario,
    wright_fisher_sweep,
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
                   help="dominance coefficient in [0,2]; omit for haploid "
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


def _build_sweep_parser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser(
        "sweep",
        help="run a Wright-Fisher simulation once per parameter value "
             "and print a summary table")
    p.add_argument("--parameter", metavar="NAME", required=True,
                   help="parameter to sweep, e.g. selection_coefficient, "
                        "migration_rate, population_size, mutation_rate, "
                        "dominance, starting_frequency")
    p.add_argument("--values", metavar="V1,V2,...", required=True,
                   help="comma-separated values to sweep over")
    p.add_argument("--population-size", type=int, metavar="N",
                   help="diploid census size per deme (default 100)")
    p.add_argument("--starting-frequency", type=float, metavar="P",
                   help="initial frequency of allele A (default 0.5)")
    p.add_argument("--generations", type=int, metavar="G",
                   help="number of generations (default 200)")
    p.add_argument("--replicate-runs", type=int, metavar="R",
                   help="number of replicate metapopulations (default 50)")
    p.add_argument("--mutation-rate", type=float, metavar="U",
                   help="per-generation symmetric mutation rate (default 0)")
    p.add_argument("--selection-coefficient", type=float, metavar="S",
                   help="selective advantage of allele A (default 0)")
    p.add_argument("--dominance", type=float, metavar="H",
                   help="dominance coefficient in [0,2]; omit for haploid")
    p.add_argument("--n-demes", type=int, metavar="D",
                   help="number of demes per replicate (default 1)")
    p.add_argument("--migration-rate", type=float, metavar="M",
                   help="fraction of alleles exchanged per generation "
                        "(default 0)")
    p.add_argument("--migration-model", metavar="MODEL",
                   help="'island' (global pool, default) or "
                        "'stepping-stone' (ring of neighbours)")
    p.add_argument("--seed", type=int, metavar="N",
                   help="RNG seed (shared across the sweep)")
    p.set_defaults(func=_cmd_sweep)


def _cmd_sweep(args: argparse.Namespace) -> int:
    try:
        values = [float(v) for v in args.values.split(",")]
    except ValueError:
        print("error: --values must be comma-separated numbers",
              file=sys.stderr)
        return 2
    try:
        rows = wright_fisher_sweep(
            args.parameter, values,
            population_size=args.population_size or 100,
            starting_frequency=args.starting_frequency or 0.5,
            generations=args.generations or 200,
            replicate_runs=args.replicate_runs or 50,
            mutation_rate=args.mutation_rate or 0.0,
            selection_coefficient=args.selection_coefficient or 0.0,
            dominance=args.dominance,
            n_demes=args.n_demes or 1,
            migration_rate=args.migration_rate or 0.0,
            migration_model=args.migration_model or "island",
            seed=args.seed,
        )
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    header = (f"{args.parameter:>22} {'p_final':>8} {'H_final':>8} "
              f"{'fixed_A':>8} {'fixed_a':>8}")
    if "final_fst" in rows[0]:
        header += f" {'Fst':>8}"
    print(header)
    for row in rows:
        line = (f"{row['value']:>22.6g} "
                f"{row['final_mean_frequency']:>8.4f} "
                f"{row['final_heterozygosity']:>8.4f} "
                f"{row['prop_fixed_A']:>8.3f} "
                f"{row['prop_fixed_a']:>8.3f}")
        if "final_fst" in row:
            line += f" {row['final_fst']:>8.4f}"
        print(line)
    return 0


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
                   help="dominance coefficient in [0,2]; omit for haploid")
    p.add_argument("--s-start", type=float, metavar="S",
                   help="sweep start (with --s-end/--s-steps)")
    p.add_argument("--s-end", type=float, metavar="S",
                   help="sweep end (inclusive)")
    p.add_argument("--s-steps", type=int, metavar="K", default=10,
                   help="number of sweep steps (default 10)")
    p.add_argument("--time", action="store_true",
                   help="also print the neutral expected fixation time "
                        "(Kimura & Ohta 1969)")
    p.add_argument("--exact", action="store_true",
                   help="also print the exact value from the "
                        "Wright-Fisher Markov chain (no diffusion "
                        "approximation): P_fix, and with --time also "
                        "the expected fixation time")
    p.set_defaults(func=_cmd_kimura)


def _cmd_kimura(args: argparse.Namespace) -> int:
    try:
        if args.s is not None:
            p = kimura_fixation_probability(
                args.p0, args.s, args.population_size, args.h)
            print(f"P_fix = {p:.6f}")
            if args.exact:
                p_exact = wright_fisher_fixation_probability(
                    args.p0, args.population_size, args.s, args.h)
                print(f"P_fix (exact WF chain) = {p_exact:.6f}")
            if args.time:
                t = expected_fixation_time(args.p0, args.population_size)
                print(f"t_fix (neutral, given fixation) = {t:.2f}")
                if args.exact:
                    t_exact = wright_fisher_expected_fixation_time(
                        args.p0, args.population_size, args.s, args.h)
                    print(f"t_fix (exact WF chain) = {t_exact:.2f}")
        elif args.s_start is not None and args.s_end is not None:
            print(f"{'s':>10} {'P_fix':>10}")
            for i in range(args.s_steps):
                s = args.s_start + (args.s_end - args.s_start) * i / max(
                    1, args.s_steps - 1)
                p = kimura_fixation_probability(
                    args.p0, s, args.population_size, args.h)
                print(f"{s:>10.4f} {p:>10.6f}")
            if args.time:
                t = expected_fixation_time(args.p0, args.population_size)
                print(f"t_fix (neutral, given fixation) = {t:.2f}")
            if args.exact:
                print("exact WF-chain values: use a single --s value")
        else:
            print("error: give --s OR --s-start/--s-end", file=sys.stderr)
            return 2
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


def _cmd_scenarios(_args: argparse.Namespace) -> int:
    from Tellurium.tellurium_engine import _SCENARIO_REGISTRY  # noqa: PLC0415
    for name in list_scenarios():
        desc = _SCENARIO_REGISTRY[name].get("description", "")
        print(f"{name:<22} {desc}")
    return 0


def _build_ne_parser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser(
        "ne",
        help="estimate effective population size from a saved CSV "
             "(wf --out FILE)")
    p.add_argument("--file", metavar="FILE", required=True,
                   help="CSV written by 'wf --out' (needs a "
                        "heterozygosity column)")
    p.set_defaults(func=_cmd_ne)


def _cmd_ne(args: argparse.Namespace) -> int:
    try:
        with pathlib.Path(args.file).open(newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            if not reader.fieldnames or "heterozygosity" not in reader.fieldnames:
                print("error: CSV has no 'heterozygosity' column",
                      file=sys.stderr)
                return 1
            values = [float(row["heterozygosity"]) for row in reader]
    except OSError as exc:
        print(f"error: cannot read {args.file}: {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"error: malformed CSV: {exc}", file=sys.stderr)
        return 1
    est = estimate_ne_from_heterozygosity(values)
    if "error" in est:
        print(f"error: {est['error']}", file=sys.stderr)
        return 1
    print(f"Ne estimate (heterozygosity decay) = {est['ne_estimate']:.2f}")
    print(f"decay rate per generation         = "
          f"{est['decay_rate_per_generation']:.6f}")
    print(f"generations used                  = {est['n_generations_used']}")
    print(f"note: {est['note']}")
    return 0


def _build_ld_parser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser(
        "ld", help="two-locus simulation: linkage disequilibrium decay")
    p.add_argument("--population-size", type=int, metavar="N",
                   default=100, help="haploid census size (default 100)")
    p.add_argument("--generations", type=int, metavar="G", default=20,
                   help="number of generations (default 20)")
    p.add_argument("--recombination-rate", type=float, metavar="R",
                   default=0.1, help="recombination fraction in [0, 0.5] "
                                     "(default 0.1)")
    p.add_argument("--mutation-rate", type=float, metavar="U",
                   default=0.0, help="per-copy symmetric mutation rate "
                                     "per locus in [0, 1] (default 0)")
    p.add_argument("--starting-frequencies", metavar="F1,F2,F3,F4",
                   default="0.5,0,0,0.5",
                   help="haplotype frequencies (AB, Ab, aB, ab) summing "
                        "to 1 (default 0.5,0,0,0.5 -- full coupling, "
                        "D0 = 0.25)")
    p.add_argument("--replicate-runs", type=int, metavar="R", default=50,
                   help="number of replicates (default 50)")
    p.add_argument("--seed", type=int, metavar="N",
                   help="RNG seed for reproducibility")
    p.add_argument("--out", metavar="FILE",
                   help="write the result table to CSV")
    p.set_defaults(func=_cmd_ld)


def _cmd_ld(args: argparse.Namespace) -> int:
    try:
        freqs = tuple(float(x) for x in
                      args.starting_frequencies.split(","))
    except ValueError:
        print("error: --starting-frequencies must be four numbers",
              file=sys.stderr)
        return 1
    try:
        result = simulate_two_locus_wright_fisher(
            population_size=args.population_size,
            generations=args.generations,
            recombination_rate=args.recombination_rate,
            starting_frequencies=freqs,
            mutation_rate=args.mutation_rate,
            replicate_runs=args.replicate_runs,
            seed=args.seed)
    except ModelBuildError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    header = ["generation", "mean_D", "mean_r2", "mean_freq_A",
              "mean_freq_B"]
    print("  ".join(h.rjust(12) for h in header))
    for row in result.data:
        print("  ".join(f"{v:12.6f}" for v in row[:len(header)]))
    la = result.ld_analysis()
    t = args.generations
    expect = theoretical_ld_decay(
        la["d_initial"], args.recombination_rate, t,
        args.population_size, args.mutation_rate)
    print(f"\nD0 = {la['d_initial']:.6f}")
    print(f"final mean D = {la['d_final']:.6f} "
          f"(expected {expect:.6f})")
    print(f"decay factor (observed) = {la['decay_factor']:.6f} "
          f"(theory (1-r)^t*(1-2u)^(2t)*(1-1/N)^t = "
          f"{expect / la['d_initial']:.6f})")
    return 0


def _build_ssa_parser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser(
        "ssa", help="Gillespie SSA: exact stochastic A -> B decay")
    p.add_argument("--a0", type=int, metavar="A0", default=1000,
                   help="initial A molecules (default 1000)")
    p.add_argument("--k", type=float, metavar="K", default=0.5,
                   help="per-molecule decay rate (default 0.5)")
    p.add_argument("--end", type=float, metavar="T", default=10.0,
                   help="simulation time (default 10)")
    p.add_argument("--seed", type=int, metavar="N",
                   help="RNG seed for reproducibility")
    p.add_argument("--out", metavar="FILE",
                   help="write the result table to CSV")
    p.set_defaults(func=_cmd_ssa)


def _cmd_ssa(args: argparse.Namespace) -> int:
    try:
        result = simulate_gillespie_ssa(
            a0=args.a0, k=args.k, end=args.end, seed=args.seed)
    except ModelBuildError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    header = ["time", "a", "b"]
    print("  ".join(h.rjust(12) for h in header))
    step = max(1, len(result.data) // 12)
    for row in result.data[::step]:
        print("  ".join(f"{v:12.6f}" for v in row[:len(header)]))
    a0, k, end = args.a0, args.k, args.end
    expected = a0 * (1.0 - __import__("math").exp(-k * end))
    n_events = len(result.data) - 2
    print(f"\nA(0) = {a0}   events = {n_events}   "
          f"final A = {result.final('a'):.0f}")
    print(f"expected B(end) = a0*(1-e^(-k*end)) = {expected:.1f}")
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Run the Tellurium CLI."""
    parser = argparse.ArgumentParser(
        prog="Tellurium.cli",
        description="Tellurium simulation engine command line")
    sub = parser.add_subparsers(dest="command", required=True,
                                metavar="{wf,kimura,ne,sweep,scenarios,ld,ssa}")
    _build_wf_parser(sub)
    _build_sweep_parser(sub)
    _build_kimura_parser(sub)
    _build_ne_parser(sub)
    _build_ld_parser(sub)
    _build_ssa_parser(sub)
    sub.add_parser("scenarios", help="list WF scenario presets").set_defaults(
        func=_cmd_scenarios)

    args = parser.parse_args(argv)
    return args.func(args)  # type: ignore[return-value]


if __name__ == "__main__":
    sys.exit(main())
