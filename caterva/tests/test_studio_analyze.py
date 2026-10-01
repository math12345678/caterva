"""The studio's `analyze` kind measures and judges what `caterva analyze` measures and judges.

The native route reads real frames: the 21 frames of replica 1 of a
`caterva md` run on hen lysozyme (1AKI, residues 1-59 and the water at the
active site; fixtures/md/README.md says how they were cut), with that run's
em.gro, and protein.pdb written from the same atoms. A second replica is
the same trajectory copied, only so the run has more than one replica; the
verdicts are whatever the library makes of that. The catalytic residues are
the six M-CSA residues test_faces.py uses, given directly, so nothing asks
the network. The `--no-run` route reads .xvg files written the way
test_analyze.py writes them.

Parity: the same exit code, the report equal to the command's stdout and
to the ANALYSIS.md it writes, and every number in the result equal to the
library value the report was printed from.
"""
from __future__ import annotations

import dataclasses
import gzip
import io
import json
import math
import random
import shutil
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import pytest

from caterva.analyze import __main__ as cli
from caterva.studio import contract
from caterva.studio.adapters import RunContext
from caterva.studio.adapters import analyze as adapter

MD = Path(__file__).parent / "fixtures" / "md"
#: Hen lysozyme's M-CSA catalytic residues, in M-CSA's order (test_faces.py).
LYSOZYME = [(48, "ASP"), (50, "SER"), (46, "ASN"), (59, "ASN"), (52, "ASP"), (35, "GLU")]


class Progress:
    def __init__(self):
        self.stages = []

    def stage(self, key, label, fraction=None):
        self.stages.append(key)

    def log(self, line):
        pass

    def check_cancelled(self):
        pass


def _lysozyme(pdb, chain):
    return list(LYSOZYME), "M-CSA's lysozyme residues, given by the test"


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    monkeypatch.setattr(cli, "catalytic_residues", _lysozyme)


def _ctx(tmp_path):
    d = tmp_path / "data" / "runs" / "20260930-120000-analyze-0badc0de"
    d.mkdir(parents=True)
    return RunContext(d.name, d, tmp_path / "data", Progress())


def _cli(argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = cli.main(argv, catalytic=_lysozyme)
    return code, out.getvalue(), err.getvalue()


def _pdb_from_gro(gro: Path) -> str:
    lines = []
    for i, (resnr, resname, name, xyz) in enumerate(cli._gro_atoms(gro), start=1):
        if resname == "SOL":
            continue
        x, y, z = (float(c) * 10 for c in xyz)
        lines.append(f"ATOM  {i:5d} {name:<4} {resname:>3} A{resnr:4d}    {x:8.3f}{y:8.3f}{z:8.3f}  1.00  0.00"
                     f"           {name[0]}")
    return "\n".join(lines) + "\nEND\n"


@pytest.fixture
def lysozyme_run(tmp_path):
    d = tmp_path / "lyso-md"
    d.mkdir()
    (d / "caterva-setup.json").write_text(json.dumps({"pdb": "1AKI", "chain": "A"}))
    (d / "em.gro").write_bytes(gzip.decompress((MD / "lyso_1aki_res1-59_water.gro.gz").read_bytes()))
    (d / "protein.pdb").write_text(_pdb_from_gro(d / "em.gro"))
    for rep in ("rep1", "rep2"):
        (d / rep).mkdir()
        shutil.copyfile(MD / "lyso_1aki_res1-59_water.xtc", d / rep / "md.xtc")
        (d / rep / "md.tpr").write_text("")  # a replica is finished when both exist; the native route reads no tpr
    return d


def test_the_native_route_on_real_frames_matches_the_command(tmp_path, lysozyme_run):
    d = lysozyme_run
    ctx = _ctx(tmp_path)
    got = adapter.analyze_run({"directory": str(d)}, ctx)
    ours = (d / "ANALYSIS.md").read_text()
    code, out, err = _cli([str(d)])
    assert got.exit_code == code and err == ""
    r = got.result
    assert r["report_markdown"] == out == ours
    assert ctx.progress.stages == ["plan", "measure", "report"]
    a = cli.analyse(d, catalytic=_lysozyme).analysis
    assert r["all_consistent"] is a.all_consistent and r["distances_consistent"] is a.distances_consistent
    assert len(r["distances"]) == len(a.distances) > 0
    for row, x in zip(r["distances"], a.distances):
        assert row["label"] == x.label and row["verdict"] == x.summary.verdict
        assert row["mean"]["value"] == x.summary.mean and row["mean"]["provenance"]["kind"] == "computed"
        assert row["crystal"]["value"] == x.crystal_nm
        assert f"| {x.label} | {x.crystal_nm:.3f} | {x.summary.mean:.3f}" in out
        assert row["change"] == cli.change_word(x.summary.verdict, x.moved)
        assert [p["mean"]["value"] for p in row["per_replica"]] == [p.result.mean for p in x.summary.replicas]
    assert [t["label"] for t in r["angles"]] == [t.label for t in a.angles] and len(r["angles"]) == 24
    for row, t in zip(r["angles"], a.angles):
        assert row["crystal"]["value"] == t.crystal_deg and row["mean"]["value"] == t.summary.mean
    assert len(r["hbonds"]) == len(a.hbonds) and len(r["rotamers"]) == len(a.rotamers)
    assert len(r["faces"]) == len(a.faces) and len(r["water"]) == len(a.water) == 6
    for row, h in zip(r["water"], a.water):
        assert [p["mean"]["value"] for p in row["per_replica"] if p["mean"]] == [
            m for _, m, f in h.per_replica if not math.isnan(f)]
        assert f"| {row['reported']} |" in out
    for row in r["rotamers"]:
        assert f"| {row['reported']} |" in out
    assert r["replicas"] == ["rep1", "rep2"] and r["mode"] == "native" and r["measured"] is True
    assert r["written"] == [str(d / "analyze.sh"), str(d / "chi1.ndx"), str(d / "ANALYSIS.md")]
    assert r["extra"] == {}
    _the_rmsf_profile_is_the_librarys(r["flexibility"], a)
    _the_thresholds_are_the_librarys(r["thresholds"])
    json.dumps(r, allow_nan=False)


def _the_thresholds_are_the_librarys(sent):
    """Each verdict's threshold is the library's constant, labelled a choice."""
    from caterva.analyze import faces, hbonds, rotamers, water
    from caterva.analyze.angles import MOVED_DEG
    from caterva.md import convergence as conv

    def values(section):
        assert all(v["provenance"] == {"kind": "chosen", "by": "default", "reason": v["provenance"]["reason"]}
                   for v in sent[section])
        return [v["value"] for v in sent[section]]

    assert values("replicas") == [conv.DISCARD, conv.MIN_BLOCKS, conv.MIN_EFFECTIVE_SAMPLES,
                                  conv.DISAGREEMENT_FACTOR, conv.CONFIDENCE]
    assert values("distances") == [cli.MOVED_NM] and values("angles") == [MOVED_DEG]
    assert values("hbonds") == [hbonds.MAX_DA_NM, hbonds.MAX_ANGLE_DEG, cli.KEPT, cli.LOST, cli.FORMED, cli.SPLIT]
    assert values("rotamers") == [rotamers.KEPT, rotamers.FLIPPED, rotamers.SPLIT]
    assert values("faces") == [faces.FLAT_DEG, faces.KEPT, faces.SPLIT]
    assert values("water") == [water.WATER_NM, water.WET, water.DRY, water.SPLIT]


def _the_rmsf_profile_is_the_librarys(flex, a):
    """The per-residue RMSF sent is every value the library measured, per
    replica, and the report's pocket and rest means are their means."""
    profile = flex["rmsf"]
    assert profile["unit"] == "nm" and profile["provenance"]["kind"] == "computed"
    assert profile["pocket"] == sorted(a.plan.pocket)
    assert profile["catalytic"] == sorted({s.resnr for s in a.plan.sites})
    assert list(profile["replicas"]) == [n for n, _ in a.flexibility.per_residue]
    pocket = set(a.plan.pocket)
    rest = set(a.plan.rest)
    for (name, per), (_, pv, rv) in zip(a.flexibility.per_residue, a.flexibility.per_replica):
        column = profile["replicas"][name]
        assert len(column) == len(profile["residues"])
        sent = {k: v for k, v in zip(profile["residues"], column) if v is not None}
        assert sent == {k: v for k, v in per.items() if not math.isnan(v)}
        inside = [v for k, v in sent.items() if k in pocket]
        outside = [v for k, v in sent.items() if k in rest]
        assert sum(inside) / len(inside) == pytest.approx(pv, rel=1e-12)
        assert sum(outside) / len(outside) == pytest.approx(rv, rel=1e-12)


def test_script_only_writes_the_script_and_measures_nothing(tmp_path, lysozyme_run):
    d = lysozyme_run
    got = adapter.analyze_run({"directory": str(d), "mode": "script_only"}, _ctx(tmp_path))
    code, out, err = _cli([str(d), "--script-only"])
    assert got.exit_code == code == 0
    assert got.result["report_markdown"] == out and got.result["measured"] is False
    assert got.result["pdb"] == "1AKI" and got.result["counts"]["angles"] == 24
    assert not (d / "ANALYSIS.md").exists()


def _ar1(rng, n, phi, mu, sd):
    x, out = mu, []
    for _ in range(n):
        x = mu + phi * (x - mu) + rng.gauss(0, sd * math.sqrt(1 - phi * phi))
        out.append(x)
    return out


def _atom(serial, name, resname, resnr, x, y, z):
    return (f"ATOM  {serial:5d} {name:<4} {resname:>3} A{resnr:4d}    "
            f"{x:8.3f}{y:8.3f}{z:8.3f}  1.00 20.00           {name[0]}")


def _xvg_run(tmp_path, means, n=4000, phi=0.5, sd=0.005):
    """A finished run as analyze.sh leaves it (test_analyze.py's construction)."""
    rng = random.Random(0)
    d = tmp_path / "xvg-run"
    d.mkdir()
    (d / "caterva-setup.json").write_text(json.dumps({"pdb": "9XYZ", "chain": "A"}))
    (d / "protein.pdb").write_text("\n".join([
        _atom(1, "CA", "HIS", 10, 0.0, 0, 0), _atom(2, "ND1", "HIS", 10, 1.0, 0, 0),
        _atom(3, "NE2", "HIS", 10, 1.0, 2.0, 0), _atom(4, "CA", "ASP", 20, 6.0, 0, 0),
        _atom(5, "OD1", "ASP", 20, 5.0, 0, 0), _atom(6, "OD2", "ASP", 20, 5.0, 2.0, 0),
        _atom(7, "CA", "GLY", 30, 9.0, 0, 0), _atom(8, "CA", "LEU", 90, 40.0, 0, 0)]) + "\nEND\n")
    for r, mu in enumerate(means, start=1):
        rep = d / f"rep{r}"
        rep.mkdir()
        (rep / "md.xtc").write_text("")
        (rep / "md.tpr").write_text("")
        (rep / "catalytic.xvg").write_text("".join(f"{i * 0.001:.3f} {v:.5f}\n"
                                                   for i, v in enumerate(_ar1(rng, n, phi, mu, sd))))
        (rep / "rmsf.xvg").write_text("10 0.05\n20 0.05\n30 0.06\n90 0.20\n")
        (rep / "water.xvg").write_text("0.000 2.000 0.000\n0.001 3.000 1.000\n")
    (d / "water_start.xvg").write_text("0.000 2.000 1.000\n")
    return d


def _two(pdb, chain):
    return [(10, "HIS"), (20, "ASP")], "a test mapping"


@pytest.mark.parametrize("means, kwargs, expected", [
    ([0.40, 0.40, 0.40], {}, 0),
    ([0.40, 0.40], {"n": 400, "phi": 0.995, "sd": 0.05}, 4),
])
def test_the_no_run_route_matches_the_command(tmp_path, monkeypatch, means, kwargs, expected):
    monkeypatch.setattr(cli, "catalytic_residues", _two)
    d = _xvg_run(tmp_path, means, **kwargs)
    got = adapter.analyze_run({"directory": str(d), "mode": "no_run"}, _ctx(tmp_path))
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = cli.main([str(d), "--no-run"], catalytic=_two)
    assert got.exit_code == code == expected
    r = got.result
    assert r["report_markdown"] == out.getvalue()
    assert r["hbonds"] is None and r["rotamers"] == []
    flex = r["flexibility"]
    a = cli.analyse(d, no_run=True, catalytic=_two).analysis
    assert [x["pocket"]["value"] for x in flex["per_replica"]] == [p for _, p, _ in a.flexibility.per_replica]
    m, sd = a.flexibility.spread
    assert flex["ratio_mean"]["value"] == m and flex["ratio_sd"]["value"] == sd
    assert flex["is_result"] is a.distances_consistent
    _the_rmsf_profile_is_the_librarys(flex, a)
    assert flex["rmsf"]["residues"] == [10, 20, 30, 90]
    if expected == 0:
        assert f"Pocket / rest: {m:.2f} ± {sd:.2f}" in r["report_markdown"]
        assert r["distances"][0]["change"] == "held"
    else:
        assert r["distances"][0]["change"] is None and "not yet a result" in r["report_markdown"]


def test_the_gromacs_route_without_gromacs_is_the_commands_refusal(tmp_path, lysozyme_run, monkeypatch):
    monkeypatch.setenv("GMX", str(tmp_path / "no-such-gmx"))
    got = adapter.analyze_run({"directory": str(lysozyme_run), "mode": "gromacs"}, _ctx(tmp_path))
    code, out, err = _cli([str(lysozyme_run), "--gromacs"])
    assert got.exit_code == code == 3 and got.result is None
    assert got.refusal == err.strip() and "GROMACS not found" in got.refusal


def test_gromacs_is_looked_for_where_a_gui_app_cannot_see_it(monkeypatch, tmp_path):
    monkeypatch.delenv("GMX", raising=False)
    monkeypatch.setenv("PATH", str(tmp_path))
    fake = tmp_path / "gmx-elsewhere"
    fake.write_text("#!/bin/sh\n")
    fake.chmod(0o755)
    monkeypatch.setattr(adapter, "GMX_FALLBACKS", (str(tmp_path / "absent"), str(fake)))
    assert adapter.find_gmx() == str(fake)
    monkeypatch.setattr(adapter, "GMX_FALLBACKS", ())
    assert adapter.find_gmx() is None


def test_a_folder_that_is_not_a_run_is_a_refusal(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    got = adapter.analyze_run({"directory": str(empty)}, _ctx(tmp_path))
    code, out, err = _cli([str(empty)])
    assert got.exit_code == code == 3 and got.refusal == err.strip()


@pytest.mark.parametrize("request_, field, needle", [
    ({"directory": "relative/run"}, "directory", "must be an absolute path"),
    ({"directory": "/no/such/run/anywhere"}, "directory", "does not exist"),
    ({"directory": "/", "mode": "fast"}, "mode", "mode must be one of"),
    ({"directory": "/", "gmx": "/bin/sh"}, "gmx", "not a key this kind takes"),
])
def test_a_malformed_request_names_its_field(request_, field, needle):
    with pytest.raises(contract.Malformed, match=needle) as e:
        adapter.analyze_argv(request_)
    assert e.value.field == field


def test_a_file_where_a_folder_is_needed_is_malformed(tmp_path):
    (tmp_path / "md.xtc").write_text("")
    with pytest.raises(contract.Malformed, match="is not a directory"):
        adapter.analyze_argv({"directory": str(tmp_path / "md.xtc")})


def test_a_section_added_on_another_branch_is_passed_through_not_dropped():
    newer = dataclasses.make_dataclass("NewerAnalysis", [("exposure", list, dataclasses.field(default_factory=list))],
                                       bases=(cli.Analysis,))
    p = cli.plan([], [])
    a = newer("1AKI", "A", "test", p, exposure=[{"residue": "Glu35", "fraction": 0.5}])
    assert adapter.extra_sections(a) == {"exposure": [{"residue": "Glu35", "fraction": 0.5}]}
