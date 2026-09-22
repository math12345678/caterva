"""`scripts/cite.py`: real constants with real citations, behind flags.

WHY THESE TESTS
---------------
The literature path worked and was unreachable (ADR 0178): `compose
--subject` never ran it, `compose_and_parameterise` failed every scout on
an import while reporting `converged=True`, and the one working entry point
read a six-key JSON payload on stdin. `cite.py` is the typeable interface
to the SAME code, so what these pin is the wiring: that the flags become
the payload `report_lab` expects, and that the offline route still produces
a document with a citation in it.

They do not hit the network. The live behaviour is recorded in ADR 0178
with the values and reference numbers it returned on the day.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CITE = ROOT / "scripts" / "cite.py"
LDH_FIXTURE = ROOT / "Tests" / "fixtures" / "brenda_ldh_fixture.html"


def _cite(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(CITE), *args],
        capture_output=True, text=True, cwd=str(ROOT), timeout=600,
    )


def test_the_script_exists_and_the_makefile_names_it():
    assert CITE.is_file()
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    assert "scripts/cite.py" in makefile, "make cite is how this is discovered"


def test_the_flags_become_the_payload_report_lab_expects():
    """The payload's shape is report_lab's contract, not this script's."""
    sys.path.insert(0, str(ROOT / "scripts"))
    try:
        import cite  # type: ignore
    finally:
        sys.path.pop(0)

    args = cite.main.__globals__["argparse"].Namespace(
        ec="1.1.1.27", enzyme=None, organism="Homo sapiens",
        substrate="pyruvate", quantity=["km", "kcat"], s0=10.0, vmax=0.25,
        concentration_unit="mM", basis="lab handout", title=None,
        question="q", fixture=None, seed=None, json=False,
    )
    payload = cite.build_payload(args)

    assert payload["ec"] == "1.1.1.27"
    assert "enzyme" not in payload, "an EC number was given; do not also send a name"
    assert payload["organism"] == "Homo sapiens"
    assert [p["quantity"] for p in payload["parameters"]] == ["km", "kcat"]
    assert all(p["substrate"] == "pyruvate" for p in payload["parameters"])
    # The values the USER supplies must travel as supplied, with their basis,
    # or the document cannot mark them "yours".
    supplied = {s["name"]: s for s in payload["supplied"]}
    assert supplied["s0"]["value"] == 10.0 and supplied["s0"]["unit"] == "mM"
    assert supplied["vmax"]["unit"] == "mM/s"
    assert supplied["s0"]["basis"] == "lab handout"


def test_a_name_is_sent_as_a_name_so_the_resolver_can_refuse_it():
    """`--enzyme` must not be silently turned into an EC number here.

    Resolving a name is UniProt's answer and a refusal when it is ambiguous
    (ADR 0178); doing it in this script would be the guess the refusal
    exists to prevent.
    """
    sys.path.insert(0, str(ROOT / "scripts"))
    try:
        import cite  # type: ignore
    finally:
        sys.path.pop(0)
    args = cite.main.__globals__["argparse"].Namespace(
        ec=None, enzyme="lactate dehydrogenase", organism=None,
        substrate="pyruvate", quantity=["km"], s0=10.0, vmax=0.25,
        concentration_unit="mM", basis="b", title=None, question="q",
        fixture=None, seed=None, json=False,
    )
    payload = cite.build_payload(args)
    assert payload["enzyme"] == "lactate dehydrogenase"
    assert "ec" not in payload


def test_either_an_ec_number_or_a_name_is_required():
    assert _cite("--substrate", "pyruvate").returncode == 2


def test_a_substrate_is_required():
    assert _cite("--ec", "1.1.1.27").returncode == 2


@pytest.mark.skipif(not LDH_FIXTURE.is_file(), reason="the saved BRENDA page is not in this tree")
def test_the_offline_route_produces_a_document_with_a_citation():
    """The whole point, offline: a measured value and who measured it."""
    run = _cite("--ec", "1.1.1.27", "--organism", "Homo sapiens",
                "--substrate", "pyruvate", "--fixture", str(LDH_FIXTURE))
    assert run.returncode == 0, run.stderr
    out = run.stdout
    assert "| km |" in out
    assert "literature" in out
    assert "BRENDA ref" in out, "a value without its reference is the thing this refuses to print"
    # The values the user supplied must be marked as theirs, not the literature's.
    assert "**yours**" in out
    # And the document must say no search was run, because none was.
    assert "no literature search" in out.lower() or "made no network requests" in out.lower()
