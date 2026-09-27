"""Antimony source generation and model-name handling.

These tests care about what the generated text *means*, not just that a string
came back -- a model that parses but encodes the wrong rate law is the failure
mode that matters here.
"""

import pytest

from caterva_engine import (
    GAMMA_PARAM,
    ModelBuildError,
    antimony_to_sbml,
    build_michaelis_menten_antimony,
    build_seir_antimony,
    build_sir_antimony,
)


# ---------------------------------------------------------------------------
# Michaelis-Menten
# ---------------------------------------------------------------------------


def test_mm_model_has_expected_structure():
    src = build_michaelis_menten_antimony(km=2.0, vmax=5.0, s0=10.0)
    assert src.startswith("model michaelis_menten")
    assert src.rstrip().endswith("end")
    assert "S -> P" in src
    assert "Vmax * S / (Km + S)" in src, "rate law must be the MM equation"


def test_mm_model_encodes_the_given_values():
    src = build_michaelis_menten_antimony(km=0.49, vmax=1.5, s0=12.0)
    assert "Km = 0.49" in src
    assert "Vmax = 1.5" in src
    assert "S = 12.0" in src
    assert "P = 0" in src, "product must start empty"


def test_mm_model_does_not_lose_precision_on_small_km():
    # 2.3e-7 mM is within the real BRENDA range; formatting it as 0.0 would
    # silently turn a valid model into a divide-by-near-zero.
    src = build_michaelis_menten_antimony(km=2.3e-07, vmax=1.0, s0=1.0)
    assert "2.3e-07" in src


def test_mm_model_accepts_integers():
    src = build_michaelis_menten_antimony(km=2, vmax=5, s0=10)
    assert "Km = 2.0" in src


def test_mm_build_validates_by_default():
    with pytest.raises(ModelBuildError):
        build_michaelis_menten_antimony(km=-1.0, vmax=1.0, s0=1.0)


def test_mm_build_can_skip_validation():
    # The simulate_* helpers validate once and then build with validate=False.
    # This test verifies that the validate=False parameter skips validation
    # and accepts out-of-range values (like negative km).
    src = build_michaelis_menten_antimony(km=-1.0, vmax=1.0, s0=1.0,
                                          validate=False)
    assert "Km = -1.0" in src


def test_mm_flagged_values_still_build():
    src = build_michaelis_menten_antimony(km=1e9, vmax=1.0, s0=1.0)
    assert "Km = 1000000000.0" in src


# ---------------------------------------------------------------------------
# SIR
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# SEIR
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Model names
# ---------------------------------------------------------------------------


def test_custom_model_name_is_used():
    src = build_michaelis_menten_antimony(km=1.0, vmax=1.0, s0=1.0,
                                          model_name="ldh_lactate")
    assert src.startswith("model ldh_lactate")


@pytest.mark.parametrize("name", ["model", "end", "species", "function",
                                  "compartment"])
def test_reserved_antimony_keywords_are_rejected(name):
    with pytest.raises(ModelBuildError, match="reserved"):
        build_michaelis_menten_antimony(km=1.0, vmax=1.0, s0=1.0,
                                        model_name=name)


@pytest.mark.parametrize("name", ["9lives", "has space", "has-dash",
                                  "semi;colon", "brace}", ""])
def test_invalid_model_names_are_rejected(name):
    with pytest.raises(ModelBuildError):
        build_michaelis_menten_antimony(km=1.0, vmax=1.0, s0=1.0,
                                        model_name=name)


def test_model_name_injection_is_blocked():
    # Without a name check, this would terminate the model early and append
    # an attacker-controlled second model.
    with pytest.raises(ModelBuildError):
        build_michaelis_menten_antimony(
            km=1.0, vmax=1.0, s0=1.0,
            model_name="m\nend\nmodel evil\n  X -> Y; 1\nend")


@pytest.mark.parametrize("name", ["_private", "m1", "Model2", "a_b_c9"])
def test_valid_model_names_are_accepted(name):
    src = build_michaelis_menten_antimony(km=1.0, vmax=1.0, s0=1.0,
                                          model_name=name)
    assert src.startswith(f"model {name}")


@pytest.mark.parametrize("name", [None, 5, ["m"]])
def test_non_string_model_names_are_rejected(name):
    with pytest.raises(ModelBuildError):
        build_michaelis_menten_antimony(km=1.0, vmax=1.0, s0=1.0,
                                        model_name=name)
