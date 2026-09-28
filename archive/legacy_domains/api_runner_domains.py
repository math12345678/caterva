
# ---- from Science-Agent-Pipeline/artifacts/api-server/src/lib/caterva_runner.py ----

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


