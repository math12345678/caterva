"""Regression tests for science_agent_runner.py.

These verify that network-lookup failures in the KEGG substrate resolver
degrade gracefully (return None) rather than crashing the whole resolution,
and that genuine programming errors are NOT swallowed by the same handler.
"""

import sys
from unittest.mock import patch

import pytest

# The runner lives under Science-Agent-Pipeline/, not Tests/. Add it to the
# path so these tests can import it directly.
sys.path.insert(0, "Science-Agent-Pipeline/artifacts/api-server/src/lib")

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
