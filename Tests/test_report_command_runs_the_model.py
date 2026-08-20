"""The report command must produce the result it is a report of.

WHY THIS FILE EXISTS
--------------------
`build_report` has always rendered a "## Result" section, and
`test_the_trajectory_is_summarised_not_dumped` has always passed. It passes
by handing `build_report` a `Trajectory()` object the test builds itself.

`scripts/report_lab.py` -- the only thing that runs in production -- never
passed a `simulation` at all. So the section was implemented, tested, and
unreachable: every report a student could actually generate stopped after
the citations, and the one command whose stated purpose is "run the
simulation and show where the numbers came from" did the second half only.

ADR 0133 recorded this honestly in its own Consequences ("the CLI does not
yet run the simulation as part of `report`"), which is why it is being
finished rather than discovered.

This is the parity-test lesson in its exact form, and this repository has
now hit it four times: **a test that constructs its own input cannot verify
how the input is produced** (ADR 0038). The fix is not a better unit test.
It is a test that drives the real script.

WHAT IS ASSERTED, AND WHY NOT THE NUMBERS
-----------------------------------------
Not "the trajectory is correct" -- `Terium/tests` owns that, against a
closed-form solution, and restating it here would be a second, weaker copy
of a check that already exists.

What is asserted is the wiring nothing else can see: that the section
exists, that it was computed from the values the document prints, and that
when it cannot be computed the document says so instead of falling silent.
"""
from __future__ import annotations

import importlib.util
import io
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent

from fixture_lineages import fixture_lineage_provider  # noqa: E402
from test_fallback_logic import (  # noqa: E402
    fake_taxon_id_provider,
    fake_uniprot_provider,
    load_fixture,
)

LDH = "1.1.1.27"


def load_script():
    """Load `scripts/report_lab.py` as a module, the real one.

    Imported by path rather than copied, so this cannot drift from what
    ships -- the same approach `test_archive_export_uses_the_model.py` uses,
    and for the same reason.
    """
    for path in (str(REPO), str(REPO / "Tests")):
        if path not in sys.path:
            sys.path.insert(0, path)
    spec = importlib.util.spec_from_file_location(
        "report_lab_script", REPO / "scripts" / "report_lab.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def script(monkeypatch):
    """The real script, with only its network edges replaced.

    The REAL `resolve_kinetic_value` still runs -- still parses the table,
    ranks the rows, applies the cross-species gate and refuses. Stubbing the
    resolver instead would make every assertion below a test of the stub.

    Four edges reach the network, not one: BRENDA's HTML, UniProt, the taxon
    id and the lineage. Only `html_provider` was injectable at the call
    site, so the first attempt at this test failed with a live `403
    Forbidden` -- worth recording, because a test that reaches the network
    fails for reasons that have nothing to do with the code under test.
    """
    module = load_script()
    real = module.resolve_kinetic_value

    def offline(ec, organism, substrate, **kwargs):
        kwargs.setdefault("uniprot_provider", fake_uniprot_provider)
        kwargs.setdefault("taxon_id_provider", fake_taxon_id_provider)
        kwargs.setdefault("lineage_provider", fixture_lineage_provider)
        kwargs.setdefault("search_literature", False)
        return real(ec, organism, substrate, **kwargs)

    monkeypatch.setattr(
        module,
        "fetch_brenda_html",
        lambda ec, timeout=15: load_fixture("brenda_ldh_fixture.html"),
    )
    monkeypatch.setattr(module, "resolve_kinetic_value", offline)
    return module


def run(script, payload, monkeypatch) -> dict:
    """Drive `main()` exactly as the CLI does: JSON in, JSON out."""
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    captured = io.StringIO()
    monkeypatch.setattr("sys.stdout", captured)
    code = script.main()
    monkeypatch.undo()
    return {"exit": code, **json.loads(captured.getvalue())}


BASE = {
    "title": "Human LDH",
    "question": "How fast is lactate consumed?",
    "ec": LDH,
    "organism": "Homo sapiens",
    "parameters": [{"name": "km", "substrate": "lactate", "quantity": "km"}],
}


def payload(**overrides) -> dict:
    merged = dict(BASE)
    merged.update(overrides)
    return merged


# ---------------------------------------------------------------------------
# The section exists at all
# ---------------------------------------------------------------------------


def test_a_complete_request_produces_a_result_section(script, monkeypatch):
    out = run(
        script,
        payload(
            supplied=[
                {"name": "s0", "value": 10.0, "unit": "mM", "basis": "lab handout"},
                {"name": "vmax", "value": 0.25, "unit": "mM/s", "basis": "measured"},
            ]
        ),
        monkeypatch,
    )

    assert out["ok"] is True
    assert "## Result" in out["markdown"], (
        "the report ran the resolver, printed the parameters and stopped "
        "before the thing the student came for"
    )
    assert "time points" in out["markdown"]


def test_the_run_uses_the_km_the_document_prints(script, monkeypatch):
    """The Result must be the result of the values in the Parameters table.

    This is the property that makes the document a claim rather than two
    unrelated printouts. Substrate falls from s0 toward zero, so a run at
    the stated s0 must end below it and not below zero -- a Result computed
    from some other s0 could not satisfy both.
    """
    out = run(
        script,
        payload(
            supplied=[
                {"name": "s0", "value": 10.0, "unit": "mM"},
                {"name": "vmax", "value": 0.25, "unit": "mM/s"},
            ]
        ),
        monkeypatch,
    )

    rows = [
        line for line in out["markdown"].splitlines() if line.startswith("| 0")
    ]
    assert rows, "no trajectory row starting at t=0"
    first = [cell.strip() for cell in rows[0].strip("|").split("|")]
    # time, then the substrate column: the run starts at the stated s0.
    assert abs(float(first[1]) - 10.0) < 1e-6, (
        f"the run started at {first[1]}, not the s0 the table states"
    )


# ---------------------------------------------------------------------------
# When it cannot run, it says so -- the whole point of the report
# ---------------------------------------------------------------------------


def test_a_missing_s0_is_a_stated_refusal_not_a_missing_section(
    script, monkeypatch
):
    out = run(script, payload(supplied=[{"name": "vmax", "value": 0.25}]), monkeypatch)

    assert "## Result" not in out["markdown"]
    assert any("simulation was not run" in r for r in out["refusals"]), (
        "the model could not run and the document did not mention it"
    )
    assert any("s0" in r for r in out["refusals"])


def test_a_missing_s0_is_described_as_the_students_choice(script, monkeypatch):
    """s0 and km are missing for opposite reasons, and must not read alike.

    Lisa Jeske's and Herbert Sauro's disagreement is about values the
    literature owns. s0 is not one: it is how much substrate went in the
    tube. Telling a student that s0 "could not be sourced" sends them
    looking for a paper that cannot exist.
    """
    out = run(script, payload(supplied=[{"name": "vmax", "value": 0.25}]), monkeypatch)

    s0_refusal = next(r for r in out["refusals"] if "s0" in r)
    assert "yours to choose" in s0_refusal
    assert "not a property" in s0_refusal


def test_an_unrunnable_model_reports_why_rather_than_falling_silent(
    script, monkeypatch
):
    """A negative Vmax is not a model. The report must not hide that."""
    out = run(
        script,
        payload(
            supplied=[
                {"name": "s0", "value": 10.0},
                {"name": "vmax", "value": -1.0},
            ]
        ),
        monkeypatch,
    )

    assert out["ok"] is True, "an invalid parameter is a finding, not a crash"
    assert "## Result" not in out["markdown"]
    assert any("would not integrate" in r for r in out["refusals"])


# ---------------------------------------------------------------------------
# One number, one place
# ---------------------------------------------------------------------------


def test_the_same_value_given_twice_with_two_numbers_is_refused(
    script, monkeypatch
):
    """`s0` could arrive as `payload["s0"]` AND inside `supplied`.

    The ensemble read the first, the Parameters table printed the second,
    and nothing compared them: a document stating 5 while being computed at
    10, internally consistent in appearance. Choosing a winner silently
    would keep the defect and add a rule, so it is refused.
    """
    out = run(
        script,
        payload(
            s0=10.0,
            supplied=[
                {"name": "s0", "value": 5.0},
                {"name": "vmax", "value": 0.25},
            ],
        ),
        monkeypatch,
    )

    assert out["ok"] is False
    assert "s0" in out["error"]
    assert "10" in out["error"] and "5" in out["error"]


def test_the_ensemble_runs_at_the_values_the_document_states(
    script, monkeypatch
):
    """The ensemble section must use the same numbers as everything else.

    It used to read `payload["s0"]` while the Parameters table printed
    `supplied`. A student who put s0 in the place the table reads -- the
    documented place -- got an ensemble section saying the model could not
    be run, in a report whose own table showed the value it needed.

    *Danio rerio* has no Km for pyruvate in this fixture, so the resolver
    withholds and offers cross-species candidates: a real ensemble, from the
    real resolution path, rather than a hand-built list.
    """
    out = run(
        script,
        payload(
            organism="Danio rerio",
            parameters=[
                {
                    "name": "km",
                    "substrate": "pyruvate",
                    "quantity": "km",
                }
            ],
            supplied=[
                {"name": "s0", "value": 10.0, "unit": "mM"},
                {"name": "vmax", "value": 0.25, "unit": "mM/s"},
            ],
        ),
        monkeypatch,
    )

    assert out["ok"] is True
    assert out["disagreements"], "no ensemble was produced for a withheld km"

    # Asserted POSITIVELY, on the outcomes table. `consequence_of` renders
    # either an outcome per candidate or a refusal, so the presence of the
    # table is the thing that distinguishes "it ran" from "it said it could
    # not". An earlier version of this test asserted the ABSENCE of a
    # sentence, guessed the wording wrong, and passed under mutation --
    # which is the failure mode this whole file exists to catch, occurring
    # in the test written to catch it.
    assert "| value | result |" in out["markdown"], (
        "the ensemble did not run at the s0 and vmax the document's own "
        "Parameters table states"
    )
    assert "not supplied" not in out["markdown"]


def test_the_same_value_given_twice_and_agreeing_is_fine(script, monkeypatch):
    """The guard must catch a contradiction, not a redundancy.

    Refusing agreement too would make the check impossible to satisfy for a
    caller that legitimately sets both.
    """
    out = run(
        script,
        payload(
            s0=10.0,
            supplied=[
                {"name": "s0", "value": 10.0},
                {"name": "vmax", "value": 0.25},
            ],
        ),
        monkeypatch,
    )

    assert out["ok"] is True
    assert "## Result" in out["markdown"]
