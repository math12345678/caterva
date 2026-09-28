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
    / "caterva_runner.py"
)

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from caterva import caterva_engine  # noqa: E402


def _load_runner():
    spec = importlib.util.spec_from_file_location("caterva_runner", RUNNER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


runner = _load_runner()

ENGINE_SIMULATE_FUNCTIONS = frozenset(
    name for name in getattr(caterva_engine, "__all__", ())
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

    # A handler nobody can reach is dead code, which is what this catches.
    # COMPOSED_DOMAINS are reachable -- they are gated on _RUNNERS, not on
    # DISPATCH -- but they have no single engine simulate_* for DISPATCH to
    # name, so they are excluded here and required to be declared there.
    composed = set(getattr(runner_module, "COMPOSED_DOMAINS", {}))
    stray_handlers = handlers - domains - composed
    if stray_handlers:
        issues.append(
            f"run_* handlers reachable through neither DISPATCH nor "
            f"COMPOSED_DOMAINS: {sorted(stray_handlers)}"
        )

    undeclared = composed - handlers
    if undeclared:
        issues.append(
            f"COMPOSED_DOMAINS declared with no run_* handler: "
            f"{sorted(undeclared)}"
        )

    overlap = composed & domains
    if overlap:
        issues.append(
            f"domains in both DISPATCH and COMPOSED_DOMAINS: {sorted(overlap)}"
        )

    for domain in domains:
        fn_name = runner_module.DISPATCH[domain]
        engine_fn = getattr(caterva_engine, fn_name, None)
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
            "simulate_gillespie_ssa",
            "simulate_gillespie_ssa_bimolecular",
            "simulate_gillespie_ssa_replicates",
            "simulate_sbml",
        }
        assert expected == ENGINE_SIMULATE_FUNCTIONS

    def test_runner_dispatches_expected_domains(self):
        assert set(runner.DISPATCH.keys()) == {
            "mm",
            "mm_competitive_inhibition",
            "gillespie_ssa",
            "gillespie_ssa_bimolecular",
            "gillespie_ssa_replicates",
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
        dispatch.pop("gillespie_ssa_bimolecular")
        monkeypatch.setattr(runner, "DISPATCH", dispatch)
        monkeypatch.setattr(
            runner, "_RUNNERS", {k: v for k, v in runner._RUNNERS.items() if k != "gillespie_ssa_bimolecular"}  # noqa: SLF001
        )
        violations = _contract_violations(runner)
        assert any("simulate_gillespie_ssa_bimolecular" in v for v in violations)

    # The mutation above deletes the entry from BOTH tables, so what catches it
    # is the engine axis: `simulate_gillespie_ssa_bimolecular` stops being dispatched.
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
            {k: v for k, v in runner._RUNNERS.items() if k != "gillespie_ssa_replicates"},  # noqa: SLF001
        )
        violations = _contract_violations(runner)
        assert any("without a run_* handler" in v and "gillespie_ssa_replicates" in v for v in violations)

    def test_mutation_dispatch_removed_but_handler_kept_is_detected(self, monkeypatch):
        """One-sided mutation: DISPATCH loses a domain, _RUNNERS still has it.

        The opposite drift, and the quieter one: the handler simply becomes
        unreachable. Nothing fails, the domain just stops existing.
        """
        monkeypatch.setattr(
            runner, "DISPATCH", {k: v for k, v in runner.DISPATCH.items() if k != "gillespie_ssa_replicates"}
        )
        violations = _contract_violations(runner)
        assert any(
            "reachable through neither DISPATCH nor COMPOSED_DOMAINS" in v
            and "gillespie_ssa_replicates" in v
            for v in violations
        )

    def test_drifted_tables_report_a_build_defect_not_a_bad_request(self, monkeypatch):
        """main() must not present an internal drift as the student's mistake."""
        monkeypatch.setattr(
            runner,
            "_RUNNERS",
            {k: v for k, v in runner._RUNNERS.items() if k != "gillespie_ssa_replicates"},  # noqa: SLF001
        )
        monkeypatch.setattr(
            sys, "stdin", io.StringIO(json.dumps({"domain": "gillespie_ssa_replicates", "parameters": {}}))
        )
        buf = io.StringIO()
        monkeypatch.setattr(sys, "stdout", buf)
        with pytest.raises(SystemExit):
            runner.main()
        error = json.loads(buf.getvalue())["error"]
        assert "build defect" in error
        assert "unknown domain" not in error  # the request was valid
        assert error != "'gillespie_ssa_replicates'"  # the bare KeyError repr this replaced


class TestRunnerExecution:
    """Each domain runs end-to-end and honours the ok/flagged/flagReason shape."""

    SMALL_PARAMS: ClassVar[dict[str, dict[str, float | int | str]]] = {
        "mm": {"km": 2.0, "vmax": 5.0, "s0": 10.0, "end": 1.0, "points": 3},
        "mm_competitive_inhibition": {
            "km": 2.0, "vmax": 5.0, "ki": 1.0, "s0": 10.0, "i0": 1.0, "end": 1.0, "points": 3,
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
        # Five molecules: legal, but too few for the trajectory to resemble
        # the deterministic curve, so the engine flags it and says why.
        payload = runner.run_gillespie_ssa({"a0": 5, "k": 1.0, "end": 2.0})
        assert payload["ok"] is True
        assert payload["flagged"] is True
        assert "molecules" in payload["flagReason"]

    def test_runtime_ceilings_reject_before_simulation(self):
        with pytest.raises(ValueError, match="API runtime ceiling"):
            runner.run_gillespie_ssa({"a0": 1_000_001})

    # ---- raw-SBML ceilings ---------------------------------------------
    #
    # run_sbml had no ceilings at all. Survivable only because nothing could
    # reach it (the API exposes no way to supply a model), but its cost is
    # driven by a caller-supplied document rather than by parameters the
    # runner can reason about, so it needs its own limits before any path
    # exposes it. See the MAX_API_SBML_* block in caterva_runner.py for the
    # measurements.

    @staticmethod
    def _sbml_chain(n: int) -> str:
        """SBML for a linear chain S0 -> S1 -> ... -> Sn (n reactions)."""
        from caterva.continuous.model_building import antimony_to_sbml

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
