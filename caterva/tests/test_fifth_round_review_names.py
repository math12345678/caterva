"""The fifth adversarial round of the real-values work (2026-11-12), the
names half: how an enzyme name is read, which EC number it is taken as, and
what is said about it (ADR 0182, fifth round).

Offline: the enzyme index, the alias and symbol tables and the protein
names file ship with the package; BRENDA's rows are stand-ins built from
the rows the review quoted (`defaults.table_rows` is replaced), and no page
is fetched.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

import caterva.compose.__main__ as cli
from caterva.compose import defaults
from caterva.compose.grammar import UnrecognisedShape, _fragment_of_enzyme_names, recognise
from caterva.enzymes.finder import Ambiguous, Resolved, find, resolve
from caterva.enzymes.sentence import match_substrate, read_sentence


@pytest.fixture(autouse=True)
def _no_page(monkeypatch):
    """Any BRENDA page a test did not stand in for is an error, not a fetch."""
    def refuse(ec):
        raise AssertionError(f"a test fetched BRENDA's page for EC {ec}")
    monkeypatch.setattr(defaults, "_page", refuse)


def _rows(by_ec):
    """{(ec, organism): [_Row, ...]} -> a `table_rows` stand-in (Km only)."""
    def table_rows(ec, table, organism):
        if table != "km":
            return ()
        return tuple(r for (e, o), rows in by_ec.items() for r in rows
                     if e == ec and (organism is None or o == organism))
    return table_rows


def _row(compound, organism, conditions="", **kw):
    return defaults._Row(compound, organism, conditions, **kw)


# -- N14: a typo is suggested as the name it is close to ----------------------------

def test_a_typo_ranks_the_whole_name_it_is_close_to_first():
    """"enolse" is one letter from 'enolase' (EC 4.2.1.11's other name) and from
    the 'enolase' inside 'E-1 enolase-phosphatase' (EC 3.1.3.77); the shorter
    accepted name won the tie, and the refusal asked for acireductone synthase."""
    found = find("enolse", limit=None)
    assert found[0].ec == "4.2.1.11" and found[0].spare == 0
    assert found[1].ec == "3.1.3.77" and found[1].spare > 0


def test_the_typo_refusal_suggests_the_name_people_use():
    with pytest.raises(UnrecognisedShape) as raised:
        recognise("enolse from baker's yeast")
    said = str(raised.value)
    assert "Did you mean 'enolase'?" in said
    assert 'caterva compose "enolase from baker\'s yeast"' in said
    assert "Did you mean 'acireductone synthase'" not in said
    # And the name suggested is one the finder reads as that enzyme.
    assert resolve("enolase", "yeast").ec == "4.2.1.11"


# -- N15: an industrial name ----------------------------------------------------------

def test_glucose_isomerase_is_xylose_isomerase():
    found = resolve("glucose isomerase")
    assert isinstance(found, Resolved) and found.ec == "5.3.1.5"
    reading = read_sentence("glucose isomerase from Streptomyces")
    assert reading.ec == "5.3.1.5"


def test_words_inside_enzyme_names_are_said_instead_of_the_shape_list():
    """A phrase the finder lists names for gets those names, not "no shape in
    this grammar matches" and the list of mechanisms."""
    said = _fragment_of_enzyme_names("phosphate isomerase from yeast")
    assert said is not None
    assert "The words are part of these enzymes' names" in said and "EC 5.3.1." in said
    assert "--subject <EC number>" in said
    assert _fragment_of_enzyme_names("signalling in a cell") is None


# -- N16: a mnemonic that is the gene symbol ------------------------------------------

def test_an_entry_name_that_is_also_the_gene_symbol_is_read_as_the_gene():
    found = resolve("NQO1", "Homo sapiens")
    assert isinstance(found, Resolved) and found.ec == "1.6.5.2" and found.isoform == "NQO1"
    assert "gene symbol UniProt gives NQO1_HUMAN (UniProtKB P15559)" in found.how
    reading = read_sentence("NQO1 with menadione in human")
    assert reading.ec == "1.6.5.2" and reading.isoform == "NQO1"


@pytest.mark.parametrize("mnemonic", ["ACES", "HXK4", "KSYK"])
def test_an_entry_name_that_is_not_the_gene_symbol_stays_a_choice(mnemonic):
    """ACES_HUMAN is ACHE, HXK4_HUMAN is GCK, KSYK_HUMAN is SYK."""
    assert isinstance(resolve(mnemonic, "Homo sapiens"), Ambiguous)
    assert read_sentence(f"{mnemonic} in human").ec is None


# -- N7: the partial-match wording ----------------------------------------------------

def test_a_phrase_inside_many_names_is_not_said_to_be_part_of_one():
    found = resolve("thioredoxin reductase", "Rattus norvegicus")
    assert isinstance(found, Ambiguous) and len(found.candidates) > 1
    assert "only part of one enzyme's name" not in found.reason
    assert f"the names of {len(found.candidates)} enzymes" in found.reason


# -- N7, N8: the organism named settles a name several enzymes match --------------------

def _args(**kw):
    return SimpleNamespace(organism=None, subject=None, isoform=None, substrate=None, inhibitor=None, **kw)


def test_the_one_candidate_with_the_organisms_protein_and_rows_is_used(monkeypatch):
    rat = "Rattus norvegicus"
    monkeypatch.setattr(defaults, "table_rows", _rows({
        ("1.8.1.9", rat): [_row("thioredoxin disulfide", rat, "wild type enzyme", value=0.00143,
                                reference_id="698965")] * 3}))
    reading = read_sentence("thioredoxin reductase inhibited by auranofin in rat")
    chosen = cli._enzyme_the_organism_singles_out(reading, _args())
    assert chosen is not None and chosen.role == "enzyme" and chosen.chosen == "1.8.1.9"
    note = chosen.note()
    assert "only it lists a protein of Rattus norvegicus" in note and "TRXR1" in note
    assert "3 Km rows for it in Rattus norvegicus" in note
    assert "EC 1.8.7.2 (ferredoxin:thioredoxin reductase) (no rows)" in note


def test_two_with_the_organisms_protein_and_one_with_rows(monkeypatch):
    soy = "Glycine max"
    monkeypatch.setattr(defaults, "table_rows", _rows({
        ("1.13.11.12", soy): [_row("linoleic acid", soy, "at pH 9.5 and 40°C")] * 10}))
    reading = read_sentence("soybean lipoxygenase with linoleic acid")
    chosen = cli._enzyme_the_organism_singles_out(reading, _args())
    assert chosen is not None and chosen.chosen == "1.13.11.12"
    assert "2 list a protein of Glycine max" in chosen.why
    assert "the only one of them with Km rows there" in chosen.why


def test_two_candidates_with_rows_in_the_organism_stay_a_refusal(monkeypatch):
    soy = "Glycine max"
    monkeypatch.setattr(defaults, "table_rows", _rows({
        ("1.13.11.12", soy): [_row("linoleic acid", soy)],
        ("1.13.11.58", soy): [_row("linoleic acid", soy)]}))
    reading = read_sentence("soybean lipoxygenase with linoleic acid")
    assert cli._enzyme_the_organism_singles_out(reading, _args()) is None


def test_rows_for_a_candidate_listing_no_protein_of_the_organism_settle_nothing(monkeypatch):
    rat = "Rattus norvegicus"
    monkeypatch.setattr(defaults, "table_rows", _rows({("1.8.7.2", rat): [_row("x", rat)]}))
    reading = read_sentence("thioredoxin reductase inhibited by auranofin in rat")
    assert cli._enzyme_the_organism_singles_out(reading, _args()) is None


def test_without_an_organism_nothing_is_settled_by_it(monkeypatch):
    monkeypatch.setattr(defaults, "table_rows", lambda *a: ())
    reading = read_sentence("lipoxygenase with linoleic acid")
    assert cli._enzyme_the_organism_singles_out(reading, _args()) is None


# -- N6, V7-03: a protein the nomenclature files under another EC number ----------------

def test_rat_glucokinase_is_read_as_hxk4_of_hexokinase(monkeypatch):
    """EC 2.7.1.2 lists no rat protein and has no rat row; rat glucokinase is
    HXK4 of EC 2.7.1.1, where BRENDA's rows name it ("adult glucokinase",
    "hexokinase IV")."""
    rat = "Rattus norvegicus"
    monkeypatch.setattr(defaults, "table_rows", _rows({("2.7.1.1", rat): [
        _row("D-glucose", rat, "31°C and pH 7.7, adult glucokinase", value=7.7, reference_id="641070"),
        _row("2-deoxy-D-glucose", rat, "rat liver enzyme, hexokinase IV", value=9.0, reference_id="640220"),
        _row("D-glucose", rat, "HK I, at 25°C, pH 7.4", value=0.039, reference_id="640259")]}))
    reading = read_sentence("glucokinase from rat liver")
    assert reading.ec == "2.7.1.2"
    args = _args()
    said = cli._read_as_the_protein_filed_elsewhere(reading, args)
    assert args.subject == "2.7.1.1" and args.isoform == "HXK4"
    assert "lists no Rattus norvegicus protein" in said and "2 Km rows of 3 name it" in said
    assert "pass --subject 2.7.1.2" in said


def test_the_named_ec_is_kept_when_no_row_of_the_other_names_the_protein(monkeypatch):
    mouse = "Mus musculus"
    monkeypatch.setattr(defaults, "table_rows", _rows({("2.7.1.1", mouse): [
        _row("D-glucose", mouse, "pH and temperature not specified in the publication")]}))
    reading = read_sentence("glucokinase in mouse")
    args = _args()
    assert cli._read_as_the_protein_filed_elsewhere(reading, args) is None
    assert args.subject is None and args.isoform is None


def test_a_row_naming_the_protein_only_by_its_accession_counts(monkeypatch):
    """Human GCK's wild-type K0.5 row (ref 739603) names it only by P35557;
    the refusal said none of the 54 rows named GCK."""
    human = "Homo sapiens"
    monkeypatch.setattr(defaults, "table_rows", _rows({("2.7.1.1", human): [
        _row("D-glucose", human, "wild-type, K0.5 value, Hill coefficient 1.8, pH 7.6, 25 °C",
             value=6.3, reference_id="739603", uniprot="P35557"),
        _row("D-glucose", human, "pH 7.5", value=0.06, reference_id="1", uniprot="P19367")]}))
    said = cli._filed_under_another_ec("2.7.1.2", human, "glucokinase")
    assert "2 Km rows for EC 2.7.1.1 in Homo sapiens, 1 of which names GCK" in said
    assert "by UniProt accession" in said and "none of them" not in said


# -- V5-6: the enzyme's words are echoed whole ----------------------------------------

@pytest.mark.parametrize("text, words", [
    ("isocitrate dehydrogenase (NADP) in human Michaelis-Menten", "isocitrate dehydrogenase (NADP)"),
    ("isocitrate dehydrogenase (NADP+) from E. coli", "isocitrate dehydrogenase (NADP+)"),
])
def test_the_enzyme_words_keep_their_closing_bracket(text, words):
    reading = read_sentence(text)
    assert reading.ec == "1.1.1.42" and reading.enzyme_text == words
    assert reading.enzyme_note().startswith(f"Read {words!r} in your description")


# -- N13: a peptide substrate typed in its codes ----------------------------------------

def test_a_peptide_typed_in_codes_is_the_name_brenda_prints():
    listed = {"succinyl-L-Ala-L-Ala-L-Ala-4-nitroanilide": 3, "4-nitrophenyl acetate": 4}
    match = match_substrate(["Suc-Ala-Ala-Ala-pNA"], listed)
    assert match.name == "succinyl-L-Ala-L-Ala-L-Ala-4-nitroanilide"
    assert match.typed == "Suc-Ala-Ala-Ala-pNA"


def test_a_different_peptide_is_not_read_as_it():
    listed = {"succinyl-L-Ala-L-Ala-L-Pro-L-Ala-4-nitroanilide": 1}
    assert match_substrate(["Suc-Ala-Ala-Ala-pNA"], listed).name is None


# -- V7-07: a row filed under another name of the compound --------------------------------

def test_a_row_filed_under_a_systematic_name_says_so(monkeypatch):
    mouse = "Mus musculus"
    cell = "(R,S)-1-benzyl-4-[(5,6-dimethoxy-1-indanon)-2-yl]methylpiperidine hydrochloride"
    monkeypatch.setattr(defaults, "table_rows", lambda ec, table, organism: (
        _row(cell, mouse, "pH 8, 25°C, wild-type enzyme", value=2.2e-06, reference_id="651163"),)
        if table == "ki" else ())
    q = SimpleNamespace(parameter_id="reaction_Ki", table="ki")
    model = SimpleNamespace(resolvable=(q,), organism=mouse, compound_for=lambda _q: "donepezil")
    m = SimpleNamespace(value=2.2e-06, unit="mM", citation="BRENDA ref 651163", organism=mouse,
                        reference_id=None)
    notes = cli._filed_under_other_names(model, {"reaction_Ki": m}, "3.1.1.7")
    assert len(notes) == 1
    assert notes[0].startswith("`reaction_Ki`: BRENDA files the row it came from (ref 651163) as '(R,S)-1-benzyl")
    assert "which Caterva reads as donepezil" in notes[0] and "the same compound under another name" in notes[0]


def test_a_counter_ion_alone_is_not_another_name(monkeypatch):
    monkeypatch.setattr(defaults, "table_rows", lambda ec, table, organism: (
        _row("acetylthiocholine iodide", organism, "", value=0.04, reference_id="666973"),))
    q = SimpleNamespace(parameter_id="reaction_Km", table="km")
    model = SimpleNamespace(resolvable=(q,), organism="Mus musculus", compound_for=lambda _q: "acetylthiocholine")
    m = SimpleNamespace(value=0.04, unit="mM", citation="BRENDA ref 666973", organism="Mus musculus",
                        reference_id="666973")
    assert cli._filed_under_other_names(model, {"reaction_Km": m}, "3.1.1.7") == []


# -- A4-05: a tie on rows goes to the substrate the field measures, and is said -----------

def test_a_tie_on_usable_rows_is_broken_by_breadth_before_unusable_rows(monkeypatch):
    """Chymotrypsin in human: L-Ala-Ala-Pro-Phe-pNA and Suc-Ala-Ala-Pro-Phe-pNA
    have 2 Km and 2 kcat each; the first has 3 more rows of a variant, which
    the search cannot use, and won without the tie being said."""
    human = "Homo sapiens"
    plain = "L-alanyl-L-alanyl-L-prolyl-L-phenylalanine p-nitroanilide"
    suc = "N-succinyl-L-alanyl-L-alanyl-L-prolyl-L-phenylalanine p-nitroanilide"

    def rows(ec, table, organism):
        if table == "ki":
            return ()
        mine = [_row(plain, human, "wild-type", reference_id="769319"),
                _row(suc, human, "wild-type", reference_id="769319")] * 2
        mine += [_row(plain, human, "mutant S189D", reference_id="769319", variant=True)] * 3
        if organism is None:
            mine += [_row(suc, "Bos taurus", "pH 7.8", reference_id=str(i)) for i in range(30)]
        return tuple(mine)
    monkeypatch.setattr(defaults, "table_rows", rows)
    monkeypatch.setattr(defaults, "_reaction_compounds", lambda ec: (frozenset(), frozenset()))
    chosen = defaults._choose_substrate("3.4.21.1", human, True)
    assert chosen.chosen == suc
    assert "as many Km and kcat rows as any other" in chosen.why
    assert "reported more widely under EC 3.4.21.1" in chosen.why
