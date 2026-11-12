"""Names a professor types, read or refused with the candidates -- never dropped.

Round-1 adversarial findings (2026-11-11): F12 (enzyme names and symbols not
read), M7 ("amylase" dropped and the report said no enzyme was named), F04
(common-name organisms: jack bean, hen egg white, electric eel), F13
(substrate abbreviations and synonyms: CDNB, hydrogen peroxide) and F15
(butyrylcholinesterase reported as a spelling correction). Offline: the
committed enzyme index, symbol table and aliases only.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from caterva.compose.organisms import normalise_organism
from caterva.enzymes.finder import TIER_TYPO, Resolved, _spacing_variant, resolve
from caterva.enzymes.index import load_index, organism_code
from caterva.enzymes.sentence import match_substrate, read_sentence


# --- a name that is not ONE enzyme is refused with its candidates (M7, F12) ---


@pytest.mark.parametrize("text, expected", [
    ("michaelis menten for amylase with starch", {"3.2.1.1", "3.2.1.2"}),
    ("aldehyde dehydrogenase with acetaldehyde", {"1.2.1.3"}),
    ("isocitrate dehydrogenase with isocitrate", {"1.1.1.41", "1.1.1.42"}),
    ("DNA polymerase with dNTP", {"2.7.7.7"}),
    ("nitric oxide synthase with arginine", {"1.14.13.39"}),
    ("elastase with elastin", {"3.4.21.36", "3.4.21.37"}),
    ("LDH with pyruvate in human", {"1.1.1.27", "1.1.1.28"}),
    ("MDH with oxaloacetate", {"1.1.1.37"}),
    ("HMG-CoA reductase with HMG-CoA", {"1.1.1.34", "1.1.1.88"}),
    ("hexokinaze with glucose in human", {"2.7.1.1"}),
])
def test_an_enzyme_name_that_is_not_one_enzyme_is_returned_as_an_ambiguity(text, expected):
    reading = read_sentence(text)
    assert reading.ec is None
    assert reading.ambiguity is not None and reading.names_enzyme, text
    assert expected <= {c.ec for c in reading.ambiguity.candidates}


def test_a_near_spelling_is_offered_never_read():
    reading = read_sentence("hexokinaze with glucose in human")
    assert reading.ambiguity.suggestions_only
    assert all(c.tier == TIER_TYPO for c in reading.ambiguity.candidates)


@pytest.mark.parametrize("text", [
    "binding of heparin to albumin", "insulin signalling with casein", "reaction with ase",
    "three step MAP kinase cascade with phosphatases", "a kinase and a phosphatase",
    "Michaelis-Menten with ATP", "competitive inhibition with CoA", "michaelis menten with lipases",
    "Michaelis-Menten with glucoze",
])
def test_compounds_and_class_words_are_still_not_enzymes(text):
    reading = read_sentence(text)
    assert reading.ec is None and reading.ambiguity is None, text


def test_the_compose_reader_refuses_amylase_with_its_candidates_instead_of_no_enzyme_named():
    from caterva.compose.__main__ import read_description

    args = SimpleNamespace(description="michaelis menten for amylase with starch", subject=None, organism=None,
                           substrate=None, inhibitor=None, isoform=None)
    out = read_description(args, look_up_substrate=False)
    assert out.name_refusal is not None
    assert "alpha-amylase" in str(out.name_refusal) and "beta-amylase" in str(out.name_refusal)
    assert "no enzyme was named" not in " ".join(out.notes)


# --- names and symbols that are one enzyme are read (F12) ---------------------


@pytest.mark.parametrize("text, ec, isoform, organism", [
    ("ALDH2 with acetaldehyde in human", "1.2.1.3", "ALDH2", "Homo sapiens"),
    ("ALDH2 Michaelis-Menten", "1.2.1.3", "ALDH2", "Homo sapiens"),
    ("HMG-CoA reductase inhibited by atorvastatin in human", "1.1.1.34", None, "Homo sapiens"),
    ("kinetics of β-galactosidase in E. coli", "3.2.1.23", None, "Escherichia coli"),
    ("DNase I with DNA", "3.1.21.1", None, None),
    ("tPA with plasminogen", "3.4.21.68", None, None),
    ("TIM with DHAP", "5.3.1.1", None, None),
])
def test_one_enzyme_names_are_read(text, ec, isoform, organism):
    reading = read_sentence(text)
    assert (reading.ec, reading.isoform, reading.organism) == (ec, isoform, organism), text


def test_protein_kinase_a_is_not_a_class_window():
    # "A" on its own is the name's letter, not the article.
    reading = read_sentence("protein kinase A competitive inhibitor", organism="bovine")
    assert reading.ec == "2.7.11.11"
    assert read_sentence("a protein kinase and a phosphatase").ec is None


def test_hmg_coa_reductase_is_still_a_choice_in_a_bacterium():
    assert not isinstance(resolve("HMG-CoA reductase", "E. coli"), Resolved)
    assert resolve("HMG-CoA reductase", "human").ec == "1.1.1.34"


def test_a_greek_letter_is_the_spelled_name():
    assert resolve("β-galactosidase").ec == "3.2.1.23"
    assert resolve("α-amylase").ec == "3.2.1.1"


# --- butyrylcholinesterase is a listed name, not a typo (F15) ------------------


def test_butyrylcholinesterase_is_read_as_a_listed_name_not_a_spelling():
    reading = read_sentence("butyrylcholinesterase Michaelis-Menten in human")
    assert reading.ec == "3.1.1.8"
    assert "spelling" not in reading.enzyme_note()
    assert "butyrylcholine esterase" in reading.enzyme_note()


def test_a_name_with_its_spacing_moved_is_that_name():
    result = _spacing_variant("pseudo cholinesterase", None, load_index())
    assert result is not None and result.ec == "3.1.1.8"
    assert "pseudocholinesterase" in result.how and "spelling" not in result.how
    # Typed exactly as listed: the finder's own decision stands.
    assert _spacing_variant("protein kinase", None, load_index()) is None


def test_a_real_spelling_note_quotes_the_name_it_was_close_to():
    reading = read_sentence("acetylcholinestrase with acetylcholine")
    assert reading.ec == "3.1.1.7" and "spelling" in reading.how


# --- common-name organisms (F04) ------------------------------------------------


@pytest.mark.parametrize("text, ec, organism", [
    ("urease from jack bean with urea", "3.5.1.5", "Canavalia ensiformis"),
    ("lysozyme from hen egg white", "3.2.1.17", "Gallus gallus"),
    ("hen egg-white lysozyme", "3.2.1.17", "Gallus gallus"),
    ("acetylcholinesterase from electric eel", "3.1.1.7", "Electrophorus electricus"),
    ("mushroom tyrosinase with L-DOPA", "1.14.18.1", "Agaricus bisporus"),
    ("calf intestinal alkaline phosphatase with pNPP", "3.1.3.1", "Bos taurus"),
    ("lactase from baker's yeast", "3.2.1.108", "Saccharomyces cerevisiae"),
    ("beta-amylase from sweet potato", "3.2.1.2", "Ipomoea batatas"),
])
def test_common_name_organisms_are_read_in_a_sentence(text, ec, organism):
    reading = read_sentence(text)
    assert (reading.ec, reading.organism) == (ec, organism), text
    assert not any(organism_word in c for c in reading.substrate_candidates
                   for organism_word in ("jack", "hen", "eel", "egg"))


@pytest.mark.parametrize("typed, binomial", [
    ("jack bean", "Canavalia ensiformis"), ("electric eel", "Electrophorus electricus"),
    ("hen egg white", "Gallus gallus"), ("Jack Bean", "Canavalia ensiformis"), ("bovine", "Bos taurus"),
    ("porcine", "Sus scrofa"), ("rat", "Rattus norvegicus"), ("mouse", "Mus musculus"),
    ("baker's yeast", "Saccharomyces cerevisiae"), ("E. coli", "Escherichia coli"),
])
def test_common_name_organisms_are_read_as_a_flag(typed, binomial):
    searched, note = normalise_organism(typed)
    assert searched == binomial
    assert organism_code(typed) is not None


def test_an_unknown_two_word_organism_is_not_said_to_be_read():
    searched, note = normalise_organism("sword bean")
    assert searched == "Sword bean"
    assert "Read --organism" not in note and "is not an organism Caterva knows" in note


def test_words_after_from_that_name_no_known_organism_are_said_not_used_as_a_substrate():
    reading = read_sentence("urease from sword bean with urea")
    assert reading.ec == "3.5.1.5" and reading.organism is None
    assert reading.unread_organism == ("sword bean", None)
    assert "sword bean" not in reading.substrate_candidates
    assert "not an organism name Caterva knows" in " ".join(reading.notes())
    # A compound after "from" is not taken for a source.
    assert read_sentence("hexokinase from glucose").unread_organism is None


# --- substrate synonyms and abbreviations (F13) ---------------------------------


@pytest.mark.parametrize("typed, listed, expected", [
    ("CDNB", {"1-chloro-2,4-dinitrobenzene": 289, "glutathione": 250}, "1-chloro-2,4-dinitrobenzene"),
    ("hydrogen peroxide", {"H2O2": 79}, "H2O2"),
    ("H2O2", {"hydrogen peroxide": 3}, "hydrogen peroxide"),
    ("GSH", {"glutathione": 13, "GSSG": 45}, "glutathione"),
    ("GSSG", {"glutathione disulfide": 41}, "glutathione disulfide"),
    ("DHAP", {"glycerone phosphate": 22, "dihydroxyacetone phosphate": 21}, "glycerone phosphate"),
    ("OAA", {"oxaloacetate": 150, "(S)-malate": 45}, "oxaloacetate"),
    ("HMG-CoA", {"3-hydroxy-3-methylglutaryl-CoA": 16, "(S)-3-hydroxy-3-methylglutaryl-CoA": 9},
     "3-hydroxy-3-methylglutaryl-CoA"),
    ("ABTS", {"2,2'-azinobis(3-ethylbenzthiazoline-6-sulfonic acid)": 12, "H2O2": 86},
     "2,2'-azinobis(3-ethylbenzthiazoline-6-sulfonic acid)"),
    ("ACh", {"Acetylcholine": 38, "acetylthiocholine": 131}, "Acetylcholine"),
])
def test_substrate_synonyms_reach_brendas_spelling(typed, listed, expected):
    match = match_substrate([typed], listed)
    assert match.name == expected
    assert "same molecule" in match.note()


def test_cdnb_is_read_from_the_sentence():
    reading = read_sentence("glutathione S-transferase with CDNB in human")
    assert reading.ec == "2.5.1.18" and "CDNB" in reading.substrate_candidates
    match = match_substrate(reading.substrate_candidates,
                            {"1-chloro-2,4-dinitrobenzene": 289, "glutathione": 250})
    assert match.name == "1-chloro-2,4-dinitrobenzene"
