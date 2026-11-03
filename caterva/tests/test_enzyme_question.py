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
