"""KEGG is not called unless an operator opts in.

WHY THIS FILE EXISTS
--------------------
KEGG's terms (https://www.kegg.jp/kegg/legal.html, 1 October 2024) state
that KEGG "is not a public database, nor is it a publicly funded database",
that non-academic use "requires a commercial license", and that even
academic users "who utilize KEGG for providing services are requested to
obtain an academic service provider license".

Terrium provides a service, and this repository contains an incorporation
checklist, a cap table and a fundraising tracker. Either reading points at a
licence from Pathway Solutions. Nobody has obtained one.

`resolve_substrate_from_kegg()` was nonetheless calling `rest.kegg.jp`
live, server-side, on every resolution where the caller supplied no
substrate. ADR 0068 and NOTICE both record this as UNRESOLVED; neither
stopped the call being made.

The project's own precedent decides it. SABIO-RK was evaluated and
DECLINED for non-commercial-only terms; stdpopsim was moved out of the
default install over a licence interaction (ADR 0061). KEGG's terms are
comparable to SABIO-RK's, and KEGG was integrated anyway — not after
weighing them, but before anyone read them.

So the lookup is off unless `TERRIUM_ENABLE_KEGG` is set, and setting it is
the operator stating that their own licence position permits it.

This does NOT assert that using KEGG would be unlawful. It asserts that
Terrium does not currently know that it is lawful, and a tool whose central
claim is traceability should not make an unexamined request on a user's
behalf.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "Tests"))
sys.path.insert(0, str(REPO / "Science-Agent-Pipeline/artifacts/api-server/src/lib"))

import enzyme_lookup  # noqa: E402


@pytest.fixture(autouse=True)
def _no_ambient_opt_in(monkeypatch):
    """Each test states its own opt-in. Inheriting the developer's shell
    would make these pass or fail for reasons outside the file."""
    monkeypatch.delenv(enzyme_lookup.KEGG_OPT_IN_ENV, raising=False)


def test_kegg_is_off_by_default():
    assert enzyme_lookup.kegg_enabled() is False


def test_fetching_without_opting_in_refuses_rather_than_calling(monkeypatch):
    # The assertion that matters: no HTTP request is attempted. If the gate
    # were removed, `retry_get` would fire and this would fail on the call
    # count rather than on the exception type — so it is checked directly.
    calls: list[str] = []
    monkeypatch.setattr(
        enzyme_lookup, "retry_get", lambda url, **kw: calls.append(url)
    )

    with pytest.raises(enzyme_lookup.KeggLicenceNotConfigured):
        enzyme_lookup.fetch_kegg_enzyme_text("1.1.1.27")

    assert calls == [], "KEGG was contacted despite the opt-in being unset"


def test_the_refusal_says_what_to_do_about_it():
    # A refusal a reader cannot act on is the same defect this project
    # fixes everywhere else. The message must name the switch and the terms.
    with pytest.raises(enzyme_lookup.KeggLicenceNotConfigured) as excinfo:
        enzyme_lookup.fetch_kegg_enzyme_text("1.1.1.27")

    message = str(excinfo.value)
    assert enzyme_lookup.KEGG_OPT_IN_ENV in message
    assert "kegg.jp/kegg/legal" in message
    assert "licence" in message.lower()


def test_opting_in_lets_the_call_through(monkeypatch):
    # The other half. A gate that is always closed would satisfy every
    # assertion above while deleting the feature.
    monkeypatch.setenv(enzyme_lookup.KEGG_OPT_IN_ENV, "1")

    class _Resp:
        text = "ENTRY       EC 1.1.1.27\n"

        def raise_for_status(self):
            return None

    seen: list[str] = []

    def _fake_get(url, **kw):
        seen.append(url)
        return _Resp()

    monkeypatch.setattr(enzyme_lookup, "retry_get", _fake_get)

    text = enzyme_lookup.fetch_kegg_enzyme_text("1.1.1.27")
    assert "EC 1.1.1.27" in text
    assert seen and "rest.kegg.jp" in seen[0]


def test_the_resolver_degrades_and_does_not_crash():
    """The behaviour `resolve_substrate_from_kegg`'s docstring promises.

    It catches `httpx.HTTPError` only — deliberately, because
    `test_programming_error_is_not_swallowed` exists to stop that clause
    being widened. A new exception type from the gate would therefore
    propagate and crash the whole resolution, which that docstring says must
    never happen. It is caught by name instead.
    """
    from science_agent_runner import resolve_substrate_from_kegg

    assert resolve_substrate_from_kegg("1.1.1.27") is None


@pytest.mark.parametrize(
    "value,expected",
    [("1", True), ("true", True), ("TRUE", True), ("yes", True),
     ("0", False), ("false", False), ("", False), ("  ", False)],
)
def test_opt_in_parsing(monkeypatch, value, expected):
    # `TERRIUM_ENABLE_KEGG=0` must mean off. An env var that is truthy
    # merely by being present is how a switch gets flipped by a stray
    # export in a CI file.
    monkeypatch.setenv(enzyme_lookup.KEGG_OPT_IN_ENV, value)
    assert enzyme_lookup.kegg_enabled() is expected
