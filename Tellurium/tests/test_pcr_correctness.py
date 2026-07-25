"""PCR amplification: exact closed-form growth, validation, and plateau.

Unlike the ODE domains, PCR is a discrete-cycle recurrence, so "correctness"
here means matching the exact closed form by construction, not agreeing with
a numerical solver to some tolerance. The tests are exact-equality checks
(within float rounding), not tolerance-band checks.
"""

import math

import pytest
from hypothesis import given, settings, strategies as st

from tellurium_engine import (
    ModelBuildError,
    PCR_MAX_EFFICIENCY,
    PCR_MIN_EFFICIENCY,
    PCR_PLAUSIBLE_LOW_EFFICIENCY,
    simulate_pcr,
    validate_pcr_params,
)


# ---------------------------------------------------------------------------
# Exact closed-form growth
# ---------------------------------------------------------------------------


def test_matches_exact_exponential_formula_at_every_cycle():
    n0, efficiency, cycles = 5.0, 0.85, 20
    result = simulate_pcr(n0=n0, efficiency=efficiency, cycles=cycles)
    for cycle, copies in zip(result.column("cycle"), result.column("copies")):
        expected = n0 * (1.0 + efficiency) ** cycle
        assert copies == pytest.approx(expected, rel=1e-12)


def test_perfect_efficiency_exactly_doubles_each_cycle():
    n0, cycles = 10.0, 15
    result = simulate_pcr(n0=n0, efficiency=1.0, cycles=cycles)
    for cycle, copies in zip(result.column("cycle"), result.column("copies")):
        assert copies == pytest.approx(n0 * (2.0 ** cycle), rel=1e-12)


def test_zero_efficiency_never_amplifies():
    n0 = 42.0
    result = simulate_pcr(n0=n0, efficiency=0.0, cycles=30)
    for copies in result.column("copies"):
        assert copies == pytest.approx(n0)


def test_first_cycle_starts_at_n0():
    result = simulate_pcr(n0=7.0, efficiency=0.9, cycles=10)
    assert result.column("cycle")[0] == 0.0
    assert result.column("copies")[0] == pytest.approx(7.0)


def test_output_has_one_row_per_cycle_plus_the_starting_point():
    cycles = 25
    result = simulate_pcr(n0=1.0, efficiency=0.9, cycles=cycles)
    assert len(result.column("cycle")) == cycles + 1


# ---------------------------------------------------------------------------
# Validation: hard rejections
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad_n0", [0.0, -1.0, -100.0, math.nan, math.inf])
def test_invalid_n0_is_rejected(bad_n0):
    v = validate_pcr_params(n0=bad_n0, efficiency=0.9, cycles=10)
    assert not v.ok
    with pytest.raises(ModelBuildError):
        simulate_pcr(n0=bad_n0, efficiency=0.9, cycles=10)


@pytest.mark.parametrize("bad_efficiency", [-0.1, -1.0, 1.1, 2.0, math.nan, math.inf])
def test_efficiency_outside_zero_to_one_is_rejected(bad_efficiency):
    v = validate_pcr_params(n0=10.0, efficiency=bad_efficiency, cycles=10)
    assert not v.ok
    with pytest.raises(ModelBuildError):
        simulate_pcr(n0=10.0, efficiency=bad_efficiency, cycles=10)


@pytest.mark.parametrize("bad_cycles", [0, -5, 61, 100])
def test_cycles_out_of_range_is_rejected(bad_cycles):
    v = validate_pcr_params(n0=10.0, efficiency=0.9, cycles=bad_cycles)
    assert not v.ok


def test_non_integer_cycles_is_rejected():
    v = validate_pcr_params(n0=10.0, efficiency=0.9, cycles=10.5)  # type: ignore[arg-type]
    assert not v.ok


def test_boolean_efficiency_is_rejected_not_silently_coerced():
    # bool is a subclass of int in Python; True/False must not silently pass
    # as 1.0/0.0 efficiency.
    v = validate_pcr_params(n0=10.0, efficiency=True, cycles=10)  # type: ignore[arg-type]
    assert not v.ok


def test_efficiency_of_exactly_one_is_the_boundary_and_is_valid():
    v = validate_pcr_params(n0=10.0, efficiency=PCR_MAX_EFFICIENCY, cycles=10)
    assert v.ok


def test_efficiency_of_exactly_zero_is_the_boundary_and_is_valid():
    v = validate_pcr_params(n0=10.0, efficiency=PCR_MIN_EFFICIENCY, cycles=10)
    assert v.ok


# ---------------------------------------------------------------------------
# Flagging: real but poor reactions
# ---------------------------------------------------------------------------


def test_low_efficiency_is_flagged_not_rejected():
    low = PCR_PLAUSIBLE_LOW_EFFICIENCY - 0.1
    v = validate_pcr_params(n0=10.0, efficiency=low, cycles=10)
    assert v.ok
    assert v.flagged
    assert v.flag_reason

    # A flagged-but-valid reaction must still simulate and carry the flag
    # through to the result -- this is the same contract test_brenda_
    # integration.py checks for the literature layer.
    result = simulate_pcr(n0=10.0, efficiency=low, cycles=10)
    assert result.flagged


def test_high_efficiency_is_not_flagged():
    v = validate_pcr_params(n0=10.0, efficiency=0.95, cycles=10)
    assert v.ok
    assert not v.flagged


# ---------------------------------------------------------------------------
# Plateau capacity (discrete logistic growth)
# ---------------------------------------------------------------------------


def test_plateau_capacity_is_never_exceeded():
    capacity = 1000.0
    result = simulate_pcr(n0=5.0, efficiency=0.9, cycles=40, plateau_capacity=capacity)
    for copies in result.column("copies"):
        assert copies <= capacity + 1e-9


def test_plateau_growth_is_monotonically_non_decreasing():
    result = simulate_pcr(n0=5.0, efficiency=0.9, cycles=40, plateau_capacity=1000.0)
    copies = result.column("copies")
    for earlier, later in zip(copies, copies[1:]):
        assert later >= earlier - 1e-9


def test_plateau_capacity_below_n0_is_rejected():
    with pytest.raises(ModelBuildError):
        simulate_pcr(n0=100.0, efficiency=0.9, cycles=10, plateau_capacity=50.0)


def test_high_cycle_count_approaches_capacity():
    capacity = 500.0
    result = simulate_pcr(n0=2.0, efficiency=0.95, cycles=60 - 1, plateau_capacity=capacity)
    # After enough cycles at reasonable efficiency, the reaction should be
    # meaningfully saturated, not still in the exponential phase.
    assert result.column("copies")[-1] > capacity * 0.5


# ---------------------------------------------------------------------------
# Property-based: holds across the whole valid input space
# ---------------------------------------------------------------------------


@given(
    n0=st.floats(min_value=1e-3, max_value=1e6, allow_nan=False, allow_infinity=False),
    efficiency=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    cycles=st.integers(min_value=1, max_value=60),
)
@settings(max_examples=200)
def test_unbounded_growth_always_matches_closed_form(n0, efficiency, cycles):
    result = simulate_pcr(n0=n0, efficiency=efficiency, cycles=cycles)
    expected_final = n0 * (1.0 + efficiency) ** cycles
    assert result.column("copies")[-1] == pytest.approx(expected_final, rel=1e-9)


@given(
    n0=st.floats(min_value=1e-3, max_value=1e6, allow_nan=False, allow_infinity=False),
    efficiency=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    cycles=st.integers(min_value=1, max_value=60),
)
@settings(max_examples=200)
def test_copies_never_decrease_across_cycles(n0, efficiency, cycles):
    result = simulate_pcr(n0=n0, efficiency=efficiency, cycles=cycles)
    copies = result.column("copies")
    for earlier, later in zip(copies, copies[1:]):
        assert later >= earlier - 1e-6
