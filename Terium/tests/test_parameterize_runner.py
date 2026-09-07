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
