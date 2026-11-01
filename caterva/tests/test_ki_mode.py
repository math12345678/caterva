"""`caterva compose` takes a Ki from a row whose stated inhibition mode fits the model.

Found on human LDH, 2026-09-29: a noncompetitive model with `--substrate
pyruvate --inhibitor <the quinoline sulfonamide of BRENDA ref 739793>`
carried 0.00059 mM, the row stating "competitive versus NADH". The same
paper's other row, 0.00252 mM "noncompetitive versus pyruvate", was in the
Measurement's own `alternatives`, and the report said the carried value
"belongs to a different mechanism" without anything choosing the other.

Every row string below is BRENDA's own, as the compose resolver returned it
(`measured_from_search(...).alternatives`, in the resolver's order, the pick
first) on 2026-09-29, and TestTheRowsAreBRENDAs checks each against a
committed copy of the page it came from:

- LDH (EC 1.1.1.27), Homo sapiens, the quinoline sulfonamide, ref 739793,
  and gossypol, ref 711801: Tests/fixtures/ki_mode/brenda_1.1.1.27.html.gz;
- hexokinase (EC 2.7.1.1), Oryctolagus cuniculus, MgADP-, ref 640206: the
  only Ki rows stating "mixed" in the repository's BRENDA fixtures, in
  Tests/fixtures/recorded/brenda_2.7.1.1.html.gz;
- monoamine oxidase (EC 1.4.3.4), Homo sapiens, benzylhydrazine and
  phenylhydrazine, ref 702238 (Binda et al. 2008, Biochemistry 47:5616):
  the rows that name an isoform AND a mode, in
  Tests/fixtures/ki_mode/brenda_1.4.3.4.html.gz.

Two values are not read from BRENDA as written: 2.52 uM, the 0.00252 mM
row written in micromolar (x 1000), and 2096 uM, the 2.096 mM row written
the same way. They show what happens to a row in another unit, which
BRENDA's Ki table (all mM) never serves.
"""
from __future__ import annotations

import csv
import gzip
import io
from pathlib import Path
from types import SimpleNamespace

import pytest

from caterva.compose import ki_mode
from caterva.compose.export import Measurement
from caterva.compose.isoform import select_isoform
from caterva.compose.ki_mode import ANY_MODE_FLAG, KITZ_WILSON_MEANING, constants_of, select_mode
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
        assert out.refused == {}
        # Measured versus NADH, not pyruvate: no better row exists, and the
        # report still says so.
        scope = read_scope(carried.commentary, motif="competitive_inhibition", table="ki",
                           substrate="pyruvate")
        assert VERSUS in [c.kind for c in scope.concerns]

    def test_a_row_of_another_mode_against_the_substrate_is_said_to_contradict_the_model(self):
        # Against pyruvate, this model's substrate, the paper found the
        # inhibitor noncompetitive. The competitive row is a constant of the
        # NADH site; the model makes the inhibitor compete with pyruvate.
        # No row fixes that, so it is a note, not a change of row.
        out = choose(ki(QUINOLINE_ROWS), "competitive_inhibition", "pyruvate")
        assert out.notes == [
            "`reaction_Ki`: a ranked row states noncompetitive inhibition versus pyruvate "
            "(0.00252 mM, BRENDA ref 739793), measured against pyruvate, this model's substrate, "
            "and the row carried (0.00059 mM, BRENDA ref 739793) states competitive inhibition "
            "versus NADH. Measured against pyruvate this inhibitor is not competitive, which is "
            "evidence against this model's mechanism for it; no choice of row fixes that"]

    def test_no_contradiction_is_claimed_when_the_carried_row_is_against_the_substrate(self):
        out = choose(ki(QUINOLINE_ROWS), "noncompetitive_inhibition", "pyruvate")
        assert not any("evidence against" in note for note in out.notes)
        # Nor for a model of NADH: the row against NADH is this model's.
        out = choose(ki(QUINOLINE_ROWS), "competitive_inhibition", "NADH")
        assert out.notes == [] and out.measured["reaction_Ki"].value == 0.00059


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
            "a row stating no inhibition mode, used because none states noncompetitive "
            f"inhibition; {KITZ_WILSON_MEANING}")
        assert "measured competitive inhibition, and this model is noncompetitive" in out.notes[0]
        assert out.notes[0].endswith(f"is used instead; {KITZ_WILSON_MEANING}")
        assert len(out.notes) == 1, "the caveat is said once, in the note that makes the change"
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

    def test_adds_nothing_of_its_own_when_the_default_would_do_the_same(self):
        out = choose(ki(QUINOLINE_ROWS), "competitive_inhibition", "pyruvate", any_mode=True)
        assert out.measured["reaction_Ki"].chosen_because is None
        assert not any(ANY_MODE_FLAG in note for note in out.notes)
        # What the rows say against the model is said whichever way the
        # row was chosen.
        assert out.notes == choose(ki(QUINOLINE_ROWS), "competitive_inhibition",
                                   "pyruvate").notes


class TestEvidenceAgainstIsOneFunction:
    """`evidence_against` and its sentence, called directly on BRENDA's own
    rows. They are public because the literature layer makes the finding
    for the API and the TypeScript CLI (fallback_logic._mechanism_evidence),
    and a second copy of the rule there would drift from the note above."""

    @staticmethod
    def _read(rows):
        return [ki_mode.read_row(r["conditions"]) for r in rows]

    def test_the_pyruvate_row_contradicts_a_competitive_pyruvate_model(self):
        nadh, pyruvate = self._read(QUINOLINE_ROWS)
        assert ki_mode.evidence_against(nadh, [nadh, pyruvate], "competitive", "pyruvate") \
            is pyruvate
        # Compared as row_scope compares a versus: case and outer space only.
        assert ki_mode.evidence_against(nadh, [pyruvate], "competitive", " Pyruvate ") \
            is pyruvate

    def test_the_sentence_is_the_notes(self):
        nadh, pyruvate = self._read(QUINOLINE_ROWS)
        label = lambda r: ki_mode.row_label(r["value"], r["unit"], r["reference_id"])  # noqa: E731
        sentence = ki_mode.evidence_against_sentence(
            pyruvate, label(QUINOLINE_ROWS[1]), nadh, label(QUINOLINE_ROWS[0]),
            "competitive", "pyruvate")
        note = choose(ki(QUINOLINE_ROWS), "competitive_inhibition", "pyruvate").notes[0]
        assert note == "`reaction_Ki`: " + sentence

    def test_nothing_contradicts_a_row_of_the_models_own_assay(self):
        nadh, pyruvate = self._read(QUINOLINE_ROWS)
        # Noncompetitive versus pyruvate, carried for that model.
        assert ki_mode.evidence_against(pyruvate, [nadh, pyruvate], "noncompetitive",
                                        "pyruvate") is None
        # Competitive versus NADH, carried for a model of NADH.
        assert ki_mode.evidence_against(nadh, [nadh, pyruvate], "competitive", "NADH") is None
        # Mixed versus glucose stands in for a noncompetitive glucose model.
        mgatp, glucose = self._read(MGADP_ROWS)
        assert ki_mode.evidence_against(glucose, [mgatp, glucose], "noncompetitive",
                                        "glucose") is None

    def test_nothing_is_measured_against_no_substrate(self):
        nadh, pyruvate = self._read(QUINOLINE_ROWS)
        assert ki_mode.evidence_against(nadh, [nadh, pyruvate], "competitive", None) is None
        assert ki_mode.evidence_against(nadh, [nadh, pyruvate], "competitive", "") is None

    def test_a_row_stating_no_mode_contradicts_nothing(self):
        # Gossypol's three rows state no mode: none is evidence of any.
        rows = self._read(GOSSYPOL_ROWS)
        for want in ki_mode.MODES:
            assert ki_mode.evidence_against(rows[0], rows, want, "pyruvate") is None

    def test_a_pick_of_another_mode_is_not_evidence_against_itself(self):
        # --any-mode can keep the pyruvate row for a competitive model; the
        # row carried is then skipped, and the NADH row is not against
        # pyruvate, so nothing is found.
        nadh, pyruvate = self._read(QUINOLINE_ROWS)
        assert ki_mode.evidence_against(pyruvate, [pyruvate, nadh], "competitive",
                                        "pyruvate") is None

    def test_a_row_naming_another_isoform_is_not_evidence(self):
        # No BRENDA row read so far names an isoform and states a mode
        # versus a substrate (TestWithIsoform's MAO rows name what they
        # measured, not what they were measured against), so this is the
        # pyruvate row as it would read naming LDH-B, for an LDH-A model:
        # another protein's mechanism says nothing about this one's.
        nadh, pyruvate = self._read(QUINOLINE_ROWS)
        ldh_b = ki_mode.read_row("LDH-B, " + NONCOMPETITIVE_VS_PYRUVATE)
        assert ldh_b.isoform == "LDH-B"
        assert ki_mode.evidence_against(nadh, [nadh, ldh_b], "competitive", "pyruvate",
                                        isoform="LDH-A") is None
        assert ki_mode.evidence_against(nadh, [nadh, ldh_b], "competitive", "pyruvate") is ldh_b


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
        # The competitive LDH row was measured versus NADH, not pyruvate. It
        # is NOT known to be the constant of a model in which the inhibitor
        # competes with pyruvate: the same paper found it noncompetitive
        # versus pyruvate, which is evidence that it does not. It is taken
        # because it states the mechanism the model names and the other
        # row states a different one (ki_mode's docstring, "A mode stated
        # against another molecule"), and the notes say what the pyruvate
        # row means for the model. The pick is set to the other row (the
        # resolver returned 0.00059 first) to show the switch goes this way.
        out = choose(ki(QUINOLINE_ROWS, pick=1), "competitive_inhibition", "pyruvate")
        carried = out.measured["reaction_Ki"]
        assert carried.value == 0.00059
        assert carried.chosen_because == (
            "the row stating competitive inhibition versus NADH, this model's mechanism "
            "though not its substrate (pyruvate)")
        assert "is used instead" in out.notes[0]
        assert "evidence against this model's mechanism" in out.notes[1]


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
            "`reaction_Ki`: the row --isoform chose (1.95 mM, BRENDA ref 702238) was determined "
            "from Kitz-Wilson plots, the K_I of an irreversible inactivation; the row stating "
            "competitive inhibition (2.096 mM, BRENDA ref 702238), this model's mechanism, is "
            "used instead; it names MAO-A, as --isoform asked"]

    def test_the_two_steps_in_any_other_order_carry_another_row(self):
        """The case the module docstring gives for running the isoform step
        first and telling the mode step the isoform. Both other ways round
        carry a row the shipped order does not."""
        motif = {"reaction_Ki": ("competitive_inhibition", "ki")}
        mode_first = select_mode({"reaction_Ki": ki(BENZYLHYDRAZINE_ROWS)}, motif,
                                 substrate="kynuramine")
        then_isoform = select_isoform(mode_first.measured, "MAO-A")
        # The mode step keeps MAO-B's competitive pick; select_isoform does
        # not read modes, and takes MAO-A's first row, a Kitz-Wilson one.
        assert then_isoform.measured["reaction_Ki"].value == 1.95
        # Told nothing of the isoform, the mode step undoes --isoform.
        by_isoform = select_isoform({"reaction_Ki": ki(BENZYLHYDRAZINE_ROWS)}, "MAO-A")
        blind = select_mode(by_isoform.measured, motif, substrate="kynuramine")
        assert blind.measured["reaction_Ki"].value == 0.026
        assert "MAO-B" in blind.measured["reaction_Ki"].commentary
        # The shipped order.
        assert self._both(BENZYLHYDRAZINE_ROWS, "MAO-A", "competitive_inhibition")[1] \
            .measured["reaction_Ki"].value == 2.096

    def test_a_row_naming_the_isoform_outranks_a_row_stating_the_mode(self):
        """Inside the ranking, the isoform comes before the mode. No ranked
        set in the 1,247 Ki rows parsed on 2026-09-29 has a row naming the
        isoform with no mode beside a row naming none with the model's
        mode, so this compares the ranks of two real LDH rows directly
        rather than inventing a ranking that puts them side by side:
        gossypol's LDH-A row (ref 711801, no mode) and the quinoline
        sulfonamide's competitive row (ref 739793, no isoform)."""
        ldh_a = ki_mode._rows(ki(GOSSYPOL_ROWS, pick=1))[0][0]
        competitive = ki_mode._rows(ki(QUINOLINE_ROWS))[0][0]
        assert (ldh_a.isoform, ldh_a.mode) == ("LDH-A", "unstated")
        assert (competitive.isoform, competitive.mode) == (None, "competitive")

        def key(row):
            return ki_mode._rank(row, "competitive", "pyruvate", "LDH-A")[:-1]
        assert key(ldh_a) < key(competitive)
        # With the mode first the order would reverse, so this is the
        # comparison the order decides.
        assert (key(ldh_a)[1:], key(ldh_a)[0]) > (key(competitive)[1:], key(competitive)[0])

    def test_another_isoforms_row_of_the_models_mode_is_never_taken(self):
        # The only MAO-B row states no mode (a Kitz-Wilson row); MAO-A's
        # competitive 0.205 mM is a constant of the other protein and is not
        # taken. Either order of the two steps gives 0.791 here.
        by_isoform, by_mode = self._both(PHENYLHYDRAZINE_ROWS, "MAO-B", "competitive_inhibition")
        assert by_isoform.measured["reaction_Ki"].value == 0.791
        assert by_mode.measured["reaction_Ki"].value == 0.791
        assert by_mode.refused == {}
        assert by_mode.notes == [
            "`reaction_Ki`: the row carried (0.791 mM, BRENDA ref 702238) states no inhibition "
            f"mode, and {KITZ_WILSON_MEANING}; no other row this model could take states "
            "competitive inhibition or is a reversible constant stating no mode"]

    def test_no_isoform_asked_takes_the_competitive_row_of_either(self):
        out = choose(ki(BENZYLHYDRAZINE_ROWS), "competitive_inhibition", "kynuramine")
        assert out.measured["reaction_Ki"].value == 0.026 and out.notes == []

    def test_an_isoform_row_stating_no_mode_is_kept_over_the_other_isoforms(self):
        # MAO-A's rows state competitive (another mode for this model) and
        # nothing; MAO-B's are never candidates.
        by_isoform, by_mode = self._both(BENZYLHYDRAZINE_ROWS, "MAO-A", "uncompetitive_inhibition")
        assert by_mode.measured["reaction_Ki"].value == 1.95
        assert [n for n in by_mode.notes if "is used instead" in n] == []
        assert KITZ_WILSON_MEANING in by_mode.notes[0]

    def test_a_refusal_under_isoform_says_which_rows_it_read(self):
        by_isoform, by_mode = self._both(QUINOLINE_ROWS, "LDH-A", "uncompetitive_inhibition",
                                         substrate="pyruvate")
        # No row names LDH-A; select_isoform keeps the unnamed pick and says
        # so, and every unnamed row states another mode.
        assert "unknown" in by_isoform.notes[0]
        assert "among those for LDH-A or naming no isoform" in by_mode.refused["reaction_Ki"]


class TestKitzWilson:
    """Ref 702238's "determined from Kitz-Wilson plots" rows are the K_I of
    an irreversible inactivation (the paper shows the hydrazines alkylate
    MAO's flavin), filed in BRENDA's Ki table and stating no mode."""

    def test_the_row_is_read_as_one(self):
        rows = ki_mode._rows(ki(PHENYLHYDRAZINE_ROWS))[0]
        assert [r.kitz_wilson for r in rows] == [False, True, True]
        assert rows[1].says() == "no inhibition mode (a Kitz-Wilson inactivation constant)"

    def test_it_ranks_after_a_reversible_row_stating_no_mode(self):
        # Gossypol's LDH-B row states no mode and is a reversible Ki. No
        # ranked set parsed has both kinds, so the ranks are compared.
        kitz_wilson = ki_mode._rows(ki(PHENYLHYDRAZINE_ROWS, pick=1))[0][0]
        reversible = ki_mode._rows(ki(GOSSYPOL_ROWS))[0][0]
        for want in ("competitive", "noncompetitive", "uncompetitive"):
            assert (ki_mode._mode_rank(reversible, want, None)
                    < ki_mode._mode_rank(kitz_wilson, want, None))

    def test_it_is_still_carried_where_nothing_else_is_and_says_so(self):
        # An uncompetitive model: the competitive row is another mode, and
        # the Kitz-Wilson rows are all that is left. A placeholder would say
        # less than the row does, so the row is carried with what it is.
        out = choose(ki(PHENYLHYDRAZINE_ROWS), "uncompetitive_inhibition", "kynuramine")
        assert out.refused == {} and out.measured["reaction_Ki"].value == 0.523
        assert out.measured["reaction_Ki"].chosen_because.endswith(KITZ_WILSON_MEANING)

    def test_any_mode_keeping_one_says_what_it_is_without_claiming_it_was_the_best(self):
        # --any-mode keeps MAO-B's Kitz-Wilson row for a competitive model
        # although MAO-B's competitive row exists. The pick is set to the
        # Kitz-Wilson row (the resolver returned 0.026 first).
        out = choose(ki(BENZYLHYDRAZINE_ROWS, pick=1), "competitive_inhibition", "kynuramine",
                     any_mode=True)
        assert out.measured["reaction_Ki"].value == 0.048
        assert "without it the row stating competitive inhibition (0.026 mM" in out.notes[0]
        assert out.notes[1].endswith(KITZ_WILSON_MEANING)


class TestScope:
    def test_a_row_in_another_unit_is_never_substituted(self):
        in_um = ({**QUINOLINE_ROWS[1], "unit": "uM", "value": 2.52},)
        out = choose(ki(QUINOLINE_ROWS[:1] + in_um), "noncompetitive_inhibition", "pyruvate")
        why = out.refused["reaction_Ki"]
        assert "reaction_Ki" not in out.measured
        assert "or no mode exists in uM, and a row in another unit is never substituted" in why

    def test_a_fitting_row_passed_over_for_its_unit_is_named(self):
        # MAO-A's competitive row written in uM; the MAO-A row in mM states
        # no mode. The mM row is carried, and the note says what was
        # passed over and why.
        in_um = tuple({**r, "unit": "uM", "value": 2096.0} if r["value"] == 2.096 else r
                      for r in BENZYLHYDRAZINE_ROWS)
        by_isoform = select_isoform({"reaction_Ki": ki(in_um)}, "MAO-A")
        out = select_mode(by_isoform.measured, {"reaction_Ki": ("competitive_inhibition", "ki")},
                          substrate="kynuramine", isoform="MAO-A")
        assert out.measured["reaction_Ki"].value == 1.95
        assert out.notes[-1] == (
            "`reaction_Ki`: a row stating competitive inhibition (2096 uM, BRENDA ref 702238) "
            "was passed over for the row carried (1.95 mM, BRENDA ref 702238), because it is in "
            "uM, not mM, and a row in another unit is never substituted")

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
    """Each row set above, read back from a committed copy of the BRENDA page
    it came from, in the order BRENDA lists it (the resolver's order)."""

    @staticmethod
    def _parsed(page, ec, inhibitor, organism):
        from caterva.checkout import LiteratureLayerUnavailable, literature_module

        try:
            brenda_client = literature_module("brenda_client")
        except LiteratureLayerUnavailable:  # pragma: no cover - the wheel
            pytest.skip("the literature layer is not installed")
        # errors="replace", as `requests` decodes the live page: the LDH
        # page carries six bytes that are not UTF-8 (the README says which).
        html = gzip.decompress(page.read_bytes()).decode("utf-8", errors="replace")
        rows = brenda_client.parse_brenda_ki_html(html, ec, [inhibitor], target_organism=organism)
        return [(r.km_value, r.conditions, r.reference_id, r.organism) for r in rows
                if r.substrate == inhibitor]

    @staticmethod
    def _as_written(rows):
        return [(r["value"], r["conditions"], r["reference_id"], r["organism"]) for r in rows]

    def test_the_mixed_rows_are_in_the_recorded_hexokinase_page(self):
        page = REPO / "Tests" / "fixtures" / "recorded" / "brenda_2.7.1.1.html.gz"
        got = self._parsed(page, "2.7.1.1", "MgADP-", "Oryctolagus cuniculus")
        assert sorted(got) == self._as_written(MGADP_ROWS)

    @pytest.mark.parametrize("ec, inhibitor, rows", [
        ("1.1.1.27", QUINOLINE, QUINOLINE_ROWS),
        ("1.1.1.27", "gossypol", GOSSYPOL_ROWS),
        ("1.4.3.4", "benzylhydrazine", BENZYLHYDRAZINE_ROWS),
        ("1.4.3.4", "phenylhydrazine", PHENYLHYDRAZINE_ROWS),
    ], ids=["ldh-quinoline", "ldh-gossypol", "mao-benzylhydrazine", "mao-phenylhydrazine"])
    def test_the_rows_are_in_the_committed_page(self, ec, inhibitor, rows):
        page = REPO / "Tests" / "fixtures" / "ki_mode" / f"brenda_{ec}.html.gz"
        assert self._parsed(page, ec, inhibitor, "Homo sapiens") == self._as_written(rows)


class TestThroughTheCommand:
    """`_search_the_literature`, with the resolver's answer replaced by the
    rows it returned live, so the wiring is tested offline."""

    LDH = dict(subject="1.1.1.27", substrate="pyruvate", inhibitor=QUINOLINE)
    MAO = dict(subject="1.4.3.4", substrate="kynuramine", inhibitor="benzylhydrazine")
    #: Human LDH's pyruvate Km rows, as BRENDA's page lists them (the
    #: committed brenda_1.1.1.27.html.gz holds both).
    KM_ROWS = (_row(0.03, None, "286469", "Homo sapiens"),
               _row(0.398, None, "286442", "Homo sapiens"))

    @staticmethod
    def _source(rows):
        first = rows[0]
        return SimpleNamespace(value=first["value"], unit=first["unit"],
                               citation=f"BRENDA ref {first['reference_id']}",
                               organism=first["organism"], origin="literature",
                               cross_species=False, ph=first["ph"],
                               temperature_c=first["temperature_c"], buffer=None,
                               explicitly_unreported=(), candidates=list(rows),
                               commentary=first["conditions"])

    @classmethod
    def _search(cls, monkeypatch, query, rows, *, enzyme=None, km=True, branches=(),
                **flags):
        import caterva.compose.pipeline as pipeline
        from caterva.agents.adapters import NOT_FOUND_REASONS
        from caterva.compose.__main__ import _search_the_literature
        from caterva.compose.pipeline import compose

        enzyme = enzyme or cls.LDH
        nothing = NOT_FOUND_REASONS["not_found"]
        search = SimpleNamespace(branches=tuple(branches), resolutions={
            "reaction_Ki": SimpleNamespace(source=cls._source(rows)),
            # The LDH Km rows; any model here is only ever asked for the
            # Ki's selection, and the Km is what makes the search non-empty.
            "reaction_Km": (SimpleNamespace(source=cls._source(cls.KM_ROWS)) if km
                            else SimpleNamespace(source=None, reason=nothing)),
            "reaction_kcat": SimpleNamespace(source=None, reason=nothing),
        })
        monkeypatch.setattr(pipeline, "compose_and_parameterise", lambda *a, **k: (None, search))
        flags.setdefault("isoform", None)
        args = SimpleNamespace(subject=enzyme["subject"], organism="Homo sapiens",
                               substrate=enzyme["substrate"], inhibitor=enzyme["inhibitor"],
                               product=None, compound=[], **flags)
        model = compose(query, subject=enzyme["subject"], organism="Homo sapiens",
                        substrate=enzyme["substrate"],
                        compounds={"@inhibitor": enzyme["inhibitor"]})
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

    def test_the_evidence_against_the_mechanism_reaches_the_report(self, monkeypatch):
        model, note, _ = self._search(
            monkeypatch, "Michaelis-Menten with a competitive inhibitor", QUINOLINE_ROWS)
        assert model.measured["reaction_Ki"].value == 0.00059
        assert ("Measured against pyruvate this inhibitor is not competitive, which is evidence "
                "against this model's mechanism for it") in note

    def test_any_mode_reaches_the_selection(self, monkeypatch):
        model, note, _ = self._search(
            monkeypatch, "Michaelis-Menten with a noncompetitive inhibitor", QUINOLINE_ROWS,
            any_mode=True)
        assert model.measured["reaction_Ki"].value == 0.00059
        assert f"{ANY_MODE_FLAG} kept the resolver's pick" in note

    def test_the_command_runs_the_isoform_step_first_and_tells_the_mode_step(self, monkeypatch):
        # The benzylhydrazine case: 2.096 only in the shipped order; mode
        # first carries 1.95, and a mode step not told the isoform, 0.026.
        model, note, refused = self._search(
            monkeypatch, "Michaelis-Menten with a competitive inhibitor", BENZYLHYDRAZINE_ROWS,
            enzyme=self.MAO, isoform="MAO-A")
        assert refused is False
        carried = model.measured["reaction_Ki"]
        assert carried.value == 2.096 and "MAO-A" in carried.commentary
        assert "the row for MAO-A (1.95 mM, BRENDA ref 702238) is used instead" in note
        assert "the row --isoform chose (1.95 mM, BRENDA ref 702238) was determined" in note

    def test_a_refused_constant_is_not_described_as_not_found(self, monkeypatch):
        model, note, refused = self._search(
            monkeypatch, "Michaelis-Menten with an uncompetitive inhibitor", QUINOLINE_ROWS)
        assert refused is False
        assert "reaction_Ki" not in model.measured
        assert ANY_MODE_FLAG in model.not_found["reaction_Ki"]
        assert "1 returned by the search and not used (reaction_Ki)" in note
        # kcat was genuinely not found; the Ki was found and refused.
        assert "1 still the motif library's placeholder (reaction_kcat)" in note

    def test_when_every_value_is_refused_the_rest_is_still_said(self, monkeypatch):
        """Nothing measured is left, so the note takes the other branch; it
        used to return before reading what else the search did."""
        model, note, refused = self._search(
            monkeypatch, "Michaelis-Menten with an uncompetitive inhibitor", QUINOLINE_ROWS,
            km=False)
        assert refused is False and not model.measured
        assert note.startswith("No measured value was used: the search returned values for "
                               "reaction_Ki and each was withheld")
        assert ("2 still the motif library's placeholder (reaction_kcat, reaction_Km): the "
                "search ran and returned nothing for them") in note
        assert "every table was searched" not in note

    def test_when_every_value_is_refused_a_failed_search_is_still_said(self, monkeypatch):
        from caterva.agents.protocol import FunctionAgent
        from caterva.agents.scheduler import Scheduler

        def unreachable(view):
            raise ConnectionError("this test's kcat scout reaches nothing")

        run = Scheduler([FunctionAgent(name="kcat", reads=(), writes=(), fn=unreachable)]).run()
        assert run.failures, "the scheduler records the raise as a failure"
        model, note, refused = self._search(
            monkeypatch, "Michaelis-Menten with an uncompetitive inhibitor", QUINOLINE_ROWS,
            km=False, branches=[SimpleNamespace(build=SimpleNamespace(run=run))])
        assert refused is False
        assert "each was withheld" in note
        assert ("part of the search failed: ConnectionError: this test's kcat scout reaches "
                "nothing") in note

    def test_the_flag_is_on_the_command(self):
        from caterva.compose.__main__ import build_parser

        assert build_parser().parse_args(["x", "--any-mode"]).any_mode is True
        assert build_parser().parse_args(["x"]).any_mode is False
