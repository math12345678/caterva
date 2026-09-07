"""The agent architecture driving the real resolver on real BRENDA markup.

Everything else that exercises `Terium/agents` injects a stand-in resolver,
which proves the architecture and proves nothing about the literature layer
underneath it. This drives `fallback_logic.resolve_kinetic_value` -- the
actual resolution chain, with its evidence ranking, variant partitioning and
assay-condition parsing -- over committed BRENDA HTML for lactate
dehydrogenase (EC 1.1.1.27).

Offline, because the HTML is a fixture. Real, because nothing between the
markup and the report is a fake.

WHAT IT FOUND
-------------
Two things, neither of which was a hypothesis first:

  * BRENDA's LDH Km and Ki are published **2.5 pH units apart** (8.0 and
    5.5). Both are real values with real references, and multiplying them
    into one model is the defect this whole subsystem exists to catch.

  * `resolve_kinetic_value` called with an EMPTY organism matches every row
    in the table, returns the minimum across all species, and reports the
    organism as "". Two such values agree about the organism trivially,
    which passed as compatibility until `organism_unattributed` was added.
    That is the commonest query a student types.
"""

from __future__ import annotations

import pathlib
import sys

import pytest

_HERE = pathlib.Path(__file__).resolve().parent
_ROOT = _HERE.parent
for _p in (str(_ROOT), str(_HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from fallback_logic import resolve_kinetic_value  # noqa: E402
from parameterize import ParameterRequest  # noqa: E402

from Terium.agents.assembly import search_model  # noqa: E402
from Terium.continuous.networks import mm_competitive_network  # noqa: E402

FIXTURES = _HERE / "fixtures"
LDH = "1.1.1.27"
HUMAN = "Homo sapiens"

#: One fixture per BRENDA table, exactly as the site serves them.
FIXTURE_FOR_TABLE = {
    "km": "brenda_ldh_fixture.html",
    "ki": "brenda_ldh_ki_fixture.html",
    "kcat": "brenda_ldh_kcat_fixture.html",
}

TAXON_IDS = {HUMAN: "9606", "Oryctolagus cuniculus": "9986", "Sus scrofa": "9823"}


def _html_provider(table: str):
    def provider(ec_number: str) -> str:
        return (FIXTURES / FIXTURE_FOR_TABLE[table]).read_text(encoding="utf-8")

    return provider


def resolve(request, *, organism, allow_cross_species):
    """The scout calling convention, over the real resolution chain."""
    return resolve_kinetic_value(
        request.ec_number,
        organism or "",
        request.substrate,
        enzyme_name=request.subject,
        quantity=request.table,
        html_provider=_html_provider(request.table),
        uniprot_provider=lambda ec, org: None,
        taxon_id_provider=TAXON_IDS.get,
        # PubMed is a network call and adds candidate papers, never values.
        search_literature=False,
        allow_cross_species=allow_cross_species,
    )


REQUESTS = [
    ParameterRequest(quantity="Km", subject="L-lactate dehydrogenase",
                     substrate="lactate", ec_number=LDH, table="km"),
    ParameterRequest(quantity="Ki", subject="L-lactate dehydrogenase",
                     substrate="gossypol", ec_number=LDH, table="ki"),
]

NETWORK = mm_competitive_network(km=0.1, vmax=1.0, ki=0.5, s0=1.0, i=0.2)


def build(**kwargs):
    return search_model(
        network=NETWORK, requests=REQUESTS, resolve=resolve, **kwargs
    )


class TestOnRealMarkup:
    def test_it_catches_a_real_ph_gap_between_two_real_brenda_values(self) -> None:
        """Not a constructed example.

        Both numbers come out of the committed BRENDA page. A pipeline that
        resolved each and stopped would hand a student a competitive-
        inhibition model whose Km was measured at pH 8.0 and whose Ki was
        measured at pH 5.5, with a correct citation beside each.
        """
        search = build()
        compatibility = search.first_pass.compatibility
        finding = next(
            f for f in compatibility.findings if f.kind == "ph_mismatch"
        )
        assert finding.severity == "serious"
        assert "2.5 pH units apart" in finding.detail
        assert "pH 8" in finding.detail and "pH 5.5" in finding.detail

    def test_an_unnamed_organism_yields_values_attributed_to_nothing(self) -> None:
        """The defect this test was written after discovering.

        With no organism, the resolver matches every row and returns the
        minimum across all species. The values are real; what they are a
        measurement OF is not recorded. Two of them must not read as
        agreeing about the organism.
        """
        search = build()
        organisms = {
            r.source.organism for r in search.first_pass.resolutions.values()
        }
        assert organisms == {""}, "the fixture behaviour this test pins changed"

        compatibility = search.first_pass.compatibility
        finding = next(
            f for f in compatibility.findings if f.kind == "organism_unattributed"
        )
        assert finding.severity == "unassessable"
        assert set(finding.quantities) == {"Km", "Ki"}
        assert "no organism is recorded" in compatibility.summary()

    def test_naming_the_organism_changes_which_value_is_returned(self) -> None:
        """The constraint reaches the resolver, and the answer moves.

        Unconstrained, the Ki is 0.0116 -- the minimum over every organism
        in the table. Inside Homo sapiens it is 0.0014, a different
        measurement from a different row. If the constraint were merely
        recorded and not applied, both runs would return the same number,
        which is precisely what a report claiming to have "searched under"
        a requirement would then be lying about.
        """
        unconstrained = build().first_pass.resolutions
        human = build(requested_organism=HUMAN).first_pass.resolutions

        assert unconstrained["Ki"].source.value == 0.0116
        assert unconstrained["Ki"].source.organism == ""

        assert human["Ki"].source.value == 0.0014
        assert human["Ki"].source.organism == HUMAN
        assert human["Km"].source.organism == HUMAN

    def test_a_named_organism_costs_one_round(self) -> None:
        # Seeded as a requirement rather than rediscovered by the critic,
        # so the literature is not queried twice for an answer the user
        # already gave.
        search = build(requested_organism=HUMAN)
        assert search.first_pass.run.round_count == 1
        assert search.first_pass.run.converged
        assert len(search.branches) == 1

    def test_every_resolved_value_carries_a_citation(self) -> None:
        # The rule the whole codebase exists for, checked at the end of the
        # real chain rather than at the top of a stand-in.
        search = build(requested_organism=HUMAN)
        for quantity, resolution in search.first_pass.resolutions.items():
            assert resolution.source is not None, quantity
            assert resolution.source.citation, f"{quantity} has no citation"
            assert "brenda-enzymes.org" in resolution.source.citation
