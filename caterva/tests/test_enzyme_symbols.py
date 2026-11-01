"""The finder's abbreviation and gene-symbol rules, on the real index and the real symbol table.

Every case here is a defect the review of 2026-10-03 found when it ran 169 names a
lab types through the finder (676 outcomes): a name RESOLVED to a different
enzyme, a recommendation made over the enzyme the organism actually has, a gene
symbol that returned nothing because it matched only UniProt entry-name
mnemonics. Each test below fails on the finder as it was and passes on the
rules finder.py documents. Nothing is mocked: the committed ExPASy ENZYME index
and the committed symbol table (data/symbols.json, built from UniProtKB by
scripts/build_enzyme_symbols.py) are what is read.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from caterva.enzymes import Ambiguous, Resolved, find, load_index, organism_code, resolve
from caterva.enzymes.finder import TIER_ABBREVIATION, TIER_SYMBOL, is_abbreviation
from caterva.enzymes.symbols import ABBREVIATION, GENE, SYMBOLS_PATH, compact_key, load_symbols


def ecs(candidates):
    return [c.ec for c in candidates]


# --- H1: a short abbreviation or symbol never resolves by itself -------------------------


@pytest.mark.parametrize(
    "name, right, wrong",
    [
        ("HK1", "2.7.1.1", "2.7.13.1"), ("HK2", "2.7.1.1", "2.7.13.1"), ("HK3", "2.7.1.1", "2.7.13.1"),
        ("SDH", "1.3.5.1", "1.1.99.32"), ("NOS", "1.14.13.39", "1.5.1.19"), ("AST", "2.6.1.1", "2.3.1.109"),
        ("SYK", "2.7.10.2", "6.1.1.6"), ("PEPC", "4.1.1.31", "3.4.23.3"), ("AK", "2.7.4.3", "2.7.2.1"),
    ],
)
def test_the_wrong_resolutions_the_review_found_are_choices_now(name, right, wrong):
    """Human, as in the review: HK1 resolved to a histidine kinase, SDH to L-sorbose 1-dehydrogenase, NOS to
    D-nopaline dehydrogenase, AST to arginine N-succinyltransferase, SYK to lysine--tRNA ligase (SYK_HUMAN is a
    mnemonic), PEPC to gastricsin, AK to acetate kinase."""
    result = resolve(name, "human")
    assert isinstance(result, Ambiguous), f"{name} resolved to EC {getattr(result, 'ec', None)}"
    assert result.confirm_only and result.recommended is None
    assert right in ecs(result.candidates)
    assert ecs(result.candidates).index(right) == 0, "the enzyme the table lists for it comes first"
    stray = [c for c in result.candidates if c.ec == wrong]
    assert all(c.partial or c.tier > TIER_ABBREVIATION for c in stray), "the wrong one is not offered as a reading of it"


def test_a_confirmed_abbreviation_is_an_exact_alternative_name_the_table_lists_for_that_enzyme_alone():
    for name, ec in [("GAPDH", "1.2.1.12"), ("ACE", "3.4.15.1"), ("BACE1", "3.4.23.46"), ("PKA", "2.7.11.11"),
                     ("PKC", "2.7.11.13"), ("HDAC", "3.5.1.98"), ("RNase A", "4.6.1.18")]:
        for organism in ("human", "yeast", None):
            result = resolve(name, organism)
            assert isinstance(result, Resolved) and result.ec == ec, (name, organism)
            assert result.candidate.confirmed and result.candidate.abbreviation
    # The same exact name, but shared with other enzymes by the table, is a choice.
    assert isinstance(resolve("NOS", "human"), Ambiguous)
    assert isinstance(resolve("SDH", "human"), Ambiguous)


def test_a_symbol_the_table_lists_is_never_resolved_even_for_one_enzyme():
    for name in ("COMT", "PARP1", "SOD", "ACHE", "DHFR", "LDHA", "GCK", "DPP4", "CYP2C9", "MMP9"):
        result = resolve(name, "human")
        assert isinstance(result, Ambiguous) and result.confirm_only and len(result.candidates) >= 1, name


def test_the_right_list_still_resolves_and_the_symbols_in_it_are_offered_for_confirmation():
    """The names the review found right: kept. Full names resolve; abbreviations resolve only when confirmed;
    a bare symbol (SOD, COMT, PARP1) is offered, one candidate, for a click."""
    full = {"trypsin": "3.4.21.4", "thrombin": "3.4.21.5", "cathepsin B": "3.4.22.1", "caspase-3": "3.4.22.56",
            "beta-lactamase": "3.5.2.6", "lysozyme": "3.2.1.17", "hexokinase": "2.7.1.1",
            "pyruvate kinase": "2.7.1.40", "catalase": "1.11.1.6", "acetylcholinesterase": "3.1.1.7",
            "monoamine oxidase": "1.4.3.4", "creatine kinase": "2.7.3.2", "GAPDH": "1.2.1.12", "ACE": "3.4.15.1",
            "BACE1": "3.4.23.46", "PKA": "2.7.11.11", "PKC": "2.7.11.13", "HDAC": "3.5.1.98"}
    for organism in ("human", "mouse", "yeast", "E. coli"):
        for name, ec in full.items():
            result = resolve(name, organism)
            assert isinstance(result, Resolved) and result.ec == ec, (name, organism)
    for name, ec in {"SOD": "1.15.1.1", "COMT": "2.1.1.6", "PARP1": "2.4.2.30"}.items():
        result = resolve(name, "human")
        assert isinstance(result, Ambiguous) and ecs(result.candidates) == [ec], name


def test_a_unique_exact_alternative_name_that_is_a_full_name_resolves():
    for name, ec in [("lipase", "3.1.1.3"), ("pepsin", "3.4.23.1"), ("triosephosphate isomerase", "5.3.1.1"),
                     ("enolase", "4.2.1.11"), ("urease", "3.5.1.5"), ("proteinase K", "3.4.21.64")]:
        result = resolve(name, "human")
        assert isinstance(result, Resolved) and result.ec == ec, name
        assert not result.candidate.abbreviation


def test_an_abbreviation_is_a_name_that_has_no_run_of_four_lower_case_letters():
    assert all(is_abbreviation(t) for t in ("GAPDH", "HK2", "RNase A", "COX-2", "CYP2C9", "RuBisCO", "Taq"))
    assert not any(is_abbreviation(t) for t in ("lipase", "pepsin", "ATP synthase", "trypsin", "HIV protease"))


# --- H1(b): a UniProt entry-name mnemonic is not a gene symbol ---------------------------


def test_the_part_of_an_entry_name_before_the_underscore_is_not_read_as_a_gene_symbol():
    """SYK_HUMAN is a lysine--tRNA ligase; the SYK gene's protein is KSYK_HUMAN. The old finder listed
    EC 6.1.1.6 for SYK because of the mnemonic."""
    index = load_index()
    assert any(p.entry_name == "SYK_HUMAN" for p in index.get("6.1.1.6").proteins["HUMAN"])
    result = resolve("SYK", "human")
    assert ecs(result.candidates) == ["2.7.10.2"], "only the gene SYK's enzyme, from the symbol table"
    # A mnemonic the table does not know is listed for the organism asked about, as a mnemonic, never resolved.
    listed = find("NAGA", "human", limit=None)
    mnemonic = [c for c in listed if c.via == "mnemonic"]
    assert mnemonic and all(c.partial and c.tier == TIER_SYMBOL for c in mnemonic)
    assert "NAGA_HUMAN" in mnemonic[0].why and "not always the gene symbol" in mnemonic[0].why
    assert not any("NAGA_MOUSE" in c.why for c in listed), "only the organism asked about"
    assert isinstance(resolve("NAGA", "human"), Ambiguous)
    assert all(c.via != "mnemonic" for c in find("NAGA", None, limit=None)), "no organism, no entry name is read"


def test_a_mnemonic_hit_is_never_recommended_and_its_prefix_is_not_a_symbol():
    assert find("HXK", "human") == [] or all(c.via != "mnemonic" for c in find("HXK", "human"))
    for c in find("ACES", "human"):
        assert c.via == "mnemonic" and c.partial


# --- H1(c): an enzyme the organism lacks is never resolved over one it has ---------------


def test_glycogen_synthase_is_not_the_bacterial_starch_synthase_for_a_human():
    human = resolve("glycogen synthase", "human")
    assert isinstance(human, Ambiguous) and "2.4.1.11" in ecs(human.candidates)
    assert "lists no human protein" in human.reason and "GYS1" in human.reason
    ranked = {c.ec: c for c in find("glycogen synthase", "human", limit=None)}
    assert ranked["2.4.1.11"].has_organism_protein and not ranked["2.4.1.21"].has_organism_protein
    # E. coli has the starch synthase and no glycogen(starch) synthase: there it is the right answer.
    ecoli = resolve("glycogen synthase", "E. coli")
    assert isinstance(ecoli, Resolved) and ecoli.ec == "2.4.1.21"
    yeast = resolve("glycogen synthase", "yeast")
    assert isinstance(yeast, Ambiguous) and "2.4.1.11" in ecs(yeast.candidates)


def test_an_accepted_name_still_resolves_for_an_organism_that_lacks_the_enzyme():
    """"subtilisin" is the bacterial enzyme whatever else mentions the word."""
    result = resolve("subtilisin", "human")
    assert isinstance(result, Resolved) and result.ec == "3.4.21.62"


# --- H3: recommendations are made across the whole list ----------------------------------


def test_adh_is_not_recommended_to_be_a_glutathione_dehydrogenase_and_offers_alcohol_dehydrogenase():
    for organism in ("human", "mouse", "yeast", "E. coli"):
        result = resolve("ADH", organism)
        assert isinstance(result, Ambiguous) and result.recommended is None, organism
        assert ecs(result.candidates)[0] == "1.1.1.1", organism
    human = {c.ec: c for c in find("ADH", "human", limit=None)}
    assert human["1.1.1.1"].organism_protein_count == 5 and human["1.1.1.1"].via == "abbreviation"


def test_cox_in_e_coli_does_not_recommend_heme_o_synthase():
    result = resolve("COX", "E. coli")
    assert result.recommended is None
    assert "2.5.1.141" not in ecs(result.candidates) or all(c.via != "abbreviation" for c in result.candidates if c.ec == "2.5.1.141")


def test_ribonuclease_a_offers_pancreatic_ribonuclease_and_not_poly_a_specific_ribonuclease():
    """The single letter A matched inside poly(A)-specific ribonuclease and recommended it."""
    listed = find("ribonuclease A", "human", limit=None)
    assert ecs(listed) == ["4.6.1.18"]
    assert "3.1.13.4" not in ecs(find("ribonuclease A", None, limit=None))
    assert isinstance(resolve("RNase A", "human"), Resolved)


def test_a_single_letter_or_a_short_query_must_be_a_word_of_the_name_not_something_in_a_parenthesis():
    assert "3.1.13.4" not in ecs(find("ribonuclease A", limit=None))
    assert "3.1.13.4" in ecs(find("poly(A)-specific ribonuclease", limit=None))
    assert "3.1.13.4" in ecs(find("poly A specific ribonuclease", limit=None))


def test_gpi_in_human_offers_glucose_6_phosphate_isomerase_first_and_recommends_nothing():
    result = resolve("GPI", "human")
    assert result.recommended is None and ecs(result.candidates)[0] == "5.3.1.9"
    pld = [c for c in result.candidates if c.ec == "3.1.4.50"]
    assert pld and all(c.partial for c in pld), "GPI-phospholipase D is only a fragment match"


def test_a_recommendation_needs_one_listed_enzyme_with_the_organisms_protein_across_the_whole_list():
    one = resolve("lactate dehydrogenase", "human")
    with_protein = [c.ec for c in one.candidates if c.has_organism_protein]
    assert one.recommended is not None and with_protein == [one.recommended.ec] == ["1.1.1.27"]
    citrate = resolve("citrate synthase", "human")
    assert citrate.recommended is None, "ATP citrate synthase also has human proteins, further down the list"
    assert [c.ec for c in citrate.candidates if c.has_organism_protein] != []
    for name in ("GPI", "ADH", "HK1", "COX"):
        assert resolve(name, "human").recommended is None, "an abbreviation is not evidence about which enzyme was meant"


def test_the_count_in_the_reason_agrees_with_what_is_listed():
    result = resolve("lactate dehydrogenase", "human")
    listed = len(find("lactate dehydrogenase", "human", limit=None))
    assert f"{listed} enzymes match" in result.reason and "these 2 match best" in result.reason
    tied = resolve("aldehyde reductase", "human")
    total = len(find("aldehyde reductase", "human", limit=None))
    assert total > 2 and tied.reason == f"{total} enzymes match 'aldehyde reductase'; these 2 match best"
    pair = resolve("L-lactate dehydrogenase (cytochrome)", "human")
    assert isinstance(pair, Resolved) or "names" in pair.reason or "match" in pair.reason


# --- M4, M5, M6: symbols and reach -------------------------------------------------------


@pytest.mark.parametrize(
    "name, organism, ec",
    [
        ("ACHE", "human", "3.1.1.7"), ("BCHE", "human", "3.1.1.8"), ("DHFR", "human", "1.5.1.3"), ("TS", "human", "2.1.1.45"),
        ("HMGCR", "human", "1.1.1.34"), ("MAOA", "human", "1.4.3.4"), ("MAOB", "human", "1.4.3.4"),
        ("PKM2", "human", "2.7.1.40"), ("SOD1", "human", "1.15.1.1"), ("CA2", "human", "4.2.1.1"),
        ("CA II", "human", "4.2.1.1"), ("PTP1B", "human", "3.1.3.48"), ("PK", "human", "2.7.1.40"), ("CK", "human", "2.7.3.2"),
        ("IDH1", "human", "1.1.1.42"), ("IDH2", "human", "1.1.1.42"), ("ENO1", "human", "4.2.1.11"),
        ("GCK", "human", "2.7.1.1"), ("HK", "human", "2.7.1.1"), ("LDHA", "human", "1.1.1.27"), ("LDH-A", "human", "1.1.1.27"),
        ("DPP4", "human", "3.4.14.5"), ("DPP-4", "human", "3.4.14.5"), ("CYP2C9", "human", "1.14.14.1"),
        ("HIV protease", "human", "3.4.23.16"), ("HIV-1 protease", None, "3.4.23.16"),
        ("glutathione S-transferase", "human", "2.5.1.18"), ("T4 lysozyme", "human", "3.2.1.17"),
        ("Taq polymerase", None, "2.7.7.7"), ("DNA polymerase I", None, "2.7.7.7"), ("HRP", "human", "1.11.1.7"),
        ("horseradish peroxidase", None, "1.11.1.7"), ("hexokinase 2", "human", "2.7.1.1"),
        ("hexokinase II", "human", "2.7.1.1"), ("ALDOB", "human", "4.1.2.13"), ("aldolase B", "human", "4.1.2.13"),
        ("GSTP1", "human", "2.5.1.18"), ("PDE5A", "human", "3.1.4.35"), ("CASP3", "human", "3.4.22.56"),
        ("HDAC8", "human", "3.5.1.98"), ("F10", "human", "3.4.21.6"), ("F2", "human", "3.4.21.5"),
        ("EGFR", "human", "2.7.10.1"), ("SRC", "human", "2.7.10.2"), ("JAK2", "human", "2.7.10.2"),
        ("MAPK1", "human", "2.7.11.24"), ("PIK3CA", "human", "2.7.1.137"), ("CDK2", "human", "2.7.11.22"),
        ("NOS3", "human", "1.14.13.39"), ("ACE2", "human", "3.4.17.23"), ("SDHA", "human", "1.3.5.1"),
        ("MDH2", "human", "1.1.1.37"), ("ACLY", "human", "2.3.3.8"), ("CS", "human", "2.3.3.1"),
        ("TPI1", "human", "5.3.1.1"), ("PGK1", "human", "2.7.2.3"), ("PFKM", "human", "2.7.1.11"),
        ("COMT", "human", "2.1.1.6"), ("PARP1", "human", "2.4.2.30"), ("BACE1", "human", "3.4.23.46"),
    ],
)
def test_the_symbols_and_names_a_lab_types_offer_the_right_enzyme_as_a_candidate(name, organism, ec):
    result = resolve(name, organism)
    candidates = [result.ec] if isinstance(result, Resolved) else ecs(result.candidates)
    assert ec in candidates, f"{name} in {organism} offers {candidates[:6]}"


def test_a_symbol_is_never_offered_across_organisms():
    """IDH1 is the NADP-dependent enzyme in human and mouse, the NAD-dependent one in yeast, and a bacterium has
    no gene of that name in the table. The yeast entry is not a human candidate and the reverse."""
    human, mouse = ecs(resolve("IDH1", "human").candidates), ecs(resolve("IDH1", "mouse").candidates)
    yeast = ecs(resolve("IDH1", "yeast").candidates)
    assert human == mouse == ["1.1.1.42"] and yeast == ["1.1.1.41"]
    assert "1.1.1.41" not in ecs(find("IDH1", "human", limit=None))
    ecoli = resolve("IDH1", "E. coli")
    assert isinstance(ecoli, Ambiguous) and not ecoli.candidates
    assert "human, mouse, yeast but not for E. coli K-12" not in ecoli.reason or "not for E. coli" in ecoli.reason
    assert "gene-symbol table lists 'IDH1' for" in ecoli.reason and "none is offered" in ecoli.reason
    # With no organism, each reading says which organism's gene it is.
    unasked = find("IDH1", None, limit=None)
    assert {c.ec for c in unasked} == {"1.1.1.41", "1.1.1.42"}
    assert any("human, mouse gene symbol" in c.why for c in unasked) and any("yeast gene symbol" in c.why for c in unasked)


def test_nonsense_returns_no_match_not_a_suggestion_from_one_shared_character_class():
    """"ethanol dehydrogenase" is not "methanol dehydrogenase" mistyped, "CYP2C9" is not a fenbendazole
    monooxygenase's symbol one edit away, and "HIV protease" is not "NIa protease"."""
    for name, organism in [("ethanol dehydrogenase", "human"), ("CYP2D6", "human"), ("zzqx protein", None),
                           ("DHFR E coli", "human"), ("HIV reverse transcriptase", "human")]:
        result = resolve(name, organism)
        assert isinstance(result, Ambiguous) and not result.candidates, (name, ecs(result.candidates))
    assert ecs(resolve("CYP2C9", "mouse").candidates) == [] or all(
        c.partial for c in resolve("CYP2C9", "mouse").candidates)
    for typo, ec in [("hexokinse", "2.7.1.1"), ("lactat dehydrogenase", "1.1.1.27"), ("acetylcholinesteras", "3.1.1.7")]:
        assert ec in ecs(find(typo, "human", limit=None))
    # A digit is never a typo, and a short word is exact only.
    assert find("CYP2C8", None, limit=None) == [] or all(c.tier != 9 for c in find("CYP2C8", None, limit=None))


# --- the one organism normaliser ---------------------------------------------------------


@pytest.mark.parametrize(
    "typed, code",
    [("human", "HUMAN"), ("Homo sapiens", "HUMAN"), ("H. sapiens", "HUMAN"), ("h.sapiens", "HUMAN"), ("HUMAN", "HUMAN"),
     ("mouse", "MOUSE"), ("Mus musculus", "MOUSE"), ("yeast", "YEAST"), ("S. cerevisiae", "YEAST"),
     ("Saccharomyces cerevisiae", "YEAST"), ("baker's yeast", "YEAST"), ("E. coli", "ECOLI"), ("e.coli", "ECOLI"),
     ("E. coli K-12", "ECOLI"), ("Escherichia coli K12", "ECOLI"), ("escherichia coli", "ECOLI"),
     ("B. subtilis", "BACSU"), ("fission yeast", "SCHPO")],
)
def test_organism_spellings_are_read_by_one_normaliser(typed, code):
    assert organism_code(typed) == code


def test_a_name_that_is_not_one_organism_is_not_guessed():
    for typed in ("monkey", "bacteria", "E. coli BL21", "", None, "Thermus aquaticus"):
        assert organism_code(typed) is None


def test_e_coli_means_k_12_and_the_caution_says_so():
    result = resolve("glucokinase", "E. coli")
    assert result.candidate.has_organism_protein
    # An enzyme with no K-12 protein: the caution names the strain it counted, not "E. coli".
    result = resolve("glucokinase", "human")
    assert result.cautions and "lists no human protein" in result.cautions[0]
    from caterva.enzymes.finder import _cautions
    from caterva.enzymes.index import ORGANISM_SCOPE

    chosen = find("acetoin dehydrogenase", "E. coli", limit=1)
    assert ORGANISM_SCOPE["ECOLI"].startswith("E. coli K-12")
    text = _cautions(load_index(), chosen[0], chosen)
    if not chosen[0].has_organism_protein:
        assert "E. coli K-12 (UniProt code ECOLI; proteins of other E. coli strains are filed under other codes" in text[0]


# --- the table itself --------------------------------------------------------------------


def test_the_symbol_table_cites_a_source_on_every_row_and_every_ec_is_an_active_enzyme():
    table = json.loads(SYMBOLS_PATH.read_text(encoding="utf-8"))
    index = load_index()
    assert table["fetched"] and table["sources"]["uniprot"] and table["sources"]["enzyme"].startswith("ExPASy ENZYME release")
    assert len(table["genes"]) >= 150 and len(table["abbreviations"]) >= 50
    for row in table["genes"]:
        assert row["source"].startswith("UniProtKB "), row["symbol"]
        for code, entry in row["organisms"].items():
            assert code in ("HUMAN", "MOUSE", "YEAST", "ECOLI") and entry["accession"] and entry["ecs"], row["symbol"]
            for ec in entry["ecs"]:
                assert index.get(ec) is not None and index.get(ec).status == "active", (row["symbol"], ec)
            listed = {p.accession for e in index.entries.values() for p in e.proteins.get(code, ())}
            assert entry["accession"] in listed, f"{row['symbol']}: {entry['accession']} is not an entry the index lists"
    for row in table["abbreviations"]:
        assert row["source"] and row["meaning"] and row["ecs"], row["symbols"]
        for ec in row["ecs"]:
            assert index.get(ec).status == "active"
            assert index.get(ec).name in row["source"], (row["symbols"], ec)


def test_the_symbol_table_reads_gene_rows_for_the_organism_only_and_abbreviations_for_all():
    table = load_symbols()
    human = table.lookup("HK2", "HUMAN")
    assert {h.kind for h in human} == {GENE, ABBREVIATION} and {h.ec for h in human} == {"2.7.1.1"}
    assert table.lookup("IDH1", "ECOLI") == []
    assert [h.ec for h in table.lookup("IDH1", "YEAST")] == ["1.1.1.41"]
    assert {h.organism for h in table.lookup("IDH1", None)} == {"HUMAN", "MOUSE", "YEAST"}
    assert compact_key("DPP-4") == compact_key("DPP4") == compact_key("dpp 4") == "dpp4"
    assert compact_key("hexokinase type II") == compact_key("hexokinase II")
    assert table.organisms_for("IDH1") == ("HUMAN", "MOUSE", "YEAST")


def test_the_data_files_are_small_and_the_index_is_still_under_three_megabytes():
    from caterva.enzymes.index import INDEX_PATH
    from caterva.enzymes.protein_names import NAMES_PATH

    assert INDEX_PATH.stat().st_size < 3_000_000
    assert NAMES_PATH.stat().st_size < 1_000_000 and SYMBOLS_PATH.stat().st_size < 300_000
