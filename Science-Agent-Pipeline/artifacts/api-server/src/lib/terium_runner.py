#!/usr/bin/env python3
"""JSON bridge between the Node API server and the Python Terium engine.

The TypeScript API server spawns this script and writes a JSON payload to
stdin. This script imports terium_engine from the repo root, runs the
requested simulation, and prints a JSON result to stdout.

Usage:
    PYTHONPATH=/repo/root python3 terium_runner.py < request.json

Expected input JSON shape:
    {
      "domain": "mm" | "mm_competitive_inhibition" | "sir" | "seir" | "pcr" | "monte_carlo_pi" |
                 "wright_fisher" | "two_locus_wright_fisher" |
                 "molecular_dynamics" | "gillespie_ssa" |
                 "gillespie_ssa_bimolecular" | "gillespie_ssa_replicates" |
                 "lotka_volterra" | "cell_cycle_oscillator" | "repressilator" | "sbml",
      "parameters": { ...domain-specific params... }
    }

Output JSON shape:
    {
      "ok": true,
      "domain": "mm",
      "parameters": { ... },
      "trajectory": [ { "t": 0.0, "S": 10.0, ... }, ... ],
      "flagged": false,
      "flagReason": null
    }

or on error (including a runtime-ceiling rejection):
    { "ok": false, "error": "..." }

The ``DISPATCH`` table below is the contract between the application layer
and the engine: every domain maps to exactly one ``simulate_*`` function.
``Terium/tests/test_boundary_contract.py`` fails if the engine's
``__all__`` gains a ``simulate_*`` the runner does not dispatch here, and
vice versa. See ADR 0007.

Runtime ceilings (``MAX_API_*`` below) reject request sizes whose wall-clock
time would make a request look hung: MD integration and Wright-Fisher
generations scale linearly with their counters, and the queue limits
*concurrency*, not *duration* (STAGE_04_PART_01 §6.3).
"""

from __future__ import annotations

import json
import pathlib
import sys
from typing import Any, Callable, Dict, Sequence


# Application-runtime ceilings, not scientific plausibility bounds. The engine
# remains authoritative for physical validity and domain flags. These bound
# wall-clock time per request: the queue governs concurrency, these govern
# duration.
#
# Measured on the pinned CI configuration (Python 3.10, numpy 1.26.4),
# 2026-08-01, by timing the engine directly:
#
#     MC   1e6 samples ............................. 0.31s
#     WF   10k generations x 10 replicates ......... 0.86s
#     MD   108 particles x 10k steps ............... 7.32s
#
# An earlier revision of this comment cited "STAGE_04_PART_01 §6.3" for these
# numbers and quoted MD at ~11s. That section does not exist and the figure
# was never measured; both are corrected above.
MAX_API_MONTE_CARLO_SAMPLES = 1_000_000
MAX_API_MD_STEPS = 10_000
MAX_API_WF_GENERATIONS = 10_000
MAX_API_WF_REPLICATES = 1_000

# SSA cost is O(initial population): each reaction event consumes one
# molecule of A. 1e6 events is a few seconds in the engine — a hard
# teaching ceiling, far above any realistic request.
MAX_API_SSA_POPULATION = 1_000_000

# The SSA ensemble view (Stage 7 Part 2) costs n_replicates x one-run
# cost. The scalar ceilings below bound each dimension; the product
# budget bounds the wall-clock total: n_replicates * population must
# stay within the single-request event budget, so a 1e6-molecule
# request can only ask for a handful of replicates, and a 1000-run
# ensemble can only use a small population.
MAX_API_SSA_REPLICATES = 1_000

# MD cost is O(N^2 * steps) -- pairwise forces, no neighbour lists (ADR 0006
# put those out of scope). Capping n_steps alone therefore does NOT bound a
# request, because the quadratic term is unconstrained. Measured at a step
# count 50x BELOW the ceiling:
#
#     n=108   0.15s      n=500   3.64s
#     n=256   0.95s      n=800   9.94s
#
# and the engine accepts n_particles=5000 (ok=True, merely flagged, then
# rounded UP to the next fcc count, 5324). That request passes every ceiling
# above and costs roughly six hours at the step limit.
#
# So the budget is applied to the product that actually drives cost. Measured
# throughput is ~1.6e7 pair-steps/second, so 1.2e8 is about a 7.5-second
# ceiling -- chosen to keep the documented 108-particle x 10k-step case
# (1.17e8) inside the budget while rejecting the pathological shapes.
MAX_API_MD_PAIR_STEPS = 120_000_000


def _fcc_particle_count(requested: int) -> int:
    """Mirror the engine's fcc round-up: 4*k^3 for the smallest sufficient k.

    The budget must be computed on the count the engine will actually
    simulate, not the count the caller asked for -- rounding is always
    upward, so using the request would systematically underestimate cost.
    """
    if requested <= 0:
        return 0
    cells = 1
    while 4 * cells**3 < requested:
        cells += 1
    return 4 * cells**3

# The repo root must be on PYTHONPATH so we can import Terium.terium_engine.
# The API server sets this when spawning the process.
from Terium import terium_engine  # noqa: E402  # type: ignore
from Terium.core.data_structures import (  # noqa: E402  # type: ignore
    DEFAULT_ABSOLUTE_TOLERANCE,
    DEFAULT_RELATIVE_TOLERANCE,
)


def _to_point(row: Sequence[float], colnames: Sequence[str]) -> Dict[str, float]:
    return {name: float(row[i]) for i, name in enumerate(colnames)}


def _serialise_result(result: Any, domain: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
    """Shared result-serialisation with the boundary validation contract."""
    flagged = bool(getattr(result, "flagged", False))
    validation = getattr(result, "validation", None)
    payload: Dict[str, Any] = {
        "ok": True,
        "domain": domain,
        "parameters": parameters,
        "trajectory": [
            _to_point(list(row), result.colnames) for row in result.data
        ],
        "flagged": flagged,
        "flagReason": getattr(validation, "flag_reason", None) if flagged else None,
        # How the run was ACTUALLY integrated, read from the engine's own
        # constants.
        #
        # The TypeScript execution record used to state `RK45` at rtol 1e-6
        # / atol 1e-8 -- a solver Terrium does not use, at tolerances four
        # orders of magnitude looser than it runs. `verifyReproducibility`
        # calibrates from those numbers, so it certified reproductions that
        # were nowhere near reproducing.
        #
        # Reported from here because this is the only side that knows. The
        # alternative -- restating the constants in TypeScript -- is the
        # duplicate-source-of-truth defect that put the wrong numbers there
        # in the first place.
        "solver": {
            "algorithm": "CVODE",
            "relativeTolerance": DEFAULT_RELATIVE_TOLERANCE,
            "absoluteTolerance": DEFAULT_ABSOLUTE_TOLERANCE,
        },
    }
    replicate_data = getattr(result, "replicate_data", None)
    if replicate_data is not None:
        payload["replicateColnames"] = getattr(result, "replicate_colnames", None)
        payload["replicateData"] = replicate_data
    return payload


def run_mm(params: Dict[str, Any]) -> Dict[str, Any]:
    km = float(params.get("km", 2.0))
    s0 = float(params.get("s0", 10.0))
    end = float(params.get("end", 10.0))
    points = int(params.get("points", 51))

    # kcat + enzyme_conc is an alternative way to specify Vmax
    # (Vmax = kcat * [E]0, ADR 0013). Both must be present: a turnover
    # number alone cannot produce a Vmax, and an enzyme concentration alone
    # has nothing to multiply.
    #
    # An explicit vmax wins when supplied. That is not arbitrary -- vmax is
    # the parameter the engine actually integrates, so honouring the derived
    # value over a stated one would silently overwrite what the caller
    # asked for.
    kcat = params.get("kcat")
    enzyme_conc = params.get("enzyme_conc")
    derived_note = None

    if "vmax" in params and params["vmax"] is not None:
        vmax = float(params["vmax"])
    elif kcat is not None and enzyme_conc is not None:
        vmax, conversion = terium_engine.vmax_from_kcat(
            kcat=float(kcat), enzyme_conc=float(enzyme_conc), km=km
        )
        conversion.raise_if_invalid()
        derived_note = (
            f"Vmax {vmax:g} mM/s derived from kcat {float(kcat):g} 1/s "
            f"x [E]0 {float(enzyme_conc):g} mM"
        )
        if conversion.flagged:
            derived_note += f". {conversion.flag_reason}"
    elif kcat is not None or enzyme_conc is not None:
        missing = "enzyme_conc" if kcat is not None else "kcat"
        raise ValueError(
            f"Vmax cannot be derived: {missing} is required alongside "
            f"{'kcat' if missing == 'enzyme_conc' else 'enzyme_conc'} "
            "(Vmax = kcat * [E]0)"
        )
    else:
        # No route to a Vmax at all. Unreachable from the API: resolveQuery()'s
        # hard rule throws RequiredParametersMissingError on any default-origin
        # vmax before the runner is spawned, and the zod schema (schemas.ts)
        # requires vmax or kcat+enzyme_conc at validation. Fail loudly rather
        # than simulate on an unverified 5.0 -- a number nobody chose.
        raise ValueError(
            "mm needs a Vmax: supply vmax directly, or supply BOTH kcat and "
            "enzyme_conc (Vmax = kcat * [E]0)"
        )

    result = terium_engine.simulate_michaelis_menten(
        km=km, vmax=vmax, s0=s0, end=end, points=points
    )

    reported: Dict[str, Any] = {
        "km": km, "vmax": vmax, "s0": s0, "end": end, "points": points,
    }
    if derived_note is not None:
        # Echo the inputs the Vmax was derived FROM, not just the result.
        # A student who sees only vmax=0.00118 cannot tell it came from a
        # literature turnover number at an enzyme concentration they chose.
        reported["kcat"] = float(kcat)
        reported["enzyme_conc"] = float(enzyme_conc)

    payload = _serialise_result(result, "mm", reported)

    if derived_note is not None:
        payload["derivedNote"] = derived_note
        # The conversion's own flag must survive. The simulation itself may
        # be perfectly fine while [E]0 sits in the regime where the MM rate
        # law is being stretched -- dropping that here would hide the one
        # warning the conversion exists to raise.
        if conversion.flagged and not payload["flagged"]:
            payload["flagged"] = True
            payload["flagReason"] = conversion.flag_reason

    return payload


def run_mm_competitive_inhibition(params: Dict[str, Any]) -> Dict[str, Any]:
    km = float(params.get("km", 2.0))
    if "vmax" not in params or params["vmax"] is None:
        # No Vmax at all. Unreachable from the API: resolveQuery()'s hard
        # rule throws RequiredParametersMissingError on any default-origin
        # vmax before the runner is spawned, and the zod schema (schemas.ts)
        # requires vmax for this domain at validation. Fail loudly rather
        # than simulate on an unverified 5.0 -- a number nobody chose.
        raise ValueError(
            "mm_competitive_inhibition needs a Vmax: supply vmax directly"
        )
    vmax = float(params["vmax"])
    ki = float(params.get("ki", 1.0))
    s0 = float(params.get("s0", 10.0))
    # Wire name is "i0" (inhibitor concentration at t=0), matching the
    # SimulationParameterSchemas shape in schemas.ts and the DOMAIN_DEFAULTS
    # entry in queryResolver.ts. The engine's own keyword argument is "i" --
    # that is an internal name inside terium_engine, not the API contract.
    i0 = float(params.get("i0", 0.0))
    end = float(params.get("end", 10.0))
    points = int(params.get("points", 51))

    result = terium_engine.simulate_mm_competitive_inhibition(
        km=km, vmax=vmax, ki=ki, s0=s0, i=i0, end=end, points=points
    )

    reported: Dict[str, Any] = {
        "km": km, "vmax": vmax, "ki": ki, "s0": s0, "i0": i0,
        "end": end, "points": points,
    }
    return _serialise_result(result, "mm_competitive_inhibition", reported)


def run_sir(params: Dict[str, Any]) -> Dict[str, Any]:
    beta = float(params.get("beta", 0.3))
    gamma = float(params.get("gamma", 0.1))
    s0 = float(params.get("s0", 990.0))
    i0 = float(params.get("i0", 10.0))
    r0 = float(params.get("r0_recovered", 0.0))
    end = float(params.get("end", 100.0))
    points = int(params.get("points", 101))

    result = terium_engine.simulate_sir(
        beta=beta, gamma=gamma, s0=s0, i0=i0, r0_recovered=r0, end=end,
        points=points
    )

    return _serialise_result(
        result, "sir",
        {"beta": beta, "gamma": gamma, "s0": s0, "i0": i0,
         "r0_recovered": r0, "end": end, "points": points},
    )


def run_seir(params: Dict[str, Any]) -> Dict[str, Any]:
    beta = float(params.get("beta", 0.3))
    sigma = float(params.get("sigma", 0.2))
    gamma = float(params.get("gamma", 0.1))
    s0 = float(params.get("s0", 990.0))
    e0 = float(params.get("e0", 10.0))
    i0 = float(params.get("i0", 0.0))
    r0 = float(params.get("r0_recovered", 0.0))
    end = float(params.get("end", 100.0))
    points = int(params.get("points", 101))

    result = terium_engine.simulate_seir(
        beta=beta, sigma=sigma, gamma=gamma, s0=s0, e0=e0, i0=i0,
        r0_recovered=r0, end=end, points=points
    )

    return _serialise_result(
        result, "seir",
        {"beta": beta, "sigma": sigma, "gamma": gamma,
         "s0": s0, "e0": e0, "i0": i0, "r0_recovered": r0,
         "end": end, "points": points},
    )


def run_pcr(params: Dict[str, Any]) -> Dict[str, Any]:
    n0 = float(params.get("n0", 100.0))
    efficiency = float(params.get("efficiency", 0.95))
    cycles = int(params.get("cycles", 30))

    result = terium_engine.simulate_pcr(
        n0=n0, efficiency=efficiency, cycles=cycles
    )

    return _serialise_result(
        result, "pcr",
        {"n0": n0, "efficiency": efficiency, "cycles": cycles},
    )


def run_monte_carlo_pi(params: Dict[str, Any]) -> Dict[str, Any]:
    n_samples = int(params.get("n_samples", 10000))
    if n_samples > MAX_API_MONTE_CARLO_SAMPLES:
        raise ValueError(
            f"n_samples={n_samples} exceeds API runtime ceiling "
            f"(MAX_API_MONTE_CARLO_SAMPLES) {MAX_API_MONTE_CARLO_SAMPLES}"
        )

    seed = params.get("seed")
    seed = None if seed is None else int(seed)
    result = terium_engine.simulate_monte_carlo_pi(
        n_samples=n_samples, seed=seed
    )

    return _serialise_result(
        result, "monte_carlo_pi",
        {"n_samples": n_samples, "seed": seed},
    )


def run_gillespie_ssa(params: Dict[str, Any]) -> Dict[str, Any]:
    a0 = int(params.get("a0", 1000))
    k = float(params.get("k", 0.5))
    end = float(params.get("end", 10.0))
    if a0 > MAX_API_SSA_POPULATION:
        raise ValueError(
            f"a0={a0} exceeds API runtime ceiling "
            f"(MAX_API_SSA_POPULATION) {MAX_API_SSA_POPULATION}"
        )

    seed = params.get("seed")
    seed = None if seed is None else int(seed)
    result = terium_engine.simulate_gillespie_ssa(
        a0=a0, k=k, end=end, seed=seed
    )

    return _serialise_result(
        result, "gillespie_ssa",
        {"a0": a0, "k": k, "end": end, "seed": seed},
    )


def run_gillespie_ssa_replicates(params: Dict[str, Any]) -> Dict[str, Any]:
    a0 = int(params.get("a0", 100))
    b0 = params.get("b0")
    b0 = None if b0 is None else int(b0)
    k = float(params.get("k", 0.005 if b0 is not None else 0.5))
    end = float(params.get("end", 10.0))
    n_replicates = int(params.get("n_replicates", 100))

    population = a0 + (b0 or 0)
    if population > MAX_API_SSA_POPULATION:
        raise ValueError(
            f"initial population {population} exceeds API runtime ceiling "
            f"(MAX_API_SSA_POPULATION) {MAX_API_SSA_POPULATION}"
        )
    if n_replicates > MAX_API_SSA_REPLICATES:
        raise ValueError(
            f"n_replicates={n_replicates} exceeds API runtime ceiling "
            f"(MAX_API_SSA_REPLICATES) {MAX_API_SSA_REPLICATES}"
        )
    if n_replicates * population > MAX_API_SSA_POPULATION:
        raise ValueError(
            f"n_replicates x initial population {n_replicates * population} "
            f"exceeds the API runtime ceiling (MAX_API_SSA_POPULATION) "
            f"{MAX_API_SSA_POPULATION}"
        )

    seed = params.get("seed")
    seed = None if seed is None else int(seed)
    result = terium_engine.simulate_gillespie_ssa_replicates(
        a0=a0, b0=b0, k=k, end=end, n_replicates=n_replicates, seed=seed
    )

    return _serialise_result(
        result, "gillespie_ssa_replicates",
        {"a0": a0, "b0": b0, "k": k, "end": end,
         "n_replicates": n_replicates, "seed": seed},
    )


def run_gillespie_ssa_bimolecular(params: Dict[str, Any]) -> Dict[str, Any]:
    a0 = int(params.get("a0", 100))
    b0 = int(params.get("b0", 100))
    k = float(params.get("k", 0.005))
    end = float(params.get("end", 10.0))
    if a0 + b0 > MAX_API_SSA_POPULATION:
        raise ValueError(
            f"a0+b0={a0 + b0} exceeds API runtime ceiling "
            f"(MAX_API_SSA_POPULATION) {MAX_API_SSA_POPULATION}"
        )

    seed = params.get("seed")
    seed = None if seed is None else int(seed)
    result = terium_engine.simulate_gillespie_ssa_bimolecular(
        a0=a0, b0=b0, k=k, end=end, seed=seed
    )

    return _serialise_result(
        result, "gillespie_ssa_bimolecular",
        {"a0": a0, "b0": b0, "k": k, "end": end, "seed": seed},
    )


def run_wright_fisher(params: Dict[str, Any]) -> Dict[str, Any]:
    population_size = int(params.get("population_size", 100))
    starting_frequency = float(params.get("starting_frequency", 0.5))
    generations = int(params.get("generations", 100))
    replicate_runs = int(params.get("replicate_runs", 100))
    mutation_rate = float(params.get("mutation_rate", 0.0))
    selection_coefficient = float(params.get("selection_coefficient", 0.0))
    dominance = params.get("dominance")
    seed = params.get("seed")

    if generations > MAX_API_WF_GENERATIONS:
        raise ValueError(
            f"generations={generations} exceeds API runtime ceiling "
            f"(MAX_API_WF_GENERATIONS) {MAX_API_WF_GENERATIONS}"
        )
    if replicate_runs > MAX_API_WF_REPLICATES:
        raise ValueError(
            f"replicate_runs={replicate_runs} exceeds API runtime ceiling "
            f"(MAX_API_WF_REPLICATES) {MAX_API_WF_REPLICATES}"
        )

    result = terium_engine.simulate_wright_fisher(
        population_size=population_size, starting_frequency=starting_frequency,
        generations=generations, replicate_runs=replicate_runs,
        mutation_rate=mutation_rate, selection_coefficient=selection_coefficient,
        dominance=dominance, seed=seed
    )

    return _serialise_result(
        result, "wright_fisher",
        {"population_size": population_size,
         "starting_frequency": starting_frequency,
         "generations": generations,
         "replicate_runs": replicate_runs,
         "mutation_rate": mutation_rate,
         "selection_coefficient": selection_coefficient,
         "dominance": dominance,
         "seed": seed},
    )


def run_two_locus_wright_fisher(params: Dict[str, Any]) -> Dict[str, Any]:
    population_size = int(params.get("population_size", 100))
    generations = int(params.get("generations", 100))
    recombination_rate = float(params.get("recombination_rate", 0.1))
    raw_freqs = params.get("starting_frequencies", [0.5, 0.0, 0.0, 0.5])
    starting_frequencies = [float(x) for x in raw_freqs]
    replicate_runs = int(params.get("replicate_runs", 100))
    mutation_rate = float(params.get("mutation_rate", 0.0))
    seed = params.get("seed")

    if generations > MAX_API_WF_GENERATIONS:
        raise ValueError(
            f"generations={generations} exceeds API runtime ceiling "
            f"(MAX_API_WF_GENERATIONS) {MAX_API_WF_GENERATIONS}"
        )
    if replicate_runs > MAX_API_WF_REPLICATES:
        raise ValueError(
            f"replicate_runs={replicate_runs} exceeds API runtime ceiling "
            f"(MAX_API_WF_REPLICATES) {MAX_API_WF_REPLICATES}"
        )

    result = terium_engine.simulate_two_locus_wright_fisher(
        population_size=population_size, generations=generations,
        recombination_rate=recombination_rate,
        starting_frequencies=starting_frequencies,
        replicate_runs=replicate_runs, mutation_rate=mutation_rate, seed=seed
    )

    # TwoLocusResult validates by raising; a returned result is un-flagged.
    return _serialise_result(
        result, "two_locus_wright_fisher",
        {"population_size": population_size,
         "generations": generations,
         "recombination_rate": recombination_rate,
         "starting_frequencies": starting_frequencies,
         "replicate_runs": replicate_runs,
         "mutation_rate": mutation_rate,
         "seed": seed},
    )


def run_molecular_dynamics(params: Dict[str, Any]) -> Dict[str, Any]:
    n_particles = int(params.get("n_particles", 108))
    temperature = float(params.get("temperature", 0.4))
    timestep = float(params.get("timestep", 0.005))
    n_steps = int(params.get("n_steps", 1000))
    density = float(params.get("density", 0.85))
    if n_steps > MAX_API_MD_STEPS:
        raise ValueError(
            f"n_steps={n_steps} exceeds API runtime ceiling "
            f"(MAX_API_MD_STEPS) {MAX_API_MD_STEPS}"
        )

    # Bound the quadratic term too -- n_steps alone does not bound the request.
    actual_n = _fcc_particle_count(n_particles)
    pair_steps = actual_n * actual_n * max(n_steps, 1)
    if pair_steps > MAX_API_MD_PAIR_STEPS:
        raise ValueError(
            f"n_particles={n_particles} (simulated as {actual_n} after fcc "
            f"round-up) with n_steps={n_steps} is {pair_steps:.3g} pair-steps, "
            f"exceeding the API runtime ceiling (MAX_API_MD_PAIR_STEPS) "
            f"{MAX_API_MD_PAIR_STEPS:.3g}. MD cost scales as N^2 * steps; "
            f"reduce either."
        )

    seed = params.get("seed")

    result = terium_engine.simulate_molecular_dynamics(
        n_particles=n_particles, temperature=temperature, timestep=timestep,
        n_steps=n_steps, density=density, seed=seed
    )

    return _serialise_result(
        result, "molecular_dynamics",
        {"n_particles": n_particles, "temperature": temperature,
         "timestep": timestep, "n_steps": n_steps, "density": density,
         "seed": seed},
    )


def run_lotka_volterra(params: Dict[str, Any]) -> Dict[str, Any]:
    """Lotka-Volterra predator-prey dynamics (Lotka 1925, Volterra 1926).

    gamma/delta defaults are 0.1/0.4, matching
    ``simulate_lotka_volterra``'s own defaults -- NOT 0.4/0.1. That
    transposed pairing put the coexistence fixed point at (0.25, 2.75)
    against a p0=10 start (a 40x excursion), drove the prey population
    negative, and drifted the system's exactly-conserved first integral
    by 49%. See the docstring on ``simulate_lotka_volterra`` and
    tests/test_lotka_volterra_correctness.py.
    """
    alpha = float(params.get("alpha", 1.1))
    beta = float(params.get("beta", 0.4))
    gamma = float(params.get("gamma", 0.1))
    delta = float(params.get("delta", 0.4))
    p0 = float(params.get("p0", 10.0))  # Prey population
    v0 = float(params.get("v0", 5.0))   # Predator population
    end = float(params.get("end", 20.0))
    points = int(params.get("points", 201))

    result = terium_engine.simulate_lotka_volterra(
        alpha=alpha, beta=beta, gamma=gamma, delta=delta,
        p0=p0, v0=v0, end=end, points=points
    )

    return _serialise_result(
        result, "lotka_volterra",
        {"alpha": alpha, "beta": beta, "gamma": gamma, "delta": delta,
         "p0": p0, "v0": v0, "end": end, "points": points},
    )


def run_cell_cycle_oscillator(params: Dict[str, Any]) -> Dict[str, Any]:
    """Cell cycle oscillator (Tyson 1991): cyclin-CDK regulation driving mitosis."""
    end = float(params.get("end", 100.0))
    points = int(params.get("points", 1001))
    seed = params.get("seed")

    result = terium_engine.simulate_cell_cycle_oscillator(
        end=end, points=points, seed=seed
    )

    return _serialise_result(
        result, "cell_cycle_oscillator",
        {"end": end, "points": points, "seed": seed},
    )


def run_repressilator(params: Dict[str, Any]) -> Dict[str, Any]:
    """Repressilator (Elowitz & Leibler 2000): three-gene synthetic oscillator."""
    end = float(params.get("end", 200.0))
    points = int(params.get("points", 2001))
    seed = params.get("seed")

    result = terium_engine.simulate_repressilator(
        end=end, points=points, seed=seed
    )

    return _serialise_result(
        result, "repressilator",
        {"end": end, "points": points, "seed": seed},
    )


def run_sbml(params: Dict[str, Any]) -> Dict[str, Any]:
    """Dispatch for ``simulate_sbml`` -- the raw-SBML escape hatch.

    Included so the contract test can require *every* ``simulate_*`` in the
    engine's ``__all__`` to be dispatched, with no exceptions.
    """
    sbml_string = params.get("sbml_string", "")
    start = float(params.get("start", 0.0))
    end = float(params.get("end", 10.0))
    points = int(params.get("points", 51))

    result = terium_engine.simulate_sbml(
        sbml_string=sbml_string, start=start, end=end, points=points
    )

    return _serialise_result(
        result, "sbml",
        {"start": start, "end": end, "points": points},
    )


# domain -> engine function name. This is the contract; see ADR 0007 and
# Terium/tests/test_boundary_contract.py. 16 API domains + SBML escape
# hatch.
#
# monte_carlo_pi and gillespie_ssa_replicates were briefly deleted from this
# table with the note "not part of the TypeScript API contract". That had it
# backwards: both are in the engine's ``__all__``, both have run_* handlers
# below, both are documented in the README's domain list, and ADR 0007's
# whole point is that the ENGINE's surface is the contract -- the
# TypeScript side follows it, not the other way round. Deleting them here
# to satisfy a stale TS union broke five boundary-contract tests, which is
# exactly the drift the contract test exists to catch. They are restored,
# and SimulationDomain in teriumRunner.ts now lists them.
#
# lotka_volterra, cell_cycle_oscillator, repressilator: see ADR 0022.
DISPATCH: Dict[str, str] = {
    "mm": "simulate_michaelis_menten",
    "mm_competitive_inhibition": "simulate_mm_competitive_inhibition",
    "sir": "simulate_sir",
    "seir": "simulate_seir",
    "wright_fisher": "simulate_wright_fisher",
    "gillespie_ssa": "simulate_gillespie_ssa",
    "pcr": "simulate_pcr",
    "molecular_dynamics": "simulate_molecular_dynamics",
    "gillespie_ssa_bimolecular": "simulate_gillespie_ssa_bimolecular",
    "two_locus_wright_fisher": "simulate_two_locus_wright_fisher",
    "monte_carlo_pi": "simulate_monte_carlo_pi",
    "gillespie_ssa_replicates": "simulate_gillespie_ssa_replicates",
    # Three ODE oscillator domains (ADR 0022). Removed earlier the same day
    # when the engine did not yet implement them; restored now that
    # simulate_lotka_volterra / _cell_cycle_oscillator / _repressilator are
    # real and in the engine's __all__.
    "lotka_volterra": "simulate_lotka_volterra",
    "cell_cycle_oscillator": "simulate_cell_cycle_oscillator",
    "repressilator": "simulate_repressilator",
    "sbml": "simulate_sbml",
}

_RUNNERS: Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]] = {
    "mm": run_mm,
    "mm_competitive_inhibition": run_mm_competitive_inhibition,
    "sir": run_sir,
    "seir": run_seir,
    "wright_fisher": run_wright_fisher,
    "gillespie_ssa": run_gillespie_ssa,
    "pcr": run_pcr,
    "molecular_dynamics": run_molecular_dynamics,
    "gillespie_ssa_bimolecular": run_gillespie_ssa_bimolecular,
    "two_locus_wright_fisher": run_two_locus_wright_fisher,
    "monte_carlo_pi": run_monte_carlo_pi,
    "gillespie_ssa_replicates": run_gillespie_ssa_replicates,
    "lotka_volterra": run_lotka_volterra,
    "cell_cycle_oscillator": run_cell_cycle_oscillator,
    "repressilator": run_repressilator,
    "sbml": run_sbml,
}


def main() -> None:
    # `--list-domains`: what this engine can actually simulate, from DISPATCH.
    #
    # WHY THIS EXISTS
    # ---------------
    # Terrium advertises fifteen teaching domains. Until now nothing could
    # tell a student what they are. `scientificCLI.ts help` lists nine
    # commands, all of them enzyme kinetics or generic; `python -m Terium.cli
    # --help` lists seven subcommands, all population genetics and Gillespie.
    # Neither mentions the other, and neither names epidemiology, PCR, Monte
    # Carlo or molecular dynamics at all -- domains this engine runs and has
    # over a thousand tests for.
    #
    # A capability nobody can find is not a capability. That is ADR 0090's
    # sentence about exported functions, and it applies with more force to a
    # product surface: the code was written, verified against closed-form
    # solutions, and left undiscoverable.
    #
    # Emitted from DISPATCH rather than typed out. A hand-written list is a
    # second source of truth that goes stale the first time a domain is
    # added, and this file already carries a comment about exactly that
    # hazard -- the membership test and the call site indexing two tables
    # "kept equal by hand (they have diverged before)".
    if "--list-domains" in sys.argv:
        print(json.dumps({"ok": True, "domains": sorted(DISPATCH)}))
        return

    # `--ensemble`: run the model once per sampled parameter set and return
    # the envelope, instead of once with a single chosen value.
    #
    # THIS IS THE ANSWER TO THE QUESTION BOTH PROFESSORS ANSWERED THE SAME WAY.
    #
    # Bakker: "we generated an ensemble of models by sampling from a
    # distribution of possible parameters [...] these scores were then used to
    # give the parameter a weight in the sampling."
    #
    # Sauro, told about the alternative: "with Barbara's you can sample and
    # get an ensemble distribution. That is the right way to do it."
    #
    # It lives HERE, on the runner, rather than in either front end, because
    # the runner is the one place both the CLI and the API read from. A
    # capability added to one of them reaches half the users, which this
    # repository has now recorded four times and made a guard for
    # (docs/one-sided-findings.txt).
    #
    # Payload shape:
    #   {"domain": "mm", "parameters": {...},
    #    "ensemble": {"parameter": "km", "draws": [...], "seed": 1}}
    #
    # The DRAWS are supplied rather than computed here. Weighting them is the
    # literature layer's job -- it needs the per-candidate reliability scores
    # -- and recomputing them in the engine would be a second implementation
    # of the sampling, which is ADR 0027's defect exactly.
    if "--ensemble" in sys.argv:
        try:
            payload = json.loads(sys.stdin.read() or "{}")
            domain = payload.get("domain")
            if domain not in DISPATCH:
                raise ValueError(f"unknown domain: {domain!r}")  # noqa: TRY301
            spec = payload.get("ensemble") or {}
            parameter = spec.get("parameter")
            draws = spec.get("draws")
            if not parameter or not isinstance(draws, list) or not draws:
                raise ValueError(  # noqa: TRY301
                    "ensemble needs {'parameter': name, 'draws': [...], 'seed': n}"
                )

            # `Tests/` holds the literature layer. Located from the
            # importable `Terium` package rather than from this file's
            # path: the runner is spawned with a PYTHONPATH the server
            # chooses, and walking up from __file__ would break the
            # moment either tree moves.
            import Terium as _terium_pkg  # noqa: PLC0415
            _root = pathlib.Path(_terium_pkg.__file__).resolve().parent.parent
            sys.path.insert(0, str(_root / "Tests"))
            from model_ensemble import run_model_ensemble  # noqa: PLC0415

            simulate = getattr(terium_engine, DISPATCH[domain])
            result = run_model_ensemble(
                simulate=simulate,
                base_parameters=payload.get("parameters", {}),
                parameter_draws={parameter: [float(d) for d in draws]},
                seed=int(spec.get("seed", 0)),
                max_runs=int(spec.get("maxRuns", 200)),
            )
            print(json.dumps({
                "ok": True,
                "ensemble": {
                    "swept": list(result.swept),
                    "seed": result.seed,
                    "succeeded": result.succeeded,
                    "attempted": result.attempted,
                    # Every failure, with the parameter set that caused it, so
                    # a band drawn over fewer runs than requested can be
                    # explained rather than merely noticed.
                    "failed": [
                        {"parameters": f.parameters, "reason": f.reason}
                        for f in result.failed
                    ],
                    "supportNote": result.support_note(),
                    "disclaimer": result.disclaimer,
                    "envelopes": [
                        {
                            "column": e.column,
                            "times": list(e.times),
                            "low": list(e.low),
                            "p05": list(e.p05),
                            "median": list(e.median),
                            "p95": list(e.p95),
                            "high": list(e.high),
                        }
                        for e in result.envelopes
                    ],
                },
            }))
            return
        except Exception as exc:  # noqa: BLE001
            print(json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"}))
            return

    try:
        raw = sys.stdin.read()
        if not raw:
            raise ValueError("no input JSON provided")  # noqa: TRY301
        payload = json.loads(raw)
        domain = payload.get("domain")
        params = payload.get("parameters", {})

        if domain not in DISPATCH:
            raise ValueError(f"unknown domain: {domain!r}")  # noqa: TRY301
        if not isinstance(params, dict):
            raise ValueError(f"parameters must be an object, got {type(params).__name__}")  # noqa: TRY301

        # The membership test above is against DISPATCH; the call below used to
        # index _RUNNERS -- a guard on a different table from the one it was
        # protecting. The two are kept equal by hand (they have diverged before:
        # see the ADR 0022 removal-and-restoration in the comment above DISPATCH)
        # and the boundary contract test now proves a one-sided edit is caught.
        # But if one ever slipped through, `_RUNNERS[domain]` raised KeyError and
        # the handler below stringified it, so the student was shown the whole
        # error as `'pcr'` -- a bare quoted domain name. Worse, it reads as
        # "you asked for something invalid" when the request was fine and the
        # build is broken. Look the handler up once, and say which it is.
        runner_fn = _RUNNERS.get(domain)
        if runner_fn is None:
            raise ValueError(  # noqa: TRY301
                f"internal error: domain {domain!r} is listed in DISPATCH but has "
                f"no handler in _RUNNERS. This is a build defect, not a bad request."
            )

        result = runner_fn(params)
        print(json.dumps(result))
    except Exception as exc:
        error_payload = {"ok": False, "error": str(exc)}
        print(json.dumps(error_payload), file=sys.stdout)
        sys.exit(1)


if __name__ == "__main__":
    main()
