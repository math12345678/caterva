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
import io
import json
import sys
from pathlib import Path
from typing import ClassVar

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
RUNNER_PATH = (
    REPO_ROOT
    / "Science-Agent-Pipeline"
    / "artifacts"
    / "api-server"
    / "src"
    / "lib"
    / "terium_runner.py"
)

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from Terium import terium_engine  # noqa: E402


def _load_runner():
    spec = importlib.util.spec_from_file_location("terium_runner", RUNNER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


runner = _load_runner()

ENGINE_SIMULATE_FUNCTIONS = frozenset(
    name for name in getattr(terium_engine, "__all__", ())
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
    handlers = set(runner_module._RUNNERS.keys())  # noqa: SLF001

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
        engine_fn = getattr(terium_engine, fn_name, None)
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
            "simulate_mm_competitive_inhibition",
            "simulate_sir",
            "simulate_seir",
            "simulate_pcr",
            "simulate_monte_carlo_pi",
            "simulate_wright_fisher",
            "simulate_two_locus_wright_fisher",
            "simulate_molecular_dynamics",
            "simulate_gillespie_ssa",
            "simulate_gillespie_ssa_bimolecular",
            "simulate_gillespie_ssa_replicates",
            "simulate_lotka_volterra",
            "simulate_cell_cycle_oscillator",
            "simulate_repressilator",
            "simulate_sbml",
        }
        assert expected == ENGINE_SIMULATE_FUNCTIONS

    def test_runner_dispatches_expected_domains(self):
        assert set(runner.DISPATCH.keys()) == {
            "mm",
            "mm_competitive_inhibition",
            "sir",
            "seir",
            "pcr",
            "monte_carlo_pi",
            "wright_fisher",
            "two_locus_wright_fisher",
            "molecular_dynamics",
            "gillespie_ssa",
            "gillespie_ssa_bimolecular",
            "gillespie_ssa_replicates",
            "lotka_volterra",
            "cell_cycle_oscillator",
            "repressilator",
            "sbml",
        }

    def test_mutation_engine_gain_is_detected(self):
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
            runner, "_RUNNERS", {k: v for k, v in runner._RUNNERS.items() if k != "molecular_dynamics"}  # noqa: SLF001
        )
        violations = _contract_violations(runner)
        assert any("simulate_molecular_dynamics" in v for v in violations)

    # The mutation above deletes the entry from BOTH tables, so what catches it
    # is the engine axis: `simulate_molecular_dynamics` stops being dispatched.
    # That left the two branches comparing DISPATCH against _RUNNERS -- the
    # `unhandled_domains` and `stray_handlers` checks -- never once shown to
    # fire. They are the branches that matter most at runtime, because main()
    # tests membership in one table and looks the handler up in the other. The
    # two mutations below edit exactly one table each.

    def test_mutation_handler_removed_but_dispatch_kept_is_detected(self, monkeypatch):
        """One-sided mutation: _RUNNERS loses a domain, DISPATCH still lists it.

        Before this was proven, a slip here reached the student as the string
        ``'pcr'`` -- the repr of a KeyError -- reported as if the request were
        invalid.
        """
        monkeypatch.setattr(
            runner,
            "_RUNNERS",
            {k: v for k, v in runner._RUNNERS.items() if k != "pcr"},  # noqa: SLF001
        )
        violations = _contract_violations(runner)
        assert any("without a run_* handler" in v and "pcr" in v for v in violations)

    def test_mutation_dispatch_removed_but_handler_kept_is_detected(self, monkeypatch):
        """One-sided mutation: DISPATCH loses a domain, _RUNNERS still has it.

        The opposite drift, and the quieter one: the handler simply becomes
        unreachable. Nothing fails, the domain just stops existing.
        """
        monkeypatch.setattr(
            runner, "DISPATCH", {k: v for k, v in runner.DISPATCH.items() if k != "pcr"}
        )
        violations = _contract_violations(runner)
        assert any("not reachable via DISPATCH" in v and "pcr" in v for v in violations)

    def test_drifted_tables_report_a_build_defect_not_a_bad_request(self, monkeypatch):
        """main() must not present an internal drift as the student's mistake."""
        monkeypatch.setattr(
            runner,
            "_RUNNERS",
            {k: v for k, v in runner._RUNNERS.items() if k != "pcr"},  # noqa: SLF001
        )
        monkeypatch.setattr(
            sys, "stdin", io.StringIO(json.dumps({"domain": "pcr", "parameters": {}}))
        )
        buf = io.StringIO()
        monkeypatch.setattr(sys, "stdout", buf)
        with pytest.raises(SystemExit):
            runner.main()
        error = json.loads(buf.getvalue())["error"]
        assert "build defect" in error
        assert "unknown domain" not in error  # the request was valid
        assert error != "'pcr'"  # the bare KeyError repr this replaced


class TestRunnerExecution:
    """Each domain runs end-to-end and honours the ok/flagged/flagReason shape."""

    SMALL_PARAMS: ClassVar[dict[str, dict[str, float | int | str]]] = {
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
        "gillespie_ssa_bimolecular": {"a0": 60, "b0": 40, "k": 0.01, "end": 2.0},
        "gillespie_ssa_replicates": {"a0": 60, "k": 0.5, "end": 2.0, "n_replicates": 10},
        "sbml": {
            "sbml_string": '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<sbml xmlns="http://www.sbml.org/sbml/level3/version1/core" level="3" version="1">'
            '<model id="m"><listOfCompartments>'
            '<compartment id="c" size="1"/></listOfCompartments>'
            "<listOfSpecies>"
            '<species id="S" compartment="c" initialConcentration="10"/></listOfSpecies>'
            '<listOfReactions><reaction id="r" reversible="false">'
            '<listOfReactants><speciesReference species="S" stoichiometry="1"/></listOfReactants>'
            '<kineticLaw><math xmlns="http://www.w3.org/1998/Math/MathML">'
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

    # ---- raw-SBML ceilings ---------------------------------------------
    #
    # run_sbml had no ceilings at all. Survivable only because nothing could
    # reach it (the API exposes no way to supply a model), but its cost is
    # driven by a caller-supplied document rather than by parameters the
    # runner can reason about, so it needs its own limits before any path
    # exposes it. See the MAX_API_SBML_* block in terium_runner.py for the
    # measurements.

    @staticmethod
    def _sbml_chain(n: int) -> str:
        """SBML for a linear chain S0 -> S1 -> ... -> Sn (n reactions)."""
        from Terium.continuous.model_building import antimony_to_sbml

        species = ", ".join(f"S{i}" for i in range(n + 1))
        lines = [
            f"model chain{n}",
            "  compartment c = 1.0;",
            f"  species {species} in c;",
            "  S0 = 100.0;",
        ]
        lines += [f"  S{i} = 0.0;" for i in range(1, n + 1)]
        lines.append("  k = 0.5;")
        lines += [f"  J{i}: S{i} -> S{i+1}; c * k * S{i};" for i in range(n)]
        lines.append("end")
        return antimony_to_sbml("\n".join(lines))

    def test_sbml_rejects_points_over_ceiling(self):
        with pytest.raises(ValueError, match="MAX_API_SBML_POINTS"):
            runner.run_sbml(
                {
                    "sbml_string": self._sbml_chain(1),
                    "points": runner.MAX_API_SBML_POINTS + 1,
                }
            )

    def test_sbml_rejects_too_many_reactions(self):
        with pytest.raises(ValueError, match="MAX_API_SBML_REACTIONS"):
            runner.run_sbml(
                {
                    "sbml_string": self._sbml_chain(
                        runner.MAX_API_SBML_REACTIONS + 1
                    ),
                    "points": 51,
                }
            )

    def test_sbml_rejects_absurd_source_length(self):
        # Must start with "<" to get PAST the path/URL guard, which runs
        # first (cheapest security check before any sizing question). A
        # payload of plain "x" characters is rejected as a path, not for
        # its length, and would not exercise this ceiling at all.
        oversized = "<" + "x" * runner.MAX_API_SBML_SOURCE_CHARS
        with pytest.raises(ValueError, match="MAX_API_SBML_SOURCE_CHARS"):
            runner.run_sbml({"sbml_string": oversized, "points": 51})

    def test_sbml_rejects_unparseable_document_with_a_reason(self):
        """Not a crash and not a bare 'failed' -- libsbml's own complaint."""
        with pytest.raises(ValueError, match="could not be parsed as SBML"):
            runner.run_sbml({"sbml_string": "<not-sbml/>", "points": 51})

    # ---- sbml_string is a fetch primitive, not just a string -----------
    #
    # simulate_sbml ends at roadrunner.RoadRunner(sbml_string), whose
    # constructor accepts SBML content OR a filesystem path OR a URL, and
    # fetches whichever it gets. Verified by execution: a bare path and a
    # file:// URI were both read off local disk, and an http:// URL produced
    # a real outbound GET to a chosen address whose response was parsed and
    # run. Unvalidated, this parameter is a local-file-read and an SSRF.
    #
    # These pin the explicit guard. The reaction-counting parse rejects
    # these too, so a regression here would NOT show up as a test failure
    # elsewhere -- which is exactly why the protection must not rest on
    # that parse, and why these tests name the vectors directly.

    @pytest.mark.parametrize(
        ("label", "payload"),
        [
            ("bare filesystem path", "/etc/hostname"),
            ("file URI", "file:///etc/hostname"),
            ("http URL", "http://127.0.0.1:9/model.xml"),
            ("cloud metadata endpoint", "http://169.254.169.254/latest/meta-data/"),
            ("https URL", "https://example.invalid/model.xml"),
            ("leading whitespace before a path", "   /etc/hostname"),
        ],
    )
    def test_sbml_refuses_paths_and_urls(self, label, payload):
        """A non-document payload must never reach the engine's loader."""
        with pytest.raises(ValueError, match="not a file path or URL"):
            runner.run_sbml({"sbml_string": payload, "points": 5})

    def test_sbml_guard_keys_on_first_non_space_character(self):
        """The guard lstrips before testing, so padding cannot smuggle a
        path past it.

        Note it is only ever the REJECTING direction that whitespace
        matters for. A real SBML document opens with an XML declaration,
        and XML forbids anything -- including whitespace -- before it
        ("XML declaration not permitted in this location"), so there is no
        such thing as a valid document with leading blanks to protect.
        """
        with pytest.raises(ValueError, match="not a file path or URL"):
            runner.run_sbml(
                {"sbml_string": "\n\t  file:///etc/hostname", "points": 5}
            )

    def test_sbml_source_ceiling_does_not_shadow_the_reaction_ceiling(self):
        """The reaction limit must be the binding constraint, not dead code.

        SBML XML runs ~15x the length of the Antimony it came from, and the
        first version of MAX_API_SBML_SOURCE_CHARS was sized against the
        Antimony figures. At 100,000 it sat BELOW the ~151 KB a legitimate
        200-reaction model occupies: legal models were rejected for length,
        and MAX_API_SBML_REACTIONS could never be reached. A model at the
        reaction ceiling must fit inside the source ceiling with room over.
        """
        at_ceiling = self._sbml_chain(runner.MAX_API_SBML_REACTIONS)
        assert len(at_ceiling) < runner.MAX_API_SBML_SOURCE_CHARS

    def test_sbml_accepts_a_substantial_but_legal_model(self):
        """A ceiling that rejects ordinary work is miscalibrated."""
        result = runner.run_sbml(
            {"sbml_string": self._sbml_chain(150), "points": 51}
        )
        assert result["ok"] is True
        assert len(result["trajectory"]) == 51

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
        actual = runner._fcc_particle_count(108)  # noqa: SLF001
        assert actual * actual * runner.MAX_API_MD_STEPS <= runner.MAX_API_MD_PAIR_STEPS

    def test_fcc_round_up_matches_engine(self):
        """The budget must use the count the engine actually simulates.

        Rounding is always upward, so budgeting on the requested count would
        systematically underestimate cost.
        """
        assert runner._fcc_particle_count(108) == 108      # 4 * 3^3  # noqa: SLF001
        assert runner._fcc_particle_count(5000) == 5324    # 4 * 11^3  # noqa: SLF001
        assert runner._fcc_particle_count(1) == 4          # smallest cell  # noqa: SLF001
        for requested in (5, 33, 100, 500, 900):
            actual = runner._fcc_particle_count(requested)  # noqa: SLF001
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
            ("gillespie_ssa_bimolecular", {"a0": 600_000, "b0": 500_000}, "MAX_API_SSA_POPULATION"),
            ("gillespie_ssa_replicates", {"a0": 100, "n_replicates": 2_000}, "MAX_API_SSA_REPLICATES"),
            ("gillespie_ssa_replicates", {"a0": 1_000_000, "n_replicates": 1_000}, "MAX_API_SSA_POPULATION"),
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
