"""The fifth adversarial round of the real-values work (2026-11-12): which
BRENDA row a constant carries.

Each case is a real BRENDA row set copied from the live page (value,
compound, organism, UniProt cell, commentary and reference as BRENDA writes
them), in a page of BRENDA's own markup so the test runs offline. Each pins a
number a professor would have found wrong:

- human hexokinase built from HK-I's Km and glucokinase's kcat;
- thymidylate synthase's K48Q Km carried because dUMP and 2'-deoxyuridylate
  were counted apart, and "10fold higher than wild-type" read as wild type;
- DPP4's Km of 1.43 mM from the paper whose kcat is 279000 1/s;
- a fumarate reductase (FrdA) Ki carried for succinate dehydrogenase;
- a "heart phosphorylase" row carried for muscle glycogen phosphorylase;
- a fenthion row listing five CYPs' accessions carried as CYP2D6's Km;
- mouse AChE rows with aluminium added to the assay or from treated mice;
- mushroom tyrosinase's 26.1 mM Km carried for pairing with another protein;
- HIV-1 protease's 0.1 M NaCl pair missed for a "pH 4.u" typo;
- pig DAAO's 440 1/s kcat carried as the extreme of the rows stating pH and
  temperature, 40-fold above the wild-type rows stating less;
- "no paper holds a pair" said of ALDH2 while the kcat's paper holds one;
- a predicted zanamivir Ki counted as a literature value;
- bovine GDH's pH 8.5 Km carried over the same paper's pH 7.4 one;
- yeast ADH's Co- and Cu-substituted enzymes counted as native rows.
"""
from __future__ import annotations

import compound_names
import protein_variant
import row_form
from fallback_logic import resolve_kinetic_pair, resolve_kinetic_value
from test_literature_quality import page
from test_third_round_review import kw, row


# -- One protein: a Km and a kcat are never two isozymes' ---------------------------------

HK_KM = [row(0.06, "D-glucose", "Homo sapiens", "hexokinase I, at 37°C, pH 8.1", "640237"),
         row(0.034, "D-glucose", "Homo sapiens", "hexokinase III from lymphocytes, at 37°C, pH 8.1",
             "640261"),
         row(6.0, "D-glucose", "Homo sapiens", "30°C, pH 7.5, wild-type", "641068"),
         row(3.8, "D-glucose", "Homo sapiens", "30°C, pH 7.5", "641067"),
         row(6.3, "D-glucose", "Homo sapiens",
             "wild-type, K0.5 value, Hill coefficient 1.8, pH 7.6, 25 °C", "739603", "P35557")]
HK_KCAT = [row(40.1, "D-glucose", "Homo sapiens", "wild-type, pH 7.6, 25 °C", "739603", "P35557"),
           row(60.4, "D-glucose", "Homo sapiens", "wild type enzyme, in 25 mM HEPES (pH 7.4), at 37°C",
               "703624", "P35557")]


def test_hexokinase_is_one_isozymes_pair_never_two_mixed():
    html = page({"KM Values": HK_KM, "Turnover Numbers": HK_KCAT})
    km, kcat = resolve_kinetic_pair("2.7.1.1", "Homo sapiens", "D-glucose", **kw(html, "Homo sapiens"))
    assert km.row_isoform == "GCK" and kcat.row_isoform == "GCK"
    assert (km.value, kcat.value) == (6.3, 40.1)
    assert "K0.5" in km.chosen_because
    assert "combines two isozymes" not in km.chosen_because


# -- One compound, one variant reading ------------------------------------------------------

def test_a_deoxynucleotide_is_one_compound_under_its_names():
    assert compound_names.same_compound("dUMP", "2'-deoxyuridylate")
    assert compound_names.same_compound("dUMP", "deoxyuridine monophosphate")
    assert compound_names.same_compound("2'-deoxyuridine 5'-monophosphate", "dUMP")
    assert not compound_names.same_compound("dUMP", "dTMP")
    assert not compound_names.same_compound("dUMP", "UMP")


def test_a_value_stated_against_the_wild_type_is_a_variants():
    verdict = protein_variant.classify("10fold higher than wild-type thymidylate synthase")
    assert verdict.status == "variant"
    assert protein_variant.classify("wild-type, pH 7.4").status == "wild_type"


TS_KM = [row(0.05, "dUMP", "Escherichia coli", "10fold higher than wild-type thymidylate synthase",
             "692639", "P0A884"),
         row(0.05, "dUMP", "Escherichia coli", "mutant K48Q", "692639", "P0A884"),
         row(0.0011, "2'-deoxyuridylate", "Escherichia coli", "wild-type, pH 7.4, 25°C", "485422"),
         row(0.0012, "2'-deoxyuridylate", "Escherichia coli", "wild-type, pH 7.4, 25°C", "485426"),
         row(0.004, "2'-deoxyuridylate", "Escherichia coli", "pH 7.4, 25°C", "485357")]


def test_thymidylate_synthase_carries_a_wild_type_dump_km():
    html = page({"KM Values": TS_KM})
    km = resolve_kinetic_value("2.1.1.45", "Escherichia coli", "dUMP", quantity="km",
                               **kw(html, "Escherichia coli"))
    assert km.found and km.value == 0.0012 and km.citation.reference_id != "692639"


# -- A paper with a probable error supplies neither constant --------------------------------

DPP4_KM = [row(0.138, "Gly-Pro-4-nitroanilide", "Homo sapiens",
               "pH 7.4, wild-type soluble enzyme, expressed in Hi5 cells", "653810"),
           row(0.165, "Gly-Pro-4-nitroanilide", "Homo sapiens", "pH 7.6, 30°C, recombinant soluble enzyme",
               "649281"),
           row(1.43, "Gly-Pro-4-nitroanilide", "Homo sapiens", "pH 7.4, wild-type enzyme", "665551", "P27487"),
           row(0.09, "Gly-Pro-4-nitroanilide", "Homo sapiens", "dimeric rDPP-IV", "678195", "P27487")]
DPP4_KCAT = [row(24, "Gly-Pro-4-nitroanilide", "Homo sapiens",
                 "pH 7.4, wild-type soluble enzyme, expressed in Hi5 cells", "653810"),
             row(20, "Gly-Pro-4-nitroanilide", "Homo sapiens",
                 "pH 7.4, wild-type soluble enzyme, expressed in Sf9 cells", "653810"),
             row(279000, "Gly-Pro-4-nitroanilide", "Homo sapiens", "pH 7.4, wild-type enzyme", "665551",
                 "P27487"),
             row(87, "Gly-Pro-4-nitroanilide", "Homo sapiens", "dimeric rDPP-IV", "678195", "P27487")]


def test_dpp4s_km_does_not_come_from_the_paper_of_the_279000_kcat():
    html = page({"KM Values": DPP4_KM, "Turnover Numbers": DPP4_KCAT})
    km, kcat = resolve_kinetic_pair("3.4.14.5", "Homo sapiens", "Gly-Pro-4-nitroanilide",
                                    isoform="DPP4", **kw(html, "Homo sapiens"))
    assert km.citation.reference_id != "665551" and kcat.citation.reference_id != "665551"
    assert (km.value, kcat.value) == (0.09, 87.0)


# Constructed from the shape of human acetyl-CoA carboxylase's rows (merge
# review of the fifth round): one paper's Km is 170-fold below every other
# Km row and is the only row stating pH and temperature. The rule set the
# paper's kcat aside as "a paper with a probable error supplies neither
# constant", yet carried that same paper's Km.
ACC_KM = [row(0.0002, "acetyl-CoA", "Homo sapiens", "pH 7.5, 37°C", "676983"),
          row(0.034, "acetyl-CoA", "Homo sapiens", "", "702459"),
          row(0.048, "acetyl-CoA", "Homo sapiens", "", "676971"),
          row(0.058, "acetyl-CoA", "Homo sapiens", "", "676972")]
ACC_KCAT = [row(0.192, "acetyl-CoA", "Homo sapiens", "pH 7.5, 37°C", "676983"),
            row(10.1, "acetyl-CoA", "Homo sapiens", "", "676971"),
            row(2.9, "acetyl-CoA", "Homo sapiens", "", "702459")]


def test_a_paper_whose_own_row_is_the_probable_error_supplies_neither_constant():
    html = page({"KM Values": ACC_KM, "Turnover Numbers": ACC_KCAT})
    km, kcat = resolve_kinetic_pair("6.4.1.2", "Homo sapiens", "acetyl-CoA", **kw(html, "Homo sapiens"))
    assert km.citation.reference_id != "676983" and kcat.citation.reference_id != "676983"
    # Said either way: as the paper's probable error, or (since the fifth
    # round's polish, R5V1-17) as the one row stating pH and temperature
    # lying more than tenfold from every other, so the rest are kept.
    said = km.chosen_because + " ".join(getattr(km, "search_log", None) or ())
    assert ("its Km (0.0002) lies more than 100-fold from every other row" in said
            or "BRENDA ref 676983: a row of that paper for the paired constant lies more than "
               "100-fold from every other row, a probable error" in said)


# -- Another enzyme filed under the EC is not an isoform -------------------------------------

def test_frda_under_succinate_dehydrogenase_is_another_enzyme():
    assert row_form.other_enzyme("1.3.5.1", "P00363") == "frdA"
    assert row_form.other_enzyme("1.3.5.1", "P0AC41") is None  # sdhA is the enzyme
    assert row_form.other_enzyme("2.7.1.1", "P35557") is None  # GCK is a hexokinase


SDH_KI = [row(0.025, "malonate", "Escherichia coli", "wild-type, pH 7.0, 30°C", "674532", "P00363")]


def test_a_fumarate_reductase_ki_is_not_succinate_dehydrogenases():
    html = page({"Ki Values": SDH_KI})
    ki = resolve_kinetic_value("1.3.5.1", "Escherichia coli", "malonate", quantity="ki",
                               **kw(html, "Escherichia coli"))
    assert not ki.found


# -- A tissue's enzyme is that tissue's isoform ------------------------------------------------

GP_KM = [row(1.7, "glucose 1-phosphate", "Oryctolagus cuniculus", "phosphorylase a", "488247"),
         row(5.5, "glucose 1-phosphate", "Oryctolagus cuniculus", "phosphorylase b", "488285"),
         row(6, "glucose 1-phosphate", "Oryctolagus cuniculus", "heart phosphorylase I and III", "488283"),
         row(8.3, "glucose 1-phosphate", "Oryctolagus cuniculus", "", "488254"),
         row(18, "glucose 1-phosphate", "Oryctolagus cuniculus", "phosphorylase ab", "488287")]


def test_a_heart_phosphorylase_row_is_not_muscle_phosphorylases():
    assert row_form.tissue_isoform_of_row("2.4.1.1", "heart phosphorylase I and III") == "the heart form"
    assert row_form.tissue_isoform_of_row("2.4.1.1", "muscle phosphorylase b") == "PYGM"
    assert row_form.tissue_isoform_of_row("1.1.1.1", "liver enzyme") is None
    html = page({"KM Values": GP_KM})
    km = resolve_kinetic_value("2.4.1.1", "Oryctolagus cuniculus", "glucose 1-phosphate",
                               quantity="km", isoform="PYGM", **kw(html, "Oryctolagus cuniculus"))
    assert km.found and km.citation.reference_id != "488283"


# -- A row listing several proteins is none of them --------------------------------------------

CYP_KM = [row(0.0022, "fenthion", "Homo sapiens", "sulfoxidation to fenthion-sulfoxide", "706823",
              "P10632, P05177, P10635, P20813, P11509"),
          row(0.0081, "fenthion", "Homo sapiens", "CYP2C19, sulfoxidation to fenthion-sulfoxide", "706823",
              "P10632, P05177, P10635, P20813, P11509"),
          row(0.012, "fenthion", "Homo sapiens", "CYP3A4, sulfoxidation to fenthion-sulfoxide", "706823",
              "P10632, P05177, P10635, P20813, P11509")]


def test_an_unattributed_multi_cyp_row_is_not_cyp2d6s():
    html = page({"KM Values": CYP_KM})
    km = resolve_kinetic_value("1.14.14.1", "Homo sapiens", "fenthion", quantity="km",
                               isoform="CYP2D6", **kw(html, "Homo sapiens"))
    assert not km.found


# -- What a row is --------------------------------------------------------------------------

def test_an_assay_additive_and_a_treated_animal_are_not_the_native_enzyme():
    assert row_form.construct_of(
        "pH 7.5, 37°C, addition of aluminium lactate during measurement of activity")
    assert row_form.construct_of("pH 7.5, 37°C, after treatment with NaCl for 3 months")
    assert row_form.construct_of("pH 8, Co-ADH") and row_form.construct_of("Cu-ADH")
    assert row_form.construct_of("pH 7.5, 37°C") is None
    assert row_form.construct_of("CoA added, pH 7") is None


ACHE_KM = [row(0.04, "acetylthiocholine", "Mus musculus", "pH 7.2, 25°C", "666973"),
           row(0.046, "acetylthiocholine", "Mus musculus", "pH 7.0, 22°C, recombinant wild-type enzyme",
               "680690"),
           row(0.46, "acetylthiocholine", "Mus musculus",
               "pH 7.5, 37°C, addition of aluminium lactate during measurement of activity", "650742"),
           row(0.61, "acetylthiocholine", "Mus musculus",
               "pH 7.5, 37°C, addition of AlCl3 during measurement of activity", "650742"),
           row(1.0, "acetylthiocholine", "Mus musculus",
               "pH 7.5, 37°C, after treatment with aluminium lactate for 3 months", "650742"),
           row(2.5, "acetylthiocholine", "Mus musculus",
               "pH 7.5, 37°C, after treatment with NaCl for 3 months", "650742")]


def test_mouse_aches_km_is_a_native_rows():
    html = page({"KM Values": ACHE_KM})
    km = resolve_kinetic_value("3.1.1.7", "Mus musculus", "acetylthiocholine", quantity="km",
                               **kw(html, "Mus musculus"))
    assert km.value in (0.04, 0.046)


def test_a_predicted_value_is_no_measurement():
    assert row_form.predicted("predicted Ki value")
    assert row_form.predicted("kcat calculated from Vmax") is None
    assert row_form.predicted("calculated value, pH 7") is None
    html = page({"Ki Values": [
        row(0.000133, "zanamivir", "Homo sapiens", "predicted Ki value", "699433"),
        row(0.0000001, "zanamivir", "Homo sapiens", "pH 6.5, 37°C", "700385")]})
    ki = resolve_kinetic_value("3.2.1.18", "Homo sapiens", "zanamivir", quantity="ki",
                               **kw(html, "Homo sapiens"))
    assert ki.value == 0.0000001 and "699433" not in (ki.chosen_because or "")


# -- Pairs ------------------------------------------------------------------------------------

TYR_KM = [row(v, "L-DOPA", "Agaricus bisporus", c, r) for v, c, r in (
    (0.17, "pH 7.0, 25°C", "697659"), (0.172, "pH 6.8, 25°C", "744671"),
    (0.28, "pH 6.8, 25°C", "767494"), (0.36, "pH 6.8, 30°C", "696757"),
    (0.933, "pH 7.0, 35°C", "744818"), (1.347, "pH 7.4, 30°C", "744014"))] + [
    row(0.3703, "L-DOPA", "Agaricus bisporus", "at pH 6.8 and 25°C", "767162", "C7FF04"),
    row(26.1, "L-DOPA", "Agaricus bisporus", "pH 6.8, 25°C, recombinant enzyme", "746472", "C7FF05")]
TYR_KCAT = [row(1810, "L-DOPA", "Agaricus bisporus", "pH 6.8, 25°C, recombinant enzyme", "746472",
                "C7FF05")]


def test_another_proteins_pair_is_not_carried_far_from_every_row():
    html = page({"KM Values": TYR_KM, "Turnover Numbers": TYR_KCAT})
    km, kcat = resolve_kinetic_pair("1.14.18.1", "Agaricus bisporus", "L-DOPA",
                                    **kw(html, "Agaricus bisporus"))
    assert km.value != 26.1
    # The pair passed over is said, with how far its Km lies.
    assert "26.1" in km.chosen_because and "746472" in km.chosen_because


HIV = "2-aminobenzoyl-TI-Nle-Phe(NO2)-QR"
HIV_KM = [row(0.0152, HIV, "Human immunodeficiency virus 1", "pH 4.u, 0.1 M NaCl", "648156"),
          row(0.00873, HIV, "Human immunodeficiency virus 1", "pH 4.9, 1.0 M NaCl", "648156"),
          row(0.00598, HIV, "Human immunodeficiency virus 1", "pH 5.0, 2.0 M NaCl", "648156")]
HIV_KCAT = [row(5.8, HIV, "Human immunodeficiency virus 1", "pH 4.8, 0.1 M NaCl", "648156"),
            row(9.25, HIV, "Human immunodeficiency virus 1", "pH 4.9, 1.0 M NaCl", "648156"),
            row(19.5, HIV, "Human immunodeficiency virus 1", "pH 5.0, 2.0 M NaCl", "648156")]


def test_an_unreadable_ph_does_not_hide_the_near_physiological_salt_pair():
    assert row_form.garbled_ph("pH 4.u, 0.1 M NaCl") == 4
    assert row_form.garbled_ph("pH 4.8, 0.1 M NaCl") is None
    html = page({"KM Values": HIV_KM, "Turnover Numbers": HIV_KCAT})
    km, kcat = resolve_kinetic_pair("3.4.23.16", "Human immunodeficiency virus 1", HIV,
                                    **kw(html, "Human immunodeficiency virus 1"))
    assert (km.value, kcat.value) == (0.0152, 5.8)
    assert "salt series" in km.chosen_because and "unreadably" in km.chosen_because


DAAO_KM = [row(1.7, "D-alanine", "Sus scrofa", "pH 8.5, 25°C", "655117"),
           row(2.0, "D-alanine", "Sus scrofa", "at pH 8.3 and 25°C", "686277")]
DAAO_KCAT = [row(440, "D-alanine", "Sus scrofa", "pH 8.5, 25°C", "655117"),
             row(10, "D-alanine", "Sus scrofa", "at pH 8.3 and 25°C", "686277"),
             row(133.3, "D-alanine", "Sus scrofa", "pH 8.5, 37°C", "743827"),
             row(151.2, "D-alanine", "Sus scrofa", "pH 7.5, 37°C", "743827"),
             row(6.5, "D-alanine", "Sus scrofa", "wild-type", "674365"),
             row(8.5, "D-alanine", "Sus scrofa", "wild-type", "391854"),
             row(12.7, "D-alanine", "Sus scrofa", "wild-type", "391860"),
             row(7.3, "D-alanine", "Sus scrofa", "apparent value, at 25°C", "686020")]


def test_a_pair_is_not_the_extreme_of_a_few_rows_far_from_the_rest():
    html = page({"KM Values": DAAO_KM, "Turnover Numbers": DAAO_KCAT})
    km, kcat = resolve_kinetic_pair("1.4.3.3", "Sus scrofa", "D-alanine", **kw(html, "Sus scrofa"))
    assert kcat.value < 30 and kcat.value != 440


ALDH_KM = [row(0.00048, "acetaldehyde", "Homo sapiens", "ALDH2, at pH 7.5 and 37°C", "684721"),
           row(0.2, "acetaldehyde", "Homo sapiens", "enzyme ALDH-2, pH 9.5", "348688")]
ALDH_KCAT = [row(19.7, "acetaldehyde", "Homo sapiens", "enzyme form ALDH-2, pH 9.5", "348688")]


def test_the_kcats_own_papers_km_is_said():
    html = page({"KM Values": ALDH_KM, "Turnover Numbers": ALDH_KCAT})
    km, kcat = resolve_kinetic_pair("1.2.1.3", "Homo sapiens", "acetaldehyde",
                                    **kw(html, "Homo sapiens"))
    assert "no paper holds a Km row" not in km.chosen_because
    assert "348688" in km.chosen_because and "0.2" in km.chosen_because


GDH_KM = [row(0.24, "L-glutamate", "Bos taurus", "at pH 8.5, 25°C", "671289"),
          row(1.01, "L-glutamate", "Bos taurus", "at pH 7.4, 25°C", "671289")]


def test_one_papers_ph_pair_is_read_nearest_ph_7_4():
    html = page({"KM Values": GDH_KM})
    km = resolve_kinetic_value("1.4.1.3", "Bos taurus", "L-glutamate", quantity="km",
                               **kw(html, "Bos taurus"))
    assert km.value == 1.01 and "nearest pH 7.4" in km.chosen_because
