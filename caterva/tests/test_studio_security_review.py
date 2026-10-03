"""Regression tests for the security review of Caterva Studio.

Each test reproduces one attack the reviewer proved through the dispatch
layer (no socket is needed) and asserts that it no longer works. They are
grouped by finding: S1 to S11 in the review, and the SECURITY section of
docs/studio/CONTRACT.md records the rules they protect.
"""
from __future__ import annotations

import io
import json
import os
import stat
import threading
from pathlib import Path
from types import SimpleNamespace
from typing import Any, List

import pytest

from caterva.studio import __main__ as studio_main
from caterva.studio.adapters import Registry
from caterva.studio.contract import SESSION_HEADER
from caterva.studio.dispatch import App, Request
from caterva.studio.security import bootstrap_url, mint_token
from caterva.studio.static_files import StaticSite
from caterva.studio.workspace import Workspace

PORT = 18771
TOKEN = mint_token()
HOST = ("Host", f"127.0.0.1:{PORT}")
AUTH = (SESSION_HEADER, TOKEN)
INDEX = ('<!doctype html><html><head><meta name="caterva-studio-page" content="token-in-url-fragment">'
         '<script type="module" src="/assets/index-abc.js"></script></head><body></body></html>')

GMX_OUT = "GROMACS version:    2025.3\n"


def make_app(tmp_path: Path, *, run=None, registry=None, job_options=None, **kwargs: Any) -> App:
    static = tmp_path / "static"
    (static / "assets").mkdir(parents=True, exist_ok=True)
    (static / "index.html").write_text(INDEX, encoding="utf-8")
    (static / "assets" / "index-abc.js").write_text("export const ok = true;\n", encoding="utf-8")
    options = dict(head=lambda host, timeout: None, literature_import=lambda: None, which=lambda name: None,
                   is_executable=lambda path: False)
    if run is not None:
        options["run"] = run
    app = App(workspace=Workspace(tmp_path / "data"), port=PORT, token=TOKEN, static_site=StaticSite(static),
              registry=registry or Registry(), capability_options=options, job_options=job_options, **kwargs)
    app.start(apply_environment=False)
    return app


def req(app: App, method: str, target: str, body: Any = None, *, token: bool = True, extra=()):
    headers = [HOST] + ([AUTH] if token else []) + list(extra)
    raw = None
    if body is not None:
        raw = json.dumps(body).encode()
        headers += [("Content-Type", "application/json"), ("Content-Length", str(len(raw)))]
    return app.dispatch(Request(method, target, headers, raw))


def program(path: Path, mode: int = 0o755) -> Path:
    path.write_text("#!/bin/sh\necho 'GROMACS version: 2025.3'\n")
    path.chmod(mode)
    return path


@pytest.fixture
def app(tmp_path):
    app = make_app(tmp_path)
    yield app
    app.close()


# ---------------------------------------------------------------------------
# S1: the session token is in no document the server serves
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", ["/", "/compose", "/index.html", "/assets/index-abc.js", "/history/x"])
def test_s1_no_document_the_server_serves_holds_the_token(app, path):
    response = req(app, "GET", path, token=False)
    assert response.status in (200, 404)
    assert TOKEN.encode() not in response.body
    assert TOKEN not in json.dumps(response.headers)


def test_s1_the_built_page_never_carries_a_placeholder_or_a_session_tag(app):
    body = req(app, "GET", "/", token=False).body.decode()
    assert "__CATERVA_SESSION_TOKEN__" not in body and 'name="caterva-session"' not in body


def test_s1_a_stranger_with_only_a_valid_host_cannot_reach_a_gromacs_run(tmp_path):
    """The reviewer's chain: GET / for the token, PUT settings, GET capabilities."""
    ran: List[Any] = []
    evil = program(tmp_path / "evil.sh")
    app = make_app(tmp_path, run=lambda *a, **k: ran.append(a))
    try:
        assert req(app, "GET", "/", token=False).status == 200  # nothing in it to use
        refused = req(app, "PUT", "/api/settings", {"theme": "system", "max_parallel_runs": 2,
                                                    "confirm_delete": True, "gromacs_path": str(evil)},
                      token=False)
        assert refused.status == 401
        assert req(app, "GET", "/api/capabilities", token=False).status == 401
        assert ran == []
    finally:
        app.close()


def test_s1_the_address_for_the_launcher_carries_the_token_in_its_fragment(app):
    url = app.bootstrap_url
    assert url == f"http://127.0.0.1:{PORT}/#token={TOKEN}"
    assert url == bootstrap_url("127.0.0.1", PORT, TOKEN)
    assert "#" not in app.url and TOKEN not in app.url
    assert bootstrap_url("::1", 7, "abc") == "http://[::1]:7/#token=abc"


def test_s1_the_printed_line_has_the_token_and_the_log_and_stderr_do_not(tmp_path, monkeypatch):
    import sys

    from caterva.studio import server as server_module

    class QuietServer(server_module.StudioHTTPServer):
        def __init__(self, host, port):  # no socket: the sandbox cannot bind
            self.app = None
            self.address_family = 2
            self.server_address = (host, 18791)

        @property
        def port(self):
            return 18791

        def serve_forever(self, poll_interval=0.5):
            pass

        def shutdown(self):
            pass

        def server_close(self):
            pass

    monkeypatch.setattr(server_module, "StudioHTTPServer", QuietServer)
    out, err = io.StringIO(), io.StringIO()
    monkeypatch.setattr(sys, "stdout", out)
    monkeypatch.setattr(sys, "stderr", err)
    stop = threading.Event()
    seen: List[App] = []

    def serving(app):
        seen.append(app)
        stop.set()

    code = studio_main.main(["--port", "0", "--no-browser", "--print-url", "--data-dir", str(tmp_path / "d")],
                            stop=stop, on_serving=serving)
    assert code == 0
    token = seen[0].token
    assert out.getvalue() == f"CATERVA_STUDIO_URL=http://127.0.0.1:18791/#token={token}\n"
    assert token not in err.getvalue()
    assert token not in (tmp_path / "d" / "studio.log").read_text()


def test_s1_the_browser_is_given_a_private_file_not_an_argument_with_the_token(tmp_path):
    opened: List[str] = []
    app = SimpleNamespace(bootstrap_url=f"http://127.0.0.1:{PORT}/#token={TOKEN}", url=f"http://127.0.0.1:{PORT}/")
    studio_main._open_browser(app, tmp_path, opener=lambda url: opened.append(url) or True, ttl_s=0.05)
    assert len(opened) == 1 and opened[0].startswith("file://") and TOKEN not in opened[0]
    page = Path(opened[0][len("file://"):])
    from urllib.parse import unquote
    page = Path(unquote(str(page)))
    assert page.name.startswith(".open-studio-")
    assert f"#token={TOKEN}" in page.read_text()
    assert stat.S_IMODE(page.stat().st_mode) == 0o600
    deadline = 50
    while page.exists() and deadline:
        threading.Event().wait(0.05)
        deadline -= 1
    assert not page.exists()


def test_s1_a_browser_that_cannot_open_logs_the_address_without_the_token(tmp_path, caplog):
    app = SimpleNamespace(bootstrap_url=f"http://127.0.0.1:{PORT}/#token={TOKEN}", url=f"http://127.0.0.1:{PORT}/")
    with caplog.at_level("WARNING", logger="caterva.studio"):
        studio_main._open_browser(app, tmp_path, opener=lambda url: False, ttl_s=0.05)
    assert "--print-url" in caplog.text and TOKEN not in caplog.text


def test_s1_the_launch_page_is_not_written_through_a_planted_link(tmp_path):
    target = tmp_path / "victim.txt"
    target.write_text("keep")
    real = studio_main.secrets.token_hex
    studio_main.secrets.token_hex = lambda n=8: "fixed"
    try:
        (tmp_path / ".open-studio-fixed.html").symlink_to(target)
        with pytest.raises(OSError):
            studio_main.write_launch_page(tmp_path, "http://127.0.0.1:1/#token=x")
    finally:
        studio_main.secrets.token_hex = real
    assert target.read_text() == "keep"


# -- gromacs_path -----------------------------------------------------------------------


def put_gmx(app: App, path: str):
    return req(app, "PUT", "/api/settings", {"theme": "system", "max_parallel_runs": 2, "confirm_delete": True,
                                             "gromacs_path": path})


@pytest.mark.parametrize("name", ["gmx", "gmx_mpi", "gmx_d", "gmx_custom"])
def test_s1_a_gmx_program_named_like_gromacs_is_accepted(app, tmp_path, name):
    gmx = program(tmp_path / "bin" / name) if (tmp_path / "bin").mkdir() is None else None
    assert put_gmx(app, str(gmx)).status == 200


@pytest.mark.parametrize("name", ["evil.sh", "gmxevil", "mdrun", "gmx.sh", "xgmx", "gmx_"])
def test_s1_a_program_with_any_other_name_is_refused(app, tmp_path, name):
    other = program(tmp_path / name)
    response = put_gmx(app, str(other))
    assert response.status == 400 and response.json()["error"]["field"] == "gromacs_path"


def test_s1_a_link_named_gmx_to_another_program_is_refused(app, tmp_path):
    evil = program(tmp_path / "evil.sh")
    link = tmp_path / "gmx"
    link.symlink_to(evil)
    response = put_gmx(app, str(link))
    assert response.status == 400 and "link" in response.json()["error"]["message"]


def test_s1_a_world_writable_program_or_folder_is_refused(app, tmp_path):
    loose = program(tmp_path / "gmx", 0o777)
    assert put_gmx(app, str(loose)).status == 400
    folder = tmp_path / "open"
    folder.mkdir()
    inside = program(folder / "gmx")
    folder.chmod(0o777)
    try:
        assert put_gmx(app, str(inside)).status == 400
    finally:
        folder.chmod(0o755)


def test_s1_relative_dotdot_directory_and_non_executable_paths_are_refused(app, tmp_path):
    good = program(tmp_path / "gmx")
    assert put_gmx(app, "gmx").status == 400
    assert put_gmx(app, f"{tmp_path}/sub/../gmx").status == 400
    assert put_gmx(app, str(tmp_path)).status == 400
    plain = tmp_path / "other" / "gmx"
    plain.parent.mkdir()
    plain.write_text("x")
    plain.chmod(0o644)
    assert put_gmx(app, str(plain)).status == 400
    assert put_gmx(app, str(good)).status == 200


def test_s1_reading_capabilities_never_runs_the_chosen_program(tmp_path):
    ran: List[list] = []

    def run(argv, **kwargs):
        ran.append(list(argv))
        return SimpleNamespace(returncode=0, stdout=GMX_OUT, stderr="")

    gmx = program(tmp_path / "gmx")
    app = make_app(tmp_path, run=run)
    try:
        assert put_gmx(app, str(gmx)).status == 200
        assert ran == [[str(gmx), "--version"]]  # the explicit save probed it once, as an argument list
        for _ in range(3):
            assert req(app, "GET", "/api/capabilities").json()["gromacs"]["found"] is True
        assert len(ran) == 1
        # A restart: the saved path is known, and reading capabilities still runs nothing.
        again = make_app(tmp_path, run=run)
        try:
            body = req(again, "GET", "/api/capabilities").json()["gromacs"]
            assert body["found"] is False and "has not been checked" in body["reason"]
            assert len(ran) == 1
            refreshed = req(again, "POST", "/api/capabilities/refresh", {})
            assert refreshed.status == 200 and refreshed.json()["gromacs"]["found"] is True
            assert len(ran) == 2
            assert req(again, "POST", "/api/capabilities/refresh", {"x": 1}).status == 400
            assert req(again, "POST", "/api/capabilities/refresh", {}, token=False).status == 401
        finally:
            again.close()
    finally:
        app.close()


def test_s1_a_chosen_program_that_changed_after_it_was_saved_is_validated_again_before_it_runs(tmp_path):
    ran: List[list] = []
    gmx = program(tmp_path / "gmx")
    app = make_app(tmp_path, run=lambda argv, **k: ran.append(list(argv)) or SimpleNamespace(
        returncode=0, stdout=GMX_OUT, stderr=""))
    try:
        assert put_gmx(app, str(gmx)).status == 200
        ran.clear()
        gmx.chmod(0o777)  # someone made it writable by everyone afterwards
        body = req(app, "POST", "/api/capabilities/refresh", {}).json()["gromacs"]
        assert body["found"] is False and "is not run" in body["reason"] and ran == []
    finally:
        app.close()


# ---------------------------------------------------------------------------
# S8: the development origin
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("text,ok", [
    ("http://127.0.0.1:18741", True), ("http://localhost:5173", True), ("http://127.0.0.1:65535", True),
    ("http://127.0.0.1:1", True),
    ("http://127.0.0.1:18741\n", False), ("http://127.0.0.1:0", False), ("http://127.0.0.1:99999", False),
    ("http://127.0.0.1:65536", False), ("http://127.0.0.1:18741/", False), ("https://127.0.0.1:18741", False),
    ("http://127.0.0.1:١٨٧٤١", False), ("http://example.com:80", False), (" http://127.0.0.1:18741", False),
])
def test_s8_the_dev_origin_is_a_whole_loopback_origin_with_a_real_port(text, ok):
    assert studio_main.valid_dev_origin(text) is ok


@pytest.mark.parametrize("bad", ["http://127.0.0.1:18741\n", "http://127.0.0.1:0", "http://127.0.0.1:99999"])
def test_s8_the_command_line_refuses_them_with_exit_2(bad, capsys):
    with pytest.raises(SystemExit) as stopped:
        studio_main.main(["--dev-origin", bad, "--no-browser"])
    assert stopped.value.code == 2
