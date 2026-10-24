"""`POST /api/runs/{id}/verify`: the independent checker over a run's claims bundle, through the server.

A compose run through the dispatch layer (the real registry, the committed
hexokinase recordings) writes its bundle under the run's folder (CONTRACT.md
11); the route re-checks it with caterva/check/verify.py and answers the
command's `--json` report. Then one byte of the pinned page is changed on
disk, re-gzipped, and the route names the Km claim among what that page
held. The refusals are held too: a run of another kind, a run that is not
done, a body that is not `{}`, and a folder that is not a bundle.
"""
from __future__ import annotations

import gzip
import json
import threading
import time
from typing import TYPE_CHECKING

import pytest

from caterva.studio import contract
from caterva.studio.adapters import AdapterOutcome, AdapterSpec, Registry, load_registry
from caterva.studio.contract import SESSION_HEADER
from caterva.studio.dispatch import App, Request
from caterva.studio.static_files import StaticSite
from caterva.studio.workspace import Workspace
from studio_kinetics_offline import hexokinase_offline

if TYPE_CHECKING:
    from pathlib import Path

PORT = 18771
TOKEN = "v" * 43
HEADERS = [("Host", f"127.0.0.1:{PORT}"), (SESSION_HEADER, TOKEN)]
HEXOKINASE = {"description": "Michaelis Menten", "subject": "2.7.1.1", "organism": "human",
              "substrate": "glucose", "no_analysis": True, "no_simulate": True, "no_ranking": True}
#: The sha256 of the recorded hexokinase page (Tests/fixtures/recorded/README.md).
HEXOKINASE_SHA256 = "3a69b492abcd7253b301d7a002f60d52a971ba9352a3a2559ec5f12f5060ef91"


def make_app(tmp_path: Path, registry) -> App:
    app = App(workspace=Workspace(tmp_path / "data"), port=PORT, token=TOKEN,
              static_site=StaticSite(tmp_path / "no-build"), registry=registry,
              capability_options=dict(head=lambda h, t: None, literature_import=lambda: None,
                                      which=lambda n: None, is_executable=lambda p: False))
    app.start(apply_environment=False)
    return app


def call(app: App, method: str, target: str, body=None):
    headers = list(HEADERS)
    raw = None
    if body is not None:
        raw = json.dumps(body).encode()
        headers += [("Content-Type", "application/json"), ("Content-Length", str(len(raw)))]
    return app.dispatch(Request(method, target, headers, raw))


def finished(app: App, run_id: str, timeout: float = 300.0) -> dict:
    """The run's record once it is done; a run that is not done in time fails the test."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        record = call(app, "GET", f"/api/runs/{run_id}").json()
        if record["status"] in ("done", "failed", "cancelled", "interrupted"):
            return record
        time.sleep(0.2)
    raise AssertionError(f"run {run_id} did not finish within {timeout} s")


# ---------------------------------------------------------------------------
# A real compose run, re-checked, then a pinned byte changed
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def hexokinase_run(tmp_path_factory):
    """One hexokinase run through the server, done; (app, record, result)."""
    tmp = tmp_path_factory.mktemp("verify")
    app = make_app(tmp, load_registry(("compose",)))
    with hexokinase_offline():
        created = call(app, "POST", "/api/runs", {"kind": "compose", "request": HEXOKINASE})
        assert created.status == 202, created.json()
        run_id = created.json()["run"]["id"]
        record = finished(app, run_id)
    assert record["status"] == "done" and record["outcome"]["exit_code"] == 0, record
    result = call(app, "GET", f"/api/runs/{run_id}/result").json()
    yield app, record, result
    app.close()


def km_claim(result: dict) -> dict:
    return next(p for p in result["model"]["parameters"] if p["id"] == "reaction_Km")["provenance"]["claim"]


def test_the_run_wrote_its_bundle_under_its_folder_and_lists_it_as_artifacts(hexokinase_run):
    app, record, result = hexokinase_run
    directory = app.ws.claims_dir(record["id"])
    assert directory == app.ws.run_dir(record["id"]) / contract.CLAIMS_DIR
    for name in ("manifest.json", "claims.jsonl", "rows.jsonl", "snapshots.jsonl"):
        assert (directory / name).is_file(), name
    assert (directory / "snapshots" / f"{HEXOKINASE_SHA256}.gz").is_file()
    names = [a["name"] for a in record["artifacts"]]
    assert "claims.zip" in names and "claims.json" in names
    assert result["claims"]["root"] == json.loads((directory / "manifest.json").read_text())["root"]
    assert km_claim(result)["row"]["reference"] == "641068"
    # The artifact routes serve both, with their recorded types.
    zipped = call(app, "GET", f"/api/runs/{record['id']}/artifacts/claims.zip")
    assert zipped.status == 200 and zipped.header("Content-Type") == "application/zip"
    listing = call(app, "GET", f"/api/runs/{record['id']}/artifacts/claims.json")
    assert listing.status == 200 and set(listing.json()) == {"manifest", "claims", "rows", "snapshots"}


def test_verify_answers_the_checkers_report_and_it_passes(hexokinase_run):
    from caterva.check.verify import verify_bundle

    app, record, result = hexokinase_run
    response = call(app, "POST", f"/api/runs/{record['id']}/verify", {})
    assert response.status == 200, response.json()
    report = response.json()
    assert set(report) == {"ok", "checks", "ran_at"}
    assert report["ok"] is True and report["ran_at"].endswith("Z")
    assert all(set(c) == {"name", "claim", "ok", "detail"} for c in report["checks"])
    assert all(c["ok"] for c in report["checks"])
    names = {c["name"] for c in report["checks"]}
    assert {"snapshot bytes", "identity", "row locator", "certificate", "dominance", "inputs", "root",
            "not checked"} <= names
    km = km_claim(result)["id"]
    assert {c["name"] for c in report["checks"] if c["claim"] == km} >= {"identity", "row locator",
                                                                         "certificate", "dominance"}
    # Line for line what `caterva verify DIR --json` prints for the same folder.
    again = verify_bundle(app.ws.claims_dir(record["id"])).to_dict()
    assert {"ok": report["ok"], "checks": report["checks"]} == again


def test_a_changed_byte_in_the_pinned_page_fails_verify_naming_the_km_claim(hexokinase_run):
    app, record, result = hexokinase_run
    km = km_claim(result)
    blob = app.ws.claims_dir(record["id"]) / "snapshots" / f"{HEXOKINASE_SHA256}.gz"
    page = bytearray(gzip.decompress(blob.read_bytes()))
    # The byte where the Km claim's reference id is certified: "641068" -> "641069".
    listing = call(app, "GET", f"/api/runs/{record['id']}/artifacts/claims.json").json()
    stored = next(c for c in listing["claims"] if f"claim:{c['id']}" == km["id"])
    certificate = next(c for c in stored["derivation"]["certificates"] if c["matched"] == "641068")
    start, end = certificate["span"]
    assert page[start:end] == b"641068"
    page[end - 1] = ord("9")
    blob.write_bytes(gzip.compress(bytes(page), mtime=0))
    try:
        response = call(app, "POST", f"/api/runs/{record['id']}/verify", {})
        assert response.status == 200
        report = response.json()
        assert report["ok"] is False
        failed = [c for c in report["checks"] if not c["ok"]]
        assert failed and failed[0]["name"] == "snapshot bytes"
        assert f"snapshot:sha256:{HEXOKINASE_SHA256}" in failed[0]["detail"]
        assert "reaction_Km" in failed[0]["detail"] and km["id"] in failed[0]["detail"]
        assert "not the snapshot's id" in failed[0]["detail"]
    finally:
        page[end - 1] = ord("8")
        blob.write_bytes(gzip.compress(bytes(page), mtime=0))
    assert call(app, "POST", f"/api/runs/{record['id']}/verify", {}).json()["ok"] is True


def test_a_folder_that_is_not_a_bundle_is_409_with_the_checkers_reason(hexokinase_run):
    app, record, _ = hexokinase_run
    manifest = app.ws.claims_dir(record["id"]) / "manifest.json"
    kept = manifest.read_bytes()
    manifest.write_text('{"format": "caterva-claims/9", "root": "claim:sha256:0"}\n', encoding="utf-8")
    try:
        response = call(app, "POST", f"/api/runs/{record['id']}/verify", {})
        assert response.status == 409
        message = response.json()["error"]["message"]
        assert message.startswith("the run's claims bundle cannot be read, so nothing in it was checked: ")
        assert "caterva-claims/9" in message
    finally:
        manifest.write_bytes(kept)


def test_verify_takes_an_empty_object_and_no_query(hexokinase_run):
    app, record, _ = hexokinase_run
    assert call(app, "POST", f"/api/runs/{record['id']}/verify", {"again": True}).status == 400
    assert call(app, "POST", f"/api/runs/{record['id']}/verify?x=1", {}).status == 400
    assert call(app, "GET", f"/api/runs/{record['id']}/verify").status == 405


# ---------------------------------------------------------------------------
# Runs that have no bundle
# ---------------------------------------------------------------------------


def _spec(kind: str, started: threading.Event, release: threading.Event) -> AdapterSpec:
    def run(request, ctx):
        started.set()
        release.wait(30)
        return AdapterOutcome(exit_code=0, result={"events": 0}, summary="nothing")

    return AdapterSpec(kind=kind, title=kind, command=kind, needs=(), argv=lambda request: ["ssa", "--seed", "1"],
                       run=run, cli_prefix=("caterva", kind))


def test_a_run_of_a_kind_that_writes_no_bundle_is_409_with_the_contracts_sentence(tmp_path):
    started, release = threading.Event(), threading.Event()
    registry = Registry()
    registry.register(_spec("sim", started, release))
    app = make_app(tmp_path, registry)
    try:
        created = call(app, "POST", "/api/runs", {"kind": "sim", "request": {}})
        assert created.status == 202
        run_id = created.json()["run"]["id"]
        assert started.wait(30)
        # Not done yet: 409, as its result is.
        running = call(app, "POST", f"/api/runs/{run_id}/verify", {})
        assert running.status == 409 and "once it is done" in running.json()["error"]["message"]
        release.set()
        assert finished(app, run_id)["status"] == "done"
        response = call(app, "POST", f"/api/runs/{run_id}/verify", {})
        assert response.status == 409
        assert response.json()["error"] == {"code": "conflict", "message": contract.NO_CLAIMS_BUNDLE}
        assert not app.ws.claims_dir(run_id).exists()
    finally:
        release.set()
        app.close()
