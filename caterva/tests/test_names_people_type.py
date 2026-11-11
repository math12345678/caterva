"""The names people type for an enzyme, a substrate and an inhibitor are read as one thing, and said (ADR 0182).

WHY THESE TESTS
---------------
A live baseline of 56 queries a biochemist types (2026-11-11) found the reader
refusing what it could read: "CYP2B6", "HK2", "LDHA", "PTP1B", "COX-2",
"MAO-B", "PDE5", "HIV-1 protease" and "angiotensin-converting enzyme" named
no enzyme or a refused one; "acetylcholinestrase" was not forgiven its one
missing letter; "trypsin cleaving BAPNA" took "cleaving BAPNA" as the
substrate; "MAO-B" pointed its re-run at EC 1.4.3.21, a different enzyme. The
owner's decision: a name that is ONE enzyme in the organism is read as it,
with its isoform and, when nothing was given, the organism it implies, each
said in a note; a name several enzymes go by is still a choice, and the class
words ADR 0181 refuses are still refused.

Offline throughout: the committed nomenclature index, the committed symbol
and alias tables, the recorded BRENDA page for EC 2.7.1.1, and monkeypatched
UniProt answers. Nothing here reaches the network.
"""
from __future__ import annotations

import gzip
import json
from pathlib import Path

import pytest

from caterva.enzymes import Ambiguous, Resolved, load_index, resolve
from caterva.enzymes.finder import spelling_match
from caterva.enzymes.policy import NameNotResolved, resolve_enzyme_name, split_mutation
from caterva.enzymes.sentence import SUBSTRATE_ABBREVIATIONS, match_substrate, read_sentence
from caterva.enzymes.symbols import ALIASES_PATH, load_symbols

REPO = Path(__file__).resolve().parents[2]
ALIASES = json.loads(ALIASES_PATH.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# The curated alias table
# ---------------------------------------------------------------------------


def test_every_alias_names_an_active_enzyme_of_the_nomenclature_and_cites_its_basis():
    entries = load_index().entries
    for row in ALIASES["aliases"]:
        ecs = [row["ec"]] if "ec" in row else list(row["by_organism"].values())
        for ec in ecs:
            assert ec in entries and entries[ec].status == "active", (row["names"], ec)
        assert row["source"].strip(), row["names"]
        for code in list(row.get("by_organism", {})) + list(row.get("organisms", [])):
            from caterva.enzymes.index import ORGANISMS

            assert code in ORGANISMS, (row["names"], code)


def test_an_alias_that_cites_a_gene_symbol_agrees_with_the_uniprot_symbol_table():
    """Where the generated symbol table holds the same human gene, the accession the hand-written row cites
    is the one UniProtKB gives it: a typo in a curated row cannot hide."""
    import re

    genes = {g["symbol"]: g for g in json.loads((REPO / "caterva/enzymes/data/symbols.json").read_text())["genes"]}
    checked = 0
    for row in ALIASES["aliases"]:
        found = re.search(r"HGNC symbol (\S+) \(UniProtKB (\w+)\)", row["source"])
        if found and found.group(1) in genes and "HUMAN" in genes[found.group(1)]["organisms"]:
            assert genes[found.group(1)]["organisms"]["HUMAN"]["accession"] == found.group(2), row["names"]
            checked += 1
    assert checked >= 15


@pytest.mark.parametrize("name, ec, isoform, organism", [
    ("CYP1A2", "1.14.14.1", "CYP1A2", "Homo sapiens"), ("CYP2A6", "1.14.14.1", "CYP2A6", "Homo sapiens"),
    ("CYP2B6", "1.14.14.1", "CYP2B6", "Homo sapiens"), ("CYP2C8", "1.14.14.1", "CYP2C8", "Homo sapiens"),
    ("CYP2C9", "1.14.14.1", "CYP2C9", "Homo sapiens"), ("CYP2C19", "1.14.14.1", "CYP2C19", "Homo sapiens"),
    ("CYP2D6", "1.14.14.1", "CYP2D6", "Homo sapiens"), ("CYP2E1", "1.14.14.1", "CYP2E1", "Homo sapiens"),
    ("CYP3A4", "1.14.14.1", "CYP3A4", "Homo sapiens"), ("CYP3A5", "1.14.14.1", "CYP3A5", "Homo sapiens"),
    ("COX-1", "1.14.99.1", "PTGS1", "Homo sapiens"), ("PTGS1", "1.14.99.1", "PTGS1", "Homo sapiens"),
    ("COX-2", "1.14.99.1", "PTGS2", "Homo sapiens"), ("PTGS2", "1.14.99.1", "PTGS2", "Homo sapiens"),
    ("MAO-A", "1.4.3.4", "MAOA", "Homo sapiens"), ("MAOA", "1.4.3.4", "MAOA", "Homo sapiens"),
    ("MAO-B", "1.4.3.4", "MAOB", "Homo sapiens"), ("MAOB", "1.4.3.4", "MAOB", "Homo sapiens"),
    ("PDE5", "3.1.4.35", "PDE5A", "Homo sapiens"), ("PDE5A", "3.1.4.35", "PDE5A", "Homo sapiens"),
    ("PTP1B", "3.1.3.48", "PTPN1", "Homo sapiens"), ("PTPN1", "3.1.3.48", "PTPN1", "Homo sapiens"),
    ("EGFR", "2.7.10.1", "EGFR", "Homo sapiens"),
    ("ACE", "3.4.15.1", None, None), ("angiotensin-converting enzyme", "3.4.15.1", None, None),
    ("angiotensin converting enzyme", "3.4.15.1", None, None),
    ("HIV-1 protease", "3.4.23.16", None, "Human immunodeficiency virus 1"),
    ("HIV protease", "3.4.23.16", None, "Human immunodeficiency virus 1"),
    ("HIV-1 PR", "3.4.23.16", None, "Human immunodeficiency virus 1"),
    ("fumarase", "4.2.1.2", None, None),
    ("invertase", "3.2.1.26", None, None), ("pepsin", "3.4.23.1", None, None),
    ("lysozyme", "3.2.1.17", None, None), ("beta-lactamase", "3.5.2.6", None, None),
    ("beta lactamase", "3.5.2.6", None, None), ("TEM-1", "3.5.2.6", "TEM-1", None),
    ("DHFR", "1.5.1.3", None, None), ("AChE", "3.1.1.7", None, None), ("BChE", "3.1.1.8", None, None),
    ("G6PD", "1.1.1.49", "G6PD", "Homo sapiens"), ("IDH1", "1.1.1.42", "IDH1", "Homo sapiens"),
    ("HK2", "2.7.1.1", "HK2", "Homo sapiens"), ("LDHA", "1.1.1.27", "LDHA", "Homo sapiens"),
    ("BACE1", "3.4.23.46", None, "Homo sapiens"),   # one human protein: no isoform to carry
    ("thrombin", "3.4.21.5", None, None),            # F2's protein, the only one of its EC
])
def test_a_name_people_type_for_one_enzyme_resolves_with_its_isoform_and_implied_organism(name, ec, isoform, organism):
    result = resolve(name, None)
    assert isinstance(result, Resolved), (name, getattr(result, "reason", ""))
    assert (result.ec, result.isoform, result.organism) == (ec, isoform, organism)
    if organism:
        assert any(organism in n for n in result.notes), "an assumed organism is always said"


def test_mao_b_is_monoamine_oxidase_never_the_primary_amine_oxidase_uniprot_also_lists():
    """The baseline's suggested re-run for MAO-B pointed at EC 1.4.3.21 (primary-amine oxidase)."""
    for name in ("MAO-B", "MAOB", "MAO-A", "MAOA"):
        for organism in (None, "human", "mouse"):
            result = resolve(name, organism)
            assert isinstance(result, Resolved) and result.ec == "1.4.3.4", (name, organism)


def test_pepck_is_read_only_when_the_organism_decides_it():
    unasked = resolve("PEPCK", None)
    assert isinstance(unasked, Ambiguous) and {c.ec for c in unasked.candidates} >= {"4.1.1.32", "4.1.1.49"}
    human = resolve("PEPCK", "human")
    assert isinstance(human, Resolved) and human.ec == "4.1.1.32"
    assert any("because the organism is human" in n for n in human.notes)
    assert resolve("PEPCK", "yeast").ec == "4.1.1.49"


def test_a_gene_symbol_is_read_for_the_organism_given_never_another_organisms():
    """IDH1 is the NADP enzyme in human and the NAD subunit in yeast; a CYP2B6 typed for a mouse is not the
    human row read across."""
    assert resolve("IDH1", "yeast").ec == "1.1.1.41"
    assert resolve("IDH1", "human").ec == "1.1.1.42" and resolve("IDH1", "human").organism is None
    mouse = resolve("CYP2B6", "mouse")
    assert not (isinstance(mouse, Resolved) and mouse.isoform == "CYP2B6"), "the human alias is not read for mouse"


def test_a_symbol_written_in_lower_case_is_not_given_an_organism():
    """Upper case is how a human gene symbol is written; "hk2" is still hexokinase (every organism the table
    holds agrees) but no organism is assumed for it."""
    result = resolve("hk2", None)
    assert isinstance(result, Resolved) and result.ec == "2.7.1.1" and result.organism is None


@pytest.mark.parametrize("name", ["HK", "LDH", "ADH", "NOS", "SDH", "AK", "COX", "HMG-CoA reductase", "CAT"])
def test_a_symbol_several_enzymes_go_by_is_still_a_choice(name):
    result = resolve(name, None)
    assert isinstance(result, Ambiguous) and len({c.ec for c in result.candidates}) > 1, name


@pytest.mark.parametrize("name", ["kinase", "protein kinase", "dehydrogenase", "protein", "phosphatase", "enzyme"])
def test_a_class_word_is_still_refused(name):
    """ADR 0181's safety rule survives ADR 0182: a word for a kind of enzyme is no enzyme. ("MAP kinase" is an
    exact other name of EC 2.7.11.24 to the finder, as before; the sentence reader's class-word guard keeps it
    out of a description, tested in test_sentence_names_the_enzyme.py.)"""
    for organism in (None, "human"):
        assert not isinstance(resolve(name, organism), Resolved), name
        with pytest.raises(NameNotResolved):
            resolve_enzyme_name(name, organism)


def test_the_organism_given_wins_and_a_viral_enzyme_says_where_brenda_files_it():
    result = resolve("HIV-1 protease", "human")
    assert isinstance(result, Resolved) and result.ec == "3.4.23.16" and result.organism is None
    assert any("Human immunodeficiency virus 1" in n and "Homo sapiens was searched" in n for n in result.notes)


# ---------------------------------------------------------------------------
# Spelling
# ---------------------------------------------------------------------------


def test_one_missing_letter_in_a_long_enzyme_name_is_read_and_said():
    result = resolve("acetylcholinestrase", None)
    assert isinstance(result, Resolved) and result.ec == "3.1.1.7"
    assert result.notes[0].startswith("Read 'acetylcholinestrase' as acetylcholinesterase (spelling)")
    named = resolve_enzyme_name("acetylcholinestrase")
    assert named.ec == "3.1.1.7"
    assert any("(spelling)" in n for n in named.notes("acetylcholinestrase"))


@pytest.mark.parametrize("text", [
    "lipse",                 # short: within a letter of too many words
    "hexokinas",             # does not end the way an enzyme name does
    "glucose 6-phosphate",   # a compound within a few letters of glucose-6-phosphatase
    "fructose bisphosphate",  # a compound within a few letters of fructose-bisphosphatase
    "lactat dehydrogenase",  # as close to D- as to L-lactate dehydrogenase
    "acetylcholine",         # the substrate, not the enzyme
    "ethanol",
])
def test_a_spelling_is_never_forgiven_into_a_guess(text):
    assert spelling_match(text) is None, text


# ---------------------------------------------------------------------------
# UniProt's gene-name search, after the nomenclature and the protein-name search
# ---------------------------------------------------------------------------


def test_the_gene_name_search_is_asked_only_after_the_protein_name_search_finds_nothing(monkeypatch):
    asked = []

    def protein(name):
        asked.append(("protein", name))
        return []

    def gene(symbol, taxon):
        asked.append(("gene", symbol, taxon))
        return ["3.1.1.1"]

    result = resolve_enzyme_name("CES1X", None, uniprot=protein, gene=gene)
    assert result.ec == "3.1.1.1" and result.isoform == "CES1X" and result.organism == "Homo sapiens"
    assert asked == [("protein", "CES1X"), ("gene", "CES1X", "9606")], "human by default, after the protein name"
    assert any("Homo sapiens" in n for n in result.notes("CES1X"))


def test_a_gene_with_several_ecs_is_refused_unless_it_is_a_p450_under_the_unspecific_monooxygenase():
    def nothing(name):
        return []

    with pytest.raises(NameNotResolved) as raised:
        resolve_enzyme_name("FOO1X", "human", uniprot=nothing, gene=lambda s, t: ["1.1.1.1", "1.1.1.2"])
    assert raised.value.kind == "ambiguous"
    p450 = resolve_enzyme_name("CYP99Z9", "mouse", uniprot=nothing,
                               gene=lambda s, t: ["1.14.14.55", "1.14.14.1"])
    assert p450.ec == "1.14.14.1" and p450.organism is None
    assert any("BRENDA files cytochrome P450 kinetics there" in n for n in p450.notes("CYP99Z9"))


def test_the_gene_query_is_exact_human_and_reviewed(monkeypatch):
    import sys

    sys.path.insert(0, str(REPO / "Tests"))
    import enzyme_lookup

    sent = {}

    class Answer:
        def raise_for_status(self):
            return None

        def json(self):
            return {"results": [{"proteinDescription": {"recommendedName": {"ecNumbers": [{"value": "1.14.14.1"}]}}}]}

    def fake_get(url, params=None, timeout=None):
        sent.update(params)
        return Answer()

    monkeypatch.setattr(enzyme_lookup, "retry_get", fake_get)
    assert enzyme_lookup.fetch_ec_numbers_by_gene("CYP2B6") == ["1.14.14.1"]
    assert sent["query"] == "gene_exact:CYP2B6 AND reviewed:true AND organism_id:9606"
    assert enzyme_lookup.fetch_ec_numbers_by_gene("hexokinase on glucose") == [], "a sentence is never sent"


def test_a_point_mutation_is_set_aside_and_said_to_be_not_modelled():
    assert split_mutation("IDH1 R132H") == ("IDH1", ("R132H",))
    assert split_mutation("hexokinase") == ("hexokinase", ())
    result = resolve_enzyme_name("IDH1 R132H")
    assert result.ec == "1.1.1.42" and result.isoform == "IDH1"
    assert any("R132H is a mutant, and mutants are not modelled" in n for n in result.notes("IDH1 R132H"))


# ---------------------------------------------------------------------------
# The sentence
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("text, ec, isoform, organism, assumed", [
    ("human HK2 on glucose", "2.7.1.1", "HK2", "Homo sapiens", False),
    ("Michaelis-Menten kinetics of human HK2 on glucose", "2.7.1.1", "HK2", "Homo sapiens", False),
    ("CYP2B6 with a competitive inhibitor Michaelis-Menten", "1.14.14.1", "CYP2B6", "Homo sapiens", True),
    ("CYP3A4 metabolising midazolam", "1.14.14.1", "CYP3A4", "Homo sapiens", True),
    ("LDHA with pyruvate in human", "1.1.1.27", "LDHA", "Homo sapiens", False),
    ("COX-2 inhibited by celecoxib", "1.14.99.1", "PTGS2", "Homo sapiens", True),
    ("MAO-B inhibited by selegiline", "1.4.3.4", "MAOB", "Homo sapiens", True),
    ("PTP1B with a competitive inhibitor", "3.1.3.48", "PTPN1", "Homo sapiens", True),
    ("angiotensin-converting enzyme inhibited by captopril", "3.4.15.1", None, None, False),
    ("HIV-1 protease with a competitive inhibitor", "3.4.23.16", None, "Human immunodeficiency virus 1", True),
    ("beta lactamase TEM-1 with ampicillin", "3.5.2.6", "TEM-1", None, False),
    ("acetylcholinestrase with acetylcholine", "3.1.1.7", None, None, False),
])
def test_the_names_from_the_baseline_are_read_from_a_sentence(text, ec, isoform, organism, assumed):
    reading = read_sentence(text)
    assert (reading.ec, reading.isoform, reading.organism, reading.organism_assumed) == (ec, isoform, organism, assumed)
    assert reading.ambiguity is None and not reading.other_enzymes
    if assumed:
        assert "Your description names no organism" in reading.organism_note()
    if isoform:
        assert f"isoform {isoform}" in reading.enzyme_note()


def test_an_organism_flag_is_never_overridden_by_one_a_symbol_implies():
    reading = read_sentence("CYP2B6 with bupropion", organism="Rattus norvegicus")
    assert reading.organism is None and not reading.organism_assumed


def test_the_misspelt_enzyme_in_a_sentence_is_said():
    reading = read_sentence("acetylcholinestrase with acetylcholine")
    assert "Read 'acetylcholinestrase' as acetylcholinesterase (spelling)" in reading.enzyme_note()
    assert reading.substrate_candidates == ("acetylcholine",)


@pytest.mark.parametrize("text, inhibitor", [
    ("angiotensin-converting enzyme inhibited by captopril", "captopril"),
    ("xanthine oxidase blocked by allopurinol", "allopurinol"),
    ("acetylcholinesterase inhibition in the presence of donepezil", "donepezil"),
    ("acetylcholinesterase with the inhibitor donepezil", "donepezil"),
    ("competitive inhibition of acetylcholinesterase by tacrine", "tacrine"),
])
def test_the_inhibitor_phrases_people_write_are_read(text, inhibitor):
    reading = read_sentence(text)
    assert reading.inhibitor_text == inhibitor, reading
    assert inhibitor not in reading.substrate_candidates


def test_an_inhibitor_of_an_enzyme_is_not_a_compound_called_the_enzyme():
    assert read_sentence("ace inhibitor").inhibitor_text is None
    assert read_sentence("a hexokinase inhibitor").inhibitor_text is None


def test_a_bare_with_is_only_a_possible_inhibitor_for_the_caller_to_decide():
    reading = read_sentence("dihydrofolate reductase with methotrexate in E. coli")
    assert reading.inhibitor_text is None and reading.possible_inhibitor_text == "methotrexate"
    assert reading.substrate_candidates[0] == "methotrexate", "still a substrate candidate; BRENDA decides"
    assert read_sentence("hexokinase inhibited by glucose 6-phosphate with glucose").possible_inhibitor_text is None


@pytest.mark.parametrize("text, candidate", [
    ("simulate trypsin cleaving BAPNA", "BAPNA"),
    ("CYP3A4 metabolising midazolam", "midazolam"),
    ("alkaline phosphatase hydrolysing pNPP", "pNPP"),
    ("hexokinase phosphorylating glucose", "glucose"),
    ("alcohol dehydrogenase oxidizing ethanol", "ethanol"),
    ("lactate dehydrogenase reducing pyruvate in human", "pyruvate"),
    ("hexokinase turning over glucose", "glucose"),
    ("trypsin acting on BAEE", "BAEE"),
])
def test_a_verb_is_never_glued_onto_the_substrate(text, candidate):
    reading = read_sentence(text)
    assert reading.substrate_candidates and reading.substrate_candidates[0] == candidate, reading.substrate_candidates


@pytest.mark.parametrize("text", ["HIV-1 protease with a competitive inhibitor",
                                  "hexokinase from Escherichia coli K-12 MG1655",
                                  "IDH1 R132H"])
def test_a_virus_strain_or_mutation_tag_is_never_a_substrate(text):
    reading = read_sentence(text)
    for tag in ("HIV-1", "K-12", "MG1655", "R132H"):
        assert tag not in reading.substrate_candidates, (text, reading.substrate_candidates)


def test_a_mutation_after_the_enzyme_is_said_to_be_not_modelled():
    reading = read_sentence("IDH1 R132H")
    assert reading.ec == "1.1.1.42" and reading.mutations == ("R132H",)
    assert "mutants are not modelled" in reading.enzyme_note()


def test_a_substrate_abbreviation_is_never_read_as_an_enzyme():
    """FBP is fructose 1,6-bisphosphatase's abbreviation and fructose 1,6-bisphosphate's: in a sentence it is
    the compound."""
    reading = read_sentence("PFK with FBP")
    assert reading.ec == "2.7.1.11" and not reading.other_enzymes
    assert "FBP" in reading.substrate_candidates


def test_guinea_pig_is_never_pig():
    reading = read_sentence("guinea pig trypsin")
    assert reading.organism == "Cavia porcellus"


# ---------------------------------------------------------------------------
# Substrate abbreviations, against what BRENDA lists
# ---------------------------------------------------------------------------

#: The spellings BRENDA's trypsin page (EC 3.4.21.4) lists, with their Km row counts, 2026-11-11.
TRYPSIN = {"N-benzoyl-DL-arginine 4-nitroanilide": 5, "Nalpha-benzoyl-DL-arginine-4-nitroanilide": 3,
           "Nalpha-benzoyl-DL-arginine 4-nitroanilide": 1, "benzoyl-L-arginine-p-nitroanilide": 16,
           "Nalpha-benzoyl-L-arginine ethyl ester": 1, "N-alpha-benzoyl-L-arginine ethyl ester": 3,
           "tosyl-Arg methyl ester": 6}


def test_bapna_is_the_dl_compound_under_its_best_measured_spelling():
    match = match_substrate(["BAPNA"], TRYPSIN)
    assert match.name == "N-benzoyl-DL-arginine 4-nitroanilide" and match.abbreviation == "BAPNA"
    assert "BAPNA" in match.note()
    assert match_substrate(["L-BAPNA"], TRYPSIN).name == "benzoyl-L-arginine-p-nitroanilide"
    assert match_substrate(["BAEE"], TRYPSIN).name == "N-alpha-benzoyl-L-arginine ethyl ester"


def test_an_abbreviation_matches_only_a_name_brenda_lists():
    assert match_substrate(["ONPG"], ["2-nitrophenyl beta-D-galactopyranoside", "lactose"]).name == \
        "2-nitrophenyl beta-D-galactopyranoside"
    assert match_substrate(["pNPP"], ["4-nitrophenyl phosphate", "p-nitrophenyl phosphate"]).name == \
        "4-nitrophenyl phosphate"
    assert match_substrate(["PEP"], ["phosphoenolpyruvate", "ADP"]).name == "phosphoenolpyruvate"
    assert match_substrate(["ATCh"], ["acetylthiocholine iodide", "butyrylthiocholine"]).name == \
        "acetylthiocholine iodide"
    assert match_substrate(["ONPG"], ["lactose"]).name is None, "nothing BRENDA lists: nothing taken"


def test_every_expansion_is_one_compound_per_group():
    for key, groups in SUBSTRATE_ABBREVIATIONS.items():
        assert groups and all(groups), key
        assert key == key.lower() and key.isalnum(), key


def test_the_recorded_hexokinase_page_gives_g6p_nothing_and_glucose_d_glucose():
    """On the recorded BRENDA page for EC 2.7.1.1 (human), D-glucose has Km rows and glucose 6-phosphate does
    not: "G6P" in a hexokinase sentence takes no substrate, and "glucose" takes D-glucose."""
    from caterva.checkout import literature_module

    client = literature_module("brenda_client")
    html = gzip.decompress((REPO / "Tests/fixtures/recorded/brenda_2.7.1.1.html.gz").read_bytes()).decode(
        "utf-8", errors="replace")
    rows = client.parse_brenda_km_html(html, "2.7.1.1", [], "Homo sapiens", require_substrate_match=False)
    counts = {}
    for row in rows:
        counts[row.substrate] = counts.get(row.substrate, 0) + 1
    assert "D-glucose" in counts
    assert match_substrate(["glucose"], counts).name == "D-glucose"
    assert match_substrate(["G6P"], counts).name is None
    reading = read_sentence("human HK2 on glucose")
    assert match_substrate(reading.substrate_candidates, counts).name == "D-glucose"


# ---------------------------------------------------------------------------
# Review of the branch (2026-11-11): what a name implies is claimed only where
# it is used, and a P450 row is read as the P450 it names
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("commentary, isoform", [
    # The live BRENDA page for EC 1.14.14.1 writes which P450 a fenthion Km
    # measured as a bare name, with no "isoform" before it.
    ("CYP2C19, at pH 7.4 and 37°C", "CYP2C19"),
    ("CYP3A4, desulfuration by recombinant human CYPs to fenthion-oxon", "CYP3A4"),
    ("complex POR-CYP1A1, pH 7.5, 37°C", "CYP1A1"),
    ("recombinant enzyme CYP2D6", "CYP2D6"),
    ("CYP2C9*1, pH 7.4", "CYP2C9"),
    ("cytochrome P450 3A4", "CYP3A4"),
    ("desulfuration by recombinant human CYPs to fenthion-oxon", None),
])
def test_a_p450_row_is_read_as_the_p450_it_names(commentary, isoform):
    from caterva.bind.core import read_isoform

    assert read_isoform(commentary) == isoform


def test_a_cyp2c19_row_is_never_taken_for_cyp2b6():
    """`compose --subject CYP2B6` sets --isoform CYP2B6. A row naming CYP2C19 must rank as ANOTHER isoform's
    (refused), not as a row naming none ("whether it measured CYP2B6 is unknown"), which it read as before."""
    from caterva.bind.core import same_isoform
    from caterva.compose.ki_mode import Reading, isoform_rank

    assert not same_isoform("CYP2B6", "CYP2C19") and not same_isoform("CYP3A4", "CYP3A5")
    assert same_isoform("CYP3A4", "P450 3A4") and same_isoform("cyp2b6", "CYP2B6")
    row = Reading(None, None, "CYP2C19", "CYP2C19, at pH 7.4 and 37°C")
    assert isoform_rank(row, "CYP2B6") is None, "another isoform's row is never a fallback"
    assert isoform_rank(Reading(None, None, "CYP2B6", "CYP2B6"), "CYP2B6") == 0


def test_a_command_that_takes_only_the_ec_number_never_claims_the_isoform_or_organism_was_searched():
    """`bind --ec`, `rates --ec`, `fep --ec` and `structure --subject` use only the EC number. Their notes said
    "so Homo sapiens was searched" and "the constants are taken from BRENDA rows that name it" while they
    searched every organism and every P450. Now they say what the name implies and the flag that applies it."""
    from caterva.enzymes.ec_option import read_ec_option

    option = read_ec_option("CYP2B6", None, uniprot=None)
    assert option.ec == "1.14.14.1"
    text = " ".join(option.notes)
    assert "was searched" not in text and "constants are taken" not in text, text
    assert "--isoform CYP2B6" in text and '--organism "Homo sapiens"' in text, text


def test_compose_claims_the_isoform_and_organism_only_when_it_applied_them(monkeypatch):
    from dataclasses import dataclass
    from types import SimpleNamespace

    import caterva.enzymes.policy as policy
    from caterva.compose.__main__ import read_subject

    monkeypatch.setattr(policy, "literature_uniprot_lookup", lambda *a, **k: None)

    @dataclass(frozen=True)
    class Model:
        subject: str
        ec_number: object = None

    args = SimpleNamespace(subject="CYP2B6", organism=None, isoform=None)
    model, note, refusal, _ = read_subject(Model("CYP2B6"), args)
    assert refusal is None and model.subject == "1.14.14.1"
    assert (args.isoform, args.organism) == ("CYP2B6", "Homo sapiens")
    assert "constants are taken from BRENDA rows that name it" in note and "Homo sapiens was searched" in note

    args = SimpleNamespace(subject="CYP2B6", organism="Homo sapiens", isoform="CYP3A4")
    _, note, _, _ = read_subject(Model("CYP2B6"), args)
    assert args.isoform == "CYP3A4", "a flag wins"
    assert "constants are taken from BRENDA rows that name it" not in note, note
    assert "--isoform CYP3A4 was used, because a flag wins" in note, note


def test_an_abbreviated_binomial_keeps_the_strain_typed_after_it():
    from caterva.compose.organisms import normalise_organism

    assert normalise_organism("E. coli BL21") == (
        "Escherichia coli BL21", "Read --organism 'E. coli BL21' as Escherichia coli BL21.")
    assert normalise_organism("HIV-1")[0] == "Human immunodeficiency virus 1"
    assert normalise_organism("Mus musculus C57BL/6") == ("Mus musculus C57BL/6", None)
