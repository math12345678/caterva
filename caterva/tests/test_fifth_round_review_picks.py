"""The fifth adversarial round of the real-values work (2026-11-12), the
parts that are caterva's: which substrate the chooser ranks first, which
row an isoform request re-takes, and what the report says of rows passed
over. Offline: `defaults.table_rows` is replaced by rows written here, and
the Measurements carry their ranked rows.

- human trypsin was modelled on "enhanced green fluorescent protein-T1", an
  engineered reporter BRENDA lists among its natural substrates, over
  Z-Gly-Pro-Arg-pNA's wild-type pairs;
- DPP4's Km was `matching[0]`, the row of a paper whose kcat is a probable
  error, and "as --isoform asked" was said when no flag was passed;
- E. coli beta-galactosidase's kcat of 90 1/s was carried with no word of
  the native rows at 400 and 620 1/s.
"""
from __future__ import annotations

from caterva.compose import defaults
from caterva.compose.export import Measurement
from caterva.compose.isoform import ASKED_BY_WORDS, select_isoform
from caterva.compose.report import _passed_over_far


def _given(monkeypatch, rows, natural=()):
    def table_rows(ec, table, organism):
        return tuple(r for r in rows.get(table, ()) if organism is None or r.organism == organism)

    monkeypatch.setattr(defaults, "table_rows", table_rows)
    monkeypatch.setattr(defaults, "_reaction_compounds", lambda ec: (
        frozenset(defaults._key(n) for n in natural), frozenset(defaults._key(n) for n in natural)))


def _row(compound, conditions="", ref="1"):
    return defaults._Row(compound, "Homo sapiens", conditions, 1.0, ref, None, False, False)


# -- An engineered reporter is never the natural substrate --------------------------------

def test_an_engineered_reporter_is_not_chosen_as_the_natural_substrate(monkeypatch):
    egfp = "enhanced green fluorescent protein-T1"
    zgpr = "Z-Gly-Pro-Arg-p-nitroanilide"
    rows = {t: [_row(egfp, "pH 7.4, 37°C", "696328")]
            + [_row(zgpr, "wild type enzyme, pH 8.0, 20°C", str(678332 + i)) for i in range(6)]
            for t in ("km", "kcat")}
    _given(monkeypatch, rows, natural=[egfp])
    choice = defaults.choose_substrate("3.4.21.4", "Homo sapiens")
    assert choice.chosen == zgpr
    assert "engineered reporter" in choice.why
    assert "natural substrate (BRENDA's Natural Substrates table) with the most rows" not in choice.why


def test_reporter_names_are_read_as_engineered():
    assert defaults.is_engineered("enhanced green fluorescent protein-T1")
    assert defaults.is_engineered("EGFP-DEVD-YFP FRET substrate")
    assert not defaults.is_engineered("Z-Gly-Pro-Arg-p-nitroanilide")
    assert not defaults.is_engineered("D-luciferin")


# -- An isoform request takes the median of its rows, never a discredited paper's -----------

def _dpp4(identifier):
    km = identifier.endswith("_Km")
    rows = (
        [{"value": 1.43, "unit": "mM", "reference_id": "665551", "conditions": "pH 7.4, wild-type enzyme",
          "isoform": "DPP4"},
         {"value": 0.09, "unit": "mM", "reference_id": "678195", "conditions": "dimeric rDPP-IV",
          "isoform": "DPP4"},
         {"value": 0.165, "unit": "mM", "reference_id": "649281", "conditions": "pH 7.6, 30°C"}]
        if km else
        [{"value": 279000.0, "unit": "1/s", "reference_id": "665551",
          "conditions": "pH 7.4, wild-type enzyme", "isoform": "DPP4"},
         {"value": 87.0, "unit": "1/s", "reference_id": "678195", "conditions": "dimeric rDPP-IV",
          "isoform": "DPP4"},
         {"value": 20.3, "unit": "1/s", "reference_id": "695876", "conditions": "pH 8.0"},
         {"value": 24.0, "unit": "1/s", "reference_id": "653810", "conditions": "pH 7.4"}])
    value, ref = (0.165, "649281") if km else (20.3, "695876")
    return Measurement(value, "mM" if km else "1/s", f"BRENDA ref {ref}", organism="Homo sapiens",
                       commentary=rows[2]["conditions"], alternatives=tuple(rows))


def test_a_paper_whose_other_constant_is_a_probable_error_supplies_neither():
    out = select_isoform({"reaction_Km": _dpp4("reaction_Km"), "reaction_kcat": _dpp4("reaction_kcat")},
                         "DPP4", ASKED_BY_WORDS)
    km, kcat = out.measured["reaction_Km"], out.measured["reaction_kcat"]
    assert km.value == 0.09 and kcat.value == 87.0
    assert "665551" not in km.citation
    assert all("as --isoform asked" not in n for n in out.notes)
    assert any("as your description asked" in n for n in out.notes)


# -- Rows passed over are said when no spread is ----------------------------------------------

def test_rows_passed_over_far_from_the_carried_row_are_said():
    m = Measurement(90.0, "1/s", "BRENDA ref 706624", organism="Escherichia coli",
                    commentary="wild type enzyme, pH 7.0 at 25°C",
                    resolver_because=("90 1/s (BRENDA ref 706624) is the only row remaining; of the 4 "
                                      "candidate rows (after the organism, substrate, isoform and "
                                      "variant checks): 3 row(s) not stating both pH and temperature "
                                      "passed over (180, 400, 620 1/s)"))
    said = _passed_over_far(m)
    assert said and said[0].startswith("3 row(s) not stating both pH and temperature passed over")
    near = Measurement(90.0, "1/s", "BRENDA ref 706624", organism="Escherichia coli",
                       resolver_because="1 row(s) not stating both pH and temperature passed over (100 1/s)")
    assert _passed_over_far(near) == []
