"""Tests moved from caterva/tests/test_sbml.py on 2026-09-27 with their domains."""

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


def test_round_trip_preserves_sir_structure():
    original = build_sir_antimony(beta=0.3, gamma=0.1, s0=999, i0=1)
    recovered = sbml_to_antimony(antimony_to_sbml(original))
    condensed = recovered.replace(" ", "")
    assert "S->I" in condensed
    assert "I->R" in condensed


def test_consecutive_translations_do_not_leak_state():
    first = antimony_to_sbml(
        build_michaelis_menten_antimony(km=1.0, vmax=1.0, s0=1.0,
                                        model_name="first"))
    second = antimony_to_sbml(
        build_sir_antimony(beta=0.3, gamma=0.1, s0=999, i0=1,
                           model_name="second"))
    assert "first" in first and "second" not in first
    assert "second" in second and "first" not in second


