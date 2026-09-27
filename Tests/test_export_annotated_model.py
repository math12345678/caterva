"""The annotated-model export — Sauro's mechanism, end to end.

Runs the real script as a subprocess, because the contract being tested is
the JSON-in/model-out seam between the TypeScript provenance layer and the
Python model builders. Testing the functions directly would skip the part
that actually breaks.
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys

import pytest

SCRIPT = pathlib.Path(__file__).resolve().parent.parent / "scripts" / "export_annotated_model.py"

MM_PAYLOAD = {
    "domain": "mm",
    "parameters": {"km": 2.5, "vmax": 5.0, "s0": 10.0},
    "query": "simulate michaelis menten of lactate dehydrogenase",
    "runId": "run_abc123",
    "provenance": {
        "km": {
            "origin": "resolved",
            "citation": "BRENDA ref 740253",
            "organism": "Homo sapiens",
            "source": "brenda_exact",
            "citationStatus": "verified",
            "reliability": {"assay completeness": "complete", "organism match": "exact"},
        },
        "vmax": {
            "origin": "resolved",
            "citation": "BRENDA ref 649716",
            "organism": "Oryctolagus cuniculus",
            "source": "brenda_cross_species",
            "crossSpecies": True,
        },
        "s0": {"origin": "user"},
    },
}


def run(payload) -> tuple[int, dict]:
    proc = subprocess.run(
        [sys.executable, str(SCRIPT)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=180,
    )
    return proc.returncode, json.loads(proc.stdout or "{}")


def test_exports_a_model_with_provenance_inside_it():
    code, out = run(MM_PAYLOAD)
    assert code == 0 and out["ok"] is True
    model = out["model"]

    assert "model michaelis_menten" in model
    assert "BRENDA ref 740253" in model
    assert "run_abc123" in model
    assert "simulate michaelis menten" in model


def test_resolver_names_reach_the_model_symbols():
    """The resolver says `s0`; the Antimony says `S`.

    Without the mapping, `S` was annotated NO PROVENANCE RECORDED while
    `s0` was reported as provenance for a parameter that does not exist --
    a model claiming no source for a value that had one. Found by the
    orphan report, which is why annotate_antimony reports orphans instead
    of dropping them.
    """
    _, out = run(MM_PAYLOAD)
    model = out["model"]

    s_line = next(l for l in model.splitlines() if l.strip().startswith("S ="))
    assert "NO PROVENANCE RECORDED" not in s_line
    assert "do not appear" not in model, "s0 should no longer be an orphan"


def test_model_structure_is_not_reported_as_an_unsourced_measurement():
    """`P = 0` says 'no product at t=0'. It is part of what the model IS,
    not a number anyone should be asked to cite."""
    _, out = run(MM_PAYLOAD)
    model = out["model"]

    p_line = next(l for l in model.splitlines() if l.strip().startswith("P ="))
    assert "model structure" in p_line
    assert "P" not in out["unsourced"]


def test_cross_species_is_the_thing_the_summary_reports():
    _, out = run(MM_PAYLOAD)
    assert out["unsourced"] == ["Vmax"]
    vmax_line = next(
        l for l in out["model"].splitlines() if l.strip().startswith("Vmax =")
    )
    assert "CROSS-SPECIES" in vmax_line
    assert "Oryctolagus cuniculus" in vmax_line


def test_a_missing_parameter_is_refused_not_defaulted():
    """An export that quietly filled a gap would produce a file whose
    comments claim full provenance for a value nobody supplied — the worst
    possible output of a provenance feature."""
    payload = {**MM_PAYLOAD, "parameters": {"km": 2.5, "vmax": 5.0}}
    code, out = run(payload)
    assert code == 1
    assert out["ok"] is False
    assert "s0" in out["error"]
    assert "Nothing is defaulted" in out["error"]


def test_an_unknown_domain_names_the_ones_it_knows():
    code, out = run({**MM_PAYLOAD, "domain": "nonexistent_domain"})
    assert code == 1
    assert "mm" in out["error"] and "sir" in out["error"]


def test_engine_validation_rejection_is_reported_not_swallowed():
    """A negative Km is rejected by the engine's own validator. The export
    must surface that reason rather than emit a model built from it."""
    payload = {**MM_PAYLOAD, "parameters": {"km": -1.0, "vmax": 5.0, "s0": 10.0}}
    code, out = run(payload)
    assert code == 1
    assert out["ok"] is False
    assert out["error"]


def test_malformed_json_fails_cleanly():
    proc = subprocess.run(
        [sys.executable, str(SCRIPT)],
        input="{not json",
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert proc.returncode == 1
    assert json.loads(proc.stdout)["ok"] is False


@pytest.mark.parametrize(
    "domain,parameters",
    [
        ("mm", {"km": 2.5, "vmax": 5.0, "s0": 10.0}),
        (
            "mm_competitive_inhibition",
            {"km": 2.5, "vmax": 5.0, "ki": 1.2, "s0": 10.0, "i": 0.5},
        ),
        ("sir", {"beta": 0.3, "gamma": 0.1, "s0": 990.0, "i0": 10.0, "r0_recovered": 0.0}),
    ],
)
def test_every_supported_domain_exports_with_every_assignment_commented(
    domain, parameters
):
    code, out = run({"domain": domain, "parameters": parameters, "provenance": {}})
    assert code == 0, out.get("error")

    for line in out["model"].splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("//"):
            continue
        if "=" in stripped and stripped.endswith(";"):
            pytest.fail(f"{domain}: assignment with no provenance comment: {stripped!r}")


def test_exported_model_still_loads_as_antimony():
    """The whole point is a file another tool can open. If the annotation
    broke the syntax, everything above would still pass."""
    _, out = run(MM_PAYLOAD)
    sys.path.insert(0, str(SCRIPT.parent.parent))
    from caterva.continuous.model_building import antimony_to_sbml

    sbml = antimony_to_sbml(out["model"])
    assert "<sbml" in sbml
    assert sbml.count("<parameter") >= 2
