"""Parameter validation: physically impossible input vs implausible-but-real.

The distinction under test throughout: ``ok=False`` means the model cannot be
built, ``flagged=True`` means it builds and runs but a human should look at it.
Collapsing those two would either silently drop unusual-but-real models or
hard-fail on values BRENDA genuinely reports.
"""


import pytest

from caterva_engine import (
    KM_PLAUSIBLE_MAX_MM,
    KM_PLAUSIBLE_MIN_MM,
    ModelBuildError,
    ParameterValidation,
    R0_IMPLAUSIBLE_ABOVE,
    validate_michaelis_menten_params,
    validate_seir_params,
    validate_sir_params,
)


# ---------------------------------------------------------------------------
# Michaelis-Menten
# ---------------------------------------------------------------------------


def test_ordinary_kinetics_params_are_accepted_unflagged():
    v = validate_michaelis_menten_params(km=0.49, vmax=5.0, s0=10.0)
    assert v.ok
    assert not v.flagged
    assert v.flag_reason is None
    assert v.errors == []


def test_hexokinase_real_km_is_accepted():
    # 0.49 mM is the real measured glucose Km for human HKDC1 (PMID 41187334),
    # verified live in an earlier session. It must pass unflagged.
    v = validate_michaelis_menten_params(km=0.49, vmax=1.0, s0=1.0)
    assert v.ok and not v.flagged


def test_zero_substrate_is_valid():
    # A model that starts with no substrate is inert but perfectly well posed.
    v = validate_michaelis_menten_params(km=1.0, vmax=1.0, s0=0.0)
    assert v.ok
    assert not v.flagged


@pytest.mark.parametrize("km", [0.0, -1.0, -1e-12])
def test_nonpositive_km_is_rejected(km):
    v = validate_michaelis_menten_params(km=km, vmax=1.0, s0=1.0)
    assert not v.ok
    assert any("Km" in e for e in v.errors)


@pytest.mark.parametrize("vmax", [0.0, -3.0])
def test_nonpositive_vmax_is_rejected(vmax):
    v = validate_michaelis_menten_params(km=1.0, vmax=vmax, s0=1.0)
    assert not v.ok
    assert any("Vmax" in e for e in v.errors)


def test_negative_substrate_is_rejected():
    v = validate_michaelis_menten_params(km=1.0, vmax=1.0, s0=-5.0)
    assert not v.ok
    assert any("S0" in e for e in v.errors)


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_nonfinite_values_are_rejected(bad):
    assert not validate_michaelis_menten_params(km=bad, vmax=1.0, s0=1.0).ok
    assert not validate_michaelis_menten_params(km=1.0, vmax=bad, s0=1.0).ok
    assert not validate_michaelis_menten_params(km=1.0, vmax=1.0, s0=bad).ok


@pytest.mark.parametrize("bad", ["1.0", None, [1.0], {"km": 1}])
def test_non_numeric_types_are_rejected(bad):
    v = validate_michaelis_menten_params(km=bad, vmax=1.0, s0=1.0)
    assert not v.ok
    assert any("must be a number" in e for e in v.errors)


def test_bool_is_not_accepted_as_a_number():
    # bool is a subclass of int in Python; True would silently become Km=1.0.
    v = validate_michaelis_menten_params(km=True, vmax=1.0, s0=1.0)
    assert not v.ok


def test_km_below_plausible_bound_is_flagged_not_rejected():
    v = validate_michaelis_menten_params(km=KM_PLAUSIBLE_MIN_MM / 10,
                                         vmax=1.0, s0=1.0)
    assert v.ok, "an implausible value must still be simulable"
    assert v.flagged
    assert "below" in v.flag_reason


def test_km_above_plausible_bound_is_flagged_not_rejected():
    v = validate_michaelis_menten_params(km=KM_PLAUSIBLE_MAX_MM * 10,
                                         vmax=1.0, s0=1.0)
    assert v.ok
    assert v.flagged
    assert "above" in v.flag_reason


@pytest.mark.parametrize("km", [KM_PLAUSIBLE_MIN_MM, KM_PLAUSIBLE_MAX_MM])
def test_plausibility_bounds_are_inclusive(km):
    # Exactly on the boundary must not flag -- off-by-one here would flag a
    # large slice of real BRENDA data.
    v = validate_michaelis_menten_params(km=km, vmax=1.0, s0=1.0)
    assert v.ok and not v.flagged


def test_raise_if_invalid_raises_only_when_invalid():
    validate_michaelis_menten_params(km=1.0, vmax=1.0, s0=1.0).raise_if_invalid()
    with pytest.raises(ModelBuildError):
        validate_michaelis_menten_params(km=-1.0, vmax=1.0,
                                         s0=1.0).raise_if_invalid()


def test_flagged_model_does_not_raise():
    # Flagged is not invalid: raise_if_invalid must stay silent.
    validate_michaelis_menten_params(km=KM_PLAUSIBLE_MAX_MM * 100, vmax=1.0,
                                     s0=1.0).raise_if_invalid()


def test_all_errors_are_collected_not_just_the_first():
    v = validate_michaelis_menten_params(km=-1.0, vmax=-1.0, s0=-1.0)
    assert not v.ok
    assert len(v.errors) == 3
    # Check that we get error messages for all three parameters
    assert any("Km" in error for error in v.errors)
    assert any("Vmax" in error for error in v.errors)
    assert any("S0" in error for error in v.errors)


# ---------------------------------------------------------------------------
# SIR
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# SEIR
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# ParameterValidation object itself
# ---------------------------------------------------------------------------


def test_default_validation_is_clean():
    v = ParameterValidation()
    assert v.ok and not v.flagged and v.flag_reason is None and v.errors == []


def test_error_lists_are_not_shared_between_instances():
    a, b = ParameterValidation(), ParameterValidation()
    a.errors.append("boom")
    assert b.errors == [], "mutable default leaked between instances"
