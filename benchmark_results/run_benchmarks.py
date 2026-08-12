#!/usr/bin/env python3
"""Regenerate benchmark_results.{csv,json} by actually running the engine.

WHY THIS EXISTS

`benchmark_results.csv` and `.json` were committed with 33 rows of timings
and no way to reproduce them. That is a problem in this repository
specifically, because `PERFORMANCE_BENCHMARKING_GUIDE.md` opens with a
hand-written banner admitting that no benchmark in it was ever run and every
latency figure was invented.

Numbers you cannot regenerate are indistinguishable from numbers somebody
made up. This closes that: every row below comes from calling the engine.

WHAT IT MEASURES, AND WHAT THAT IS WORTH

Wall-clock time for one `simulate_*` call, repeated `--repeats` times, with
the mean and sample standard deviation reported alongside **every raw
timing** — not just the summary. A mean of three runs hides a 10x outlier;
the raw list does not.

It does NOT claim to be a rigorous performance benchmark:

  * no warm-up, so the first call carries import and JIT costs
  * a shared machine's scheduling noise is not controlled for
  * the parameter sets are illustrative sizes, not a workload model

Those are real limitations and are stated here rather than implied away. The
honest use of this file is *relative*: "did this change make the SSA path
slower", not "Terrium runs SIR in 23 ms".

Usage:
    python benchmark_results/run_benchmarks.py            # rewrite both files
    python benchmark_results/run_benchmarks.py --check    # compare, do not write
    python benchmark_results/run_benchmarks.py --repeats 5
"""

from __future__ import annotations

import argparse
import csv
import json
import pathlib
import statistics
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
sys.path.insert(0, str(REPO_ROOT))

from Terium import terium_engine as te  # noqa: E402

#: domain -> {size: kwargs}. Every parameter is supplied explicitly: the
#: engine refuses to default an experimental condition (ADR 0012/0013), and
#: a benchmark that relied on a default would be timing a code path no user
#: can reach.
WORKLOADS: dict[str, tuple[object, dict[str, dict]]] = {
    "michaelis_menten": (
        te.simulate_michaelis_menten,
        {
            "small":  dict(km=2.0, vmax=5.0, s0=10.0, end=10.0, points=51),
            "medium": dict(km=2.0, vmax=5.0, s0=10.0, end=100.0, points=501),
            "large":  dict(km=2.0, vmax=5.0, s0=10.0, end=1000.0, points=5001),
        },
    ),
    "competitive_inhibition": (
        te.simulate_mm_competitive_inhibition,
        {
            "small":  dict(km=2.0, ki=1.0, vmax=5.0, s0=10.0, i=0.1, end=10.0, points=51),
            "medium": dict(km=2.0, ki=1.0, vmax=5.0, s0=10.0, i=0.1, end=100.0, points=501),
            "large":  dict(km=2.0, ki=1.0, vmax=5.0, s0=10.0, i=0.1, end=1000.0, points=5001),
        },
    ),
    "sir": (
        te.simulate_sir,
        {
            "small":  dict(beta=0.3, gamma=0.1, s0=990, i0=10, r0_recovered=0, end=10.0, points=51),
            "medium": dict(beta=0.3, gamma=0.1, s0=990, i0=10, r0_recovered=0, end=100.0, points=501),
            "large":  dict(beta=0.3, gamma=0.1, s0=990, i0=10, r0_recovered=0, end=1000.0, points=5001),
        },
    ),
    "seir": (
        te.simulate_seir,
        {
            "small":  dict(beta=0.3, sigma=0.2, gamma=0.1, s0=990, e0=10, i0=1, end=10.0, points=51),
            "medium": dict(beta=0.3, sigma=0.2, gamma=0.1, s0=990, e0=10, i0=1, end=100.0, points=501),
            "large":  dict(beta=0.3, sigma=0.2, gamma=0.1, s0=990, e0=10, i0=1, end=1000.0, points=5001),
        },
    ),
    "pcr": (
        te.simulate_pcr,
        {
            "small":  dict(n0=100, efficiency=0.95, cycles=20),
            "medium": dict(n0=100, efficiency=0.95, cycles=35),
            "large":  dict(n0=100, efficiency=0.95, cycles=50),
        },
    ),
    "monte_carlo_pi": (
        te.simulate_monte_carlo_pi,
        {
            "small":  dict(n_samples=10_000, seed=42),
            "medium": dict(n_samples=100_000, seed=42),
            "large":  dict(n_samples=1_000_000, seed=42),
        },
    ),
    "wright_fisher": (
        te.simulate_wright_fisher,
        {
            "small":  dict(population_size=100, generations=100, starting_frequency=0.5,
                           selection_coefficient=0.0, seed=42),
            "medium": dict(population_size=1000, generations=500, starting_frequency=0.5,
                           selection_coefficient=0.0, seed=42),
            "large":  dict(population_size=10_000, generations=1000, starting_frequency=0.5,
                           selection_coefficient=0.0, seed=42),
        },
    ),
    "gillespie_ssa": (
        te.simulate_gillespie_ssa,
        {
            "small":  dict(a0=100, k=0.5, end=5.0, seed=42),
            "medium": dict(a0=1000, k=0.5, end=10.0, seed=42),
            "large":  dict(a0=10_000, k=0.5, end=20.0, seed=42),
        },
    ),
    "gillespie_ssa_bimolecular": (
        te.simulate_gillespie_ssa_bimolecular,
        {
            "small":  dict(a0=100, b0=100, k=0.005, end=5.0, seed=42),
            "medium": dict(a0=500, b0=500, k=0.005, end=10.0, seed=42),
            "large":  dict(a0=1000, b0=1000, k=0.005, end=20.0, seed=42),
        },
    ),
    "gillespie_ssa_replicates": (
        te.simulate_gillespie_ssa_replicates,
        {
            "small":  dict(a0=100, k=0.5, end=5.0, n_replicates=10, seed=42),
            "medium": dict(a0=100, k=0.5, end=5.0, n_replicates=50, seed=42),
            "large":  dict(a0=100, k=0.5, end=5.0, n_replicates=100, seed=42),
        },
    ),
    "molecular_dynamics": (
        te.simulate_molecular_dynamics,
        {
            "small":  dict(n_particles=27, density=0.85, temperature=0.4, timestep=0.005, n_steps=100, seed=42),
            "medium": dict(n_particles=64, density=0.85, temperature=0.4, timestep=0.005, n_steps=500, seed=42),
            "large":  dict(n_particles=125, density=0.85, temperature=0.4, timestep=0.005, n_steps=1000, seed=42),
        },
    ),
}

FIELDS = ["domain", "problem_size", "mean_time_s", "std_time_s", "raw_times_s"]
SIZES = ["small", "medium", "large"]


def time_one(fn, kwargs: dict, repeats: int) -> list[float]:
    times: list[float] = []
    for _ in range(repeats):
        start = time.perf_counter()
        fn(**kwargs)
        times.append(time.perf_counter() - start)
    return times


def run(repeats: int) -> list[dict]:
    rows: list[dict] = []
    for domain, (fn, sizes) in WORKLOADS.items():
        for size in SIZES:
            if size not in sizes:
                continue
            print(f"  {domain:<28} {size:<7}", end=" ", flush=True)
            try:
                raw = time_one(fn, sizes[size], repeats)
            except Exception as exc:  # noqa: BLE001
                # A failure is reported, never silently dropped: a missing row
                # in the output would read as "this domain was not measured"
                # rather than "this domain did not run".
                print(f"FAILED: {type(exc).__name__}: {exc}")
                rows.append({
                    "domain": domain, "problem_size": size,
                    "mean_time_s": "", "std_time_s": "",
                    "raw_times_s": f"FAILED: {type(exc).__name__}: {exc}",
                })
                continue
            mean = statistics.fmean(raw)
            std = statistics.stdev(raw) if len(raw) > 1 else 0.0
            print(f"{mean * 1000:8.2f} ms  ± {std * 1000:.2f}")
            rows.append({
                "domain": domain, "problem_size": size,
                "mean_time_s": mean, "std_time_s": std, "raw_times_s": raw,
            })
    return rows


def write(rows: list[dict]) -> None:
    with (HERE / "benchmark_results.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({**row, "raw_times_s": json.dumps(row["raw_times_s"])
                             if isinstance(row["raw_times_s"], list) else row["raw_times_s"]})
    (HERE / "benchmark_results.json").write_text(json.dumps(rows, indent=1) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--check", action="store_true",
                        help="run and report, but do not rewrite the committed files")
    args = parser.parse_args()

    print(f"Running {len(WORKLOADS)} domains x {len(SIZES)} sizes, "
          f"{args.repeats} repeats each\n")
    rows = run(args.repeats)

    failures = [r for r in rows if r["mean_time_s"] == ""]
    print(f"\n{len(rows) - len(failures)}/{len(rows)} workloads timed.")

    if failures:
        print(f"{len(failures)} FAILED:")
        for row in failures:
            print(f"  {row['domain']}/{row['problem_size']}: {row['raw_times_s']}")

    if args.check:
        print("\n--check: files not rewritten.")
        return 1 if failures else 0

    write(rows)
    print(f"\nWrote benchmark_results.csv and .json ({len(rows)} rows).")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
