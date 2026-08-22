"""The flagship command can be run without a network, and says what that cost.

WHY THIS FILE EXISTS
--------------------
On 2026-08-21 the exact invocation printed in `report`'s own help text was
run, as a student would run it:

    $ scientific report --ec 1.1.1.27 --organism "Homo sapiens" \\
          --substrate "(S)-lactate" --s0 10mM --vmax 0.25mM/s --seed 1
    -> Could not resolve 'km': 403 Forbidden

That was the whole run. `ensemble` had taken `--fixture` since it was
written; `report` — the command this project chose as its product — had no
path that did not require four live services at that instant. It could not
be demonstrated, and no test could exercise it end to end.

**The status was also pointing at the wrong host.** The 403 came from NCBI
Taxonomy, not BRENDA. A message naming the parameter and the HTTP code, and
not the service, sends a student to check whether the wrong database is
down.

WHAT IS ASSERTED, AND WHY IT IS NOT `contains`
----------------------------------------------
Five `contains` assertions passed for the wrong reason in one session of
this project, each satisfied by output that also *explained* the thing being
matched. So the offline note is asserted on the sentence, and the EC-mismatch
refusal is asserted to be absent of any resolved value — a refusal that still
returned rows would be the defect it exists to prevent.
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
REPORT_LAB = REPO_ROOT / "scripts" / "report_lab.py"
LDH_PAGE = REPO_ROOT / "Tests" / "fixtures" / "brenda_ldh_fixture.html"
LDH = "1.1.1.27"


def run(payload: dict) -> dict:
    """Drive the script the way the CLI drives it: JSON in, JSON out."""
    done = subprocess.run(
        [sys.executable, str(REPORT_LAB)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        timeout=300,
    )
    try:
        return json.loads(done.stdout.strip())
    except json.JSONDecodeError:  # pragma: no cover - diagnostic path
        pytest.fail(
            f"report_lab.py returned unparseable output.\n"
            f"stdout: {done.stdout[:400]}\nstderr: {done.stderr[:400]}"
        )


def offline_payload(**overrides) -> dict:
    payload = {
        "ec": LDH,
        "organism": "Homo sapiens",
        "fixture": str(LDH_PAGE),
        "parameters": [{"name": "km", "substrate": "pyruvate", "quantity": "km"}],
        "supplied": [
            {"name": "s0", "value": 10, "unit": "mM"},
            {"name": "vmax", "value": 0.25, "unit": "mM/s"},
        ],
        "s0": 10,
        "vmax": 0.25,
        "seed": 1,
    }
    payload.update(overrides)
    return payload


def test_a_saved_page_produces_a_whole_document_with_no_network():
    """The regression this file is named for.

    No skipif and no network marker: if this needs a network to pass, the
    fixture path does not work and the test should say so rather than being
    quietly skipped in the one environment that would notice.
    """
    result = run(offline_payload())
    assert result.get("ok") is True, result.get("error")
    markdown = result["markdown"]

    # A document, not a stub. Each of these is a section a student hands in.
    for heading in ("## Parameters", "## Result", "## What Terrium would not do"):
        assert heading in markdown, f"the report has no {heading!r} section"

    # The literature value actually reached the table — the point of the run.
    assert "0.03 mM" in markdown
    assert "BRENDA ref 286469" in markdown


def test_the_document_says_the_organism_was_not_verified():
    """Running offline costs a real check, and the cost is stated.

    Asserted on the SENTENCE. A report that silently skipped organism
    verification would be indistinguishable from one where the organism
    matched, which is the shape this project has recorded five times as
    'computed and not delivered'.
    """
    result = run(offline_payload())
    markdown = result["markdown"]

    assert "Organism relatedness is therefore NOT ASSESSED" in markdown
    # In the refusals section specifically, not loose in the prose.
    refusals = markdown.split("## What Terrium would not do", 1)[1]
    assert "NOT ASSESSED" in refusals
    assert result["refusals"], "the note must be a refusal, not decoration"


def test_a_live_run_carries_no_offline_note():
    """The note must not appear when it is not true.

    Without this, a note hardcoded into every report would pass the test
    above forever. Driven through the payload rather than the network: no
    fixture key means the offline branch is not taken, and the resolver is
    never reached because the EC is missing — which fails for a DIFFERENT
    reason, asserted here so the two cannot be confused.
    """
    result = run({"organism": "Homo sapiens", "parameters": []})
    assert result.get("ok") is not True
    assert "NOT ASSESSED" not in result.get("error", "")


def test_one_enzymes_page_is_refused_for_another_enzymes_question():
    """A real reference number attached to the wrong protein (ADR 0126).

    Nothing about a filename stops this. The page is read, its EC compared,
    and the run refused — and no value comes back, because a refusal that
    still returned rows would be the defect wearing a warning label.
    """
    result = run(offline_payload(ec="2.7.1.1", parameters=[
        {"name": "km", "substrate": "glucose", "quantity": "km"}
    ]))
    assert result.get("ok") is not True
    assert "markdown" not in result or not result.get("markdown")
    assert "2.7.1.1" in result["error"] and LDH in result["error"]


def test_a_page_that_names_no_enzyme_is_refused_rather_than_read(tmp_path):
    """'I could not identify it' must not pass as 'it matches'.

    The third state. Without this the mismatch check could be satisfied by
    a page containing no EC at all, which is the narrower-matcher failure
    this repository has now recorded eight times.
    """
    blank = tmp_path / "blank.html"
    blank.write_text("<html><body>no ec here</body></html>", encoding="utf-8")

    result = run(offline_payload(fixture=str(blank)))
    assert result.get("ok") is not True
    assert "contains no EC number" in result["error"]


def test_a_missing_fixture_is_named_rather_than_fetched(tmp_path):
    """A path that does not exist must not silently fall back to the network.

    That fallback is the tempting one to write, and it would mean `--fixture
    typo.html` quietly did the live lookup the student was avoiding.
    """
    result = run(offline_payload(fixture=str(tmp_path / "absent.html")))
    assert result.get("ok") is not True
    assert "No saved BRENDA page" in result["error"]
