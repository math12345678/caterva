"""pytest suite for core_fulltext.py.

Entirely offline via an injectable `fetch` function, matching every other
resolver's test pattern in this project (see test_fallback_logic.py's
html_provider, test_popgen_resolver.py's stdpopsim import guard). No real
network call is exercised here -- see the module docstring for why this
project's sandbox cannot live-verify the CORE API directly.
"""

from __future__ import annotations

import httpx
import pytest

import core_fulltext
from core_fulltext import (
    CoreFullTextCandidate,
    parse_core_search,
    resolve_open_access_fulltext,
)


# A response shaped like CORE v3's documented search-works schema.
FIXTURE_RESPONSE = {
    "totalHits": 2,
    "results": [
        {
            "id": 12345678,
            "title": "A real-shaped result with full metadata",
            "doi": "10.1000/example.doi",
            "downloadUrl": "https://core.ac.uk/download/12345678.pdf",
            "yearPublished": 2020,
        },
        {
            "id": 87654321,
            "title": "A result missing optional fields",
            # doi, downloadUrl, yearPublished all absent -- CORE does not
            # guarantee every field on every result.
        },
    ],
}


class TestParsing:
    def test_parses_a_full_record(self):
        candidates = parse_core_search(FIXTURE_RESPONSE)
        assert len(candidates) == 2
        first = candidates[0]
        assert first.core_id == "12345678"
        assert first.doi == "10.1000/example.doi"
        assert first.download_url == "https://core.ac.uk/download/12345678.pdf"
        assert first.year == 2020

    def test_missing_optional_fields_are_none_not_defaulted(self):
        candidates = parse_core_search(FIXTURE_RESPONSE)
        second = candidates[1]
        assert second.doi is None
        assert second.download_url is None
        assert second.year is None

    def test_a_result_with_no_id_or_title_is_skipped(self):
        malformed = {"results": [{"doi": "10.1/nothing"}, {"id": 1, "title": ""}]}
        assert parse_core_search(malformed) == []

    def test_empty_results_list(self):
        assert parse_core_search({"results": []}) == []

    def test_missing_results_key_entirely(self):
        assert parse_core_search({}) == []


class TestResolveWithoutApiKey:
    def test_missing_key_degrades_to_not_found(self, monkeypatch):
        monkeypatch.setattr(core_fulltext, "CORE_API_KEY", None)
        result = resolve_open_access_fulltext("anything")
        assert result.found is False
        assert any("CORE_API_KEY" in entry for entry in result.search_log)

    def test_missing_key_never_raises(self, monkeypatch):
        """A missing key is a configuration fact, not an error -- this
        must degrade exactly like every other resolver's missing-
        dependency case (stdpopsim not installed, etc.), never propagate
        an exception the caller has to catch specially."""
        monkeypatch.setattr(core_fulltext, "CORE_API_KEY", None)
        resolve_open_access_fulltext("anything")  # must not raise


class TestResolveWithInjectedFetch:
    def test_resolves_candidates_from_a_fixture_shaped_response(self, monkeypatch):
        monkeypatch.setattr(core_fulltext, "CORE_API_KEY", "fake-key-for-this-test")

        def fake_fetch(query: str, max_results: int) -> dict:
            return FIXTURE_RESPONSE

        result = resolve_open_access_fulltext("test query", fetch=fake_fetch)
        assert result.found is True
        assert len(result.candidates) == 2
        assert result.candidates[0].doi == "10.1000/example.doi"

    def test_empty_search_result_is_not_found(self, monkeypatch):
        monkeypatch.setattr(core_fulltext, "CORE_API_KEY", "fake-key-for-this-test")

        def empty_fetch(query: str, max_results: int) -> dict:
            return {"results": []}

        result = resolve_open_access_fulltext("nothing matches this", fetch=empty_fetch)
        assert result.found is False
        assert result.candidates == []

    def test_http_error_degrades_gracefully_not_an_exception(self, monkeypatch):
        """A network failure must never propagate past this function --
        exactly like the KEGG substrate lookup's httpx.HTTPError handling
        in science_agent_runner.py."""
        monkeypatch.setattr(core_fulltext, "CORE_API_KEY", "fake-key-for-this-test")

        def failing_fetch(query: str, max_results: int) -> dict:
            raise httpx.HTTPError("simulated network failure")

        result = resolve_open_access_fulltext("anything", fetch=failing_fetch)
        assert result.found is False
        assert any("CORE search failed" in entry for entry in result.search_log)

    def test_never_fabricates_a_result_when_nothing_is_found(self, monkeypatch):
        """Regression guard for the one failure mode that matters most:
        no candidates found must never silently become a fabricated
        found=True with an invented paper."""
        monkeypatch.setattr(core_fulltext, "CORE_API_KEY", "fake-key-for-this-test")

        def empty_fetch(query: str, max_results: int) -> dict:
            return {"results": []}

        result = resolve_open_access_fulltext(
            "a query with no real matches", fetch=empty_fetch
        )
        assert result.found is False
        assert result.candidates == []
