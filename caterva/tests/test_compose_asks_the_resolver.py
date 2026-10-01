"""`caterva compose` tells the resolver what the model is of, and carries its row.

Until 2026-09-30 compose asked the literature layer's resolver for each
constant on evidence alone, and then chose among the rows it returned by the
model's isoform (`--isoform`) and inhibition mode. The API and the TypeScript
CLI ask the same resolver WITH the isoform and the mode, and it ranks every
row by them before it builds its evidence frontier. So the two could carry
different rows for one model: Trypanosoma cruzi hexokinase and ADP,
competitive model, 1.3 mM in compose and 1.5 mM from the API
(Tests/test_ki_mode_resolution.py, on the recorded page). This checks each
link of the fix, offline: what each request carries, that the scout passes it
on, what a refusal says, and `narrowed.carry`, which keeps the carried row the
resolver's whatever the selections arrive at.

The BRENDA rows are the committed pages' own, as test_ki_mode.py uses them.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from caterva.compose.export import Measurement
from caterva.compose.narrowed import Narrowed, carry, evidence_view, same_row, select_for_model
from caterva.compose.pipeline import compose

QUINOLINE = "3-[7-(2,4-dimethoxypyrimidin-5-yl)-3-sulfamoylquinolin-4-yl]aminobenzoic acid"
COMPETITIVE_VS_NADH = ("pH 7.5, 37°C, recombinant His-tagged enzyme, pyruvate reduction, "
                       "competitive versus NADH")
NONCOMPETITIVE_VS_PYRUVATE = ("pH 7.5, 37°C, recombinant His-tagged enzyme, pyruvate reduction, "
                              "noncompetitive versus pyruvate")


def _row(value, conditions, ref, organism="Homo sapiens", ph=None, temperature_c=None):
    return {"value": value, "unit": "mM", "organism": organism, "reference_id": ref,
            "conditions": conditions, "ph": ph, "temperature_c": temperature_c, "buffer": None}


#: BRENDA ref 739793, human LDH and the quinoline sulfonamide.
COMPETITIVE = _row(0.00059, COMPETITIVE_VS_NADH, "739793", ph=7.5, temperature_c=37.0)
NONCOMPETITIVE = _row(0.00252, NONCOMPETITIVE_VS_PYRUVATE, "739793", ph=7.5, temperature_c=37.0)
#: Trypanosoma cruzi hexokinase and ADP, the recorded page.
CRUZI_NO_MODE = _row(1.3, "natural hexokinase from epimastigotes, at pH 7.5", "640265",
                     organism="Trypanosoma cruzi", ph=7.5)
CRUZI_COMPETITIVE = _row(1.5, "competitive to ATP", "640216", organism="Trypanosoma cruzi")


def _source(row, candidates, evidence_only=(), mode_default=None):
    return SimpleNamespace(value=row["value"], unit=row["unit"],
                           citation=f"BRENDA ref {row['reference_id']}",
                           organism=row["organism"], origin="literature", cross_species=False,
                           ph=row["ph"], temperature_c=row["temperature_c"], buffer=None,
                           explicitly_unreported=(), candidates=tuple(candidates),
                           commentary=row["conditions"], evidence_only=tuple(evidence_only),
                           mode_default=mode_default)


def _search(**resolutions):
    return SimpleNamespace(resolutions=resolutions)


class TestEachRequestSaysWhatTheModelIsOf:
    def _model(self, query, **kw):
        return compose(query, subject="1.1.1.27", organism="Homo sapiens", substrate="pyruvate",
                       compounds={"@inhibitor": "gossypol"}, **kw)

    def test_an_inhibition_constant_carries_its_motifs_mode_and_the_models_substrate(self):
        from dataclasses import replace

        model = replace(self._model("Michaelis-Menten with a noncompetitive inhibitor"),
                        isoform="LDH-A")
        by_table = {r.table: r for r in model.parameter_requests()}
        ki = by_table["ki"]
        assert (ki.substrate, ki.inhibition_mode, ki.model_substrate, ki.isoform) == (
            "gossypol", "noncompetitive", "pyruvate", "LDH-A")
        # A Km or a kcat is ranked by the isoform only: a mode says nothing
        # about which Km row is the model's.
        for table in ("km", "kcat"):
            assert (by_table[table].inhibition_mode, by_table[table].model_substrate,
                    by_table[table].isoform) == (None, None, "LDH-A")

    def test_any_mode_asks_for_no_mode_and_sends_the_mode_to_compare(self):
        """`--any-mode` asks the question the API and the CLI ask with no
        mode, and sends the motif's mode, with the model's substrate, only as
        the one to compare with (`compare_mode`), so the resolver can say
        what the default would have carried."""
        model = self._model("Michaelis-Menten with a competitive inhibitor")
        ki = next(r for r in model.parameter_requests(any_mode=True) if r.table == "ki")
        assert (ki.inhibition_mode, ki.compare_mode, ki.model_substrate) == (
            None, "competitive", "pyruvate")
        default = next(r for r in model.parameter_requests() if r.table == "ki")
        assert (default.inhibition_mode, default.compare_mode, default.model_substrate) == (
            "competitive", None, "pyruvate")
        # A Km or a kcat has no mode either way.
        for request in model.parameter_requests(any_mode=True):
            if request.table != "ki":
                assert (request.inhibition_mode, request.compare_mode,
                        request.model_substrate) == (None, None, None)

    def test_product_inhibition_is_ranked_as_competitive(self):
        """`row_scope.MODE_OF_MOTIF`: a product inhibits competitively."""
        model = compose("Michaelis-Menten with product inhibition", subject="1.1.1.27",
                        organism="Homo sapiens", substrate="pyruvate",
                        compounds={"@product": "lactate"})
        modes = {r.table: r.inhibition_mode for r in model.parameter_requests()}
        assert modes.get("ki") == "competitive"

    def test_compose_and_parameterise_sends_them(self):
        from caterva.compose.pipeline import compose_and_parameterise

        seen = []

        def resolve(request, *, organism, allow_cross_species):
            seen.append(request)
            return SimpleNamespace(found=False, source="not_found")

        compose_and_parameterise("Michaelis-Menten with a competitive inhibitor",
                                 subject="1.1.1.27", organism="Homo sapiens",
                                 substrate="pyruvate", compounds={"@inhibitor": "gossypol"},
                                 isoform="LDH-A", resolve=resolve)
        ki = next(r for r in seen if r.table == "ki")
        assert (ki.isoform, ki.inhibition_mode, ki.model_substrate) == (
            "LDH-A", "competitive", "pyruvate")


class TestTheScoutPassesThemOn:
    def test_to_the_resolver(self, monkeypatch):
        from caterva.agents.scouts import brenda_resolver
        from caterva.checkout import literature_module

        from Tests.parameterize import ParameterRequest

        # The scout imports `Tests.fallback_logic`, or the literature layer's
        # flat `fallback_logic` where that fails; which one depends on what
        # is already on the path. Both are replaced, so nothing here reaches
        # BRENDA.
        calls = []
        record = lambda **kw: calls.append(kw) or "answer"  # noqa: E731
        monkeypatch.setattr(literature_module("fallback_logic"), "resolve_kinetic_value", record)
        import Tests.fallback_logic as packaged
        monkeypatch.setattr(packaged, "resolve_kinetic_value", record)
        resolve = brenda_resolver(search_literature=False)
        request = ParameterRequest(quantity="reaction_Ki", substrate="gossypol",
                                   ec_number="1.1.1.27", table="ki", isoform="LDH-A",
                                   inhibition_mode="competitive", model_substrate="pyruvate")
        assert resolve(request, organism="Homo sapiens", allow_cross_species=False) == "answer"
        assert {k: calls[0][k] for k in ("isoform", "inhibition_mode", "model_substrate",
                                         "substrate", "quantity")} == {
            "isoform": "LDH-A", "inhibition_mode": "competitive", "model_substrate": "pyruvate",
            "substrate": "gossypol", "quantity": "ki"}
        # A request that says nothing sends nothing: the resolver's defaults.
        resolve(ParameterRequest(quantity="reaction_Km", substrate="pyruvate",
                                 ec_number="1.1.1.27", table="km"),
                organism="Homo sapiens", allow_cross_species=False)
        assert not {"isoform", "inhibition_mode", "model_substrate", "compare_mode"} & set(calls[1])
        # --any-mode's request: no mode to rank by, one to compare with.
        resolve(ParameterRequest(quantity="reaction_Ki", substrate="gossypol",
                                 ec_number="1.1.1.27", table="ki", compare_mode="competitive",
                                 model_substrate="pyruvate"),
                organism="Homo sapiens", allow_cross_species=False)
        assert "inhibition_mode" not in calls[2]
        assert (calls[2]["compare_mode"], calls[2]["model_substrate"]) == ("competitive", "pyruvate")

    def test_a_refusal_keeps_the_resolvers_word(self):
        from caterva.agents.scheduler import Scheduler
        from caterva.agents.scouts import ParameterScout, param_key

        from Tests.parameterize import ParameterRequest

        refused = SimpleNamespace(
            found=False, source="mode_withheld",
            modes_available=["competitive inhibition versus NADH",
                             "noncompetitive inhibition versus pyruvate"])
        scout = ParameterScout(request=ParameterRequest(quantity="reaction_Ki", table="ki"),
                               resolve=lambda request, **kw: refused)
        resolution = Scheduler([scout]).run().blackboard.get(param_key("reaction_Ki"))
        assert resolution.source is None and resolution.outcome == "mode_withheld"
        assert resolution.reason.endswith(
            "-- the rows state: competitive inhibition versus NADH; noncompetitive inhibition "
            "versus pyruvate")


class TestWhatARefusalSays:
    @pytest.mark.parametrize("result, ends", [
        (SimpleNamespace(found=False, source="isoform_withheld",
                         isoforms_available=["LDH-A", "LDH-B", "LDH-C"]),
         "a different protein's, so none is used -- the rows measured: LDH-A, LDH-B, LDH-C"),
        (SimpleNamespace(found=False, source="variant_withheld",
                         variant_candidates_available=["Y124C", "isozyme H4"]),
         "(ADR 0029) -- the variants: Y124C, isozyme H4"),
    ])
    def test_it_names_what_it_withheld(self, result, ends):
        from caterva.agents.adapters import to_parameter_source

        source, reason = to_parameter_source("reaction_Ki", result)
        assert source is None and reason.endswith(ends)

    def test_compose_calls_it_withheld_and_names_the_flag(self):
        from caterva.compose.ki_mode import ANY_MODE_FLAG

        search = _search(
            reaction_Ki=SimpleNamespace(source=None, reason="every row ... so none is used",
                                        outcome="mode_withheld"),
            reaction_Km=SimpleNamespace(source=None, reason="no LDH-X row",
                                        outcome="isoform_withheld"),
            reaction_kcat=SimpleNamespace(source=None, reason="nothing found", outcome="not_found"),
        )
        chosen = select_for_model(search, {"reaction_Ki": ("competitive_inhibition", "ki")},
                                  substrate="pyruvate", isoform="LDH-X", any_mode=False)
        assert chosen.withheld["reaction_Ki"].endswith(
            f". Pass {ANY_MODE_FLAG} to use the resolver's pick whatever mode it states; the "
            f"report still flags it")
        assert chosen.withheld["reaction_Km"] == "no LDH-X row (--isoform LDH-X)"
        # Not found is not withheld.
        assert "reaction_kcat" not in chosen.withheld


class TestTheViewTheSelectionsRead:
    def test_the_unasked_pick_is_the_resolvers_pick_and_the_asked_row_comes_first(self):
        """LDH, noncompetitive model: the resolver asked returns 0.00252 and,
        unasked, 0.00059. The selections are shown 0.00059 as "the resolver's
        pick", so the report says what the mode replaced, as it always has."""
        answer = _source(NONCOMPETITIVE, [NONCOMPETITIVE], [COMPETITIVE, NONCOMPETITIVE])
        chosen = select_for_model(_search(reaction_Ki=SimpleNamespace(source=answer)),
                                  {"reaction_Ki": ("noncompetitive_inhibition", "ki")},
                                  substrate="pyruvate", isoform=None, any_mode=False)
        carried = chosen.measured["reaction_Ki"]
        assert (carried.value, carried.commentary) == (0.00252, NONCOMPETITIVE_VS_PYRUVATE)
        assert chosen.notes == [
            "`reaction_Ki`: the resolver's pick (0.00059 mM, BRENDA ref 739793) measured "
            "competitive inhibition versus NADH, and this model is noncompetitive; the row "
            "stating noncompetitive inhibition versus pyruvate (0.00252 mM, BRENDA ref "
            "739793), this model's mechanism and substrate, is used instead"]
        assert carried.chosen_because == (
            "the row stating noncompetitive inhibition versus pyruvate, this model's mechanism "
            "and substrate")

    def test_the_rows_set_aside_still_speak_against_the_mechanism(self):
        """Competitive model: the resolver asked keeps only the competitive
        row; the noncompetitive row versus pyruvate, which it set aside, is
        still named as evidence against the model's mechanism."""
        answer = _source(COMPETITIVE, [COMPETITIVE], [COMPETITIVE, NONCOMPETITIVE])
        chosen = select_for_model(_search(reaction_Ki=SimpleNamespace(source=answer)),
                                  {"reaction_Ki": ("competitive_inhibition", "ki")},
                                  substrate="pyruvate", isoform=None, any_mode=False)
        assert chosen.measured["reaction_Ki"].value == 0.00059
        assert chosen.measured["reaction_Ki"].chosen_because is None
        assert "is evidence against this model's mechanism for it" in chosen.notes[0]

    def test_the_trypanosoma_cruzi_row_the_frontier_dropped_is_carried(self):
        answer = _source(CRUZI_COMPETITIVE, [CRUZI_COMPETITIVE], [CRUZI_NO_MODE])
        chosen = select_for_model(_search(reaction_Ki=SimpleNamespace(source=answer)),
                                  {"reaction_Ki": ("competitive_inhibition", "ki")},
                                  substrate="glucose", isoform=None, any_mode=False)
        assert chosen.measured["reaction_Ki"].value == 1.5
        # The report now prints a 1.3 to 1.5 mM spread where it printed none
        # (1.3 mM was carried alone). Deliberate: the rows a model carries
        # beside its own are the resolver's unasked frontier, as they were
        # before 2026-09-30 whenever a selection moved off the resolver's
        # pick (LDH's competitive and noncompetitive quinoline rows, 0.00059
        # and 0.00252 mM, have always been one spread), plus the frontier of
        # the rows it kept for the model. 1.3 mM is a real ADP Ki of the same
        # enzyme; that a model carries 1.5 does not make it disagree less.
        assert chosen.measured["reaction_Ki"].disagreement == (1.3, 1.5)

    def test_an_answer_with_nothing_unasked_passes_through(self):
        m = Measurement(0.03, "mM", "BRENDA ref 286469", commentary=None)
        view = evidence_view({"reaction_Km": m}, {})
        assert view.measured["reaction_Km"] is m and view.chosen == {}


class TestAnyModeNamesTheRowTheDefaultCarries:
    """`--any-mode` carries the resolver's answer to a request with no mode,
    and says what the default would carry from the resolver's own answer to
    the default's question (`mode_default`), not from the rows it holds.
    The rows are the committed pages'; Tests/test_ki_mode_resolution.py
    runs the same through the real resolver."""

    def _default(self, mode, substrate, row=None, modes=()):
        return {"mode": mode, "model_substrate": substrate, "row": row,
                "modes_available": tuple(modes)}

    def test_the_trypanosoma_cruzi_row_the_answer_does_not_hold_is_named(self):
        """The case that was stated rather than fixed: the no-mode answer
        holds 1.3 mM alone, so a note over its rows could only say nothing.
        The resolver's default answer is 1.5 mM, and the note names it."""
        answer = _source(CRUZI_NO_MODE, [CRUZI_NO_MODE],
                         mode_default=self._default("competitive", "glucose", CRUZI_COMPETITIVE))
        chosen = select_for_model(_search(reaction_Ki=SimpleNamespace(source=answer)),
                                  {"reaction_Ki": ("competitive_inhibition", "ki")},
                                  substrate="glucose", isoform=None, any_mode=True)
        carried = chosen.measured["reaction_Ki"]
        assert (carried.value, carried.commentary) == (1.3, CRUZI_NO_MODE["conditions"])
        assert carried.chosen_because == "the resolver's pick, kept by --any-mode"
        assert chosen.notes == [
            "`reaction_Ki`: --any-mode kept the resolver's pick (1.3 mM, BRENDA ref 640265), "
            "which states no inhibition mode; without it the row stating competitive inhibition "
            "versus ATP (1.5 mM, BRENDA ref 640216), this model's mechanism though not its "
            "substrate (glucose), would be used; the resolver, asked for a competitive model of "
            "glucose, ranks by the mode every row it keeps once variants are set aside, before "
            "choosing on evidence, and returns it"]
        # The default's row is among the alternatives, so the spread printed
        # is the one the default prints.
        assert carried.disagreement == (1.3, 1.5)

    def test_a_default_that_refuses_is_said_with_the_modes_it_found(self):
        answer = _source(COMPETITIVE, [COMPETITIVE, NONCOMPETITIVE], mode_default=self._default(
            "uncompetitive", "pyruvate", None, ["competitive inhibition versus NADH",
                                                "noncompetitive inhibition versus pyruvate"]))
        chosen = select_for_model(_search(reaction_Ki=SimpleNamespace(source=answer)),
                                  {"reaction_Ki": ("uncompetitive_inhibition", "ki")},
                                  substrate="pyruvate", isoform=None, any_mode=True)
        assert chosen.measured["reaction_Ki"].value == 0.00059 and chosen.withheld == {}
        assert chosen.notes[0].endswith(
            "without it the constant would be refused; the resolver, asked for an uncompetitive "
            "model of pyruvate, finds that every row it keeps once variants are set aside "
            "states another mode (competitive "
            "inhibition versus NADH; noncompetitive inhibition versus pyruvate)")

    def test_a_default_that_carries_the_same_row_adds_nothing(self):
        answer = _source(COMPETITIVE, [COMPETITIVE, NONCOMPETITIVE],
                         mode_default=self._default("competitive", "pyruvate", COMPETITIVE))
        chosen = select_for_model(_search(reaction_Ki=SimpleNamespace(source=answer)),
                                  {"reaction_Ki": ("competitive_inhibition", "ki")},
                                  substrate="pyruvate", isoform=None, any_mode=True)
        assert chosen.measured["reaction_Ki"].chosen_because is None
        assert not any("--any-mode" in note for note in chosen.notes)

    def test_without_any_mode_a_default_is_not_read(self):
        """A default only answers --any-mode's question; the default path
        carries the resolver's row and says what its choice replaced."""
        answer = _source(CRUZI_NO_MODE, [CRUZI_NO_MODE],
                         mode_default=self._default("competitive", "glucose", CRUZI_COMPETITIVE))
        chosen = select_for_model(_search(reaction_Ki=SimpleNamespace(source=answer)),
                                  {"reaction_Ki": ("competitive_inhibition", "ki")},
                                  substrate="glucose", isoform=None, any_mode=False)
        assert chosen.measured["reaction_Ki"].disagreement is None
        assert not any("--any-mode" in note for note in chosen.notes)

    def test_the_adapter_hands_it_on_as_a_plain_record(self):
        from caterva.agents.adapters import mode_default_of, to_parameter_source

        result = SimpleNamespace(
            found=True, value=1.3, unit="mM", organism="Trypanosoma cruzi",
            assay_ph=7.5, assay_temperature_c=None, assay_buffer=None,
            citation=SimpleNamespace(source="BRENDA", reference_id="640265"),
            cross_species_flag=False, assay_unreported=[], ensemble_candidates=[CRUZI_NO_MODE],
            commentary=CRUZI_NO_MODE["conditions"], evidence_only=[],
            mode_default=SimpleNamespace(mode="competitive", model_substrate="glucose",
                                         row=CRUZI_COMPETITIVE, modes_available=[]))
        source, _ = to_parameter_source("reaction_Ki", result)
        assert source.mode_default == {"mode": "competitive", "model_substrate": "glucose",
                                       "row": CRUZI_COMPETITIVE, "modes_available": ()}
        # A result that predates the field, or says nothing, gives None.
        assert mode_default_of(SimpleNamespace()) is None
        assert mode_default_of(SimpleNamespace(mode_default=None)) is None


class TestCarry:
    """What happens when the selections, choosing among the rows they are
    shown, arrive at another row than the resolver's. Of 1,353 found answers
    checked on 2026-09-30 (every organism, compound and table on the three
    committed full pages, asked for each isoform its rows name and, for a Ki,
    each mode), none does: this is the rule for when one does, checked on
    two real rows put side by side, not a pool BRENDA holds."""

    def _narrowed(self):
        answer = Measurement(0.00252, "mM", "BRENDA ref 739793 — “a title”",
                             organism="Homo sapiens", commentary=NONCOMPETITIVE_VS_PYRUVATE,
                             alternatives=(NONCOMPETITIVE,))
        view = evidence_view({"reaction_Ki": answer},
                             {"reaction_Ki": (COMPETITIVE, NONCOMPETITIVE)})
        return view

    def test_the_resolvers_row_is_carried_and_said_to_be(self):
        narrowed = self._narrowed()
        elsewhere = narrowed.measured["reaction_Ki"]  # the unasked pick, 0.00059
        measured, refused, notes = carry({"reaction_Ki": elsewhere}, {}, narrowed,
                                         {"reaction_Ki": "noncompetitive"}, "LDH-A")
        carried = measured["reaction_Ki"]
        assert (carried.value, carried.commentary) == (0.00252, NONCOMPETITIVE_VS_PYRUVATE)
        # The resolver's own Measurement, with its full citation.
        assert carried.citation == "BRENDA ref 739793 — “a title”"
        assert carried.chosen_because == (
            "the resolver's row for LDH-A and a noncompetitive model, ranked among every row "
            "BRENDA holds before choosing on evidence")
        assert refused == {} and notes == [
            "`reaction_Ki`: choosing among the rows the evidence alone returned arrives at "
            "0.00059 mM, BRENDA ref 739793; the resolver, asked for LDH-A and a noncompetitive "
            "model, ranks every row BRENDA holds by it before choosing on evidence, and returns "
            "0.00252 mM, BRENDA ref 739793, which is used, so this model carries the row the "
            "API and the TypeScript CLI return for it"]

    def test_a_selection_refusing_the_resolvers_row_is_overruled_and_said_to_be(self):
        narrowed = self._narrowed()
        measured, refused, notes = carry({}, {"reaction_Ki": "every row states another mode"},
                                         narrowed, {"reaction_Ki": "noncompetitive"}, None)
        assert measured["reaction_Ki"].value == 0.00252 and refused == {}
        assert notes[0].startswith("`reaction_Ki`: the selections here refused it (every row "
                                   "states another mode)")

    def test_the_same_row_is_left_alone(self):
        narrowed = self._narrowed()
        mine = narrowed.answers["reaction_Ki"]
        measured, _, notes = carry({"reaction_Ki": mine}, {}, narrowed, {}, None)
        assert measured["reaction_Ki"] is mine and notes == []

    def test_rows_are_the_same_by_value_commentary_and_reference(self):
        assert same_row(COMPETITIVE, dict(COMPETITIVE, ph=None))
        assert not same_row(COMPETITIVE, NONCOMPETITIVE)
        assert not same_row(COMPETITIVE, dict(COMPETITIVE, reference_id="1"))
        assert isinstance(Narrowed(measured={}), Narrowed)
