"""`caterva compose --isoform`: constants from rows that measured the isoform asked for.

The rows are BRENDA's own, for human lactate dehydrogenase and gossypol
(ref 711801): one paper, three isoforms, three Ki values. The resolver ranks
them as equally well evidenced and returns LDH-B's; a model of LDH-A needs
LDH-A's.
"""
from __future__ import annotations

import pytest

from caterva.compose.export import Measurement
from caterva.compose.isoform import same_isoform, select_isoform
from caterva.compose.row_scope import ISOFORM, read_scope

UNSTATED = "pH not specified in the publication, temperature not specified in the publication"
ROWS = (
    {"value": 0.0014, "unit": "mM", "reference_id": "711801", "organism": "Homo sapiens",
     "conditions": f"LDH-B, {UNSTATED}", "ph": None, "temperature_c": None, "buffer": None},
    {"value": 0.0019, "unit": "mM", "reference_id": "711801", "organism": "Homo sapiens",
     "conditions": f"LDH-A, {UNSTATED}", "ph": None, "temperature_c": None, "buffer": None},
    {"value": 0.0042, "unit": "mM", "reference_id": "711801", "organism": "Homo sapiens",
     "conditions": f"LDH-C, {UNSTATED}", "ph": None, "temperature_c": None, "buffer": None},
)


def gossypol_ki(**kw):
    base = dict(value=0.0014, unit="mM", citation="BRENDA ref 711801", organism="Homo sapiens",
                commentary=f"LDH-B, {UNSTATED}", alternatives=ROWS,
                assay_unreported=("temperature", "pH"))
    base.update(kw)
    return Measurement(**base)


def pyruvate_km():
    # BRENDA's two human rows name no isoform (refs 286469 and 286442).
    return Measurement(0.03, "mM", "BRENDA ref 286469", organism="Homo sapiens", commentary=None,
                       alternatives=({"value": 0.03, "unit": "mM", "reference_id": "286469", "conditions": None},
                                     {"value": 0.398, "unit": "mM", "reference_id": "286442", "conditions": None}))


class TestNames:
    @pytest.mark.parametrize("a,b", [("LDH-A", "ldha"), ("LDH-A", "LDH A"), ("ldh_a", "LDH-A")])
    def test_spelling_does_not_matter(self, a, b):
        assert same_isoform(a, b)

    def test_different_isoforms_and_nothing_are_not_the_same(self):
        assert not same_isoform("LDH-A", "LDH-B")
        assert not same_isoform(None, "LDH-A") and not same_isoform(None, None)


class TestSelect:
    def test_the_row_for_the_isoform_asked_for_replaces_the_resolvers_pick(self):
        out = select_isoform({"reaction_Ki": gossypol_ki()}, "LDH-A")
        ki = out.measured["reaction_Ki"]
        assert ki.value == 0.0019 and ki.citation == "BRENDA ref 711801"
        assert ki.commentary.startswith("LDH-A")
        assert set(ki.assay_unreported) == {"pH", "temperature"}
        assert "as --isoform asked" in ki.chosen_because
        assert "measured LDH-B" in out.notes[0] and "0.0019" in out.notes[0]
        # The other rows stay: the spread is still reported, now saying why
        # the carried value was carried.
        assert ki.spread is not None and "the row for LDH-A" in ki.spread.sentence()

    def test_the_resolvers_pick_is_kept_when_it_is_the_isoform_asked_for(self):
        out = select_isoform({"reaction_Ki": gossypol_ki()}, "ldh-b")
        assert out.measured["reaction_Ki"].value == 0.0014 and out.notes == [] and out.refused == {}

    def test_a_row_naming_no_isoform_is_kept_and_said_to_be_unknown(self):
        out = select_isoform({"reaction_Km": pyruvate_km()}, "LDH-A")
        assert out.measured["reaction_Km"].value == 0.03
        assert "unknown" in out.notes[0]

    def test_a_constant_only_measured_on_other_isoforms_is_refused(self):
        out = select_isoform({"reaction_Ki": gossypol_ki()}, "LDH-Z")
        assert "reaction_Ki" not in out.measured
        assert "LDH-A, LDH-B, LDH-C" in out.refused["reaction_Ki"]
        assert "different protein" in out.refused["reaction_Ki"]

    def test_a_row_naming_no_isoform_beats_a_known_wrong_one(self):
        rows = ROWS + ({"value": 0.0025, "unit": "mM", "reference_id": "999", "conditions": "pH 7.4"},)
        out = select_isoform({"reaction_Ki": gossypol_ki(alternatives=rows)}, "LDH-Z")
        ki = out.measured["reaction_Ki"]
        assert ki.value == 0.0025 and "naming no isoform" in ki.chosen_because

    def test_a_row_in_another_unit_is_never_substituted(self):
        rows = ({**ROWS[1], "unit": "uM", "value": 1.9},)
        out = select_isoform({"reaction_Ki": gossypol_ki(alternatives=ROWS[:1] + rows)}, "LDH-A")
        assert "reaction_Ki" in out.refused


class TestTheReportSaysSo:
    def test_a_matching_row_raises_no_isoform_concern(self):
        scope = read_scope(f"LDH-A, {UNSTATED}", motif="competitive_inhibition", table="ki", isoform="LDH-A")
        assert ISOFORM not in [c.kind for c in scope.concerns]

    def test_a_row_naming_none_is_unknown_for_the_isoform_asked_for(self):
        scope = read_scope("pH 7.4, 25°C", motif="competitive_inhibition", table="km", isoform="LDH-A")
        assert [c.kind for c in scope.concerns] == [ISOFORM]
        assert "LDH-A" in scope.concerns[0].plain and "unknown" in scope.concerns[0].plain

    def test_a_row_with_no_commentary_is_unknown_too(self):
        scope = read_scope(None, motif="competitive_inhibition", table="km", isoform="LDH-A")
        assert scope is not None and "no commentary" in scope.concerns[0].plain
        assert read_scope(None, motif="competitive_inhibition", table="km") is None
