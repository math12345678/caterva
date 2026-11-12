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


# --- a gene symbol is read with an organism as well as without one (F12) -----


@pytest.mark.parametrize("text, ec, organism", [
    ("ACE2 kinetics", "3.4.17.23", "Homo sapiens"),
    ("Michaelis-Menten for ACE2 in human", "3.4.17.23", "Homo sapiens"),
    ("ACE2 kinetics in mouse", "3.4.17.23", "Mus musculus"),
])
def test_a_gene_symbol_the_table_reads_is_kept_when_the_organism_is_named(text, ec, organism):
    # "ACE2" alone was read (the assumed-organism note let it through) and
    # "ACE2 in human" was dropped: naming the organism lost the enzyme.
    reading = read_sentence(text)
    assert (reading.ec, reading.organism) == (ec, organism), text


@pytest.mark.parametrize("text, ec", [
    ("DHODH with dihydroorotate in human", "1.3.5.2"),
    ("APRT kinetics in human", "2.4.2.7"),
    ("IMPDH with IMP in human", "1.1.1.205"),
    ("HGPRT with hypoxanthine in human", "2.4.2.8"),
    ("HPRT kinetics", "2.4.2.8"),
    ("GGT kinetics in human", "2.3.2.2"),
    ("FAAH with anandamide in rat", "3.5.1.99"),
    ("SARS-CoV-2 Mpro kinetics", "3.4.22.69"),
    ("3CL protease kinetics", "3.4.22.69"),
])
def test_curated_abbreviations_name_one_enzyme(text, ec):
    reading = read_sentence(text)
    assert reading.ec == ec, text


@pytest.mark.parametrize("text, ec", [
    ("CS kinetics in human", "2.3.3.1"),
    ("Michaelis-Menten for TS in human", "2.1.1.45"),
])
def test_a_two_letter_symbol_with_an_organism_is_refused_with_its_enzyme_named(text, ec):
    reading = read_sentence(text)
    assert reading.ec is None
    assert reading.ambiguity is not None and reading.ambiguity.confirm_only
    assert [c.ec for c in reading.ambiguity.candidates] == [ec]


@pytest.mark.parametrize("text, ec", [("TS kinetics", "2.1.1.45"), ("CS kinetics", "2.3.3.1"),
                                      ("michaelis menten with a TS analogue", "2.1.1.45")])
def test_two_letters_without_an_organism_are_refused_with_the_enzyme_named_never_read(text, ec):
    # Two letters are never read as an enzyme, but a description naming no
    # other enzyme is refused with the one they would be, not "no enzyme
    # was named" (they may be something else: the reason says so).
    reading = read_sentence(text)
    assert reading.ec is None, text
    assert reading.ambiguity is not None and reading.ambiguity.confirm_only
    assert [c.ec for c in reading.ambiguity.candidates] == [ec]
    assert "may be something else" in reading.ambiguity.reason


def test_two_letters_beside_a_named_enzyme_are_left_alone():
    reading = read_sentence("thymidylate synthase with a TS analogue")
    assert reading.ec == "2.1.1.45" and reading.ambiguity is None


def test_a_near_spelling_is_not_called_several_enzymes_in_the_compose_note():
    from caterva.compose.__main__ import read_description

    args = SimpleNamespace(description="hexokinaze with glucose in human", subject=None, organism=None,
                           substrate=None, inhibitor=None, isoform=None)
    out = read_description(args, look_up_substrate=False)
    assert out.name_refusal is not None
    assert "not one enzyme" not in out.refusal_note
    assert "No enzyme is named 'hexokinaze'" in out.refusal_note and "EC 2.7.1.1" in out.refusal_note


# --- the typo tier is fast enough for the studio's finder endpoint ----------


def test_the_typo_tier_gives_the_same_answer_and_compares_each_word_once():
    import time

    from caterva.enzymes import finder

    finder.find("pyruvate kinase")  # load the index and tables
    calls = 0
    real = finder._within

    def counting(a, b, limit):
        nonlocal calls
        calls += 1
        return real(a, b, limit)

    finder._within = counting
    try:
        started = time.process_time()
        found = finder.find("hexokinse", organism="human")
        spent = time.process_time() - started
    finally:
        finder._within = real
    assert [c.ec for c in found][:1] == ["2.7.1.1"] and found[0].tier == TIER_TYPO
    # One comparison per distinct name word, not one per word of every name
    # (the latter was ~100,000 calls and seconds of wall time on a busy machine).
    assert calls <= len(finder._tables(load_index()).vocabulary)
    assert spent < 2.0


# --- a mammalian gene symbol in a mammal the table does not hold it for (F12) -


@pytest.mark.parametrize("text, ec, organism, isoform", [
    ("MMP-9 from bovine with gelatin", "3.4.24.35", "Bos taurus", None),
    ("factor Xa from bovine with S-2222", "3.4.21.6", "Bos taurus", None),
    ("HDAC1 kinetics in rat", "3.5.1.98", "Rattus norvegicus", "HDAC1"),
    ("CA2 from bovine with 4-nitrophenyl acetate", "4.2.1.1", "Bos taurus", "CA2"),
    ("DPP4 in rat", "3.4.14.5", "Rattus norvegicus", None),
])
def test_a_mammalian_symbol_is_read_as_its_ortholog_with_a_note(text, ec, organism, isoform):
    reading = read_sentence(text)
    assert (reading.ec, reading.organism) == (ec, organism), text
    assert reading.isoform == isoform
    result = resolve(reading.enzyme_text, organism)
    assert any("mammalian orthologs carry one symbol" in n for n in result.notes)


@pytest.mark.parametrize("text, why", [
    ("CYP2D6 with dextromethorphan in rat", "not for rat"),   # P450 families differ between species
    ("MAO-A with serotonin in E. coli", "not for E. coli"),
    ("DPP4 in E. coli", "not for E. coli"),
])
def test_a_symbol_of_another_organism_is_refused_never_dropped(text, why):
    # Refused with the reason, and no other organism's enzyme offered as a
    # candidate (the hand-checked lab_names fixture forbids that).
    reading = read_sentence(text)
    assert reading.ec is None, text
    assert reading.ambiguity is not None and not reading.ambiguity.candidates
    assert why in reading.ambiguity.reason


def test_an_abbreviation_of_several_enzymes_stays_a_choice_in_an_organism_too():
    # ADR 0181/0182: an abbreviation is never resolved by the organism's
    # protein list; "rabbit muscle LDH" is refused with both enzymes named.
    reading = read_sentence("rabbit muscle LDH with pyruvate")
    assert reading.ec is None and {"1.1.1.27", "1.1.1.28"} <= {c.ec for c in reading.ambiguity.candidates}


# --- names written the other ways people write them (F12) --------------------


@pytest.mark.parametrize("text, ec, isoform, organism", [
    ("hCA II with CO2", "4.2.1.1", "CA2", "Homo sapiens"),
    ("P450 3A4 with midazolam", "1.14.14.1", "CYP3A4", "Homo sapiens"),
    ("cytochrome P450 3A4 with testosterone in human", "1.14.14.1", "CYP3A4", "Homo sapiens"),
    ("p38 kinetics in human", "2.7.11.24", "MAPK14", "Homo sapiens"),
    ("ERK2 with myelin basic protein in human", "2.7.11.24", "MAPK1", "Homo sapiens"),
    ("iNOS with L-arginine in mouse", "1.14.13.39", "NOS2", "Mus musculus"),
    ("SIRT1 with NAD+ in human", "2.3.1.286", "SIRT1", "Homo sapiens"),
    ("HER2 kinetics in human", "2.7.10.1", "ERBB2", "Homo sapiens"),
    ("KPC-2 with meropenem", "3.5.2.6", "KPC-2", None),
    ("PP2A with phosphorylase a", "3.1.3.16", "PP2A", None),
])
def test_symbols_and_lab_names_are_read(text, ec, isoform, organism):
    reading = read_sentence(text)
    assert (reading.ec, reading.isoform, reading.organism) == (ec, isoform, organism), text


@pytest.mark.parametrize("text, ec", [
    ("factor VIIa kinetics", "3.4.21.21"),
    ("uPA with plasminogen in human", "3.4.21.73"),
    ("HPPD inhibited by mesotrione", "1.13.11.27"),
    ("11beta-HSD1 with cortisone in human", "1.1.1.146"),
    ("HIV-1 RT inhibited by nevirapine", "2.7.7.49"),
    ("NS3 protease kinetics", "3.4.21.98"),
    ("beta-gal with ONPG", "3.2.1.23"),
    ("pig liver esterase with ethyl butyrate", "3.1.1.1"),
    ("Renilla luciferase with coelenterazine", "1.13.12.5"),
    ("PFK-1 with fructose 6-phosphate in rat", "2.7.1.11"),
    ("InhA with NADH", "1.3.1.9"),
])
def test_curated_names_name_one_enzyme(text, ec):
    assert read_sentence(text).ec == ec, text


@pytest.mark.parametrize("text, expected", [
    ("calpain with casein", {"3.4.22.52", "3.4.22.53"}),
    ("PI3K with PIP2 in human", {"2.7.1.137", "2.7.1.153"}),
])
def test_a_family_name_is_refused_with_its_members(text, expected):
    reading = read_sentence(text)
    assert reading.ec is None and reading.ambiguity is not None, text
    assert expected <= {c.ec for c in reading.ambiguity.candidates}


def test_hiv_1_reverse_transcriptase_searches_hiv_1():
    # "HIV-1" says which virus; plain "HIV" is HIV-1 or HIV-2 and is not read as either.
    reading = read_sentence("HIV-1 reverse transcriptase inhibited by nevirapine")
    assert reading.ec == "2.7.7.49" and reading.organism == "Human immunodeficiency virus 1"


# --- tissue words, trade-code substrates, firefly (F04, F13) -----------------


@pytest.mark.parametrize("text, substrates", [
    ("rabbit muscle LDH with pyruvate", ("pyruvate",)),
    ("catalase from bovine liver with H2O2", ("H2O2",)),
    ("alkaline phosphatase from calf intestine with p-nitrophenyl phosphate", ("p-nitrophenyl phosphate",)),
    ("thrombin with S-2238", ("S-2238",)),
    ("chymotrypsin from bovine pancreas with BTEE", ("BTEE",)),
])
def test_tissue_words_are_the_source_and_trade_codes_are_substrates(text, substrates):
    assert read_sentence(text).substrate_candidates == substrates, text


@pytest.mark.parametrize("typed, listed, expected", [
    ("S-2238", {"D-phenylalanyl-pipecolyl-L-arginine-4-nitroanilide": 67, "S2238": 5},
     "D-phenylalanyl-pipecolyl-L-arginine-4-nitroanilide"),
    ("BTEE", {"N-benzoyl-L-tyrosine ethyl ester": 32}, "N-benzoyl-L-tyrosine ethyl ester"),
    ("Suc-AAPF-pNA", {"N-succinyl-Ala-Ala-Pro-Phe-4-nitroanilide": 60}, "N-succinyl-Ala-Ala-Pro-Phe-4-nitroanilide"),
    ("MUNANA", {"4-methylumbelliferyl alpha-D-N-acetylneuraminic acid": 109},
     "4-methylumbelliferyl alpha-D-N-acetylneuraminic acid"),
    # Review, 2026-11-12: bovine factor Xa's S-2222 rows are spelled out, and
    # "factor Xa with S-2222 in bovine" fell to S-2337 (the piperidineamide).
    ("S-2222", {"benzoyl-Ile-Glu-(-H/OMe)-Gly-Arg-p-nitroanilide": 3,
                "benzoyl-Ile-Glu(piperidineamide)-Gly-Arg-p-nitroanilide": 3},
     "benzoyl-Ile-Glu-(-H/OMe)-Gly-Arg-p-nitroanilide"),
])
def test_trade_codes_reach_brendas_spelling(typed, listed, expected):
    assert match_substrate((typed,), listed).name == expected


def test_firefly_is_photinus_pyralis():
    reading = read_sentence("luciferase from firefly with luciferin")
    assert reading.organism == "Photinus pyralis" and reading.unread_organism is None


def test_a_symbol_of_another_organism_is_not_called_several_enzymes_in_the_compose_note():
    from caterva.compose.__main__ import read_description

    args = SimpleNamespace(description="CYP2D6 with dextromethorphan in rat", subject=None, organism=None,
                           substrate=None, inhibitor=None, isoform=None)
    out = read_description(args, look_up_substrate=False)
    assert out.name_refusal is not None
    assert "not one enzyme" not in out.refusal_note and "not for rat" in out.refusal_note


@pytest.mark.parametrize("text, organism", [
    ("pancreatic amylase kinetics from pig", "Sus scrofa"),
    ("salivary amylase with starch in human", "Homo sapiens"),
    ("porcine pancreatic alpha-amylase", "Sus scrofa"),
])
def test_pancreatic_and_salivary_amylase_are_alpha_amylase(text, organism):
    """Review, 2026-11-12: refused as 'amylase', eight enzymes, though both are EC 3.2.1.1."""
    reading = read_sentence(text)
    assert (reading.ec, reading.organism) == ("3.2.1.1", organism)


def test_amylase_alone_is_still_refused_with_its_candidates():
    reading = read_sentence("michaelis menten for amylase with starch")
    assert reading.ec is None and reading.ambiguity is not None
    assert {"3.2.1.1", "3.2.1.2"} <= {c.ec for c in reading.ambiguity.candidates}


@pytest.mark.parametrize("text, ec", [
    ("Michaelis-Menten for chymotripsin in bovine", "3.4.21.1"),
    ("trypsine from bovine with BAPNA", "3.4.21.4"),
    ("lysozme from hen egg white", "3.2.1.17"),
    ("thrombine with S-2238 in human", "3.4.21.5"),
])
def test_a_misspelt_one_word_name_is_refused_with_the_name_not_dropped(text, ec):
    """Review, 2026-11-12: names ending -in or -zyme were only near-spelled when they
    ended -ase, so "chymotripsin" was dropped and the report said no enzyme was named."""
    reading = read_sentence(text)
    assert reading.ec is None and reading.names_enzyme, text
    assert reading.ambiguity is not None and ec in {c.ec for c in reading.ambiguity.candidates}


@pytest.mark.parametrize("text", [
    "plasmid DNA with EcoRI",
    "Michaelis-Menten with glutamine in human",
    "michaelis menten with heparin",
])
def test_a_compound_close_to_a_one_word_name_is_not_a_misspelling(text):
    reading = read_sentence(text)
    assert reading.ambiguity is None or not all(
        c.via == "typo" for c in reading.ambiguity.candidates), text
