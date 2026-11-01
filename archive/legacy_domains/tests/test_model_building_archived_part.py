"""Tests moved from caterva/tests/test_model_building.py on 2026-09-27 with their domains."""

def test_sir_model_has_both_transitions():
    src = build_sir_antimony(beta=0.3, gamma=0.1, s0=999, i0=1)
    assert "S -> I" in src
    assert "I -> R" in src


def test_sir_uses_frequency_dependent_transmission():
    # beta*S*I/N, not beta*S*I -- the difference changes the dynamics entirely
    # once population size varies between test cases.
    src = build_sir_antimony(beta=0.3, gamma=0.1, s0=999, i0=1)
    assert "beta * S * I / N" in src
    assert f"{GAMMA_PARAM} * I" in src


def test_sir_population_constant_is_the_sum_of_compartments():
    src = build_sir_antimony(beta=0.3, gamma=0.1, s0=990, i0=8,
                             r0_recovered=2)
    assert "N = 1000.0" in src


def test_sir_records_initial_recovered():
    src = build_sir_antimony(beta=0.3, gamma=0.1, s0=900, i0=10,
                             r0_recovered=90)
    assert "R = 90.0" in src


def test_sir_build_validates_by_default():
    with pytest.raises(ModelBuildError):
        build_sir_antimony(beta=-0.3, gamma=0.1, s0=999, i0=1)


def test_seir_model_has_three_transitions():
    src = build_seir_antimony(beta=0.5, sigma=0.2, gamma=0.1, s0=990, e0=10,
                              i0=0)
    assert "S -> E" in src
    assert "E -> I" in src
    assert "I -> R" in src


def test_seir_infection_is_driven_by_infectious_not_exposed():
    # A classic modelling error is writing beta*S*E/N; exposed individuals are
    # not yet infectious.
    src = build_seir_antimony(beta=0.5, sigma=0.2, gamma=0.1, s0=990, e0=10,
                              i0=0)
    assert "S -> E; beta * S * I / N" in src
    assert "beta * S * E" not in src


def test_recovery_rate_avoids_the_reserved_gamma_symbol():
    # A bare `gamma` is Antimony's built-in gamma function, so emitting it as a
    # parameter name is a hard parse error rather than a shadowing warning.
    # This test pins the workaround: no standalone `gamma` token may appear.
    for src in (build_sir_antimony(beta=0.3, gamma=0.1, s0=999, i0=1),
                build_seir_antimony(beta=0.5, sigma=0.2, gamma=0.1, s0=990,
                                    e0=10, i0=0)):
        code_lines = [ln for ln in src.splitlines()
                      if not ln.strip().startswith("#")]
        for line in code_lines:
            assert "gamma " not in line.replace(GAMMA_PARAM, "")
        # And it must actually parse.
        antimony_to_sbml(src)


def test_generated_model_explains_the_gamma_rename():
    # The model source is shown to students; an unexplained symbol rename
    # would read as a mistake.
    src = build_sir_antimony(beta=0.3, gamma=0.1, s0=999, i0=1)
    assert "#" in src
    assert "reserved" in src


def test_seir_progression_uses_sigma():
    src = build_seir_antimony(beta=0.5, sigma=0.2, gamma=0.1, s0=990, e0=10,
                              i0=0)
    assert "E -> I; sigma * E" in src


def test_seir_population_includes_exposed():
    src = build_seir_antimony(beta=0.5, sigma=0.2, gamma=0.1, s0=900, e0=50,
                              i0=40, r0_recovered=10)
    assert "N = 1000.0" in src


