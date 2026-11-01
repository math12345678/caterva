"""A doi.org citation URL is asked of CrossRef -- checked without a network.

WHY THIS EXISTS
---------------
`verify_citations_live.py` checks every static URL in queryResolver.ts.
Publishers bot-gate the doi.org redirect, so asking doi.org answers 403 and
says nothing about the citation: every doi.org URL there came back
UNREACHABLE on every run until the URL section learned to rewrite
`https://doi.org/<doi>` to `https://api.crossref.org/works/<doi>` (the
`DOI_URL` match in `main`). That rewrite runs only under `--live`, so no
offline run ever executed it; a broken pattern or a dropped rewrite would
put the section back to "unreachable" and stay green everywhere.

This drives the script's own `main()` with `bounded_get` replaced by a
recorder, so the assertions are about the URLs the real code asks for, not
about a copy of its regex.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys

import pytest

_SCRIPT = (
    pathlib.Path(__file__).resolve().parents[1]
    / "scripts"
    / "verify_citations_live.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("verify_citations_live", _SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["verify_citations_live"] = module
    spec.loader.exec_module(module)
    return module


verify = _load()


class _Response:
    """What every check reads off a response: a 200 with an empty body."""

    status_code = 200
    text = ""

    def json(self) -> dict:
        return {"message": {"title": []}, "result": {}}


@pytest.fixture
def asked(monkeypatch, tmp_path):
    """Run main() offline; return the URLs it asked for, in order."""
    resolver = tmp_path / "queryResolver.ts"
    resolver.write_text(
        "const a = 'https://doi.org/10.1021/bi201284u';\n"
        "const b = 'http://dx.DOI.org/10.1038/NG.3285';\n"
        "const c = 'https://www.brenda-enzymes.org/';\n",
        encoding="utf-8",
    )
    urls: list[str] = []

    def fake_get(url, **_kwargs):
        urls.append(url)
        return _Response()

    monkeypatch.setattr(verify, "QUERY_RESOLVER", resolver)
    monkeypatch.setattr(verify, "bounded_get", fake_get)
    # No .env read: the run needs no key, and none is ever printed.
    monkeypatch.setattr(verify, "load_env_keys", lambda *_a, **_k: {})
    monkeypatch.setattr(verify, "discovered_dois", lambda: {})
    monkeypatch.setattr(verify, "claimed_titles", lambda: {})
    verify.main()
    return urls


def test_a_doi_org_url_is_asked_of_crossref(asked):
    assert "https://api.crossref.org/works/10.1021/bi201284u" in asked
    assert "https://doi.org/10.1021/bi201284u" not in asked


def test_dx_doi_org_and_http_are_rewritten_too(asked):
    # DOI_URL accepts dx.doi.org, plain http, and any case in the host. The
    # DOI itself is passed through as written; CrossRef matches it
    # case-insensitively.
    assert "https://api.crossref.org/works/10.1038/NG.3285" in asked
    assert not [u for u in asked if "doi.org/" in u.lower() and "crossref" not in u]


def test_a_url_that_is_not_a_doi_is_asked_as_it_is(asked):
    assert "https://www.brenda-enzymes.org/" in asked
    assert not [u for u in asked if "crossref.org/works/https" in u]


def test_the_pattern_takes_the_doi_and_nothing_else():
    m = verify.DOI_URL.match("https://doi.org/10.1016/0022-2836(76)90041-4")
    assert m and m.group(1) == "10.1016/0022-2836(76)90041-4"
    assert verify.DOI_URL.match("https://example.org/doi.org/10.1/x") is None
    assert verify.DOI_URL.match("https://doi.org/not-a-doi") is None
