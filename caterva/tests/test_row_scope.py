"""What a value's own source row says it measured, carried into every export.

Found on human LDH, 2026-09-29: `caterva compose ... --inhibitor gossypol`
resolves Ki = 0.0014 mM from BRENDA ref 711801, whose row reads "LDH-B, pH
not specified in the publication, temperature not specified in the
publication". The report said so. The four exports did not: a lab that took
the SBML, the Antimony, the CSV or the methods paragraph got 0.0014 mM with a
citation and no word that it is one isoform's constant with no stated mode.

The same run showed a second gap. `Measurement.alternatives` carried the
other rows the resolver ranked (Km 0.03 vs 0.398 mM, 13-fold) and
`Measurement.disagreement` computed their range, but no exporter printed
either, although the field's own comment said the composed model got them.

The row strings below are BRENDA's own, from that run.
"""
from __future__ import annotations

import csv
import io
from types import SimpleNamespace

import pytest

from caterva.compose.builder import Composition
from caterva.compose.export import (
    CSV_COLUMNS, SCOPE_MARKER, SPREAD_MARKER, Measurement, provenance_of,
    to_antimony, to_methods_paragraph, to_parameter_csv,
)
from caterva.compose.library import COMPETITIVE_INHIBITION, NONCOMPETITIVE_INHIBITION
from caterva.compose.row_scope import (
    ISOFORM, MODE_MISMATCH, MODE_UNSTATED, VERSUS, read_scope,
)

LDH_B_ROW = "LDH-B, pH not specified in the publication, temperature not specified in the publication"


def kinds(scope):
    return [c.kind for c in scope.concerns]


class TestReadScope:
    def test_no_commentary_is_nothing_to_read(self):
        assert read_scope(None, motif="competitive_inhibition", table="ki") is None
        assert read_scope("   ", motif="competitive_inhibition", table="ki") is None

    def test_the_gossypol_row(self):
        scope = read_scope(LDH_B_ROW, motif="competitive_inhibition", table="ki", substrate="pyruvate")
        assert scope.isoform == "LDH-B"
        assert scope.mode == "unstated"
        assert kinds(scope) == [ISOFORM, MODE_UNSTATED]

    def test_a_km_row_is_not_read_for_an_inhibition_mode(self):
        # "states no inhibition mode" about a Km would be true and useless.
        scope = read_scope(LDH_B_ROW, motif="competitive_inhibition", table="km")
        assert scope.mode is None
        assert kinds(scope) == [ISOFORM]

    def test_another_mode_is_another_mechanism(self):
        scope = read_scope("noncompetitive, pH 7.5", motif="competitive_inhibition", table="ki")
        assert kinds(scope) == [MODE_MISMATCH]
        assert "**noncompetitive**" in scope.concerns[0].text
        assert "**" not in scope.concerns[0].plain

    def test_mixed_is_accepted_for_a_noncompetitive_model(self):
        scope = read_scope("mixed-type inhibition, pH 7.5", motif="noncompetitive_inhibition", table="ki")
        assert MODE_MISMATCH not in kinds(scope)

    def test_measured_against_another_molecule(self):
        scope = read_scope("competitive versus NADH, pH 7.5", motif="competitive_inhibition",
                           table="ki", substrate="pyruvate")
        assert scope.versus == "NADH"
        assert kinds(scope) == [VERSUS]
        assert "not versus pyruvate" in scope.concerns[0].plain

    def test_a_row_that_matches_the_model_raises_nothing(self):
        scope = read_scope("competitive versus pyruvate, pH 7.5, 25°C", motif="competitive_inhibition",
                           table="ki", substrate="Pyruvate")
        assert scope is not None and scope.mode == "competitive" and not scope.any


class TestSpread:
    def ki(self, **kw):
        base = dict(value=0.0014, unit="mM", citation="BRENDA ref 711801", organism="Homo sapiens",
                    reference_id="711801", commentary=LDH_B_ROW,
                    alternatives=({"value": 0.0014, "reference_id": "711801"},
                                  {"value": 0.0019, "reference_id": "711801"},
                                  {"value": 0.0042, "reference_id": "711801"}))
        base.update(kw)
        return Measurement(**base)

    def test_one_paper_with_three_rows_is_not_a_controversy(self):
        spread = self.ki().spread
        assert (spread.low, spread.high, spread.n_values) == (0.0014, 0.0042, 3)
        assert spread.one_source
        assert spread.fold == pytest.approx(3.0)
        assert "one source (BRENDA ref 711801) reports 3 values" in spread.sentence()
        assert "read that paper" in spread.sentence()

    def test_two_papers(self):
        km = Measurement(0.03, "mM", "BRENDA ref 286469", reference_id="286469",
                         alternatives=({"value": 0.03, "reference_id": "286469"},
                                       {"value": 0.398, "reference_id": "286442"}))
        spread = km.spread
        assert not spread.one_source
        assert "2 sources report 2 values (BRENDA ref 286442, 286469)" in spread.sentence()
        assert "13.3-fold" in spread.sentence()

    def test_every_rendering_says_it_is_not_an_error_bar(self):
        assert "not an uncertainty estimate" in self.ki().spread.sentence()

    def test_agreeing_rows_have_no_spread(self):
        assert self.ki(alternatives=({"value": 0.0014},)).spread is None
        assert self.ki(alternatives=()).spread is None


def _ldh_model(ki: Measurement, substrate="pyruvate"):
    """competitive_inhibition with its Ki measured, passed the way the
    pipeline passes a ComposedModel: a composition plus the substrate."""
    composition = Composition("ldh")
    composition.add(COMPETITIVE_INHIBITION, "reaction")
    source = SimpleNamespace(recognition=SimpleNamespace(composition=composition),
                             query="Michaelis-Menten with a competitive inhibitor",
                             subject="1.1.1.27", substrate=substrate)
    return provenance_of(source, measured={"reaction_Ki": ki})


@pytest.fixture(scope="module")
def ldh():
    return _ldh_model(TestSpread().ki())


class TestEveryExportCarriesIt:
    def test_csv_columns(self, ldh):
        for column in ("source_row_commentary", "measured_isoform", "inhibition_mode",
                       "inhibition_measured_versus", "reported_values_low",
                       "reported_values_high", "reported_values_references"):
            assert column in CSV_COLUMNS
        assert CSV_COLUMNS[-1] == "provenance"

    def test_csv_row(self, ldh):
        rows = {r["identifier"]: r for r in csv.DictReader(io.StringIO(to_parameter_csv(ldh)))}
        ki = rows["reaction_Ki"]
        assert ki["source_row_commentary"] == LDH_B_ROW
        assert ki["measured_isoform"] == "LDH-B"
        assert ki["inhibition_mode"] == "unstated"
        assert (ki["reported_values_low"], ki["reported_values_high"]) == ("0.0014", "0.0042")
        assert ki["reported_values_references"] == "711801"
        assert f"{SCOPE_MARKER}: the row measured isoform LDH-B" in ki["provenance"]
        assert f"{SPREAD_MARKER}:" in ki["provenance"]
        # A placeholder row has none of it, and says nothing it cannot know.
        kcat = rows["reaction_kcat"]
        assert kcat["measured_isoform"] == kcat["reported_values_low"] == ""
        assert SCOPE_MARKER not in kcat["provenance"]

    def test_antimony_footer(self, ldh):
        text = to_antimony(ldh)
        assert "the row states no inhibition mode" in text
        assert "spanning 0.0014 to 0.0042 mM" in text

    def test_methods_paragraph(self, ldh):
        text = to_methods_paragraph(ldh)
        assert "  - The row measured isoform LDH-B" in text
        assert "  - The row states no inhibition mode" in text
        assert "  - The values disagree: one source (BRENDA ref 711801)" in text

    def test_a_ki_measured_against_the_cofactor(self):
        model = _ldh_model(TestSpread().ki(commentary="competitive versus NADH", alternatives=()))
        rows = {r["identifier"]: r for r in csv.DictReader(io.StringIO(to_parameter_csv(model)))}
        assert rows["reaction_Ki"]["inhibition_measured_versus"] == "NADH"
        assert "not versus pyruvate" in rows["reaction_Ki"]["provenance"]

    def test_a_plain_composition_has_no_substrate_to_compare(self):
        composition = Composition("bare")
        composition.add(NONCOMPETITIVE_INHIBITION, "r")
        model = provenance_of(composition, measured={"r_Ki": TestSpread().ki(
            commentary="competitive versus NADH", alternatives=())})
        scope = model.origin_of("r_Ki").scope
        assert [c.kind for c in scope.concerns] == [MODE_MISMATCH]
