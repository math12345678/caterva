"""Every core route through the dispatch layer, the static page, the socket handler's framing, and the command.

The dispatch layer is a function, so each route of caterva/studio/routes.py
whose owner is core is called here directly (an adapter-owned route is
checked for its 503 until its owner registers it, and for how its
refusals map to statuses). The socket handler is driven over a socket
pair, which needs no port, so its byte-level behaviour (status line,
headers, Content-Length, a refused body never read as the next request,
an event stream written frame by frame) is tested here too. `caterva
studio` itself is run through `main(argv)`: its flag checks, its refusals,
and a whole serve with a server object that listens on nothing, so the
one `CATERVA_STUDIO_URL=` line, the log file and a clean stop are seen
without binding. test_studio_socket.py does the same over a real port.
"""
from __future__ import annotations

import io
import json
import socket
import threading
import time
from pathlib import Path
from typing import List

import pytest

from caterva import __version__
from caterva.studio import __main__ as studio_main
from caterva.studio.adapters import Registry, load_registry
from caterva.studio.contract import (
    SESSION_HEADER, STUDIO_API_VERSION, Health, Malformed, NotFound, Settings, Unavailable,
)
from caterva.studio.dispatch import App, Request
from caterva.studio.routes import ROUTES
from caterva.studio.server import StudioHTTPServer, StudioRequestHandler, bind_address
from caterva.studio.static_files import IMMUTABLE, StaticSite
from caterva.studio.workspace import Workspace

PORT = 18768
TOKEN = "s" * 43
HEADERS = [("Host", f"127.0.0.1:{PORT}"), (SESSION_HEADER, TOKEN)]
INDEX = ('<!doctype html><html><head><meta name="caterva-studio-page" content="token-in-url-fragment" />'
         '<link rel="stylesheet" href="/assets/index-0a1b2c.css"></head><body><div id="root"></div></body></html>')


def _options():
    return dict(head=lambda h, t: None, literature_import=lambda: None, which=lambda n: None,
                is_executable=lambda p: False)


def make_app(tmp_path: Path, *, static=None, registry=None, **kwargs) -> App:
    app = App(workspace=Workspace(tmp_path / "data"), port=PORT, token=TOKEN,
              static_site=StaticSite(static or tmp_path / "no-build"), registry=registry or Registry(),
              capability_options=_options(), **kwargs)
    app.start(apply_environment=False)
    return app


@pytest.fixture
def built(tmp_path: Path) -> Path:
    root = tmp_path / "static"
    (root / "assets").mkdir(parents=True)
    (root / "index.html").write_text(INDEX, encoding="utf-8")
    (root / "assets" / "index-0a1b2c.css").write_text("body{margin:0}\n", encoding="utf-8")
    (root / "assets" / "font.woff2").write_bytes(b"wOF2")
    (root / "favicon.svg").write_text("<svg/>", encoding="utf-8")
    return root


@pytest.fixture
def app(tmp_path: Path, built: Path):
    app = make_app(tmp_path, static=built)
    yield app
    app.close()


def call(app: App, method: str, target: str, body=None, *extra):
    headers = list(HEADERS) + list(extra)
    raw = None
    if body is not None:
        raw = json.dumps(body).encode()
        headers += [("Content-Type", "application/json"), ("Content-Length", str(len(raw)))]
    return app.dispatch(Request(method, target, headers, raw))


# -- meta routes ------------------------------------------------------------------


def test_health_answers_its_contract_shape(app):
    response = call(app, "GET", "/api/health")
    body = response.json()
    assert response.status == 200 and set(body) == set(Health.__required_keys__)
    assert body["ok"] is True and body["version"] == __version__ and body["api_version"] == STUDIO_API_VERSION
    assert body["started_at"] == app.started_at and body["started_at"].endswith("Z")
    assert call(app, "GET", "/api/health?x=1").status == 400


def test_capabilities_and_its_one_query_key(app):
    assert call(app, "GET", "/api/capabilities").json()["network"]["checked"] is False
    assert call(app, "GET", "/api/capabilities?probe=network").json()["network"]["checked"] is True
    for bad in ("probe=all", "refresh=1", "probe=network&probe=network"):
        assert call(app, "GET", f"/api/capabilities?{bad}").status == 400, bad
    assert call(app, "GET", "/api/capabilities").json()["ui"]["built"] is True


def test_settings_read_replace_and_refuse(app, tmp_path):
    settings = call(app, "GET", "/api/settings").json()
    assert set(Settings.__required_keys__) <= set(settings) <= set(Settings.__required_keys__) | set(
        Settings.__optional_keys__)
    new = {"theme": "dark", "max_parallel_runs": 4, "confirm_delete": False}
    stored = call(app, "PUT", "/api/settings", new)
    assert stored.status == 200
    assert stored.json() == {**new, "gromacs_path": None, "offline": False}
    assert json.loads((tmp_path / "data" / "settings.json").read_text()) == stored.json()
    refused = call(app, "PUT", "/api/settings", {**new, "max_parallel_runs": 0})
    assert refused.status == 400 and refused.json()["error"]["field"] == "max_parallel_runs"
    assert call(app, "GET", "/api/settings").json()["max_parallel_runs"] == 4
    assert call(app, "POST", "/api/settings", new).status == 405


def test_offline_setting_changes_capabilities_at_once(app):
    call(app, "PUT", "/api/settings", {"theme": "system", "max_parallel_runs": 2, "confirm_delete": True,
                                       "offline": True})
    network = call(app, "GET", "/api/capabilities?probe=network").json()["network"]
    assert network["checked"] is False and network["reason"].startswith("offline mode is on")


def test_every_core_route_has_a_handler_and_every_adapter_route_answers_503_until_registered(app):
    for route in ROUTES:
        if route.owner == "core":
            assert callable(getattr(app, f"_h_{route.handler}")), route.handler
    assert call(app, "GET", "/api/compose/shapes").status == 503
    assert call(app, "POST", "/api/organisms/normalise", {"name": "human"}).status == 503
    response = call(app, "GET", "/api/structure/1abc/coordinates")
    assert response.status == 503 and "not built yet" in response.json()["error"]["message"]
    assert call(app, "GET", "/api/structure/abcd/coordinates").status == 404  # not a PDB id


def test_an_adapter_endpoints_refusals_map_to_their_statuses(tmp_path):
    answers = {}

    def coordinates(request):
        return answers[request.params["pdb_id"]](request)

    def malformed(r):
        raise Malformed("bad", field="pdb_id")

    def not_found(r):
        raise NotFound("No entry 9zzz at the RCSB")

    def unavailable(r):
        raise Unavailable("the network is not reachable")

    answers.update({"1abc": lambda r: {"pdb_id": r.params["pdb_id"], "query": dict(r.query)},
                    "2abc": malformed, "9zzz": not_found, "3abc": unavailable})
    registry = Registry()
    registry.add_endpoint("structure_coordinates", coordinates, owner="structure")
    with pytest.raises(ValueError):
        registry.add_endpoint("health", coordinates, owner="structure")
    app = make_app(tmp_path, registry=registry)
    try:
        assert call(app, "GET", "/api/structure/1abc/coordinates?model=1").json() == {
            "pdb_id": "1abc", "query": {"model": "1"}}
        assert call(app, "GET", "/api/structure/2abc/coordinates").json()["error"] == {
            "code": "malformed", "message": "bad", "field": "pdb_id"}
        assert call(app, "GET", "/api/structure/9zzz/coordinates").status == 404
        assert call(app, "GET", "/api/structure/3abc/coordinates").status == 503
    finally:
        app.close()


def test_the_real_registry_loads_every_adapter_module(tmp_path):
    registry = load_registry()
    assert set(registry.kinds()) | set(registry.missing()) == {
        "compose", "constants", "sim", "bind", "structure", "prepare", "md.setup", "md.summarise", "analyze",
        "fep.status", "complex.check", "rates"}


def test_a_run_id_that_does_not_exist_is_404_on_every_run_route(app):
    rid = "20260930-141502-compose-3f9a0c1d"
    for method, target in (("GET", f"/api/runs/{rid}"), ("DELETE", f"/api/runs/{rid}"),
                           ("GET", f"/api/runs/{rid}/result"), ("GET", f"/api/runs/{rid}/events"),
                           ("GET", f"/api/runs/{rid}/artifacts/report.md"), ("GET", f"/api/runs/{rid}/bundle")):
        assert call(app, method, target).status == 404, target
    assert call(app, "POST", f"/api/runs/{rid}/cancel", {}).status == 404


# -- the page ---------------------------------------------------------------------------


def test_the_page_holds_no_token_and_its_client_routes_get_the_page(app):
    for target in ("/", "/compose", "/history/20260930-141502-compose-3f9a0c1d", "/index.html"):
        response = call(app, "GET", target)
        assert response.status == 200, target
        assert response.header("Content-Type") == "text/html; charset=utf-8"
        assert TOKEN not in response.body.decode()
        assert 'name="caterva-studio-page"' in response.body.decode()
        assert response.header("Cache-Control") == "no-store"


def test_assets_are_served_with_their_types_and_cached_forever(app):
    css = call(app, "GET", "/assets/index-0a1b2c.css")
    assert css.status == 200 and css.header("Content-Type") == "text/css; charset=utf-8"
    assert css.header("Cache-Control") == IMMUTABLE
    assert css.header("Content-Security-Policy") is None
    assert call(app, "GET", "/assets/font.woff2").header("Content-Type") == "font/woff2"
    svg = call(app, "GET", "/favicon.svg")
    assert svg.header("Content-Type") == "image/svg+xml" and svg.header("Cache-Control") == "no-cache"
    missing = call(app, "GET", "/assets/index-ffffff.js")
    assert missing.status == 404 and missing.json()["error"]["code"] == "not_found"
    assert call(app, "POST", "/compose", {}).status == 405
    assert call(app, "HEAD", "/").status == 200


def test_a_page_not_built_from_this_package_is_a_500_not_a_page_that_cannot_reach_the_server(tmp_path):
    root = tmp_path / "foreign"
    root.mkdir()
    (root / "index.html").write_text("<!doctype html><html><head></head><body>someone else's</body></html>")
    app = make_app(tmp_path, static=root)
    try:
        response = call(app, "GET", "/")
        assert response.status == 500
        assert "not built from this package" in response.json()["error"]["message"]
        assert "no page marker" in call(app, "GET", "/api/capabilities").json()["ui"]["reason"]
    finally:
        app.close()


def test_a_missing_build_gets_the_page_that_says_how_to_build_it(tmp_path):
    app = make_app(tmp_path)
    try:
        response = call(app, "GET", "/")
        text = response.body.decode()
        assert response.status == 200
        assert "pnpm --filter @workspace/caterva-studio run build" in text
        assert "Science-Agent-Pipeline/" in text and "the page is not built" in text
        assert call(app, "GET", "/api/capabilities").json()["ui"]["built"] is False
    finally:
        app.close()


# -- the socket handler, over a socket pair ------------------------------------------------


class _PairServer:
    def __init__(self, app: App) -> None:
        self.app = app


def exchange(app: App, raw: bytes) -> bytes:
    """Send `raw` to a StudioRequestHandler over a socket pair; everything it wrote back."""
    ours, theirs = socket.socketpair()
    ours.settimeout(60)

    def send():
        # From a thread: a request larger than the pair's buffer would
        # otherwise block before the handler starts reading it.
        try:
            ours.sendall(raw)
            ours.shutdown(socket.SHUT_WR)
        except OSError:
            pass  # the handler closed early (a request line too long): its answer is what is tested

    def handle():
        try:
            StudioRequestHandler(theirs, ("127.0.0.1", 50000), _PairServer(app))
        finally:
            theirs.close()

    sender = threading.Thread(target=send, daemon=True)
    handler = threading.Thread(target=handle, daemon=True)
    sender.start()
    handler.start()
    try:
        chunks = []
        while True:
            chunk = ours.recv(65536)
            if not chunk:
                break
            chunks.append(chunk)
        handler.join(60)
        return b"".join(chunks)
    finally:
        ours.close()


def split_response(data: bytes):
    head, _, body = data.partition(b"\r\n\r\n")
    lines = head.decode("latin-1").split("\r\n")
    headers = [tuple(line.split(": ", 1)) for line in lines[1:]]
    return lines[0], headers, body


def test_the_handler_writes_status_headers_and_an_exact_length(app):
    raw = (f"GET /api/health HTTP/1.1\r\nHost: 127.0.0.1:{PORT}\r\n{SESSION_HEADER}: {TOKEN}\r\n\r\n").encode()
    status, headers, body = split_response(exchange(app, raw))
    names = [k.lower() for k, _ in headers]
    assert status == "HTTP/1.1 200 OK"
    assert names.count("server") == 1 and ("Server", "caterva-studio") in headers
    assert ("Content-Length", str(len(body))) in headers
    assert json.loads(body)["ok"] is True
    assert "date" in names


def test_a_refused_body_is_never_read_as_the_next_request(app):
    smuggled = (f"GET /api/settings HTTP/1.1\r\nHost: 127.0.0.1:{PORT}\r\n{SESSION_HEADER}: {TOKEN}\r\n\r\n")
    raw = (f"POST /api/runs HTTP/1.1\r\nHost: 127.0.0.1:{PORT}\r\nContent-Type: application/json\r\n"
           f"Content-Length: {len(smuggled)}\r\n\r\n{smuggled}").encode()
    data = exchange(app, raw)
    assert data.count(b"HTTP/1.1 ") == 1
    status, headers, _ = split_response(data)
    assert status.startswith("HTTP/1.1 401") and ("Connection", "close") in headers


def test_two_requests_on_one_connection_are_both_answered(app):
    one = f"GET /api/health HTTP/1.1\r\nHost: 127.0.0.1:{PORT}\r\n{SESSION_HEADER}: {TOKEN}\r\n\r\n"
    assert exchange(app, (one + one).encode()).count(b"HTTP/1.1 200 OK") == 2


def test_a_head_request_has_headers_and_no_body(app):
    data = exchange(app, f"HEAD / HTTP/1.1\r\nHost: 127.0.0.1:{PORT}\r\n\r\n".encode())
    status, headers, body = split_response(data)
    assert status == "HTTP/1.1 200 OK" and body == b""
    assert int(dict(headers)["Content-Length"]) > 0


def test_an_unknown_method_and_a_broken_request_line_get_json_errors(app):
    status, headers, body = split_response(
        exchange(app, f"PROPFIND /api/health HTTP/1.1\r\nHost: 127.0.0.1:{PORT}\r\n{SESSION_HEADER}: {TOKEN}\r\n\r\n"
                 .encode()))
    assert status.startswith("HTTP/1.1 405") and json.loads(body)["error"]["code"] == "method_not_allowed"
    status, headers, body = split_response(exchange(app, b"GARBAGE\r\n\r\n"))
    assert " 400 " in status
    assert json.loads(body)["error"]["code"] == "malformed"
    assert ("X-Frame-Options", "DENY") in headers
    status, _, body = split_response(exchange(app, b"GET /" + b"a" * 70000 + b" HTTP/1.1\r\n\r\n"))
    assert " 400 " in status and json.loads(body)["error"]["code"] == "malformed"


def test_an_event_stream_is_written_frame_by_frame_and_closed(tmp_path):
    from caterva.tests.test_studio_jobs import Gate, spec

    gate = Gate()
    registry = Registry()
    registry.register(spec("compose", gate.run))
    app = make_app(tmp_path, registry=registry, job_options=dict(keepalive_s=0.2, poll_s=0.05, tick_s=0.02))
    try:
        created = call(app, "POST", "/api/runs", {"kind": "compose", "request": {}})
        rid = created.json()["run"]["id"]
        gate.release.set()
        raw = (f"GET /api/runs/{rid}/events HTTP/1.1\r\nHost: 127.0.0.1:{PORT}\r\n{SESSION_HEADER}: {TOKEN}\r\n"
               "\r\n").encode()
        status, headers, body = split_response(exchange(app, raw))
        assert status == "HTTP/1.1 200 OK"
        assert ("Content-Type", "text/event-stream; charset=utf-8") in headers
        assert ("Connection", "close") in headers
        assert "content-length" not in [k.lower() for k, _ in headers]
        frames = body.decode().split("\n\n")
        assert frames[-1] == ""
        assert [f.split("\n")[1] for f in frames[:-1] if not f.startswith(":")][-1] == "event: end"
    finally:
        app.close()


def test_a_page_that_goes_away_ends_its_stream(app):
    closed = threading.Event()

    def frames():
        try:
            while True:
                yield b": keep-alive\n\n"
                time.sleep(0.01)
        finally:
            closed.set()

    from caterva.studio.dispatch import Response

    original = app.dispatch
    app.dispatch = lambda request: Response(200, [("Content-Type", "text/event-stream")], stream=frames())
    ours, theirs = socket.socketpair()
    try:
        ours.sendall(f"GET /x HTTP/1.1\r\nHost: 127.0.0.1:{PORT}\r\n\r\n".encode())
        worker = threading.Thread(target=StudioRequestHandler,
                                  args=(theirs, ("127.0.0.1", 50000), _PairServer(app)), daemon=True)
        worker.start()
        assert ours.recv(1024).startswith(b"HTTP/1.1 200")
        ours.close()
        assert closed.wait(10)
        worker.join(10)
        assert not worker.is_alive()
    finally:
        app.dispatch = original
        theirs.close()


def test_localhost_is_bound_as_its_numeric_address():
    assert bind_address("localhost") == (socket.AF_INET, "127.0.0.1")
    assert bind_address("::1") == (socket.AF_INET6, "::1")
    with pytest.raises(ValueError):
        bind_address("0.0.0.0")


# -- the command ------------------------------------------------------------------------------


@pytest.mark.parametrize("argv,words", [
    (["--host", "0.0.0.0"], "is not a loopback address"),
    (["--host", "192.168.1.5"], "is not a loopback address"),
    (["--port", "70000"], "is not a port number"),
    (["--port", "-1"], "is not a port number"),
    (["--port", "eighty"], "invalid int value"),
    (["--dev-origin", "http://evil.example:5173"], "is not a loopback origin"),
    (["--dev-origin", "http://127.0.0.1:5173/path"], "is not a loopback origin"),
    (["--dev-origin", "https://127.0.0.1:5173"], "is not a loopback origin"),
    (["--data-dir", " "], "--data-dir needs a path"),
    (["--no-such-flag"], "unrecognized arguments"),
])
def test_a_malformed_command_line_exits_2_saying_why(argv, words, capsys):
    with pytest.raises(SystemExit) as exited:
        studio_main.main(argv)
    assert exited.value.code == 2
    assert words in capsys.readouterr().err


def test_help_names_every_flag(capsys):
    with pytest.raises(SystemExit) as exited:
        studio_main.main(["--help"])
    assert exited.value.code == 0
    text = capsys.readouterr().out
    for flag in ("--host", "--port", "--no-browser", "--dev-origin", "--data-dir", "--print-url", "--self-test"):
        assert flag in text


def test_a_data_folder_that_cannot_be_written_exits_3(tmp_path, capsys):
    blocker = tmp_path / "file"
    blocker.write_text("x")
    assert studio_main.main(["--no-browser", "--data-dir", str(blocker / "data")]) == 3
    assert "refused: the data folder" in capsys.readouterr().err


@pytest.mark.parametrize("errno_value,words", [(48, "is already in use"), (1, "refused to let the studio listen")])
def test_a_port_that_cannot_be_bound_exits_3(tmp_path, capsys, monkeypatch, errno_value, words):
    import errno as errno_module

    code = errno_module.EADDRINUSE if errno_value == 48 else errno_module.EPERM

    def refuse(host, port):
        raise OSError(code, "refused here")

    monkeypatch.setattr("caterva.studio.server.StudioHTTPServer", refuse)
    assert studio_main.main(["--no-browser", "--port", "18799", "--data-dir", str(tmp_path / "d")]) == 3
    assert words in capsys.readouterr().err


class _QuietServer:
    """Stands in for StudioHTTPServer: everything but listening."""

    def __init__(self, host, port):
        self.port = port or 18790
        self.app = None
        self._stopped = threading.Event()

    def serve_forever(self, poll_interval=0.5):
        self._stopped.wait()

    def shutdown(self):
        self._stopped.set()

    def server_close(self):
        pass


def test_serving_prints_exactly_the_url_line_logs_to_the_data_folder_and_stops_cleanly(tmp_path, monkeypatch):
    import sys

    monkeypatch.setattr("caterva.studio.server.StudioHTTPServer", _QuietServer)
    out, err = io.StringIO(), io.StringIO()
    monkeypatch.setattr(sys, "stdout", out)
    monkeypatch.setattr(sys, "stderr", err)
    stop = threading.Event()
    seen: List[App] = []

    def serving(app):
        seen.append(app)
        print("a stray print while serving")  # routed: never on stdout
        stop.set()

    code = studio_main.main(["--port", "0", "--no-browser", "--print-url", "--data-dir", str(tmp_path / "data")],
                            stop=stop, on_serving=serving)
    assert code == 0
    assert out.getvalue() == f"CATERVA_STUDIO_URL=http://127.0.0.1:18790/#token={seen[0].token}\n"
    assert "a stray print while serving" in err.getvalue()
    log = (tmp_path / "data" / "studio.log").read_text()
    assert "serving http://127.0.0.1:18790/" in log and "stopped" in log
    assert seen[0].token not in log and seen[0].token not in err.getvalue()  # only the URL line holds it
    assert sys.stdout is out and sys.stderr is err


def test_the_parent_dying_or_stdin_closing_stops_the_server():
    import os

    stop = threading.Event()
    parent = [100]
    studio_main.watch_parent(stop, stdin_fd=None, getppid=lambda: parent[0], poll_s=0.01)
    time.sleep(0.05)
    assert not stop.is_set()
    parent[0] = 1
    assert stop.wait(5)

    stop = threading.Event()
    read_end, write_end = os.pipe()
    try:
        assert studio_main.stdin_is_pipe(read_end)
        studio_main.watch_parent(stop, stdin_fd=read_end, getppid=lambda: 100, poll_s=0.01)
        os.write(write_end, b"anything the shell writes is ignored\n")
        time.sleep(0.05)
        assert not stop.is_set()
        os.close(write_end)
        write_end = -1
        assert stop.wait(5)
    finally:
        if write_end >= 0:
            os.close(write_end)
        os.close(read_end)


def test_a_terminal_or_dev_null_is_not_a_pipe():
    import os

    fd = os.open(os.devnull, os.O_RDONLY)
    try:
        assert not studio_main.stdin_is_pipe(fd)
    finally:
        os.close(fd)


def test_the_self_test_reports_a_server_that_could_not_start(tmp_path, monkeypatch, capsys):
    import errno as errno_module

    def refuse(host, port):
        raise OSError(errno_module.EPERM, "Operation not permitted")

    monkeypatch.setattr("caterva.studio.server.StudioHTTPServer", refuse)
    assert studio_main.main(["--self-test", "--data-dir", str(tmp_path / "d")]) == 1
    out = capsys.readouterr().out
    assert out.startswith("FAIL start: ") and "refused to let the studio listen" in out
    assert len(out.strip().splitlines()) == 1


def test_a_peer_that_leaves_is_logged_quietly_and_a_fault_is_not(caplog):
    # handle_error is called by socketserver inside the except block that
    # caught the exception; the server itself is not needed to decide.
    caplog.set_level("DEBUG", logger="caterva.studio")
    try:
        raise ConnectionResetError(54, "Connection reset by peer")
    except ConnectionResetError:
        StudioHTTPServer.handle_error(None, None, ("127.0.0.1", 50000))
    left = [r for r in caplog.records if "127.0.0.1" in r.getMessage()]
    assert [(r.levelname, r.exc_info) for r in left] == [("DEBUG", None)]
    assert "closed from its end" in left[0].getMessage()

    caplog.clear()
    try:
        raise ValueError("a fault in the handler")
    except ValueError:
        StudioHTTPServer.handle_error(None, None, ("127.0.0.1", 50001))
    fault = [r for r in caplog.records if "127.0.0.1" in r.getMessage()]
    assert [r.levelname for r in fault] == ["ERROR"]
    assert fault[0].exc_info is not None and fault[0].exc_info[0] is ValueError

