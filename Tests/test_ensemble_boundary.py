"""The ensemble crosses the runner boundary — exercised, not mocked.

WHY THIS FILE IS SEPARATE FROM test_model_ensemble.py
------------------------------------------------------
`test_model_ensemble.py` drives the function with a fake simulator. That
pins the envelope arithmetic and proves nothing about whether the capability
reaches anybody, which is a distinction this repository has paid for
repeatedly:

    "a test that pins a component tells you nothing about the wiring"
    -- ADR 0027

The ensemble is emitted from `caterva_runner.py` deliberately, because that is
the single place both the CLI and the API read from — a capability added to
one front end reaches half the users, which `docs/one-sided-findings.txt`
exists to track. So the thing worth testing is the runner invocation itself:
spawn, stdin, dispatch, engine, JSON out.

These spawn a real subprocess against the real engine. They are slower than
a mock and they are the only tests here that could have caught a broken
`--ensemble` flag, an import that fails only under the server's PYTHONPATH,
or a payload shape the runner rejects.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
RUNNER = (
    REPO_ROOT
    / "Science-Agent-Pipeline"
    / "artifacts"
    / "api-server"
    / "src"
    / "lib"
    / "caterva_runner.py"
)


def run_ensemble(payload: dict) -> dict:
    """Spawn the runner exactly as the API server does."""
    env = {**os.environ, "PYTHONPATH": str(REPO_ROOT)}
    proc = subprocess.run(
        [sys.executable, str(RUNNER), "--ensemble"],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
        timeout=180,
    )
    assert proc.stdout.strip(), f"runner produced no stdout; stderr={proc.stderr[-800:]}"
    return json.loads(proc.stdout.strip().splitlines()[-1])


BASE = {
    "domain": "mm",
    "parameters": {"vmax": 5.0, "s0": 10.0, "end": 10.0, "points": 6},
}


def with_draws(draws: list, **spec) -> dict:
    return {**BASE, "ensemble": {"parameter": "km", "draws": draws, "seed": 1, **spec}}


class TestItCrossesTheBoundary:
    def test_a_band_comes_back_from_the_real_engine(self) -> None:
        out = run_ensemble(with_draws([0.03, 0.398] * 20))
        assert out["ok"] is True, out.get("error")
        ensemble = out["ensemble"]
        assert ensemble["swept"] == ["km"]
        assert ensemble["succeeded"] == 40

    def test_the_band_is_wider_than_a_point_where_the_parameter_matters(self) -> None:
        """The whole claim. Two published Km values, thirteen-fold apart, give
        a visibly different substrate curve — which is the thing a student
        cannot see when `min()` picks one and reports it alone.
        """
        out = run_ensemble(with_draws([0.03, 0.398] * 20))
        substrate = next(
            e for e in out["ensemble"]["envelopes"] if e["column"] == "[S]"
        )
        spread = [h - lo for lo, h in zip(substrate["low"], substrate["high"])]
        assert max(spread) > 0.5, "the two Km values produced no visible difference"

    def test_every_output_column_gets_an_envelope(self) -> None:
        out = run_ensemble(with_draws([0.03, 0.398] * 5))
        columns = {e["column"] for e in out["ensemble"]["envelopes"]}
        assert columns == {"[S]", "[P]"}

    def test_the_disclaimer_survives_the_boundary(self) -> None:
        """ADR 0024's objection applies to the trajectories exactly as it
        applies to the parameters, and a sentence that is dropped in transit
        is a sentence nobody reads.
        """
        out = run_ensemble(with_draws([0.03, 0.398]))
        assert "NOT an uncertainty estimate" in out["ensemble"]["disclaimer"]

    def test_the_support_note_survives_the_boundary(self) -> None:
        out = run_ensemble(with_draws([0.03, 0.398]))
        assert "runs" in out["ensemble"]["supportNote"]


class TestItRefusesRatherThanGuessing:
    def test_an_unknown_domain_is_refused(self) -> None:
        out = run_ensemble({**with_draws([1.0]), "domain": "not_a_domain"})
        assert out["ok"] is False
        assert "unknown domain" in out["error"]

    def test_a_missing_draws_list_is_refused(self) -> None:
        out = run_ensemble({**BASE, "ensemble": {"parameter": "km", "seed": 1}})
        assert out["ok"] is False
        assert "draws" in out["error"]

    def test_an_empty_draws_list_is_refused(self) -> None:
        """An ensemble over nothing is not an empty band, it is a resolution
        failure the caller should report.
        """
        out = run_ensemble(with_draws([]))
        assert out["ok"] is False

    def test_a_missing_parameter_name_is_refused(self) -> None:
        out = run_ensemble({**BASE, "ensemble": {"draws": [1.0], "seed": 1}})
        assert out["ok"] is False

    def test_a_failure_is_reported_as_json_not_a_traceback(self) -> None:
        """The API server parses stdout. A traceback on stderr with an empty
        stdout is indistinguishable from a hang at the other end.
        """
        out = run_ensemble({"domain": "mm", "ensemble": {"parameter": "km", "draws": []}})
        assert out["ok"] is False
        assert isinstance(out["error"], str) and out["error"]


class TestTheCapIsRealAndVisible:
    def test_max_runs_bounds_the_work_and_is_reported(self) -> None:
        """Integrating an ODE two thousand times is not free. The cap keeps a
        student from waiting on runs that stopped changing the band, and
        `attempted` makes the truncation visible rather than silent.
        """
        out = run_ensemble(with_draws([0.03, 0.398] * 100, maxRuns=10))
        assert out["ensemble"]["attempted"] == 10
        assert out["ensemble"]["succeeded"] == 10

    @pytest.mark.parametrize("seed", [1, 7])
    def test_the_seed_is_carried_back(self, seed: int) -> None:
        out = run_ensemble(with_draws([0.03, 0.398], seed=seed))
        assert out["ensemble"]["seed"] == seed
