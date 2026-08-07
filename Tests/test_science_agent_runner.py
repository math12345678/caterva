"""Regression tests for science_agent_runner.py.

These verify that network-lookup failures in the KEGG substrate resolver
degrade gracefully (return None) rather than crashing the whole resolution,
and that genuine programming errors are NOT swallowed by the same handler.
The mutation_rate (population-genetics) path is covered end-to-end so a
wrong dict-field access like the ``popgen_result['doi']`` KeyError -- caught
by the runner's broad except and degraded to a cryptic ``{'ok': false}``
error -- cannot silently land again (ADR 0008: literature provenance must
surface or fail loudly, never silently).
"""

import io
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# The runner lives under Science-Agent-Pipeline/, not Tests/. Derive the
# path from this file's location so the import works regardless of the
# working directory pytest happens to be invoked from.
_RUNNER_DIR = (
    Path(__file__).resolve().parents[1]
    / "Science-Agent-Pipeline"
    / "artifacts"
    / "api-server"
    / "src"
    / "lib"
)
sys.path.insert(0, str(_RUNNER_DIR))

import science_agent_runner  # noqa: E402
from science_agent_runner import resolve_substrate_from_kegg  # noqa: E402


class TestResolveSubstrateFromKegg:
    """Edge cases for the KEGG substrate lookup."""

    def test_http_error_returns_none(self):
        """An HTTP error (e.g. 404 for an unknown EC number) must degrade to
        None, not crash the resolution."""
        with patch("science_agent_runner.enzyme_lookup.fetch_kegg_enzyme_text") as mock_fetch:
            mock_fetch.side_effect = __import__("httpx").HTTPStatusError(
                "404 Not Found",
                request=None,
                response=__import__("httpx").Response(404, request=None),
            )
            result = resolve_substrate_from_kegg("1.1.1.1")
        assert result is None

    def test_timeout_returns_none(self):
        """A network timeout must degrade to None."""
        with patch("science_agent_runner.enzyme_lookup.fetch_kegg_enzyme_text") as mock_fetch:
            mock_fetch.side_effect = __import__("httpx").TimeoutException("timeout")
            result = resolve_substrate_from_kegg("1.1.1.1")
        assert result is None

    def test_programming_error_is_not_swallowed(self):
        """A genuine programming error (e.g. AttributeError from a typo)
        must surface, not be silently caught by the broad except."""
        with patch("science_agent_runner.enzyme_lookup.fetch_kegg_enzyme_text") as mock_fetch:
            mock_fetch.side_effect = AttributeError("typo in internal code")
            with pytest.raises(AttributeError, match="typo"):
                resolve_substrate_from_kegg("1.1.1.1")


class TestPopgenMutationRateResolution:
    """The mutation_rate path of the runner's main() end-to-end.

    Regression: main() read ``popgen_result['doi']`` from a dict that had no
    ``doi`` key. On the first successful stdpopsim hit the KeyError was caught
    by the broad except and returned as ``{"ok": false, "error": "'doi'"}`` --
    every Wright-Fisher literature mutation_rate call failed with a cryptic
    error instead of a value. These tests drive main() with a mocked resolver
    so they stay offline and pin the success and not-found shapes.
    """

    @staticmethod
    def _run_with_capsys(capsys, payload: dict) -> dict:
        old_stdin = sys.stdin
        sys.stdin = io.StringIO(json.dumps(payload))
        try:
            science_agent_runner.main()
        finally:
            sys.stdin = old_stdin
        return json.loads(capsys.readouterr().out)

    def test_success_path_returns_value_and_doi_locator(self, capsys, monkeypatch):
        """A found mutation rate must come back with the value and a citation
        carrying a resolvable DOI -- not crash on a missing dict field."""
        from popgen_resolver import PopgenResult

        fake = PopgenResult(
            found=True,
            value=1.29e-8,
            organism="Homo sapiens",
            source="stdpopsim",
            citation="International Human Genome Sequencing Consortium (2001)",
            doi="10.1038/35057062",
        )
        monkeypatch.setattr(
            science_agent_runner.popgen_resolver,
            "resolve_mutation_rate",
            lambda organism: fake,
        )

        out = self._run_with_capsys(
            capsys, {"parameterType": "mutation_rate", "organism": "Homo sapiens"}
        )

        assert out["ok"] is True
        assert out["found"] is True
        assert out["km"] == pytest.approx(1.29e-8)
        assert out["citation"]["referenceId"] == "10.1038/35057062"
        assert out["citation"]["url"] == "https://doi.org/10.1038/35057062"

    def test_not_found_path_returns_honest_found_false(self, capsys, monkeypatch):
        """An organism stdpopsim has nothing for degrades to found:false --
        never a fabricated value, never a crash."""
        from popgen_resolver import PopgenResult

        monkeypatch.setattr(
            science_agent_runner.popgen_resolver,
            "resolve_mutation_rate",
            lambda organism: PopgenResult(found=False, search_log=["not in catalog"]),
        )

        out = self._run_with_capsys(
            capsys, {"parameterType": "mutation_rate", "organism": "Unknownus"}
        )

        assert out["ok"] is True
        assert out["found"] is False
        assert out["source"] == "popgen_not_found"
