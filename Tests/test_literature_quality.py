"""The layer that turns BRENDA rows into the number a model carries (ADR 0182).

Professors will check these numbers against the papers. A wrong number
labelled "literature" is worse than a placeholder, so each test here pins one
way a real BRENDA row was turned into a wrong number before 2026-11-11, and
the rule that now prevents it:

- ORGANISM. The parser matched the target organism as a substring of the
  whole row and relabelled the row with the target: "Homo s" matched every
  human row and was printed as "Homo s"; a commentary reading "expressed in
  Escherichia coli" made a yeast row an E. coli one. Matching is now exact on
  the organism cell's binomial, and the row keeps BRENDA's own spelling.
- TABLE. A page with no "Turnover Numbers" table (EC 2.7.10.1) was scanned
  whole and gave ~580 "turnover numbers" read from its Km, IC50 and inhibitor
  tables. A table the page's navigation does not list now yields nothing.
- SUBSTRATE. "D-glucose" was a substring match, so 2-deoxy-D-glucose and
  beta-D-glucose rows were labelled D-glucose. The whole compound is matched.
- REFERENCE. Only six-digit cells were references, so five-digit BRENDA
  references were lost, and a six-digit VALUE was cited as a reference.
- THE PICK. `min()` over the frontier carried kcat 1e-06 1/s for human
  carbonic anhydrase (true ~1e6). Now: implausible values set aside, complete
  assay conditions and non-mutants preferred, the control arm of a paper's
  presence/absence experiment preferred, then the MEDIAN row -- a real row
  with a real reference, never an average -- and a Km/kcat pair from one
  paper when one exists. A spread over 100-fold is recorded for the report.
- ISOFORM. "isozyme CA II" read as "CA", so CA I and CA II matched each
  other; "hCA II", "P450 2B6" and "PDE5" were not read at all.

Offline: synthetic pages built below in BRENDA's own markup, and the recorded
hexokinase page (fixtures/recorded/brenda_2.7.1.1.html.gz).
"""
from __future__ import annotations

import gzip
from pathlib import Path

import pytest

import brenda_client as bc
from brenda_client import (
    organism_matches,
    parse_brenda_ki_html,
    parse_brenda_km_html,
    parse_brenda_turnover_html,
    substrate_matches,
)
from fallback_logic import resolve_kinetic_pair, resolve_kinetic_value

RECORDED_HK = Path(__file__).parent / "fixtures" / "recorded" / "brenda_2.7.1.1.html.gz"


def recorded_hexokinase() -> str:
    return gzip.decompress(RECORDED_HK.read_bytes()).decode("utf-8", errors="replace")


# -- A page in BRENDA's markup ------------------------------------------------
#
# BRENDA's navigation links each table to a container by
# "javascript:showTable('tabN')", and every table uses the same div.row /
# div.cell markup: value | compound | organism | uniprot | commentary | ref.

_TAB_IDS = {"KM Values": "tab12", "Turnover Numbers": "tab44", "kcat/KM Values": "tab305",
            "Ki Values": "tab49", "IC50 Values": "tab54", "Inhibitors": "tab11"}


def page(tables: dict) -> str:
    """A BRENDA-shaped page holding `tables` ({label: [row cells, ...]})."""
    nav = "".join(f"<a href=\"javascript:showTable('{_TAB_IDS[label]}')\">{label}</a>"
                  for label in tables)
    body = []
    for label, rows in tables.items():
        cells = "".join(
            f'<div class="row" id="{_TAB_IDS[label]}r{i}">'
            + "".join(f'<div class="cell">{c}</div>' for c in row) + "</div>"
            for i, row in enumerate(rows))
        body.append(f'<div id="{_TAB_IDS[label]}" class="equal">{cells}</div>')
    return f"<html><body><nav>{nav}</nav>{''.join(body)}</body></html>"


def row(value, compound, organism="Homo sapiens", commentary="pH 7.5, 25°C", ref="700001"):
    """One data row. The value is written as BRENDA writes it, in plain
    decimals ("0.000001", never "1e-06")."""
    text = value if isinstance(value, str) else format(value, ".12f").rstrip("0").rstrip(".")
    return [text, compound, organism, "-", commentary, ref]


def resolve(html, substrate, quantity, organism="Homo sapiens", **kw):
    return resolve_kinetic_value(
        "9.9.9.9", organism, substrate, quantity=quantity,
        html_provider=lambda ec: html, uniprot_provider=lambda ec, org: None,
        taxon_id_provider={"Homo sapiens": "9606"}.get, search_literature=False, **kw)


# -- Organism ------------------------------------------------------------------


class TestTheOrganismIsMatchedExactlyAndLabelledAsBrendaWritesIt:
    def test_a_partial_name_matches_no_row(self):
        assert not organism_matches("Homo sapiens", "Homo s")
        assert not organism_matches("Homo sapiens", "Homo")

    def test_the_binomial_matches_in_any_case_and_with_a_strain_after_it(self):
        assert organism_matches("Homo sapiens", "homo SAPIENS")
        assert organism_matches("Escherichia coli K-12", "Escherichia coli")
        assert organism_matches("Brassica rapa subsp. oleifera", "Brassica rapa")
        assert not organism_matches("Escherichia coli", "Escherichia coli K-12")

    def test_a_commentary_is_not_an_organism_cell(self):
        assert not organism_matches("Escherichia coli, pH 7.5, 25°C", "Escherichia coli")

    def test_homo_s_finds_no_human_hexokinase_row_on_the_recorded_page(self):
        """`--organism "Homo S"` became "Homo s", which matched all of human
        hexokinase's rows by substring and printed them as "Homo s"."""
        html = recorded_hexokinase()
        assert parse_brenda_km_html(html, "2.7.1.1", ["D-glucose"], "Homo s") == []
        human = parse_brenda_km_html(html, "2.7.1.1", ["D-glucose"], "homo sapiens")
        assert human and {e.organism for e in human} == {"Homo sapiens"}

    def test_a_row_naming_the_organism_only_in_its_commentary_is_not_that_organisms(self):
        html = page({"KM Values": [
            row(0.4, "ampicillin", "Saccharomyces cerevisiae",
                "recombinant enzyme expressed in Escherichia coli, pH 7, 25°C"),
            row(0.05, "ampicillin", "Escherichia coli", "pH 7, 25°C", "700002"),
        ]})
        rows = parse_brenda_km_html(html, "3.5.2.6", ["ampicillin"], "Escherichia coli")
        assert [(e.km_value, e.organism) for e in rows] == [(0.05, "Escherichia coli")]

    def test_a_strain_row_keeps_its_strain_in_the_label(self):
        html = page({"KM Values": [row(0.05, "ampicillin", "Escherichia coli K-12")]})
        rows = parse_brenda_km_html(html, "3.5.2.6", ["ampicillin"], "Escherichia coli")
        assert [e.organism for e in rows] == ["Escherichia coli K-12"]


# -- Table boundaries ----------------------------------------------------------


class TestEachParserReadsOnlyItsOwnTable:
    HTML = page({
        "KM Values": [row(0.5, "ATP")],
        "kcat/KM Values": [row(120, "ATP", ref="700005")],
        "Ki Values": [row(0.3, "ATP", ref="700002")],
        "IC50 Values": [row(0.02, "ATP", ref="700003")],
        "Inhibitors": [["erlotinib", "Homo sapiens", "-", "competitive", "700004"]],
    })

    def test_a_page_with_no_turnover_table_gives_no_turnover_numbers(self):
        """EC 2.7.10.1 has no Turnover Numbers table; the whole-page scan
        returned ~580 rows from its other tables (measured live 2026-11-11)."""
        assert parse_brenda_turnover_html(self.HTML, "2.7.10.1", [], None,
                                          require_substrate_match=False) == []
        assert parse_brenda_turnover_html(self.HTML, "2.7.10.1", ["ATP"], "Homo sapiens") == []

    def test_km_ki_and_turnover_each_read_their_own_rows(self):
        both = page({"KM Values": [row(0.5, "ATP")],
                     "Turnover Numbers": [row(61, "ATP", ref="700006")],
                     "kcat/KM Values": [row(120, "ATP", ref="700005")],
                     "Ki Values": [row(0.3, "ATP", ref="700002")]})
        assert [e.km_value for e in parse_brenda_km_html(both, "x", ["ATP"])] == [0.5]
        assert [e.km_value for e in parse_brenda_turnover_html(both, "x", ["ATP"])] == [61.0]
        assert [e.km_value for e in parse_brenda_ki_html(both, "x", ["ATP"])] == [0.3]

    def test_a_page_with_no_ki_table_gives_no_ki(self):
        html = page({"KM Values": [row(0.5, "ATP")]})
        assert parse_brenda_ki_html(html, "x", [], None, require_substrate_match=False) == []

    def test_a_page_without_any_navigation_is_still_scanned_and_marked_unscoped(self):
        """The cut-down fixture case the whole-page fallback exists for."""
        bare = ('<html><body><div class="row">' + "".join(
            f'<div class="cell">{c}</div>' for c in row(0.5, "ATP")) + "</div></body></html>")
        rows = parse_brenda_km_html(bare, "x", ["ATP"])
        assert [e.km_value for e in rows] == [0.5] and rows[0].table_scoped is False

    def test_the_recorded_hexokinase_page_has_a_turnover_table_and_reads_it(self):
        rows = parse_brenda_turnover_html(recorded_hexokinase(), "2.7.1.1", ["D-glucose"])
        assert rows and all(e.unit == "1/s" and e.table_scoped for e in rows)


# -- Substrate and reference ---------------------------------------------------


class TestTheSubstrateIsTheWholeCompound:
    def test_a_compound_containing_the_name_is_another_compound(self):
        assert not substrate_matches("2-deoxy-D-glucose", "D-glucose")
        assert not substrate_matches("beta-D-glucose", "D-glucose")
        assert not substrate_matches("phenylpyruvate", "pyruvate")
        assert not substrate_matches("(E)-5-styrylisatin", "isatin")

    def test_spelling_counter_ion_and_an_unasked_stereo_descriptor_still_match(self):
        assert substrate_matches("acetyl thiocholine", "acetylthiocholine")
        assert substrate_matches("acetylthiocholine iodide", "acetylthiocholine")
        assert substrate_matches("(S)-lactate", "lactate")
        assert substrate_matches("D-Glucose", "d-glucose")

    def test_the_recorded_human_d_glucose_pools_hold_only_d_glucose(self):
        """Before: 5 of 30 Km rows were 2-deoxy-D-glucose and 17 of 78 kcat
        rows beta- or 2-deoxy-D-glucose, every one labelled D-glucose."""
        html = recorded_hexokinase()
        km = parse_brenda_km_html(html, "2.7.1.1", ["D-glucose"], "Homo sapiens")
        kcat = parse_brenda_turnover_html(html, "2.7.1.1", ["D-glucose"], "Homo sapiens")
        assert len(km) == 25 and len(kcat) == 61
        assert {e.substrate for e in km + kcat} == {"D-glucose"}

    def test_a_row_matched_through_a_stereo_descriptor_keeps_brendas_name(self):
        html = recorded_hexokinase()
        labels = {e.substrate for e in
                  parse_brenda_turnover_html(html, "2.7.1.1", ["glucose"], "Homo sapiens")}
        assert labels == {"D-glucose", "beta-D-glucose"}

    def test_a_row_with_no_compound_cell_is_matched_on_the_whole_name_too(self):
        """Found in review: a row whose organism sits in cell 1 (EC 3.1.1.7's
        layout) has no compound cell, and the match on its text was still a
        substring, so a commentary naming 2-deoxy-D-glucose made it a
        D-glucose row and phenylpyruvate a pyruvate one."""
        html = page({"KM Values": [
            ["0.5", "Homo sapiens", "-", "with 2-deoxy-D-glucose, pH 7.5, 25°C", "700001"],
            ["0.7", "Homo sapiens", "-", "with D-glucose, pH 7.5, 25°C", "700002"],
            ["0.9", "Homo sapiens", "-", "phenylpyruvate, pH 7, 30°C", "700003"],
            ["1.1", "Homo sapiens", "-", "acetyl thiocholine, pH 7, 30°C", "700004"],
        ]})
        glucose = parse_brenda_km_html(html, "2.7.1.1", ["D-glucose"], "Homo sapiens")
        assert [(e.km_value, e.substrate) for e in glucose] == [(0.7, "D-glucose")]
        assert parse_brenda_km_html(html, "2.7.1.1", ["pyruvate"], "Homo sapiens") == []
        spaced = parse_brenda_km_html(html, "3.1.1.7", ["acetylthiocholine"], "Homo sapiens")
        assert [(e.km_value, e.substrate) for e in spaced] == [(1.1, "acetylthiocholine")]
        assert bc.substrate_named_in("with (S)-lactate, pH 7", "lactate") == "(S)-lactate"

    def test_the_form_a_row_measured_is_said_when_the_request_named_none(self):
        """Found in review: the report prints the compound typed beside the
        number, so a "(R)-lactate" row carried for "lactate" must say which
        form it measured."""
        html = page({"KM Values": [row(0.5, "(S)-lactate"),
                                   row(0.7, "(R)-lactate", ref="700002"),
                                   row(0.9, "(S)-lactate", ref="700003")]})
        r = resolve(html, "lactate", "km")
        assert r.value == 0.7
        assert "BRENDA names this row's compound '(R)-lactate'" in r.chosen_because
        same = resolve(page({"KM Values": [row(0.5, "acetylthiocholine iodide")]}),
                       "acetylthiocholine", "km")
        assert "names this row's compound" not in same.chosen_because


class TestTheReferenceIsTheReferenceCell:
    def test_five_digit_and_listed_references_are_read_and_a_value_never_is(self):
        html = page({"Turnover Numbers": [
            row(217, "CO2", commentary="pH 6.3, MES buffer", ref="33572"),
            row(130000, "CO2", commentary="-", ref="33536"),
            row(150000, "CO2", commentary="-", ref="697525,701131"),
        ]})
        got = [(e.km_value, e.reference_id, e.conditions)
               for e in parse_brenda_turnover_html(html, "4.2.1.1", ["CO2"])]
        assert got == [(217.0, "33572", "pH 6.3, MES buffer"),
                       (130000.0, "33536", None),
                       (150000.0, "697525", None)]


# -- The pick ------------------------------------------------------------------


class TestThePickIsTheMedianOfTheBestDescribedRows:
    def test_an_implausible_kcat_is_set_aside_and_named(self):
        """Human carbonic anhydrase and CO2 carried 1e-06 1/s, the minimum of
        rows reaching 1.4e6, as GROUNDED."""
        html = page({"Turnover Numbers": [
            row(1e-06, "CO2", ref="729224"), row(13000, "CO2", ref="699246"),
            row(600000, "CO2", ref="775944"), row(1400000, "CO2", ref="696613")]})
        r = resolve(html, "CO2", "kcat")
        assert r.value == 600000 and r.citation.reference_id == "775944"
        assert r.set_aside == [{
            "value": 1e-06, "unit": "1/s", "reference_id": "729224",
            "reason": "1e-06 1/s is below the physically plausible range for a kcat "
                      "(0.001 to 1e+08 1/s)"}]
        assert "physically implausible" in r.chosen_because
        assert sorted(c["value"] for c in r.ensemble_candidates) == [13000, 600000, 1400000]

    def test_an_implausible_km_is_set_aside_too(self):
        html = page({"KM Values": [row(5e-08, "X", ref="700001"), row(0.2, "X", ref="700002"),
                                   row(0.4, "X", ref="700003"), row(0.9, "X", ref="700004")]})
        assert resolve(html, "X", "km").value == 0.4

    def test_when_every_row_is_implausible_none_is_reported_and_each_is_named(self):
        """With no plausible row to prefer, the pick would still be a number
        no enzyme has. It is withheld, never reported as a measurement, and
        the rows are named so a reader can check them."""
        html = page({"Turnover Numbers": [row(1e-05, "X", ref="700001"), row(2e-06, "X", ref="700002")]})
        r = resolve(html, "X", "kcat")
        assert r.found is False and r.value is None
        assert r.source == "implausible_withheld"
        assert r.implausible_values == ["1e-05 1/s (BRENDA ref 700001)", "2e-06 1/s (BRENDA ref 700002)"]
        assert any("outside the physically plausible range" in line for line in r.search_log)

    def test_compose_says_why_an_implausible_constant_is_a_placeholder(self):
        from caterva.agents.adapters import to_parameter_source

        html = page({"Turnover Numbers": [row(1e-05, "X", ref="700001")]})
        source, reason = to_parameter_source("reaction_kcat", resolve(html, "X", "kcat"))
        assert source is None
        assert reason.startswith("every row BRENDA holds for this constant is outside the physically "
                                 "plausible range")
        assert "the values: 1e-05 1/s (BRENDA ref 700001)" in reason

    def test_the_median_is_an_actual_row_never_an_average(self):
        html = page({"KM Values": [row(v, "X", ref=f"70000{i}")
                                   for i, v in enumerate([0.01, 0.2, 0.3, 5.0, 9.0])]})
        r = resolve(html, "X", "km")
        assert r.value == 0.3 and r.citation.reference_id == "700002"
        assert "median of the 5 remaining rows" in r.chosen_because

    def test_with_an_even_count_the_lower_middle_row_is_taken(self):
        html = page({"KM Values": [row(v, "X", ref=f"70000{i}")
                                   for i, v in enumerate([0.1, 0.2, 0.4, 0.8])]})
        r = resolve(html, "X", "km")
        assert r.value == 0.2 and "lower of the two middle values" in r.chosen_because

    def test_rows_stating_ph_and_temperature_are_preferred(self):
        html = page({"KM Values": [
            row(0.01, "X", commentary="recombinant enzyme", ref="700001"),
            row(0.02, "X", commentary="pH 8", ref="700002"),
            row(0.5, "X", commentary="pH 7.5, 30°C", ref="700003")]})
        r = resolve(html, "X", "km")
        assert r.value == 0.5
        assert "2 row(s) not stating both pH and temperature passed over" in r.chosen_because

    def test_mutants_are_passed_over_for_wild_type_rows_even_when_variants_are_allowed(self):
        html = page({"Turnover Numbers": [
            row(0.5, "X", commentary="mutant R132H, pH 7.5, 25°C", ref="700001"),
            row(0.7, "X", commentary="C123A, pH 7.5, 25°C", ref="700002"),
            row(40, "X", commentary="wild-type, pH 7.5, 25°C", ref="700003")]})
        r = resolve(html, "X", "kcat", allow_variants=True)
        assert r.value == 40
        assert "2 mutant row(s) passed over for wild-type ones" in r.chosen_because

    def test_the_treated_arm_of_a_papers_own_experiment_is_passed_over(self):
        """CA II and CO2, BRENDA ref 702518: 13 mM without timolol, 0.012 and
        0.013 mM with it. The median of all three was 0.013."""
        html = page({"KM Values": [
            row(0.012, "CO2", commentary="in the presence of 4.5 mM timolol, pH 7.4, 25°C",
                ref="702518"),
            row(0.013, "CO2", commentary="in the presence of 2.0 mM timolol, pH 7.4, 25°C",
                ref="702518"),
            row(13.0, "CO2", commentary="in the absence of timolol, pH 7.4, 25°C", ref="702518"),
            row(9.3, "CO2", commentary="pH 7.4, 25°C", ref="696613")]})
        r = resolve(html, "CO2", "km")
        assert r.value == 9.3
        assert "measured with timolol added passed over" in r.chosen_because

    def test_a_spread_over_a_hundredfold_is_recorded_and_the_pick_stands(self):
        html = page({"Turnover Numbers": [row(v, "X", ref=f"70000{i}")
                                          for i, v in enumerate([0.43, 90.7, 273, 3660.68])]})
        r = resolve(html, "X", "kcat")
        assert r.value == 90.7 and r.wide_spread is True
        assert r.spread_fold == pytest.approx(3660.68 / 0.43)
        assert "more than 100-fold" in r.chosen_because

    def test_a_narrow_spread_is_not_flagged(self):
        html = page({"Turnover Numbers": [row(v, "X", ref=f"70000{i}")
                                          for i, v in enumerate([40.1, 60.4, 101])]})
        r = resolve(html, "X", "kcat")
        assert r.value == 60.4 and r.wide_spread is False

    def test_the_tie_sentence_says_median_not_lowest(self):
        html = page({"KM Values": [row(v, "X", ref=f"70000{i}") for i, v in enumerate([1, 2, 3])]})
        reason = resolve(html, "X", "km").selection_tie.reason
        assert "median row" in reason and "lowest" not in reason


class TestAKmAndAKcatComeFromOnePaperWhenOneHasBoth:
    HTML = page({
        "KM Values": [row(0.05, "S", ref="700001"), row(0.2, "S", ref="700002"),
                      row(0.3, "S", ref="700003")],
        "Turnover Numbers": [row(10, "S", ref="700004"), row(30, "S", ref="700003"),
                             row(50, "S", ref="700005")],
    })

    def test_prefer_reference_takes_that_papers_row(self):
        r = resolve(self.HTML, "S", "kcat", prefer_reference="700003")
        assert r.value == 30 and r.citation.reference_id == "700003"
        assert "the paper the paired constant came from" in r.chosen_because

    def test_a_reference_with_no_row_changes_nothing_and_is_said(self):
        r = resolve(self.HTML, "S", "kcat", prefer_reference="799999")
        assert r.value == 30  # the median anyway
        assert any("different papers" in line for line in r.search_log)

    def test_the_pair_is_rechosen_from_the_paper_that_measured_both(self):
        km, kcat = resolve_kinetic_pair(
            "9.9.9.9", "Homo sapiens", "S", html_provider=lambda ec: self.HTML,
            uniprot_provider=lambda ec, org: None, taxon_id_provider={"Homo sapiens": "9606"}.get,
            search_literature=False)
        assert (km.value, kcat.value) == (0.3, 30)
        assert km.citation.reference_id == kcat.citation.reference_id == "700003"

    def test_on_the_recorded_page_hexokinase_is_not_paired_through_a_k05(self):
        """Pairing once carried ref 739603's Km 6.3 mM and kcat 40.1 1/s,
        "measured together": the 6.3 mM row is glucokinase's K0.5 with a Hill
        coefficient of 1.8, not a Michaelis-Menten Km, and its kcat row
        states other conditions. No paper on the page holds a Km row and a
        kcat row under one set of stated conditions, so each constant is the
        independent pick and both say so; the kcat names its isozyme (GCK,
        from the row's own UniProt accession) and the Km is HK-I's."""
        html = recorded_hexokinase()
        kw = dict(html_provider=lambda ec: html, uniprot_provider=lambda ec, org: None,
                  taxon_id_provider={"Homo sapiens": "9606"}.get, search_literature=False)
        alone_km = resolve_kinetic_value("2.7.1.1", "Homo sapiens", "D-glucose", **kw)
        alone_kcat = resolve_kinetic_value("2.7.1.1", "Homo sapiens", "D-glucose",
                                           quantity="kcat", **kw)
        assert (alone_km.value, alone_km.citation.reference_id) == (0.06, "640237")
        assert (alone_kcat.value, alone_kcat.citation.reference_id) == (60.4, "703624")
        assert alone_km.wide_spread is True  # hexokinase I and IV share the pool
        km, kcat = resolve_kinetic_pair("2.7.1.1", "Homo sapiens", "D-glucose", **kw)
        assert (km.value, kcat.value) == (0.06, 60.4)
        assert "chosen independently, not as a measured pair" in km.chosen_because
        assert "K0.5 / Hill" in km.chosen_because
        assert any("(P35557) is GCK" in n for n in kcat.row_notes)


# -- Isoforms ------------------------------------------------------------------


class TestIsozymeSpellingsAreReadWithoutMatchingAnotherIsozyme:
    @pytest.fixture(autouse=True)
    def _reader(self):
        pytest.importorskip("caterva.bind.core")

    @pytest.mark.parametrize("commentary", [
        "isozyme CA II, pH 7.5, 25°C", "hCA II, pH 7.4", "CA-II", "CAII",
        "isoform carbonic anhydrase II, at pH 7.4 and 25°C", "recombinant CA2"])
    def test_carbonic_anhydrase_ii_in_every_spelling(self, commentary):
        from caterva.bind.core import read_isoform, same_isoform
        assert read_isoform(commentary) == "CA-II"
        assert same_isoform("CA II", commentary) and same_isoform("II", commentary)
        assert not same_isoform("CA I", commentary)

    def test_carbonic_anhydrase_numerals_past_viii_and_not_a_brain_region(self):
        from caterva.bind.core import read_isoform, same_isoform
        assert read_isoform("isozyme CA IX") == "CA-IX"
        assert read_isoform("isoform CA XIII") == "CA-XIII"
        assert not same_isoform("CA IX", "CA II")
        assert read_isoform("hippocampal CA1 neurons") is None
        assert read_isoform("pH 7.5, CA 2 mM") is None

    def test_an_inhibitor_written_cai_and_a_calcium_ion_are_not_isozymes(self):
        """Found in review: "CAI" (a carbonic anhydrase inhibitor) read as
        CA I, and "CA2+" as CA II, so such a row could answer a CA I or CA
        II request for an isozyme it never named."""
        from caterva.bind.core import read_isoform
        assert read_isoform("a sulfonamide CAI, pH 7.5") is None
        assert read_isoform("CA2+ dependent") is None
        assert read_isoform("hCAI") == "CA-I" and read_isoform("CA I") == "CA-I"

    @pytest.mark.parametrize("commentary", [
        "CYP2B6", "isoform CYP2B6", "P450 2B6", "cytochrome P450 2B6, pH 7.4", "CYP 2B6"])
    def test_cyp2b6_in_every_spelling_and_never_cyp2b1(self, commentary):
        from caterva.bind.core import same_isoform
        assert same_isoform("CYP2B6", commentary) and same_isoform("2B6", commentary)
        assert not same_isoform("CYP2B1", commentary)

    def test_phosphodiesterase_family_and_subfamily(self):
        from caterva.bind.core import read_isoform, same_isoform
        assert read_isoform("isozyme PDE5A, pH 7.5") == "PDE5A"
        assert same_isoform("PDE5", "PDE5A") and same_isoform("PDE5", "phosphodiesterase 5")
        assert not same_isoform("PDE4A", "PDE4B") and not same_isoform("PDE5", "PDE6")

    def test_the_resolver_keeps_only_ca_ii_rows_when_ca_ii_is_asked(self):
        html = page({"Turnover Numbers": [
            row(200000, "CO2", commentary="isoform carbonic anhydrase I, at pH 7.4 and 25°C",
                ref="696613"),
            row(1400000, "CO2", commentary="isoform carbonic anhydrase II, at pH 7.4 and 25°C",
                ref="696613"),
            row(600000, "CO2", commentary="wild type isozyme hCA II, pH 7.5, 23°C",
                ref="775944"),
            row(13000, "CO2", commentary="isozyme CA III, pH 7.4, 25°C", ref="696613")]})
        r = resolve(html, "CO2", "kcat", isoform="CA II")
        assert sorted(c["value"] for c in r.ensemble_candidates) == [600000, 1400000]
        assert r.value == 600000
