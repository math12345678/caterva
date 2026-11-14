"""The polish pass after the sixth adversarial round of the real-values work
(2026-11-14), the parts that are the literature layer's. Offline: every
commentary below is a BRENDA row's, copied from the live page.

- "phenylalanine hydroxylase R408W" carried the Km of the wild-type/R408W
  allelic combination (ref 712843) as the mutant's;
- bromelain's pair was a row with gallic acid added ("gallic 0.02 g/l"),
  beside the same paper's "without gallic" control (ref 717695);
- 5-lipoxygenase's pair was the "8-HETE formation" row, a side product,
  over the same paper's overall assay (ref 742078);
- a sulfated trypsin row was called an alteration of a "native" enzyme;
- "hexosaminidase A", "placental enzyme" and the MB hybrid of creatine
  kinase were read as naming no isoform, or the wrong one;
- "D-Fructose 1-phosphate" and "fructose 1-phosphate" reached different rows.
"""
from __future__ import annotations

from types import SimpleNamespace

import compound_names
import fallback_logic
import row_form
from brenda_client import substrate_matches
from effector import extract_effectors


# -- A mutant mixed with the wild type is not the mutant ---------------------------------

ALLELIC = "allelic combination wild-type/mutant R408W, Vmax: 0.7 micromol/min/mg, pH 6.8, 37°C"


def test_an_allelic_combination_is_a_mixture():
    assert fallback_logic.mixed_with_wild_type(ALLELIC)
    assert fallback_logic.mixed_with_wild_type("heterozygous R408W carrier")
    assert fallback_logic.mixed_with_wild_type("co-expression of wild-type and mutant R252W")
    assert not fallback_logic.mixed_with_wild_type("mutant R408W, pH 7.0, 25°C")
    assert not fallback_logic.mixed_with_wild_type("wild-type enzyme, pH 6.8, 37°C")


def test_a_mixed_row_is_never_the_mutants_row():
    mixed = SimpleNamespace(conditions=ALLELIC, km_value=3.0)
    pure = SimpleNamespace(conditions="mutant R408W, pH 7.0, 25°C", km_value=0.035)
    log: list = []
    assert fallback_logic._partition_mutant([mixed, pure], "R408W", log, "exact-match") == [pure]
    assert any("mixture with the wild type" in line for line in log)
    log = []
    assert fallback_logic._partition_mutant([mixed], "R408W", log, "exact-match") == []
    assert any("No exact-match row measures the mutant R408W" in line for line in log)


# -- A dosed addition beside its control -------------------------------------------------

def test_a_dosed_addition_is_read_with_its_amount():
    assert row_form.dosed_additives("pH 3.2, 25°C, gallic 0.02 g/l") == {"gallic": 0.02}
    assert row_form.dosed_additives("pH 3.2, 25°C, free SO2 25 mg/l") == {"free so2": 25.0}
    assert row_form.dosed_additives("pH 3.2, 25°C, ethanol 0%") == {"ethanol": 0.0}
    assert row_form.dosed_additives("pH 3.2, 25°C") == {}
    assert row_form.dosed_additives("wild-type, pH 7.5, 37°C") == {}


def _entry(conditions, ref="717695"):
    return SimpleNamespace(conditions=conditions, reference_id=ref,
                           effectors=extract_effectors(conditions))


def test_the_dosed_row_is_the_treated_arm_when_the_paper_has_the_control():
    dosed = _entry("pH 3.2, 25°C, gallic 0.02 g/l")
    control = _entry("pH 3.2, 25°C, without gallic")
    ethanol = _entry("pH 3.2, 25°C, ethanol 12%")
    zero = _entry("pH 3.2, 25°C, ethanol 0%")
    rows = [dosed, control, ethanol, zero]
    assert fallback_logic._added_compounds(dosed, rows) == ["gallic"]
    assert fallback_logic._added_compounds(ethanol, rows) == ["ethanol"]
    assert fallback_logic._added_compounds(control, rows) == []
    assert fallback_logic._added_compounds(zero, rows) == []
    # Without the control in the same paper a dose decides nothing.
    alone = _entry("pH 3.2, 25°C, gallic 0.02 g/l", ref="1")
    assert fallback_logic._added_compounds(alone, [alone, _entry("pH 3.2, 25°C, without gallic", ref="2")]) == []


# -- One product's formation is not the reaction's turnover -------------------------------

def test_a_row_following_one_product_is_read():
    assert row_form.one_product_formed("pH 7.5, 25°C, HPLC analysis, 8-HETE formation") == "8-HETE"
    assert row_form.one_product_formed("formation of 5-HPETE, pH 7.5") == "5-HPETE"
    assert row_form.one_product_formed("pH 7.5, 25°C, UV-Vis spectrophotometric analysis") is None
    assert row_form.one_product_formed("product formation, pH 7") is None


def test_the_overall_assay_is_preferred_within_one_paper():
    side = SimpleNamespace(conditions="pH 7.5, 25°C, HPLC analysis, 8-HETE formation", reference_id="742078")
    whole = SimpleNamespace(conditions="pH 7.5, 25°C, UV-Vis spectrophotometric analysis",
                            reference_id="742078")
    other = SimpleNamespace(conditions="pH 7.5, 25°C", reference_id="741898")
    assert fallback_logic._one_product_beside_overall(side, [side, whole, other])
    assert not fallback_logic._one_product_beside_overall(whole, [side, whole, other])
    assert not fallback_logic._one_product_beside_overall(side, [side, other])


# -- Sulfated is a form, not an alteration of a "native" enzyme ---------------------------

def test_a_sulfated_row_is_labelled_as_that_form():
    said = row_form.construct_of("pH 8.0, 37°C, uncleaved enzyme, sulfated")
    assert said and said.startswith(row_form.SULFATED_FORM)
    assert "modification state" not in said
    assert row_form.construct_of("pH 8.0, 37°C, cleaved enzyme, nonsulfated").startswith(
        "a modification state of the enzyme")
    assert row_form.construct_of("pH 8.0, 37°C, uncleaved enzyme, nonsulfated") is None
    assert row_form.construct_of("sulfated substrate") is None


# -- Forms named in words, and tissues ----------------------------------------------------

def test_forms_named_in_words_are_read_for_their_ec():
    read = row_form.tissue_isoform_of_row
    assert read("3.2.1.52", "hexosaminidase A") == "HEXA"
    assert read("3.2.1.52", "form A") == "HEXA"
    assert read("3.2.1.52", "hexosaminidase B") == "HEXB"
    assert read("3.2.1.52", "wild type enzyme, at pH 7.4 and 37°C") is None
    assert read("2.7.3.2", "hybrid form consisting of muscle and brain creatine kinase isoforms, pH and "
                           "temperature not specified in the publication") == "CK-MB"
    assert read("2.7.3.2", "pH 7.0, muscle-type cytosolic isozyme") == "CKM"
    assert read("2.7.3.2", "wild-type hBBCK") == "CKB"
    assert read("3.1.3.1", "pH 9.8, native placental enzyme") == "ALPP"
    assert read("3.1.3.1", "allozyme D, pH 7.5, 37°C, in presence of Mg2+ and Zn2+") is None
    # Another EC's rows are not read by these tables.
    assert read("1.1.1.1", "form A") is None


def test_an_allozyme_is_said_on_the_row():
    entry = SimpleNamespace(conditions="allozyme D, pH 7.5, 37°C, in presence of Mg2+ and Zn2+",
                            ec_number="3.1.3.1", uniprot=None, variant=None)
    notes = fallback_logic._row_notes(entry, "km")
    assert any("allozyme D" in n and "genetic variant" in n for n in notes)


# -- One compound, filed with and without the descriptor of its natural form --------------

def test_natural_forms_are_one_compound():
    same = compound_names.same_compound
    assert same("fructose 1-phosphate", "D-Fructose 1-phosphate")
    assert same("hydroxymethylglutaryl-CoA", "(S)-3-hydroxy-3-methylglutaryl-CoA")
    assert same("pyridoxal phosphate", "pyridoxal 5'-phosphate")
    assert same("phenylalanine", "L-phenylalanine") and same("L-Phe", "phenylalanine")
    assert not same("D-phenylalanine", "phenylalanine")
    assert not same("L-fructose 1-phosphate", "fructose 1-phosphate")
    # Both spellings reach the same rows, whichever is asked for.
    assert substrate_matches("fructose 1-phosphate", "D-Fructose 1-phosphate")
    assert substrate_matches("D-Fructose 1-phosphate", "fructose 1-phosphate")
    assert substrate_matches("hydroxymethylglutaryl-CoA", "(S)-3-hydroxy-3-methylglutaryl-CoA")


# -- A row measured with an activator added ------------------------------------------------

def test_a_row_naming_its_activator_is_an_altered_assay():
    """Human phenylalanine hydroxylase, ref 713593: one row per activator.
    With "phenylalanine" and "L-phenylalanine" counted as one compound the
    median of the pool moved onto one of them (0.14 mM, "activator: L-Phe (4
    mM)") from the wild-type row (0.318 mM, ref 712471)."""
    said = row_form.construct_of("post-translational activation of human cDNA-expressed PAH, activator: "
                                 "H2O2 (0.1 mM), Vmax: 28.4 nmoles/min/mg, pH 6.8, 37°C")
    assert said and said.startswith("an assay with a compound added") and "H2O2" in said
    assert row_form.construct_of("activator: L-Phe (4 mM), pH 6.8")
    # An ion named as the activator is the assay's cofactor.
    assert row_form.construct_of("pH 7, activator: Mg2+") is None
    assert row_form.construct_of("activator: K+, pH 8") is None
