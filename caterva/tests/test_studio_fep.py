"""The studio's `fep.status` and `complex.check` kinds read what `caterva fep --summarise` and `caterva complex --check` read.

The FEP run is the one test_fep.py writes: a real `caterva fep` setup held
to the committed BRENDA Ki page for human LDH-A (Tests/fixtures/
brenda_ldh_ki_fixture.html), with each leg's `gmx bar` log written as that
test writes them. The pose checks use the constructed systems of
test_complex.py, whose answers are known by construction. Neither runs
GROMACS: the studio only reads these runs (the adapter's docstring says why).
"""
from __future__ import annotations

import io
import json
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import numpy as np
import pytest

from caterva.fep import complex as cx
from caterva.studio import contract
from caterva.studio.adapters import RunContext, load_registry
from caterva.studio.adapters import fep as adapter
from test_complex import _rot, _system, _write_gro
from test_fep import _finish, run as write_fep_setup


class Progress:
    def __init__(self):
        self.stages = []

    def stage(self, key, label, fraction=None):
        self.stages.append(key)

    def log(self, line):
        pass

    def check_cancelled(self):
        pass


def _ctx(tmp_path, kind):
    d = tmp_path / "data" / "runs" / f"20260930-120000-{kind}-0badc0de"
    d.mkdir(parents=True)
    return RunContext(d.name, d, tmp_path / "data", Progress())


def _cli(main, argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = main(argv)
    return code, out.getvalue(), err.getvalue()


def _fep_run(tmp_path, replicas):
    write_fep_setup(tmp_path)
    out = tmp_path / "out"
    corr = json.loads((out / "caterva-fep.json").read_text())["restraint"]["correction_kj"]
    target_kj, solv = -8.4 * 4.184, 20.0
    _finish(out, [solv + corr - target_kj + d for d in (-0.4, 0.0, 0.4)][:replicas], [solv] * replicas)
    return out


@pytest.mark.parametrize("replicas, expected", [(3, 0), (1, 4)])
def test_the_status_matches_the_command(tmp_path, replicas, expected):
    from caterva.fep.__main__ import main, read_summary

    out = _fep_run(tmp_path, replicas)
    ctx = _ctx(tmp_path, "fep-status")
    got = adapter.status_run({"directory": str(out)}, ctx)
    code, printed, err = _cli(main, ["--summarise", str(out)])
    assert got.exit_code == code == expected
    r = got.result
    assert r["report_text"] == printed
    assert ctx.progress.stages == ["read", "judge"]
    s, _ = read_summary(out)
    assert [row["dg_kcal"]["value"] for row in r["replicas"]] == [x.dg_kcal for x in s.replicas]
    assert [row["complex_kj"]["value"] for row in r["replicas"]] == [x.complex_kj for x in s.replicas]
    assert [row["complex_err_kj"]["value"] for row in r["replicas"]] == [x.complex_err_kj for x in s.replicas]
    rec = s.record
    assert r["band_low"]["value"] == rec["target"]["band_kcal"][0]
    assert r["band_high"]["value"] == rec["target"]["band_kcal"][1]
    assert r["temperature_k"]["value"] == rec["temperature_k"]
    assert r["temperature_k"]["provenance"]["kind"] == "measured"  # the Ki's assay temperature, 310.15 K
    assert r["temperature_k"]["provenance"]["citation"]["text"] == ", ".join(
        f"BRENDA ref {x}" for x in rec["target"]["references"])
    assert r["restraint_correction"]["value"] == rec["restraint"]["correction_kj"] / 4.184
    if expected == 0:
        assert r["verdict"]["word"] == s.verdict.word == "agrees"
        assert r["computed"]["value"] == s.mean and r["sigma"]["value"] == s.sigma
        assert f"COMPUTED  {s.mean:.2f} ± {s.sigma:.2f} kcal/mol" in printed
        assert r["not_a_result"] is None
    else:
        assert r["verdict"] is None and r["computed"] is None
        assert r["not_a_result"].startswith("NOT A RESULT: 1 finished replica(s)")
    assert r["replicas_planned"] == 3
    json.dumps(r, allow_nan=False)


def test_a_folder_fep_did_not_write_is_a_refusal(tmp_path):
    from caterva.fep.__main__ import main

    got = adapter.status_run({"directory": str(tmp_path)}, _ctx(tmp_path, "fep-status"))
    code, printed, err = _cli(main, ["--summarise", str(tmp_path)])
    assert got.exit_code == code == 3 and got.result is None and got.refusal == err.strip()


# --- complex.check ----------------------------------------------------------------------------------


@pytest.mark.parametrize("moved, expected", [(False, 0), (True, 4)])
def test_the_pose_check_matches_the_command(tmp_path, moved, expected):
    start = _system()
    _write_gro(tmp_path / "boxed.gro", start)
    if moved:
        after = [(r, n, x + (np.array([0.3, 0, 0]) if r == "LIG" else 0)) for r, n, x in start]
    else:
        R, t = _rot([1, 1, 0], 0.4), np.array([0.5, -0.2, 0.3])
        after = [(r, n, x @ R + t) for r, n, x in start]
    _write_gro(tmp_path / "npt.gro", after)
    got = adapter.check_run({"directory": str(tmp_path), "ligand": "LIG"}, _ctx(tmp_path, "complex-check"))
    code, printed, err = _cli(cx.main, ["--check", str(tmp_path), "--ligand", "LIG"])
    assert got.exit_code == code == expected and err == ""
    r = got.result
    assert r["report_text"] == printed and r["kept"] is (expected == 0)
    rmsd, ca, n = cx.check(tmp_path, "LIG")
    assert r["values"]["ligand_rmsd"]["value"] == rmsd and r["values"]["ca_rmsd"]["value"] == ca
    assert r["ca_atoms"] == n and r["frames"] is None
    assert r["values"]["centroid_shift"]["value"] == cx.centroid_shift(tmp_path, "LIG")
    assert r["values"]["kept_threshold"]["value"] == cx.POSE_KEPT_NM
    assert f"{rmsd * 10:.2f} A from the crystal pose" in printed


def test_output_from_another_build_is_a_refusal(tmp_path):
    _write_gro(tmp_path / "boxed.gro", _system())
    _write_gro(tmp_path / "npt.gro", [("GLY", "N", np.zeros(3))] * 10)
    got = adapter.check_run({"directory": str(tmp_path), "ligand": "LIG"}, _ctx(tmp_path, "complex-check"))
    code, printed, err = _cli(cx.main, ["--check", str(tmp_path), "--ligand", "LIG"])
    assert got.exit_code == code == 3 and got.refusal == err.strip() and "not this build" in got.refusal


@pytest.mark.parametrize("request_, field", [
    ({"directory": "/"}, "ligand"),
    ({"directory": "/", "ligand": "LIG X"}, "ligand"),
    ({"directory": "/", "ligand": "LIG", "ligand_itp": "/tmp/lig.itp"}, "ligand_itp"),
    ({"directory": "relative", "ligand": "LIG"}, "directory"),
])
def test_a_malformed_check_names_its_field(request_, field):
    with pytest.raises(contract.Malformed) as e:
        adapter.check_argv(request_)
    assert e.value.field == field


def test_both_kinds_are_registered_and_need_nothing_beyond_the_engine():
    registry = load_registry()
    assert registry.get("fep.status").needs == () and registry.get("complex.check").needs == ()
    assert registry.get("fep.status").argv({"directory": "/"}) == ["--summarise", str(Path("/").resolve())]
