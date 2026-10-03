"""One policy turns a name into an EC number; these are its branches.

WHY THIS EXISTS
---------------
`caterva.enzymes.policy.resolve_enzyme_name` is the function every command
that takes an enzyme name calls (test_every_name_reaches_one_policy in
Tests/ proves they do). Its branches are the product: the nomenclature
answers first and UniProt is never asked when it can; a tie is refused with
every candidate named and the flag to re-run with; a typo is a suggestion;
a transferred number says it was replaced; UniProt's protein-name search is
the fallback for a name the nomenclature does not hold.

The UniProt step is an injected function here, as it is everywhere in this
repository's tests of refusals: a test that needed the network to check a
refusal's wording would fail for reasons unrelated to the wording. Every
enzyme name, number, candidate and message is the real index's.
"""
from __future__ import annotations

import pytest

from caterva.enzymes.policy import (
    AMBIGUOUS, DELETED_OR_UNKNOWN, LOOKUP_FAILED, NONE_FOUND, SUGGESTIONS,
    NameNotResolved, literature_uniprot_lookup, resolve_enzyme_name,
)


class Uniprot:
    """Stands in for the UniProt call and records that it was made."""

    def __init__(self, *answer):
        self.answer = list(answer)
        self.calls = []

    def __call__(self, name):
        self.calls.append(name)
        return list(self.answer)


def test_the_nomenclature_answers_first_and_uniprot_is_never_asked():
    uniprot = Uniprot("9.9.9.9")
    resolution = resolve_enzyme_name("pyruvate kinase", "human", uniprot=uniprot)
    assert (resolution.ec, resolution.source, resolution.name) == ("2.7.1.40", "nomenclature", "pyruvate kinase")
    assert uniprot.calls == []


def test_what_the_name_was_read_as_is_a_sentence_for_the_report():
    resolution = resolve_enzyme_name("pyruvate kinase", "human")
    assert resolution.notes("pyruvate kinase") == [
        "Read 'pyruvate kinase' as EC 2.7.1.40 (pyruvate kinase): accepted name matches exactly."]


def test_an_ec_number_given_as_such_needs_no_sentence():
    resolution = resolve_enzyme_name("1.1.1.27", "human")
    assert resolution.ec == "1.1.1.27" and resolution.notes("1.1.1.27") == []


def test_a_transferred_number_is_replaced_and_the_sentence_says_so():
    resolution = resolve_enzyme_name("1.1.1.32")
    assert resolution.ec == "1.1.1.1"
    (sentence,) = resolution.notes("1.1.1.32")
    assert "was transferred" in sentence and "EC 1.1.1.1 (alcohol dehydrogenase)" in sentence


def test_an_enzyme_with_no_protein_from_the_organism_adds_a_caution_to_the_sentence():
    sentences = resolve_enzyme_name("glucokinase", "human").notes("glucokinase")
    assert sentences[0].startswith("Read 'glucokinase' as EC 2.7.1.2 (glucokinase)")
    assert any("lists no human protein" in s for s in sentences)


def test_a_tie_refuses_names_every_candidate_and_ends_with_the_flag():
    with pytest.raises(NameNotResolved) as raised:
        resolve_enzyme_name("lactate dehydrogenase", "human")
    error = raised.value
    assert error.kind == AMBIGUOUS
    assert error.candidates[:2] == ["1.1.1.27", "1.1.1.28"]
    assert [n["name"] for n in error.named[:2]] == ["L-lactate dehydrogenase", "D-lactate dehydrogenase"]
    assert error.named[0]["label"].startswith("EC 1.1.1.27 L-lactate dehydrogenase (human: ")
    message = str(error)
    assert "EC 1.1.1.27 L-lactate dehydrogenase (human: " in message
    assert "recommended" in message and message.endswith("--subject 1.1.1.27")


def test_a_caller_with_another_spelling_for_the_flag_ends_with_its_own():
    with pytest.raises(NameNotResolved) as raised:
        resolve_enzyme_name("lactate dehydrogenase", None, rerun="--ec {ec}")
    assert str(raised.value).endswith("for example --ec 1.1.1.27")


def test_a_refusal_lists_the_tied_enzymes_before_the_weaker_ones():
    with pytest.raises(NameNotResolved) as raised:
        resolve_enzyme_name("lactate dehydrogenase", "human")
    lines = str(raised.value).splitlines()
    weaker = lines.index("Weaker matches:")
    assert [l.strip().split()[1] for l in lines[1:weaker]] == ["1.1.1.27", "1.1.1.28"]
    assert any("D-lactate dehydrogenase (quinone)" in l for l in lines[weaker:])


def test_an_ec_number_the_nomenclature_does_not_hold_is_refused_unless_the_caller_allows_it():
    with pytest.raises(NameNotResolved) as raised:
        resolve_enzyme_name("9.9.9.9")
    assert raised.value.kind == DELETED_OR_UNKNOWN
    allowed = resolve_enzyme_name("9.9.9.9", allow_unlisted_ec=True)
    assert allowed.ec == "9.9.9.9" and allowed.source == "given"


def test_a_deleted_ec_number_is_refused_even_when_unlisted_numbers_are_allowed():
    with pytest.raises(NameNotResolved) as raised:
        resolve_enzyme_name("1.1.1.74", allow_unlisted_ec=True)
    assert raised.value.kind == DELETED_OR_UNKNOWN and "deleted" in str(raised.value)


def test_a_transferred_number_with_several_successors_names_them():
    with pytest.raises(NameNotResolved) as raised:
        resolve_enzyme_name("1.1.1.5")
    assert raised.value.candidates == ["1.1.1.303", "1.1.1.304"]
    assert "diacetyl reductase [(R)-acetoin forming]" in str(raised.value)


# --- step 4: UniProt, only for what the nomenclature does not hold ----------


def test_a_protein_name_the_nomenclature_lacks_is_asked_of_uniprot():
    uniprot = Uniprot("2.7.1.2")
    resolution = resolve_enzyme_name("glucokinase regulatory protein", None, uniprot=uniprot)
    assert (resolution.ec, resolution.source, resolution.name) == ("2.7.1.2", "uniprot", "glucokinase")
    assert uniprot.calls == ["glucokinase regulatory protein"]
    assert "UniProt" in resolution.how
    assert resolution.notes("glucokinase regulatory protein")[0].startswith(
        "Read 'glucokinase regulatory protein' as EC 2.7.1.2 (glucokinase)")


def test_uniprot_class_numbers_are_dropped_and_what_is_left_is_the_answer():
    uniprot = Uniprot("1.1.98.-", "1.1.-.-", "2.7.1.2", "2.7.1.2")
    assert resolve_enzyme_name("glucokinase regulatory protein", None, uniprot=uniprot).ec == "2.7.1.2"


def test_several_enzymes_from_uniprot_are_refused_with_names_from_the_nomenclature():
    uniprot = Uniprot("1.1.1.27", "1.1.1.28")
    with pytest.raises(NameNotResolved) as raised:
        resolve_enzyme_name("glucokinase regulatory protein", "human", uniprot=uniprot)
    assert raised.value.kind == AMBIGUOUS
    message = str(raised.value)
    assert "EC 1.1.1.27 L-lactate dehydrogenase" in message and "EC 1.1.1.28 D-lactate dehydrogenase" in message
    assert message.endswith("--subject 1.1.1.27")


def test_a_typo_with_uniprot_finding_nothing_is_refused_with_the_suggestions():
    uniprot = Uniprot()
    with pytest.raises(NameNotResolved) as raised:
        resolve_enzyme_name("hexokinse", "human", uniprot=uniprot)
    assert raised.value.kind == SUGGESTIONS
    assert uniprot.calls == ["hexokinse"], "UniProt was asked before the suggestion was given up on"
    assert "Did you mean" in str(raised.value) and "EC 2.7.1.1 hexokinase" in str(raised.value)
    assert raised.value.candidates == ["2.7.1.1"]


def test_a_typo_uniprot_can_settle_is_settled_by_uniprot():
    uniprot = Uniprot("2.7.1.1")
    assert resolve_enzyme_name("hexokinse", None, uniprot=uniprot).ec == "2.7.1.1"


def test_without_a_uniprot_lookup_a_typo_is_still_a_suggestion_and_nothing_is_a_refusal():
    with pytest.raises(NameNotResolved) as typo:
        resolve_enzyme_name("hexokinse", None)
    assert typo.value.kind == SUGGESTIONS
    with pytest.raises(NameNotResolved) as nothing:
        resolve_enzyme_name("xyzzy plugh", None)
    assert nothing.value.kind == NONE_FOUND and nothing.value.candidates == []
    assert "Check the spelling" in str(nothing.value)


def test_a_name_nobody_indexes_says_so_after_asking_uniprot():
    uniprot = Uniprot()
    with pytest.raises(NameNotResolved) as raised:
        resolve_enzyme_name("xyzzy plugh", None, uniprot=uniprot)
    assert raised.value.kind == NONE_FOUND
    assert "UniProt indexes no reviewed enzyme" in str(raised.value)
    assert "pass the EC number directly" in str(raised.value)


def test_a_network_failure_is_not_reported_as_an_unknown_enzyme():
    def explodes(name):
        raise ConnectionError("connection reset")

    with pytest.raises(NameNotResolved) as raised:
        resolve_enzyme_name("xyzzy plugh", None, uniprot=explodes)
    assert raised.value.kind == LOOKUP_FAILED
    assert "Could not look up" in str(raised.value) and "connection reset" in str(raised.value)
    assert "no reviewed enzyme" not in str(raised.value)


def test_a_failure_with_suggestions_in_hand_still_shows_them():
    def explodes(name):
        raise ConnectionError("connection reset")

    with pytest.raises(NameNotResolved) as raised:
        resolve_enzyme_name("hexokinse", None, uniprot=explodes)
    assert raised.value.kind == LOOKUP_FAILED
    assert "connection reset" in str(raised.value) and "EC 2.7.1.1 hexokinase" in str(raised.value)


def test_a_fragment_of_a_longer_name_is_a_suggestion_even_when_it_is_the_only_match():
    with pytest.raises(NameNotResolved) as raised:
        resolve_enzyme_name("LDH", "human")
    assert raised.value.kind == SUGGESTIONS
    assert "EC 1.1.1.27 L-lactate dehydrogenase" in str(raised.value)
    assert str(raised.value).endswith("--subject <its EC number>")


def test_the_literature_lookup_is_available_in_a_checkout():
    lookup = literature_uniprot_lookup()
    assert callable(lookup), "the checkout's Tests/ holds enzyme_lookup, which asks UniProt"
