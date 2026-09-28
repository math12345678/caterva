
# ---- from caterva/continuous/simulations.py ----

def simulate_sir(beta: float, gamma: float, s0: float, i0: float,
                  r0_recovered: float = 0.0, start: float = 0.0,
                  end: float = 100.0, points: int = 101) -> SimulationResult:
    """Validate, build, translate and integrate an SIR epidemiological model.
    
    This implements the classic SIR (Susceptible-Infected-Recovered) model
    for disease spread. The model tracks three compartments over time and
    is commonly used in epidemiology teaching and research.
    
    Args:
        beta: Transmission rate (higher = faster spread)
        gamma: Recovery rate (higher = faster recovery)
        s0: Initial number of susceptible individuals
        i0: Initial number of infected individuals
        r0_recovered: Initial number of recovered individuals
        start: Start time for simulation
        end: End time for simulation
        points: Number of time points for output
        
    Returns:
        SimulationResult containing the time evolution of all three compartments
        
    Raises:
        ModelBuildError: If parameters are invalid
        SimulationError: If the integration fails
    """
    validation = validate_sir_params(beta, gamma, s0, i0, r0_recovered)
    validation.raise_if_invalid()
    model = build_sir_antimony(beta, gamma, s0, i0, r0_recovered)
    sbml = antimony_to_sbml(model, "sir")
    return simulate_sbml(sbml, start, end, points, model_name="sir",
                         validation=validation)


def simulate_seir(beta: float, sigma: float, gamma: float, s0: float,
                  e0: float, i0: float, r0_recovered: float = 0.0,
                  start: float = 0.0, end: float = 100.0,
                  points: int = 101) -> SimulationResult:
    """Validate, build, translate and integrate an SEIR epidemiological model.
    
    This is an extension of the SIR model that adds an exposed compartment (E)
    representing individuals who have been infected but are not yet infectious.
    This better models diseases with incubation periods like COVID-19.
    
    Args:
        beta: Transmission rate (higher = faster spread)
        sigma: Progression rate from exposed to infectious
        gamma: Recovery rate (higher = faster recovery)
        s0: Initial number of susceptible individuals
        e0: Initial number of exposed individuals (incubating)
        i0: Initial number of infectious individuals
        r0_recovered: Initial number of recovered individuals
        start: Start time for simulation
        end: End time for simulation
        points: Number of time points for output
        
    Returns:
        SimulationResult containing the time evolution of all four compartments
        
    Raises:
        ModelBuildError: If parameters are invalid
        SimulationError: If the integration fails
    """
    validation = validate_seir_params(beta, sigma, gamma, s0, e0, i0,
                                      r0_recovered)
    validation.raise_if_invalid()
    model = build_seir_antimony(beta, sigma, gamma, s0, e0, i0, r0_recovered)
    sbml = antimony_to_sbml(model, "seir")
    return simulate_sbml(sbml, start, end, points, model_name="seir",
                         validation=validation)


def simulate_lotka_volterra(alpha: float = 1.1, beta: float = 0.4,
                            gamma: float = 0.1, delta: float = 0.4,
                            p0: float = 10.0, v0: float = 5.0,
                            start: float = 0.0, end: float = 20.0,
                            points: int = 201) -> SimulationResult:
    """Validate, build, translate and integrate a Lotka-Volterra
    predator-prey model (Lotka 1925; Volterra 1926).

    Defaults reproduce the classic ~10-year lynx-hare oscillation cycle
    on an annual-cycle time axis: the small-oscillation period is
    ``2*pi/sqrt(alpha*delta) = 9.47``. See docs/adr/0022.

    `gamma` and `delta` were transposed here until 2026-08-09
    (gamma=0.4, delta=0.1). That put the coexistence fixed point
    ``(delta/gamma, alpha/beta)`` at (0.25, 2.75) while the prey starts at
    10 -- a 40x excursion that drove the prey population to -5.9e-11 and
    drifted the system's exactly-conserved first integral by 49%, so the
    integrated trajectory was not the modelled system at all. It also made
    the docstring's own ~10-year claim false: the transposed pair gives a
    period of 18.9, not 9.47.

    Biologically the transposition described predators converting prey into
    offspring (gamma) four times faster than they die (delta); the ordinary
    case, and the one Volterra's own figures use, is gamma < delta. Pinned
    by tests/test_lotka_volterra_correctness.py.
    """
    validation = validate_lotka_volterra_params(alpha, beta, gamma, delta, p0, v0)
    validation.raise_if_invalid()
    model = build_lotka_volterra_antimony(alpha, beta, gamma, delta, p0, v0)
    sbml = antimony_to_sbml(model, "lotka_volterra")
    return simulate_sbml(sbml, start, end, points, model_name="lotka_volterra",
                         validation=validation)


def simulate_cell_cycle_oscillator(start: float = 0.0, end: float = 100.0,
                                   points: int = 1001,
                                   seed: int | None = None) -> SimulationResult:
    """Integrate Tyson's (1991) 2-variable cdc2-cyclin relaxation
    oscillator using the paper's own standard oscillatory parameter set.

    ``seed`` is accepted for call-signature symmetry with the stochastic
    domains but is unused: this is a deterministic ODE system with no
    randomness anywhere in it. See docs/adr/0022.
    """
    del seed  # deterministic model; kept for API symmetry only
    model = build_cell_cycle_oscillator_antimony()
    sbml = antimony_to_sbml(model, "cell_cycle_oscillator")
    return simulate_sbml(sbml, start, end, points,
                         model_name="cell_cycle_oscillator",
                         validation=ParameterValidation())


def simulate_repressilator(start: float = 0.0, end: float = 200.0,
                           points: int = 2001,
                           seed: int | None = None) -> SimulationResult:
    """Integrate the Elowitz & Leibler (2000) repressilator using the
    paper's own standard oscillatory parameter set.

    ``seed`` is accepted for call-signature symmetry with the stochastic
    domains but is unused: this is a deterministic ODE system with no
    randomness anywhere in it. See docs/adr/0022.
    """
    del seed  # deterministic model; kept for API symmetry only
    model = build_repressilator_antimony()
    sbml = antimony_to_sbml(model, "repressilator")
    return simulate_sbml(sbml, start, end, points, model_name="repressilator",
                         validation=ParameterValidation())


