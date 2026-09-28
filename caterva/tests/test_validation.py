"""Parameter validation: physically impossible input vs implausible-but-real.

The distinction under test throughout: ``ok=False`` means the model cannot be
built, ``flagged=True`` means it builds and runs but a human should look at it.
Collapsing those two would either silently drop unusual-but-real models or
hard-fail on values BRENDA genuinely reports.
"""


import pytest

from caterva_engine import KM_PLAUSIBLE_MAX_MM, KM_PLAUSIBLE_MIN_MM, ModelBuildError, ParameterValidation, R0_IMPLAUSIBLE_ABOVE, validate_michaelis_menten_params


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


# ---------------------------------------------------------------------------
# SEIR
# ---------------------------------------------------------------------------


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
