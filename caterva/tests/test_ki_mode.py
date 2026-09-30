"""`caterva compose` takes a Ki from a row whose stated inhibition mode fits the model.

Found on human LDH, 2026-09-29: a noncompetitive model with `--substrate
pyruvate --inhibitor <the quinoline sulfonamide of BRENDA ref 739793>`
carried 0.00059 mM, the row stating "competitive versus NADH". The same
paper's other row, 0.00252 mM "noncompetitive versus pyruvate", was in the
Measurement's own `alternatives`, and the report said the carried value
"belongs to a different mechanism" without anything choosing the other.

Every row string below is BRENDA's own, as the compose resolver returned it
(`measured_from_search(...).alternatives`, in the resolver's order, the pick
first) on 2026-09-29:

- LDH (EC 1.1.1.27), Homo sapiens, the quinoline sulfonamide, ref 739793;
- LDH, Homo sapiens, gossypol, ref 711801 (also in
  Tests/fixtures/brenda_ldh_ki_fixture.html);
- hexokinase (EC 2.7.1.1), Oryctolagus cuniculus, MgADP-, ref 640206: the
  only Ki rows stating "mixed" in the repository's BRENDA fixtures, in
  Tests/fixtures/recorded/brenda_2.7.1.1.html.gz (checked below);
- monoamine oxidase (EC 1.4.3.4), Homo sapiens, benzylhydrazine and
  phenylhydrazine, ref 702238: the rows that name an isoform AND a mode.

The one value not read from BRENDA is the unit test's 2.52 uM, which is
the 0.00252 mM row written in micromolar (x 1000) to show that a row in
another unit is never moved across.
"""
from __future__ import annotations

import csv
import gzip
import io
from pathlib import Path
from types import SimpleNamespace

import pytest

from caterva.compose.export import Measurement
from caterva.compose.isoform import select_isoform
from caterva.compose.ki_mode import ANY_MODE_FLAG, constants_of, select_mode
from caterva.compose.row_scope import MODE_MISMATCH, MODE_UNSTATED, VERSUS, read_scope

REPO = Path(__file__).resolve().parents[2]

# -- LDH and the quinoline sulfonamide, BRENDA ref 739793 ------------------
QUINOLINE = "3-[7-(2,4-dimethoxypyrimidin-5-yl)-3-sulfamoylquinolin-4-yl]aminobenzoic acid"
COMPETITIVE_VS_NADH = ("pH 7.5, 37°C, recombinant His-tagged enzyme, pyruvate reduction, "
                       "competitive versus NADH")
NONCOMPETITIVE_VS_PYRUVATE = ("pH 7.5, 37°C, recombinant His-tagged enzyme, pyruvate reduction, "
                              "noncompetitive versus pyruvate")


def _row(value, conditions, ref, organism, ph=None, temperature_c=None, unit="mM"):
    return {"value": value, "unit": unit, "organism": organism, "reference_id": ref,
            "conditions": conditions, "ph": ph, "temperature_c": temperature_c, "buffer": None}


QUINOLINE_ROWS = (
    _row(0.00059, COMPETITIVE_VS_NADH, "739793", "Homo sapiens", 7.5, 37.0),
    _row(0.00252, NONCOMPETITIVE_VS_PYRUVATE, "739793", "Homo sapiens", 7.5, 37.0),
)

# -- LDH and gossypol, BRENDA ref 711801 -----------------------------------
UNSTATED = "pH not specified in the publication, temperature not specified in the publication"
GOSSYPOL_ROWS = (
    _row(0.0014, f"LDH-B, {UNSTATED}", "711801", "Homo sapiens"),
    _row(0.0019, f"LDH-A, {UNSTATED}", "711801", "Homo sapiens"),
    _row(0.0042, f"LDH-C, {UNSTATED}", "711801", "Homo sapiens"),
)

# -- hexokinase and MgADP-, rabbit erythrocyte, BRENDA ref 640206 ----------
MIXED_VS_MGATP = "erythrocyte enzyme, mixed inhibitor versus MgATP2-"
MIXED_VS_GLUCOSE = "erythrocyte enzyme, mixed inhibitor versus glucose"
MGADP_ROWS = (
    _row(3.0, MIXED_VS_MGATP, "640206", "Oryctolagus cuniculus"),
    _row(7.8, MIXED_VS_GLUCOSE, "640206", "Oryctolagus cuniculus"),
)

# -- monoamine oxidase and two hydrazines, BRENDA ref 702238 ---------------
COMPETITIVE_DATA = "determined from competitive inhibition data of substrate oxidation at 25°C"
KITZ_WILSON = ("determined from Kitz-Wilson plots of the hydrazine concentration dependence "
               "on rates in enzyme inhibition at 15°C")
BENZYLHYDRAZINE_ROWS = (
    _row(0.026, f"pH 7.5, MAO-B, {COMPETITIVE_DATA}", "702238", "Homo sapiens", 7.5, 25.0),
    _row(0.048, f"pH 7.5, MAO-B, {KITZ_WILSON}", "702238", "Homo sapiens", 7.5, 15.0),
    _row(1.95, f"pH 7.5, MAO-A, {KITZ_WILSON}", "702238", "Homo sapiens", 7.5, 15.0),
    _row(2.096, f"pH 7.5, MAO-A, {COMPETITIVE_DATA}", "702238", "Homo sapiens", 7.5, 25.0),
)
PHENYLHYDRAZINE_ROWS = (
    _row(0.205, f"pH 7.5, MAO-A, {COMPETITIVE_DATA}", "702238", "Homo sapiens", 7.5, 25.0),
    _row(0.523, f"pH 7.5, MAO-A, {KITZ_WILSON}", "702238", "Homo sapiens", 7.5, 15.0),
    _row(0.791, f"pH 7.5, MAO-B, {KITZ_WILSON}", "702238", "Homo sapiens", 7.5, 15.0),
)


def ki(rows, pick=0, **kw):
    """A Ki as `measured_from_search` builds it: the resolver's pick, with
    every row it ranked (the pick among them) as alternatives."""
    first = rows[pick]
    base = dict(value=first["value"], unit=first["unit"], citation=f"BRENDA ref {first['reference_id']}",
                organism=first["organism"], commentary=first["conditions"], alternatives=tuple(rows),
                assay_ph=first["ph"], assay_temperature_c=first["temperature_c"])
    base.update(kw)
    return Measurement(**base)


def choose(measurement, motif, substrate, **kw):
    return select_mode({"reaction_Ki": measurement}, {"reaction_Ki": (motif, "ki")},
                       substrate=substrate, **kw)


class TestAMatchingModeIsChosen:
    def test_a_noncompetitive_model_takes_the_noncompetitive_row(self):
        out = choose(ki(QUINOLINE_ROWS), "noncompetitive_inhibition", "pyruvate")
        carried = out.measured["reaction_Ki"]
        assert carried.value == 0.00252
        assert carried.commentary == NONCOMPETITIVE_VS_PYRUVATE
        assert carried.citation == "BRENDA ref 739793"
        assert (carried.assay_ph, carried.assay_temperature_c) == (7.5, 37.0)
        assert carried.chosen_because == (
            "the row stating noncompetitive inhibition versus pyruvate, this model's "
            "mechanism and substrate")
        assert out.refused == {}
        assert out.notes == [
            "`reaction_Ki`: the resolver's pick (0.00059 mM, BRENDA ref 739793) measured "
            "competitive inhibition versus NADH, and this model is noncompetitive; the row "
            "stating noncompetitive inhibition versus pyruvate (0.00252 mM, BRENDA ref 739793), "
            "this model's mechanism and substrate, is used instead"]

    def test_the_report_then_has_nothing_to_flag_about_mode_or_versus(self):
        carried = choose(ki(QUINOLINE_ROWS), "noncompetitive_inhibition", "pyruvate").measured["reaction_Ki"]
        scope = read_scope(carried.commentary, motif="noncompetitive_inhibition", table="ki",
                           substrate="pyruvate")
        assert [c.kind for c in scope.concerns if c.kind in (MODE_MISMATCH, VERSUS)] == []

    def test_every_surface_says_why_through_the_spread(self):
        carried = choose(ki(QUINOLINE_ROWS), "noncompetitive_inhibition", "pyruvate").measured["reaction_Ki"]
        sentence = carried.spread.sentence()
        assert "this model carries 0.00252, the row stating noncompetitive inhibition" in sentence

    def test_a_competitive_model_keeps_the_resolvers_pick(self):
        out = choose(ki(QUINOLINE_ROWS), "competitive_inhibition", "pyruvate")
        carried = out.measured["reaction_Ki"]
        assert carried.value == 0.00059 and carried.chosen_because is None
        assert out.notes == [] and out.refused == {}
        # Measured versus NADH, not pyruvate: no better row exists, and the
        # report still says so.
        scope = read_scope(carried.commentary, motif="competitive_inhibition", table="ki",
                           substrate="pyruvate")
        assert VERSUS in [c.kind for c in scope.concerns]


class TestNoStatedMode:
    def test_gossypol_is_unchanged(self):
        """The README example: every row states no mode, so the pick stays
        and the report's own "states no inhibition mode" is the finding."""
        out = choose(ki(GOSSYPOL_ROWS), "competitive_inhibition", "pyruvate")
        assert out.measured["reaction_Ki"].value == 0.0014
        assert out.measured["reaction_Ki"].chosen_because is None
        assert out.notes == [] and out.refused == {}

    def test_a_row_stating_no_mode_beats_a_pick_of_another_mode(self):
        # Phenylhydrazine and human MAO: the pick is MAO-A's competitive row;
        # a noncompetitive model has no row of its mode, and the next rows
        # state none.
        out = choose(ki(PHENYLHYDRAZINE_ROWS), "noncompetitive_inhibition", "kynuramine")
        carried = out.measured["reaction_Ki"]
        assert carried.value == 0.523
        assert carried.chosen_because == (
            "a row stating no inhibition mode, used because none states noncompetitive inhibition")
        assert "measured competitive inhibition, and this model is noncompetitive" in out.notes[0]
        scope = read_scope(carried.commentary, motif="noncompetitive_inhibition", table="ki")
        assert MODE_UNSTATED in [c.kind for c in scope.concerns]


class TestOnlyAnotherMode:
    def test_is_refused_naming_the_modes_and_the_flag(self):
        out = choose(ki(QUINOLINE_ROWS), "uncompetitive_inhibition", "pyruvate")
        assert "reaction_Ki" not in out.measured
        why = out.refused["reaction_Ki"]
        assert "a mode other than uncompetitive" in why
        assert "competitive inhibition versus NADH (0.00059 mM, BRENDA ref 739793)" in why
        assert "noncompetitive inhibition versus pyruvate (0.00252 mM, BRENDA ref 739793)" in why
        assert ANY_MODE_FLAG in why and "Each is a constant of a different mechanism" in why
        assert "|" not in why, "the reason is printed in a Markdown table cell"

    def test_mixed_rows_are_not_a_competitive_constant(self):
        out = choose(ki(MGADP_ROWS), "competitive_inhibition", "glucose")
        assert out.refused["reaction_Ki"].count("mixed inhibition versus") == 2


class TestAnyMode:
    def test_keeps_the_pick_and_says_what_the_default_would_do(self):
        out = choose(ki(QUINOLINE_ROWS), "noncompetitive_inhibition", "pyruvate", any_mode=True)
        carried = out.measured["reaction_Ki"]
        assert carried.value == 0.00059
        assert carried.chosen_because == (
            "the resolver's pick, kept by --any-mode although it measured competitive "
            "inhibition and this model is noncompetitive")
        assert ("without it the row stating noncompetitive inhibition versus pyruvate "
                "(0.00252 mM, BRENDA ref 739793)") in out.notes[0]
        # row_scope still flags it: the flag changes what is carried, not
        # what the report says about it.
        scope = read_scope(carried.commentary, motif="noncompetitive_inhibition", table="ki",
                           substrate="pyruvate")
        assert MODE_MISMATCH in [c.kind for c in scope.concerns]

    def test_keeps_a_constant_the_default_refuses(self):
        out = choose(ki(QUINOLINE_ROWS), "uncompetitive_inhibition", "pyruvate", any_mode=True)
        assert out.measured["reaction_Ki"].value == 0.00059 and out.refused == {}
        assert out.notes[0].endswith("without it the constant would be refused")

    def test_says_nothing_when_the_default_would_do_the_same(self):
        out = choose(ki(QUINOLINE_ROWS), "competitive_inhibition", "pyruvate", any_mode=True)
        assert out.notes == [] and out.measured["reaction_Ki"].chosen_because is None


class TestMixedAndVersus:
    def test_mixed_is_taken_for_a_noncompetitive_model(self):
        out = choose(ki(MGADP_ROWS), "noncompetitive_inhibition", "MgATP2-")
        assert out.refused == {} and out.measured["reaction_Ki"].value == 3.0
        assert out.notes == []

    def test_the_row_measured_against_the_models_substrate_is_preferred(self):
        # Rabbit hexokinase, glucose as the substrate: the resolver's pick is
        # the Ki versus MgATP2-, and the same paper measured it versus glucose.
        out = choose(ki(MGADP_ROWS), "noncompetitive_inhibition", "glucose")
        carried = out.measured["reaction_Ki"]
        assert carried.value == 7.8 and carried.commentary == MIXED_VS_GLUCOSE
        assert carried.chosen_because == (
            "the row stating mixed inhibition versus glucose, which counts as noncompetitive, "
            "against this model's substrate")
        assert "not versus glucose, this model's substrate" in out.notes[0]
        scope = read_scope(carried.commentary, motif="noncompetitive_inhibition", table="ki",
                           substrate="glucose")
        assert [c.kind for c in scope.concerns if c.kind in (MODE_MISMATCH, VERSUS)] == []

    def test_a_row_measured_against_another_molecule_is_still_taken_over_another_mode(self):
        # The competitive LDH row was measured versus NADH, not pyruvate; it
        # is still this mechanism's constant, and nothing better exists. The
        # pick is set to the other row (the resolver returned 0.00059 first)
        # to show the switch goes this way too.
        out = choose(ki(QUINOLINE_ROWS, pick=1), "competitive_inhibition", "pyruvate")
        carried = out.measured["reaction_Ki"]
        assert carried.value == 0.00059
        assert carried.chosen_because == (
            "the row stating competitive inhibition versus NADH, this model's mechanism "
            "though not its substrate (pyruvate)")


class TestWithIsoform:
    """`--isoform` first, then the mode, over the same ranked rows."""

    def _both(self, rows, isoform, motif, substrate="kynuramine"):
        by_isoform = select_isoform({"reaction_Ki": ki(rows)}, isoform)
        by_mode = select_mode(by_isoform.measured, {"reaction_Ki": (motif, "ki")},
                              substrate=substrate, isoform=isoform)
        return by_isoform, by_mode

    def test_the_isoforms_competitive_row_replaces_its_kitz_wilson_row(self):
        by_isoform, by_mode = self._both(BENZYLHYDRAZINE_ROWS, "MAO-A", "competitive_inhibition")
        # --isoform takes the first MAO-A row the resolver ranked...
        assert by_isoform.measured["reaction_Ki"].value == 1.95
        # ...and the mode moves it to MAO-A's competitive row, not MAO-B's.
        carried = by_mode.measured["reaction_Ki"]
        assert carried.value == 2.096 and "MAO-A" in carried.commentary
        assert carried.chosen_because == (
            "the row stating competitive inhibition, this model's mechanism; it names MAO-A, "
            "as --isoform asked")
        assert by_mode.notes == [
            "`reaction_Ki`: the row --isoform chose (1.95 mM, BRENDA ref 702238) states no "
            "inhibition mode; the row stating competitive inhibition (2.096 mM, BRENDA ref "
            "702238), this model's mechanism, is used instead; it names MAO-A, as --isoform asked"]

    def test_the_isoform_outranks_the_mode(self):
        # The only MAO-B row states no mode; MAO-A's competitive row is a
        # constant of the other protein and is not taken.
        by_isoform, by_mode = self._both(PHENYLHYDRAZINE_ROWS, "MAO-B", "competitive_inhibition")
        assert by_isoform.measured["reaction_Ki"].value == 0.791
        assert by_mode.measured["reaction_Ki"].value == 0.791
        assert by_mode.notes == [] and by_mode.refused == {}

    def test_no_isoform_asked_takes_the_competitive_row_of_either(self):
        out = choose(ki(BENZYLHYDRAZINE_ROWS), "competitive_inhibition", "kynuramine")
        assert out.measured["reaction_Ki"].value == 0.026 and out.notes == []

    def test_an_isoform_row_stating_no_mode_is_kept_over_the_other_isoforms(self):
        # MAO-A's rows state competitive (another mode for this model) and
        # nothing; MAO-B's are never candidates.
        by_isoform, by_mode = self._both(BENZYLHYDRAZINE_ROWS, "MAO-A", "uncompetitive_inhibition")
        assert by_mode.measured["reaction_Ki"].value == 1.95 and by_mode.notes == []

    def test_a_refusal_under_isoform_says_which_rows_it_read(self):
        by_isoform, by_mode = self._both(QUINOLINE_ROWS, "LDH-A", "uncompetitive_inhibition",
                                         substrate="pyruvate")
        # No row names LDH-A; select_isoform keeps the unnamed pick and says
        # so, and every unnamed row states another mode.
        assert "unknown" in by_isoform.notes[0]
        assert "among those for LDH-A or naming no isoform" in by_mode.refused["reaction_Ki"]


class TestScope:
    def test_a_row_in_another_unit_is_never_substituted(self):
        in_um = ({**QUINOLINE_ROWS[1], "unit": "uM", "value": 2.52},)
        out = choose(ki(QUINOLINE_ROWS[:1] + in_um), "noncompetitive_inhibition", "pyruvate")
        why = out.refused["reaction_Ki"]
        assert "reaction_Ki" not in out.measured
        assert "or no mode exists in uM, and a row in another unit is never substituted" in why

    def test_only_inhibition_constants_of_inhibition_motifs_are_touched(self):
        km = Measurement(0.03, "mM", "BRENDA ref 286469", organism="Homo sapiens",
                         commentary=None,
                         alternatives=(_row(0.03, None, "286469", "Homo sapiens"),
                                       _row(0.398, None, "286442", "Homo sapiens")))
        quinoline = ki(QUINOLINE_ROWS)
        out = select_mode(
            {"reaction_Km": km, "reaction_Ki": quinoline, "sub_Ksi": quinoline},
            {"reaction_Km": ("noncompetitive_inhibition", "km"),
             "reaction_Ki": ("noncompetitive_inhibition", "ki"),
             # A substrate-inhibition constant is in the ki table and has no
             # inhibition mode a row could contradict.
             "sub_Ksi": ("substrate_inhibition", "ki")},
            substrate="pyruvate")
        assert out.measured["reaction_Km"] is km
        assert out.measured["sub_Ksi"] is quinoline
        assert out.measured["reaction_Ki"].value == 0.00252

    def test_constants_of_reads_the_models_own_quantities(self):
        from caterva.compose.pipeline import compose

        model = compose("Michaelis-Menten with a noncompetitive inhibitor", subject="1.1.1.27")
        assert constants_of(model)["reaction_Ki"] == ("noncompetitive_inhibition", "ki")
        assert constants_of(model)["reaction_Km"] == ("noncompetitive_inhibition", "km")


class TestTheRowsAreBRENDAs:
    def test_the_mixed_rows_are_in_the_recorded_hexokinase_page(self):
        from caterva.checkout import LiteratureLayerUnavailable, literature_module

        try:
            brenda_client = literature_module("brenda_client")
        except LiteratureLayerUnavailable:  # pragma: no cover - the wheel
            pytest.skip("the literature layer is not installed")
        page = REPO / "Tests" / "fixtures" / "recorded" / "brenda_2.7.1.1.html.gz"
        html = gzip.decompress(page.read_bytes()).decode("utf-8", errors="replace")
        rows = brenda_client.parse_brenda_ki_html(
            html, "2.7.1.1", ["MgADP-"], target_organism="Oryctolagus cuniculus")
        got = sorted((r.km_value, r.conditions, r.reference_id) for r in rows
                     if r.substrate == "MgADP-")
        assert got == [(3.0, MIXED_VS_MGATP, "640206"), (7.8, MIXED_VS_GLUCOSE, "640206")]


class TestThroughTheCommand:
    """`_search_the_literature`, with the resolver's answer replaced by the
    rows it returned live, so the wiring is tested offline."""

    @staticmethod
    def _search(monkeypatch, query, rows, **flags):
        import caterva.compose.pipeline as pipeline
        from caterva.compose.__main__ import _search_the_literature
        from caterva.compose.pipeline import compose

        def source(value, rows, commentary, ph=None, temperature_c=None):
            return SimpleNamespace(value=value, unit="mM", citation=f"BRENDA ref {rows[0]['reference_id']}",
                                   organism="Homo sapiens", origin="literature", cross_species=False,
                                   ph=ph, temperature_c=temperature_c, buffer=None,
                                   explicitly_unreported=(), candidates=list(rows),
                                   commentary=commentary)

        km_rows = (_row(0.03, None, "286469", "Homo sapiens"), _row(0.398, None, "286442", "Homo sapiens"))
        search = SimpleNamespace(resolutions={
            "reaction_Ki": SimpleNamespace(source=source(rows[0]["value"], rows, rows[0]["conditions"],
                                                         rows[0]["ph"], rows[0]["temperature_c"])),
            "reaction_Km": SimpleNamespace(source=source(0.03, km_rows, None)),
            "reaction_kcat": SimpleNamespace(source=None, reason="no value in the organism requested"),
        })
        monkeypatch.setattr(pipeline, "compose_and_parameterise", lambda *a, **k: (None, search))
        args = SimpleNamespace(subject="1.1.1.27", organism="Homo sapiens", substrate="pyruvate",
                               inhibitor=QUINOLINE, product=None, compound=[], **flags)
        model = compose(query, subject="1.1.1.27", organism="Homo sapiens", substrate="pyruvate",
                        compounds={"@inhibitor": QUINOLINE})
        return _search_the_literature(model, args)

    def test_the_report_and_the_export_carry_the_chosen_row(self, monkeypatch):
        from caterva.compose.export import provenance_of, to_parameter_csv

        model, note, refused = self._search(
            monkeypatch, "Michaelis-Menten with a noncompetitive inhibitor", QUINOLINE_ROWS)
        assert refused is False
        assert model.measured["reaction_Ki"].value == 0.00252
        assert "is used instead" in note and "0.00252 mM" in note
        table = to_parameter_csv(provenance_of(model, measured=dict(model.measured)))
        row = next(r for r in csv.DictReader(io.StringIO(table)) if r["identifier"] == "reaction_Ki")
        assert float(row["value"]) == 0.00252
        assert "the row stating noncompetitive inhibition versus pyruvate" in row["provenance"]

    def test_any_mode_reaches_the_selection(self, monkeypatch):
        model, note, _ = self._search(
            monkeypatch, "Michaelis-Menten with a noncompetitive inhibitor", QUINOLINE_ROWS,
            any_mode=True)
        assert model.measured["reaction_Ki"].value == 0.00059
        assert f"{ANY_MODE_FLAG} kept the resolver's pick" in note

    def test_a_refused_constant_is_not_described_as_not_found(self, monkeypatch):
        model, note, refused = self._search(
            monkeypatch, "Michaelis-Menten with an uncompetitive inhibitor", QUINOLINE_ROWS)
        assert refused is False
        assert "reaction_Ki" not in model.measured
        assert ANY_MODE_FLAG in model.not_found["reaction_Ki"]
        assert "1 returned by the search and not used (reaction_Ki)" in note
        # kcat was genuinely not found; the Ki was found and refused.
        assert "1 still the motif library's placeholder (reaction_kcat)" in note

    def test_the_flag_is_on_the_command(self):
        from caterva.compose.__main__ import build_parser

        assert build_parser().parse_args(["x", "--any-mode"]).any_mode is True
        assert build_parser().parse_args(["x"]).any_mode is False
