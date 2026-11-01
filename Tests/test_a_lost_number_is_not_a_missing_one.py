"""A number the caller lost is not a number the student never gave.

WHAT WAS MEASURED
-----------------
The CLI read `--s0` with `Number()`. The help text teaches `--s0 10mM`, so
that is what a student types:

    Number('10mM')               -> NaN
    JSON.stringify({s0: NaN})    -> {"s0": null}

`report_lab.py` then built its supplied list with a comprehension filtering
on `s.get("value") is not None`, which deleted the entry. Driven end to end
through the real script before the fix, the document came back saying:

    the simulation was not run: s0 is missing — yours to choose — how much
    substrate you put in, not a property of the enzyme

**They chose it.** The tool lost it and then lectured them for not providing
it. That refusal is worse than a crash, because it names a plausible cause,
reads as actionable, and sends the student to fix something that was never
wrong.

WHY THE PYTHON SIDE STILL CHECKS
--------------------------------
The CLI is fixed (`src/cli/reportQuantities.ts`, and its own tests). This is
the second line, and it guards a different thing: any caller — the HTTP API,
a notebook, a future front end — can build this payload. A `name` with no
`value` is a defect in whoever built it, and the only safe response to a
defect is to say so. Dropping it produces a report that is wrong about its
own inputs while looking complete, which is the failure mode this whole
project exists to remove.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


def load_script():
    for path in (str(REPO), str(REPO / "Tests")):
        if path not in sys.path:
            sys.path.insert(0, path)
    spec = importlib.util.spec_from_file_location(
        "report_lab_supplied", REPO / "scripts" / "report_lab.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def script():
    return load_script()


def test_a_value_that_arrives_null_is_refused_not_dropped(script):
    with pytest.raises(script.MalformedSuppliedValue) as raised:
        script.supplied_values(
            {"supplied": [{"name": "s0", "value": None, "unit": "mM"}]}
        )

    message = str(raised.value)
    assert "s0" in message
    # The message must point at the real cause. "Invalid payload" would be
    # true and useless; the student's actual mistake, if any, is upstream in
    # what they typed for the flag.
    assert "unit was not understood" in message


def test_the_refusal_says_it_will_not_report_it_as_missing(script):
    """The sentence that names the original defect.

    Kept as an assertion because the failure it describes is invisible: a
    reader of a dropped value sees a coherent document. If this guard is ever
    softened back into a filter, this is the line that goes first.
    """
    with pytest.raises(script.MalformedSuppliedValue) as raised:
        script.supplied_values({"supplied": [{"name": "s0", "value": None}]})

    assert "report it as missing" in str(raised.value)


def test_a_value_with_no_name_is_refused(script):
    with pytest.raises(script.MalformedSuppliedValue):
        script.supplied_values({"supplied": [{"value": 10.0}]})


def test_a_real_value_still_comes_through(script):
    """The guard against overcorrecting.

    Refusing everything would satisfy all three tests above while deleting
    the feature.
    """
    values = script.supplied_values(
        {
            "supplied": [
                {"name": "s0", "value": 10.0, "unit": "mM", "basis": "lab handout"},
                {"name": "vmax", "value": 0.25},
            ]
        }
    )

    assert [v.name for v in values] == ["s0", "vmax"]
    assert values[0].value == 10.0
    assert values[0].basis == "lab handout"


def test_no_supplied_values_at_all_is_not_an_error(script):
    """Absence is not malformation.

    A report with everything resolved from literature supplies nothing, and
    must not be refused for it.
    """
    assert script.supplied_values({}) == []
    assert script.supplied_values({"supplied": []}) == []


def test_zero_is_a_value(script):
    """`0` is falsy in both languages, and it is a legitimate s0.

    A guard written as `if not entry.get("value")` would refuse it. That is
    the same class of bug as the one being fixed — a real number treated as
    absence — so it is pinned rather than left to a future edit.
    """
    values = script.supplied_values({"supplied": [{"name": "i0", "value": 0}]})
    assert values[0].value == 0.0


def test_the_check_runs_before_anything_is_fetched(script, monkeypatch):
    """A malformed payload must not cost a BRENDA round trip.

    The first version of this guard sat after the resolver loop, so the
    observed failure was `Could not resolve 'km': 403 Forbidden` — the
    network error masking the payload defect entirely, and the check
    untestable without a network.
    """
    import io
    import json

    def must_not_be_called(*args, **kwargs):
        raise AssertionError("the resolver ran before the payload was checked")

    monkeypatch.setattr(script, "resolve_kinetic_value", must_not_be_called)
    monkeypatch.setattr(script, "fetch_brenda_html", must_not_be_called)
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({
        "ec": "1.1.1.27",
        "organism": "Homo sapiens",
        "parameters": [{"name": "km", "substrate": "lactate", "quantity": "km"}],
        "supplied": [{"name": "s0", "value": None, "unit": "mM"}],
    })))
    captured = io.StringIO()
    monkeypatch.setattr("sys.stdout", captured)
    code = script.main()
    monkeypatch.undo()

    out = json.loads(captured.getvalue())
    assert code == 1
    assert out["ok"] is False
    assert "s0" in out["error"]
