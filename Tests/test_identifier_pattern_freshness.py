"""The freshness guard must be able to reach all three of its verdicts.

This sandbox can only ever produce one of them — the proxy blocks the
registry, so every live run says `unreachable`. A guard whose other two
branches have never executed is a guard nobody has checked, and "it looks
right" is the standard this project spent several passes rejecting.

So the fetch is stubbed and each verdict is driven deliberately, including
the one that matters most: a **narrowed** live pattern, which is the case
where Terrium would be minting URIs the registry no longer accepts.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
GUARD = REPO / "scripts" / "check_identifier_patterns_fresh.py"


def load_guard():
    spec = importlib.util.spec_from_file_location("check_identifier_patterns_fresh", GUARD)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def guard():
    return load_guard()


@pytest.fixture
def captured(guard):
    return json.loads(guard.FIXTURE.read_text(encoding="utf-8"))


def run(guard, monkeypatch, capsys, fetch):
    monkeypatch.setattr(guard, "fetch", fetch)
    monkeypatch.setattr(guard.sys, "argv", ["check_identifier_patterns_fresh.py"])
    code = guard.main()
    return code, capsys.readouterr().out


class TestAllThreeVerdicts:
    def test_matched_when_the_registry_agrees(self, guard, captured, monkeypatch, capsys):
        def agreeing(prefix):
            spec = captured["namespaces"][prefix]
            return {"pattern": spec["pattern"], "sampleId": spec["sampleId"]}

        code, out = run(guard, monkeypatch, capsys, agreeing)
        assert code == 0
        assert "every captured pattern still matches" in out
        # It must also say what it did NOT check. A pass that reads as
        # broader than it is, is how a guard becomes trusted for something
        # it never did.
        assert "compares patterns, not records" in out

    def test_drifted_when_the_registry_narrowed_a_pattern(
        self, guard, captured, monkeypatch, capsys
    ):
        """The dangerous direction: Terrium would mint accessions the
        registry no longer considers well-formed."""

        def narrowed(prefix):
            spec = captured["namespaces"][prefix]
            pattern = r"^\d{8}$" if prefix == "pubmed" else spec["pattern"]
            return {"pattern": pattern, "sampleId": spec["sampleId"]}

        code, out = run(guard, monkeypatch, capsys, narrowed)
        assert code == 2, "drift must not share an exit code with anything else"
        assert "DRIFTED" in out
        assert "pubmed" in out
        # Both directions have to be explained, or a reader seeing DRIFTED
        # cannot tell whether Terrium is now too strict or too loose.
        assert "WIDENED" in out and "NARROWED" in out

    def test_unreachable_is_not_reported_as_matched(
        self, guard, monkeypatch, capsys
    ):
        def blocked(prefix):
            raise ConnectionError("403 Forbidden")

        code, out = run(guard, monkeypatch, capsys, blocked)
        assert code == 1
        assert "UNREACHABLE" in out
        assert "'Could not check' is not 'checked and fine'" in out
        # And emphatically not a pass.
        assert "every captured pattern still matches" not in out

    def test_one_unreachable_namespace_does_not_become_a_pass(
        self, guard, captured, monkeypatch, capsys
    ):
        """A partial answer is not a whole one.

        The tempting implementation checks what it can and reports OK. Then
        a registry that fails for exactly one namespace — the one that
        changed — reads green forever.
        """

        def mostly_fine(prefix):
            if prefix == "brenda":
                raise ConnectionError("timeout")
            spec = captured["namespaces"][prefix]
            return {"pattern": spec["pattern"], "sampleId": spec["sampleId"]}

        code, out = run(guard, monkeypatch, capsys, mostly_fine)
        assert code == 1
        assert "unreachable  brenda" in out
        assert "every captured pattern still matches" not in out

    def test_drift_outranks_unreachable(self, guard, captured, monkeypatch, capsys):
        # If something definitely changed AND something could not be
        # reached, the change is the actionable fact and must not be
        # downgraded to "we could not look".
        def mixed(prefix):
            if prefix == "brenda":
                raise ConnectionError("timeout")
            spec = captured["namespaces"][prefix]
            pattern = r"^\d{8}$" if prefix == "pubmed" else spec["pattern"]
            return {"pattern": pattern, "sampleId": spec["sampleId"]}

        code, _ = run(guard, monkeypatch, capsys, mixed)
        assert code == 2


class TestTheGuardReadsTheSameFileTheCodeDoes:
    def test_it_points_at_the_fixture_miriam_actually_loads(self, guard):
        # A freshness guard aimed at a different copy of the patterns would
        # pass while the copy in use rotted. Compared as resolved paths, so
        # a relative-path refactor cannot silently split them.
        from Terium.core import miriam

        assert guard.FIXTURE.resolve() == miriam._FIXTURE.resolve()

    def test_every_namespace_the_code_uses_is_checked(self, guard, captured):
        from Terium.core import miriam

        assert set(captured["namespaces"]) >= set(miriam.NAMESPACES), (
            "a namespace the code mints in is not covered by the freshness check"
        )
