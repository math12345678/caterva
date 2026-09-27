#!/usr/bin/env python3
"""JSON bridge between the Node API server and the Python Caterva engine.

The TypeScript API server spawns this script and writes a JSON payload to
stdin. This script imports caterva_engine from the repo root, runs the
requested simulation, and prints a JSON result to stdout.

Usage:
    PYTHONPATH=/repo/root python3 caterva_runner.py < request.json

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
``caterva/tests/test_boundary_contract.py`` fails if the engine's
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
import re
import sys
from typing import Any, Callable, Dict, Sequence

# Used by run_sbml to count a supplied model's reactions/species against the
# MAX_API_SBML_* ceilings. Declared in requirements.txt (python-libsbml) and
# already imported across the engine (caterva/core/sbml_units.py and others),
# so this adds a dependency to this file, not to the project.
import libsbml  # type: ignore[import-untyped]


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

# ---------------------------------------------------------------------------
# Raw-SBML ceilings.
#
# run_sbml had NO ceilings of any kind. That was survivable only because
# nothing could reach it: the API exposes no way to supply a model, and
# resolve_query never yields domain "sbml". Any path that does expose it
# needs these first, because unlike every other domain the cost here is not
# keyed to a parameter this file can reason about.
#
# Measured 2026-09-02 on this machine (Python 3.13, libroadrunner 2.8.0),
# by timing the engine directly:
#
#   points, on a 1-species decay model:
#       51 ......... 0.29s      json    0.00 MB
#       10,000 ..... 0.25s      json    0.40 MB
#       100,000 .... 1.07s      json    4.02 MB
#       500,000 .... 3.97s      json   20.14 MB
#
#   model size, at points=51, linear chain S0->S1->...->Sn:
#       10 reactions .... 0.15s      50 reactions .... 0.84s
#       200 reactions ... 4.66s     500 reactions ... 29.86s
#
# `points` is bounded by the RESULT payload, not by integration time: the
# trajectory is serialised to JSON over the runner's stdout, parsed in Node,
# held in the job queue and persisted. 20 MB per request is the problem long
# before 4 seconds is. 100k points is ~4 MB and far beyond any plotting need
# (no display resolves more than a few thousand points).
#
# Reaction count is the MD trap in a different costume: cost grows FASTER
# than linearly (2.5x the reactions -> 6.4x the time, roughly quadratic), so
# a limit that looks generous becomes a multi-minute request one step later.
# 200 reactions is ~4.7s, a 25x margin under the 120s subprocess timeout, and
# larger than the overwhelming majority of published kinetic models (the
# BioModels median is well under 100 species).
#
# NOTE ON WHAT THESE CANNOT DO: for an arbitrary ODE system, integration cost
# is not a function of any countable input. A STIFF 3-species model can cost
# more than a benign 200-reaction one, and no static ceiling can see that
# coming. These bound the shapes that ARE countable so the caller gets a
# precise, actionable error instead of a timeout; the wall-clock timeout in
# catervaRunner.ts remains the only real backstop for the rest.
MAX_API_SBML_POINTS = 100_000
MAX_API_SBML_REACTIONS = 200
MAX_API_SBML_SPECIES = 200
# A parse-cost guard applied before the document is handed to libsbml, so
# something absurd is rejected without being parsed at all.
#
# Sized against SBML XML, which is what this handler actually receives --
# NOT against Antimony. Measured, same models as above:
#
#     reactions   antimony    sbml xml    ratio
#           10         523       8,251    15.8x
#          100       5,027      75,575    15.0x
#          200      10,627     150,875    14.2x
#
# SBML is ~15x the Antimony source it came from. A first version of this
# constant was 100,000 because it had been sized against the Antimony
# figures, which put it BELOW the ~151 KB a legitimate 200-reaction model
# occupies: it rejected models the reaction ceiling was meant to allow, and
# made MAX_API_SBML_REACTIONS unreachable dead code. Caught by testing each
# ceiling against a real document rather than trusting the arithmetic.
#
# 400,000 is ~2.6x the largest model the reaction/species limits permit,
# leaving room for documents that are denser per reaction (more reactants,
# longer kinetic laws, MIRIAM annotations) while still bounding parse cost.
# The reaction and species ceilings stay the binding constraints, which is
# the intent -- this one is a backstop, not a second opinion.
MAX_API_SBML_SOURCE_CHARS = 400_000

# Antimony is the human-writable DSL the SBML above is usually generated
# from, and it is ~15x more compact (see the ratio table), so its ceiling is
# scaled to match: a model at MAX_API_SBML_REACTIONS is ~10.6 KB of Antimony,
# and 40,000 keeps the same ~2.6x headroom the SBML limit has. The converted
# SBML is checked against every ceiling above regardless, so this only bounds
# the cost of the conversion itself.
MAX_API_ANTIMONY_SOURCE_CHARS = 40_000


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

# The repo root must be on PYTHONPATH so we can import caterva.caterva_engine.
# The API server sets this when spawning the process.
from caterva import caterva_engine  # noqa: E402  # type: ignore
from caterva.core.data_structures import (  # noqa: E402  # type: ignore
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
        # / atol 1e-8 -- a solver Caterva does not use, at tolerances four
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
        vmax, conversion = caterva_engine.vmax_from_kcat(
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

    result = caterva_engine.simulate_michaelis_menten(
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
    # that is an internal name inside caterva_engine, not the API contract.
    i0 = float(params.get("i0", 0.0))
    end = float(params.get("end", 10.0))
    points = int(params.get("points", 51))

    result = caterva_engine.simulate_mm_competitive_inhibition(
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

    result = caterva_engine.simulate_sir(
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

    result = caterva_engine.simulate_seir(
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

    result = caterva_engine.simulate_pcr(
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
    result = caterva_engine.simulate_monte_carlo_pi(
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
    result = caterva_engine.simulate_gillespie_ssa(
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
    result = caterva_engine.simulate_gillespie_ssa_replicates(
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
    result = caterva_engine.simulate_gillespie_ssa_bimolecular(
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

    result = caterva_engine.simulate_wright_fisher(
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

    result = caterva_engine.simulate_two_locus_wright_fisher(
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

    result = caterva_engine.simulate_molecular_dynamics(
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

    result = caterva_engine.simulate_lotka_volterra(
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

    result = caterva_engine.simulate_cell_cycle_oscillator(
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

    result = caterva_engine.simulate_repressilator(
        end=end, points=points, seed=seed
    )

    return _serialise_result(
        result, "repressilator",
        {"end": end, "points": points, "seed": seed},
    )


# Antimony's `import` directive reads files off disk. Verified by execution
# 2026-09-02: `import "<path>"` at the top of a model successfully pulled in
# a local file and its contents became part of the compiled model, and a
# path that exists but is not Antimony returns "Could not open '<path>'",
# which is a file-existence oracle on its own.
#
# So Antimony source is a local-file-read primitive for exactly the same
# reason an unvalidated sbml_string is, by a different mechanism -- the
# language has an include facility and the API has no business honouring it
# for text that arrived over HTTP. There is no legitimate use for it here:
# a caller cannot know what paths exist on the server, so any import in a
# submitted model is either a mistake or an attempt.
#
# Matched on a line whose first token is `import`, which is where the
# directive is valid. Comments (`#` or `//`) are stripped first so a
# commented-out import is not a false positive.
_ANTIMONY_IMPORT_RE = re.compile(r"^\s*import\b", re.IGNORECASE)


def _antimony_to_sbml_for_api(antimony_string: str) -> str:
    """Validate caller-supplied Antimony and translate it to SBML."""
    if len(antimony_string) > MAX_API_ANTIMONY_SOURCE_CHARS:
        raise ValueError(
            f"antimony source is {len(antimony_string)} characters, which "
            f"exceeds the API runtime ceiling "
            f"(MAX_API_ANTIMONY_SOURCE_CHARS) "
            f"{MAX_API_ANTIMONY_SOURCE_CHARS}"
        )

    for lineno, raw in enumerate(antimony_string.splitlines(), start=1):
        line = raw.split("#", 1)[0].split("//", 1)[0]
        if _ANTIMONY_IMPORT_RE.match(line):
            raise ValueError(
                f"antimony 'import' is not permitted (line {lineno}). It "
                "reads files from the server's filesystem. Inline the "
                "model instead."
            )

    try:
        return caterva_engine.antimony_to_sbml(antimony_string)
    except Exception as exc:
        # The engine's own parse error names the line and token, which is
        # the only thing that helps someone fix their model.
        raise ValueError(f"antimony source could not be parsed: {exc}") from exc


def run_sbml(params: Dict[str, Any]) -> Dict[str, Any]:
    """Dispatch for ``simulate_sbml`` -- the raw-SBML escape hatch.

    Included so the contract test can require *every* ``simulate_*`` in the
    engine's ``__all__`` to be dispatched, with no exceptions.

    Unlike every other handler here, the cost of this one is driven by a
    document the caller supplies rather than by parameters this file can
    reason about, so the ceilings are enforced on the document itself. See
    the MAX_API_SBML_* block above for the measurements behind each limit
    and for what they explicitly cannot bound.
    """
    sbml_string = params.get("sbml_string", "")
    antimony_string = params.get("antimony_string", "")
    start = float(params.get("start", 0.0))
    end = float(params.get("end", 10.0))
    points = int(params.get("points", 51))

    if antimony_string and sbml_string:
        raise ValueError(
            "supply either antimony_string or sbml_string, not both"
        )
    if not antimony_string and not sbml_string:
        raise ValueError(
            "a model is required: supply antimony_string or sbml_string"
        )

    if antimony_string:
        sbml_string = _antimony_to_sbml_for_api(antimony_string)

    # SECURITY, and the reason this check exists at all:
    #
    # `simulate_sbml` ends at `roadrunner.RoadRunner(sbml_string)`
    # (caterva/core/utils.py). RoadRunner's constructor does not take SBML
    # CONTENT -- it takes content OR A FILESYSTEM PATH OR A URL, and it
    # fetches whichever it is given. Its own error text says so: "could not
    # open <x> as a file or uri".
    #
    # Verified by execution, 2026-09-02, all three through this handler's
    # own engine call:
    #   - a bare path      -> read off local disk and simulated
    #   - "file://..."     -> same
    #   - "http://..."     -> an OUTBOUND GET to an attacker-chosen URL,
    #                         observed arriving at a local listener, whose
    #                         response was then parsed and run
    #
    # So an unvalidated `sbml_string` is a local-file-read and a
    # server-side request forgery primitive, not merely a parsing surface.
    # On a host with a cloud metadata endpoint (169.254.169.254) or any
    # internal service reachable by GET, that is the whole attack.
    #
    # Requiring the payload to BE an XML document closes it: a path or URL
    # is not well-formed XML, so it never reaches RoadRunner. This must
    # stay an explicit, named check. The reaction-counting parse below
    # happens to reject these too, but relying on that would make the
    # protection an accident of validation order that a later refactor
    # could remove without anyone noticing what it was for.
    stripped = sbml_string.lstrip()
    if not stripped.startswith("<"):
        raise ValueError(
            "model source must be an SBML XML document, not a file path or "
            "URL. The engine's model loader would fetch a path or URL, "
            "which would read local files or make requests from the "
            "server; supply the document itself."
        )

    # Cheapest remaining check: reject an absurd document before libsbml is
    # asked to parse it.
    if len(sbml_string) > MAX_API_SBML_SOURCE_CHARS:
        raise ValueError(
            f"model source is {len(sbml_string)} characters, which exceeds "
            f"the API runtime ceiling (MAX_API_SBML_SOURCE_CHARS) "
            f"{MAX_API_SBML_SOURCE_CHARS}"
        )

    if points > MAX_API_SBML_POINTS:
        raise ValueError(
            f"points={points} exceeds API runtime ceiling "
            f"(MAX_API_SBML_POINTS) {MAX_API_SBML_POINTS}"
        )

    # Counted from the parsed document, not from the source text: the same
    # model can be written many ways, and a regex over the source would
    # both miss and over-count. libsbml has already validated structure by
    # the time these are readable.
    doc = libsbml.readSBMLFromString(sbml_string)
    model = doc.getModel()
    if model is None:
        errors = "; ".join(
            doc.getError(i).getMessage().strip()
            for i in range(min(doc.getNumErrors(), 3))
        )
        raise ValueError(
            "model source could not be parsed as SBML"
            + (f": {errors}" if errors else "")
        )

    n_reactions = model.getNumReactions()
    n_species = model.getNumSpecies()
    if n_reactions > MAX_API_SBML_REACTIONS:
        raise ValueError(
            f"model has {n_reactions} reactions, which exceeds the API "
            f"runtime ceiling (MAX_API_SBML_REACTIONS) "
            f"{MAX_API_SBML_REACTIONS}"
        )
    if n_species > MAX_API_SBML_SPECIES:
        raise ValueError(
            f"model has {n_species} species, which exceeds the API runtime "
            f"ceiling (MAX_API_SBML_SPECIES) {MAX_API_SBML_SPECIES}"
        )

    result = caterva_engine.simulate_sbml(
        sbml_string=sbml_string, start=start, end=end, points=points
    )

    return _serialise_result(
        result, "sbml",
        {"start": start, "end": end, "points": points},
    )



# ---------------------------------------------------------------------------
# The open path: a model the caller CONSTRUCTS, rather than one of sixteen
# names.
#
# Everything above this line dispatches a fixed domain to a fixed engine
# function with a fixed parameter list. This one accepts a reaction network
# -- species, parameters, reactions, rate rules -- validates it, refuses it
# if any of its numbers is unsourced, compiles it and runs it.
#
# WHY IT IS SAFE TO ACCEPT A CALLER-BUILT MODEL HERE
#
# run_sbml's comment above records that an unvalidated model source is a
# local-file-read and SSRF primitive, because the engine's loader will fetch
# a path or a URL. That surface does not exist on this path: the SBML handed
# to the engine is GENERATED by Caterva from a validated structure, never
# supplied by the caller, so there is no string for the loader to interpret
# as a location.
#
# What the caller does supply is rate-law text, and that is checked by
# `caterva/core/network.py`: every symbol must resolve to a species or
# parameter of the same network, no statement syntax, and only a fixed list
# of mathematical functions. A rate law naming something undeclared is
# rejected before compilation with the offending symbol named.
#
# The size ceilings are the SBML ones, deliberately. They bound the same
# resource -- how much work roadrunner is asked to do -- and a second set of
# numbers for the same thing is how two limits drift apart.
# ---------------------------------------------------------------------------


def _network_from_spec(spec: Any) -> Any:
    """Build a ReactionNetwork from the JSON the API sends.

    Defensive about shape at every step: this structure originates outside
    the process and may have been produced by a language model. A missing
    key or a wrong type is reported as a message a caller can act on, not
    as a KeyError or a TypeError from three frames down.
    """
    from caterva.core.network import (
        AssignmentRule, Parameter, RateRule, Reaction, ReactionNetwork, Species,
    )

    if not isinstance(spec, dict):
        raise ValueError(
            f"network must be an object, got {type(spec).__name__}"
        )

    def _seq(key: str) -> List[Any]:
        value = spec.get(key, [])
        if value is None:
            return []
        if not isinstance(value, list):
            raise ValueError(f"network.{key} must be a list")
        return value

    def _entry(item: Any, key: str, index: int) -> Dict[str, Any]:
        if not isinstance(item, dict):
            raise ValueError(
                f"network.{key}[{index}] must be an object, got "
                f"{type(item).__name__}"
            )
        return item

    def _stoich(raw: Any, where: str) -> Dict[str, int]:
        if raw is None:
            return {}
        if not isinstance(raw, dict):
            raise ValueError(f"{where} must be an object of species -> count")
        out: Dict[str, int] = {}
        for sid, count in raw.items():
            if isinstance(count, bool) or not isinstance(count, int):
                # Antimony accepts non-integer stoichiometry; Caterva does
                # not, because a fractional coefficient makes the derived
                # conservation laws meaningless as counts of anything.
                raise ValueError(
                    f"{where}.{sid} must be a whole number, got {count!r}"
                )
            out[str(sid)] = count
        return out

    species = tuple(
        Species(str(_entry(s, "species", i).get("id", "")),
                float(_entry(s, "species", i).get("initial", 0.0)))
        for i, s in enumerate(_seq("species"))
    )
    parameters = tuple(
        Parameter(str(_entry(p_, "parameters", i).get("id", "")),
                  float(_entry(p_, "parameters", i).get("value", 0.0)))
        for i, p_ in enumerate(_seq("parameters"))
    )
    reactions = tuple(
        Reaction(
            str(_entry(r, "reactions", i).get("id", "")),
            _stoich(r.get("reactants"), f"network.reactions[{i}].reactants"),
            _stoich(r.get("products"), f"network.reactions[{i}].products"),
            str(r.get("rateLaw", r.get("rate_law", ""))),
        )
        for i, r in enumerate(_seq("reactions"))
    )
    rate_rules = tuple(
        RateRule(str(_entry(r, "rateRules", i).get("target", "")),
                 str(_entry(r, "rateRules", i).get("expression", "")))
        for i, r in enumerate(_seq("rateRules"))
    )
    assignment_rules = tuple(
        AssignmentRule(str(_entry(r, "assignmentRules", i).get("target", "")),
                       str(_entry(r, "assignmentRules", i).get("expression", "")))
        for i, r in enumerate(_seq("assignmentRules"))
    )

    return ReactionNetwork(
        name=str(spec.get("name", "network")),
        species=species,
        parameters=parameters,
        reactions=reactions,
        rate_rules=rate_rules,
        assignment_rules=assignment_rules,
    )


def _sources_from_spec(spec: Any) -> Dict[str, Any]:
    """Build the provenance map. An absent map is an EMPTY map, never a
    permissive one -- with no sources the network is refused, quantity by
    quantity, which is the intended behaviour and not an error case."""
    from caterva.core.network_provenance import QuantitySource

    if spec is None:
        return {}
    if not isinstance(spec, dict):
        raise ValueError("sources must be an object of quantity -> source")
    out: Dict[str, Any] = {}
    for quantity, source in spec.items():
        if not isinstance(source, dict):
            raise ValueError(
                f"sources.{quantity} must be an object with an 'origin'"
            )
        out[str(quantity)] = QuantitySource(
            origin=str(source.get("origin", "")),
            citation=source.get("citation"),
            note=source.get("note"),
        )
    return out


def run_network(params: Dict[str, Any]) -> Dict[str, Any]:
    """Simulate a caller-constructed reaction network."""
    from caterva.core.network import describe_conservation_laws
    from caterva.core.network_provenance import (
        compile_with_provenance, provenance_report,
    )

    network = _network_from_spec(params.get("network"))
    sources = _sources_from_spec(params.get("sources"))

    start = float(params.get("start", 0.0))
    end = float(params.get("end", 10.0))
    points = int(params.get("points", 51))

    if points > MAX_API_SBML_POINTS:
        raise ValueError(
            f"points={points} exceeds API runtime ceiling "
            f"(MAX_API_SBML_POINTS) {MAX_API_SBML_POINTS}"
        )
    n_reactions = len(network.reactions) + len(network.rate_rules)
    if n_reactions > MAX_API_SBML_REACTIONS:
        raise ValueError(
            f"network has {n_reactions} reactions and rate rules, which "
            f"exceeds the API runtime ceiling (MAX_API_SBML_REACTIONS) "
            f"{MAX_API_SBML_REACTIONS}"
        )
    if len(network.species) > MAX_API_SBML_SPECIES:
        raise ValueError(
            f"network has {len(network.species)} species, which exceeds the "
            f"API runtime ceiling (MAX_API_SBML_SPECIES) "
            f"{MAX_API_SBML_SPECIES}"
        )

    # Structure, then provenance, then compilation -- and every one of them
    # before roadrunner is asked for anything. A model that will be refused
    # must cost nothing to refuse.
    antimony_string = compile_with_provenance(network, sources)
    sbml_string = caterva_engine.antimony_to_sbml(antimony_string)

    result = caterva_engine.simulate_sbml(
        sbml_string=sbml_string, start=start, end=end, points=points
    )

    payload = _serialise_result(
        result, "network",
        {"start": start, "end": end, "points": points,
         "networkName": network.name},
    )
    # What the model conserves, derived from its own stoichiometry rather
    # than asserted by anyone, and what backs each of its numbers. Both are
    # things a reader of a simulation is entitled to and cannot currently
    # get from any other domain.
    payload["conservationLaws"] = describe_conservation_laws(network)
    payload["quantitySources"] = provenance_report(network, sources)
    payload["antimony"] = antimony_string

    # Opt-in: which of these numbers is the answer resting on, and how good
    # is each one?
    #
    # Costs two extra integrations per quantity (central differences), so a
    # caller asks for it rather than paying for it on every run. On by
    # default would make an interactive request several times slower for a
    # result most callers do not read.
    if params.get("audit"):
        from caterva.core.model_audit import audit as audit_model
        from caterva.core.sensitivity import analyse

        def _rerun(candidate):
            return caterva_engine.simulate_sbml(
                sbml_string=caterva_engine.antimony_to_sbml(
                    compile_with_provenance(candidate, sources)
                ),
                start=start,
                end=end,
                points=points,
            )

        report = analyse(network, _rerun)
        result_audit = audit_model(network, report, sources)
        payload["audit"] = {
            "summary": result_audit.summary(),
            "caveats": list(result_audit.caveats),
            "quantities": [
                {
                    "quantity": q.quantity,
                    "peakRelativeSensitivity": q.sensitivity.peak,
                    "peakSpecies": q.sensitivity.peak_species,
                    "peakTime": q.sensitivity.peak_time,
                    "sourceTier": q.tier,
                    "citation": q.citation,
                    "influential": q.influential,
                    "worthMeasuring": q.worth_measuring,
                }
                for q in result_audit.quantities
            ],
            "unranked": [
                {"quantity": q, "reason": why} for q, why in result_audit.unranked
            ],
            "toMeasure": [q.quantity for q in result_audit.to_measure],
        }

    return payload


# domain -> engine function name. This is the contract; see ADR 0007 and
# caterva/tests/test_boundary_contract.py. 16 API domains + SBML escape
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
# and SimulationDomain in catervaRunner.ts now lists them.
#
# lotka_volterra, cell_cycle_oscillator, repressilator: see ADR 0022.
def run_parameterize(
    params: Dict[str, Any], *, resolve: Any = None
) -> Dict[str, Any]:
    """Build a model from a description by searching the literature for it.

    The open path's other half. `run_network` takes a network whose values
    the caller already has; this takes a network whose values it does not,
    and goes and looks for them -- resolving every constant concurrently,
    judging whether the set composes, re-searching under whatever the
    judgement requires, and exploring each candidate organism when the
    literature offers more than one.

    Returns the search, including the branches that did NOT work out. Those
    are the useful part: "no Ki has been measured in human, though one
    exists in rabbit" is a result, and a report that showed only the
    surviving branch would have thrown it away.
    """
    # `Tests/` holds the literature layer. Located from the importable
    # `caterva` package rather than from this file's path, for the reason
    # given at the model_ensemble import below: the runner is spawned with
    # a PYTHONPATH the server chooses, and walking up from __file__ breaks
    # the moment either tree moves.
    import sys as _sys

    import caterva as _caterva_pkg  # noqa: PLC0415

    repo_root = pathlib.Path(_caterva_pkg.__file__).resolve().parent.parent
    for candidate in (repo_root, repo_root / "Tests"):
        if str(candidate) not in _sys.path:
            _sys.path.insert(0, str(candidate))

    from caterva.agents.assembly import search_model
    from caterva.agents.scouts import brenda_resolver
    from Tests.parameterize import ParameterRequest

    network = _network_from_spec(params.get("network"))
    raw_requests = params.get("requests") or []
    if not raw_requests:
        raise ValueError(
            "parameterize needs at least one request: the quantities to "
            "resolve. An empty list would return a model with every "
            "placeholder value intact."
        )

    requests = [
        ParameterRequest(
            quantity=str(entry["quantity"]),
            subject=entry.get("subject"),
            substrate=entry.get("substrate"),
            organism=entry.get("organism"),
            ec_number=entry.get("ec_number"),
            table=entry.get("table"),
            expected_unit=entry.get("expected_unit"),
        )
        for entry in raw_requests
    ]

    declared = {r.quantity for r in requests}
    available = set(network.quantity_ids())
    unknown = declared - available
    if unknown:
        raise ValueError(
            f"asked to resolve {sorted(unknown)}, which this network does "
            f"not contain. Its quantities are {sorted(available)}."
        )

    # Quantities the caller is NOT asking the literature for -- their own
    # bench measurements, and the scenario choices no paper could supply
    # (an initial concentration, a simulation window). The literature fills
    # what it can; the caller declares the rest; anything left over is
    # refused by name, quantity by quantity, exactly as `run_network` does.
    caller_sources = _sources_from_spec(params.get("sources"))

    # `resolve` is keyword-only and `main()` never supplies it, so a
    # request body cannot reach it. It exists so this path can be exercised
    # without BRENDA -- a front door that can only be tested online is a
    # front door nobody tests.
    search = search_model(
        network=network,
        requests=requests,
        resolve=resolve or brenda_resolver(),
        requested_organism=params.get("organism"),
    )

    payload = _serialise_search(search)
    payload["simulation"] = _simulate_search(search, caller_sources, params)
    return payload


def _simulate_search(
    search: Any, caller_sources: Dict[str, Any], params: Dict[str, Any]
) -> Dict[str, Any]:
    """Run the chosen model, or say precisely why it was not run.

    The end of the loop: a description goes in, and what comes out is a
    trajectory computed from constants that are each cited, that were
    checked against each other, and that all describe the same organism --
    or a statement of which of those three did not hold.

    Every refusal below is a different fact and keeps its own sentence. A
    single "could not simulate" would collapse "the literature has no human
    Ki", "you did not tell us the enzyme concentration" and "these values
    are from two animals" into one unactionable line.
    """
    from caterva.core.network_provenance import (
        QuantitySource, compile_with_provenance, unsourced_quantities,
    )

    build = search.build
    if build is None:
        return {
            "ran": False,
            "because": (
                "no single model was chosen: "
                + (
                    "more than one organism yields a complete model and "
                    "nothing in the request separates them"
                    if search.undecided
                    else "no organism has every constant this model needs"
                )
            ),
        }
    if build.missing:
        return {
            "ran": False,
            "because": (
                f"no measured value for {', '.join(build.missing)}; Caterva "
                f"does not substitute a default for a constant the "
                f"literature did not supply"
            ),
        }
    compatibility = build.compatibility
    if compatibility is not None and compatibility.blocking:
        return {
            "ran": False,
            "because": (
                "the resolved values do not describe one system: "
                + "; ".join(f.detail for f in compatibility.blocking)
            ),
        }

    # Resolved values become `resolved` sources carrying the citation the
    # scout came back with. Merged UNDER the caller's map, not over it: a
    # caller who supplied their own measurement for a quantity keeps it,
    # since their assay is the one they are modelling.
    sources: Dict[str, Any] = {}
    for quantity, resolution in build.resolutions.items():
        source = resolution.source
        if source is None:
            continue
        sources[quantity] = QuantitySource(
            origin="resolved",
            citation=source.citation,
            note=(
                f"{source.value} {source.unit or ''}".strip()
                + (f", {source.organism}" if source.organism else "")
                + (f", pH {source.ph:g}" if source.ph is not None else "")
                + (
                    f", {source.temperature_c:g} C"
                    if source.temperature_c is not None
                    else ""
                )
            ),
        )
    sources.update(caller_sources)

    from caterva.agents.adapters import with_resolved_values

    network = with_resolved_values(
        build.run.blackboard.get("network"), build.resolutions
    )

    problems = unsourced_quantities(network, sources)
    if problems:
        # Names for a caller to act on, sentences for a person to read.
        # The names come from asking the SAME predicate per quantity rather
        # than from splitting the sentences, so a reworded message cannot
        # quietly change which quantities the machine-readable field lists.
        unsourced = [
            quantity
            for quantity in network.quantity_ids()
            if sources.get(quantity) is None
            or sources[quantity].problems(quantity)
        ]
        return {
            "ran": False,
            "because": (
                f"{len(unsourced)} quantit"
                f"{'y' if len(unsourced) == 1 else 'ies'} the literature was "
                f"not asked for and you did not supply: "
                f"{', '.join(unsourced)}. Send them under `sources` and they "
                f"will be recorded as yours."
            ),
            "unsourced": unsourced,
            "problems": list(problems),
        }

    start = float(params.get("start", 0.0))
    end = float(params.get("end", 10.0))
    points = int(params.get("points", 51))
    if points > MAX_API_SBML_POINTS:
        raise ValueError(
            f"points={points} exceeds API runtime ceiling "
            f"(MAX_API_SBML_POINTS) {MAX_API_SBML_POINTS}"
        )

    antimony_string = compile_with_provenance(network, sources)
    sbml_string = caterva_engine.antimony_to_sbml(antimony_string)
    result = caterva_engine.simulate_sbml(
        sbml_string=sbml_string, start=start, end=end, points=points
    )
    serialised = _serialise_result(
        result, "parameterize", {"start": start, "end": end, "points": points}
    )
    return {
        "ran": True,
        "trajectory": serialised.get("trajectory", []),
        "values": {p.id: p.value for p in network.parameters},
        "initials": {s.id: s.initial for s in network.species},
        "quantitySources": {
            quantity: {
                "origin": source.origin,
                "citation": source.citation,
                "note": source.note,
            }
            for quantity, source in sources.items()
        },
    }


def _serialise_search(search: Any) -> Dict[str, Any]:
    """The search as JSON, branches included."""
    def source_payload(source: Any) -> Any:
        if source is None:
            return None
        return {
            "value": source.value,
            "unit": source.unit,
            "organism": source.organism,
            "ph": source.ph,
            "temperature_c": source.temperature_c,
            "buffer": source.buffer,
            "citation": source.citation,
            "cross_species": source.cross_species,
            "explicitly_unreported": list(source.explicitly_unreported),
        }

    def build_payload(build: Any) -> Dict[str, Any]:
        compatibility = build.compatibility
        return {
            "converged": build.run.converged,
            "rounds": build.run.round_count,
            "constraints": [
                {
                    "kind": c.kind,
                    "subject": c.subject,
                    "requirement": c.requirement,
                    "reason": c.reason,
                    "raised_by": c.raised_by,
                }
                for c in build.run.constraints.all()
            ],
            "resolved": {
                quantity: source_payload(getattr(r, "source", None))
                for quantity, r in build.resolutions.items()
            },
            "missing": {
                quantity: build.resolutions[quantity].reason
                for quantity in build.missing
            },
            "findings": [
                {
                    "kind": f.kind,
                    "severity": f.severity,
                    "quantities": list(f.quantities),
                    "detail": f.detail,
                }
                for f in (compatibility.findings if compatibility else ())
            ],
            "unassessable": list(compatibility.unassessable) if compatibility else [],
            "coherent": bool(compatibility.coherent) if compatibility else False,
            "simulated": bool(build.simulation.get("ran")),
            "not_simulated_because": build.simulation.get("refused_because"),
            "summary": build.summary(),
        }

    chosen = search.build
    return {
        "domain": "parameterize",
        "chosen_organism": search.chosen.organism if search.chosen else None,
        "undecided_organisms": list(search.undecided),
        "branches": [
            {
                "organism": branch.organism,
                "complete": branch.complete,
                "build": build_payload(branch.build),
            }
            for branch in search.branches
        ],
        "model": build_payload(chosen) if chosen is not None else None,
        "summary": search.summary(),
    }


def run_compose(params: Dict[str, Any]) -> Dict[str, Any]:
    """Build a model from a description of its MECHANISM, with no catalogue.

    The third path, and the only one that needs neither a catalogue entry
    nor a language model. `caterva/compose` recognises a shape -- a cascade,
    a toggle switch, competition for a substrate -- and composes it from
    motifs whose rate laws are dimensionally checked before anything runs.

    Measured on the twenty-query benchmark: this builds eleven, and nine of
    those eleven are queries the catalogue cannot reach at any length,
    because "three step" becomes "four step" and each would need its own
    entry.

    It refuses two kinds of thing, and the difference is carried through to
    the caller: a NAMED PATHWAY needs a pathway database Caterva does not
    read, and an unrecognised SHAPE needs different words. Collapsing them
    would send somebody asking about glycolysis away to rephrase forever.
    """
    import sys as _sys

    import caterva as _caterva_pkg  # noqa: PLC0415

    repo_root = pathlib.Path(_caterva_pkg.__file__).resolve().parent.parent
    for candidate in (repo_root, repo_root / "Tests"):
        if str(candidate) not in _sys.path:
            _sys.path.insert(0, str(candidate))

    from caterva.compose.pipeline import UnrecognisedShape, compose

    description = params.get("description") or params.get("query")
    if not description or not str(description).strip():
        raise ValueError(
            "compose needs a `description` of the mechanism -- 'three step "
            "phosphorylation cascade', 'two enzymes competing for the same "
            "substrate'. It builds shapes, not named subjects."
        )

    try:
        model = compose(
            str(description),
            subject=params.get("subject"),
            name=params.get("name"),
        )
    except UnrecognisedShape as exc:
        # Returned as a RESULT rather than raised, because a refusal here is
        # an ordinary outcome carrying information the caller needs -- which
        # of the two refusals it was, and what would work instead.
        return {
            "ok": True,
            "domain": "compose",
            "built": False,
            "reason": str(exc),
            "kind": (
                "named_pathway" if "named pathway" in str(exc)
                else "unrecognised_shape"
            ),
            "shapes": list(_shapes()),
        }

    network = model.network
    unit_findings = model.recognition.composition.unit_findings()

    return {
        "ok": True,
        "domain": "compose",
        "built": True,
        "rule": model.recognition.rule,
        "reading": model.recognition.reading,
        "network": {
            "name": network.name,
            "species": [
                {"id": s.id, "initial": s.initial} for s in network.species
            ],
            "parameters": [
                {"id": p.id, "value": p.value} for p in network.parameters
            ],
            "reactions": [
                {
                    "id": r.id,
                    "reactants": dict(r.reactants),
                    "products": dict(r.products),
                    "rateLaw": r.rate_law,
                }
                for r in network.reactions
            ],
        },
        "conservationLaws": _conservation_law_strings(network),
        "notes": list(model.recognition.composition.notes),
        "toResolve": [
            {
                "id": q.parameter_id,
                "motif": q.motif_name,
                "parameter": q.parameter_name,
                "unit": q.unit,
                "table": q.table,
                "description": q.description,
            }
            for q in model.resolvable
        ],
        "yourChoice": list(model.chosen),
        "structureOnly": model.structure_only,
        "unitFindings": [
            {"where": f.where, "detail": f.detail, "severity": f.severity}
            for f in unit_findings
        ],
        "summary": model.summary(),
    }


def _shapes() -> Any:
    from caterva.compose.grammar import shapes

    return shapes()


def _conservation_law_strings(network: Any) -> Any:
    from caterva.core.network import describe_conservation_laws

    return list(describe_conservation_laws(network))


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

#: Domains handled here that do NOT map to one engine `simulate_*`.
#:
#: DISPATCH is the domain -> engine-function contract (ADR 0007), and
#: test_boundary_contract.py requires it to be exhaustive over the engine's
#: __all__ in both directions. That contract is correct and stays.
#:
#: `network` does not fit it, and forcing it in would be a lie: it composes
#: three engine calls -- compile_with_provenance, antimony_to_sbml,
#: simulate_sbml -- and there is no single `simulate_network` for DISPATCH to
#: name. Declaring the category is better than either weakening the contract
#: or inventing an engine function to satisfy it.
#:
#: The boundary test reads this, so a composed domain is still required to
#: have a handler and is still not allowed to be unreachable.
COMPOSED_DOMAINS: Dict[str, str] = {
    "compose": (
        "a description of a MECHANISM rather than a named model: the shape "
        "is recognised deterministically, composed from motifs, and its "
        "rate laws are dimensionally checked before anything runs"
    ),
    "parameterize": (
        "a network whose constants are unknown: every one is searched for "
        "concurrently, the set is judged for mutual compatibility, the "
        "search re-runs under whatever that judgement requires, and each "
        "candidate organism is explored rather than chosen between"
    ),
    "network": (
        "a caller-constructed reaction network: validated, refused if any "
        "quantity is unsourced, then compiled to Antimony and simulated"
    ),
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
    "compose": run_compose,
    "parameterize": run_parameterize,
    # The open path. Deliberately absent from DISPATCH: that table
    # maps a domain to an engine `simulate_*` function and is asserted
    # exhaustive against the engine's __all__ by
    # test_boundary_contract.py. `network` has no single engine
    # function -- it composes compile_with_provenance,
    # antimony_to_sbml and simulate_sbml -- so adding it there would
    # break a contract that is correct as it stands.
    "network": run_network,
}


def main() -> None:
    # `--list-domains`: what this engine can actually simulate, from DISPATCH.
    #
    # WHY THIS EXISTS
    # ---------------
    # Caterva advertises fifteen teaching domains. Until now nothing could
    # tell a student what they are. `scientificCLI.ts help` lists nine
    # commands, all of them enzyme kinetics or generic; `python -m caterva.cli
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
                # Ensemble runs replicate a single engine function, so this
                # one is correctly gated on DISPATCH: a composed domain has
                # no single function to replicate.
                raise ValueError(f"unknown domain: {domain!r}")  # noqa: TRY301
            spec = payload.get("ensemble") or {}
            parameter = spec.get("parameter")
            draws = spec.get("draws")
            if not parameter or not isinstance(draws, list) or not draws:
                raise ValueError(  # noqa: TRY301
                    "ensemble needs {'parameter': name, 'draws': [...], 'seed': n}"
                )

            # `Tests/` holds the literature layer. Located from the
            # importable `caterva` package rather than from this file's
            # path: the runner is spawned with a PYTHONPATH the server
            # chooses, and walking up from __file__ would break the
            # moment either tree moves.
            import caterva as _caterva_pkg  # noqa: PLC0415
            _root = pathlib.Path(_caterva_pkg.__file__).resolve().parent.parent
            sys.path.insert(0, str(_root / "Tests"))
            from model_ensemble import run_model_ensemble  # noqa: PLC0415

            simulate = getattr(caterva_engine, DISPATCH[domain])
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

        # Membership is tested against the DECLARED domains -- DISPATCH plus
        # COMPOSED_DOMAINS -- and not against _RUNNERS.
        #
        # That distinction carries the error message. A domain this build
        # declares but has no handler for is a BUILD DEFECT, and saying
        # "unknown domain" for it blames the caller for a request that was
        # fine. Testing _RUNNERS directly would collapse the two cases into
        # the wrong one; the missing-handler check below keeps them apart.
        if domain not in DISPATCH and domain not in COMPOSED_DOMAINS:
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
                f"internal error: domain {domain!r} is declared (DISPATCH or "
                f"COMPOSED_DOMAINS) but has no handler in _RUNNERS. This is a "
                f"build defect, not a bad request."
            )

        result = runner_fn(params)
        print(json.dumps(result))
    except Exception as exc:
        error_payload = {"ok": False, "error": str(exc)}
        print(json.dumps(error_payload), file=sys.stdout)
        sys.exit(1)


if __name__ == "__main__":
    main()
