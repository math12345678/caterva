"""Antimony <-> SBML translation, validation, and round-trip fidelity.

SBML is the interchange format Caterva hands to anything outside the browser,
so a round trip that quietly drops a parameter would corrupt exported models
without ever raising.
"""

import threading

import libsbml
import pytest

from caterva_engine import (
    GAMMA_PARAM,
    ModelBuildError,
    antimony_to_sbml,
    build_michaelis_menten_antimony,
    build_seir_antimony,
    build_sir_antimony,
    sbml_to_antimony,
    validate_sbml,
)


# ---------------------------------------------------------------------------
# Translation
# ---------------------------------------------------------------------------


def test_mm_model_translates_to_sbml():
    sbml = antimony_to_sbml(
        build_michaelis_menten_antimony(km=2.0, vmax=5.0, s0=10.0))
    assert "<sbml" in sbml
    assert "michaelis_menten" in sbml


def test_sbml_output_is_parseable_by_libsbml():
    sbml = antimony_to_sbml(
        build_michaelis_menten_antimony(km=2.0, vmax=5.0, s0=10.0))
    doc = libsbml.readSBMLFromString(sbml)
    assert doc.getModel() is not None


def test_generated_models_have_no_sbml_errors():
    for src in (
        build_michaelis_menten_antimony(km=2.0, vmax=5.0, s0=10.0),
        build_sir_antimony(beta=0.3, gamma=0.1, s0=999, i0=1),
        build_seir_antimony(beta=0.5, sigma=0.2, gamma=0.1, s0=990, e0=10,
                            i0=0),
    ):
        assert validate_sbml(antimony_to_sbml(src)) == []


def test_sbml_contains_the_species_and_parameters():
    sbml = antimony_to_sbml(build_sir_antimony(beta=0.3, gamma=0.1, s0=999,
                                               i0=1))
    model = libsbml.readSBMLFromString(sbml).getModel()
    species = {model.getSpecies(i).getId() for i in range(model.getNumSpecies())}
    params = {model.getParameter(i).getId()
              for i in range(model.getNumParameters())}
    assert {"S", "I", "R"} <= species
    assert {"beta", GAMMA_PARAM, "N"} <= params


def test_explicit_model_name_selects_the_right_module():
    src = build_michaelis_menten_antimony(km=1.0, vmax=1.0, s0=1.0,
                                          model_name="ldh")
    sbml = antimony_to_sbml(src, model_name="ldh")
    assert "ldh" in sbml


# ---------------------------------------------------------------------------
# Round trip
# ---------------------------------------------------------------------------


def test_round_trip_preserves_parameter_values():
    original = build_michaelis_menten_antimony(km=0.49, vmax=1.5, s0=12.0)
    recovered = sbml_to_antimony(antimony_to_sbml(original))
    assert "0.49" in recovered
    assert "1.5" in recovered
    assert "12" in recovered


def test_round_trip_preserves_the_rate_law():
    original = build_michaelis_menten_antimony(km=2.0, vmax=5.0, s0=10.0)
    recovered = sbml_to_antimony(antimony_to_sbml(original))
    condensed = recovered.replace(" ", "")
    assert "Vmax*S/(Km+S)" in condensed


def test_round_trip_preserves_sir_structure():
    original = build_sir_antimony(beta=0.3, gamma=0.1, s0=999, i0=1)
    recovered = sbml_to_antimony(antimony_to_sbml(original))
    condensed = recovered.replace(" ", "")
    assert "S->I" in condensed
    assert "I->R" in condensed


def test_double_round_trip_is_stable():
    # One translation can normalise formatting; a second must then be a no-op.
    once = sbml_to_antimony(antimony_to_sbml(
        build_michaelis_menten_antimony(km=2.0, vmax=5.0, s0=10.0)))
    twice = sbml_to_antimony(antimony_to_sbml(once))
    assert once.replace(" ", "") == twice.replace(" ", "")


def test_round_trip_preserves_small_km_magnitude():
    original = build_michaelis_menten_antimony(km=2.3e-07, vmax=1.0, s0=1.0)
    recovered = sbml_to_antimony(antimony_to_sbml(original))
    assert "2.3e-07" in recovered.replace("E-", "e-").replace("e-7", "e-07")


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


def test_syntactically_invalid_antimony_raises():
    with pytest.raises(ModelBuildError, match="failed to parse"):
        antimony_to_sbml("model broken\n  S -> ; (((\nend")


def test_error_message_includes_antimony_diagnostics():
    with pytest.raises(ModelBuildError) as exc:
        antimony_to_sbml("model broken\n  S -> ; (((\nend")
    assert "line" in str(exc.value).lower()


@pytest.mark.parametrize("bad", ["", "   ", "\n\n"])
def test_empty_antimony_raises(bad):
    with pytest.raises(ModelBuildError, match="empty"):
        antimony_to_sbml(bad)


@pytest.mark.parametrize("bad", [None, 42, b"model m end"])
def test_non_string_antimony_raises(bad):
    with pytest.raises(ModelBuildError):
        antimony_to_sbml(bad)


def test_unknown_module_name_raises():
    src = build_michaelis_menten_antimony(km=1.0, vmax=1.0, s0=1.0)
    with pytest.raises(ModelBuildError):
        antimony_to_sbml(src, model_name="no_such_module")


def test_invalid_sbml_raises_on_reverse_translation():
    with pytest.raises(ModelBuildError):
        sbml_to_antimony("<not-sbml>nope</not-sbml>")


@pytest.mark.parametrize("bad", ["", "   ", None])
def test_empty_sbml_raises(bad):
    with pytest.raises(ModelBuildError, match="empty"):
        sbml_to_antimony(bad)


# ---------------------------------------------------------------------------
# Global state safety
#
# libantimony keeps module-level state. Caterva's backend serves many students
# concurrently, so a leaked previous load would return one user's model to
# another.
# ---------------------------------------------------------------------------


def test_consecutive_translations_do_not_leak_state():
    first = antimony_to_sbml(
        build_michaelis_menten_antimony(km=1.0, vmax=1.0, s0=1.0,
                                        model_name="first"))
    second = antimony_to_sbml(
        build_sir_antimony(beta=0.3, gamma=0.1, s0=999, i0=1,
                           model_name="second"))
    assert "first" in first and "second" not in first
    assert "second" in second and "first" not in second


def test_repeated_translation_is_deterministic():
    src = build_michaelis_menten_antimony(km=2.0, vmax=5.0, s0=10.0)
    outputs = {antimony_to_sbml(src) for _ in range(5)}
    assert len(outputs) == 1


def test_concurrent_translation_returns_correct_models():
    results: dict[int, str] = {}
    errors: list[Exception] = []

    def worker(i: int) -> None:
        try:
            src = build_michaelis_menten_antimony(
                km=float(i + 1), vmax=1.0, s0=1.0, model_name=f"m{i}")
            results[i] = antimony_to_sbml(src, model_name=f"m{i}")
        except Exception as exc:  # pragma: no cover - only on real failure
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"concurrent translation raised: {errors}"
    assert len(results) == 8
    for i, sbml in results.items():
        assert f"m{i}" in sbml, "a thread received another thread's model"


# ---------------------------------------------------------------------------
# validate_sbml
# ---------------------------------------------------------------------------


def test_validate_sbml_reports_problems_for_broken_documents():
    problems = validate_sbml("<?xml version='1.0'?><sbml></sbml>")
    assert problems, "a malformed SBML document should not validate clean"


def test_validate_sbml_returns_a_list_of_strings():
    problems = validate_sbml(antimony_to_sbml(
        build_michaelis_menten_antimony(km=1.0, vmax=1.0, s0=1.0)))
    assert isinstance(problems, list)
    assert all(isinstance(p, str) for p in problems)
