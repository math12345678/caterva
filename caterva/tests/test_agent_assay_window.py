"""The assay window: a condition mismatch re-searched, never invented (ADR 0171).

THE CASE
--------
A Km measured at pH 8.0 and a kcat measured at pH 6.0 describe no single
assay, but both are real, cited numbers. The old chain reports the gap and
stops. This machinery turns the gap into a SEARCH when the literature allows
it: the resolver already returns every row it considered, with its
conditions, so the critic can ask "is one of this value's own rows inside
the other's conditions", and -- only then -- emit an `assay_window`
constraint. The scout honours it by re-selecting among those same rows. The
re-selected number is a measurement that is already in the table; nothing is
interpolated, averaged or corrected toward the window.

The tests here are the mechanism on synthetic tables, exactly shaped like
the real BRENDA frontier. `Tests/test_agent_architecture_on_real_brenda.py`
repeats the flagship case over real committed BRENDA markup.
"""

from __future__ import annotations

import pytest

from caterva.agents.assay_window import (
    WINDOW_KIND,
    candidate_distance,
    parse_window_requirement,
    window_requirement,
    within_window,
)
from caterva.agents.assembly import build_model
from caterva.agents.constraints import Constraint
from caterva.agents.scouts import ParameterScout, param_key
from caterva.continuous.networks import mm_competitive_network

NETWORK = mm_competitive_network(km=0.1, vmax=1.0, ki=0.5, s0=1.0, i=0.2)


class FakeKineticResult:
    """The fields of `KineticResult` the adapter reads, plus the frontier."""

    def __init__(self, **kw):
        self.found = kw.get("found", False)
        self.value = kw.get("value")
        self.unit = kw.get("unit")
        self.organism = kw.get("organism")
        self.source = kw.get("source", "not_found")
        self.citation = kw.get("citation")
        self.cross_species_flag = kw.get("cross_species_flag", False)
        self.assay_ph = kw.get("assay_ph")
        self.assay_temperature_c = kw.get("assay_temperature_c")
        self.assay_buffer = kw.get("assay_buffer")
        self.assay_unreported = kw.get("assay_unreported", [])
        self.ensemble_candidates = kw.get("ensemble_candidates", [])
        self.cross_species_organisms_available = kw.get("available", [])


def row(value, ph, temperature_c=None, *, unit="mM", reference_id="R", buffer=None):
    """One frontier row, exactly the dict `_score_frontier` produces."""
    return {
        "value": float(value),
        "unit": unit,
        "organism": "",
        "reference_id": reference_id,
        "conditions": "idem",
        "ph": ph,
        "temperature_c": temperature_c,
        "buffer": buffer,
        "grades": {
            "assay_completeness": "good",
            "condition_proximity": "good",
            "organism_match": "good",
        },
    }


def windowed_resolver(rows):
    """A resolver over `{quantity: [frontier rows]}`.

    The winner is the row with the smallest value, which is the fallback
    the live resolver reaches; the frontier is the whole table. Both are
    facts about the table rather than about constraints, so they do not
    change when a constraint appears -- what changes is which row the scout
    presents, which is exactly what these tests watch.
    """
    def resolve(request, *, organism, allow_cross_species):
        table = rows.get(request.quantity, [])
        if not table:
            return FakeKineticResult(found=False, source="not_found")
        winner = min(table, key=lambda c: c["value"])
        return FakeKineticResult(
            found=True,
            value=winner["value"],
            unit=winner["unit"],
            organism=winner.get("organism") or "",
            source="brenda_exact",
            citation=type("C", (), {"source": "BRENDA", "reference_id": "test"})(),
            assay_ph=winner.get("ph"),
            assay_temperature_c=winner.get("temperature_c"),
            assay_buffer=winner.get("buffer"),
            ensemble_candidates=[dict(c) for c in table],
        )
    return resolve


def request(quantity, table):
    from Tests.parameterize import ParameterRequest
    return ParameterRequest(
        quantity=quantity, subject="L-lactate dehydrogenase",
        substrate="lactate", ec_number="1.1.1.27", table=table,
    )


class TestTheWindowText:
    def test_requirement_is_canonical_and_round_trips(self) -> None:
        # Constraint identity is (kind, subject, requirement): two otherwise
        # identical windows must render into the SAME string or the store
        # never deduplicates them and the run never converges.
        text = window_requirement(ph=8.0, temperature_c=25.0)
        assert text == "pH 8; temperature 25"
        assert parse_window_requirement(text) == (8.0, 25.0, None)

        # An axis the reference does not state is simply absent, and parses
        # back to None rather than to a guessed number.
        ph_only = window_requirement(ph=8.0, temperature_c=None)
        assert ph_only == "pH 8"
        assert parse_window_requirement(ph_only) == (8.0, None, None)
        no_axes = window_requirement(ph=None, temperature_c=None)
        assert no_axes == ""
        assert parse_window_requirement(no_axes) == (None, None, None)

    def test_a_negative_temperature_round_trips(self) -> None:
        text = window_requirement(ph=None, temperature_c=-25.0)
        assert parse_window_requirement(text) == (None, -25.0, None)

    def test_a_buffer_axis_round_trips_and_is_canonical(self) -> None:
        # The buffer names the reference's own buffer (ADR 0175). Parsed
        # buffer text is whitespace-collapsed, so two spellings of one
        # buffer render identically and deduplicate as one constraint.
        text = window_requirement(
            ph=7.4, temperature_c=37.0, buffer="0.1 M MOPS buffer"
        )
        assert text == "pH 7.4; temperature 37; buffer 0.1 M MOPS buffer"
        assert parse_window_requirement(text) == (7.4, 37.0, "0.1 M MOPS buffer")

        padded = window_requirement(
            ph=7.4, temperature_c=37.0, buffer="  0.1 M  MOPS buffer "
        )
        assert padded == text

        # A reference that states no buffer demands none: the axis is
        # absent from the text, exactly like an unstated pH.
        no_buffer = window_requirement(ph=7.4, temperature_c=37.0)
        assert "buffer" not in no_buffer
        assert parse_window_requirement(no_buffer) == (7.4, 37.0, None)


class TestTheDistanceMetric:
    def test_zero_is_the_row_that_sits_on_the_reference(self) -> None:
        assert candidate_distance(
            row(32.0, 8.0, 25.0), reference_ph=8.0, reference_temperature_c=25.0
        ) == 0.0

    def test_each_axis_is_normalised_by_its_own_threshold(self) -> None:
        # One pH unit is the full window (distance 1); ten Celsius is the
        # full window (distance 1): same ruler, different step size.
        assert candidate_distance(
            row(1.0, 7.0, 15.0), reference_ph=8.0, reference_temperature_c=25.0
        ) == 1.0
        assert candidate_distance(
            row(1.0, 6.9, 25.0), reference_ph=8.0, reference_temperature_c=25.0
        ) == pytest.approx(1.1)

    def test_an_axis_the_reference_is_silent_on_is_skipped(self) -> None:
        # Km has no temperature; a kcat row at any temperature can still be
        # inside the pH window, because nothing on the temperature axis was
        # ever asserted.
        assert candidate_distance(
            row(32.0, 8.0, 25.0), reference_ph=8.0, reference_temperature_c=None
        ) == 0.0

    def test_unassessable_is_not_close(self) -> None:
        # No stated conditions: the row is neither inside nor outside -- it
        # must not be reportable as close. Distinguishable from distance 0,
        # which the same API returns for the reference itself.
        assert candidate_distance(
            row(1.0, None, None), reference_ph=8.0, reference_temperature_c=25.0
        ) is None
        assert not within_window(
            row(1.0, None, None), reference_ph=8.0, reference_temperature_c=25.0
        )

    def test_boundary_is_inside(self) -> None:
        assert within_window(
            row(1.0, 7.0, 25.0), reference_ph=8.0, reference_temperature_c=25.0
        )


class TestTheBufferAxis:
    """The buffer is a categorical gate, not a distance (ADR 0175).

    A buffer has no `*_SERIOUS` half-width -- two buffers are either the
    same identity or they are not. `within_window` enforces that as a hard
    gate on top of the numeric distance, and the rule it uses is the one the
    model judge already uses to report a `buffer_mismatch`, so a window and
    the judge never disagree about which rows could fix a mismatch.
    """

    def test_a_different_buffer_is_outside_no_matter_how_close(self) -> None:
        # Distance 0 (the row sits exactly on the reference's pH and
        # temperature) is still outside when the buffer differs: closeness
        # on the numbers is not closeness on an identity.
        assert not within_window(
            row(1.0, 7.4, 37.0, buffer="Tris"),
            reference_ph=7.4,
            reference_temperature_c=37.0,
            reference_buffer="0.1 M MOPS buffer",
        )

    def test_an_equivalent_buffer_is_inside(self) -> None:
        # Same normalized string -- the judge's rule -- is inside.
        assert within_window(
            row(1.0, 7.4, 37.0, buffer="0.1 M MOPS buffer"),
            reference_ph=7.4,
            reference_temperature_c=37.0,
            reference_buffer="0.1 M MOPS buffer",
        )

    def test_silence_on_a_demanded_buffer_is_not_compliance(self) -> None:
        # The row states a pH and temperature but no buffer. Claiming it
        # satisfies "must be in 0.1 M MOPS buffer" would be reporting
        # silence as proximity, the error this module exists to refuse.
        assert not within_window(
            row(1.0, 7.4, 37.0, buffer=None),
            reference_ph=7.4,
            reference_temperature_c=37.0,
            reference_buffer="0.1 M MOPS buffer",
        )

    def test_a_window_that_names_no_buffer_demands_none(self) -> None:
        # No reference buffer -> no buffer axis -> a buffer-silent row is
        # judged on its numbers alone, exactly as before ADR 0175.
        assert within_window(
            row(1.0, 7.4, 37.0, buffer=None),
            reference_ph=7.4,
            reference_temperature_c=37.0,
            reference_buffer=None,
        )

    def test_the_window_rule_is_the_judge_rule(self) -> None:
        # model_compatibility.assess builds its `buffer_mismatch` from
        # distinct case-collapsed strings; the window must come to the same
        # verdict on the same pair, or a window could "resolve" a mismatch
        # the judge still sees (ADR 0027).
        from Tests.assay_conditions import buffers_equivalent

        assert buffers_equivalent("0.1 M MOPS buffer", "0.1 M MOPS buffer")
        assert buffers_equivalent("HEPES", "hepes")
        assert not buffers_equivalent("0.5 M Tris-HCl", "500 mM Tris")
        assert not buffers_equivalent("0.1 M MOPS buffer", None)
        assert not buffers_equivalent(None, None)
        assert not buffers_equivalent("0.1 M MOPS buffer", "Tris")


class TestTheCriticDecidesWhen:
    """The three outcomes the critic's `_condition_constraint` can have."""

    def _notes(self, build, agent="critic:coherence"):
        return [
            note
            for record in build.run.rounds
            for run in record.ran
            if run.agent == agent
            for note in run.notes
        ]

    def test_only_one_side_can_move_so_it_gets_the_constraint(self) -> None:
        # Km's table is all pH-8 rows -- it cannot satisfy a pH-6 window.
        # kcat's table has a pH-8 row, so it CAN satisfy Km's. Exactly one
        # direction works, and it is the one the constraint demands.
        rows = {
            "Km": [row(21.78, 8.0), row(10.73, 8.0)],
            "kcat": [
                row(94.7, 5.5, 30.0, unit="1/s"),
                row(21.1, 6.0, 25.0, unit="1/s"),
                row(32.0, 8.0, 25.0, unit="1/s"),
            ],
        }
        from caterva.agents.assembly import build_model

        build = build_model(
            network=NETWORK,
            requests=[request("Km", "km"), request("kcat", "kcat")],
            resolve=windowed_resolver(rows),
        )
        windows = build.run.constraints.of_kind(WINDOW_KIND)
        assert len(windows) == 1
        assert windows[0].subject == "kcat"
        assert windows[0].requirement == "pH 8"

    def test_both_can_move_so_caterva_will_not_pick_a_side(self) -> None:
        # Each value has a row inside the other's conditions, so either
        # could be re-selected and neither is privileged. Emitting one
        # direction would be an invisible scientific decision -- the exact
        # class of thing this architecture exists to remove.
        rows = {
            "Km": [row(10.0, 8.0), row(30.0, 6.0)],
            "Ki": [row(0.5, 6.0), row(1.0, 8.0)],
        }
        build = build_model(
            network=NETWORK,
            requests=[request("Km", "km"), request("Ki", "ki")],
            resolve=windowed_resolver(rows),
        )
        assert build.run.constraints.of_kind(WINDOW_KIND) == ()
        assert any("neither is privileged" in n for n in self._notes(build))

    def test_neither_can_move_so_it_stays_a_finding(self) -> None:
        # No frontier row of either value sits inside the other's
        # conditions. A constraint promising a re-search would promise the
        # impossible; the mismatch stands, named as one.
        rows = {
            "Km": [row(10.73, 8.0), row(21.78, 8.0)],
            "Ki": [row(0.5, 5.5), row(0.0116, 5.5)],
        }
        build = build_model(
            network=NETWORK,
            requests=[request("Km", "km"), request("Ki", "ki")],
            resolve=windowed_resolver(rows),
        )
        assert build.run.constraints.of_kind(WINDOW_KIND) == ()
        assert any("no re-search could remove" in n for n in self._notes(build))

    def test_a_buffer_mismatch_becomes_a_window_when_a_row_states_it(
        self,
    ) -> None:
        """The gap ADR 0172 left open, now closed (ADR 0175).

        Two values sit at the SAME pH and temperature, so neither pH nor
        temperature mismatch fires; they differ only in buffer -- which used
        to be permanently non-actionable because the frontier carried no
        buffer axis. kcat's own frontier holds a row really measured in
        Km's buffer, so the buffer mismatch becomes a window naming that
        buffer, and only kcat can move.
        """
        rows = {
            "Km": [
                row(10.73, 7.4, 37.0, buffer="HEPES"),
                row(21.78, 7.4, 37.0, buffer="HEPES"),
            ],
            "kcat": [
                row(21.1, 7.4, 37.0, unit="1/s", buffer="Tris"),
                row(35.0, 7.4, 37.0, unit="1/s", buffer="HEPES"),
            ],
        }
        build = build_model(
            network=NETWORK,
            requests=[request("Km", "km"), request("kcat", "kcat")],
            resolve=windowed_resolver(rows),
        )
        windows = build.run.constraints.of_kind(WINDOW_KIND)
        assert len(windows) == 1
        assert windows[0].subject == "kcat"
        assert "buffer HEPES" in windows[0].requirement

    def test_a_buffer_mismatch_without_a_matching_row_stays_a_finding(
        self,
    ) -> None:
        # Neither value's frontier holds a row stating the other's buffer,
        # so no re-search could satisfy a buffer window; emitting one would
        # be unactionable. It stays a finding with the reason stated.
        rows = {
            "Km": [row(10.73, 7.4, 37.0, buffer="HEPES")],
            "kcat": [row(21.1, 7.4, 37.0, unit="1/s", buffer="Tris")],
        }
        build = build_model(
            network=NETWORK,
            requests=[request("Km", "km"), request("kcat", "kcat")],
            resolve=windowed_resolver(rows),
        )
        assert build.run.constraints.of_kind(WINDOW_KIND) == ()
        assert any("no re-search could remove" in n for n in self._notes(build))


class TestTheScoutReSelects:
    def _scout_result(self, quantity, resolve, windows=()):
        from caterva.agents.scheduler import Scheduler
        from caterva.agents.protocol import Agent

        from Tests.parameterize import Resolution

        scout = ParameterScout(request=request(quantity, quantity.lower()), resolve=resolve)
        scheduler = Scheduler([scout])
        return scheduler.run(initial_constraints=list(windows)), scout

    def test_it_chooses_the_nearest_inside_row_over_the_resolver_default(
        self,
    ) -> None:
        rows = {
            "kcat": [
                row(94.7, 5.5, 30.0, unit="1/s"),
                row(21.1, 6.0, 25.0, unit="1/s"),
                row(32.0, 8.0, 25.0, unit="1/s"),
            ],
        }
        window = Constraint(
            kind="assay_window", subject="kcat", requirement="pH 8",
            reason="test", raised_by="test",
        )
        report, _ = self._scout_result(
            "kcat", windowed_resolver(rows), windows=(window,)
        )
        source = report.blackboard.get(param_key("kcat")).source
        assert source.value == 32.0
        assert source.ph == 8.0
        assert source.temperature_c == 25.0
        # Cited as the adapter cites the resolver's own row, so the path that
        # produced a citation cannot be read off it (adapters.citation_text).
        assert source.citation == "BRENDA ref R"

        note = next(
            n for r in report.rounds for ar in r.ran if ar.agent == "scout:kcat"
            for n in ar.notes
        )
        assert "chose 32.0 1/s @ pH 8, 25 C" in note
        assert "over the resolver's default 21.1 1/s @ pH 6, 25 C" in note
        assert "2 of 3 frontier row(s) fall outside" in note

    def test_an_already_inside_resolver_choice_stands(self) -> None:
        rows = {"kcat": [row(21.1, 8.0, 25.0, unit="1/s")]}
        window = Constraint(
            kind="assay_window", subject="kcat", requirement="pH 8",
            reason="test", raised_by="test",
        )
        report, _ = self._scout_result(
            "kcat", windowed_resolver(rows), windows=(window,)
        )
        source = report.blackboard.get(param_key("kcat")).source
        assert source.value == 21.1
        note = next(
            n for r in report.rounds for ar in r.ran if ar.agent == "scout:kcat"
            for n in ar.notes
        )
        assert "already the nearest frontier row inside" in note

    def test_when_no_row_satisfies_the_window_the_default_stands(self) -> None:
        # Re-selecting an outside row would manufacture a measurement the
        # literature does not support; the resolver's answer is presented
        # and the note says the window matched nothing.
        rows = {"kcat": [row(21.1, 6.0, 25.0, unit="1/s")]}
        window = Constraint(
            kind="assay_window", subject="kcat", requirement="pH 10",
            reason="test", raised_by="test",
        )
        report, _ = self._scout_result(
            "kcat", windowed_resolver(rows), windows=(window,)
        )
        source = report.blackboard.get(param_key("kcat")).source
        assert source.value == 21.1
        note = next(
            n for r in report.rounds for ar in r.ran if ar.agent == "scout:kcat"
            for n in ar.notes
        )
        assert "no row the resolver returned satisfies" in note

    def test_a_value_without_a_frontier_is_not_re_selected(self) -> None:
        # A user-supplied or registry value legitimately carries no frontier
        # (the adapter attaches candidates only to literature results). It
        # must simply be left alone, not treated as immovable by default.
        def resolve(request, *, organism, allow_cross_species):
            return FakeKineticResult(
                found=True, value=0.15, unit="mM", organism="",
                source="brenda_exact",
                citation=type("C", (), {"source": "BRENDA", "reference_id": "test"})(),
                assay_ph=7.4, assay_temperature_c=37.0,
            )

        window = Constraint(
            kind="assay_window", subject="Km", requirement="pH 8",
            reason="test", raised_by="test",
        )
        report, _ = self._scout_result("Km", resolve, windows=(window,))
        source = report.blackboard.get(param_key("Km")).source
        assert source.value == 0.15
        assert all(
            not ar.notes
            for r in report.rounds for ar in r.ran if ar.agent == "scout:Km"
        )

    def test_it_chooses_the_row_that_states_the_reference_buffer(
        self,
    ) -> None:
        """Buffer beats numeric proximity, because buffer is not a distance.

        A numerically closer row in the wrong buffer (or in no stated
        buffer) is outside the window; the chosen row is the one the
        literature really measured in the reference's buffer.
        """
        rows = {
            "kcat": [
                row(21.1, 6.0, 25.0, unit="1/s", buffer=None),
                row(33.0, 8.0, 25.0, unit="1/s", buffer="Tris"),
                row(40.0, 8.0, 25.0, unit="1/s",
                    buffer="0.1 M MOPS buffer"),
            ],
        }
        window = Constraint(
            kind="assay_window",
            subject="kcat",
            requirement="pH 8; buffer 0.1 M MOPS buffer",
            reason="test",
            raised_by="test",
        )
        report, _ = self._scout_result(
            "kcat", windowed_resolver(rows), windows=(window,)
        )
        source = report.blackboard.get(param_key("kcat")).source
        assert source.value == 40.0
        assert source.buffer == "0.1 M MOPS buffer"
        assert source.ph == 8.0

        note = next(
            n for r in report.rounds for ar in r.ran
            if ar.agent == "scout:kcat" for n in ar.notes
        )
        assert "in 0.1 M MOPS buffer" in note
        assert "over the resolver's default 21.1 1/s @ pH 6, 25 C" in note
        assert "2 of 3 frontier row(s) fall outside" in note

    def test_re_selection_keeps_the_chosen_rows_own_provenance(self) -> None:
        # The re-selected row is a different measurement. Its buffer is the
        # one the frontier carries for THAT row (here the row states none,
        # so None is honest -- not the resolver-winner's buffer carried
        # forward); the citation must name the chosen row's reference_id;
        # and cross_species must flip ONLY when the chosen row actually
        # names a different organism.
        rows = {
            "kcat": [
                # The resolver winner: named organism, buffer stated, etc.
                row(21.1, 6.0, 25.0, unit="1/s", reference_id="W"),
                # A row at the reference's pH in a different organism.
                {
                    "value": 32.0, "unit": "1/s", "organism": "Escherichia coli",
                    "reference_id": "D", "conditions": "idem",
                    "ph": 8.0, "temperature_c": 25.0,
                    "grades": {"assay_completeness": "good",
                               "condition_proximity": "good",
                               "organism_match": "good"},
                },
            ],
        }
        window = Constraint(
            kind="assay_window", subject="kcat", requirement="pH 8",
            reason="test", raised_by="test",
        )
        report, _ = self._scout_result(
            "kcat", windowed_resolver(rows), windows=(window,)
        )
        source = report.blackboard.get(param_key("kcat")).source
        assert source.value == 32.0
        assert source.buffer is None          # this row states no buffer
        assert source.citation == "BRENDA ref D"
        assert source.organism == "Escherichia coli"
        assert source.cross_species is True   # a different organism was chosen
        assert source.ph == 8.0
        assert source.temperature_c == 25.0


class TestTheWholeLoop:
    def test_km_at_ph_8_pulls_kcat_to_its_pH_8_row(self) -> None:
        """The flagship behaviour, on the real-data shape.

        Round 1 resolves Km at pH 8 and kcat at pH 6 and the critic sees
        the gap; round 2 honours the window and the run converges with kcat
        re-selected to its pH-8 row. Both numbers were already in the
        tables; the only thing that moved was which row is presented.
        """
        rows = {
            "Km": [row(21.78, 8.0), row(10.73, 8.0)],
            "kcat": [
                row(94.7, 5.5, 30.0, unit="1/s"),
                row(21.1, 6.0, 25.0, unit="1/s"),
                row(32.0, 8.0, 25.0, unit="1/s"),
            ],
        }
        search = build_model(
            network=NETWORK,
            requests=[request("Km", "km"), request("kcat", "kcat")],
            resolve=windowed_resolver(rows),
        )

        assert search.run.converged
        assert search.run.round_count == 2

        assert search.resolutions["Km"].source.value == 10.73
        assert search.resolutions["Km"].source.ph == 8.0

        kcat = search.resolutions["kcat"].source
        assert kcat.value == 32.0
        assert kcat.ph == 8.0
        assert kcat.temperature_c == 25.0

        rejected = search.rejected_values()
        assert len(rejected) == 1
        assert "kcat" in rejected[0]
        assert "32" in rejected[0] and "21.1" in rejected[0]
        # Km, the immovable reference, must not be reported as having moved.
        assert all("Km" not in r for r in rejected)

        assert "assay_window [kcat] must be pH 8" in search.summary()

    def test_one_round_when_the_set_is_already_inside(self) -> None:
        # Both values at pH 8 already: no gap, no second round, no
        # constraint. The window machinery exists to fix a mismatch, not to
        # manufacture work when there isn't one.
        rows = {
            "Km": [row(10.73, 8.0)],
            "kcat": [row(32.0, 8.0, 25.0, unit="1/s")],
        }
        search = build_model(
            network=NETWORK,
            requests=[request("Km", "km"), request("kcat", "kcat")],
            resolve=windowed_resolver(rows),
        )
        assert search.run.converged
        assert search.run.round_count == 1
        assert search.run.constraints.all() == ()

    def test_same_numeric_conditions_still_resolve_a_buffer_gap(self) -> None:
        """The buffer flagship: identical pH/temperature, different buffers.

        Round 1 resolves Km (pH 7.4/37, HEPES) and kcat (pH 7.4/37, Tris) at
        identical numbers, so no pH or temperature gap exists -- only the
        buffer differs. Round 2 honours the window naming Km's buffer and
        kcat is re-selected to the row really measured in HEPES. The
        re-selected number was already in kcat's table; nothing was invented.
        """
        rows = {
            "Km": [
                row(10.73, 7.4, 37.0, buffer="HEPES"),
                row(21.78, 7.4, 37.0, buffer="HEPES"),
            ],
            "kcat": [
                row(21.1, 7.4, 37.0, unit="1/s", buffer="Tris"),
                row(35.0, 7.4, 37.0, unit="1/s", buffer="HEPES"),
                row(94.7, 7.4, 37.0, unit="1/s", buffer="HEPES"),
            ],
        }
        search = build_model(
            network=NETWORK,
            requests=[request("Km", "km"), request("kcat", "kcat")],
            resolve=windowed_resolver(rows),
        )

        assert search.run.converged
        assert search.run.round_count == 2

        kcat = search.resolutions["kcat"].source
        assert kcat.value == 35.0
        assert kcat.buffer == "HEPES"
        assert kcat.ph == 7.4

        rejected = search.rejected_values()
        assert len(rejected) == 1
        assert "kcat" in rejected[0]
        assert "35.0" in rejected[0] and "21.1" in rejected[0]

        assert "buffer HEPES" in search.summary()