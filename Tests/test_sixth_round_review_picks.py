"""The sixth adversarial round of the real-values work (2026-11-13): which
BRENDA row a constant carries, in the literature layer.

Each case is a real BRENDA row set copied from the live page (value,
compound, organism, UniProt cell, commentary and reference as BRENDA writes
them), in a page of BRENDA's own markup so the test runs offline:

- a refolded "His-taggged" CES1 row, a xylose isomerase row "in D2O" and a
  chymotrypsin row with CTAB and an ionic liquid in the assay were read as
  the native enzyme's;
- trypsin's "uncleaved enzyme, nonsulfated" rows, the intact enzyme, were
  read as a modification state;
- AMP's FBPase Ki with "Hill-coefficient 1.9" was built into a one-site
  model unsaid, and the "muscle enzyme" row was called FBP1's;
- "aldolase B" in a row's words was read as naming no isoform;
- PARP1's NAD+ Km was the median of one paper's five values, one per
  PARP-family protein, none said to be whose;
- phenylethylamine and 6-phosphogluconate were counted apart under their
  spellings.
"""
from __future__ import annotations

import compound_names
import row_form
from fallback_logic import minority_cluster, resolve_kinetic_pair, resolve_kinetic_value
from test_literature_quality import page
from test_third_round_review import kw, row


# -- Altered preparations and conditions --------------------------------------------------

def test_a_refolded_or_tagged_enzyme_is_a_construct():
    said = row_form.construct_of("recombinant refolded His-taggged wild-type enzyme, pH 7.5, 37°C")
    assert said and said.startswith("a tagged construct")
    assert row_form.construct_of("refolded wild-type enzyme, pH 7.5").startswith("a refolded preparation")


def test_heavy_water_is_an_altered_condition():
    said = row_form.construct_of("in D2O, 24 mM imidazole buffer, 10 mM MgCl2, at pH 7.5 and 25°C")
    assert said and "D2O" in said
    assert row_form.construct_of("native wild type enzyme, in 100 mM HEPES-NaOH (pH 7.7), 25°C") is None


def test_a_surfactant_or_ionic_liquid_in_the_assay_is_an_altered_condition():
    for text in ("presence of 2 mM cetyltrimethylammonium bromide, 0.1 M 1-butyl-4-methylpyridinium "
                 "chloride, pH 7.5, 25°C",
                 "pH 8, in presence of 10 mM SDS",
                 "0.5 M 1-butyl-3-methylimidazolium chloride, 25°C",
                 "in ionic liquid, pH 7"):
        said = row_form.construct_of(text)
        assert said and "surfactant or ionic liquid" in said, text
    assert row_form.construct_of("25°C, pH 7.5") is None


def test_the_intact_unmodified_enzyme_is_native():
    assert row_form.construct_of("pH 8.0, 37°C, uncleaved enzyme, nonsulfated") is None
    assert row_form.construct_of("pH 8.0, 37°C, cleaved enzyme, nonsulfated")
    assert row_form.construct_of("pH 8.0, 37°C, uncleaved enzyme, sulfated")


# -- What a row says it measured ------------------------------------------------------------

def test_a_hyphenated_hill_coefficient_is_read():
    assert row_form.half_saturation("wild-type, pH 7.0, 37°C, Hill-coefficient 1.9")
    assert row_form._HILL_VALUE.search("Hill-coefficient 1.9").group(1) == "1.9"


def test_tissue_and_letter_isoforms_are_read_from_the_words():
    assert row_form.tissue_isoform_of_row("3.1.3.11", "wild-type muscle enzyme, pH 7.5, 37°C") == "FBP2"
    assert row_form.tissue_isoform_of_row("3.1.3.11", "wild-type liver enzyme, pH 7.5, 37°C") == "FBP1"
    assert row_form.tissue_isoform_of_row("4.1.2.13", "aldolase B") == "ALDOB"
    assert row_form.tissue_isoform_of_row("4.1.2.13", "mutant aldolase C Y363S") == "ALDOC"
    assert row_form.tissue_isoform_of_row("4.1.2.13", "wild-type enzyme, 22°C") is None


# -- One compound under its spellings --------------------------------------------------------

def test_phenylethylamine_and_6_phosphogluconate_are_one_compound_each():
    assert compound_names.same_compound("2-Phenylethylamine", "Phenylethylamine")
    assert compound_names.same_compound("beta-phenylethylamine", "phenethylamine")
    assert compound_names.same_compound("6-phospho-D-gluconate", "6-phosphogluconate")
    assert not compound_names.same_compound("6-phosphono-D-gluconate", "6-phosphogluconate")
    assert not compound_names.same_compound("phenylethylamine", "benzylamine")


# -- NEW-09: one paper's value per protein is no protein's -----------------------------------

PARP_CELL = "O95271, P09874, Q9UGN5, Q9H2K2, C9J7L3"
PARP_KM = [row(v, "NAD+", "Homo sapiens", "pH and temperature not specified in the publication",
               "776950", PARP_CELL) for v in (0.011, 0.031, 0.035, 0.159, 0.251)]


def test_one_papers_value_per_protein_is_not_parp1s():
    html = page({"KM Values": PARP_KM})
    km = resolve_kinetic_value("2.4.2.30", "Homo sapiens", "NAD+", quantity="km", isoform="PARP1",
                               **kw(html, "Homo sapiens"))
    assert not km.found


def test_one_value_under_a_shared_cell_is_still_taken():
    # One row, one value: nothing says the paper gave one per protein.
    html = page({"KM Values": PARP_KM[2:3]})
    km = resolve_kinetic_value("2.4.2.30", "Homo sapiens", "NAD+", quantity="km",
                               **kw(html, "Homo sapiens"))
    assert km.found and km.value == 0.035


# -- NEW-03: two papers sharing a slip do not hide each other ---------------------------------

F1P = "fructose 1-phosphate"
ALDOLASE_KM = (
    [row(0.0022, "D-Fructose 1-phosphate", "Homo sapiens", "wild-type enzyme, 22°C", "651313", "P05062"),
     row(0.0024, "D-Fructose 1-phosphate", "Homo sapiens", "wild-type, 22°C, pH 7.6", "651985"),
     row(0.24, "D-Fructose 1-phosphate", "Homo sapiens", "pH 7.4, 10°C, wild-type enzyme", "649476"),
     row(0.88, "D-Fructose 1-phosphate", "Homo sapiens", "pH 7.4, 30°C, wild-type enzyme", "649476"),
     row(16.0, "D-Fructose 1-phosphate", "Homo sapiens", "-", "666852"),
     row(1.1, F1P, "Homo sapiens", "recombinant enzyme", "4949"),
     row(2.3, F1P, "Homo sapiens", "liver enzyme", "4949"),
     row(2.0, F1P, "Homo sapiens", "-", "4933"),
     row(3.0, F1P, "Homo sapiens", "-", "4912"),
     row(3.7, F1P, "Homo sapiens", "aldolase B", "4945"),
     row(18.0, F1P, "Homo sapiens", "aldolase C", "4945"),
     row(27.0, F1P, "Homo sapiens", "aldolase A", "4945")])
ALDOLASE_KCAT = (
    [row(0.67, "D-Fructose 1-phosphate", "Homo sapiens", "wild-type enzyme, 22°C", "651313", "P05062"),
     row(0.12, "D-Fructose 1-phosphate", "Homo sapiens", "pH 7.4, 10°C, wild-type enzyme", "649476"),
     row(2.0, "D-Fructose 1-phosphate", "Homo sapiens", "pH 7.4, 30°C, wild-type enzyme", "649476"),
     row(2.8, "D-Fructose 1-phosphate", "Homo sapiens", "-", "666852"),
     row(1.28, F1P, "Homo sapiens", "aldolase A", "4945"),
     row(1.48, F1P, "Homo sapiens", "aldolase C", "4945"),
     row(10.8, F1P, "Homo sapiens", "aldolase B", "4945")])


class _E:
    def __init__(self, value, ref, conditions="", ec="4.1.2.13"):
        self.km_value, self.reference_id, self.conditions, self.ec_number = value, ref, conditions, ec
        self.uniprot, self.uniprot_from_row = None, False


def test_a_far_cluster_of_two_papers_is_a_probable_error():
    rows = [_E(0.0022, "651313"), _E(0.0024, "651985"), _E(0.24, "649476"), _E(0.88, "649476"),
            _E(16.0, "666852"), _E(1.1, "4949"), _E(2.3, "4949"), _E(2.0, "4933"), _E(3.0, "4912"),
            _E(3.7, "4945"), _E(18.0, "4945"), _E(27.0, "4945")]
    found = minority_cluster(rows)
    assert set(found) == {"651313", "651985"}
    assert "651985" in found["651313"][1] and "unit slip" in found["651313"][1]


def test_a_cluster_is_left_alone_when_it_may_be_right():
    # Outnumbered less than three to one.
    few = [_E(0.002, "1"), _E(2.0, "2"), _E(3.0, "3")]
    assert minority_cluster(few) == {}
    # A paper with rows near and far runs a series over a condition.
    series = [_E(0.008, "649476"), _E(0.12, "649476"), _E(2.0, "649476"), _E(2.8, "1"), _E(1.3, "2"),
              _E(1.5, "3"), _E(10.8, "4")]
    assert minority_cluster(series) == {}
    # Three papers agreeing are not a slip.
    three = [_E(0.002, "1"), _E(0.0022, "2"), _E(0.0024, "3")] + [_E(2.0 + i, str(10 + i)) for i in range(9)]
    assert minority_cluster(three) == {}
    # Within 100-fold of the others' median: a wide literature, not an error.
    wide = [_E(0.05, "1"), _E(2.0, "2"), _E(3.0, "3"), _E(4.0, "4")]
    assert minority_cluster(wide) == {}


def test_aldolase_b_carries_the_pair_the_other_papers_agree_with():
    html = page({"KM Values": ALDOLASE_KM, "Turnover Numbers": ALDOLASE_KCAT})
    km, kcat = resolve_kinetic_pair("4.1.2.13", "Homo sapiens", F1P, isoform="ALDOB",
                                    **kw(html, "Homo sapiens"))
    assert (km.value, kcat.value) == (3.7, 10.8)
    assert km.citation.reference_id == kcat.citation.reference_id == "4945"
    assert "BRENDA ref 651313's row was not used" in km.chosen_because
    assert "651985" in km.chosen_because
