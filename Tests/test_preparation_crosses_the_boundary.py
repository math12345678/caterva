"""The preparation DECISION must survive the runner's emission.

WHY THIS FILE EXISTS
--------------------
`enzyme_preparation.differs_for(quantity)` answers both halves of the
judgement: was the enzyme altered, and did the curator say the alteration
left THIS quantity alone. Golden tuple G2's row is PEGylated and its
commentary says "does not alter the Km value", so resolving Km must NOT
warn while resolving Ki on the same row must.

`queryResolver.ts` originally re-derived that from `status` and
`stated_not_to_affect`. Two implementations of one rule — ADR 0027 — so the
runner now emits `warrantsWarning` and TypeScript reads it.

**Which moved the risk rather than removing it.** Mutation: make the runner
emit `"warrantsWarning": True` unconditionally. The Python suite stayed
green (it tests `differs_for`, not the emission) and the TypeScript suite
stayed green (it mocks the runner and supplies the field itself). Both sides
tested; the join untested — the exact shape
`poolFindingsReachTheUser.test.ts` was written about, where "each one tested
the computation; none tested the boundary".

So this file reads the EMITTED JSON.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# The runner lives under Science-Agent-Pipeline/, not Tests/. Same path
# derivation as test_science_agent_runner.py, for the same reason: the
# import must work regardless of pytest's working directory.
_RUNNER_DIR = (
    Path(__file__).resolve().parents[1]
    / "Science-Agent-Pipeline"
    / "artifacts"
    / "api-server"
    / "src"
    / "lib"
)
if str(_RUNNER_DIR) not in sys.path:
    sys.path.insert(0, str(_RUNNER_DIR))

import science_agent_runner  # noqa: E402
from enzyme_preparation import classify
from fallback_logic import KineticResult
from citation import Citation


def _pegylated(quantity: str) -> KineticResult:
    commentary = (
        "pH 8, 27°C, attachment of polyethylene glycol side chains to "
        "lysine residues does not alter the Km value"
    )
    return KineticResult(
        found=True,
        value=0.09,
        unit="mM",
        organism="Homo sapiens",
        source="brenda_exact",
        citation=Citation(source="BRENDA", reference_id="649716"),
        preparation=classify(commentary),
        search_log=[],
    )


@pytest.mark.parametrize(
    "quantity,expected",
    [
        # The curator's statement names KM, so resolving KM warrants no
        # warning and resolving KI does.
        ("km", False),
        ("ki", True),
        ("kcat", True),
    ],
)
def test_the_emitted_decision_matches_the_rule(
    capsys, monkeypatch, quantity, expected
) -> None:
    result = _pegylated(quantity)
    monkeypatch.setattr(
        science_agent_runner,
        "resolve_kinetic_value",
        lambda *args, **kwargs: result,
    )

    payload = {
        "ecNumber": "3.1.1.7",
        "enzymeName": "acetylcholinesterase",
        "substrate": "acetyl thiocholine",
        "organism": "Homo sapiens",
        "quantity": quantity,
    }
    monkeypatch.setattr(science_agent_runner.sys, "stdin", _Stdin(payload))
    science_agent_runner.main()
    out = json.loads(capsys.readouterr().out)

    assert out["found"] is True
    emitted = out["preparation"]
    assert emitted is not None, "the preparation never crossed the boundary"

    # The DECISION, not the inputs. Asserted against the rule itself so the
    # two cannot drift: if `differs_for` changes, this follows it.
    assert emitted["warrantsWarning"] is result.preparation.differs_for(quantity)
    assert emitted["warrantsWarning"] is expected

    # The inputs travel too, so a client may render differently — but they
    # are not what it should decide from.
    assert emitted["status"] == "modified"
    assert emitted["stated_not_to_affect"] == "KM"


class _Stdin:
    def __init__(self, payload: dict) -> None:
        self._text = json.dumps(payload)

    def read(self) -> str:
        return self._text
