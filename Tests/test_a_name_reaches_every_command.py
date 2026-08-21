"""A student knows the enzyme's name. Every command must take one.

WHY THIS FILE EXISTS
--------------------
Measured against the shipped CLI, as a second-year student would type it:

    $ scientific report --enzyme "lactate dehydrogenase" \\
          --organism "Homo sapiens" --substrate lactate
    ✗ report needs an enzyme, an organism and a substrate, e.g.
        scientific report --ec 1.1.1.27 ...

**The message says "needs an enzyme" and then rejects the enzyme they
gave.** `catalog --enzyme NAME` and `simulate --resolve --enzyme E` had both
accepted a name for weeks; `report` -- the one command whose whole purpose
is producing something a person can hand in -- required an EC number, which
is the single piece of information a teaching-lab student is least likely to
have. ADR 0124 named this as the last remaining guess in a first query and
ADR 0126 built the lookup; nothing then connected it to `report`.

THE POLICY IS NOT "RESOLVE THE NAME"
------------------------------------
It is "resolve the name, or refuse and say what you found". "lactate
dehydrogenase" is EC 1.1.1.27 (L-lactate dehydrogenase) AND EC 1.1.1.28
(D-lactate dehydrogenase): different proteins, different stereoisomers, one
common name. A wrong Km is a wrong number; a wrong EC is a correctly
formatted citation for a different protein.

That decision existed once, inside `report_enzyme_catalog.py`, where only
`catalog` could reach it. This file pins it in ONE place -- `enzyme_lookup`
-- and pins that both commands go through it, because two copies of one
refusal drift (ADR 0003, 0027, 0036, 0086).

UniProt is injected throughout. A test that had to reach the network to
check the wording of a refusal would fail for reasons unrelated to the
refusal, which is how this session has already lost an hour once.
"""
from __future__ import annotations

import pytest

from enzyme_lookup import EnzymeNameNotResolved, ec_number_for_name

LDH_BOTH = ["1.1.1.27", "1.1.1.28"]


def uniprot_returning(*candidates):
    """Stands in for the UniProt call, and records that it was made."""
    calls: list[tuple] = []

    def fetch(name, taxon_id):
        calls.append((name, taxon_id))
        return list(candidates)

    fetch.calls = calls
    return fetch


# ---------------------------------------------------------------------------
# One name, one enzyme
# ---------------------------------------------------------------------------


def test_a_name_matching_one_enzyme_resolves_to_it():
    fetch = uniprot_returning("1.1.1.1")
    assert ec_number_for_name("alcohol dehydrogenase", fetch=fetch) == "1.1.1.1"
    assert fetch.calls == [("alcohol dehydrogenase", None)]


# ---------------------------------------------------------------------------
# One name, two enzymes -- the case that must never resolve
# ---------------------------------------------------------------------------


def test_an_ambiguous_name_refuses_rather_than_picking():
    with pytest.raises(EnzymeNameNotResolved) as raised:
        ec_number_for_name("lactate dehydrogenase", fetch=uniprot_returning(*LDH_BOTH))

    message = str(raised.value)
    # BOTH must appear. A refusal that cannot say what it refused leaves the
    # choice unexercisable, and the student cannot re-run with "the one you
    # meant" if the tool will not say what the options were.
    assert "1.1.1.27" in message
    assert "1.1.1.28" in message
    assert raised.value.candidates == LDH_BOTH


def test_the_ambiguity_refusal_says_why_it_matters():
    """Not "ambiguous input". The reason is the whole argument.

    A student who reads "ambiguous" picks one to get moving. A student who
    reads "a wrong EC number is a citation for the wrong enzyme" goes and
    checks which one they meant.
    """
    with pytest.raises(EnzymeNameNotResolved) as raised:
        ec_number_for_name("lactate dehydrogenase", fetch=uniprot_returning(*LDH_BOTH))

    assert "different proteins" in str(raised.value)
    assert "citation for the wrong enzyme" in str(raised.value)


def test_a_name_nothing_indexes_says_so_and_offers_the_way_round():
    with pytest.raises(EnzymeNameNotResolved) as raised:
        ec_number_for_name("dehydrogenase of nothing", fetch=uniprot_returning())

    message = str(raised.value)
    assert "no reviewed enzyme" in message
    # Sauro's warning: a refusal with no path is how people end up hardcoding.
    assert "pass the EC number directly" in message


def test_a_network_failure_is_not_reported_as_an_unknown_enzyme():
    """The three-state rule, at the name step.

    "UniProt has no such enzyme" and "UniProt could not be reached" send a
    student to opposite places. Collapsing them tells someone their enzyme
    does not exist because the wifi dropped.
    """
    def explodes(name, taxon_id):
        raise ConnectionError("connection reset")

    with pytest.raises(EnzymeNameNotResolved) as raised:
        ec_number_for_name("lactate dehydrogenase", fetch=explodes)

    message = str(raised.value)
    assert "Could not look up" in message
    assert "connection reset" in message
    assert "no reviewed enzyme" not in message


# ---------------------------------------------------------------------------
# Both commands go through the one policy
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "script",
    ["report_lab.py", "report_enzyme_catalog.py"],
    ids=["report", "catalog"],
)
def test_both_commands_import_the_shared_policy(script):
    """Pins the wiring, not the behaviour.

    ADR 0126 put this decision inside the catalog script. When `report`
    needed it, copying the block would have produced two refusals that
    agree today and drift on the first edit -- which is the defect this
    repository has spent most of its effort on. Asserting the import is
    what stops the copy coming back.
    """
    import pathlib

    source = (
        pathlib.Path(__file__).resolve().parent.parent / "scripts" / script
    ).read_text(encoding="utf-8")

    assert "ec_number_for_name" in source, (
        f"{script} no longer routes name→EC through the shared policy"
    )
    # The IMPORT specifically, not just the call. A concurrent agent's
    # mutation loop restored this file from a snapshot taken before the
    # import was added, leaving the call site intact and the name unbound --
    # a NameError armed on exactly the branch this feature adds, invisible
    # to a check that only looked for the function's name somewhere in the
    # file. `test_the_enzyme_name_branch_actually_runs` is the real guard;
    # this one says which line is missing when it fires.
    assert "from enzyme_lookup import" in source, (
        f"{script} calls ec_number_for_name without importing it"
    )
    # The inlined version called this directly. Its return to either script
    # is the copy coming back.
    assert "fetch_ec_numbers_by_name(" not in source, (
        f"{script} calls the raw lookup again, bypassing the refusal policy"
    )


def test_the_enzyme_name_branch_actually_runs(monkeypatch):
    """Execute the branch, rather than asserting text about it.

    Everything above this line is a test of source code as a string. None of
    it would notice an unbound name, a typo in the payload key, or the
    branch never being reached -- and the first of those had already
    happened by the time this was written.

    So: drive `main()` with an `enzyme` and no `ec`, and require that the
    ambiguity refusal comes back out of the process.
    """
    import importlib.util
    import io
    import json
    import pathlib
    import sys

    repo = pathlib.Path(__file__).resolve().parent.parent
    for path in (str(repo), str(repo / "Tests")):
        if path not in sys.path:
            sys.path.insert(0, path)
    spec = importlib.util.spec_from_file_location(
        "report_lab_name_branch", repo / "scripts" / "report_lab.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    # UniProt injected at the module's own reference, so no network is
    # touched and the assertion is about the refusal, not the connection.
    monkeypatch.setattr(
        module, "ec_number_for_name",
        lambda name, *a, **k: (_ for _ in ()).throw(
            EnzymeNameNotResolved(
                "'lactate dehydrogenase' names more than one enzyme: "
                "1.1.1.27, 1.1.1.28.", LDH_BOTH
            )
        ),
    )
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({
        "enzyme": "lactate dehydrogenase",
        "organism": "Homo sapiens",
        "parameters": [{"name": "km", "substrate": "lactate", "quantity": "km"}],
    })))
    captured = io.StringIO()
    monkeypatch.setattr("sys.stdout", captured)
    code = module.main()
    monkeypatch.undo()

    out = json.loads(captured.getvalue())
    assert code == 1
    assert out["ok"] is False
    assert "1.1.1.27" in out["error"] and "1.1.1.28" in out["error"], (
        "the enzyme-name branch did not reach the shared refusal"
    )
