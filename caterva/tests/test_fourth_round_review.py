"""The fourth adversarial round of the real-values work (2026-11-12), the
parts that are caterva's: how a sentence, a row's commentary and a
choice are read. Offline: the enzyme index, the symbol table and the
isoform reader are files in the package; no BRENDA page is fetched.
"""
from __future__ import annotations

import pytest

from caterva.bind.core import read_isoform, same_isoform
from caterva.compose import defaults
from caterva.compose.export import Measurement, _two_forms
from caterva.compose.report import _additives
from caterva.compose.row_scope import ASSAY_SUBSTRATE, read_scope
from caterva.enzymes.finder import Resolved, resolve
from caterva.enzymes.isozyme import IsozymeNotice, describe_isoform
from caterva.enzymes.sentence import read_sentence


# -- Isoforms a row names in words the reader did not know ------------------------------

@pytest.mark.parametrize("text, reading", [
    ("inducible isoform from macrophage after preincubation", "inducible isoform"),
    ("recombinant iNOS, pH 7.4", "NOS2"),
    ("wild-type PTPalpha, 25C, pH 7.0", "PTPRA"),
    ("25°C, pH 7.05, low activity carbonic anhydrase", "CA-I"),
    ("pH 7.5, 20°C, HCA IX", "CA-IX"),
])
def test_a_row_names_its_isoform(text, reading):
    assert read_isoform(text) == reading


def test_inducible_is_nos2_and_cox2_never_nos1():
    assert same_isoform("inducible isoform", "NOS2") and same_isoform("inducible isoform", "PTGS2")
    assert not same_isoform("inducible isoform", "NOS1")
    assert not same_isoform("PTPRA", "PTPN1")


# -- Names --------------------------------------------------------------------------

def test_a_cofactor_written_first_reads_the_enzyme_of_that_cofactor():
    assert resolve("NADP-isocitrate dehydrogenase", "Escherichia coli").ec == "1.1.1.42"
    assert resolve("NAD-isocitrate dehydrogenase", None).ec == "1.1.1.41"
    reading = read_sentence("NADP-isocitrate dehydrogenase from E. coli")
    assert reading.ec == "1.1.1.42" and reading.organism == "Escherichia coli"


def test_the_organism_named_singles_out_the_qualified_sibling():
    found = resolve("glutamate dehydrogenase", "Bos taurus")
    assert isinstance(found, Resolved) and found.ec == "1.4.1.3"
    # An acceptor qualifier is another enzyme, not this one with its cofactor.
    assert resolve("L-lactate dehydrogenase", "yeast").ec == "1.1.1.27"


def test_impdh2_is_read_as_a_gene_symbol():
    reading = read_sentence("IMPDH2 with mycophenolic acid")
    assert reading.ec == "1.1.1.205" and reading.isoform == "IMPDH2"


def test_a_virus_is_read_as_the_organism():
    reading = read_sentence("herpes simplex virus thymidine kinase with ganciclovir")
    assert reading.organism == "Herpes simplex virus" and reading.ec == "2.7.1.21"


def test_a_gene_symbol_filed_under_another_ec_is_said_to_be_one():
    said = describe_isoform("1.14.14.1", "Homo sapiens", "CYP2B6")
    # Not "filed under another EC number": BRENDA lists P20813 under this
    # one; only Caterva's copy of the list leaves it out (R5B-02).
    assert said.startswith("--isoform 'CYP2B6' names UniProtKB P20813, which is not among")
    assert "another EC number" not in said
    assert "is not a gene symbol" not in said


def test_an_isoform_is_chosen_only_where_its_ortholog_is():
    found = defaults.organisms_with_isoform("4.2.1.1", "CA1")
    assert "Homo sapiens" in found and "Escherichia coli" not in found


# -- What a remedy offers -------------------------------------------------------------

def test_no_placeholder_name_is_offered_and_a_measured_protein_is_not_swapped():
    bare = IsozymeNotice(ec="1.1.1.1", organism="HORSE", count=3, symbols=())
    assert "its name" not in bare.remedy
    measured = IsozymeNotice(ec="3.4.24.11", organism="HUMAN", count=2, symbols=("MME", "MMEL1"),
                             measured_as="MME")
    assert "--isoform MME" in measured.remedy and "MMEL1" not in measured.remedy
    suggested = IsozymeNotice(ec="2.7.1.1", organism="HUMAN", count=5,
                              symbols=("HKDC1", "HK1", "HK2", "HK3", "GCK"), suggest="HK1")
    assert "(for example --isoform HK1)" in suggested.remedy


# -- What a row is, said -------------------------------------------------------------

def test_a_ki_on_another_assay_substrate_is_a_concern():
    scope = read_scope("pH 8.0, 37°C, wild-type enzyme, hydrolysis of o-aminobenzoyl-SDK-(dinitrophenyl)-P-OH",
                       motif="competitive_inhibition", table="ki", substrate="angiotensin I")
    (concern,) = [c for c in scope.concerns if c.kind == ASSAY_SUBSTRATE]
    assert "N-domain-selective" in concern.text


def test_the_condition_line_carries_salts_and_ions():
    assert _additives("pH 5.0, 2.0 M NaCl") == ["with 2.0 M NaCl"]
    assert _additives("wild type enzyme, in the presence of K+, pH 6.0") == ["with K+"]


def test_a_spread_of_two_forms_says_so():
    rows = [{"value": 0.0055, "conditions": "corebral cortex, membrane-bound form"},
            {"value": 0.0114, "conditions": "hypothalamus, membrane-bound form"},
            {"value": 0.304, "conditions": "corebral cortex, soluble enzyme"},
            {"value": 0.465, "conditions": "hypophysis, soluble enzyme"}]
    assert _two_forms(rows) == (("membrane-bound form", 0.0055, 0.0114), ("soluble form", 0.304, 0.465))


def test_a_mutants_spread_is_its_own_rows():
    m = Measurement(1.5, "mM", "BRENDA ref 760535", commentary="mutant enzyme R132H, at pH 7.5 and 37°C",
                    alternatives=({"value": 0.015, "conditions": "wild type enzyme, at pH 7.5 and 21°C"},
                                  {"value": 1.1, "conditions": "mutant R132H, 37°C"}))
    assert m.disagreement == (1.1, 1.5)
