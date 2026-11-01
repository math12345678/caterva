"""Every place a name becomes an EC number reaches the one policy.

WHY THIS EXISTS
---------------
Six places turn an enzyme name into an EC number: `caterva compose
--subject`, `caterva structure --subject`, the catalog script, the report
script (which `cite.py` and the TypeScript CLI call), the literature-layer
helper `ec_number_for_name`, and the runner the API server spawns. Before
the enzyme finder, five of them shared one UniProt search and the sixth,
the runner, had a copy. A policy in two places drifts, and this repository
has found that defect in a plausibility table, a reliability score and a
request validator.

So this does not read their source and hope. It makes the one function
`caterva.enzymes.policy.resolve_enzyme_name` report each call it receives,
then drives every caller with the name the owner complained about, and
requires that each one reached it and that each one's refusal carries the
same named candidates. A caller that kept a private copy of the decision
would not be seen by the spy and fails here.

Nothing reaches the network: every name below is settled, or refused, by the
shipped enzyme nomenclature before any lookup could be made.
"""
from __future__ import annotations

import importlib.util
import io
import json
import pathlib
import sys

import pytest

import enzyme_lookup

REPO = pathlib.Path(__file__).resolve().parent.parent
LIB_DIR = str(REPO / "Science-Agent-Pipeline" / "artifacts" / "api-server" / "src" / "lib")
for path in (str(REPO), str(REPO / "Tests"), LIB_DIR):
    if path not in sys.path:
        sys.path.insert(0, path)

import science_agent_runner  # noqa: E402

from caterva.enzymes import policy  # noqa: E402

NAME = "lactate dehydrogenase"


@pytest.fixture()
def spy(monkeypatch):
    """Record every call to the policy, delegating to the real one."""
    calls = []
    real = policy.resolve_enzyme_name

    def recording(name, *args, **kwargs):
        calls.append(name)
        return real(name, *args, **kwargs)

    monkeypatch.setattr(policy, "resolve_enzyme_name", recording)
    import caterva.structure.__main__ as structure

    monkeypatch.setattr(structure, "resolve_enzyme_name", recording)
    return calls


def _script(name):
    spec = importlib.util.spec_from_file_location(f"{name}_under_test", REPO / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_script(monkeypatch, module, payload):
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    out = io.StringIO()
    monkeypatch.setattr(sys, "stdout", out)
    code = module.main()
    return code, json.loads(out.getvalue())


def _assert_names_both_enzymes(text):
    assert "EC 1.1.1.27 L-lactate dehydrogenase" in text, text
    assert "EC 1.1.1.28 D-lactate dehydrogenase" in text, text


def test_the_literature_layer_helper_reaches_it(spy):
    with pytest.raises(enzyme_lookup.EnzymeNameNotResolved) as raised:
        enzyme_lookup.ec_number_for_name(NAME, organism="human")
    assert spy == [NAME]
    _assert_names_both_enzymes(str(raised.value))
    assert raised.value.candidates[:2] == ["1.1.1.27", "1.1.1.28"]


def test_compose_reaches_it(spy, capsys):
    from caterva.compose.__main__ import main

    code = main(["Michaelis Menten", "--subject", NAME, "--organism", "human", "--substrate", "pyruvate",
                 "--no-simulate", "--no-ranking", "--no-analysis"])
    out = capsys.readouterr().out
    assert code == 3, "a refused name must not exit 0"
    assert spy == [NAME]
    _assert_names_both_enzymes(out)
    assert "--subject 1.1.1.27" in out


def test_compose_says_what_a_resolved_name_was_read_as(spy):
    from types import SimpleNamespace

    from caterva.compose.__main__ import _resolve_subject
    from caterva.compose.pipeline import compose

    model = compose("Michaelis Menten", subject="pyruvate kinase", organism="human")
    args = SimpleNamespace(subject="pyruvate kinase", organism="human")
    resolved, read_as, refusal = _resolve_subject(model, args)
    assert spy == ["pyruvate kinase"]
    assert refusal is None and resolved.subject == "2.7.1.40"
    assert read_as == "Read 'pyruvate kinase' as EC 2.7.1.40 (pyruvate kinase): accepted name matches exactly."


def test_compose_replaces_a_transferred_ec_number_and_says_so(spy):
    from types import SimpleNamespace

    from caterva.compose.__main__ import _resolve_subject
    from caterva.compose.pipeline import compose

    model = compose("Michaelis Menten", subject="1.1.1.32", organism="human")
    resolved, read_as, refusal = _resolve_subject(model, SimpleNamespace(subject="1.1.1.32", organism="human"))
    assert spy == ["1.1.1.32"]
    assert refusal is None and resolved.subject == "1.1.1.1"
    assert "was transferred" in read_as


def test_compose_leaves_an_ec_number_the_nomenclature_does_not_hold_alone(spy):
    from types import SimpleNamespace

    from caterva.compose.__main__ import _resolve_subject
    from caterva.compose.pipeline import compose

    model = compose("Michaelis Menten", subject="9.9.9.9", organism="human")
    resolved, read_as, refusal = _resolve_subject(model, SimpleNamespace(subject="9.9.9.9", organism="human"))
    assert (resolved.subject, read_as, refusal) == ("9.9.9.9", None, None)


def test_structure_reaches_it(spy, capsys):
    from caterva.structure.__main__ import main

    code = main(["--subject", NAME, "--organism", "human"])
    err = capsys.readouterr().err
    assert code == 3
    assert spy == [NAME]
    _assert_names_both_enzymes(err)
    assert err.startswith("Refused:")


def test_catalog_reaches_it(spy, monkeypatch):
    code, out = _run_script(monkeypatch, _script("report_enzyme_catalog"), {"enzyme": NAME, "organism": "Homo sapiens"})
    assert code == 1 and out["ok"] is False
    assert spy == [NAME]
    _assert_names_both_enzymes(out["error"])
    assert out["error"].endswith("--ec 1.1.1.27")


def test_report_reaches_it(spy, monkeypatch):
    code, out = _run_script(monkeypatch, _script("report_lab"), {
        "enzyme": NAME, "organism": "Homo sapiens",
        "parameters": [{"name": "km", "substrate": "lactate", "quantity": "km"}],
    })
    assert code == 1 and out["ok"] is False
    assert spy == [NAME]
    _assert_names_both_enzymes(out["error"])
    assert out["error"].endswith("--ec 1.1.1.27")


def test_the_runner_reaches_it(spy, monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(
        {"enzymeName": NAME, "organism": "Homo sapiens", "substrate": "lactate"})))
    science_agent_runner.main()
    result = json.loads(capsys.readouterr().out)
    assert spy == [NAME]
    assert result["source"] == "ec_ambiguous"
    _assert_names_both_enzymes(result["ecRefusal"])
    assert result["ecCandidates"][:2] == ["1.1.1.27", "1.1.1.28"]
    assert [c["label"] for c in result["ecCandidateNames"][:2]][0].startswith("EC 1.1.1.27 L-lactate dehydrogenase")


def test_the_runner_resolves_a_unique_name_without_asking_uniprot(spy, monkeypatch):
    def not_called(*args, **kwargs):
        raise AssertionError("UniProt was asked for a name the nomenclature holds")

    monkeypatch.setattr(enzyme_lookup, "fetch_ec_numbers_by_name", not_called)
    monkeypatch.setattr(enzyme_lookup, "fetch_taxon_id", not_called)
    assert science_agent_runner.resolve_ec_number("pyruvate kinase", "Homo sapiens") == "2.7.1.40"
    assert science_agent_runner.resolve_ec_number(NAME, "Homo sapiens") is None
    assert spy == ["pyruvate kinase", NAME]


def test_the_typescript_layer_forwards_the_refusal_and_derives_nothing():
    """The runner's sentence is carried as `ecRefusal`; queryResolver.ts uses it as written.

    A source check, because the TypeScript suite is not run from here: the
    branch must read `ecRefusal`, and must not build a sentence of its own
    from the bare numbers when the refusal is present.
    """
    source = (REPO / "Science-Agent-Pipeline" / "artifacts" / "api-server" / "src" / "lib" / "queryResolver.ts").read_text()
    assert "ecRefusal" in source
    branch = source[source.index("if ((reason === \"ec_ambiguous\" || reason === \"ec_not_resolved\") && ecRefusal)"):]
    assert "${ecRefusal}" in branch[:600]
    assert "agentResult.ecRefusal" in source
    runner_ts = (REPO / "Science-Agent-Pipeline" / "artifacts" / "api-server" / "src" / "lib" / "scienceAgent.ts").read_text()
    assert "ecCandidateNames" in runner_ts and "ecRefusal" in runner_ts


def test_no_command_keeps_a_private_copy_of_the_decision():
    """The raw UniProt name search is reached only through the policy's fallback.

    `fetch_ec_numbers_by_name` is the step-4 lookup; a command calling it
    directly would be deciding a name for itself.
    """
    allowed = {
        "Tests/enzyme_lookup.py",                       # defines it and passes it to the policy
        "caterva/enzymes/policy.py",                    # the fallback lookup helper
        "Science-Agent-Pipeline/artifacts/api-server/src/lib/science_agent_runner.py",  # its organism-narrowed fallback
    }
    offenders = []
    for root in ("caterva", "scripts", "Science-Agent-Pipeline/artifacts/api-server/src/lib", "Tests"):
        for path in (REPO / root).rglob("*.py"):
            rel = path.relative_to(REPO).as_posix()
            if rel in allowed or "/tests/" in rel or "/_literature/" in rel or path.name.startswith("test_"):
                continue
            if "fetch_ec_numbers_by_name(" in path.read_text(encoding="utf-8", errors="replace"):
                offenders.append(rel)
    assert offenders == []
