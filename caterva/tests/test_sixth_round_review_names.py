"""The sixth adversarial round of the real-values work (2026-11-13), the
names half: how an enzyme name, a gene symbol or a typo is read, and which
EC number it is taken as (ADR 0182, sixth round).

Offline: the enzyme index, the symbol tables and the protein names file
ship with the package; BRENDA's rows are stand-ins built from the rows the
review quoted (`defaults.table_rows` is replaced), and no page is fetched.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

import caterva.compose.__main__ as cli
from caterva.compose import defaults
from caterva.compose.grammar import UnrecognisedShape
from caterva.enzymes.finder import TIER_TYPO, Ambiguous, Resolved, find, resolve
from caterva.enzymes.sentence import read_sentence


@pytest.fixture(autouse=True)
def _no_page(monkeypatch):
    """Any BRENDA page a test did not stand in for is an error, not a fetch."""
    def refuse(ec):
        raise AssertionError(f"a test fetched BRENDA's page for EC {ec}")
    monkeypatch.setattr(defaults, "_page", refuse)


def _rows(by_key):
    """{(ec, table, organism): [_Row, ...]} -> a `table_rows` stand-in."""
    def table_rows(ec, table, organism):
        return tuple(r for (e, t, o), rows in by_key.items() for r in rows
                     if e == ec and t == table and (organism is None or o == organism))
    return table_rows


def _row(compound, organism, conditions="", **kw):
    return defaults._Row(compound, organism, conditions, **kw)


def _args(**kw):
    base = dict(organism=None, subject=None, isoform=None, substrate=None, inhibitor=None)
    base.update(kw)
    return SimpleNamespace(**base)


# -- NEW-01: "6-phosphogluconate dehydrogenase" -------------------------------------

def test_an_anion_spelling_reads_the_acid_spelling_the_nomenclature_lists():
    """The nomenclature lists "6-phosphogluconic dehydrogenase" (EC 1.1.1.43
    and 1.1.1.44); people type the anion. The refusal offered EC 1.1.1.43
    only, the wrong enzyme for the pentose-phosphate step."""
    found = resolve("6-phosphogluconate dehydrogenase", "Ovis aries")
    assert isinstance(found, Ambiguous)
    assert {"1.1.1.43", "1.1.1.44"} <= {c.ec for c in found.candidates}
    assert "-ic, -ate" in found.reason
    reading = read_sentence("6-phosphogluconate dehydrogenase from sheep liver")
    assert reading.ambiguity is not None and reading.organism == "Ovis aries"


def test_the_sheep_rows_settle_6pgd_as_ec_1_1_1_44(monkeypatch):
    sheep = "Ovis aries"
    monkeypatch.setattr(defaults, "table_rows", _rows({
        ("1.1.1.44", "km", sheep): [_row("6-phospho-D-gluconate", sheep, "wild type enzyme", value=0.028,
                                         reference_id="669487", uniprot="P00349")] * 3}))
    reading = read_sentence("6-phosphogluconate dehydrogenase from sheep liver")
    chosen = cli._enzyme_the_data_singles_out(reading, _args())
    assert chosen is not None and chosen.chosen == "1.1.1.44"


def test_a_phrase_of_a_listed_name_is_not_respelt():
    """"isocitrate dehydrogenase" is a phrase of EC 1.1.1.41's and 1.1.1.42's
    names; "isocitric dehydrogenase" is another name of EC 1.1.1.41 only.
    The respelling must not drop EC 1.1.1.42 from the choice."""
    found = resolve("isocitrate dehydrogenase")
    assert isinstance(found, Ambiguous) and {"1.1.1.41", "1.1.1.42"} <= {c.ec for c in found.candidates}
    assert "-ic, -ate" not in (found.reason or "")


def test_subject_names_the_enzyme_the_reader_could_not_place():
    """The refusal advised "--subject <EC>"; the advised command was refused
    with the same words, because the reader still could not place the name."""
    text = "frobnicase from sheep liver"
    reading = read_sentence(text)
    assert reading.ec is None and not reading.names_enzyme
    with pytest.raises(UnrecognisedShape):
        cli._shape_from(text, reading)
    description, rule, note = cli._shape_from(text, reading, "1.1.1.44")
    assert rule == "michaelis_menten" and "--subject 1.1.1.44 named the enzyme" in note


# -- NEW-02: MurA, a bacterial gene symbol ------------------------------------------

def test_mura_in_e_coli_is_ec_2_5_1_7():
    reading = read_sentence("MurA inhibited by fosfomycin in E. coli")
    assert reading.ec == "2.5.1.7", reading
    assert any("MURA_ECOLI" in n or "gene symbol" in n for n in (reading.how or "",) + tuple(reading.read_notes))


def test_a_bacterial_gene_symbol_is_read_only_as_written():
    """"MurA" and "murA" are the gene; "mura" is a word, and a bacterial
    gene in capitals is not read (E. coli's udp gene is not "UDP")."""
    assert isinstance(resolve("murA", "Escherichia coli"), Resolved)
    assert not (isinstance(resolve("mura", "Escherichia coli"), Resolved))
    assert read_sentence("UDP-glucose with UDP in E. coli").ec != "2.4.2.3"


def test_fosfomycin_is_said_to_be_an_irreversible_inactivator():
    from fallback_logic import IRREVERSIBLE_INHIBITOR

    assert IRREVERSIBLE_INHIBITOR.search("fosfomycin")
    assert IRREVERSIBLE_INHIBITOR.search("phosphomycin")


# -- NEW-14: typos are ranked by the organism's protein ---------------------------

def test_a_typo_is_ranked_by_the_organism_named():
    """"phosphoglucomutse" is one letter from phosphoglucomutase (EC 5.4.2.2,
    rabbit PGM1) and from beta-phosphoglucomutase (EC 5.4.2.6, bacterial).
    The refusal recommended the one with no rabbit protein."""
    found = [c for c in find("phosphoglucomutse", "Oryctolagus cuniculus", limit=None) if c.tier == TIER_TYPO]
    assert found and found[0].ec == "5.4.2.2" and found[0].has_organism_protein


def test_a_five_letter_head_word_typo_is_suggested():
    """"phosphoglycerate kinse" got the shape refusal and no suggestion."""
    reading = read_sentence("phosphoglycerate kinse from yeast")
    assert reading.ambiguity is not None and reading.ambiguity.suggestions_only
    assert reading.ambiguity.candidates[0].ec == "2.7.2.3"
    # One five-letter word alone is never read as a typo.
    assert not [c for c in find("kinse", limit=None) if c.tier == TIER_TYPO]


def test_the_typo_advice_says_when_the_organism_is_what_is_missing(monkeypatch):
    """BRENDA has no rabbit Km row under EC 5.4.2.2: the advised command
    must name an organism that has rows, or it is refused again."""
    yeast = "Saccharomyces cerevisiae"
    monkeypatch.setattr(defaults, "table_rows", _rows({
        ("5.4.2.2", "km", yeast): [_row("alpha-D-glucose 1-phosphate", yeast, "pH 7.5, 30°C")] * 5}))
    reading = read_sentence("phosphoglucomutse from rabbit muscle")
    said = cli._no_candidate_in_the_organism(reading.ambiguity, "Oryctolagus cuniculus")
    assert said is not None
    assert "EC 5.4.2.2 has no Km row in Oryctolagus cuniculus" in said
    assert "Saccharomyces cerevisiae (5 rows)" in said


# -- NEW-15: a gene symbol of one protein under several EC numbers ----------------

def test_akr1c3_is_read_as_one_protein_under_several_ec_numbers():
    found = resolve("AKR1C3")
    assert isinstance(found, Ambiguous) and found.gene == "AKR1C3"
    assert {"1.1.1.188", "1.1.1.357"} <= {c.ec for c in found.candidates}
    assert "P42330" in found.reason
    reading = read_sentence("AKR1C3 with a competitive inhibitor")
    assert reading.ambiguity is not None and reading.ambiguity.gene == "AKR1C3"
    assert reading.enzyme_text == "AKR1C3"


def test_the_rows_naming_the_gene_settle_the_ec_number(monkeypatch):
    human = "Homo sapiens"
    akr = dict(uniprot="P42330")
    monkeypatch.setattr(defaults, "table_rows", _rows({
        ("1.1.1.357", "km", human): [_row("androsterone", human, "pH 7.0, 25°C", **akr)] * 15,
        ("1.1.1.357", "kcat", human): [_row("androsterone", human, "pH 7.0, 25°C", **akr)] * 13,
        ("1.1.1.188", "km", human): [_row("prostaglandin H2", human, "pH 7.0, 37°C", **akr)] * 6,
        ("1.1.1.188", "kcat", human): [_row("prostaglandin H2", human, "pH 7.0, 37°C", **akr)] * 2,
        ("1.1.1.188", "ki", human): [_row("indomethacin", human, "pH 7.0, 37°C", **akr)] * 12}))
    text = "AKR1C3 with a competitive inhibitor"
    reading = read_sentence(text)
    chosen = cli._enzyme_the_gene_rows_single_out(reading, _args(), text)
    assert chosen is not None and chosen.chosen == "1.1.1.188"
    note = chosen.note()
    assert "AKR1C3" in note and "EC 1.1.1.357" in note


def test_a_reagent_spelled_as_a_gene_symbol_does_not_displace_the_enzyme():
    """SDS is a detergent and a human gene symbol (SDHL_HUMAN); lysozyme is
    the enzyme named."""
    reading = read_sentence("lysozyme with SDS")
    assert reading.ec == "3.2.1.17" and reading.ambiguity is None
    assert "SDS" in reading.substrate_candidates, "free to be read as the compound it is"
    # Named alone, the symbol is read: nothing else names an enzyme.
    assert getattr(read_sentence("SDS kinetics").ambiguity, "gene", None) == "SDS"


def test_a_bacterial_gene_in_a_mechanism_does_not_replace_the_mechanism():
    """EnvZ is now read (E. coli's histidine kinase, EC 2.7.13.3); the
    two-component system described is still the shape built, not
    Michaelis-Menten with "two-component system" as the substrate."""
    text = "EnvZ phosphorylating OmpR in E. coli, a two-component system"
    reading = read_sentence(text)
    assert reading.ec == "2.7.13.3"
    _, rule, _ = cli._shape_from(text, reading)
    assert rule == "two_component_system"


def test_muras_twin_rows_are_not_counted_as_the_enzymes():
    """`defaults` withholds a mutant's twin row as the resolver does
    (`row_form.mutant_twins`): the "at pH 8.0" fosfomycin rows of ref 637598
    repeat the C115D mutant's values beside a stated wild-type row."""
    coli = "Escherichia coli"
    rows = (_row("fosfomycin", coli, "wild-type enzyme", value=0.0086, reference_id="637598"),
            _row("fosfomycin", coli, "mutant C115D", value=1.0, reference_id="637598", variant=True),
            _row("fosfomycin", coli, "at pH 8.0", value=1.0, reference_id="637598"),
            _row("fosfomycin", coli, "at pH 6.0", value=5.0, reference_id="637598"))
    marked = defaults._mutant_twins_are_variants(rows, defaults._client())
    assert [r.variant for r in marked] == [False, True, True, False]


def test_a_row_whose_accession_is_the_genes_protein_is_said_to_be_its_row():
    """AKR1C3 is the only human protein EC 1.1.1.188 lists, so the resolver
    reads no isoform off a P42330 cell. The report said of AKR1C3's own
    rows that "whether it measured AKR1C3 is unknown"."""
    from caterva.compose.isoform import select_isoform

    row = {"value": 0.0015, "unit": "mM", "reference_id": "685035", "conditions": "pH 7.0, 37°C",
           "isoform": None, "uniprot": "P42330"}
    m = SimpleNamespace(value=0.0015, unit="mM", citation="BRENDA ref 685035", reference_id=None,
                        commentary="pH 7.0, 37°C", row_isoform=None, alternatives=(row,))
    out = select_isoform({"reaction_Km": m}, "AKR1C3")
    assert out.measured["reaction_Km"] is m
    assert out.notes == ["`reaction_Km`: the row's UniProt accession (P42330) is AKR1C3"]
    # Another protein's accession, or none: still said to be unknown.
    for cell in ("P15121", None):
        other = SimpleNamespace(**{**vars(m), "alternatives": ({**row, "uniprot": cell},)})
        assert "unknown" in " ".join(select_isoform({"reaction_Km": other}, "AKR1C3").notes)
