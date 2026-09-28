"""Tests moved from caterva/tests/test_validation.py on 2026-09-27 with their domains."""

def test_ordinary_sir_params_accepted():
    v = validate_sir_params(beta=0.3, gamma=0.1, s0=999, i0=1)
    assert v.ok and not v.flagged


@pytest.mark.parametrize("field,kwargs", [
    ("beta", dict(beta=0.0, gamma=0.1, s0=99, i0=1)),
    ("beta", dict(beta=-0.3, gamma=0.1, s0=99, i0=1)),
    ("gamma", dict(beta=0.3, gamma=0.0, s0=99, i0=1)),
    ("gamma", dict(beta=0.3, gamma=-0.1, s0=99, i0=1)),
])
def test_nonpositive_rates_are_rejected(field, kwargs):
    v = validate_sir_params(**kwargs)
    assert not v.ok
    assert any(field in e for e in v.errors)


def test_negative_compartment_is_rejected():
    assert not validate_sir_params(beta=0.3, gamma=0.1, s0=-1, i0=1).ok
    assert not validate_sir_params(beta=0.3, gamma=0.1, s0=99, i0=-1).ok
    assert not validate_sir_params(beta=0.3, gamma=0.1, s0=99, i0=1,
                                   r0_recovered=-5).ok


def test_empty_population_is_rejected():
    v = validate_sir_params(beta=0.3, gamma=0.1, s0=0, i0=0, r0_recovered=0)
    assert not v.ok
    assert any("population" in e for e in v.errors)


def test_zero_infected_is_flagged_not_rejected():
    v = validate_sir_params(beta=0.3, gamma=0.1, s0=1000, i0=0)
    assert v.ok
    assert v.flagged
    assert "I0" in v.flag_reason


def test_implausibly_high_r0_is_flagged():
    v = validate_sir_params(beta=100.0, gamma=0.1, s0=999, i0=1)
    assert v.ok
    assert v.flagged
    assert "R0" in v.flag_reason


def test_measles_scale_r0_is_not_flagged():
    # Measles R0 is genuinely 12-18; flagging it would be a false positive.
    v = validate_sir_params(beta=1.8, gamma=0.1, s0=999, i0=1)
    assert v.ok and not v.flagged


def test_r0_flag_boundary_is_exclusive():
    v = validate_sir_params(beta=R0_IMPLAUSIBLE_ABOVE * 0.1, gamma=0.1,
                            s0=999, i0=1)
    assert v.ok and not v.flagged


def test_ordinary_seir_params_accepted():
    v = validate_seir_params(beta=0.5, sigma=0.2, gamma=0.1, s0=990, e0=10,
                             i0=0)
    assert v.ok


def test_seir_outbreak_can_be_seeded_from_exposed_alone():
    # This is the case SIR's "I0 == 0 means nothing happens" rule gets wrong,
    # so SEIR must not inherit that flag.
    v = validate_seir_params(beta=0.5, sigma=0.2, gamma=0.1, s0=990, e0=10,
                             i0=0)
    assert v.ok
    assert not v.flagged


def test_seir_with_no_exposed_and_no_infected_is_flagged():
    v = validate_seir_params(beta=0.5, sigma=0.2, gamma=0.1, s0=1000, e0=0,
                             i0=0)
    assert v.ok
    assert v.flagged
    assert "E0" in v.flag_reason and "I0" in v.flag_reason


@pytest.mark.parametrize("sigma", [0.0, -0.2, float("nan")])
def test_bad_sigma_is_rejected(sigma):
    v = validate_seir_params(beta=0.5, sigma=sigma, gamma=0.1, s0=990, e0=10,
                             i0=0)
    assert not v.ok


def test_negative_exposed_is_rejected():
    v = validate_seir_params(beta=0.5, sigma=0.2, gamma=0.1, s0=990, e0=-1,
                             i0=1)
    assert not v.ok


def test_seir_inherits_sir_rate_validation():
    v = validate_seir_params(beta=-0.5, sigma=0.2, gamma=0.1, s0=990, e0=10,
                             i0=0)
    assert not v.ok
    assert any("beta" in e for e in v.errors)


