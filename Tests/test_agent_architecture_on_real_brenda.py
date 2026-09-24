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

  * `resolve_kinetic_value` called with an EMPTY organism used to match
    every row in the table, return the cross-species minimum, and report
    the organism as "". That is the commonest query a student types. The
    loss was not "between parse and result": the parser treated "" as a
    real organism filter (an empty string is a substring of every row) and
    then OVERWROTE each row's organism label with the requested "", so the
    resolver had no organism to report. ADR 0174 fixed it at the parser:
    "" now means "any organism" (exactly like `None`), every row keeps its
    real organism label, and the values below carry the organism of the row
    they came from. `organism_unattributed` therefore no longer appears on
    the real chain -- and the set-compiler's cross-species complaint does,
    because two animals really were measured.
"""

from __future__ import annotations

import re

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

    def test_unnamed_organism_values_carry_their_own_organism(self) -> None:
        """The empty-organism bug fixed (ADR 0174).

        An empty organism means "any organism", not "an organism whose name
        is ''". The resolver scans the whole table and returns the
        best-evidenced value WITH the organism of the row it came from, so
        the number is never detached from its subject. The two values here
        come from two different animals; the set-judge reports that as a
        blocking organism mismatch, and the silence-as-compatibility error
        (`organism_unattributed` on a set that "agreed" by having no
        organism at all) is gone because the resolver no longer produces it.
        """
        search = build()

        organisms = {
            r.source.organism for r in search.first_pass.resolutions.values()
        }
        assert organisms == {"Homo sapiens", "Cryptosporidium parvum"}

        # The values themselves do not move: this fix is about attribution,
        # not about picking a different number from a different row.
        resolutions = search.first_pass.resolutions
        assert resolutions["Km"].source.value == 10.73
        assert resolutions["Ki"].source.value == 0.0116
        assert resolutions["Km"].source.organism == HUMAN
        assert resolutions["Ki"].source.organism == "Cryptosporidium parvum"

        compatibility = search.first_pass.compatibility
        assert not any(
            f.kind == "organism_unattributed" for f in compatibility.findings
        )
        mismatch = next(
            f for f in compatibility.findings if f.kind == "organism_mismatch"
        )
        assert mismatch.severity == "blocking"
        assert set(mismatch.quantities) == {"Km", "Ki"}

        # The architecture responds as designed: one unconstrained pass plus
        # one run inside each organism the literature actually offered.
        assert len(search.branches) == 3

    def test_naming_the_organism_changes_which_value_is_returned(self) -> None:
        """The constraint reaches the resolver, and the answer moves.

        Unconstrained, the Ki is 0.0116 -- the best-evidenced row across
        every organism in the table, which is a Cryptosporidium parvum
        measurement. Inside Homo sapiens it is 0.0014, a different
        measurement from a different row. If the constraint were merely
        recorded and not applied, both runs would return the same number,
        which is precisely what a report claiming to have "searched under"
        a requirement would then be lying about.
        """
        unconstrained = build().first_pass.resolutions
        human = build(requested_organism=HUMAN).first_pass.resolutions

        assert unconstrained["Ki"].source.value == 0.0116
        assert unconstrained["Ki"].source.organism == "Cryptosporidium parvum"

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
            # Since v0.3.3 the citation names the paper ("BRENDA ref 740253"),
            # not the database's home page, which identified nothing.
            assert re.search(r"BRENDA ref \d+", resolution.source.citation), (
                quantity, resolution.source.citation)

    def test_a_real_ph_gap_is_fixed_by_re_selecting_a_real_row(self) -> None:
        """Not a constructed example, and not a corrected number.

        The lactate Km and the (all-substrate) kcat come from the same
        committed BRENDA pages, at pH 8.0 and pH 6.0. Km's table has no
        row at pH 6, so it cannot move and is the reference; kcat's table
        has a row at pH 8.0 (the 32.0 1/s measurement), so the critic can
        demand exactly that. The run re-selects it over the resolver's
        default minimum (21.1) and converges. 32.0 was already in the
        table; nothing was interpolated, averaged or corrected.
        """
        kcat_request = ParameterRequest(
            quantity="kcat", subject="L-lactate dehydrogenase",
            substrate="", ec_number=LDH, table="kcat",
        )
        search = search_model(
            network=NETWORK,
            requests=[REQUESTS[0], kcat_request],
            resolve=resolve,
        )
        first = search.first_pass

        assert first.run.converged
        assert first.run.round_count == 2
        window = first.run.constraints.of_kind("assay_window")
        assert len(window) == 1
        assert window[0].subject == "kcat"
        assert window[0].requirement == "pH 8"

        km = first.resolutions["Km"].source
        assert km.value == 10.73
        assert km.ph == 8.0
        # Km is the immovable reference and must not be reported as moved.
        kcat = first.resolutions["kcat"].source
        assert kcat.value == 32.0
        assert kcat.ph == 8.0
        assert kcat.temperature_c == 25.0

        # The value that was replaced is named, and is the resolver's
        # default minimum rather than a number nobody saw.
        rejected = first.rejected_values()
        assert len(rejected) == 1
        assert "kcat" in rejected[0]
        assert "21.1" in rejected[0] and "32" in rejected[0]

        compatibility = first.compatibility
        assert not any(f.kind == "ph_mismatch" for f in compatibility.findings)
        assert "assay_window [kcat] must be pH 8" in first.summary()
