"""caterva.enzymes.question: the system read out of a short question, or None.

The TypeScript CLI's --resolve parser was anchored on prepositions, so
"hexokinase glucose human" and "human hexokinase on glucose" read as naming
no system. These pin the orderings that are now read -- each one from names
the shared tables hold exactly -- and the ones that must still be refused.
"""
import pytest

from caterva.enzymes.index import organism_binomial
from caterva.enzymes.question import canonical_organism, read_system

HEXOKINASE_HUMAN = {"enzyme": "hexokinase", "substrate": "glucose",
                    "organism": "Homo sapiens"}


@pytest.mark.parametrize("query, typed", [
    ("hexokinase glucose human", "human"),
    ("hexokinase with glucose in humans", "humans"),
    ("human hexokinase on glucose", "human"),
    ("human hexokinase glucose", "human"),
    ("simulate michaelis menten of hexokinase glucose in humans", "humans"),
])
def test_orderings_without_the_full_preposition_pattern_are_read(query, typed):
    assert read_system(query) == {**HEXOKINASE_HUMAN, "typed": typed}


def test_a_multiword_enzyme_name_is_bounded_by_the_nomenclature():
    # "lactate" alone is only a phrase inside longer names (tier 5), so the
    # enzyme cannot end there; "lactate dehydrogenase" is a name.
    assert read_system("lactate dehydrogenase pyruvate human") == {
        "enzyme": "lactate dehydrogenase", "substrate": "pyruvate",
        "organism": "Homo sapiens", "typed": "human"}


@pytest.mark.parametrize("query", [
    "hexokinase glucose",            # no organism the table holds
    "glucose hexokinase human",      # "glucose" names no enzyme
    "hexokinase human",              # nothing left for a substrate
    "michaelis menten",
    "hexokinase on glucose with ATP human",  # two joiners: two readings
    "human hexokinase glucose mouse",        # an organism at both ends
])
def test_anything_not_read_exactly_is_refused(query):
    assert read_system(query) is None


def test_a_strain_is_kept_as_typed():
    assert read_system("acetylcholinesterase acetylcholine E. coli K-12")["organism"] == "E. coli K-12"
    assert organism_binomial("E. coli K-12") is None


def test_canonical_organism_names_what_was_typed():
    assert canonical_organism("humans") == {"organism": "Homo sapiens", "typed": "humans"}
    assert canonical_organism("Thermus aquaticus") == {
        "organism": "Thermus aquaticus", "typed": "Thermus aquaticus"}


# --- found 2026-11-03 by review -------------------------------------------
#
# "enzyme" equals "D-enzyme" (EC 2.4.1.25) once the D- is set aside, so it
# reached the stereo-tolerant tier and was read as an enzyme name; the
# runner then cited BRENDA ref 737180 (27.5 mM, 4-alpha-glucanotransferase)
# for `simulate "enzyme maltotriose arabidopsis"`. The fix is in finder.py,
# the one place every command resolves a name, so both the reader and the
# resolver are pinned here.

@pytest.mark.parametrize("query", [
    "enzyme glucose human",
    "michaelis menten enzyme kinetics glucose human",
    "enzyme maltotriose arabidopsis",
])
def test_a_class_word_is_not_read_as_an_enzyme(query):
    assert read_system(query) is None


@pytest.mark.parametrize("word", ["enzyme", "protein", "peptidase", "dioxygenase"])
def test_a_class_word_does_not_resolve_to_the_enzyme_whose_labelled_name_it_is(word):
    from caterva.enzymes.finder import TIER_ALTERNATIVE_TOLERANT, Resolved, find, resolve

    assert not isinstance(resolve(word, "human"), Resolved)
    assert all(c.tier > TIER_ALTERNATIVE_TOLERANT for c in find(word, "human"))


def test_a_one_word_name_only_its_own_enzyme_uses_still_resolves_tolerantly():
    # The rule is "a word of OTHER enzymes' names", not "one word": the
    # stereo-tolerant tier keeps doing its job where nothing else competes.
    from caterva.enzymes.finder import Resolved, resolve

    result = resolve("fuculokinase", "human")
    assert isinstance(result, Resolved) and result.ec == "2.7.1.51"


@pytest.mark.parametrize("query", [
    "hexokinase glucose phosphoglucose isomerase human",
    "hexokinase glucose then pyruvate kinase human",
    "hexokinase glucose and fructose human",
])
def test_a_cascade_or_mixture_is_refused_not_read_with_a_junk_substrate(query):
    assert read_system(query) is None


def test_the_identity_shown_at_confirmation_is_the_resolver_s():
    from caterva.enzymes.question import enzyme_identity

    assert enzyme_identity("hexokinase", "Homo sapiens") == {"ec": "2.7.1.1", "name": "hexokinase"}
    # Two enzymes by that name: nothing decided offline, so nothing shown as one.
    assert enzyme_identity("lactate dehydrogenase", "Homo sapiens") is None
    assert enzyme_identity("enzyme", "Arabidopsis thaliana") is None
