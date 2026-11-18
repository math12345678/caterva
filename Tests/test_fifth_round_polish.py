"""The fifth round's polish (2026-11-13): which BRENDA row a constant
carries, for the verified findings of the fifth round's last review.

Each case is a set of real BRENDA rows copied from the live page (value,
compound, organism, UniProt cell, commentary and reference as BRENDA writes
them), in a page of BRENDA's own markup so the test runs offline. Each test
names the finding it holds to.
"""
from __future__ import annotations

import compound_names
import row_form
from fallback_logic import resolve_kinetic_pair, resolve_kinetic_value
from test_literature_quality import page
from test_third_round_review import kw, row


# -- R5V1-01: a row tied to the isoform only by its paper, far from all the rest -------------

NOS_KM = [row(4.8, "L-arginine", "Rattus norvegicus", "pH 7.6, 10°C, wild type", "659257"),
          row(0.0022, "L-arginine", "Rattus norvegicus", "22°C, wild type", "658119"),
          row(0.0033, "L-arginine", "Rattus norvegicus", "pH 7.4", "440208"),
          row(0.014, "L-arginine", "Rattus norvegicus", "pH 7.5", "440210"),
          row(0.11, "L-arginine", "Rattus norvegicus", "-", "440230"),
          # The paper's other entry, naming NOS1: why 659257 is read as NOS1's.
          row(0.5, "NADPH", "Rattus norvegicus", "nNOS, pH 7.6", "659257")]


def test_a_row_tied_to_the_isoform_only_by_its_paper_and_far_from_all_others_is_set_aside():
    html = page({"KM Values": NOS_KM})
    r = resolve_kinetic_value("1.14.13.39", "Rattus norvegicus", "L-arginine", quantity="km",
                              isoform="NOS1", **kw(html, "Rattus norvegicus"))
    assert r.found and r.value != 4.8
    assert any("only because their paper names NOS1 elsewhere" in line and "probable error" in line
               for line in r.search_log)


# -- R5V1-02: two pairs agree on kcat and differ a thousandfold in Km --------------------------

PGA_KM = [row(19, "penicillin G", "Escherichia coli", "pH 7.8, 25°C", "650570"),
          row(19.5, "penicillin G", "Escherichia coli", "pH 7.8, 25°C", "710906"),
          row(0.013, "penicillin G", "Escherichia coli", "pH 7.0, 30°C", "668439", "P06875"),
          row(0.025, "penicillin G", "Escherichia coli", "-", "650021"),
          row(28, "penicillin G", "Escherichia coli", "-", "650022"),
          row(56.19, "penicillin G", "Escherichia coli", "-", "650023")]
PGA_KCAT = [row(50, "penicillin G", "Escherichia coli", "pH 7.8, 25°C", "650570"),
            row(39, "penicillin G", "Escherichia coli", "pH 7.0, 30°C", "668439", "P06875")]


def test_a_pair_whose_km_is_a_thousandfold_off_beside_an_accessioned_pair_is_not_carried():
    html = page({"KM Values": PGA_KM, "Turnover Numbers": PGA_KCAT})
    km, kcat = resolve_kinetic_pair("3.5.1.11", "Escherichia coli", "penicillin G",
                                    **kw(html, "Escherichia coli"))
    assert (km.value, kcat.value) == (0.013, 39)
    assert "signature of a unit slip" in km.chosen_because


# -- R5V1-17: one row stating pH and temperature, tenfold from every other -------------------

LOX_KM = [row(0.636, "linoleic acid", "Glycine max", "at pH 9.5 and 40°C", "764604"),
          row(0.01191, "linoleic acid", "Glycine max", "pH 9.0", "704118"),
          row(0.021, "linoleic acid", "Glycine max", "pH 9.0", "706032"),
          row(0.028, "linoleic acid", "Glycine max", "-", "706032")]


def test_one_conditioned_row_far_from_three_others_does_not_outrank_them():
    html = page({"KM Values": LOX_KM})
    r = resolve_kinetic_value("1.13.11.12", "Glycine max", "linoleic acid", quantity="km",
                              **kw(html, "Glycine max"))
    assert r.value == 0.021
    assert "lies more than 10-fold from every one of the 3 other rows" in r.chosen_because


def test_two_others_are_no_bulk_and_the_conditioned_row_still_wins():
    html = page({"KM Values": LOX_KM[:3]})
    r = resolve_kinetic_value("1.13.11.12", "Glycine max", "linoleic acid", quantity="km",
                              **kw(html, "Glycine max"))
    assert r.value == 0.636


# -- R5V1-10, R5V1-12: the enzyme from its own source, and no tag ---------------------------

CHY_KM = [row(0.007, "Abz-peptide", "Bos taurus", "hydrolysis by calf chymosin", "667763"),
          row(0.0056, "Abz-peptide", "Bos taurus", "hydrolysis by recombinant chymosin", "667763"),
          row(0.0056, "Abz-peptide", "Bos taurus", "hydrolysis by transgenic chymosin", "667763")]
CHY_KCAT = [row(1.6, "Abz-peptide", "Bos taurus", "hydrolysis by calf chymosin", "667763"),
            row(0.12, "Abz-peptide", "Bos taurus", "hydrolysis by recombinant chymosin", "667763"),
            row(0.16, "Abz-peptide", "Bos taurus", "hydrolysis by transgenic chymosin", "667763")]


def test_the_enzyme_from_its_own_source_beats_the_same_papers_transgenic_preparation():
    html = page({"KM Values": CHY_KM, "Turnover Numbers": CHY_KCAT})
    km, kcat = resolve_kinetic_pair("3.4.23.4", "Bos taurus", "Abz-peptide", **kw(html, "Bos taurus"))
    assert (km.value, kcat.value) == (0.007, 1.6)


def test_a_his_tagged_enzyme_is_a_construct():
    assert row_form.construct_of("recombinant His12-tagged wild type enzyme, in 100 mM HEPES")
    assert row_form.construct_of("N-terminally His6-tagged enzyme")
    assert row_form.construct_of("native wild type enzyme, in 100 mM HEPES") is None


# -- R5V1-06: the adult form over the fetal -------------------------------------------------

GCK_KM = [row(7.4, "D-glucose", "Rattus norvegicus", "31°C and pH 7.7, fetal glucokinase", "641070"),
          row(7.7, "D-glucose", "Rattus norvegicus", "31°C and pH 7.7, adult glucokinase", "641070")]


def test_the_adult_form_is_carried_over_the_same_papers_fetal_form():
    html = page({"KM Values": GCK_KM})
    r = resolve_kinetic_value("2.7.1.1", "Rattus norvegicus", "D-glucose", quantity="km",
                              **kw(html, "Rattus norvegicus"))
    assert r.value == 7.7
    assert "fetal, neonatal or embryonic form passed over" in r.chosen_because


# -- R5V1-11: a pair at an assay temperature over one at 8 C ---------------------------------

GA_KM = [row(0.28, "maltose", "Aspergillus niger", "8°C, pH 4.5, wild-type G2", "654806"),
         row(0.18, "maltose", "Aspergillus niger", "pH 4.5, 45°C", "666786"),
         row(0.83, "maltose", "Aspergillus niger", "pH 4.5, 35°C, recombinant wild-type enzyme",
             "682864")]
GA_KCAT = [row(0.46, "maltose", "Aspergillus niger", "8°C, pH 4.5, wild-type G2", "654806"),
           row(0.33, "maltose", "Aspergillus niger", "pH 4.5, 20°C", "666786"),
           row(7.55, "maltose", "Aspergillus niger", "pH 4.5, 35°C, recombinant wild-type enzyme",
               "682864")]


def test_a_pair_measured_at_an_ordinary_assay_temperature_beats_one_at_8_c():
    html = page({"KM Values": GA_KM, "Turnover Numbers": GA_KCAT})
    km, kcat = resolve_kinetic_pair("3.2.1.3", "Aspergillus niger", "maltose",
                                    **kw(html, "Aspergillus niger"))
    assert (km.value, kcat.value) == (0.83, 7.55)
    assert "outside the 25-37°C of an ordinary assay" in km.chosen_because


# -- R5V1-24: the carried row passed over and taken back is said -----------------------------

CPA_KM = [row(0.7, "hippuryl-Phe", "Bos taurus", "pH 7.5", "650547"),
          row(1.07, "hippuryl-Phe", "Bos taurus", "-", "650016"),
          row(0.102, "hippuryl-Phe", "Bos taurus", "pH 7.5, 25°C", "771957"),
          row(0.4, "hippuryl-Phe", "Bos taurus", "pH 7.5, 25°C", "773000")]
CPA_KCAT = [row(81, "hippuryl-Phe", "Bos taurus", "pH 7.5", "650547")]


def test_a_carried_row_from_among_those_passed_over_says_so():
    html = page({"KM Values": CPA_KM, "Turnover Numbers": CPA_KCAT})
    km, _ = resolve_kinetic_pair("3.4.17.1", "Bos taurus", "hippuryl-Phe", **kw(html, "Bos taurus"))
    assert km.value == 0.7
    assert "is one of those passed over, taken back" in km.chosen_because


# -- XS5-06: one wild-type Km with near-identical kcat rows is one measurement --------------

ACHE_KM = [row(0.054, "acetylthiocholine", "Mus musculus", "wild-type enzyme", "652194")]
ACHE_KCAT = [row(2667, "acetylthiocholine", "Mus musculus", "wild-type enzyme", "652194"),
             row(2670, "acetylthiocholine", "Mus musculus", "wild-type enzyme", "652194")]


def test_kcat_rows_within_one_percent_are_one_measurement_for_pairing():
    html = page({"KM Values": ACHE_KM, "Turnover Numbers": ACHE_KCAT})
    km, kcat = resolve_kinetic_pair("3.1.1.7", "Mus musculus", "acetylthiocholine",
                                    **kw(html, "Mus musculus"))
    assert "are one measurement" in km.chosen_because
    assert "cannot be told" not in km.chosen_because


# -- R5V1-03, R5V1-08, R5V1-09, R5V1-30, XS5-02, R5V1-28: one compound, several names ---------

def test_drug_codes_and_full_names_are_one_compound():
    same = compound_names.same_compound
    assert same("sitagliptin", "MK-0431")
    assert same("SAHA", "suberoylanilide hydroxamic acid") and same("vorinostat", "SAHA")
    assert same("teriflunomide", "2-hydroxyethylidene-cyanoacetic acid 4-trifluoromethyl anilide")
    assert same("sivelestat", "ONO-5046")
    assert same("o-nitrophenyl-beta-D-galactoside", "2-nitrophenyl beta-D-galactopyranoside")
    assert same("ONPG", "2-nitrophenyl beta-D-galactopyranoside")
    assert same("dihydroorotate", "S-dihydroorotate")
    assert not same("sitagliptin", "vildagliptin")


# -- XS5-03: a compound filed under another name is said by the resolver ---------------------

DON_KI = [row(2.2e-06, "(R,S)-1-benzyl-4-[(5,6-dimethoxy-1-indanon)-2-yl]methylpiperidine hydrochloride",
              "Mus musculus", "pH 8.0, 25°C", "651163")]


def test_the_resolver_says_a_row_is_filed_under_another_name():
    html = page({"Ki Values": DON_KI})
    r = resolve_kinetic_value("3.1.1.7", "Mus musculus", "donepezil", quantity="ki",
                              **kw(html, "Mus musculus"))
    assert r.found and r.value == 2.2e-06
    assert "which Caterva reads as donepezil: the same compound under another name" in r.chosen_because
    assert any("the same compound under another name" in n for n in r.row_notes)


# -- S5-01, R5V1-3: a paper's signature mutations say whose protein it measured -------------

def test_a_papers_signature_mutations_name_its_isoform():
    html = page({"KM Values": [
        row(0.0298, "Z-Gly-Pro-Arg-p-nitroanilide", "Homo sapiens", "wild type enzyme, pH 8.0, 20°C",
            "678332"),
        row(0.05, "Z-Gly-Pro-Arg-p-nitroanilide", "Homo sapiens", "mutant enzyme R193G, pH 8.0, 20°C",
            "678332")]})
    assert "PRSS3" in row_form.paper_isoforms("3.4.21.4", html)[("homo sapiens", "678332")]
    gck = page({"Turnover Numbers": [
        row(29.0, "2-deoxy-D-glucose", "Homo sapiens", "wild-type enzyme", "672188"),
        row(39, "D-glucose", "Homo sapiens", "mutant enzyme Y214C", "672188")]})
    assert "GCK" in row_form.paper_isoforms("2.7.1.1", gck)[("homo sapiens", "672188")]
