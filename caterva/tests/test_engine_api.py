"""SimulationResult accessors, steady state, parameter scanning, error paths."""

import numpy as np
import pytest

from caterva_engine import ParameterValidation, SimulationError, SimulationResult, antimony_to_sbml, build_michaelis_menten_antimony, parameter_scan, simulate_michaelis_menten, simulate_sbml, steady_state, validate_michaelis_menten_params


@pytest.fixture
def mm_sbml():
    return antimony_to_sbml(
        build_michaelis_menten_antimony(km=2.0, vmax=5.0, s0=10.0))


# ---------------------------------------------------------------------------
# SimulationResult
# ---------------------------------------------------------------------------


def test_column_lookup_tolerates_concentration_brackets():
    # roadrunner labels species columns "[S]"; callers should not have to know.
    res = simulate_michaelis_menten(km=2.0, vmax=5.0, s0=10.0, points=5)
    assert res.column("S") == res.column("[S]")


def test_unknown_column_raises_keyerror():
    res = simulate_michaelis_menten(km=2.0, vmax=5.0, s0=10.0, points=5)
    with pytest.raises(KeyError):
        res.column("Q")


def test_time_and_len_accessors():
    res = simulate_michaelis_menten(km=2.0, vmax=5.0, s0=10.0, points=9)
    assert len(res) == 9
    assert len(res.time) == 9


def test_final_returns_the_last_value():
    res = simulate_michaelis_menten(km=2.0, vmax=5.0, s0=10.0, points=9)
    assert res.final("S") == res.column("S")[-1]


def test_result_carries_model_name_and_validation():
    res = simulate_michaelis_menten(km=2.0, vmax=5.0, s0=10.0, points=5)
    assert res.model_name == "michaelis_menten"
    assert isinstance(res.validation, ParameterValidation)


def test_flagged_property_mirrors_validation():
    clean = SimulationResult([], [], "m", ParameterValidation())
    dirty = SimulationResult([], [], "m",
                             ParameterValidation(flagged=True,
                                                 flag_reason="why"))
    assert not clean.flagged
    assert dirty.flagged


def test_data_is_plain_python_floats():
    # The API boundary should hand back JSON-serialisable values, not numpy
    # scalars that break json.dumps downstream.
    res = simulate_michaelis_menten(km=2.0, vmax=5.0, s0=10.0, points=5)
    assert all(type(v) is float for row in res.data for v in row)


# ---------------------------------------------------------------------------
# simulate_sbml
# ---------------------------------------------------------------------------


def test_simulate_sbml_runs_a_raw_document(mm_sbml):
    res = simulate_sbml(mm_sbml, end=5.0, points=11)
    assert len(res) == 11
    assert "time" in res.colnames


def test_selections_restrict_the_returned_columns(mm_sbml):
    res = simulate_sbml(mm_sbml, end=5.0, points=6, selections=["time", "S"])
    assert res.colnames == ["time", "S"]


def test_invalid_selection_raises(mm_sbml):
    with pytest.raises(SimulationError):
        simulate_sbml(mm_sbml, selections=["time", "NoSuchSpecies"])


def test_unloadable_document_raises_simulation_error():
    with pytest.raises(SimulationError, match="could not load"):
        simulate_sbml("<not-sbml/>")


def test_simulate_sbml_defaults_to_clean_validation(mm_sbml):
    res = simulate_sbml(mm_sbml, points=3)
    assert not res.flagged


# ---------------------------------------------------------------------------
# steady_state
# ---------------------------------------------------------------------------


def test_steady_state_of_an_irreversible_reaction_exhausts_substrate(mm_sbml):
    state = steady_state(mm_sbml)
    assert set(state) == {"S", "P"}
    assert state["S"] == pytest.approx(0.0, abs=1e-6)


def test_steady_state_conserves_total_mass(mm_sbml):
    state = steady_state(mm_sbml)
    assert state["S"] + state["P"] == pytest.approx(10.0, rel=1e-4)


def test_steady_state_returns_plain_floats(mm_sbml):
    state = steady_state(mm_sbml)
    assert all(type(v) is float for v in state.values())


def test_steady_state_on_a_broken_document_raises():
    with pytest.raises(SimulationError):
        steady_state("<not-sbml/>")


# ---------------------------------------------------------------------------
# parameter_scan
# ---------------------------------------------------------------------------


def test_scan_returns_one_result_per_value(mm_sbml):
    results = parameter_scan(mm_sbml, "Vmax", [1.0, 2.0, 5.0], end=2.0,
                             points=6)
    assert len(results) == 3
    assert all(len(r) == 6 for r in results)


def test_scan_actually_varies_the_parameter(mm_sbml):
    slow, fast = parameter_scan(mm_sbml, "Vmax", [0.5, 20.0], end=2.0,
                                points=6)
    assert fast.final("S") < slow.final("S")


def test_scan_over_km_changes_the_outcome(mm_sbml):
    tight, loose = parameter_scan(mm_sbml, "Km", [0.01, 500.0], end=1.0,
                                  points=6)
    assert loose.final("S") > tight.final("S")


def test_scan_resets_state_between_runs(mm_sbml):
    # Without an explicit reset, run N would start from run N-1's end state.
    results = parameter_scan(mm_sbml, "Vmax", [5.0, 5.0, 5.0], end=2.0,
                             points=6)
    first = results[0].column("S")
    for r in results[1:]:
        np.testing.assert_allclose(r.column("S"), first, rtol=1e-9)


def test_scan_labels_each_result_with_its_value(mm_sbml):
    results = parameter_scan(mm_sbml, "Vmax", [1.0, 2.0], end=1.0, points=3)
    assert results[0].model_name == "Vmax=1.0"
    assert results[1].model_name == "Vmax=2.0"


def test_scan_over_an_unknown_parameter_raises(mm_sbml):
    with pytest.raises(SimulationError, match="not a global parameter"):
        parameter_scan(mm_sbml, "NoSuchParam", [1.0])


def test_scan_error_lists_the_available_parameters(mm_sbml):
    with pytest.raises(SimulationError) as exc:
        parameter_scan(mm_sbml, "nope", [1.0])
    assert "Vmax" in str(exc.value) and "Km" in str(exc.value)


def test_scan_with_no_values_raises(mm_sbml):
    with pytest.raises(SimulationError, match="at least one value"):
        parameter_scan(mm_sbml, "Vmax", [])


def test_scan_accepts_a_generator(mm_sbml):
    results = parameter_scan(mm_sbml, "Vmax", (float(v) for v in (1, 2)),
                             end=1.0, points=3)
    assert len(results) == 2


def test_scan_supports_selections(mm_sbml):
    results = parameter_scan(mm_sbml, "Vmax", [1.0], end=1.0, points=3,
                             selections=["time", "S"])
    assert results[0].colnames == ["time", "S"]


# ---------------------------------------------------------------------------
# Parameter validation consistency
# ---------------------------------------------------------------------------


def test_michaelis_menten_negative_km():
    validation = validate_michaelis_menten_params(km=-1.0, vmax=5.0, s0=10.0)
    assert not validation.ok
    assert "Km" in validation.errors[0]


def test_michaelis_menten_zero_vmax():
    validation = validate_michaelis_menten_params(km=2.0, vmax=0.0, s0=10.0)
    assert not validation.ok
    assert "Vmax" in validation.errors[0]


def test_michaelis_menten_below_plausible_km():
    validation = validate_michaelis_menten_params(km=1e-8, vmax=5.0, s0=10.0)
    assert validation.ok
    assert validation.flagged
    assert "below the plausible lower bound" in validation.flag_reason


def test_michaelis_menten_above_plausible_km():
    validation = validate_michaelis_menten_params(km=1e4, vmax=5.0, s0=10.0)
    assert validation.ok
    assert validation.flagged
    assert "above the plausible upper bound" in validation.flag_reason


