"""Tests moved from caterva/tests/test_engine_api.py on 2026-09-27 with their domains."""

@pytest.fixture
def sir_sbml():
    return antimony_to_sbml(
        build_sir_antimony(beta=0.3, gamma=0.1, s0=999, i0=1))


def test_sir_negative_beta():
    validation = validate_sir_params(beta=-0.1, gamma=0.1, s0=999, i0=1)
    assert not validation.ok
    assert "beta" in validation.errors[0]


def test_sir_zero_population():
    validation = validate_sir_params(beta=0.3, gamma=0.1, s0=0.0, i0=0.0,
                                     r0_recovered=0.0)
    assert not validation.ok
    assert "total population" in validation.errors[0]


def test_sir_zero_infected():
    validation = validate_sir_params(beta=0.3, gamma=0.1, s0=999, i0=0.0)
    assert validation.ok
    assert validation.flagged
    assert "I0 is zero" in validation.flag_reason


def test_sir_above_plausible_r0():
    validation = validate_sir_params(beta=200.0, gamma=0.1, s0=999, i0=1)
    assert validation.ok
    assert validation.flagged
    assert "exceeds" in validation.flag_reason


def test_seir_negative_gamma():
    validation = validate_seir_params(beta=0.3, sigma=0.1, gamma=-0.1, s0=999,
                                      e0=0.0, i0=1)
    assert not validation.ok
    assert "gamma" in validation.errors[0]


def test_seir_zero_total_population():
    validation = validate_seir_params(beta=0.3, sigma=0.1, gamma=0.1, s0=0.0,
                                      e0=0.0, i0=0.0, r0_recovered=0.0)
    assert not validation.ok
    assert "total population" in validation.errors[0]


def test_seir_zero_infected_and_exposed():
    validation = validate_seir_params(beta=0.3, sigma=0.1, gamma=0.1, s0=999,
                                      e0=0.0, i0=0.0)
    assert validation.ok
    assert validation.flagged
    assert "both E0 and I0 are zero" in validation.flag_reason


def test_seir_good_parameters():
    validation = validate_seir_params(beta=0.3, sigma=0.1, gamma=0.1, s0=999,
                                      e0=10.0, i0=1)
    assert validation.ok
    assert not validation.flagged


def test_scan_over_beta_changes_epidemic_size(sir_sbml):
    mild, severe = parameter_scan(sir_sbml, "beta", [0.11, 0.9], end=500.0,
                                  points=101)
    assert severe.final("R") > mild.final("R")
