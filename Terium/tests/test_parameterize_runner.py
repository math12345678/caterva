"""The `parameterize` domain as the API actually calls it.

Exercises `run_parameterize` end to end -- network spec in, JSON out --
with a resolver standing in for BRENDA. The point is the contract: an API
consumer must be able to see the branches that did NOT work out, because
"no Ki has been measured in human, though one exists in rabbit" is the
result, and a payload carrying only the surviving branch would discard it.
"""

from __future__ import annotations

import pathlib
import sys

import pytest

_LIB = (
    pathlib.Path(__file__).resolve().parents[2]
    / "Science-Agent-Pipeline" / "artifacts" / "api-server" / "src" / "lib"
)
sys.path.insert(0, str(_LIB))

import terium_runner  # noqa: E402

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "tests"))
from test_agent_model_build import HUMAN, RABBIT, brenda_like  # noqa: E402

NETWORK_SPEC = {
    "name": "mm_competitive_inhibition",
    "species": [{"id": "S", "initial": 1.0}, {"id": "P", "initial": 0.0}],
    "parameters": [
        {"id": "Vmax", "value": 1.0},
        {"id": "Km", "value": 0.1},
        {"id": "Ki", "value": 0.5},
        {"id": "I", "value": 0.2},
    ],
    "reactions": [
        {
            "id": "v",
            "reactants": {"S": 1},
            "products": {"P": 1},
            "rate_law": "Vmax * S / (Km * (1 + I / Ki) + S)",
        }
    ],
}

REQUESTS = [
    {"quantity": "Km", "subject": "hexokinase", "substrate": "D-glucose",
     "ec_number": "2.7.1.1", "table": "km"},
    {"quantity": "Ki", "subject": "hexokinase", "substrate": "D-glucose",
     "ec_number": "2.7.1.1", "table": "ki"},
]


def run(rows, **params):
    return terium_runner.run_parameterize(
        {"network": NETWORK_SPEC, "requests": REQUESTS, **params},
        resolve=brenda_like(rows),
    )


class TestTheContract:
    def test_it_returns_the_branches_that_did_not_work_out(self) -> None:
        payload = run({
            "Km": [(HUMAN, 0.15, 7.4, 37.0, "HEPES")],
            "Ki": [(RABBIT, 0.9, 7.4, 37.0, "HEPES"), (HUMAN, 0.4, 7.4, 37.0, "HEPES")],
        })
        by_organism = {
            b["organism"]: b for b in payload["branches"] if b["organism"]
        }
        assert by_organism[HUMAN]["complete"] is True
        assert by_organism[RABBIT]["complete"] is False
        assert "Km" in by_organism[RABBIT]["build"]["missing"]
        assert payload["chosen_organism"] == HUMAN
        assert payload["model"]["resolved"]["Km"]["organism"] == HUMAN

    def test_a_resolved_value_carries_its_conditions_and_citation(self) -> None:
        payload = run({
            "Km": [(HUMAN, 0.15, 7.4, 37.0, "HEPES")],
            "Ki": [(HUMAN, 0.4, 7.4, 37.0, "HEPES")],
        })
        km = payload["model"]["resolved"]["Km"]
        assert km == {
            "value": 0.15, "unit": "mM", "organism": HUMAN, "ph": 7.4,
            "temperature_c": 37.0, "buffer": "HEPES",
            "citation": "reference:BRENDA Km", "cross_species": False,
            "explicitly_unreported": [],
        }

    def test_a_named_organism_constrains_the_first_pass_not_the_second(
        self,
    ) -> None:
        """The audit trail, and the query it saves.

        A named organism is a requirement from the outset. Before it was
        seeded, the scouts searched unconstrained, the critic noticed the
        mismatch, and a second round repeated every literature query to
        reach an answer the user had already given -- doubling the BRENDA
        traffic for a question nobody asked.
        """
        payload = run(
            {
                "Km": [(HUMAN, 0.15, 7.4, 37.0, "HEPES"), (RABBIT, 0.3, 7.4, 37.0, "HEPES")],
                "Ki": [(RABBIT, 0.9, 7.4, 37.0, "HEPES"), (HUMAN, 0.4, 7.4, 37.0, "HEPES")],
            },
            organism=HUMAN,
        )
        constraints = payload["model"]["constraints"]
        assert [
            (c["kind"], c["requirement"], c["raised_by"]) for c in constraints
        ] == [("organism", HUMAN, "<input>")], constraints
        assert payload["model"]["rounds"] == 1
        assert payload["model"]["resolved"]["Ki"]["organism"] == HUMAN

    def test_a_discovered_constraint_names_the_critic_that_raised_it(self) -> None:
        # The other half: when the user named nothing, the requirement is
        # the critic's own finding and must be attributed to it.
        payload = run({
            "Km": [(HUMAN, 0.15, 7.4, 37.0, "HEPES"), (HUMAN, 0.2, 7.4, 37.0, "HEPES")],
            "Ki": [(RABBIT, 0.9, 7.4, 37.0, "HEPES"), (HUMAN, 0.4, 7.4, 37.0, "HEPES")],
        })
        human_branch = next(
            b for b in payload["branches"] if b["organism"] == HUMAN
        )
        raisers = {c["raised_by"] for c in human_branch["build"]["constraints"]}
        assert "search_model" in raisers

    def test_no_model_means_model_is_null_not_a_mixed_organism_one(self) -> None:
        payload = run({
            "Km": [(HUMAN, 0.15, 7.4, 37.0, "HEPES")],
            "Ki": [(RABBIT, 0.9, 7.4, 37.0, "HEPES")],
        })
        assert payload["model"] is None
        assert payload["chosen_organism"] is None
        assert "has not assembled one" in payload["summary"]


class TestTheRefusals:
    def test_asking_for_a_quantity_the_network_does_not_have_is_refused(self) -> None:
        with pytest.raises(ValueError, match="does not contain"):
            terium_runner.run_parameterize(
                {
                    "network": NETWORK_SPEC,
                    "requests": [{"quantity": "kcat", "table": "kcat"}],
                },
                resolve=brenda_like({}),
            )

    def test_an_empty_request_list_is_refused(self) -> None:
        # Otherwise it returns a model with every placeholder intact and a
        # clean bill of health, which is the worst output this system could
        # produce.
        with pytest.raises(ValueError, match="at least one request"):
            terium_runner.run_parameterize(
                {"network": NETWORK_SPEC, "requests": []},
                resolve=brenda_like({}),
            )


class TestRegistration:
    def test_the_domain_is_registered_where_the_dispatcher_looks(self) -> None:
        assert "parameterize" in terium_runner.COMPOSED_DOMAINS
        assert "parameterize" in terium_runner._RUNNERS
        # And NOT in DISPATCH: that table maps a domain to a single engine
        # `simulate_*` function and is asserted exhaustive against the
        # engine's __all__. This domain composes several.
        assert "parameterize" not in terium_runner.DISPATCH


class TestTheWholeLoop:
    """Description in, cited running model out -- or a reason, by name.

    This is the end of the chain the architecture exists to make possible:
    the constants are resolved from the literature concurrently, checked
    against each other, narrowed to one organism, substituted into the
    network, compiled with provenance and integrated. Nothing on the axis
    is a number nobody measured.
    """

    #: The quantities no paper supplies: a scenario choice and the
    #: caller's own enzyme preparation. Declared by the caller, recorded
    #: as theirs.
    CALLER_SOURCES = {
        "Vmax": {"origin": "user", "note": "measured in this assay"},
        "I": {"origin": "user", "note": "inhibitor concentration used"},
        "S": {"origin": "user", "note": "starting substrate"},
        "P": {"origin": "user", "note": "no product at t=0"},
    }

    def test_a_coherent_set_is_compiled_and_integrated(self) -> None:
        payload = terium_runner.run_parameterize(
            {
                "network": NETWORK_SPEC,
                "requests": REQUESTS,
                "sources": self.CALLER_SOURCES,
                "organism": HUMAN,
                "end": 5.0,
                "points": 11,
            },
            resolve=brenda_like({
                "Km": [(HUMAN, 0.15, 7.4, 37.0, "HEPES")],
                "Ki": [(HUMAN, 0.4, 7.4, 37.0, "HEPES")],
            }),
        )
        simulation = payload["simulation"]
        assert simulation["ran"] is True, simulation.get("because")
        assert len(simulation["trajectory"]) == 11

        # The trajectory was computed from the RESOLVED constants, not the
        # placeholders the network was constructed with.
        assert simulation["values"]["Km"] == 0.15
        assert simulation["values"]["Ki"] == 0.4

        # And every quantity carries where it came from -- the literature
        # ones cited, the caller's recorded as theirs.
        origins = {
            q: s["origin"] for q, s in simulation["quantitySources"].items()
        }
        assert origins["Km"] == "resolved" and origins["Ki"] == "resolved"
        assert origins["Vmax"] == "user"
        assert simulation["quantitySources"]["Km"]["citation"]

    def test_a_quantity_nobody_sourced_stops_the_run_and_is_named(self) -> None:
        # Vmax omitted from the caller's map. The literature was not asked
        # for it and the caller did not supply it, so it is refused BY NAME
        # rather than defaulted to whatever the network was built with.
        sources = dict(self.CALLER_SOURCES)
        del sources["Vmax"]
        payload = terium_runner.run_parameterize(
            {
                "network": NETWORK_SPEC, "requests": REQUESTS,
                "sources": sources, "organism": HUMAN,
            },
            resolve=brenda_like({
                "Km": [(HUMAN, 0.15, 7.4, 37.0, "HEPES")],
                "Ki": [(HUMAN, 0.4, 7.4, 37.0, "HEPES")],
            }),
        )
        simulation = payload["simulation"]
        assert simulation["ran"] is False
        assert simulation["unsourced"] == ["Vmax"]
        assert "recorded as yours" in simulation["because"]

    def test_a_caller_value_is_not_overwritten_by_the_literature(self) -> None:
        # Someone modelling their own enzyme preparation keeps their own
        # number. Their assay is the one they are modelling.
        sources = dict(self.CALLER_SOURCES)
        sources["Km"] = {"origin": "user", "note": "my own Km"}
        payload = terium_runner.run_parameterize(
            {
                "network": NETWORK_SPEC, "requests": REQUESTS,
                "sources": sources, "organism": HUMAN,
            },
            resolve=brenda_like({
                "Km": [(HUMAN, 0.15, 7.4, 37.0, "HEPES")],
                "Ki": [(HUMAN, 0.4, 7.4, 37.0, "HEPES")],
            }),
        )
        assert payload["simulation"]["quantitySources"]["Km"]["origin"] == "user"

    def test_each_refusal_keeps_its_own_sentence(self) -> None:
        """Three different reasons a model does not run, never collapsed.

        "The literature has no human Ki", "these values are from two
        animals" and "you did not tell us Vmax" lead to three different
        next actions, and one "could not simulate" would make all of them
        unactionable.
        """
        # (a) nothing found for Ki anywhere.
        no_ki = terium_runner.run_parameterize(
            {"network": NETWORK_SPEC, "requests": REQUESTS,
             "sources": self.CALLER_SOURCES},
            resolve=brenda_like({"Km": [(HUMAN, 0.15, 7.4, 37.0, "HEPES")]}),
        )["simulation"]
        assert no_ki["ran"] is False
        assert "no measured value for Ki" in no_ki["because"]

        # (b) two organisms, neither complete.
        split = terium_runner.run_parameterize(
            {"network": NETWORK_SPEC, "requests": REQUESTS,
             "sources": self.CALLER_SOURCES},
            resolve=brenda_like({
                "Km": [(HUMAN, 0.15, 7.4, 37.0, "HEPES")],
                "Ki": [(RABBIT, 0.9, 7.4, 37.0, "HEPES")],
            }),
        )["simulation"]
        assert split["ran"] is False
        assert "no organism has every constant" in split["because"]

        # (c) two organisms, BOTH complete: a choice Terrium will not make.
        both = terium_runner.run_parameterize(
            {"network": NETWORK_SPEC, "requests": REQUESTS,
             "sources": self.CALLER_SOURCES},
            resolve=brenda_like({
                "Km": [(HUMAN, 0.15, 7.4, 37.0, "HEPES"), (RABBIT, 0.3, 7.4, 37.0, "HEPES")],
                "Ki": [(RABBIT, 0.9, 7.4, 37.0, "HEPES"), (HUMAN, 0.4, 7.4, 37.0, "HEPES")],
            }),
        )["simulation"]
        assert both["ran"] is False
        assert "nothing in the request separates them" in both["because"]

        assert len({no_ki["because"], split["because"], both["because"]}) == 3


class TestTheBlockingRefusalFires:
    """A defensive check has to be shown firing, or it is decoration.

    `_simulate_search` refuses a set with a blocking finding. Reached
    through `search_model` that branch is dead code today: the only blocking
    kind is `organism_mismatch`, which needs two organisms, which triggers
    per-organism exploration, which only ever chooses a complete branch. A
    mutation deleting the check therefore survived the whole suite.

    It is kept rather than deleted because it guards the invariant, not the
    current vocabulary -- the day a second blocking kind exists (a unit
    mismatch, a variant mismatch) it becomes live with no warning. So it is
    exercised directly, on a build that genuinely carries one.
    """

    def test_a_blocking_finding_stops_the_simulation_by_name(self) -> None:
        from Terium.agents.assembly import build_model
        from Tests.parameterize import ParameterRequest

        requests = [
            ParameterRequest(quantity=q, subject="hexokinase",
                             ec_number="2.7.1.1", substrate="D-glucose",
                             table=q.lower())
            for q in ("Km", "Ki")
        ]
        # `build_model` runs one fixpoint and does NOT branch, so a
        # two-organism set survives to the executor with both values found.
        build = build_model(
            network=terium_runner._network_from_spec(NETWORK_SPEC),
            requests=requests,
            resolve=brenda_like({
                "Km": [(HUMAN, 0.15, 7.4, 37.0, "HEPES")],
                "Ki": [(RABBIT, 0.9, 7.4, 37.0, "HEPES")],
            }),
        )
        assert not build.missing, "the earlier guard would fire instead"
        assert build.compatibility.blocking, "no blocking finding to test"

        search = type("OneBranch", (), {
            "build": build, "undecided": (),
        })()
        simulation = terium_runner._simulate_search(search, {}, {})

        assert simulation["ran"] is False
        assert "do not describe one system" in simulation["because"]
        assert "different organisms" in simulation["because"]
