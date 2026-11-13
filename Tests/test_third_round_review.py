"""The third adversarial round of the real-values work (2026-11-12).

Each case is a real BRENDA row set, copied from the live page on 2026-11-12
(value, compound, organism, UniProt cell, commentary and reference as BRENDA
writes them), placed in a page of BRENDA's own markup so the test runs
offline, or the recorded hexokinase page. Each pins a number a professor
would have found wrong, or a report that would have misled one:

- a UniProt outage on the optional fallback-accession lookup aborted the
  whole BRENDA search (every constant a placeholder, exit 3);
- carbonic anhydrase's CA II pair vetoed by a CA III kcat "pick";
- mushroom tyrosinase's Km and kcat from two UniProt entries (PPO3, PPO4);
- IDH1 R132H's 21 C pair over the same paper's 37 C one; fumarase's pH 6.5
  pair over the same paper's pH 7.5 one;
- E. coli adenylate kinase's AMP rows, given as ranges, dropped;
- HK2's kcat taken from a glucokinase paper's row naming no isoform;
- one compound under several spellings (Z-/N-benzyloxycarbonyl-, p-/4-,
  "brequinar sodium") counted as several, and searched under one;
- an albumin-bound lysozyme, a "catalyctic domain" and a paper's
  modification-state series carried over the native enzyme's rows;
- Shp2, Csk, GSTk and tACE rows read as naming no isoform.
"""
from __future__ import annotations

import gzip
from pathlib import Path

import httpx
import pytest

import compound_names
import row_form
from brenda_client import parse_brenda_km_html
from fallback_logic import resolve_kinetic_pair, resolve_kinetic_value
from test_literature_quality import page

RECORDED = Path(__file__).parent / "fixtures" / "recorded"


def row(value, compound, organism, commentary, ref, uniprot="-"):
    text = value if isinstance(value, str) else format(value, ".15f").rstrip("0").rstrip(".")
    return [text, compound, organism, uniprot, commentary, ref]


def kw(html, organism, uniprot_provider=None):
    return dict(html_provider=lambda ec: html,
                uniprot_provider=uniprot_provider or (lambda ec, org: None),
                taxon_id_provider={organism: "1"}.get, search_literature=False)


# -- A UniProt outage is not a failed search ---------------------------------------

DHFR_KM = [row(0.0008, "dihydrofolate", "Escherichia coli", "wild-type, pH 7, 25°C", "765726"),
           row(0.0012, "dihydrofolate", "Escherichia coli", "pH 7.0, 25°C", "700001")]


@pytest.mark.parametrize("failure", [
    httpx.ReadTimeout("read timed out"),
    httpx.HTTPStatusError("503 Backend fetch failed", request=httpx.Request("GET", "https://rest.uniprot.org"),
                          response=httpx.Response(503)),
])
def test_a_uniprot_outage_leaves_the_brenda_rows_measured(failure):
    """DHFR and methotrexate in E. coli (queries 17 and 22) and 17 of 30
    adversary runs: the accession is only stamped on rows with no UniProt
    cell, and its failure ended the search before a row was read."""
    def down(ec, taxon):
        raise failure

    html = page({"KM Values": DHFR_KM})
    r = resolve_kinetic_value("1.5.1.3", "Escherichia coli", "dihydrofolate", quantity="km",
                              **kw(html, "Escherichia coli", down))
    assert r.found and r.value in (0.0008, 0.0012)


# -- One protein per pair ---------------------------------------------------------------

CA_KM = [row(9.3, "CO2", "Homo sapiens", "pH 7.5, 20°C, wild-type", "729384"),
         row(8, "CO2", "Homo sapiens", "pH 7.5, 25°C", "33547"),
         row(10, "CO2", "Homo sapiens", "pH 7.5, 25°C", "33548")]
CA_KCAT = [row(1400000, "CO2", "Homo sapiens", "pH 7.5, 20°C, wild-type", "729384"),
           row(13000, "CO2", "Homo sapiens", "at 20°C and pH 7.5", "699246", "P07451")]
CA_SYNONYMS = [["carbonic anhydrase II", "Homo sapiens", "-", "-", "729384"]]


def test_a_pick_of_another_isozyme_does_not_veto_one_papers_pair():
    """Human carbonic anhydrase (query 5): the kcat "pick" 13000 1/s was CA
    III's (P07451) and the lower of two rows of two isozymes; it set aside
    ref 729384's CA II pair, Km 9.3 mM and kcat 1.4e6 1/s, as "more than
    10-fold from the picks", and the model carried CA II's Km with CA III's
    kcat under a plain GROUNDED."""
    html = page({"KM Values": CA_KM, "Turnover Numbers": CA_KCAT, "Synonyms": CA_SYNONYMS})
    km, kcat = resolve_kinetic_pair("4.2.1.1", "Homo sapiens", "CO2", **kw(html, "Homo sapiens"))
    assert (km.value, kcat.value) == (9.3, 1400000.0)
    assert km.citation.reference_id == kcat.citation.reference_id == "729384"


TYR_KM = [row(0.3703, "L-Dopa", "Agaricus bisporus", "at pH 6.8 and 25°C", "767162", "C7FF04"),
          row(26.1, "L-Dopa", "Agaricus bisporus", "pH 6.8, 25°C, recombinant enzyme", "746472",
              "C7FF05")]
TYR_KCAT = [row(1810, "L-Dopa", "Agaricus bisporus", "pH 6.8, 25°C, recombinant enzyme", "746472",
                "C7FF05")]


def test_two_uniprot_entries_are_two_proteins_even_outside_the_enzyme_index():
    """Mushroom tyrosinase: Km from C7FF04 (PPO3), kcat from C7FF05 (PPO4),
    no isoform concern. A pair of one protein is carried instead."""
    html = page({"KM Values": TYR_KM, "Turnover Numbers": TYR_KCAT})
    km, kcat = resolve_kinetic_pair("1.14.18.1", "Agaricus bisporus", "L-Dopa",
                                    **kw(html, "Agaricus bisporus"))
    assert (km.value, kcat.value) == (26.1, 1810.0)
    assert km.row_uniprot == kcat.row_uniprot == "C7FF05"


# -- A paper's series is read as a series ----------------------------------------

IDH_KM = [row(6, "isocitrate", "Homo sapiens", "mutant enzyme R132H, at pH 7.5 and 21°C", "761477",
              "O75874"),
          row(4.2, "isocitrate", "Homo sapiens", "mutant enzyme R132H, at pH 7.5 and 37°C", "761477",
              "O75874")]
IDH_KCAT = [row(0.12, "isocitrate", "Homo sapiens", "mutant enzyme R132H, at pH 7.5 and 21°C",
                "761477", "O75874"),
            row(2.4, "isocitrate", "Homo sapiens", "mutant enzyme R132H, at pH 7.5 and 37°C", "761477",
                "O75874")]


def test_a_papers_temperature_series_gives_its_assay_temperature_pair():
    """IDH1 R132H (query 42): the 21 C pair (6 mM, 0.12 1/s) was carried over
    the same paper's 37 C pair (4.2 mM, 2.4 1/s): the 37 C kcat lay "far"
    from a kcat pick that was the 21 C row itself."""
    html = page({"KM Values": IDH_KM, "Turnover Numbers": IDH_KCAT})
    km, kcat = resolve_kinetic_pair("1.1.1.42", "Homo sapiens", "isocitrate",
                                    **kw(html, "Homo sapiens"), mutation="R132H")
    assert (km.value, kcat.value) == (4.2, 2.4)


FUM_KM = [row(0.4, "fumarate", "Homo sapiens", "pH 6.5, 25°C", "771047", "P07954"),
          row(0.27, "fumarate", "Homo sapiens", "pH 7.0, 25°C", "771047", "P07954"),
          row(0.37, "fumarate", "Homo sapiens", "pH 7.5, 25°C", "771047", "P07954")]
FUM_KCAT = [row(175, "fumarate", "Homo sapiens", "pH 6.5, 25°C", "771047", "P07954"),
            row(202, "fumarate", "Homo sapiens", "pH 7.0, 25°C", "771047", "P07954"),
            row(370, "fumarate", "Homo sapiens", "pH 7.5, 25°C", "771047", "P07954")]


def test_a_papers_ph_series_gives_its_pair_nearest_ph_7_4():
    """Fumarase (query 48): ref 771047's pH 6.5 pair held the kcat median."""
    html = page({"KM Values": FUM_KM, "Turnover Numbers": FUM_KCAT})
    km, kcat = resolve_kinetic_pair("4.2.1.2", "Homo sapiens", "fumarate",
                                    **kw(html, "Homo sapiens"))
    assert (km.value, kcat.value) == (0.37, 370.0)


# -- A value BRENDA gives as a range ---------------------------------------------------

ADK_KM = [row("0.038 - 0.04", "AMP", "Escherichia coli", "pH 7.4, 27°C", "642585"),
          row(0.85, "2'-dAMP", "Escherichia coli", "pH 7.4, 27°C", "642585")]


def test_a_range_is_one_papers_value_carried_by_its_lower_bound():
    """E. coli adenylate kinase: AMP's only rows are ranges, and both the
    chooser and the resolver dropped them, so 2'-dAMP was modelled."""
    html = page({"KM Values": ADK_KM})
    r = resolve_kinetic_value("2.7.4.3", "Escherichia coli", "AMP", quantity="km",
                              **kw(html, "Escherichia coli"))
    assert r.found and r.value == 0.038
    assert any("range (0.038 - 0.04" in note for note in r.row_notes)


def test_a_range_beside_single_values_of_its_compound_is_not_used():
    """On the recorded hexokinase page "0.057 - 0.061" spans "wild-type and
    nonaggregating interface mutant hexokinase I": a range is evidence of last
    resort, and human D-glucose has 25 single-value rows."""
    html = gzip.decompress((RECORDED / "brenda_2.7.1.1.html.gz").read_bytes()).decode("utf-8")
    rows = parse_brenda_km_html(html, "2.7.1.1", ["D-glucose"], "Homo sapiens", None)
    assert rows and not any(r.value_range for r in rows)


# -- Rows naming no isoform among rows naming only another -----------------------------

def test_hk2s_kcat_is_not_a_glucokinase_papers_row_naming_none():
    """'HK2 with glucose' (query 34): every human D-glucose kcat row that names
    a protein names GCK; ref 672188's "38 | wild-type enzyme", a glucokinase
    Y214C paper's, was carried as HK2's under a plain GROUNDED."""
    html = gzip.decompress((RECORDED / "brenda_2.7.1.1.html.gz").read_bytes()).decode("utf-8")
    r = resolve_kinetic_value("2.7.1.1", "Homo sapiens", "D-glucose", quantity="kcat",
                              isoform="HK2", **kw(html, "Homo sapiens"))
    assert not r.found and r.source == "isoform_withheld"
    # Since the fifth round's polish the paper's Y214C row marks ref 672188
    # as glucokinase's (row_form.ISOFORM_MUTATIONS), so its row is GCK's,
    # not a row naming none among GCK's.
    assert r.isoform_unnamed_withheld > 0 or any("GCK" in iso for iso in r.isoforms_available)


# -- One compound, several spellings -----------------------------------------------------

@pytest.mark.parametrize("a, b", [
    ("Z-Gly-Pro-Arg-p-nitroanilide", "N-benzyloxycarbonyl-Gly-Pro-Arg-4-nitroanilide"),
    ("N-carbobenzyloxy-Gly-Pro-Arg-p-nitroanilide", "Z-Gly-Pro-Arg-4-nitroanilide"),
    ("p-nitrophenyl phosphate", "4-nitrophenyl phosphate"),
    ("2-nitrophenyl-beta-D-galactopyranoside", "2-nitrophenyl beta-D-galactopyranoside"),
    ("N-benzoyl-DL-arginine 4-nitroanilide", "Nalpha-benzoyl-DL-arginine-4-nitroanilide"),
    ("brequinar", "brequinar sodium"), ("GSSG", "glutathione disulfide"),
    ("L-Glu", "L-glutamate"), ("creatine phosphate", "phosphocreatine"),
    ("(S)-malate", "L-malate"), ("D-fructose 1,6-bisphosphate", "D-fructose-1,6-bisphosphate"),
])
def test_spellings_of_one_compound_are_one(a, b):
    assert compound_names.same_compound(a, b)


@pytest.mark.parametrize("a, b", [
    ("D-glucose", "L-glucose"), ("2-deoxy-D-glucose", "D-glucose"), ("pyruvate", "phenylpyruvate"),
    ("N-benzoyl-DL-arginine 4-nitroanilide", "N-benzoyl-L-arginine 4-nitroanilide"),
    ("sodium", "potassium"),
])
def test_different_compounds_stay_different(a, b):
    assert not compound_names.same_compound(a, b)


TRYPSIN_KM = [row(0.0298, "Z-Gly-Pro-Arg-p-nitroanilide", "Homo sapiens",
                  "wild type enzyme, in 20 mM Tricine,10 mM CaCl2, at pH 8.0 and 20°C", "678332"),
              row(0.0361, "N-benzyloxycarbonyl-Gly-Pro-Arg-4-nitroanilide", "Homo sapiens",
                  "pH 8.0, 37°C, uncleaved enzyme, nonsulfated", "772843")]


def test_the_search_takes_every_spelling_and_the_native_row():
    """Trypsin (query 3): the search took only ref 772843's modification-state
    rows, spelled one way, over ref 678332's wild-type row spelled another."""
    html = page({"KM Values": TRYPSIN_KM})
    r = resolve_kinetic_value("3.4.21.4", "Homo sapiens",
                              "N-benzyloxycarbonyl-Gly-Pro-Arg-4-nitroanilide", quantity="km",
                              **kw(html, "Homo sapiens"))
    assert r.found and r.value == 0.0298


# -- What a row is ------------------------------------------------------------------------

@pytest.mark.parametrize("commentary, what", [
    ("human serum albumin-bound enzyme, pH 5.2, 37°C", "an enzyme bound to a carrier"),
    ("reaction catalyzed by the catalyctic domain of the enzyme", "an isolated domain"),
    ("pH 8.0, 37°C, uncleaved enzyme, nonsulfated", "a modification state of the enzyme"),
])
def test_an_altered_preparation_is_read(commentary, what):
    assert (row_form.construct_of(commentary) or "").startswith(what)


@pytest.mark.parametrize("commentary", [
    "free enzyme, pH 5.2, 37°C", "membrane-bound enzyme", "sulfated substrate", "wild type enzyme"])
def test_the_native_enzyme_is_not_an_altered_preparation(commentary):
    assert row_form.construct_of(commentary) is None


LYSO_KM = [row(0.0008, "4-methylumbelliferyl-beta-D-N,N',N''-triacetylchitotrioside", "Gallus gallus",
               "human serum albumin-bound enzyme, pH 5.2, 37°C", "718362"),
           row(0.001, "4-methylumbelliferyl-beta-D-N,N',N''-triacetylchitotrioside", "Gallus gallus",
               "free enzyme, pH 5.2, 37°C", "718362")]


def test_the_free_enzymes_row_is_carried_over_the_albumin_bound_one():
    html = page({"KM Values": LYSO_KM})
    r = resolve_kinetic_value("3.2.1.17", "Gallus gallus",
                              "4-methylumbelliferyl-beta-D-N,N',N''-triacetylchitotrioside",
                              quantity="km", **kw(html, "Gallus gallus"))
    assert r.found and r.value == 0.001


@pytest.mark.parametrize("commentary, reading", [
    ("Ki value for inhibition of wild type Shp2", "SHP-2"),
    ("pH 8.0, 30°C, recombinant wild-type Csk", "Csk"),
    ("pH 7.4, 25°C, recombinant wild-type GSTk", "GSTK1"),
    ("GSTP1-1 wild type", "GSTP1"),
])
def test_a_protein_symbol_in_a_row_names_its_protein(commentary, reading):
    from caterva.bind.core import read_isoform
    assert read_isoform(commentary) == reading


def test_testis_ace_is_said_to_be_testis_ace():
    """ACE (query 30): the carried row is tACE, the one-domain germinal form."""
    from caterva.bind.core import read_isoform
    assert read_isoform("37°C, pH 8.3, tACE").startswith("testis ACE (tACE")


# -- An outlier of one paper is said -------------------------------------------------------

DHODH_KM = [row(0.29, "dihydroorotate", "Homo sapiens", "pH 8.2, 25°C", "762769", "Q02127"),
            row(0.004, "dihydroorotate", "Homo sapiens", "cosubstrate ubiquinone-50", "391233"),
            row(0.009, "dihydroorotate", "Homo sapiens", "cosubstrate decylubiquinone", "391233"),
            row(0.0155, "dihydroorotate", "Homo sapiens", "-", "390921")]


def test_a_single_row_far_from_every_other_papers_rows_is_said_to_be_an_outlier():
    """Human DHODH: 0.29 mM, the only row stating pH and temperature, 20-70x
    above every other paper's rows, carried without a word."""
    html = page({"KM Values": DHODH_KM})
    r = resolve_kinetic_value("1.3.5.2", "Homo sapiens", "dihydroorotate", quantity="km",
                              **kw(html, "Homo sapiens"))
    # Since the fifth round's polish (R5V1-17) the one row stating pH and
    # temperature, more than tenfold from every one of three others, no
    # longer outranks them: the others are kept and their median carried,
    # and the outlier is said.
    assert r.value == 0.009
    assert ("the one row stating both pH and temperature (0.29 mM, BRENDA ref 762769) lies more "
            "than 10-fold from every one of the 3 other rows" in r.chosen_because)
