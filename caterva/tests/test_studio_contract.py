"""The studio's contract: Python and TypeScript declare the same shapes, and a number keeps its origin.

WHY THIS FILE EXISTS
--------------------
`caterva/studio/contract.py` and the page's `src/api/types.ts` are written
by hand on both sides of an HTTP boundary, by different people at once
(docs/studio/CONTRACT.md). A key renamed on one side arrives on the other as
`undefined`, and the page draws an empty cell: on this project, a number
silently missing looks like a number nobody measured. So every TypedDict,
string union and shared constant is compared here, key by key, including
which keys are optional.

The provenance helpers are checked against the real engine (a composed
Michaelis-Menten model), not against objects built for the test, because
the defect they exist to prevent is a real origin mis-transcribed.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import math
import re
from pathlib import Path
from typing import get_args

import pytest

from caterva.studio import contract, routes
from caterva.studio.adapters import ADAPTER_MODULES, cli_parser, load_registry, parse_cli

ROOT = Path(__file__).resolve().parents[2]
STUDIO_UI = ROOT / "Science-Agent-Pipeline" / "artifacts" / "caterva-studio"
TYPES_TS = STUDIO_UI / "src" / "api" / "types.ts"
CONTRACT_MD = ROOT / "docs" / "studio" / "CONTRACT.md"
FIXTURE = STUDIO_UI / "src" / "__fixtures__" / "api" / "contract" / "michaelis-menten-parameters.json"

#: Interfaces the page declares for its own convenience, with no Python twin.
TS_ONLY = {"RunRequests", "RunResults"}
#: Python aliases (not TypedDicts) the page declares as `type X = ...`.
PY_ALIASES = {"RatesRequest", "RatesResult"}


# ---------------------------------------------------------------------------
# Reading types.ts
# ---------------------------------------------------------------------------


def _ts_source() -> str:
    assert TYPES_TS.is_file(), f"{TYPES_TS} is missing; the page cannot mirror a contract it does not have"
    # Comments removed so a commented-out key cannot count as declared.
    text = TYPES_TS.read_text(encoding="utf-8")
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return re.sub(r"//[^\n]*", "", text)


def _ts_interfaces() -> dict[str, dict[str, bool]]:
    """interface name -> {key: optional?}"""
    out: dict[str, dict[str, bool]] = {}
    for name, body in re.findall(r"export interface (\w+)\s*\{(.*?)\n\}", _ts_source(), flags=re.S):
        keys: dict[str, bool] = {}
        for key, optional in re.findall(r"^\s*\"?([\w.]+)\"?(\?)?\s*:", body, flags=re.M):
            keys[key] = bool(optional)
        out[name] = keys
    return out


def _ts_unions() -> dict[str, tuple[str, ...]]:
    out: dict[str, tuple[str, ...]] = {}
    for name, body in re.findall(r"export type (\w+)\s*=\s*([^;]+);", _ts_source()):
        members = re.findall(r'"([^"]*)"', body)
        if members and "|" in body:
            out[name] = tuple(members)
    return out


def _ts_constants() -> dict[str, object]:
    out: dict[str, object] = {}
    for name, value in re.findall(r"export const (\w+)\s*=\s*([^;]+);", _ts_source()):
        value = value.strip()
        if value.startswith('"'):
            out[name] = json.loads(value)
        elif re.fullmatch(r"\d+", value):
            out[name] = int(value)
    return out


def test_types_ts_was_read_at_all():
    """A parser that matched nothing would make every mirror test pass."""
    assert len(_ts_interfaces()) >= 80
    assert len(_ts_unions()) >= 10
    assert len(_ts_constants()) >= 6


# ---------------------------------------------------------------------------
# The mirror
# ---------------------------------------------------------------------------


def test_every_python_shape_has_a_typescript_twin_and_no_stray_ones():
    py = set(contract.MIRRORED_TYPES)
    ts = set(_ts_interfaces()) - TS_ONLY
    assert py - ts == set(), f"declared in contract.py and missing from types.ts: {sorted(py - ts)}"
    assert ts - py == set(), f"declared in types.ts and missing from contract.py: {sorted(ts - py)}"


@pytest.mark.parametrize("name", contract.MIRRORED_TYPES)
def test_each_shape_has_the_same_keys_and_the_same_optional_ones(name):
    typed = getattr(contract, name)
    ts = _ts_interfaces()[name]
    py = {k: (k in typed.__optional_keys__) for k in list(typed.__required_keys__) + list(typed.__optional_keys__)}
    assert set(ts) == set(py), f"{name}: keys differ; python only {set(py) - set(ts)}, ts only {set(ts) - set(py)}"
    differ = {k for k in py if py[k] != ts[k]}
    assert not differ, f"{name}: optional in one and required in the other: {sorted(differ)}"


@pytest.mark.parametrize("name", sorted(contract.MIRRORED_UNIONS))
def test_each_string_union_has_the_same_members(name):
    assert _ts_unions().get(name) == contract.MIRRORED_UNIONS[name]


def test_the_literals_and_their_tuples_agree():
    pairs = [
        (contract.RunKind, contract.RUN_KINDS), (contract.RunStatus, contract.RUN_STATUSES),
        (contract.OutcomeMeaning, contract.OUTCOME_MEANINGS), (contract.ProvenanceKind, contract.PROVENANCE_KINDS),
        (contract.ChosenBy, contract.CHOSEN_BY), (contract.Nonfinite, contract.NONFINITE),
        (contract.ErrorCode, contract.ERROR_CODES), (contract.Need, contract.NEEDS),
        (contract.Theme, contract.THEMES), (contract.EventName, contract.EVENT_NAMES),
        (contract.SectionStatus, contract.SECTION_STATUSES),
    ]
    for literal, members in pairs:
        assert get_args(literal) == members


def test_the_shared_constants_agree():
    ts = _ts_constants()
    for name, value in contract.MIRRORED_CONSTANTS.items():
        assert ts.get(name) == value, f"{name}: python {value!r}, types.ts {ts.get(name)!r}"


def test_every_kind_names_request_and_result_shapes_both_sides_declare():
    assert set(contract.KIND_SHAPES) == set(contract.RUN_KINDS)
    declared = set(contract.MIRRORED_TYPES) | PY_ALIASES
    ts_text = _ts_source()
    for kind, (request, result) in contract.KIND_SHAPES.items():
        assert request in declared and result in declared, kind
        assert re.search(rf'"?{re.escape(kind)}"?:\s*\["{request}",\s*"{result}"\]', ts_text), (
            f"types.ts KIND_SHAPES disagrees about {kind}"
        )


# ---------------------------------------------------------------------------
# Routes and the document that describes them
# ---------------------------------------------------------------------------


def test_every_route_is_in_the_contract_document_and_handlers_are_unique():
    assert CONTRACT_MD.is_file(), "docs/studio/CONTRACT.md is the contract; it must exist"
    text = CONTRACT_MD.read_text(encoding="utf-8")
    handlers = [r.handler for r in routes.ROUTES]
    assert len(handlers) == len(set(handlers))
    for route in routes.ROUTES:
        assert f"{route.method} {route.path}" in text, f"{route.method} {route.path} is not documented"


def test_routes_distinguish_not_found_from_wrong_method_and_hide_dev_only_ones():
    run = "20260930-141502-md-setup-0123abcd"
    route, params, _ = routes.find("GET", f"/api/runs/{run}/artifacts/model.sbml", dev=False)
    assert route is not None and params == {"id": run, "name": "model.sbml"}
    assert routes.find("POST", "/api/health", dev=False) == (None, {}, True)
    assert routes.find("GET", "/api/runs/../../etc/passwd", dev=False) == (None, {}, False)
    assert routes.find("GET", "/api/dev/session", dev=False)[0] is None
    assert routes.find("GET", "/api/dev/session", dev=True)[0].handler == "dev_session"


# ---------------------------------------------------------------------------
# The adapter registry
# ---------------------------------------------------------------------------


def test_every_adapter_module_exists_and_loads():
    adapters = ROOT / "caterva" / "studio" / "adapters"
    for name in ADAPTER_MODULES:
        assert (adapters / f"{name}.py").is_file(), name
    registry = load_registry()
    assert set(registry.kinds()) | set(registry.missing()) == set(contract.RUN_KINDS)
    assert not set(registry.kinds()) & set(registry.missing())


def test_an_adapter_may_answer_only_the_routes_it_owns():
    from caterva.studio.adapters import Registry

    owners = {r.owner for r in routes.ROUTES}
    assert owners - {"core"} <= set(ADAPTER_MODULES), owners
    registry = Registry()
    handler = lambda request: {"shapes": []}  # noqa: E731
    registry.add_endpoint("compose_shapes", handler, owner="compose")
    assert registry.endpoint("compose_shapes") is handler
    with pytest.raises(ValueError, match="registered twice"):
        registry.add_endpoint("compose_shapes", handler, owner="compose")
    with pytest.raises(ValueError, match="belongs to 'structure'"):
        registry.add_endpoint("structure_coordinates", handler, owner="compose")
    with pytest.raises(ValueError, match="belongs to 'core'"):
        registry.add_endpoint("health", handler, owner="compose")
    with pytest.raises(ValueError, match="not a handler"):
        registry.add_endpoint("compose_everything", handler, owner="compose")


def test_a_malformed_request_is_refused_with_argparse_s_own_message():
    from caterva.compose.__main__ import build_parser

    with pytest.raises(contract.Malformed, match="invalid choice: 'pdf'"):
        parse_cli(build_parser, ["Michaelis Menten", "--export", "pdf"], "caterva compose")
    with pytest.raises(contract.Malformed, match="not a run"):
        parse_cli(build_parser, ["--help"], "caterva compose")
    args = parse_cli(build_parser, ["Michaelis Menten", "--robustness"], "caterva compose")
    assert args.description == "Michaelis Menten"


def test_a_subcommand_parser_refuses_the_same_way():
    def build(prog):
        parser = argparse.ArgumentParser(prog=prog)
        sub = parser.add_subparsers(dest="command", required=True)
        ssa = sub.add_parser("ssa")
        ssa.add_argument("--a0", type=int)
        return parser

    with pytest.raises(contract.Malformed, match="invalid int value"):
        cli_parser(build, "caterva sim").parse_args(["ssa", "--a0", "many"])


# ---------------------------------------------------------------------------
# Serialisation without rounding
# ---------------------------------------------------------------------------


def test_jsonable_keeps_floats_exact_and_names_what_json_cannot_hold():
    import numpy as np

    @dataclasses.dataclass(frozen=True)
    class Point:
        x: float

        @property
        def doubled(self) -> float:
            return self.x * 2

    out = contract.jsonable({"p": Point(0.1 + 0.2), "z": complex(1, -2), "n": float("nan"),
                             "a": np.array([1.5, 2.5]), "i": np.int64(3), "t": (1, 2)})
    assert out["p"] == {"x": 0.1 + 0.2, "doubled": (0.1 + 0.2) * 2}
    assert out["z"] == {"re": 1.0, "im": -2.0}
    assert out["n"] is None and out["a"] == [1.5, 2.5] and out["i"] == 3 and out["t"] == [1, 2]
    json.dumps(out, allow_nan=False)
    with pytest.raises(TypeError, match="no rule for"):
        contract.jsonable(object())


def test_a_non_finite_value_is_kept_as_a_named_fact():
    v = contract.sourced(float("inf"), "s", contract.computed("settling time"))
    assert v["value"] is None and v["nonfinite"] == "inf"
    with pytest.raises(ValueError, match="without a reason"):
        contract.placeholder("  ")
    with pytest.raises(ValueError):
        contract.outcome_for("compose", 2, "malformed questions never become runs")


def test_an_outcome_says_why_it_is_not_a_success_in_the_command_s_words():
    assert contract.outcome_for("sim", 0, "1000 events")["reason"] is None
    refused = contract.outcome_for("compose", 3, "not built", "Not built.\n\nglycolysis is a subject")
    assert refused["meaning"] == "refused" and refused["reason"].startswith("Not built.")
    with pytest.raises(ValueError, match="must carry the CLI's reason"):
        contract.outcome_for("compose", 3, "not built")
    negative = contract.outcome_for("bind", 4, "disagrees")
    assert negative["meaning"] == "negative" and negative["reason"] == contract.NEGATIVE_MEANING["bind"]
    with pytest.raises(ValueError, match="never exits 4"):
        contract.outcome_for("compose", 4, "compose has no exit 4")
    assert set(contract.NEGATIVE_MEANING) <= set(contract.RUN_KINDS)


def test_the_negative_meanings_agree_with_types_ts():
    body = re.search(r"export const NEGATIVE_MEANING[^=]*=\s*\{(.*?)\};", _ts_source(), flags=re.S)
    assert body, "types.ts declares no NEGATIVE_MEANING"
    ts = {k: v for k, v in re.findall(r'^\s*"?([\w.]+)"?:\s*"([^"]*)",?$', body.group(1), flags=re.M)}
    assert ts == dict(contract.NEGATIVE_MEANING)


def test_a_real_stability_report_serialises_with_its_judgements():
    from caterva.compose.analysis import analyse
    from caterva.compose.pipeline import compose

    report = analyse(compose("a toggle switch between two repressors").network)
    out = contract.jsonable(report)
    json.dumps(out, allow_nan=False)
    assert out["starts_tried"] == report.starts_tried
    assert [p["stable"] for p in out["fixed_points"]] == [p.stable for p in report.fixed_points]
    for point, original in zip(out["fixed_points"], report.fixed_points):
        for eig, value in zip(point["eigenvalues"], original.eigenvalues):
            assert eig == {"re": value.real, "im": value.imag}


# ---------------------------------------------------------------------------
# Provenance, from the engine's own decision
# ---------------------------------------------------------------------------


def _structure_only_values():
    from caterva.compose.export import provenance_of
    from caterva.compose.pipeline import compose

    model = compose("Michaelis Menten")
    provenanced = provenance_of(model)
    return provenanced, [contract.from_parameter_origin(o) for o in provenanced.origins]


def test_every_number_of_a_composed_model_keeps_the_origin_export_decided():
    provenanced, values = _structure_only_values()
    assert len(values) == len(provenanced.origins)
    for origin, value in zip(provenanced.origins, values):
        assert value["id"] == origin.identifier
        assert value["value"] == origin.value and value["unit"] == origin.unit
        assert value["provenance"]["kind"] == origin.origin
        # The reason is the exporters' own sentence, not a second one.
        assert value["provenance"]["reason"] == origin.sentence()
    assert {v["provenance"]["kind"] for v in values} == {"placeholder", "chosen"}
    json.dumps(values, allow_nan=False)


def test_the_page_s_fixture_is_what_the_helpers_produce_today():
    """The page's component tests render this file; it must be the engine's
    output, not a hand-edited copy (its README says how it was made)."""
    assert FIXTURE.is_file()
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    _, values = _structure_only_values()
    assert fixture["structure_only"]["parameters"] == values
    measured = [v for v in fixture["searched"]["parameters"] if v["provenance"]["kind"] == "measured"]
    assert {v["id"] for v in measured} == {"reaction_Km", "reaction_kcat"}
    for v in measured:
        assert v["provenance"]["citation"]["text"].startswith("BRENDA ref ")
        assert not math.isnan(v["value"])


# ---------------------------------------------------------------------------
# The command
# ---------------------------------------------------------------------------


def test_studio_is_a_command_and_refuses_a_non_loopback_host():
    import io
    from contextlib import redirect_stderr, redirect_stdout

    from caterva.app import COMMANDS, main

    assert COMMANDS["studio"][0] == "caterva.studio.__main__"
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        with pytest.raises(SystemExit) as exc:
            main(["studio", "--host", "0.0.0.0"])
    assert exc.value.code == 2 and "not a loopback address" in err.getvalue()
    with redirect_stdout(out), redirect_stderr(err):
        with pytest.raises(SystemExit) as exc:
            main(["studio", "--dev-origin", "https://evil.example"])
    assert exc.value.code == 2 and "not a loopback origin" in err.getvalue()
    with redirect_stdout(out), redirect_stderr(err):
        with pytest.raises(SystemExit) as exc:
            main(["studio", "--help"])
    assert exc.value.code == 0
    for flag in ("--host", "--port", "--no-browser", "--dev-origin", "--data-dir", "--print-url", "--self-test"):
        assert flag in out.getvalue()


# ---------------------------------------------------------------------------
# An upstream outage is not a refusal
# ---------------------------------------------------------------------------

UNIPROT_TIMEOUT = (
    "ReadTimeout: HTTPSConnectionPool(host='rest.uniprot.org', port=443): "
    "Read timed out. (read timeout=30)"
)
UNIPROT_503 = (
    "HTTPError: 503 Server Error: Service Unavailable for url: "
    "https://rest.uniprot.org/uniprotkb/search?query=ec%3A1.1.1.27&format=json"
)


def test_a_timeout_is_classified_as_the_network_with_its_host() -> None:
    failure = contract.network_failure(UNIPROT_TIMEOUT)
    assert failure == {"host": "rest.uniprot.org", "status": None, "timed_out": True}


def test_an_http_error_status_is_classified_with_its_status() -> None:
    failure = contract.network_failure(UNIPROT_503)
    assert failure == {"host": "rest.uniprot.org", "status": 503, "timed_out": False}


def test_a_refusal_that_only_mentions_the_network_stays_a_refusal() -> None:
    offline = "Refused: offline mode is on, and this request needs the network."
    assert contract.network_failure(offline) is None
    assert contract.outcome_for("structure", 3, "Refused", offline)["meaning"] == "refused"


def test_outcome_for_marks_an_outage_apart_from_a_refusal_and_keeps_the_raw_text() -> None:
    for text in (UNIPROT_TIMEOUT, UNIPROT_503):
        outcome = contract.outcome_for("structure", 3, text.split(":")[0], text, has_result=False)
        assert outcome["meaning"] == "network"
        assert outcome["exit_code"] == 3
        assert outcome["reason"] == text
        assert outcome["network"]["host"] == "rest.uniprot.org"
        assert outcome["has_result"] is False


def test_a_name_refusal_is_never_an_outage() -> None:
    outcome = contract.outcome_for(
        "compose", 3, "x", "ReadTimeout: HTTPSConnectionPool(host='rest.uniprot.org')",
        name_refusal={"kind": "lookup_failed"},
    )
    assert outcome["meaning"] == "refused"
    assert "network" not in outcome
