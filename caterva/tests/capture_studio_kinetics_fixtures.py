"""Capture the kinetics screens' compose fixtures from the running dispatch layer.

    cd <repository root> && PYTHONPATH=$PWD python caterva/tests/capture_studio_kinetics_fixtures.py

Every file written under
Science-Agent-Pipeline/artifacts/caterva-studio/src/__fixtures__/api/kinetics/
is what the studio server answered to a real request, through
`caterva.studio.dispatch.App.dispatch` exactly as the socket layer hands a
request over: `POST /api/runs`, then `GET /api/runs/{id}` until the run
finished, then the record, `GET /api/runs/{id}/result` and `GET
/api/runs/{id}/events`. Nothing is typed by hand and the JSON must not be
edited by hand; the README beside them says what each is.

The README there records that the first capture (2026-10-01) was made in a
scratch tree before core was merged, by hand; this script is that recipe,
written down, and rewrites only the compose runs (the ones whose answers
changed when every compose run started writing its claims bundle, ADR
0179). The constants, sim and bind fixtures are not touched. Two
replacements are made in what is written, and no other edit: the scratch
data directory becomes `<data dir>`, and the temporary folder the offline
context serves the LDH page from becomes `<recorded pages>`.

Literature answers are the committed recordings (the same context managers
the parity tests use, `studio_kinetics_offline.py`); a request with no
recording is refused, never sent. The LDH runs' literature pages are not
recorded, so their bundles say, honestly, that those pages were not
captured (`claims.notes`), and their claims carry no paper.

The hexokinase run (`compose-hexokinase-claims`) is the one whose
literature pages are recorded too (`caterva/tests/fixtures/compose_claims/`),
so its Km claim carries the paper's title and PubMed id; it is the run the
re-check fixtures are taken over: `verify-hexokinase` is `POST
/api/runs/{id}/verify` on it as written, `verify-hexokinase-changed-byte`
the same after one byte of the pinned page was changed on disk (the last
digit of the certified reference id, as caterva/tests/test_studio_verify.py
changes it) and restored afterwards, and `verify-no-bundle` the 409 for the
unrecognised-shape run, which built nothing and so wrote no bundle. Each
verify fixture is `{"status", "body"}`, as the malformed-request fixture is.
"""
from __future__ import annotations

import gzip
import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "caterva" / "tests"))

OUT = REPO / "Science-Agent-Pipeline" / "artifacts" / "caterva-studio" / "src" / "__fixtures__" / "api" / "kinetics"
PORT = 18720
TOKEN = "k" * 43

#: The scratch folder of this run, as the server spells it (and as the
#: operating system resolves it): replaced in everything written, so that
#: no fixture names a throwaway folder on the machine that captured it.
SCRATCH: List[str] = []

LDH = {"subject": "1.1.1.27", "organism": "human", "substrate": "pyruvate"}
#: The hexokinase run of caterva/tests/test_studio_verify.py: the search only,
#: so the fixture is the claims and not a dossier.
HEXOKINASE = {"description": "Michaelis Menten", "subject": "2.7.1.1", "organism": "human",
              "substrate": "glucose", "no_analysis": True, "no_simulate": True, "no_ranking": True}
#: The sha256 of the recorded hexokinase page (Tests/fixtures/recorded/README.md).
HEXOKINASE_SHA256 = "3a69b492abcd7253b301d7a002f60d52a971ba9352a3a2559ec5f12f5060ef91"
QUINOLINE = "3-[7-(2,4-dimethoxypyrimidin-5-yl)-3-sulfamoylquinolin-4-yl]aminobenzoic acid"
BINDING = "reversible binding of a ligand to a receptor"


#: The folder `studio_kinetics_offline.ldh_offline` serves the committed LDH
#: page from (a temporary copy, so that fetch_brenda_html reads it the way
#: it reads a recording), and the one `hexokinase_offline(literature=True)`
#: merges the replay recordings into: a claim's snapshot says it was served
#: from there, and the fixture says so without naming a throwaway folder.
RECORDED_PAGE = re.compile(re.escape(tempfile.gettempdir()) + r"/caterva-(?:brenda|replay)-[^/\"]+")


def neutral(text: str, data_dir: str) -> str:
    text = text.replace(data_dir, "<data dir>")
    for spelling in sorted(SCRATCH, key=len, reverse=True):
        text = text.replace(spelling, "<data dir>")
    # The hexokinase page is served from the repository's own recordings, so
    # a snapshot's `served_from` would name this checkout's folder.
    for spelling in sorted({str(REPO), str(REPO.resolve())}, key=len, reverse=True):
        text = text.replace(spelling, "<repository>")
    return RECORDED_PAGE.sub("<recorded pages>", text)


def make_app(work: Path):
    from caterva.studio.adapters import load_registry
    from caterva.studio.dispatch import App
    from caterva.studio.static_files import StaticSite
    from caterva.studio.workspace import Workspace

    app = App(workspace=Workspace(work / "data"), port=PORT, token=TOKEN, static_site=StaticSite(work / "no-build"),
              registry=load_registry(),
              capability_options=dict(head=lambda h, t: None, which=lambda n: None, is_executable=lambda p: False))
    app.start(apply_environment=False)
    return app


def call(app: Any, method: str, target: str, body: Any = None):
    from caterva.studio.contract import SESSION_HEADER
    from caterva.studio.dispatch import Request

    headers = [("Host", f"127.0.0.1:{PORT}"), (SESSION_HEADER, TOKEN)]
    raw = None
    if body is not None:
        raw = json.dumps(body).encode()
        headers += [("Content-Type", "application/json"), ("Content-Length", str(len(raw)))]
    return app.dispatch(Request(method, target, headers, raw))


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text + "\n", encoding="utf-8")
    print("wrote", path.relative_to(REPO))


def run(app: Any, kind: str, request: Dict[str, Any], name: str) -> Optional[str]:
    """POST /api/runs, wait, and keep the run, its result and its events; the run's id, or
    None when the request was refused before a run existed."""
    created = call(app, "POST", "/api/runs", {"kind": kind, "request": request})
    data_dir = str(app.ws.root)
    if created.status != 202:
        # A malformed request: the status and the error body, as the page receives them.
        write(OUT / f"{name}.json", neutral(json.dumps({
            "status": created.status, "body": created.json(),
        }, indent=1, ensure_ascii=False, allow_nan=False), data_dir))
        print("  ", created.status, created.json()["error"]["message"])
        return None
    run_id = created.json()["run"]["id"]
    while True:
        record = call(app, "GET", f"/api/runs/{run_id}").json()
        if record["status"] in ("done", "failed", "cancelled", "interrupted"):
            break
        time.sleep(0.2)
    result = call(app, "GET", f"/api/runs/{run_id}/result")
    events = call(app, "GET", f"/api/runs/{run_id}/events")
    frames: List[Dict[str, Any]] = []
    for chunk in events.stream or ():
        for block in chunk.decode("utf-8").split("\n\n"):
            fields = dict(line.split(": ", 1) for line in block.splitlines() if ": " in line)
            if "event" in fields and "data" in fields:
                frames.append({"event": fields["event"], "data": json.loads(fields["data"])})
    # Both keys always, as the first capture wrote them: `result` is the kind's
    # Result or null, `error` the 404 body of a run that finished without one, or null.
    text = json.dumps({
        "captured": {"kind": kind, "request": request},
        "run": record,
        "result_status": result.status,
        "result": result.json() if result.status == 200 else None,
        "error": result.json() if result.status != 200 else None,
        "events": frames,
    }, indent=1, ensure_ascii=False, allow_nan=False)
    write(OUT / f"{name}.json", neutral(text, data_dir))
    print("  ", record["status"], record["outcome"]["meaning"] if record.get("outcome") else "",
          "claims" if result.status == 200 and result.json().get("claims") else "no claims")
    return run_id


def verify(app: Any, run_id: str, name: str) -> None:
    """POST /api/runs/{id}/verify with `{}`: the status and the body, as the page receives them."""
    response = call(app, "POST", f"/api/runs/{run_id}/verify", {})
    write(OUT / f"{name}.json", neutral(json.dumps({
        "status": response.status, "body": response.json(),
    }, indent=1, ensure_ascii=False, allow_nan=False), str(app.ws.root)))
    body = response.json()
    print("  ", response.status, body.get("ok") if response.status == 200 else body["error"]["message"])


def change_one_pinned_byte(app: Any, run_id: str, km_claim: str) -> Any:
    """Change the last digit of the Km claim's certified reference id in the pinned page
    (`641068` -> `641069`), as caterva/tests/test_studio_verify.py does; the returned
    function puts the byte back."""
    blob = app.ws.claims_dir(run_id) / "snapshots" / f"{HEXOKINASE_SHA256}.gz"
    page = bytearray(gzip.decompress(blob.read_bytes()))
    listing = call(app, "GET", f"/api/runs/{run_id}/artifacts/claims.json").json()
    stored = next(c for c in listing["claims"] if f"claim:{c['id']}" == km_claim)
    certificate = next(c for c in stored["derivation"]["certificates"] if c["matched"] == "641068")
    start, end = certificate["span"]
    assert page[start:end] == b"641068", page[start:end]
    kept = page[end - 1]
    page[end - 1] = ord("9")
    blob.write_bytes(gzip.compress(bytes(page), mtime=0))

    def restore() -> None:
        page[end - 1] = kept
        blob.write_bytes(gzip.compress(bytes(page), mtime=0))

    return restore


def main() -> None:
    from studio_kinetics_offline import hexokinase_offline, ldh_offline

    work = Path(tempfile.mkdtemp(prefix="caterva-kinetics-fixtures-"))
    SCRATCH[:] = [str(work), str(work.resolve())]
    os.environ["XDG_CACHE_HOME"] = str(work / "cache")
    app = make_app(work)
    try:
        with ldh_offline():
            run(app, "compose", {"description": "Michaelis-Menten with a competitive inhibitor",
                                 "inhibitor": "gossypol", **LDH}, "compose-ldh-gossypol")
            run(app, "compose", {"description": "Michaelis-Menten with a noncompetitive inhibitor",
                                 "inhibitor": QUINOLINE, **LDH}, "compose-ldh-noncompetitive")
        run(app, "compose", {"description": BINDING,
                             "analyses": {"crnt": True, "scale": True, "validate": True, "reduction": True,
                                          "robustness": {"samples": 5}}}, "compose-binding-analyses")
        run(app, "compose", {"description": BINDING, "sweep": {"parameters": ["complex_kon"]},
                             "analyses": {"predictions": True, "identifiability": True, "design": True,
                                          "screen": True, "robustness": {"samples": 30},
                                          "stochastic": {"volume_l": 1e-18, "seed": 11},
                                          "knockout": ["complex_A"]}}, "compose-binding-charts")
        unrecognised = run(app, "compose", {"description": "glycolysis"}, "compose-unrecognised")
        run(app, "compose", {"description": BINDING, "analyses": {"robustness": {"samples": 0}}},
            "compose-malformed")
        with hexokinase_offline(literature=True):
            hexokinase = run(app, "compose", HEXOKINASE, "compose-hexokinase-claims")
        assert hexokinase is not None and unrecognised is not None
        verify(app, hexokinase, "verify-hexokinase")
        result = call(app, "GET", f"/api/runs/{hexokinase}/result").json()
        km = next(p for p in result["model"]["parameters"] if p["id"] == "reaction_Km")
        restore = change_one_pinned_byte(app, hexokinase, km["provenance"]["claim"]["id"])
        try:
            verify(app, hexokinase, "verify-hexokinase-changed-byte")
        finally:
            restore()
        verify(app, unrecognised, "verify-no-bundle")
    finally:
        app.close()


if __name__ == "__main__":
    main()
