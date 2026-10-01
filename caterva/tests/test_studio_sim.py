"""Caterva Studio's `sim` kind against `caterva sim ssa`, seeded.

The adapter calls the command's own three functions (`simulate`,
`expectation`, `report`), so for the same request and seed: the report is
the command's stdout, every row of the event table is the engine's row
(and the CSV artefact is what `--out` writes), the final counts are the
table's last row, and the ODE expectation is the number the command
formats into its last line. The bimolecular case is tested with an
explicit k because the command's --k default (0.5) contradicts its help
(0.005) for that reaction; the page always sends k.
"""
from __future__ import annotations

import csv
import io

import pytest

from caterva.cli import build_parser, expectation, main, simulate
from caterva.studio import contract
from caterva.studio.adapters import sim as adapter
from studio_kinetics_offline import Recorder, context, run_cli

DECAY = {"seed": 42, "a0": 200, "k": 0.3, "end": 10.0}
ASSOCIATION = {"seed": 7, "bimolecular": True, "a0": 120, "b0": 80, "k": 0.005, "end": 5.0}


def both(request, tmp_path):
    argv = adapter.argv(request)
    code, out, err = run_cli(main, argv)
    outcome = adapter.run(request, context(tmp_path))
    return code, out, err, outcome


@pytest.mark.parametrize("request_", [DECAY, ASSOCIATION], ids=["decay", "association"])
def test_the_report_is_the_commands_stdout(request_, tmp_path):
    code, out, err, outcome = both(request_, tmp_path)
    assert code == outcome.exit_code == 0 and err == ""
    assert outcome.result["report_text"] + "\n" == out


@pytest.mark.parametrize("request_", [DECAY, ASSOCIATION], ids=["decay", "association"])
def test_every_number_is_the_engines(request_, tmp_path):
    outcome = adapter.run(request_, context(tmp_path))
    args = build_parser("caterva sim").parse_args(adapter.argv(request_))
    run = simulate(args)
    summary = expectation(args, run)
    result = outcome.result
    assert result["columns"] == list(run.colnames)
    assert result["rows"] == len(run.data) and result["every"] == 1
    for j, name in enumerate(run.colnames):
        assert result["series"][name] == [row[j] for row in run.data]
    assert result["events"] == summary["events"] == len(run.data) - 2
    assert result["expected"]["value"] == summary["expected"]
    assert result["expected"]["provenance"]["kind"] == "computed"
    for name in run.colnames[1:]:
        assert result["final"][name]["value"] == run.final(name) == run.data[-1][list(run.colnames).index(name)]
    # The command prints the expectation to one decimal: the same string.
    assert f"{result['expected']['value']:.1f}" in result["report_text"].splitlines()[-1]


def test_the_csv_artefact_is_every_row(tmp_path):
    outcome = adapter.run(DECAY, context(tmp_path))
    (artifact,) = outcome.artifacts
    rows = list(csv.reader(io.StringIO(artifact.content.decode("utf-8"))))
    assert rows[0] == outcome.result["columns"]
    assert len(rows) - 1 == outcome.result["rows"]
    assert [float(r[0]) for r in rows[1:]] == outcome.result["series"]["time"]


def test_a_given_input_is_chosen_by_the_user_and_an_absent_one_by_the_default(tmp_path):
    outcome = adapter.run({"seed": 1}, context(tmp_path))
    parameters = outcome.result["parameters"]
    defaults = build_parser("caterva sim").parse_args(["ssa"])
    for name in ("a0", "k", "end"):
        assert parameters[name]["value"] == getattr(defaults, name)
        assert parameters[name]["provenance"] == {
            "kind": "chosen", "by": "default", "reason": f"the default of caterva sim ssa --{name}"}
    given = adapter.run(DECAY, context(tmp_path)).result["parameters"]
    assert given["k"]["value"] == 0.3 and given["k"]["provenance"] == {"kind": "chosen", "by": "user"}


def test_the_same_seed_gives_the_same_trajectory(tmp_path):
    a = adapter.run(DECAY, context(tmp_path)).result
    b = adapter.run(DECAY, context(tmp_path)).result
    assert a["series"] == b["series"] and a["seed"] == 42


def test_progress_has_the_simulate_stage(tmp_path):
    progress = Recorder()
    adapter.run(DECAY, context(tmp_path, progress))
    assert progress.stages() == ["simulate"]


def test_argv_is_ssa_first_and_never_out():
    argv = adapter.argv(ASSOCIATION)
    assert argv[0] == "ssa" and "--bimolecular" in argv
    assert "--k=0.005" in argv and "--seed=7" in argv
    assert not any(a.startswith("--out") for a in argv)


@pytest.mark.parametrize("request_, field", [
    ({}, "seed"),
    ({"seed": None}, "seed"),
    ({"seed": 1, "a0": 2.5}, "a0"),
    ({"seed": 1, "k": "fast"}, "k"),
    ({"seed": 1, "bimolecular": "yes"}, "bimolecular"),
    ({"seed": 1, "out": "x.csv"}, "out"),
])
def test_a_malformed_request_names_its_field(request_, field):
    with pytest.raises(contract.Malformed) as caught:
        adapter.argv(request_)
    assert caught.value.field == field


def test_parameters_the_engine_refuses_are_refused_in_its_words():
    with pytest.raises(contract.Malformed) as caught:
        adapter.argv({"seed": 1, "k": -1.0})
    code, _, err = run_cli(main, ["ssa", "--k=-1.0", "--seed=1"])
    assert code == 1
    assert err.strip() == str(caught.value)


def test_the_kind_is_registered():
    from caterva.studio.adapters import Registry

    registry = Registry()
    adapter.register(registry)
    spec = registry.get("sim")
    assert spec.needs == () and spec.cli_prefix == ("caterva", "sim") and spec.serial
