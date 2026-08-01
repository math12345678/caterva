"""Continuous domains: antimony/SBML model building and roadrunner ODE simulation."""

try:
    from Tellurium.continuous.model_building import (
        GAMMA_PARAM,
        _GAMMA_NOTE,
        build_michaelis_menten_antimony,
        build_sir_antimony,
        build_seir_antimony,
        antimony_to_sbml,
        sbml_to_antimony,
        validate_sbml,
    )
    from Tellurium.continuous.simulations import (
        simulate_sbml,
        simulate_michaelis_menten,
        simulate_sir,
        simulate_seir,
        steady_state,
        parameter_scan,
    )
except ModuleNotFoundError:  # flat mode
    from continuous.model_building import (
        GAMMA_PARAM,
        _GAMMA_NOTE,
        build_michaelis_menten_antimony,
        build_sir_antimony,
        build_seir_antimony,
        antimony_to_sbml,
        sbml_to_antimony,
        validate_sbml,
    )
    from continuous.simulations import (
        simulate_sbml,
        simulate_michaelis_menten,
        simulate_sir,
        simulate_seir,
        steady_state,
        parameter_scan,
    )
