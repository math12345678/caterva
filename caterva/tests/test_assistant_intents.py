"""Intent validation: the model proposes, the grammar and the finder dispose.

The proposals below are hand-written test inputs (what a model might return);
the shapes, the limits, the organism rules and the grammar they are checked
against are the engine's own.
"""
from __future__ import annotations

import pytest

from caterva.assistant import intents
from caterva.assistant.intents import IntentRejected, shape_catalogue, validate_describe, winning_rule
from caterva.compose.grammar import RULES, UnrecognisedShape, recognise

WORDS = "an enzyme turning pyruvate into lactate, slowed by gossypol in human cells"


def test_the_catalogue_is_the_grammars_own_thirty_six_shapes():
    shapes = shape_catalogue()
    assert [s.name for s in shapes] == sorted(r.name for r in RULES)
    assert len(shapes) == 36
    assert {s.name for s in shapes if s.needs_stages} == {"phosphorylation_cascade", "enzyme_cascade",
                                                          "metabolic_pathway"}


@pytest.mark.parametrize("shape", shape_catalogue(), ids=lambda s: s.name)
def test_every_shape_can_be_proposed_and_is_read_back_as_itself(shape):
    """The description built here is recognised as the proposed shape, for all 36 (and each variant)."""
    variants = shape.variants or (None,)
    for variant in variants:
        intent = validate_describe({"shape": shape.name, "stages": 3 if shape.needs_stages else None,
                                    "variant": variant}, WORDS, set())
        assert winning_rule(intent.description) == shape.name
        assert intent.request["description"] == intent.description
        recognise(intent.description)  # the engine does not refuse it


def test_the_variant_table_is_checked_against_the_grammar():
    for shape, variants in intents.VARIANTS.items():
        for variant, words in variants.items():
            assert winning_rule(words) == shape, (shape, variant)


def test_a_shape_that_is_not_in_the_library_is_rejected():
    for name in ("glycolysis", "Michaelis_Menten", "michaelis_menten ", "", None, 7, ["inhibition"]):
        with pytest.raises(IntentRejected):
            validate_describe({"shape": name}, WORDS, set())


def test_extra_fields_are_rejected():
    with pytest.raises(IntentRejected, match="not part of an intent"):
        validate_describe({"shape": "michaelis_menten", "km": 0.5}, WORDS, set())
    with pytest.raises(IntentRejected, match="not part of an intent"):
        validate_describe({"shape": "michaelis_menten", "description": "anything at all"}, WORDS, set())


def test_a_reply_that_is_not_an_object_is_rejected():
    for bad in ("michaelis_menten", ["michaelis_menten"], 3, None):
        with pytest.raises(IntentRejected):
            validate_describe(bad, WORDS, set())


def test_steps_are_a_whole_number_within_the_grammars_limit():
    ok = validate_describe({"shape": "enzyme_cascade", "stages": intents.max_stages()}, WORDS, set())
    assert str(intents.max_stages()) in ok.description
    for stages in (0, -1, intents.max_stages() + 1, 2.5, "3", True, None):
        with pytest.raises(IntentRejected):
            validate_describe({"shape": "enzyme_cascade", "stages": stages}, WORDS, set())
    with pytest.raises(IntentRejected, match="does not take a number of steps"):
        validate_describe({"shape": "michaelis_menten", "stages": 3}, WORDS, set())


def test_a_shape_the_engine_refuses_to_choose_for_needs_its_variant_named():
    with pytest.raises(IntentRejected, match="variants"):
        validate_describe({"shape": "bi_substrate"}, WORDS, set())
    with pytest.raises(IntentRejected, match="variants"):
        validate_describe({"shape": "inhibition"}, WORDS, set())   # the grammar would silently pick competitive
    with pytest.raises(IntentRejected, match="variants"):
        validate_describe({"shape": "inhibition", "variant": "irreversible"}, WORDS, set())
    with pytest.raises(IntentRejected, match="no variants"):
        validate_describe({"shape": "michaelis_menten", "variant": "competitive"}, WORDS, set())
    intent = validate_describe({"shape": "inhibition", "variant": "uncompetitive"}, WORDS, set())
    assert intent.reading == "uncompetitive inhibition"


def test_an_ec_number_the_finder_did_not_list_is_rejected():
    candidates = {"1.1.1.27", "1.1.1.28"}
    ok = validate_describe({"shape": "michaelis_menten", "subject_ec": "1.1.1.27"}, WORDS, candidates)
    assert ok.request["subject"] == "1.1.1.27"
    for ec in ("1.1.1.1", "2.7.1.1", "1.1.1", "EC 1.1.1.27", "1.1.1.27; rm -rf", "99.99.99.99", 27):
        with pytest.raises(IntentRejected):
            validate_describe({"shape": "michaelis_menten", "subject_ec": ec}, WORDS, candidates)
    with pytest.raises(IntentRejected, match="not one the enzyme finder listed"):
        validate_describe({"shape": "michaelis_menten", "subject_ec": "1.1.1.27"}, WORDS, set())


def test_a_name_must_be_in_the_persons_own_words():
    ok = validate_describe({"shape": "inhibition", "variant": "competitive", "substrate": "pyruvate",
                            "inhibitor": "gossypol", "organism": "human"}, WORDS, set())
    assert ok.request["substrate"] == "pyruvate" and ok.request["inhibitor"] == "gossypol"
    assert ok.request["organism"] == "human" and ok.organism_note
    for field, value in (("substrate", "glucose"), ("inhibitor", "aspirin"), ("organism", "mouse")):
        with pytest.raises(IntentRejected, match="not in your own words"):
            validate_describe({"shape": "inhibition", "variant": "competitive", field: value}, WORDS, set())


def test_a_name_must_be_a_plain_name():
    words = "x; $(reboot) and --flag and <b>bold</b>"
    for value in ("x; $(reboot)", "--flag and", "<b>bold</b>", "a" * 90, "line\nbreak"):
        with pytest.raises(IntentRejected):
            validate_describe({"shape": "inhibition", "variant": "competitive", "substrate": value}, words, set())


def test_every_problem_is_reported_not_just_the_first():
    with pytest.raises(IntentRejected) as caught:
        validate_describe({"shape": "enzyme_cascade", "stages": 99, "substrate": "glucose", "subject_ec": "9.9.9.9",
                           "organism": "dragon"}, WORDS, set())
    assert len(caught.value.reasons) == 4


def test_the_description_sent_to_the_engine_is_built_here_never_taken_from_the_model():
    intent = validate_describe({"shape": "michaelis_menten"}, WORDS, set())
    assert intent.description == "one enzyme turning one substrate into one product"
    assert set(intent.request) == {"description"}
    with pytest.raises(UnrecognisedShape):
        recognise("glycolysis")   # and the engine's own refusal still stands for what is not a shape
