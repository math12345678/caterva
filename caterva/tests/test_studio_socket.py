"""`caterva studio` over a real loopback socket: the URL line, the page, the token, a stream, the self-test, stopping.

The other studio tests call the dispatch layer, which binds nothing. These
bind a port, because what the macOS shell and a browser depend on can only
be seen through one: that `--print-url` prints the line once the socket
really listens, that a forged Host is refused on the wire, that an event
stream arrives frame by frame, that SIGTERM and a closed stdin stop the
process with exit 0, and that `--self-test` passes.

They run in CI. Where the operating system refuses to bind (a sandbox
that answers `listen` with EPERM), they FAIL, saying so: a skipped socket
test reads as a passed one in a summary, and the socket layer would then
never have been tested anywhere.
"""
from __future__ import annotations

import http.client
import json
import os
import signal
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, List

import pytest

from caterva.studio import __main__ as studio_main
from caterva.studio.contract import SESSION_HEADER, URL_LINE_PREFIX

REPO = Path(__file__).resolve().parents[2]


def can_bind() -> str:
    """'' when a loopback port can be bound here, else the operating system's refusal."""
    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            probe.bind(("127.0.0.1", 0))
            probe.listen(1)
        finally:
            probe.close()
    except OSError as exc:
        return f"{exc.strerror or exc} (errno {exc.errno})"
    return ""


@pytest.fixture(scope="module", autouse=True)
def binding_allowed():
    refusal = can_bind()
    if refusal:
        pytest.fail(f"these tests need a loopback port and this environment refused to bind one: {refusal}. "
                    "They run in CI; a sandbox that forbids listening cannot run them.", pytrace=False)


@pytest.fixture
def served(tmp_path: Path):
    """A real `caterva studio` in this process, on a free port."""
    stop = threading.Event()
    ready = threading.Event()
    holder: List[Any] = []
    result: List[int] = []

    def on_serving(app):
        holder.append(app)
        ready.set()

    def run():
        result.append(studio_main.main(["--port", "0", "--no-browser", "--data-dir", str(tmp_path / "data")],
                                       stop=stop, on_serving=on_serving))
        ready.set()

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    assert ready.wait(120), "the server did not start"
    assert holder, f"the server exited {result}"
    yield holder[0]
    stop.set()
    thread.join(60)
    assert result == [0]


def request(app, method: str, path: str, *, headers=None, body: bytes = None):
    conn = http.client.HTTPConnection("127.0.0.1", app.guard.port, timeout=30)
    try:
        conn.request(method, path, body=body, headers=headers or {})
        response = conn.getresponse()
        return response.status, {k.lower(): v for k, v in response.getheaders()}, response.read()
    finally:
        conn.close()


def test_health_needs_the_token_over_the_wire(served):
    status, headers, body = request(served, "GET", "/api/health", headers={SESSION_HEADER: served.token})
    assert status == 200 and json.loads(body)["ok"] is True
    assert headers["server"] == "caterva-studio"
    assert request(served, "GET", "/api/health")[0] == 401


def test_a_forged_host_is_refused_over_the_wire(served):
    status, _, body = request(served, "GET", "/", headers={"Host": f"evil.example:{served.guard.port}"})
    assert status == 403 and served.token.encode() not in body


def test_the_page_or_the_not_built_page_over_the_wire(served):
    status, headers, body = request(served, "GET", "/")
    assert status == 200 and "content-security-policy" in headers
    built, _ = served.static.built()
    if built:
        assert served.token.encode() not in body and b'name="caterva-studio-page"' in body
    else:
        assert b"the page is not built" in body


def test_a_run_s_events_arrive_over_the_wire(tmp_path, served):
    from caterva.studio.adapters import AdapterOutcome, AdapterSpec

    def run(request, ctx):
        ctx.progress.stage("only", "The only stage")
        return AdapterOutcome(0, {"note": "done"}, "finished")

    served.registry._specs["sim"] = AdapterSpec(kind="sim", title="t", command="caterva sim ssa", needs=(),
                                                argv=lambda r: [], run=run, cli_prefix=("caterva-studio-test",))
    body = json.dumps({"kind": "sim", "request": {}}).encode()
    status, _, created = request(served, "POST", "/api/runs", body=body, headers={
        SESSION_HEADER: served.token, "Content-Type": "application/json"})
    assert status == 202
    rid = json.loads(created)["run"]["id"]
    conn = http.client.HTTPConnection("127.0.0.1", served.guard.port, timeout=30)
    try:
        conn.request("GET", f"/api/runs/{rid}/events", headers={SESSION_HEADER: served.token})
        response = conn.getresponse()
        assert response.status == 200
        assert response.getheader("Content-Type").startswith("text/event-stream")
        text = response.read().decode()
    finally:
        conn.close()
    names = [line[7:] for line in text.split("\n") if line.startswith("event: ")]
    assert names == ["status", "status", "stage", "result", "status", "end"]


def test_print_url_then_sigterm_stops_with_exit_0(tmp_path):
    process = subprocess.Popen(
        [sys.executable, "-m", "caterva.app", "studio", "--port", "0", "--no-browser", "--print-url",
         "--data-dir", str(tmp_path / "data")],
        cwd=REPO, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        line = process.stdout.readline()
        assert line.startswith(URL_LINE_PREFIX + "http://127.0.0.1:") and line.endswith("/\n")
        url = line[len(URL_LINE_PREFIX):].strip()
        port = int(url.rsplit(":", 1)[1].rstrip("/"))
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
        conn.request("GET", "/")
        assert conn.getresponse().status == 200
        conn.close()
        process.send_signal(signal.SIGTERM)
        assert process.wait(60) == 0
        assert process.stdout.read() == ""  # the URL line was the only thing on stdout
    finally:
        if process.poll() is None:
            process.kill()


def test_closing_stdin_stops_a_server_the_app_started(tmp_path):
    process = subprocess.Popen(
        [sys.executable, "-m", "caterva.app", "studio", "--port", "0", "--no-browser", "--print-url",
         "--data-dir", str(tmp_path / "data")],
        cwd=REPO, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        assert process.stdout.readline().startswith(URL_LINE_PREFIX)
        time.sleep(0.5)
        assert process.poll() is None
        process.stdin.close()
        assert process.wait(60) == 0
        assert "stdin closed" in process.stderr.read()
    finally:
        if process.poll() is None:
            process.kill()


def test_a_port_in_use_is_refused_with_exit_3(tmp_path):
    holder = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    holder.bind(("127.0.0.1", 0))
    holder.listen(1)
    try:
        port = holder.getsockname()[1]
        done = subprocess.run(
            [sys.executable, "-m", "caterva.app", "studio", "--port", str(port), "--no-browser",
             "--data-dir", str(tmp_path / "data")],
            cwd=REPO, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=120)
        assert done.returncode == 3
        assert "is already in use" in done.stderr
        assert done.stdout == ""
    finally:
        holder.close()


def test_the_self_test_passes(tmp_path):
    done = subprocess.run([sys.executable, "-m", "caterva.app", "studio", "--self-test"],
                          cwd=REPO, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=300,
                          env={**os.environ, "HOME": str(tmp_path)})
    assert done.returncode == 0, done.stdout + done.stderr
    lines = done.stdout.strip().splitlines()
    assert lines[0].startswith("ok   start: listening on http://127.0.0.1:")
    assert all(line.startswith("ok   ") for line in lines), done.stdout
    assert any(line.startswith("ok   /api/health: 200") for line in lines)
    assert lines[-1] == "ok   stop: the server stopped cleanly"
    assert not (tmp_path / "Library").exists()  # the self-test never touches the user's data folder


def _raw(app, payload: bytes = b"", timeout: float = 10.0) -> socket.socket:
    sock = socket.create_connection(("127.0.0.1", app.guard.port), timeout=timeout)
    if payload:
        sock.sendall(payload)
    return sock


def test_a_connection_over_the_ceiling_is_answered_503_with_retry_after(monkeypatch, tmp_path):
    from caterva.studio import limits

    monkeypatch.setattr(limits, "MAX_CONNECTIONS", 3)
    stop = threading.Event()
    ready = threading.Event()
    holder: List[Any] = []

    def run():
        studio_main.main(["--port", "0", "--no-browser", "--data-dir", str(tmp_path / "data")], stop=stop,
                         on_serving=lambda app: (holder.append(app), ready.set()))

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    assert ready.wait(120)
    app = holder[0]
    held = []
    try:
        for _ in range(3):  # three idle connections, each holding a handler waiting for its request line
            held.append(_raw(app))
        time.sleep(0.3)
        extra = _raw(app)
        extra.settimeout(10)
        answer = extra.recv(4096)
        extra.close()
        assert answer.startswith(b"HTTP/1.1 503") and b"Retry-After: 2" in answer
    finally:
        for sock in held:
            sock.close()
        stop.set()
        thread.join(60)


def test_a_request_dripped_in_slowly_is_cut_off_by_its_total_deadline(monkeypatch, tmp_path):
    from caterva.studio import limits

    monkeypatch.setattr(limits, "HEADER_DEADLINE_S", 1.0)
    stop = threading.Event()
    ready = threading.Event()
    holder: List[Any] = []

    def run():
        studio_main.main(["--port", "0", "--no-browser", "--data-dir", str(tmp_path / "data")], stop=stop,
                         on_serving=lambda app: (holder.append(app), ready.set()))

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    assert ready.wait(120)
    app = holder[0]
    started = time.monotonic()
    sock = _raw(app, f"GET /api/health HTTP/1.1\r\nHost: 127.0.0.1:{app.guard.port}\r\n".encode())
    closed = False
    try:
        for _ in range(40):  # a header byte every 0.3 s, each well inside the idle limit
            time.sleep(0.3)
            try:
                sock.sendall(b"X")
            except OSError:
                closed = True
                break
            sock.settimeout(0.01)
            try:
                if sock.recv(1) == b"":
                    closed = True
                    break
            except (socket.timeout, BlockingIOError):
                pass
    finally:
        sock.close()
        stop.set()
        thread.join(60)
    assert closed and time.monotonic() - started < 8

