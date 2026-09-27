"""The whole run, on the case that motivates the architecture.

THE SCENARIO
------------
A student asks for competitive inhibition of an enzyme and names no
organism -- which is what students actually type. BRENDA answers each
constant from whichever row ranks best, and those rows are not from the same
animal. Every value is real and cited. The model is nonsense.

The old chain resolves the two constants, notices nothing, and simulates.
The chain plus a compatibility check resolves them, reports the mismatch,
and stops. This run resolves them, rejects the mismatch, RE-SEARCHES inside
one organism, and reports what that turned up -- including, in the second
test, that the missing measurement does not exist at all.

The resolver here is a fixture that reproduces BRENDA's shape: an
unconstrained query returns the best-evidenced row from any organism, and a
constrained one returns only that organism's rows.
"""

from __future__ import annotations

import pytest

from caterva.agents.assembly import build_model, search_model
from caterva.agents.critics import CoherenceCritic
from caterva.agents.scouts import ParameterScout, param_key
from caterva.continuous.networks import mm_competitive_network
from Tests.parameterize import ParameterRequest

HUMAN = "Homo sapiens"
RABBIT = "Oryctolagus cuniculus"


class FakeKineticResult:
    """The fields of `KineticResult` the adapter reads."""

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
        self.cross_species_organisms_available = kw.get("available", [])


def brenda_like(rows):
    """A resolver over `rows`: {quantity: [(organism, value, ph, temp, buf)]}.

    Unconstrained, it returns the first row for the quantity -- BRENDA's
    evidence rank, which has no reason to prefer one organism. Constrained,
    it returns only rows from that organism, and nothing if there are none.
    """
    calls = []

    def resolve(request, *, organism, allow_cross_species):
        calls.append((request.quantity, organism))
        candidates = rows.get(request.quantity, [])
        if organism:
            candidates = [r for r in candidates if r[0] == organism]
        if not candidates:
            return FakeKineticResult(
                found=False,
                source="cross_species_withheld" if rows.get(request.quantity) else "not_found",
                available=[r[0] for r in rows.get(request.quantity, [])],
            )
        org, value, ph, temp, buf = candidates[0]
        return FakeKineticResult(
            found=True, value=value, unit="mM", organism=org, source="brenda_exact",
            # The REAL `Citation` (Tests/citation.py) declares `source` and
            # `reference_id`. This fixture used to invent a field called
            # `reference`, and `citation_text` used to look for exactly that
            # invented name -- so the stub and the bug agreed with each other
            # and the suite passed while every real BRENDA citation was being
            # degraded to a bare enzyme-page URL (ADR 0178). A fixture whose
            # shape no production object has is a test of nothing.
            citation=type("C", (), {
                "source": "BRENDA", "reference_id": request.quantity,
            })(),
            assay_ph=ph, assay_temperature_c=temp, assay_buffer=buf,
        )

    resolve.calls = calls
    return resolve


def requests_for(*quantities):
    return [
        ParameterRequest(quantity=q, subject="hexokinase", ec_number="2.7.1.1",
                         substrate="D-glucose", table=q.lower())
        for q in quantities
    ]


NETWORK = mm_competitive_network(km=0.1, vmax=1.0, ki=0.5, s0=1.0, i=0.2)


class TestTheLoopThatDidNotExist:
    def test_a_mismatch_is_explored_organism_by_organism(self) -> None:
        """The flagship behaviour.

        The first pass draws a human Km and a rabbit Ki -- one value each,
        so no majority exists and no tiebreak would be honest. Instead the
        model is built inside each organism in turn. Only one completes.
        """
        resolve = brenda_like({
            "Km": [(HUMAN, 0.15, 7.4, 37.0, "HEPES")],
            "Ki": [(RABBIT, 0.9, 7.4, 37.0, "HEPES"), (HUMAN, 0.4, 7.4, 37.0, "HEPES")],
        })
        search = search_model(
            network=NETWORK, requests=requests_for("Km", "Ki"), resolve=resolve,
        )

        assert search.chosen is not None
        assert search.chosen.organism == HUMAN
        organisms = {r.source.organism for r in search.build.resolutions.values()}
        assert organisms == {HUMAN}, organisms
        assert search.build.usable

        summary = search.summary()
        assert "built the model separately inside each" in summary
        assert f"[{HUMAN}: complete]" in summary
        assert f"[{RABBIT}: no measured Km]" in summary

    def test_when_no_organism_completes_it_says_what_each_one_lacks(self) -> None:
        """The answer a per-parameter resolver cannot give.

        A human Km and a rabbit Ki, and neither animal has both. "No model
        found" would be true and useless. Naming the missing measurement per
        organism tells a researcher exactly what to go and measure, and in
        which species.
        """
        resolve = brenda_like({
            "Km": [(HUMAN, 0.15, 7.4, 37.0, "HEPES")],
            "Ki": [(RABBIT, 0.9, 7.4, 37.0, "HEPES")],
        })
        search = search_model(
            network=NETWORK, requests=requests_for("Km", "Ki"), resolve=resolve,
        )

        assert search.chosen is None
        by_organism = {
            b.organism: b.build.missing for b in search.branches if b.organism
        }
        assert by_organism == {HUMAN: ("Ki",), RABBIT: ("Km",)}

        summary = search.summary()
        assert f"[{HUMAN}: no measured Ki]" in summary
        assert f"[{RABBIT}: no measured Km]" in summary
        assert "has not assembled one" in summary
        # And it must NOT report the mixed-organism first pass as a model.
        assert search.build is None
        assert "Resolved 2 of 2" not in summary

    def test_a_gap_names_the_requirement_that_closed_the_search(self) -> None:
        """Otherwise the report is false in a way that costs bench time.

        Inside the human branch there is no Ki -- but one exists, in a
        rabbit. A bare "no Ki found" would send a researcher looking for a
        measurement that is already in BRENDA under another animal. The
        reason must say the search was narrowed and by what.
        """
        resolve = brenda_like({
            "Km": [(HUMAN, 0.15, 7.4, 37.0, "HEPES")],
            "Ki": [(RABBIT, 0.9, 7.4, 37.0, "HEPES")],
        })
        search = search_model(
            network=NETWORK, requests=requests_for("Km", "Ki"), resolve=resolve,
        )
        human = next(b for b in search.branches if b.organism == HUMAN)
        reason = human.build.resolutions["Ki"].reason
        assert "searched under the requirement" in reason
        assert HUMAN in reason
        # And the underlying resolver outcome is still there, so the reader
        # learns the value exists elsewhere rather than only that it was
        # excluded.
        assert "cross-species" in reason or "other organisms" in reason

    def test_two_complete_organisms_are_both_reported_and_neither_chosen(
        self,
    ) -> None:
        """Several whole models is a finding, not a failure.

        Both animals have both constants. Picking one would throw away the
        fact that the literature supports two -- and would do it invisibly.
        """
        resolve = brenda_like({
            "Km": [(HUMAN, 0.15, 7.4, 37.0, "HEPES"), (RABBIT, 0.3, 7.4, 37.0, "HEPES")],
            "Ki": [(RABBIT, 0.9, 7.4, 37.0, "HEPES"), (HUMAN, 0.4, 7.4, 37.0, "HEPES")],
        })
        search = search_model(
            network=NETWORK, requests=requests_for("Km", "Ki"), resolve=resolve,
        )
        assert search.chosen is None
        assert set(search.undecided) == {HUMAN, RABBIT}
        assert "has not chosen" in search.summary()

    def test_naming_the_organism_settles_it_without_any_branching(self) -> None:
        """The same literature as the previous test, one request different.

        With an organism named, the coherence critic has a principled
        requirement to emit and the fixpoint alone resolves it. No
        per-organism exploration runs at all -- the expensive path exists
        for the case where the user gave nothing to go on, and must not be
        taken when they did.
        """
        resolve = brenda_like({
            "Km": [(HUMAN, 0.15, 7.4, 37.0, "HEPES"), (RABBIT, 0.3, 7.4, 37.0, "HEPES")],
            "Ki": [(RABBIT, 0.9, 7.4, 37.0, "HEPES"), (HUMAN, 0.4, 7.4, 37.0, "HEPES")],
        })
        search = search_model(
            network=NETWORK, requests=requests_for("Km", "Ki"), resolve=resolve,
            requested_organism=RABBIT,
        )
        assert len(search.branches) == 1, "no exploration was needed"
        assert search.undecided == ()
        assert {r.source.organism for r in search.build.resolutions.values()} == {RABBIT}
        assert search.build.usable
        assert f"organism must be {RABBIT}" in search.build.summary()

    def test_an_already_coherent_set_costs_one_round_and_no_branching(self) -> None:
        # Nothing to discover, so no second pass and no per-organism runs.
        # A version that always branched would multiply every literature
        # query by the number of organisms in the database.
        resolve = brenda_like({
            "Km": [(HUMAN, 0.15, 7.4, 37.0, "HEPES")],
            "Ki": [(HUMAN, 0.4, 7.4, 37.0, "HEPES")],
        })
        search = search_model(
            network=NETWORK, requests=requests_for("Km", "Ki"), resolve=resolve,
        )
        assert search.build.run.round_count == 1
        assert len(search.branches) == 1
        assert search.build.usable
        assert len(resolve.calls) == 2


class TestRefusal:
    def test_it_will_not_simulate_a_model_with_a_hole_in_it(self) -> None:
        resolve = brenda_like({"Km": [(HUMAN, 0.15, 7.4, 37.0, "HEPES")]})
        build = build_model(
            network=NETWORK, requests=requests_for("Km", "Ki"), resolve=resolve,
        )
        assert build.simulation["ran"] is False
        assert "does not substitute a default" in build.simulation["refused_because"]

    def test_it_will_not_simulate_an_unresolved_organism_mismatch(self) -> None:
        # Forced by seeding both values as found in different organisms and
        # denying any re-search: the executor must refuse rather than
        # integrate constants that describe no animal.
        resolve = brenda_like({
            "Km": [(HUMAN, 0.15, 7.4, 37.0, "HEPES")],
            "Ki": [(RABBIT, 0.9, 7.4, 37.0, "HEPES")],
        })
        build = build_model(
            network=NETWORK, requests=requests_for("Km", "Ki"), resolve=resolve,
        )
        assert build.simulation["ran"] is False
        assert "do not describe one system" in build.simulation["refused_because"]

    def test_it_simulates_the_resolved_values_not_the_placeholders(self) -> None:
        """The bug this test was written to catch.

        A network is constructed with stand-in constants so its structure
        can be checked before any literature is searched -- `NETWORK` holds
        km=0.1 and ki=0.5. Simulating that object after resolution would
        plot the stand-ins beneath a report full of citations: every number
        on the axis unmeasured, every number in the provenance real.
        """
        resolve = brenda_like({
            "Km": [(HUMAN, 0.15, 7.4, 37.0, "HEPES")],
            "Ki": [(HUMAN, 0.4, 7.4, 37.0, "HEPES")],
        })
        simulated = []
        build = build_model(
            network=NETWORK, requests=requests_for("Km", "Ki"), resolve=resolve,
            simulate=lambda net: simulated.append(net) or "trajectory",
        )
        assert build.simulation["ran"] is True
        assert build.simulation["result"] == "trajectory"

        values = {p.id: p.value for p in simulated[0].parameters}
        assert values["Km"] == 0.15, "placeholder Km reached the simulator"
        assert values["Ki"] == 0.4, "placeholder Ki reached the simulator"
        # And the untouched constants are left exactly as constructed.
        assert values["Vmax"] == 1.0
        # The original object is unchanged: substitution returns a new
        # network rather than mutating the caller's.
        assert {p.id: p.value for p in NETWORK.parameters}["Km"] == 0.1

    def test_it_refuses_to_convert_between_units(self) -> None:
        # A model built in mM and a value published in uM. The conversion
        # is not always dimensionless, so Caterva states the mismatch
        # instead of multiplying by a factor it did not look up.
        from Tests.parameterize import ParameterRequest

        resolve = brenda_like({
            "Km": [(HUMAN, 150.0, 7.4, 37.0, "HEPES")],
            "Ki": [(HUMAN, 0.4, 7.4, 37.0, "HEPES")],
        })
        requests = [
            ParameterRequest(quantity="Km", subject="hexokinase",
                             ec_number="2.7.1.1", substrate="D-glucose",
                             table="km", expected_unit="uM"),
            ParameterRequest(quantity="Ki", subject="hexokinase",
                             ec_number="2.7.1.1", substrate="D-glucose",
                             table="ki"),
        ]
        build = build_model(
            network=NETWORK, requests=requests, resolve=resolve,
            simulate=lambda net: "trajectory",
        )
        assert build.simulation["ran"] is False
        assert "does not convert" in build.simulation["refused_because"]


class TestParallelism:
    def test_every_scout_occupies_one_level(self) -> None:
        # Eight constants means eight concurrent searches, which is the
        # practical reason this beats the sequential chain.
        from caterva.agents.assembly import build_agents
        from caterva.agents.scheduler import Scheduler

        resolve = brenda_like({})
        agents = build_agents(
            requests=requests_for("Km", "Ki", "kcat"), resolve=resolve,
        )
        levels = Scheduler(agents).levels
        scouts = {a.name for a in levels[0] if a.name.startswith("scout:")}
        assert scouts == {"scout:Km", "scout:Ki", "scout:kcat"}
        assert "critic:coherence" in {a.name for a in levels[1]}
        assert "executor" in {a.name for a in levels[2]}


class TestAFailedScoutIsNotAGap:
    """The bug this class was written for, found by re-reading the executor.

    A scout that raises -- a timed-out BRENDA request -- never writes its
    blackboard key. The executor's missing-check skipped absent keys, so
    that quantity was not counted as missing, was not passed to
    `with_resolved_values`, and kept the placeholder value the network was
    constructed with. The model then simulated.

    That is the partial-substitution fabrication arriving through an outage
    rather than through a gap, past the guard built to stop it.
    """

    def test_a_crashed_scout_stops_the_model_rather_than_leaving_a_placeholder(
        self,
    ) -> None:
        def resolve(request, *, organism, allow_cross_species):
            if request.quantity == "Ki":
                raise TimeoutError("BRENDA read timed out")
            return brenda_like({
                "Km": [(HUMAN, 0.15, 7.4, 37.0, "HEPES")]
            })(request, organism=organism, allow_cross_species=allow_cross_species)

        simulated = []
        build = build_model(
            network=NETWORK, requests=requests_for("Km", "Ki"), resolve=resolve,
            simulate=lambda net: simulated.append(net) or "trajectory",
        )

        assert simulated == [], "a model with a placeholder Ki reached the simulator"
        assert build.simulation["ran"] is False
        assert build.simulation["never_reported"] == ("Ki",)

    def test_an_outage_and_a_gap_are_worded_differently(self) -> None:
        # "BRENDA has no human Ki" and "we could not reach BRENDA" lead to
        # different actions. Reporting the second as the first tells a
        # researcher a measurement does not exist because a server was down.
        def crashing(request, *, organism, allow_cross_species):
            if request.quantity == "Ki":
                raise TimeoutError("BRENDA read timed out")
            return brenda_like({"Km": [(HUMAN, 0.15, 7.4, 37.0, "HEPES")]})(
                request, organism=organism, allow_cross_species=allow_cross_species
            )

        outage = build_model(
            network=NETWORK, requests=requests_for("Km", "Ki"), resolve=crashing,
        ).simulation
        gap = build_model(
            network=NETWORK, requests=requests_for("Km", "Ki"),
            resolve=brenda_like({"Km": [(HUMAN, 0.15, 7.4, 37.0, "HEPES")]}),
        ).simulation

        assert "outage, not a literature gap" in outage["refused_because"]
        assert "no measured value for Ki" in gap["refused_because"]
        assert outage["refused_because"] != gap["refused_because"]
        assert outage["never_reported"] == ("Ki",) and outage["unresolved"] == ()
        assert gap["unresolved"] == ("Ki",) and gap["never_reported"] == ()

    def test_the_failure_itself_is_still_reported(self) -> None:
        # And the underlying exception is not swallowed by the refusal.
        def crashing(request, *, organism, allow_cross_species):
            raise TimeoutError("BRENDA read timed out")

        build = build_model(
            network=NETWORK, requests=requests_for("Km"), resolve=crashing,
        )
        assert "BRENDA read timed out" in build.run.summary()
        assert [f.agent for f in build.run.failures] == ["scout:Km"]
