"""The isozyme notice: what it says for a few proteins, for a broad class, for E. coli, and for a family filed elsewhere.

Real index, real names. The cases are the ones the review of 2026-10-03 found misleading: "245 human isozymes" for
EC 2.7.11.1 (245 different kinases); EC 1.1.1.1's human list leaving out ADH1B and ADH4, which the nomenclature files
under EC 1.1.1.105; "lists no E. coli protein" for 76 EC numbers that have a protein in another E. coli strain and
none in K-12.
"""
from __future__ import annotations

from caterva.enzymes import load_index, resolve
from caterva.enzymes.isozyme import BROAD_CLASS, describe_isoform, isozyme_notice


def test_a_few_proteins_are_isozymes_named_by_gene_symbol():
    notice = isozyme_notice("2.7.1.1", "human")
    assert notice.count == 5 and not notice.broad
    assert notice.symbols == ("HKDC1", "HK1", "HK2", "HK3", "GCK")
    assert notice.detail.startswith("EC 2.7.1.1 has 5 human isozymes in the enzyme nomenclature's UniProt entries")
    assert "(HKDC1, HK1, HK2, HK3, GCK)" in notice.detail and "HXK" not in notice.detail
    assert "pass --isoform with one of these names (for example --isoform HKDC1)" in notice.remedy
    assert "a constant whose rows name none is kept and flagged" in notice.remedy


def test_more_than_twelve_proteins_are_a_broad_class_not_isozymes():
    assert BROAD_CLASS == 12
    notice = isozyme_notice("2.7.11.1", "human")
    assert notice.count == 245 and notice.broad
    assert notice.detail.startswith("245 different human proteins share EC 2.7.11.1 (a broad class")
    assert "isozymes" not in notice.detail.replace("not isozymes of one enzyme", "")
    assert "(HK" not in notice.detail and "isozymes of one enzyme can differ" not in notice.detail
    assert notice.summary == "EC 2.7.11.1 is a broad class of 245 different proteins in human, none chosen"
    assert "isozyme" not in notice.headline
    thirteen = [ec for ec, e in load_index().entries.items() if len(e.proteins.get("HUMAN", ())) == BROAD_CLASS + 1]
    assert thirteen and isozyme_notice(thirteen[0], "human").broad
    twelve = [ec for ec, e in load_index().entries.items() if len(e.proteins.get("HUMAN", ())) == BROAD_CLASS]
    assert twelve and not isozyme_notice(twelve[0], "human").broad


def test_alcohol_dehydrogenases_the_nomenclature_files_under_another_ec_are_named():
    notice = isozyme_notice("1.1.1.1", "human")
    assert notice.symbols == ("ADH1A", "ADH1C", "ADH6", "ADH7", "ADH5")
    assert notice.elsewhere == (("ADH1B", "1.1.1.105"), ("ADH4", "1.1.1.105"))
    assert "ADH1B, ADH4 under EC 1.1.1.105 instead, so this list may leave out a protein papers measured" in notice.detail
    # An EC whose family is filed nowhere else says nothing about it.
    assert isozyme_notice("2.7.1.1", "human").elsewhere == ()


def test_e_coli_is_k_12_and_the_notice_and_the_caution_say_so():
    notice = isozyme_notice("1.1.1.1", "E. coli")
    assert notice.label == "E. coli K-12" and "5 E. coli K-12 isozymes" in notice.detail
    only_elsewhere = [ec for ec, e in load_index().entries.items()
                      if e.status == "active" and not e.counts.get("ECOLI")
                      and any(c.startswith("ECO") and c != "ECOLI" for c in e.counts)]
    assert len(only_elsewhere) == 76
    result = resolve("dTDP-4-dehydro-6-deoxyglucose reductase", "E. coli")
    (caution,) = result.cautions
    assert "lists no protein from E. coli K-12 (UniProt code ECOLI; proteins of other E. coli strains are filed " \
           "under other codes and are not counted)" in caution
    assert "lists no E. coli protein" not in caution


def test_the_notice_is_quiet_when_it_should_be():
    assert isozyme_notice("2.7.1.1", "pig") is None
    assert isozyme_notice("2.7.1.1", None) is None
    assert isozyme_notice("2.7.1.1", "Thermus aquaticus") is None
    assert isozyme_notice(None, "human") is None and isozyme_notice("1.1.1", "human") is None
    assert isozyme_notice("2.7.1.1", "human", "HK1", unstated=[]) is None


def test_what_an_isoform_label_was_read_as_is_said_and_a_stranger_is_said_not_to_match():
    said = describe_isoform("2.7.1.1", "human", "hexokinase type II")
    assert said.startswith("--isoform 'hexokinase type II' was read as HK2, human protein HXK2_HUMAN (UniProt P52789)")
    assert "Hexokinase type II" in said and "HK II" in said
    stranger = describe_isoform("2.7.1.1", "human", "HK9")
    assert "is not a gene symbol or name the enzyme nomenclature's UniProt entries give" in stranger
    assert "(HKDC1, HK1, HK2, HK3, GCK)" in stranger
    assert describe_isoform("2.7.1.40", "human", "PKM") is not None
    assert describe_isoform("3.5.1.2", "pig", "x") is None
