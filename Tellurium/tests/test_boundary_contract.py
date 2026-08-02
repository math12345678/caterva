"""Engine/application boundary contract test.

Rule 4 of the Stage 4 spec: the runner's dispatch table must stay in lockstep
with the engine's public simulation API. This test fails if:

  * the engine's ``__all__`` gains a ``simulate_*`` that the runner does not
    dispatch (unreachable domain), or
  * the runner dispatches a ``simulate_*`` that no longer exists in the
    engine (dangling dispatch), or
  * a ``DISPATCH`` domain has no matching ``run_*`` handler.

The runner is loaded from source here -- the same file the API server spawns
-- so the test guards the actual artifact, not a copy. See ADR 0007.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
RUNNER_PATH = (
    REPO_ROOT
    / "Science-Agent-Pipeline"
    / "artifacts"
    / "api-server"
    / "src"
    / "lib"
    / "tellurium_runner.py"
)

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from Tellurium import tellurium_engine  # noqa: E402


def _load_runner():
    spec = importlib.util.spec_from_file_location("tellurium_runner", RUNNER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


runner = _load_runner()

ENGINE_SIMULATE_FUNCTIONS = frozenset(
    name for name in getattr(tellurium_engine, "__all__", ())
    if name.startswith("simulate_")
)


def _contract_violations(
    runner_module,
    engine_functions: frozenset[str] = ENGINE_SIMULATE_FUNCTIONS,
) -> list[str]:
    """Return human-readable boundary violations (empty means healthy)."""
    issues: list[str] = []
    dispatched = set(runner_module.DISPATCH.values())
    domains = set(runner_module.DISPATCH.keys())
    handlers = set(runner_module._RUNNERS.keys())

    engine_only = engine_functions - dispatched
    if engine_only:
        issues.append(
            f"engine simulate_* not dispatched by runner: {sorted(engine_only)}"
        )

    dangling = dispatched - engine_functions
    if dangling:
        issues.append(
            f"runner dispatches simulate_* missing from engine: {sorted(dangling)}"
        )

    unhandled_domains = domains - handlers
    if unhandled_domains:
        issues.append(
            f"DISPATCH domains without a run_* handler: {sorted(unhandled_domains)}"
        )

    stray_handlers = handlers - domains
    if stray_handlers:
        issues.append(
            f"run_* handlers not reachable via DISPATCH: {sorted(stray_handlers)}"
        )

    for domain in domains:
        fn_name = runner_module.DISPATCH[domain]
        engine_fn = getattr(tellurium_engine, fn_name, None)
        if engine_fn is None:
            continue
        runner_fn = getattr(runner_module, f"run_{domain}", None)
        if runner_fn is None:
            issues.append(f"DISPATCH domain {domain!r} has no run_{domain} handler")

    return issues


class TestBoundaryContract:
    def test_every_engine_domain_is_dispatched(self):
        violations = _contract_violations(runner)
        assert not violations, "Boundary contract violated:\n" + "\n".join(
            f"  - {v}" for v in violations
        )

    def test_engine_all_contains_expected_domains(self):
        expected = {
            "simulate_michaelis_menten",
            "simulate_sir",
            "simulate_seir",
            "simulate_pcr",
            "simulate_monte_carlo_pi",
            "simulate_wright_fisher",
            "simulate_two_locus_wright_fisher",
            "simulate_molecular_dynamics",
            "simulate_gillespie_ssa",
            "simulate_sbml",
        }
        assert ENGINE_SIMULATE_FUNCTIONS == expected

    def test_runner_dispatches_expected_domains(self):
        assert set(runner.DISPATCH.keys()) == {
            "mm",
            "sir",
            "seir",
            "pcr",
            "monte_carlo_pi",
            "wright_fisher",
            "two_locus_wright_fisher",
            "molecular_dynamics",
            "gillespie_ssa",
            "sbml",
        }

    def test_mutation_engine_gain_is_detected(self, monkeypatch):
        """Simulated mutation: engine gains simulate_* the runner lacks."""
        mutated_engine = frozenset((*ENGINE_SIMULATE_FUNCTIONS, "simulate_bogus"))
        violations = _contract_violations(runner, mutated_engine)
        assert any("simulate_bogus" in v for v in violations)

    def test_mutation_runner_gain_is_detected(self, monkeypatch):
        """Simulated mutation: runner dispatches a simulate_* the engine lacks."""
        monkeypatch.setattr(runner, "DISPATCH", dict(runner.DISPATCH))
        runner.DISPATCH["mm"] = "simulate_does_not_exist"
        violations = _contract_violations(runner)
        assert any("missing from engine" in v for v in violations)

    def test_mutation_deleted_dispatch_entry_is_detected(self, monkeypatch):
        """Simulated mutation: one dispatch branch deleted (the Rule 4 case)."""
        dispatch = dict(runner.DISPATCH)
        dispatch.pop("molecular_dynamics")
        monkeypatch.setattr(runner, "DISPATCH", dispatch)
        monkeypatch.setattr(
            runner, "_RUNNERS", {k: v for k, v in runner._RUNNERS.items() if k != "molecular_dynamics"}
        )
        violations = _contract_violations(runner)
        assert any("simulate_molecular_dynamics" in v for v in violations)


class TestRunnerExecution:
    """Each domain runs end-to-end and honours the ok/flagged/flagReason shape."""

    SMALL_PARAMS = {
        "mm": {"km": 2.0, "vmax": 5.0, "s0": 10.0, "end": 1.0, "points": 3},
        "sir": {"beta": 0.3, "gamma": 0.1, "s0": 990.0, "i0": 10.0, "end": 10.0, "points": 4},
        "seir": {"beta": 0.3, "sigma": 0.2, "gamma": 0.1, "e0": 10.0, "end": 10.0, "points": 4},
        "pcr": {"n0": 100.0, "efficiency": 0.95, "cycles": 5},
        "monte_carlo_pi": {"n_samples": 64},
        "wright_fisher": {
            "population_size": 40, "starting_frequency": 0.5, "generations": 5,
            "replicate_runs": 3,
        },
        "two_locus_wright_fisher": {
            "population_size": 40, "generations": 5, "recombination_rate": 0.1,
            "replicate_runs": 3,
        },
        "molecular_dynamics": {
            "n_particles": 13, "temperature": 0.4, "timestep": 0.005, "n_steps": 5,
        },
        "gillespie_ssa": {"a0": 100, "k": 1.0, "end": 2.0},
        "sbml": {
            "sbml_string": "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
            "<sbml xmlns=\"http://www.sbml.org/sbml/level3/version1/core\" level=\"3\" version=\"1\">"
            "<model id=\"m\"><listOfCompartments>"
            "<compartment id=\"c\" size=\"1\"/></listOfCompartments>"
            "<listOfSpecies>"
            "<species id=\"S\" compartment=\"c\" initialConcentration=\"10\"/></listOfSpecies>"
            "<listOfReactions><reaction id=\"r\" reversible=\"false\">"
            "<listOfReactants><speciesReference species=\"S\" stoichiometry=\"1\"/></listOfReactants>"
            "<kineticLaw><math xmlns=\"http://www.w3.org/1998/Math/MathML\">"
            "<apply><times/><cn>1.0</cn><ci>S</ci></apply></math></kineticLaw>"
            "</reaction></listOfReactions></model></sbml>",
            "start": 0.0, "end": 1.0, "points": 3,
        },
    }

    @pytest.mark.parametrize("domain", sorted(SMALL_PARAMS))
    def test_domain_runs_and_shapes_ok(self, domain):
        handler = getattr(runner, f"run_{domain}")
        payload = handler(self.SMALL_PARAMS[domain])

        assert payload["ok"] is True
        assert payload["domain"] == domain
        assert isinstance(payload["parameters"], dict)
        assert isinstance(payload["trajectory"], list) and len(payload["trajectory"]) > 0
        point = payload["trajectory"][0]
        assert isinstance(point, dict) and point
        assert payload["flagged"] in (True, False)
        assert payload["flagReason"] is None or isinstance(payload["flagReason"], str)

    def test_flagged_engine_result_preserves_reason(self):
        payload = runner.run_molecular_dynamics({
            "n_particles": 13,
            "temperature": 0.9,
            "timestep": 0.005,
            "n_steps": 2,
        })
        assert payload["ok"] is True
        assert payload["flagged"] is True
        assert "initialization temperature" in payload["flagReason"]

    def test_runtime_ceilings_reject_before_simulation(self):
        with pytest.raises(ValueError, match="API runtime ceiling"):
            runner.run_monte_carlo_pi({"n_samples": 1_000_001})
        with pytest.raises(ValueError, match="API runtime ceiling"):
            runner.run_molecular_dynamics({"n_steps": 10_001})
        with pytest.raises(ValueError, match="API runtime ceiling"):
            runner.run_gillespie_ssa({"a0": 1_000_001})

    # ---- MD quadratic-cost ceiling -------------------------------------
    #
    # n_steps alone does not bound an MD request: cost is O(N^2 * steps) and
    # the engine ACCEPTS n_particles=5000 (ok=True, merely flagged, then
    # rounded up to 5324). Measured before the fix: 800 particles at 200
    # steps -- 4% of the step ceiling -- already cost 9.94s, and 5000
    # particles at the step ceiling is roughly six hours.

    def test_md_pair_step_budget_rejects_large_particle_counts(self):
        """A request under every scalar ceiling but quadratically huge."""
        with pytest.raises(ValueError, match="pair-steps"):
            runner.run_molecular_dynamics({"n_particles": 5000, "n_steps": 100})

    def test_md_pair_step_budget_rejects_at_step_ceiling(self):
        with pytest.raises(ValueError, match="pair-steps"):
            runner.run_molecular_dynamics(
                {"n_particles": 5000, "n_steps": runner.MAX_API_MD_STEPS})

    def test_md_documented_reference_case_stays_within_budget(self):
        """108 particles x 10k steps is the documented case and must remain
        allowed -- a budget that rejects it would be miscalibrated."""
        actual = runner._fcc_particle_count(108)
        assert actual * actual * runner.MAX_API_MD_STEPS <= runner.MAX_API_MD_PAIR_STEPS

    def test_fcc_round_up_matches_engine(self):
        """The budget must use the count the engine actually simulates.

        Rounding is always upward, so budgeting on the requested count would
        systematically underestimate cost.
        """
        assert runner._fcc_particle_count(108) == 108      # 4 * 3^3
        assert runner._fcc_particle_count(5000) == 5324    # 4 * 11^3
        assert runner._fcc_particle_count(1) == 4          # smallest cell
        for requested in (5, 33, 100, 500, 900):
            actual = runner._fcc_particle_count(requested)
            assert actual >= requested
            k = round((actual / 4) ** (1 / 3))
            assert actual == 4 * k**3
            assert 4 * (k - 1) ** 3 < requested  # k is the smallest sufficient

    def test_unknown_domain_returns_error(self, capsys):
        import json

        import io

        old_stdin = sys.stdin
        sys.stdin = io.StringIO(json.dumps({"domain": "nope", "parameters": {}}))
        try:
            with pytest.raises(SystemExit) as exc:
                runner.main()
            assert exc.value.code == 1
        finally:
            sys.stdin = old_stdin
        out = json.loads(capsys.readouterr().out)
        assert out["ok"] is False
        assert "unknown domain" in out["error"]

    @pytest.mark.parametrize(
        ("domain", "params", "ceiling_name"),
        [
            ("molecular_dynamics", {"n_steps": 10_001}, "MAX_API_MD_STEPS"),
            ("monte_carlo_pi", {"n_samples": 1_000_001}, "MAX_API_MONTE_CARLO_SAMPLES"),
            ("wright_fisher", {"generations": 10_001}, "MAX_API_WF_GENERATIONS"),
            ("two_locus_wright_fisher", {"generations": 10_001}, "MAX_API_WF_GENERATIONS"),
            ("gillespie_ssa", {"a0": 1_000_001}, "MAX_API_SSA_POPULATION"),
        ],
    )
    def test_runtime_ceiling_rejects_oversized_request(
        self, domain, params, ceiling_name, capsys
    ):
        """A request that would tie up a runner slot for many seconds is
        rejected with a structured error instead of running (STAGE_04_PART_01
        §6.3: the queue limits concurrency, the runner limits duration)."""
        import json

        import io

        payload = dict(self.SMALL_PARAMS[domain])
        payload.update(params)
        old_stdin = sys.stdin
        sys.stdin = io.StringIO(json.dumps({"domain": domain, "parameters": payload}))
        try:
            with pytest.raises(SystemExit) as exc:
                runner.main()
            assert exc.value.code == 1
        finally:
            sys.stdin = old_stdin
        out = json.loads(capsys.readouterr().out)
        assert out["ok"] is False
        assert ceiling_name in out["error"]
