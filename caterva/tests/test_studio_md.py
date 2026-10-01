"""The studio's `md.setup` and `md.summarise` kinds write and read what `caterva md` writes and reads.

A setup is compared file by file with the command's own setup of the same
question, and its printed lines with the command's stdout. The setup that
takes its conditions from the kinetics replays the committed BRENDA page
and HTTP answers for human hexokinase (Tests/fixtures/recorded/, the
variables set here, in a test, as Tests/test_recorded_env_is_test_only.py
requires): the setup does not check that the entry it names is that
enzyme, so the PDB id only names the files. The summaries read replicas
written as the convergence tests write them (caterva/tests/test_md_convergence.py).
"""
from __future__ import annotations

import io
import math
import random
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import pytest

from caterva.studio import contract
from caterva.studio.adapters import RunContext, load_registry
from caterva.studio.adapters import md as adapter

ROOT = Path(__file__).resolve().parents[2]
RECORDED = ROOT / "Tests" / "fixtures" / "recorded"


class Progress:
    def __init__(self):
        self.stages = []

    def stage(self, key, label, fraction=None):
        self.stages.append(key)

    def log(self, line):
        pass

    def check_cancelled(self):
        pass


def _ctx(tmp_path, kind="md-setup"):
    d = tmp_path / "data" / "runs" / f"20260930-120000-{kind}-0badc0de"
    d.mkdir(parents=True)
    return RunContext(d.name, d, tmp_path / "data", Progress())


def _cli(argv):
    from caterva.md.__main__ import main

    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = main(argv)
    return code, out.getvalue(), err.getvalue()


def _files(d: Path):
    return {str(p.relative_to(d)): p.read_text() for p in sorted(d.rglob("*")) if p.is_file()}


def _same_setup(tmp_path, request):
    ours, theirs = tmp_path / "ours", tmp_path / "theirs"
    got = adapter.setup_run(request | {"out": str(ours)}, _ctx(tmp_path))
    argv = adapter.setup_argv(request | {"out": str(theirs)})
    code, out, err = _cli(argv)
    assert _files(ours) == _files(theirs)
    assert got.result["report_text"] == out.replace(str(theirs), str(ours))
    return got, code


def test_a_setup_writes_the_commands_files_and_labels_every_default(tmp_path):
    from caterva.md.setup import Conditions, MdSetup

    got, code = _same_setup(tmp_path, {"pdb": "1i10", "chain": "A"})
    assert got.exit_code == code == 0 and got.refusal is None
    r = got.result
    library = MdSetup(pdb_id="1I10", chain="A", conditions=Conditions())
    assert r["files"] == list(library.files())
    assert r["parameters"] == [{"name": p.name, "value": p.value, "origin": p.origin, "source": p.source}
                               for p in library.parameters]
    assert r["temperature"]["value"] == 298.15
    assert r["temperature"]["provenance"] == {"kind": "chosen", "by": "default",
                                              "reason": "chosen: 25 C, no measured value supplied"}
    assert r["ph"] is None
    assert r["ns"]["value"] == 10.0 and r["ns"]["provenance"]["by"] == "default"
    assert r["seeds"] == [20260927, 20260928, 20260929] and r["replicas"] == 3
    assert r["provenance_markdown"] == (tmp_path / "ours" / "PROVENANCE.md").read_text()
    assert "bash " in r["report_text"] and "--summarise" in r["report_text"]


def test_what_the_person_chose_is_labelled_theirs(tmp_path):
    got, code = _same_setup(tmp_path, {"pdb": "1I10", "temperature_k": 310.0, "ph": 7.0, "ns": 2.5,
                                       "replicas": 1, "seed": 7})
    assert got.exit_code == code == 0
    r = got.result
    assert r["temperature"]["value"] == 310.0 and r["temperature"]["provenance"]["by"] == "user"
    assert r["ph"]["value"] == 7.0 and r["ph"]["provenance"]["by"] == "user"
    assert r["ns"]["value"] == 2.5 and r["ns"]["provenance"]["by"] == "user"
    assert r["seeds"] == [7]
    assert "One replica is one sample" in r["report_text"]


def test_measured_conditions_carry_their_citation(tmp_path, monkeypatch):
    monkeypatch.setenv("CATERVA_BRENDA_RECORDED", str(RECORDED))
    monkeypatch.setenv("CATERVA_HTTP_RECORDED", str(RECORDED / "http"))
    got, code = _same_setup(tmp_path, {"pdb": "1I10", "chain": "A", "subject": "2.7.1.1", "organism": "human",
                                       "substrate": "glucose"})
    assert got.exit_code == code == 0
    t, ph = got.result["temperature"], got.result["ph"]
    assert t["value"] == pytest.approx(303.15) and t["provenance"]["kind"] == "measured"
    assert t["provenance"]["citation"]["text"] == "BRENDA ref 641068"
    # The Measurement says it came through the literature layer, not which
    # registry: no link is guessed from the citation's text.
    assert t["provenance"]["citation"]["via"] == "literature" and "url" not in t["provenance"]["citation"]
    assert t["provenance"]["commentary"] == "30°C, pH 7.5, wild-type"
    assert t["provenance"]["conditions"]["temperature_c"] == 30.0
    assert ph["value"] == 7.5 and ph["provenance"]["kind"] == "measured"
    assert got.result["note"] == "conditions from BRENDA ref 641068, the assay behind Km = 6 mM (Homo sapiens)"


def test_the_default_folder_is_inside_the_run(tmp_path):
    argv = adapter.setup_argv({"pdb": "1I10"})
    assert argv[-2:] == ["--out", f"{adapter.RUN_DIR_PLACEHOLDER}/md-setup"]
    ctx = _ctx(tmp_path)
    got = adapter.setup_run({"pdb": "1I10"}, ctx)
    assert got.result["out_dir"] == str(ctx.run_dir / "md-setup")
    assert (ctx.run_dir / "md-setup" / "run.sh").is_file()


@pytest.mark.parametrize("make, needle", [
    (lambda d: "relative/out", "must be an absolute path"),
    (lambda d: str(d / "missing-parent" / "out"), "does not exist"),
    (lambda d: str(d / "a-file"), "exists and is not a directory"),
    (lambda d: str(d / "full"), "holds files and no previous `caterva md` setup"),
    (lambda d: str(d / "data" / "elsewhere"), "inside the studio's workspace"),
])
def test_an_output_folder_that_breaks_the_rules_is_refused_before_anything_is_written(tmp_path, make, needle):
    (tmp_path / "a-file").write_text("x")
    (tmp_path / "full").mkdir()
    (tmp_path / "full" / "notes.txt").write_text("someone's work")
    ctx = _ctx(tmp_path)
    with pytest.raises(contract.Malformed, match=needle) as e:
        adapter.setup_run({"pdb": "1I10", "out": make(tmp_path)}, ctx)
    assert e.value.field == "out"
    assert (tmp_path / "full" / "notes.txt").read_text() == "someone's work"
    assert not (tmp_path / "data" / "elsewhere").exists()


def test_a_previous_setup_may_be_rewritten(tmp_path):
    adapter.setup_run({"pdb": "1I10", "out": str(tmp_path / "again")}, _ctx(tmp_path))
    assert adapter.setup_argv({"pdb": "1I10", "out": str(tmp_path / "again")})[-1] == str(tmp_path / "again")


@pytest.mark.parametrize("request_, needle", [
    ({"pdb": "1I1"}, "is not a PDB id"),
    ({"pdb": "1I10", "replicas": 0}, "--replicas must be at least 1"),
    ({"pdb": "1I10", "subject": "2.7.1.1"}, "needs both --subject and --substrate"),
    ({"pdb": "1I10", "ns": "10"}, "'ns' must be a finite number"),
    ({"pdb": "1I10", "seed": 1.5}, "'seed' must be a whole number"),
    ({"pdb": "1I10", "summarise": "/tmp"}, "not a key this kind takes"),
])
def test_a_malformed_setup_is_refused_in_the_commands_words(request_, needle):
    with pytest.raises(contract.Malformed, match=needle):
        adapter.setup_argv(request_)


# --- summarise ------------------------------------------------------------------------------------


def _ar1(rng, n, phi, mu, sd):
    x, out = mu, []
    for _ in range(n):
        x = mu + phi * (x - mu) + rng.gauss(0, sd * math.sqrt(1 - phi * phi))
        out.append(x)
    return out


def _write_run(d: Path, series):
    head = '# gmx rms\n@    title "RMSD"\n@    xaxis  label "Time (ns)"\n'
    for i, values in enumerate(series, start=1):
        (d / f"rep{i}").mkdir(parents=True)
        (d / f"rep{i}" / "rmsd.xvg").write_text(head + "".join(f"{k * 0.01:.3f}  {v:.6f}\n"
                                                              for k, v in enumerate(values)))
    return d


@pytest.mark.parametrize("phi, n, expected", [(0.5, 4000, 0), (0.995, 400, 4)])
def test_a_summary_matches_the_command(tmp_path, phi, n, expected):
    from caterva.md.convergence import collect, summarise

    rng = random.Random(0)
    d = _write_run(tmp_path / "run", [_ar1(rng, n, phi, 0.20, 0.02 if phi < 0.9 else 0.05) for _ in range(3)])
    got = adapter.summarise_run({"directory": str(d)}, _ctx(tmp_path, "md-summarise"))
    written = (d / "CONVERGENCE.md").read_text()
    code, out, err = _cli(["--summarise", str(d)])
    assert got.exit_code == code == expected
    r = got.result
    assert r["report_markdown"] == out == written
    s = summarise(collect(d), "backbone RMSD from the starting structure", "nm")
    assert r["verdict"] == s.verdict and r["mean"]["value"] == s.mean
    assert r["spread"]["value"] == s.spread and r["ci95"]["value"] == s.ci95
    for row, rep in zip(r["replicas"], s.replicas):
        assert row["mean"]["value"] == rep.result.mean and row["error"]["value"] == rep.result.sem
        assert row["frames"] == rep.frames and row["kept"] == rep.kept
        assert row["mean"]["provenance"]["kind"] == "computed"
    assert r["written"] == str(d / "CONVERGENCE.md")


def test_a_folder_that_has_not_run_is_a_refusal(tmp_path):
    got = adapter.summarise_run({"directory": str(tmp_path)}, _ctx(tmp_path, "md-summarise"))
    code, out, err = _cli(["--summarise", str(tmp_path)])
    assert got.exit_code == code == 3 and got.result is None and got.refusal == err.strip()


@pytest.mark.parametrize("value, needle", [
    ("relative/run", "must be an absolute path"),
    ("/no/such/folder/anywhere", "does not exist"),
])
def test_a_summary_of_a_path_that_is_not_a_folder_is_malformed(tmp_path, value, needle):
    with pytest.raises(contract.Malformed, match=needle):
        adapter.summarise_argv({"directory": value})
    (tmp_path / "f").write_text("x")
    with pytest.raises(contract.Malformed, match="is not a directory"):
        adapter.summarise_argv({"directory": str(tmp_path / "f")})


def test_both_kinds_are_registered():
    registry = load_registry()
    assert registry.get("md.setup").cli_prefix == registry.get("md.summarise").cli_prefix == ("caterva", "md")
