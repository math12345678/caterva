"""Capture the enzyme finder's UI fixtures from the running dispatch layer.

    cd <repository root> && PYTHONPATH=$PWD python caterva/tests/capture_studio_enzyme_fixtures.py

Every file written under
Science-Agent-Pipeline/artifacts/caterva-studio/src/__fixtures__/api/enzymes/
is what the studio server answered to a real request, through
`caterva.studio.dispatch.App.dispatch` exactly as the socket layer hands a
request over: the finder's two GET routes, a compose run, a constants run, a
structure run and the capabilities. Nothing is typed by hand and the JSON
must not be edited by hand. The README beside them says what each is.

Literature and structure answers are the committed recordings (the same
context managers the parity tests use); a request with no recording is
refused, never sent. Only the two names `structure-by-name-ldha` and
`structure-name-several-enzymes` are rewritten under `../structure/`,
because the name policy changed what the engine answers to them.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional
from urllib.parse import quote, quote_plus

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "caterva" / "tests"))

OUT = REPO / "Science-Agent-Pipeline" / "artifacts" / "caterva-studio" / "src" / "__fixtures__" / "api"
ENZYMES = OUT / "enzymes"
STRUCTURE = OUT / "structure"
PORT = 18770
TOKEN = "f" * 43


def write(path: Path, body: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(body, indent=1, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    print("wrote", path.relative_to(REPO))


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


def get_json(app: Any, target: str) -> Dict[str, Any]:
    response = call(app, "GET", target)
    return {"request": {"method": "GET", "path": target}, "status": response.status, "body": response.json()}


def run(app: Any, kind: str, request: Dict[str, Any], name: str) -> None:
    """POST /api/runs, wait, and keep the run, its result and its events."""
    created = call(app, "POST", "/api/runs", {"kind": kind, "request": request})
    assert created.status == 202, created.json()
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
    data_dir = str(app.ws.root)
    text = json.dumps({
        "captured": {"kind": kind, "request": request},
        "run": record,
        "result_status": result.status,
        ("result" if result.status == 200 else "error"): result.json(),
        "events": frames,
    }, indent=1, ensure_ascii=False, allow_nan=False).replace(data_dir, "<data dir>")
    path = ENZYMES / f"{name}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text + "\n", encoding="utf-8")
    print("wrote", path.relative_to(REPO), record["status"], record["outcome"]["meaning"] if record.get("outcome") else "")


@contextlib.contextmanager
def structure_recordings() -> Iterator[None]:
    """The UniProt and RCSB answers of caterva/tests/fixtures/structure/ldh_human.json, replayed."""
    from caterva.checkout import literature_module
    from caterva.structure import search

    fixtures = REPO / "caterva" / "tests" / "fixtures" / "structure"
    calls = json.loads((fixtures / "ldh_human.json").read_text())["calls"]

    def replay(url: str, payload: Any) -> Any:
        return calls[hashlib.sha256((url + json.dumps(payload, sort_keys=True)).encode()).hexdigest()[:16]]["response"]

    names = json.loads((fixtures / "uniprot_ec_by_name.json").read_text())["answers"]
    lookup = literature_module("enzyme_lookup")
    saved = (search.live_http, lookup.fetch_ec_numbers_by_name)
    search.live_http = lambda timeout=30.0: search.Http(replay, replay)
    lookup.fetch_ec_numbers_by_name = lambda name, taxon_id=None, timeout=15: lookup.parse_ec_number_candidates(names[name])
    try:
        yield
    finally:
        search.live_http, lookup.fetch_ec_numbers_by_name = saved


def main() -> None:
    from studio_kinetics_offline import hexokinase_offline, ldh_offline

    work = Path(tempfile.mkdtemp(prefix="caterva-enzyme-fixtures-"))
    os.environ["XDG_CACHE_HOME"] = str(work / "cache")
    app = make_app(work)
    try:
        # The finder, for the queries the owner complained about and the ones a typeahead meets.
        for query, organism in [
            ("lactate dehydrogenase", None), ("lactate dehydrogenase", "human"), ("pyruvate kinase", None),
            ("hexokinase", "human"), ("glucokinase", None), ("LDHA", "human"), ("hexokinse", "human"),
            ("1.1.1.27", "human"), ("1.1.1", None), ("zzqx protein of no enzyme", None), ("9.9.9.9", None),
            # What the review of 2026-10-03 found it resolving wrongly, and what it answers now.
            ("HK1", "human"), ("SDH", "human"), ("glycogen synthase", "human"), ("ADH", "human"),
            ("GAPDH", "human"), ("IDH1", "yeast"), ("ACHE", "human"), ("HIV protease", None),
            ("COX", "E. coli"), ("ribonuclease A", "human"),
        ]:
            target = f"/api/enzymes/find?q={quote(query)}" + (f"&organism={quote(organism)}" if organism else "")
            slug = "-".join(filter(None, [query.replace(" ", "-").replace(".", "-").lower(),
                                          organism.replace(". ", "-").replace(" ", "-").lower() if organism else None]))
            write(ENZYMES / f"find-{slug}.json", get_json(app, target))
        # A transferred and a deleted number, from the nomenclature itself: the first of each in EC order.
        from caterva.enzymes import load_index

        entries = load_index().entries
        for status, need_one in (("transferred", True), ("deleted", False)):
            ec = next(e for e in sorted(entries) if entries[e].status == status
                      and (len(entries[e].superseded_by) == 1 if need_one else not entries[e].superseded_by))
            write(ENZYMES / f"find-{status}-{ec}.json", get_json(app, f"/api/enzymes/find?q={ec}"))
        write(ENZYMES / "detail-2.7.1.1-human.json", get_json(app, "/api/enzymes/2.7.1.1?organism=human"))
        write(ENZYMES / "detail-1.1.1.27-human.json", get_json(app, "/api/enzymes/1.1.1.27?organism=human"))
        write(ENZYMES / "detail-5.3.1.1-human.json", get_json(app, "/api/enzymes/5.3.1.1?organism=human"))
        write(ENZYMES / "detail-9.9.9.9.json", get_json(app, "/api/enzymes/9.9.9.9"))
        # An EC number that is several proteins, a broad class, an E. coli (K-12) count, and the two retired kinds.
        write(ENZYMES / "detail-1.1.1.1-human.json", get_json(app, "/api/enzymes/1.1.1.1?organism=human"))
        write(ENZYMES / "detail-2.7.11.1-human.json", get_json(app, "/api/enzymes/2.7.11.1?organism=human"))
        write(ENZYMES / "detail-1.1.1.1-e-coli.json", get_json(app, "/api/enzymes/1.1.1.1?organism=" + quote_plus("E. coli")))
        for status, need_one in (("transferred", True), ("deleted", False)):
            ec = next(e for e in sorted(entries) if entries[e].status == status
                      and (len(entries[e].superseded_by) == 1 if need_one else not entries[e].superseded_by))
            write(ENZYMES / f"detail-{status}-{ec}.json", get_json(app, f"/api/enzymes/{ec}"))

        # The network, as the status bar sees it before anything happened, and after a BRENDA lookup worked.
        nothing_yet = get_json(app, "/api/capabilities")
        write(ENZYMES / "capabilities-nothing-yet.json", nothing_yet)
        # The workspace fixture of the same answer keeps the rest of what it captured and takes the
        # server's current `network`, which is the one thing this change altered in that answer.
        workspace = OUT / "workspace" / "capabilities.json"
        kept = json.loads(workspace.read_text(encoding="utf-8"))
        kept["network"] = nothing_yet["body"]["network"]
        write(workspace, kept)

        # Compose: the live run the steady-state defect was seen on, and the isozyme notice.
        with ldh_offline():
            run(app, "compose", {"description": "Michaelis Menten", "subject": "1.1.1.27", "organism": "human",
                                 "substrate": "pyruvate"}, "compose-ldh-human-pyruvate")
            run(app, "compose", {"description": "Michaelis Menten", "subject": "lactate dehydrogenase",
                                 "organism": "human", "substrate": "pyruvate"}, "compose-name-several-enzymes")
        # A line of equilibria: the count of steady states found depends on where the search started.
        run(app, "compose", {"description": "two enzymes competing for the same substrate"},
            "compose-two-enzymes-competing")
        with hexokinase_offline():
            run(app, "compose", {"description": "Michaelis Menten", "subject": "2.7.1.1", "organism": "human",
                                 "substrate": "glucose"}, "compose-hexokinase-human-glucose")
            run(app, "compose", {"description": "Michaelis Menten", "subject": "2.7.1.1", "organism": "human",
                                 "substrate": "glucose", "isoform": "HXK1"}, "compose-hexokinase-human-glucose-hxk1")
            run(app, "compose", {"description": "Michaelis Menten", "subject": "2.7.1.1", "organism": "human",
                                 "substrate": "glucose", "isoform": "HK2"}, "compose-hexokinase-human-glucose-hk2")
            run(app, "compose", {"description": "Michaelis Menten", "subject": "2.7.1.1", "organism": "human",
                                 "substrate": "glucose", "isoform": "GCK"}, "compose-hexokinase-human-glucose-gck")
            run(app, "compose", {"description": "Michaelis Menten", "subject": "2.7.1.1", "organism": "human",
                                 "substrate": "glucose", "compounds": {"@inhibitor": "gossypol"}},
                "compose-michaelis-menten-unused-inhibitor")
            run(app, "constants", {"enzyme": "lactate dehydrogenase", "organism": "human", "substrate": "pyruvate"},
                "constants-name-several-enzymes")
            run(app, "constants", {"ec": "2.7.1.1", "organism": "human", "substrate": "glucose"},
                "constants-hexokinase-human-glucose")

        # A REAL lookup, outside the recordings: PubChem's compound-name search, through the HTTP layer the
        # literature layer uses. The server notes that the host answered, and says so in /api/capabilities,
        # for that host alone. Nothing is written if it could not be made.
        from caterva.checkout import literature_module

        http_retry = literature_module("http_retry")
        http_retry.clear_memo()
        answer = http_retry.retry_get("https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/gossypol/cids/JSON",
                                      timeout=20)
        assert answer.status_code == 200, f"PubChem answered {answer.status_code}"
        capabilities = get_json(app, "/api/capabilities")
        network = capabilities["body"]["network"]
        assert network["source"] == "use" and network["hosts"]["pubchem.ncbi.nlm.nih.gov"] is True
        assert network["hosts"]["rest.uniprot.org"] is None, "one host's answer says nothing about another's"
        write(ENZYMES / "capabilities-after-a-lookup.json", capabilities)

        # A REAL request to UniProt: asked for hexokinase's EC numbers. With UniProt then known to be reachable, a
        # name the nomenclature does not hold is asked of UniProt. If UniProt does not answer, the file that needs
        # it is NOT rewritten and the script says so.
        try:
            answered = literature_module("enzyme_lookup").fetch_ec_numbers_by_name("hexokinase", None, timeout=20)
        except Exception as exc:  # noqa: BLE001 - reported; the file is then kept as it was
            answered = None
            print(f"UniProt did not answer ({type(exc).__name__}); find-pyruvate-kinase-pkm-human.json was NOT rewritten")
        if answered:
            assert get_json(app, "/api/capabilities")["body"]["network"]["hosts"]["rest.uniprot.org"] is True
            write(ENZYMES / "find-pyruvate-kinase-pkm-human.json",
                  get_json(app, f"/api/enzymes/find?q={quote('pyruvate kinase PKM')}&organism=human"))

        # Structures: the name policy changed what these two answer, so they are written again.
        with structure_recordings():
            for request, name in [
                ({"subject": "L-lactate dehydrogenase A chain", "organism": "human", "gene": "LDHA", "top": 8,
                  "chimerax": True}, "structure-by-name-ldha"),
                ({"subject": "lactate dehydrogenase"}, "structure-name-several-enzymes"),
            ]:
                spec = app.registry.get("structure")
                from caterva.studio import contract
                from caterva.studio.adapters import RunContext

                class Progress:
                    def stage(self, *a: Any, **k: Any) -> None: ...
                    def log(self, line: str) -> None: ...
                    def check_cancelled(self) -> None: ...

                argv = spec.argv(request)
                d = work / "runs" / "20260930-120000-structure-0badc0de"
                d.mkdir(parents=True, exist_ok=True)
                argv = [a.replace("@RUN_DIR@", str(d)) for a in argv]
                got = spec.run(request, RunContext(d.name, d, work, Progress()))
                write(STRUCTURE / f"{name}.json", {
                    "kind": "structure", "request": request, "cli": [*spec.cli_prefix, *argv],
                    "outcome": contract.outcome_for("structure", got.exit_code, got.summary, got.refusal,
                                                    got.name_refusal),
                    "result": got.result})
    finally:
        app.close()


if __name__ == "__main__":
    main()
