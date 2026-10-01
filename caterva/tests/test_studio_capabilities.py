"""What the installation can do, decided by looking: each part of /api/capabilities.

Every outside effect (importing the literature layer, finding and running
`gmx`, contacting the five hosts) is handed to CapabilityProbe as a
function, so each answer and each failure can be produced here on purpose
and its wording checked: the page shows these reasons as they are
(docs/studio/CONTRACT.md section 10). One test runs the real probe against
this checkout's real literature layer and registry.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import List

import pytest

from caterva.studio.adapters import AdapterOutcome, AdapterSpec, Registry, load_registry
from caterva.studio.capabilities import (
    GMX_FALLBACKS, NETWORK_HOSTS, NOT_BUILT_YET, OFFLINE_REASON, CapabilityProbe, parse_gmx_version,
)
from caterva.studio.contract import RUN_KINDS, Capabilities
from caterva.studio.static_files import StaticSite
from caterva.studio.workspace import DEFAULT_SETTINGS, Workspace

GMX_OUTPUT = (
    "                      :-) GROMACS - gmx, 2025.3-Homebrew (-:\n\n"
    "Executable:   /opt/homebrew/bin/../Cellar/gromacs/2025.3/bin/gmx\n"
    "GROMACS version:     2025.3-Homebrew\n"
    "Precision:           mixed\n"
)


def probe(tmp_path: Path, *, settings=None, environ=None, which=None, run=None, head=None, literature=None,
          find_spec=None, registry=None, is_executable=None) -> CapabilityProbe:
    ws = Workspace(tmp_path / "data")
    ws.ensure()
    current = dict(DEFAULT_SETTINGS, **(settings or {}))
    return CapabilityProbe(
        registry=registry or Registry(), workspace=ws, static_site=StaticSite(tmp_path / "static"),
        dev_origin=None, settings=lambda: current, environ=environ if environ is not None else {},
        which=which or (lambda name: None),
        run=run or (lambda *a, **k: SimpleNamespace(returncode=0, stdout=GMX_OUTPUT, stderr="")),
        head=head or (lambda host, timeout: None), literature_import=literature or (lambda: None),
        find_spec=find_spec or (lambda name: None), clock=lambda: "2026-09-30T12:00:00.000Z",
        is_executable=is_executable or (lambda path: False),
    )


def test_the_snapshot_has_exactly_the_contracts_keys(tmp_path):
    snapshot = probe(tmp_path).snapshot()
    assert set(snapshot) == set(Capabilities.__required_keys__)
    assert set(snapshot["kinds"]) == set(RUN_KINDS)
    assert snapshot["ui"] == {"built": False, "static_dir": str(tmp_path / "static"),
                              "reason": snapshot["ui"]["reason"]}
    assert "has not been built" in snapshot["ui"]["reason"]
    assert snapshot["data_dir"] == {"path": str(tmp_path / "data"), "writable": True, "runs": 0, "reason": None}


def test_the_network_is_never_probed_unasked(tmp_path):
    calls: List[str] = []
    p = probe(tmp_path, head=lambda host, timeout: calls.append(host))
    network = p.snapshot()["network"]
    assert calls == []
    assert network["checked"] is False and network["reachable"] is None
    assert network["hosts"] == {h: None for h in NETWORK_HOSTS}
    assert "only when asked" in network["reason"]


def test_a_probe_contacts_each_host_once_with_a_short_timeout(tmp_path):
    seen = []

    def head(host, timeout):
        seen.append((host, timeout))
        return None if host != "rest.uniprot.org" else "no answer within 5 s"

    network = probe(tmp_path, head=head).snapshot(probe_network=True)["network"]
    assert sorted(seen) == sorted((h, 5.0) for h in NETWORK_HOSTS)
    assert network["checked"] is True and network["reachable"] is False
    assert network["hosts"]["rest.uniprot.org"] is False and network["hosts"]["files.rcsb.org"] is True
    assert network["reason"] == "not reachable from this computer: rest.uniprot.org: no answer within 5 s"
    assert network["checked_at"] == "2026-09-30T12:00:00.000Z"


def test_a_probe_that_raises_counts_as_unreachable(tmp_path):
    def head(host, timeout):
        raise RuntimeError("resolver broke")

    network = probe(tmp_path, head=head).probe_network()
    assert network["reachable"] is False
    assert "RuntimeError: resolver broke" in network["reason"]


def test_offline_mode_contacts_nothing_and_marks_network_kinds_unavailable(tmp_path):
    calls = []
    registry = Registry()
    registry.register(AdapterSpec(kind="constants", title="Constants", command="python3 scripts/cite.py",
                                  needs=("network", "literature"), argv=lambda r: [],
                                  run=lambda r, c: AdapterOutcome(0, {}, "")))
    registry.register(AdapterSpec(kind="sim", title="Simulate", command="caterva sim ssa", needs=(),
                                  argv=lambda r: [], run=lambda r, c: AdapterOutcome(0, {}, "")))
    snapshot = probe(tmp_path, settings={"offline": True}, registry=registry,
                     head=lambda h, t: calls.append(h)).snapshot(probe_network=True)
    assert calls == []
    assert snapshot["network"]["checked"] is False and snapshot["network"]["reason"] == OFFLINE_REASON
    assert snapshot["kinds"]["constants"] == {"available": False, "title": "Constants",
                                              "command": "python3 scripts/cite.py",
                                              "needs": ["network", "literature"], "reason": OFFLINE_REASON}
    assert snapshot["kinds"]["sim"]["available"] is True


def test_the_literature_layer_is_tried_once_and_its_refusal_kept(tmp_path):
    attempts = []

    def literature():
        attempts.append(1)
        raise ImportError("the literature layer is only in a source checkout")

    p = probe(tmp_path, literature=literature)
    assert p.literature() == {"available": False, "reason": "the literature layer is only in a source checkout"}
    p.literature()
    assert attempts == [1]


def test_gromacs_found_on_path_with_its_version(tmp_path):
    p = probe(tmp_path, which=lambda name: "/usr/bin/gmx" if name == "gmx" else None)
    assert p.gromacs() == {"found": True, "path": "/usr/bin/gmx", "version": "2025.3-Homebrew", "reason": None}


def test_gromacs_order_setting_then_gmx_env_then_path_then_homebrew(tmp_path):
    which = {"gmx": "/usr/bin/gmx", "gmx_mpi": "/opt/x/gmx_mpi"}.get
    assert probe(tmp_path, settings={"gromacs_path": "/chosen/gmx"}, environ={"GMX": "gmx_mpi"},
                 which=which).gromacs_candidate() == ("/chosen/gmx", "the gromacs_path setting")
    assert probe(tmp_path, environ={"GMX": "gmx_mpi"}, which=which).gromacs_candidate() == \
        ("/opt/x/gmx_mpi", "$GMX (gmx_mpi)")
    assert probe(tmp_path, which=which).gromacs_candidate() == ("/usr/bin/gmx", "gmx on PATH")
    assert probe(tmp_path, is_executable=lambda p: p == GMX_FALLBACKS[1]).gromacs_candidate()[0] == GMX_FALLBACKS[1]


def test_gromacs_missing_slow_or_broken_says_which(tmp_path):
    missing = probe(tmp_path).gromacs()
    assert missing["found"] is False and "GROMACS was not found" in missing["reason"]

    def slow(*a, **k):
        raise subprocess.TimeoutExpired(a[0], 5)

    slow_answer = probe(tmp_path, which=lambda n: "/usr/bin/gmx", run=slow).gromacs()
    assert slow_answer["reason"] == "/usr/bin/gmx (from gmx on PATH) did not answer `--version` within 5 s"
    broken = probe(tmp_path, which=lambda n: "/usr/bin/gmx",
                   run=lambda *a, **k: SimpleNamespace(returncode=1, stdout="", stderr="dyld: no library")).gromacs()
    assert broken["found"] is False and "exited 1" in broken["reason"]


def test_gromacs_is_looked_for_again_until_found_then_kept(tmp_path):
    found = [None]
    runs = []

    def run(*a, **k):
        runs.append(a[0][0])
        return SimpleNamespace(returncode=0, stdout=GMX_OUTPUT, stderr="")

    p = probe(tmp_path, which=lambda n: found[0], run=run)
    assert p.gromacs()["found"] is False
    found[0] = "/usr/bin/gmx"
    assert p.gromacs()["found"] is True
    p.gromacs()
    assert runs == ["/usr/bin/gmx"]


def test_gmx_version_line_parsing():
    assert parse_gmx_version(GMX_OUTPUT) == "2025.3-Homebrew"
    assert parse_gmx_version("no version here") is None


def test_the_gmx_environment_follows_the_setting_and_homebrew(tmp_path):
    environ = {}
    probe(tmp_path, settings={"gromacs_path": "/chosen/gmx"}, environ=environ).apply_gromacs_to_environment()
    assert environ == {"GMX": "/chosen/gmx"}
    environ = {}
    probe(tmp_path, environ=environ, is_executable=lambda p: p == GMX_FALLBACKS[0]).apply_gromacs_to_environment()
    assert environ == {"GMX": GMX_FALLBACKS[0]}
    environ = {"GMX": "mine"}
    probe(tmp_path, environ=environ).apply_gromacs_to_environment()
    assert environ == {"GMX": "mine"}


def test_rates_needs_both_the_module_and_an_adapter(tmp_path):
    assert probe(tmp_path).rates() == {
        "available": False,
        "reason": "the caterva.rates module is not in this installation; no adapter registered the rates kind"}
    assert probe(tmp_path, find_spec=lambda name: object()).rates() == {
        "available": False, "reason": "no adapter registered the rates kind"}


def test_kinds_not_registered_are_not_built_yet_and_a_raising_check_is_reported(tmp_path):
    def raises():
        raise OSError("disk gone")

    registry = Registry()
    registry.register(AdapterSpec(kind="bind", title="Bind", command="caterva bind", needs=("literature",),
                                  argv=lambda r: [], run=lambda r, c: AdapterOutcome(0, {}, ""), unavailable=raises))
    kinds = probe(tmp_path, registry=registry).kinds()
    assert kinds["compose"] == {"available": False, "title": "caterva compose", "command": "caterva compose",
                                "needs": [], "reason": NOT_BUILT_YET}
    assert kinds["bind"]["available"] is False
    assert kinds["bind"]["reason"] == "could not tell whether it can run here: OSError: disk gone"


def test_the_real_probe_on_this_checkout(tmp_path):
    """No injected functions but the network's: this checkout's literature
    layer imports, and every kind is reported, registered or not."""
    ws = Workspace(tmp_path / "data")
    ws.ensure()
    real = CapabilityProbe(registry=load_registry(), workspace=ws, static_site=StaticSite(tmp_path / "static"),
                           dev_origin="http://127.0.0.1:18741", settings=lambda: DEFAULT_SETTINGS,
                           environ=dict(os.environ), head=lambda h, t: None)
    snapshot = real.snapshot()
    assert snapshot["literature"] == {"available": True, "reason": None}
    assert set(snapshot["kinds"]) == set(RUN_KINDS)
    assert snapshot["dev_origin"] == "http://127.0.0.1:18741"
    assert snapshot["frozen"] is False
