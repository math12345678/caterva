
# ---- from caterva/continuous/model_building.py ----

def build_sir_antimony(beta: float, gamma: float, s0: float, i0: float,
                       r0_recovered: float = 0.0, model_name: str = "sir",
                       validate: bool = True) -> str:
    """Build a standard frequency-dependent SIR model.

        dS/dt = -beta*S*I/N
        dI/dt =  beta*S*I/N - gamma*I
        dR/dt =  gamma*I
    """
    if validate:
        validate_sir_params(beta, gamma, s0, i0, r0_recovered).raise_if_invalid()
    _check_model_name(model_name)
    n = s0 + i0 + r0_recovered
    return (
        f"model {model_name}\n"
        f"{_GAMMA_NOTE}"
        f"  J0: S -> I; beta * S * I / N;\n"
        f"  J1: I -> R; {GAMMA_PARAM} * I;\n"
        f"  S = {_fmt(s0)};\n"
        f"  I = {_fmt(i0)};\n"
        f"  R = {_fmt(r0_recovered)};\n"
        f"  beta = {_fmt(beta)};\n"
        f"  {GAMMA_PARAM} = {_fmt(gamma)};\n"
        f"  N = {_fmt(n)};\n"
        f"end\n"
    )


def build_seir_antimony(beta: float, sigma: float, gamma: float, s0: float,
                        e0: float, i0: float, r0_recovered: float = 0.0,
                        model_name: str = "seir",
                        validate: bool = True) -> str:
    """Build an SEIR model with an explicit latent (exposed) compartment.

        dS/dt = -beta*S*I/N
        dE/dt =  beta*S*I/N - sigma*E
        dI/dt =  sigma*E - gamma*I
        dR/dt =  gamma*I
    """
    if validate:
        validate_seir_params(beta, sigma, gamma, s0, e0, i0, r0_recovered).raise_if_invalid()
    _check_model_name(model_name)
    n = s0 + e0 + i0 + r0_recovered
    return (
        f"model {model_name}\n"
        f"{_GAMMA_NOTE}"
        f"  J0: S -> E; beta * S * I / N;\n"
        f"  J1: E -> I; sigma * E;\n"
        f"  J2: I -> R; {GAMMA_PARAM} * I;\n"
        f"  S = {_fmt(s0)};\n"
        f"  E = {_fmt(e0)};\n"
        f"  I = {_fmt(i0)};\n"
        f"  R = {_fmt(r0_recovered)};\n"
        f"  beta = {_fmt(beta)};\n"
        f"  sigma = {_fmt(sigma)};\n"
        f"  {GAMMA_PARAM} = {_fmt(gamma)};\n"
        f"  N = {_fmt(n)};\n"
        f"end\n"
    )


def build_lotka_volterra_antimony(alpha: float, beta: float, gamma: float,
                                  delta: float, p0: float, v0: float,
                                  model_name: str = "lotka_volterra",
                                  validate: bool = True) -> str:
    """Build a Lotka-Volterra predator-prey model (Lotka 1925; Volterra 1926).

        dP/dt = alpha*P - beta*P*V   (prey: growth, predation loss)
        dV/dt = gamma*P*V - delta*V  (predator: growth from predation, death)

    P and V are declared with direct rate rules (Antimony ``P' = ...``
    syntax), not mass-action reactions -- there is no real chemical
    species here, just two coupled populations, and a rate rule is the
    faithful translation of the ODE as the source states it.
    """
    if validate:
        validate_lotka_volterra_params(alpha, beta, gamma, delta, p0, v0).raise_if_invalid()
    _check_model_name(model_name)
    # 'gamma' is a reserved function name in Antimony (the gamma function) --
    # same collision the SIR/SEIR recovery rate hits (see GAMMA_PARAM /
    # _GAMMA_NOTE above). The predator growth-from-predation rate is
    # therefore emitted as 'gamma_rate' below; the Python API still takes
    # 'gamma'.
    return (
        f"model {model_name}\n"
        f"{_GAMMA_NOTE}"
        f"  P' = alpha * P - beta * P * V;\n"
        f"  V' = {GAMMA_PARAM} * P * V - delta * V;\n"
        f"  P = {_fmt(p0)};\n"
        f"  V = {_fmt(v0)};\n"
        f"  alpha = {_fmt(alpha)};\n"
        f"  beta = {_fmt(beta)};\n"
        f"  {GAMMA_PARAM} = {_fmt(gamma)};\n"
        f"  delta = {_fmt(delta)};\n"
        f"end\n"
    )


TYSON_KAPPA = 0.015


TYSON_K6 = 1.0


TYSON_K4 = 180.0


TYSON_K4PRIME = 0.018


def build_cell_cycle_oscillator_antimony(
        model_name: str = "cell_cycle_oscillator") -> str:
    """Build Tyson's (1991) 2-variable cdc2-cyclin relaxation oscillator.

    No caller-supplied kinetic parameters: every rate constant is the
    literature's own standard oscillatory set (see module-level comment
    above), so there is nothing here for a caller to get wrong. This
    mirrors how ``molecular_dynamics`` treats its Lennard-Jones constants.
    """
    _check_model_name(model_name)
    return (
        f"model {model_name}\n"
        f"  u' = k4 * (v - u) * (alpha + u^2) - k6 * u;\n"
        f"  v' = kappa - k6 * u;\n"
        f"  u = 0;\n"
        f"  v = 0;\n"
        f"  kappa = {_fmt(TYSON_KAPPA)};\n"
        f"  k6 = {_fmt(TYSON_K6)};\n"
        f"  k4 = {_fmt(TYSON_K4)};\n"
        f"  k4prime = {_fmt(TYSON_K4PRIME)};\n"
        f"  alpha := k4prime / k4;\n"
        f"  cyclin_fraction := v - u;\n"
        f"end\n"
    )


REPRESSILATOR_ALPHA = 216.404


REPRESSILATOR_ALPHA0 = 0.2164


REPRESSILATOR_BETA = 0.2


REPRESSILATOR_N = 2.0


def build_repressilator_antimony(
        model_name: str = "repressilator") -> str:
    """Build the Elowitz & Leibler (2000) repressilator.

    No caller-supplied kinetic parameters, for the same reason as the
    cell cycle oscillator: the model is defined by the literature's own
    standard oscillatory parameter set.
    """
    _check_model_name(model_name)
    return (
        f"model {model_name}\n"
        f"  m1' = -m1 + alpha / (1 + p3^n) + alpha0;\n"
        f"  m2' = -m2 + alpha / (1 + p1^n) + alpha0;\n"
        f"  m3' = -m3 + alpha / (1 + p2^n) + alpha0;\n"
        f"  p1' = -beta * (p1 - m1);\n"
        f"  p2' = -beta * (p2 - m2);\n"
        f"  p3' = -beta * (p3 - m3);\n"
        f"  m1 = 0; m2 = 0; m3 = 0;\n"
        f"  p1 = 1; p2 = 2; p3 = 3;\n"
        f"  alpha = {_fmt(REPRESSILATOR_ALPHA)};\n"
        f"  alpha0 = {_fmt(REPRESSILATOR_ALPHA0)};\n"
        f"  beta = {_fmt(REPRESSILATOR_BETA)};\n"
        f"  n = {_fmt(REPRESSILATOR_N)};\n"
        f"end\n"
    )


