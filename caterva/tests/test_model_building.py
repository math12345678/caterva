"""Antimony source generation and model-name handling.

These tests care about what the generated text *means*, not just that a string
came back -- a model that parses but encodes the wrong rate law is the failure
mode that matters here.
"""

import pytest

from caterva_engine import GAMMA_PARAM, ModelBuildError, antimony_to_sbml, build_michaelis_menten_antimony


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


# ---------------------------------------------------------------------------
# SEIR
# ---------------------------------------------------------------------------


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
