"""A failed organism lookup must not become a confident answer about a human.

`enzyme_lookup.DEFAULT_TAXON_ID = "9606"` was the default argument of three
network functions and the right-hand side of

    taxon_id = fetch_taxon_id(organism) or DEFAULT_TAXON_ID

`fetch_taxon_id` returns None when NCBI is unreachable, rate-limited, or does
not recognise the name. So the substitution fired on a **network failure**,
not on a missing argument: ask about *Thermus aquaticus* while NCBI is down,
and the next line fetched the human UniProt accession and stamped it onto the
thermophile's measurement as that row's protein identity.

That is the three-outcome rule broken at the point it matters most — "could
not look" collapsed into a confident wrong answer — inside the codebase whose
headline behaviour is refusing to substitute one organism's value for
another's. Caterva would refuse a cross-species *Km* while silently attaching
a cross-species *accession* to it.

These tests are offline. They stub the taxonomy lookup to fail, which is
exactly the condition that used to trigger the substitution.
"""

from __future__ import annotations

import inspect

import pytest

import brenda_client
import brenda_structured
import enzyme_lookup


class _Response:
    """Just enough of an httpx response for the parser to read."""

    text = "<html><body></body></html>"


def _empty_page(*args, **kwargs):
    return _Response()


class TestTheDefaultIsGoneAndCannotReturn:
    def test_there_is_no_default_taxon_constant(self):
        assert not hasattr(enzyme_lookup, "DEFAULT_TAXON_ID"), (
            "A default organism is the same defect as a default pH: it "
            "answers a question about a species the caller never named."
        )

    @pytest.mark.parametrize(
        "function",
        [
            enzyme_lookup.fetch_uniprot_accession,
            enzyme_lookup.fetch_ec_number_by_name,
            enzyme_lookup.resolve_enzyme,
        ],
    )
    def test_taxon_id_is_required_not_defaulted(self, function):
        parameter = inspect.signature(function).parameters["taxon_id"]
        assert parameter.default is inspect.Parameter.empty, (
            f"{function.__name__} defaults its taxon; an omitted argument "
            "would silently pick an organism."
        )

    def test_the_orchestrators_do_not_default_the_taxon_to_a_species(self):
        # These may default to None -- meaning "derive it from the organism"
        # -- but never to a concrete taxon, which would be a second source
        # of truth able to disagree with target_organism.
        for name in (
            "fetch_and_parse_brenda_km",
            "fetch_and_parse_brenda_kcat",
            "fetch_and_parse_brenda_ki",
        ):
            default = inspect.signature(getattr(brenda_client, name)).parameters[
                "taxon_id"
            ].default
            assert default is None, f"{name} defaults taxon_id to {default!r}"


class TestAFailedLookupYieldsNoAccession:
    def test_brenda_structured_does_not_fall_back_to_human(self, monkeypatch):
        """The exact line that used to read `... or DEFAULT_TAXON_ID`."""
        asked: list[str] = []

        def taxon_unavailable(organism, *args, **kwargs):
            return None  # NCBI down, or the name is unknown

        def record_accession_request(ec_number, taxon_id, *args, **kwargs):
            asked.append(taxon_id)
            return "P00338"  # the human LDH accession

        monkeypatch.setattr(enzyme_lookup, "fetch_taxon_id", taxon_unavailable)
        monkeypatch.setattr(
            enzyme_lookup, "fetch_uniprot_accession", record_accession_request
        )
        monkeypatch.setattr(brenda_structured, "retry_get", _empty_page)

        brenda_structured.parse_brenda_km(
            "1.1.1.27", "Thermus aquaticus", ["pyruvate"]
        )

        assert asked == [], (
            "UniProt was queried despite an unresolved taxon; whatever id it "
            f"was given ({asked}) was not one anybody looked up."
        )

    def test_a_resolved_taxon_is_still_used(self, monkeypatch):
        # The refusal must not be achieved by breaking the feature. This is
        # the same path with the lookup working.
        asked: list[str] = []
        monkeypatch.setattr(
            enzyme_lookup, "fetch_taxon_id", lambda organism, *a, **k: "274"
        )
        monkeypatch.setattr(
            enzyme_lookup,
            "fetch_uniprot_accession",
            lambda ec, taxon, *a, **k: asked.append(taxon) or "Q9X0J1",
        )
        monkeypatch.setattr(brenda_structured, "retry_get", _empty_page)

        brenda_structured.parse_brenda_km(
            "1.1.1.27", "Thermus thermophilus", ["pyruvate"]
        )
        assert asked == ["274"]

    def test_the_orchestrator_derives_the_taxon_from_the_organism(self, monkeypatch):
        # Not from a default, and not from a second parameter that could
        # disagree with the organism actually requested.
        seen: dict[str, object] = {}

        monkeypatch.setattr(
            enzyme_lookup,
            "fetch_taxon_id",
            lambda organism, *a, **k: seen.setdefault("organism", organism) and None or "274",
        )
        monkeypatch.setattr(
            enzyme_lookup,
            "fetch_uniprot_accession",
            lambda ec, taxon, *a, **k: seen.setdefault("taxon", taxon),
        )
        monkeypatch.setattr(
            enzyme_lookup, "fetch_kegg_enzyme_text", lambda *a, **k: ""
        )
        monkeypatch.setattr(enzyme_lookup, "parse_kegg_substrates", lambda *a, **k: [])
        monkeypatch.setattr(
            brenda_client, "fetch_brenda_html", lambda *a, **k: "<html></html>"
        )

        brenda_client.fetch_and_parse_brenda_km(
            "1.1.1.27", target_organism="Thermus thermophilus"
        )

        assert seen.get("organism") == "Thermus thermophilus"
        assert seen.get("taxon") == "274"


class TestTheCorrectImplementationStillAgrees:
    def test_fallback_logic_refuses_on_an_unresolved_taxon(self):
        """`fallback_logic` always had this right.

        Pinned here so the two implementations of one step cannot drift
        apart again — last time they did, the one with a default was the
        one that was wrong, and it was the older one.
        """
        from fallback_logic import _resolve_fallback_uniprot

        called: list[object] = []
        result = _resolve_fallback_uniprot(
            "1.1.1.27",
            "Thermus aquaticus",
            uniprot_provider=lambda ec, taxon: called.append(taxon) or "P00338",
            taxon_id_provider=lambda organism: None,
        )
        assert result is None
        assert called == []


class TestTheRunnerEmitsNoDefaultTaxon:
    """The same defect, one layer up, and it survived a mutation test.

    Removing the runner's taxon fields was caught immediately (the contract
    test pins the output shape). Adding `or "9606"` inside `taxon_id_for`
    was **not** — because the contract test lets the real
    `fetch_taxon_id` run, which raises in a sandboxed environment, so the
    `or` branch was never reached and the mutant behaved identically.

    A mutation surviving means the tests do not cover the thing, not that
    the mutation is harmless. These stub the lookup to return None — a name
    NCBI does not recognise, which is the case the `or` branch exists to
    swallow.
    """

    @staticmethod
    def _runner():
        # The runner lives beside the API server, not on Tests/'s path.
        # Imported the same way test_runner_contract.py does it, rather
        # than by copying the module here -- a second copy would pass its
        # own tests while the shipped one drifted.
        import os
        import sys

        lib_dir = os.path.join(
            os.path.dirname(__file__), "..", "Science-Agent-Pipeline",
            "artifacts", "api-server", "src", "lib",
        )
        if lib_dir not in sys.path:
            sys.path.insert(0, lib_dir)
        import science_agent_runner

        return science_agent_runner

    def test_an_unrecognised_organism_yields_no_taxon(self, monkeypatch):
        runner = self._runner()
        monkeypatch.setattr(
            enzyme_lookup, "fetch_taxon_id", lambda organism, *a, **k: None
        )
        assert runner.taxon_id_for("Nonexistus fakeus") is None, (
            "an unresolved name became a taxon id; the only way that happens "
            "is a default, and a default here names a species nobody asked "
            "about"
        )

    def test_a_failed_lookup_yields_no_taxon(self, monkeypatch):
        runner = self._runner()

        def unreachable(organism, *args, **kwargs):
            raise ConnectionError("403 Forbidden")

        monkeypatch.setattr(enzyme_lookup, "fetch_taxon_id", unreachable)
        assert runner.taxon_id_for("Homo sapiens") is None

    def test_a_resolved_organism_still_yields_its_taxon(self, monkeypatch):
        # The refusal must not be achieved by breaking the feature.
        runner = self._runner()
        monkeypatch.setattr(
            enzyme_lookup, "fetch_taxon_id", lambda organism, *a, **k: "274"
        )
        assert runner.taxon_id_for("Thermus thermophilus") == "274"

    def test_no_organism_means_no_lookup_at_all(self, monkeypatch):
        runner = self._runner()
        called: list[str] = []
        monkeypatch.setattr(
            enzyme_lookup,
            "fetch_taxon_id",
            lambda organism, *a, **k: called.append(organism) or "9606",
        )
        assert runner.taxon_id_for("") is None
        assert runner.taxon_id_for(None) is None
        assert called == [], "an empty organism was sent to NCBI as a query"
