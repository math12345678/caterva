#!/usr/bin/env python3
"""JSON bridge between the Node API server and the Python Tellurium engine.

The TypeScript API server spawns this script and writes a JSON payload to
stdin. This script imports tellurium_engine from the repo root, runs the
requested simulation, and prints a JSON result to stdout.

Usage:
    PYTHONPATH=/repo/root python3 tellurium_runner.py < request.json

Expected input JSON shape:
    {
      "domain": "mm" | "sir" | "seir" | "pcr" | "monte_carlo_pi" |
                 "wright_fisher" | "two_locus_wright_fisher" |
                 "molecular_dynamics" | "sbml",
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

or on error:
    { "ok": false, "error": "..." }

The ``DISPATCH`` table below is the contract between the application layer
and the engine: every domain maps to exactly one ``simulate_*`` function.
``Tellurium/tests/test_boundary_contract.py`` fails if the engine's
``__all__`` gains a ``simulate_*`` the runner does not dispatch here, and
vice versa. See ADR 0007.
"""

from __future__ import annotations

import json
import sys
from typing import Any, Callable, Dict, List, Sequence


# Application-runtime ceilings, not scientific plausibility bounds. The engine
# remains authoritative for physical validity and domain flags.
MAX_API_MONTE_CARLO_SAMPLES = 1_000_000
MAX_API_MD_STEPS = 10_000

# The repo root must be on PYTHONPATH so we can import Tellurium.tellurium_engine.
# The API server sets this when spawning the process.
from Tellurium import tellurium_engine  # type: ignore


def _to_point(row: Sequence[float], colnames: Sequence[str]) -> Dict[str, float]:
    return {name: float(row[i]) for i, name in enumerate(colnames)}


def _serialise_result(result: Any, domain: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
    """Shared result-serialisation with the boundary validation contract."""
    flagged = bool(getattr(result, "flagged", False))
    validation = getattr(result, "validation", None)
    return {
        "ok": True,
        "domain": domain,
        "parameters": parameters,
        "trajectory": [
            _to_point(list(row), result.colnames) for row in result.data
        ],
        "flagged": flagged,
        "flagReason": getattr(validation, "flag_reason", None) if flagged else None,
    }


def run_mm(params: Dict[str, Any]) -> Dict[str, Any]:
    km = float(params.get("km", 2.0))
    vmax = float(params.get("vmax", 5.0))
    s0 = float(params.get("s0", 10.0))
    end = float(params.get("end", 10.0))
    points = int(params.get("points", 51))

    result = tellurium_engine.simulate_michaelis_menten(
        km=km, vmax=vmax, s0=s0, end=end, points=points
    )

    return _serialise_result(
        result, "mm",
        {"km": km, "vmax": vmax, "s0": s0, "end": end, "points": points},
    )


def run_sir(params: Dict[str, Any]) -> Dict[str, Any]:
    beta = float(params.get("beta", 0.3))
    gamma = float(params.get("gamma", 0.1))
    s0 = float(params.get("s0", 990.0))
    i0 = float(params.get("i0", 10.0))
    r0 = float(params.get("r0_recovered", 0.0))
    end = float(params.get("end", 100.0))
    points = int(params.get("points", 101))

    result = tellurium_engine.simulate_sir(
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

    result = tellurium_engine.simulate_seir(
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

    result = tellurium_engine.simulate_pcr(
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
            f"{MAX_API_MONTE_CARLO_SAMPLES}"
        )

    seed = params.get("seed")
    seed = None if seed is None else int(seed)
    result = tellurium_engine.simulate_monte_carlo_pi(
        n_samples=n_samples, seed=seed
    )

    return _serialise_result(
        result, "monte_carlo_pi",
        {"n_samples": n_samples, "seed": seed},
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

    result = tellurium_engine.simulate_wright_fisher(
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

    result = tellurium_engine.simulate_two_locus_wright_fisher(
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
    if n_steps > MAX_API_MD_STEPS:
        raise ValueError(
            f"n_steps={n_steps} exceeds API runtime ceiling {MAX_API_MD_STEPS}"
        )
    seed = params.get("seed")

    result = tellurium_engine.simulate_molecular_dynamics(
        n_particles=n_particles, temperature=temperature, timestep=timestep,
        n_steps=n_steps, seed=seed
    )

    return _serialise_result(
        result, "molecular_dynamics",
        {"n_particles": n_particles, "temperature": temperature,
         "timestep": timestep, "n_steps": n_steps, "seed": seed},
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

    result = tellurium_engine.simulate_sbml(
        sbml_string=sbml_string, start=start, end=end, points=points
    )

    return _serialise_result(
        result, "sbml",
        {"start": start, "end": end, "points": points},
    )


# domain -> engine function name. This is the contract; see ADR 0007 and
# Tellurium/tests/test_boundary_contract.py.
DISPATCH: Dict[str, str] = {
    "mm": "simulate_michaelis_menten",
    "sir": "simulate_sir",
    "seir": "simulate_seir",
    "pcr": "simulate_pcr",
    "monte_carlo_pi": "simulate_monte_carlo_pi",
    "wright_fisher": "simulate_wright_fisher",
    "two_locus_wright_fisher": "simulate_two_locus_wright_fisher",
    "molecular_dynamics": "simulate_molecular_dynamics",
    "sbml": "simulate_sbml",
}

_RUNNERS: Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]] = {
    "mm": run_mm,
    "sir": run_sir,
    "seir": run_seir,
    "pcr": run_pcr,
    "monte_carlo_pi": run_monte_carlo_pi,
    "wright_fisher": run_wright_fisher,
    "two_locus_wright_fisher": run_two_locus_wright_fisher,
    "molecular_dynamics": run_molecular_dynamics,
    "sbml": run_sbml,
}


def main() -> None:
    try:
        raw = sys.stdin.read()
        if not raw:
            raise ValueError("no input JSON provided")
        payload = json.loads(raw)
        domain = payload.get("domain")
        params = payload.get("parameters", {})

        if domain not in DISPATCH:
            raise ValueError(f"unknown domain: {domain!r}")
        if not isinstance(params, dict):
            raise ValueError(f"parameters must be an object, got {type(params).__name__}")

        result = _RUNNERS[domain](params)
        print(json.dumps(result))
    except Exception as exc:
        error_payload = {"ok": False, "error": str(exc)}
        print(json.dumps(error_payload), file=sys.stdout)
        sys.exit(1)


if __name__ == "__main__":
    main()
