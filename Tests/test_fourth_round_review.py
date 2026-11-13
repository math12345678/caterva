"""The fourth adversarial round of the real-values work (2026-11-12).

Each case is a real BRENDA row set copied from the live page (value, compound,
organism, UniProt cell, commentary and reference as BRENDA writes them), in a
page of BRENDA's own markup so the test runs offline. Each pins a number a
professor would have found wrong:

- caspase-3's Ac-DEVD-pNA pair, filed under the three-letter spelling;
  human trypsin's BAPNA pair under "benzoyl-DL-Arg-p-nitroanilide"; L-NMMA,
  DFMO, galantamine and donepezil under the names their papers used;
- PKM2's Km measured with the activator FBP present, carried as the Km;
- DPP4's kcat of 279000 1/s, 3000-fold from every other row, carried
  because its row named the isoform;
- Candida rugosa lipase's 0.00017 mM beside 0.17 mM, the sub-micromolar
  row taken as "the lower of the two middle values";
- HIV-1 protease's 2.0 M NaCl pair carried over the same paper's 1.0 M one;
- chymotrypsin's unlabelled row carried over the same paper's wild-type row;
- human hexokinase's HK-I Km traded for glucokinase's K0.5;
- NOS2's L-NMMA rows ("inducible isoform from macrophage") withheld as
  another isozyme's; PTPalpha rows counted as PTP1B's; CA I's "low activity
  carbonic anhydrase" rows counted as CA II's.
"""
from __future__ import annotations

import pytest

import compound_names
import effector
import fallback_logic
from fallback_logic import resolve_kinetic_pair, resolve_kinetic_value
from test_literature_quality import page
from test_third_round_review import kw, row


# -- One compound, the names papers and readers use -------------------------------------

@pytest.mark.parametrize("a, b", [
    ("Ac-DEVD-pNA", "acetyl-L-Asp-L-Glu-L-Val-L-Asp-4-nitroanilide"),
    ("acetyl-DEVD-4-nitroanilide", "acetyl-L-Asp-L-Glu-L-Val-L-Asp-4-nitroanilide"),
    ("acetyl-DEVD-AMC", "acetyl-L-Asp-L-Glu-L-Val-L-Asp-7-amido-4-methylcoumarin"),
    ("Suc-AAPF-pNA", "N-succinyl-L-alanyl-L-alanyl-L-prolyl-L-phenylalanine p-nitroanilide"),
    ("benzoyl-DL-Arg-p-nitroanilide", "N-benzoyl-DL-arginine 4-nitroanilide"),
    ("BAPNA", "benzoyl-DL-Arg-p-nitroanilide"),
    ("L-NMMA", "Ngamma-monomethyl-L-arginine"),
    ("DFMO", "alpha-difluoromethylornithine"),
    ("galantamine", "galanthamine"),
    ("donepezil", "(R,S)-1-benzyl-4-[(5,6-dimethoxy-1-indanon)-2-yl]methylpiperidine hydrochloride"),
    ("O2-", "O2.-"), ("superoxide", "O2-"),
    ("arachidonate", "arachidonic acid"), ("D-Ala", "D-alanine"), ("L-Orn", "L-ornithine"),
    ("adrenaline", "epinephrine"), ("HMG-CoA", "hydroxymethylglutaryl-CoA"),
    ("H-D-Phe-Pip-Arg-pNA", "D-Phe-Pip-Arg-pNA"),
])
def test_one_compound_under_the_names_papers_and_readers_use(a, b):
    assert compound_names.same_compound(a, b)


@pytest.mark.parametrize("a, b", [
    ("N-benzoyl-DL-arginine 4-nitroanilide", "N-benzoyl-L-arginine 4-nitroanilide"),
    ("L-NMMA", "L-NAME"), ("D-Ala", "L-Ala"), ("acetyl-DEVD-pNA", "acetyl-YVAD-pNA"),
    ("S-adenosyl-L-methionine", "L-methionine"), ("L-arginine", "D-arginine"),
])
def test_different_compounds_stay_different(a, b):
    assert not compound_names.same_compound(a, b)


CASPASE_KM = [row(0.011, "acetyl-DEVD-4-nitroanilide", "Homo sapiens", "pH 7.4, 37°C", "647471"),
              row(0.067, "acetyl-L-Asp-L-Glu-L-Val-L-Asp-4-nitroanilide", "Homo sapiens",
                  "pH 7.5, 22°C", "669888")]
CASPASE_KCAT = [row(0.88, "acetyl-L-Asp-L-Glu-L-Val-L-Asp-4-nitroanilide", "Homo sapiens",
                    "pH 7.5, 22°C", "669888")]


def test_caspase_3s_pair_is_reached_under_the_one_letter_name():
    html = page({"KM Values": CASPASE_KM, "Turnover Numbers": CASPASE_KCAT})
    km, kcat = resolve_kinetic_pair("3.4.22.56", "Homo sapiens", "acetyl-DEVD-4-nitroanilide",
                                    **kw(html, "Homo sapiens"))
    assert kcat.found and kcat.value == 0.88
    assert km.found and km.citation.reference_id == "669888"


# -- An activator present makes an apparent constant ------------------------------------

def test_activation_by_is_an_activator_present():
    (found,) = effector.extract_effectors("pH 8.0, 32°C, activation by 2 mM D-fructose-1,6-bisphosphate")
    assert found.presence == "present" and found.role == "activator"


PK_KM = [row(0.17, "phosphoenolpyruvate", "Homo sapiens",
             "pH 8.0, 32°C, activation by 2 mM D-fructose-1,6-bisphosphate", "661215", "P14618"),
         row(2.1, "phosphoenolpyruvate", "Homo sapiens", "pH 8.0, 32°C", "661215", "P14618"),
         row(0.13, "phosphoenolpyruvate", "Homo sapiens",
             "wild type enzyme, in the presence of K+, in 50 mM Mes-Tris, pH 6.0, at 25°C", "674499")]
PK_KCAT = [row(1182, "phosphoenolpyruvate", "Homo sapiens",
               "wild type enzyme, in the presence of K+, in 50 mM Mes-Tris, pH 6.0, at 25°C", "674499")]


def test_pkm2s_fbp_activated_km_is_not_the_km_and_the_kcats_paper_gives_its_pair():
    html = page({"KM Values": PK_KM, "Turnover Numbers": PK_KCAT})
    km, kcat = resolve_kinetic_pair("2.7.1.40", "Homo sapiens", "phosphoenolpyruvate",
                                    **kw(html, "Homo sapiens"))
    assert km.value != 0.17
    assert (km.value, kcat.value) == (0.13, 1182)
    assert km.citation.reference_id == kcat.citation.reference_id == "674499"


def test_a_bare_inhibitor_at_a_concentration_is_present():
    from types import SimpleNamespace

    entry = SimpleNamespace(effectors=[], conditions=(
        "0.008 mM inhibitor 3-(3,5-dibromo)-4-hydroxybenzylidine-5-iodo-1,3-dihydro-indol-2-one"))
    assert fallback_logic._inhibitors_in_assay(entry, frozenset()) == [
        "3-(3,5-dibromo)-4-hydroxybenzylidine-5-iodo-1,3-dihydro-indol-2-one"]


# -- Rows that are probable errors ------------------------------------------------------

def test_a_row_no_other_comes_near_is_isolated():
    assert fallback_logic.isolated([20, 24, 87, 279000]) == [3]
    assert fallback_logic.isolated([7.18, 93, 6500]) == []
    assert fallback_logic.isolated([0.17, 0.00017]) == []  # two rows: neither can be told


CRL_KM = [row(0.00017, "4-nitrophenyl palmitate", "Diutina rugosa", "free enzyme, pH 7.0, 37°C", "714870"),
          row(0.17, "4-nitrophenyl palmitate", "Diutina rugosa", "pH 7.0, 37°C, free enzyme", "678010"),
          row(0.136, "4-nitrophenyl palmitate", "Diutina rugosa",
              "pH 7.0, 37°C, enzyme immobilized with glutaraldehyde", "678010"),
          row(0.274, "4-nitrophenyl palmitate", "Diutina rugosa",
              "pH 7.0, 37°C, enzyme immobilized with carbonyldiimidazole", "678010")]


def test_a_thousandfold_pair_is_told_apart_by_the_other_rows():
    html = page({"KM Values": CRL_KM})
    r = resolve_kinetic_value("3.1.1.3", "Diutina rugosa", "4-nitrophenyl palmitate", quantity="km",
                              **kw(html, "Diutina rugosa"))
    assert r.value == 0.17
    assert "signature of a unit slip" in r.chosen_because


# -- Series, labels and pairs ----------------------------------------------------------

HIV_KM = [row(0.00598, "2-aminobenzoyl-TI-Nle-Phe(NO2)-QR", "Human immunodeficiency virus 1",
              "pH 5.0, 2.0 M NaCl", "648156"),
          row(0.00873, "2-aminobenzoyl-TI-Nle-Phe(NO2)-QR", "Human immunodeficiency virus 1",
              "pH 4.9, 1.0 M NaCl", "648156")]
HIV_KCAT = [row(19.5, "2-aminobenzoyl-TI-Nle-Phe(NO2)-QR", "Human immunodeficiency virus 1",
                "pH 5.0, 2.0 M NaCl", "648156"),
            row(9.25, "2-aminobenzoyl-TI-Nle-Phe(NO2)-QR", "Human immunodeficiency virus 1",
                "pH 4.9, 1.0 M NaCl", "648156")]


def test_a_salt_series_is_read_nearest_a_cells_ionic_strength():
    html = page({"KM Values": HIV_KM, "Turnover Numbers": HIV_KCAT})
    km, kcat = resolve_kinetic_pair("3.4.23.16", "Human immunodeficiency virus 1",
                                    "2-aminobenzoyl-TI-Nle-Phe(NO2)-QR",
                                    **kw(html, "Human immunodeficiency virus 1"))
    assert (km.value, kcat.value) == (0.00873, 9.25)


CHYMO_KM = [row(0.304, "N-succinyl-L-alanyl-L-alanyl-L-prolyl-L-phenylalanine p-nitroanilide",
                "Homo sapiens", "pH 8, temperature not specified in the publication", "769319"),
            row(0.575, "N-succinyl-L-alanyl-L-alanyl-L-prolyl-L-phenylalanine p-nitroanilide",
                "Homo sapiens", "wild-type, pH 8, temperature not specified in the publication",
                "769319")]


def test_a_papers_labelled_wild_type_beats_its_unlabelled_row():
    html = page({"KM Values": CHYMO_KM})
    r = resolve_kinetic_value("3.4.21.1", "Homo sapiens",
                              "N-succinyl-L-alanyl-L-alanyl-L-prolyl-L-phenylalanine p-nitroanilide",
                              quantity="km", **kw(html, "Homo sapiens"))
    assert r.value == 0.575


HK_KM = [row(0.06, "D-glucose", "Homo sapiens", "hexokinase I, at 37°C, pH 8.1", "640237"),
         row(6.3, "D-glucose", "Homo sapiens", "wild-type, K0.5 value, Hill coefficient 1.8, pH 7.6, 25 °C",
             "739603", "P35557")]
HK_KCAT = [row(40.1, "D-glucose", "Homo sapiens", "wild-type, pH 7.6, 25 °C", "739603", "P35557")]


def test_a_native_km_is_not_traded_for_another_isozymes_k05():
    html = page({"KM Values": HK_KM, "Turnover Numbers": HK_KCAT})
    km, kcat = resolve_kinetic_pair("2.7.1.1", "Homo sapiens", "D-glucose", **kw(html, "Homo sapiens"))
    assert km.value == 0.06 and km.row_isoform == "HK-I"
    assert "combines two isozymes' constants" in km.chosen_because


def test_a_ki_measured_on_another_assay_substrate_is_said():
    note = fallback_logic._row_notes(type("E", (), {
        "conditions": "pH 8.0, 37°C, wild-type enzyme, hydrolysis of o-aminobenzoyl-SDK-(dinitrophenyl)-P-OH",
        "substrate": "captopril", "value_range": None, "ec_number": "3.4.15.1", "uniprot": None,
        "reference_id": "650001", "inhibitors_present": [], "paper_isoform": None,
        "uniprot_from_row": False, "variant": None})(), "ki")
    assert any("hydrolysis of o-aminobenzoyl-SDK" in n for n in note)


def test_an_irreversible_inactivator_is_said_to_be_one():
    assert fallback_logic.IRREVERSIBLE_INHIBITOR.search("L-Phe-L-Pro-L-Arg-chloromethylketone")
    assert fallback_logic.IRREVERSIBLE_INHIBITOR.search("selegiline")
    assert not fallback_logic.IRREVERSIBLE_INHIBITOR.search("argatroban")
