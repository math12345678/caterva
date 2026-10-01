"""The studio's `prepare` kind gives what `caterva prepare` gives, and accepts only the paths it should.

The entries are real (fixtures/prepare/: 1I10, human LDH-A, one clean
chain; 1L63, T4 lysozyme, every chain blocked) and their UniProt sequences
committed beside them; `caterva prepare`'s own fetch is answered from those
files, so the command and the adapter read the same bytes offline.
"""
from __future__ import annotations

import gzip
import io
import json
import os
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import pytest

from caterva.studio import contract
from caterva.studio.adapters import RunContext
from caterva.studio.adapters import prepare as adapter

FIX = Path(__file__).parent / "fixtures" / "prepare"


class Progress:
    def __init__(self):
        self.stages = []

    def stage(self, key, label, fraction=None):
        self.stages.append(key)

    def log(self, line):
        pass

    def check_cancelled(self):
        pass


def _cif(pid):
    with gzip.open(FIX / f"{pid}.trimmed.cif.gz", "rt") as fh:
        return fh.read()


@pytest.fixture(autouse=True)
def recorded(monkeypatch, tmp_path):
    from caterva.prepare import __main__ as prepare

    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))

    def fetch(url):
        name = url.rsplit("/", 1)[-1]
        if name.endswith(".cif"):
            return _cif(name[:-4])
        return (FIX / name).read_text()

    monkeypatch.setattr(prepare, "live_fetch", lambda timeout=60.0: fetch)


def _local(tmp_path, pid):
    p = tmp_path / f"{pid}.cif"
    p.write_text(_cif(pid))
    return str(p)


def _ctx(tmp_path):
    d = tmp_path / "runs" / "20260930-120000-prepare-0badc0de"
    d.mkdir(parents=True)
    return RunContext(d.name, d, tmp_path, Progress())


def _cli(argv):
    from caterva.prepare.__main__ import main

    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = main(argv)
    return code, out.getvalue(), err.getvalue()


@pytest.mark.parametrize("entry, ph, expected", [("1I10", 7.4, 0), ("1L63", None, 4), ("local:1I10", 6.0, 0)])
def test_the_audit_matches_the_command(tmp_path, entry, ph, expected):
    from caterva.prepare.__main__ import clean_chains

    entry = _local(tmp_path, entry.split(":")[1]) if entry.startswith("local:") else entry
    request = {"entry": entry} | ({"ph": ph} if ph is not None else {})
    ctx = _ctx(tmp_path)
    got = adapter.prepare_run(request, ctx)
    json_path = tmp_path / "audit.json"
    code, out, err = _cli(adapter.prepare_argv(request) + ["--json", str(json_path)])
    assert got.exit_code == code == expected and err == ""
    r = got.result
    assert r["report_markdown"] == out
    assert r["audit"] == json.loads(json_path.read_text())
    assert ctx.progress.stages == ["fetch", "audit"]
    a = r["audit"]
    assert r["clean_chains"] == [s["chain"] for s in a["chain_summary"]
                                 if s["blocks"] == 0 and s["catalytic_intact"]]
    assert r["clean"] is (expected == 0)
    assert len(r["findings"]) == len(a["findings"])
    for row, f in zip(r["findings"], a["findings"]):
        assert row["severity"] == f["severity"] and row["what"] == f["what"]
        if f["distance"] is None:
            assert row["distance"] is None
        else:
            assert row["distance"]["value"] == f["distance"]
            assert row["distance"]["provenance"]["kind"] == "computed"
            assert f"| {f['distance']:.1f} |" in out
    if a["resolution"] is not None:
        assert r["resolution"]["value"] == a["resolution"] and f"{a['resolution']} Å" in out
    assert r["active_site_radius"]["provenance"] == {"kind": "chosen", "by": "default",
                                                     "reason": "a chosen cutoff, not a physical boundary "
                                                               "(caterva prepare)"}
    assert clean_chains  # the exit rule the adapter used is the command's
    json.dumps(r, allow_nan=False)


def test_the_protonation_table_is_the_reports_rows(tmp_path):
    got = adapter.prepare_run({"entry": "1I10", "ph": 7.4}, _ctx(tmp_path))
    rows = got.result["protonation"]
    assert rows, "1I10 has titratable residues at the active site"
    report = got.result["report_markdown"]
    for row in rows:
        line = next(x for x in report.splitlines() if x.startswith(f"| {row['residue']} |"))
        assert f"| {row['distance']['value']:.1f} | {row['at_ph']} |" in line
        assert row["state"] in line
        if row["pka"] is not None:
            assert row["pka"]["provenance"]["kind"] == "measured"
            assert "10.1002/pro.19" in row["pka"]["provenance"]["citation"]["text"]
            assert f"{row['protonated']['value']:.0%} protonated at pH 7.4" in row["at_ph"]
    assert got.result["ph"]["value"] == 7.4 and got.result["ph"]["provenance"]["by"] == "user"


def test_without_a_ph_there_is_no_protonation_table(tmp_path):
    got = adapter.prepare_run({"entry": "1I10"}, _ctx(tmp_path))
    assert got.result["protonation"] is None and got.result["ph"] is None


def test_an_entry_the_pdb_does_not_have_is_a_refusal_with_no_result(tmp_path, monkeypatch):
    from caterva.prepare import __main__ as prepare

    def fetch(url):
        raise prepare.PrepareError(f"not found: {url}")

    monkeypatch.setattr(prepare, "live_fetch", lambda timeout=60.0: fetch)
    got = adapter.prepare_run({"entry": "9ZZZ"}, _ctx(tmp_path))
    code, out, err = _cli(["9ZZZ"])
    assert got.exit_code == code == 3 and got.result is None
    assert got.refusal == err.strip() == "caterva prepare: not found: https://files.rcsb.org/download/9ZZZ.cif"


def test_no_network_is_a_refusal(tmp_path, monkeypatch):
    import requests
    from caterva.prepare import __main__ as prepare

    def down(url):
        raise requests.ConnectionError("network is unreachable")

    monkeypatch.setattr(prepare, "live_fetch", lambda timeout=60.0: down)
    got = adapter.prepare_run({"entry": "1I10"}, _ctx(tmp_path))
    assert got.exit_code == 3 and got.refusal.startswith("caterva prepare: could not reach the PDB or UniProt")


# --- what a request may name ---------------------------------------------------------------------


def test_a_local_file_is_recorded_resolved(tmp_path):
    real = Path(_local(tmp_path, "1I10"))
    link = tmp_path / "link.cif"
    os.symlink(real, link)
    assert adapter.prepare_argv({"entry": str(link)}) == [str(real.resolve())]


@pytest.mark.parametrize("make, needle", [
    (lambda d: str(d / "missing.cif"), "does not exist"),
    (lambda d: str(d), "not a regular file"),
    (lambda d: str(d / ".." / d.name / "notes.txt"), "is not a .cif or .mmcif file"),
    (lambda d: "relative/path.cif", "must be an absolute path"),
    (lambda d: "../../etc/passwd", "must be an absolute path"),
    (lambda d: "/etc/../etc/passwd", "is not a .cif or .mmcif file"),
    (lambda d: "/tmp/a\x00b.cif", "NUL"),
    (lambda d: "/" + "a" * 5000 + ".cif", "longer than"),
    (lambda d: "not an entry", "neither a PDB id"),
])
def test_a_path_that_breaks_the_rules_is_malformed_under_its_field(tmp_path, make, needle):
    (tmp_path / "notes.txt").write_text("not a structure")
    with pytest.raises(contract.Malformed, match=needle) as e:
        adapter.prepare_argv({"entry": make(tmp_path)})
    assert e.value.field == "entry"


@pytest.mark.parametrize("request_, field", [
    ({"entry": "1I10", "ph": "7"}, "ph"),
    ({"entry": "1I10", "ph": True}, "ph"),
    ({"entry": "1I10", "out": "/tmp/x.md"}, "out"),
    ({"entry": "1I10", "json": "/tmp/x.json"}, "json"),
    ({"entry": "1I10", "no_cache": "yes"}, "no_cache"),
])
def test_keys_the_kind_does_not_take_or_wrong_types_are_malformed(request_, field):
    with pytest.raises(contract.Malformed) as e:
        adapter.prepare_argv(request_)
    assert e.value.field == field
