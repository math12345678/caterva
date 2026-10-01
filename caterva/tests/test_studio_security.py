"""The studio's security rules, each tried against the pure dispatch layer.

A local server is reachable by every page the user has open, so each rule
of docs/studio/CONTRACT.md section 3 is exercised here with the request a
hostile page (or a confused one) would actually send: a rebinding page's
Host, a foreign Origin, a cross-site fetch, a request without the session
token or with the token in the URL, a path that climbs out of the static
folder in each spelling a browser or a script can produce, a body that is
too large or not JSON. No port is bound; test_studio_socket.py repeats the
important ones over a real socket.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from caterva.studio.adapters import Registry
from caterva.studio.contract import MAX_BODY_BYTES, SESSION_HEADER, TOKEN_PLACEHOLDER
from caterva.studio.dispatch import App, Request
from caterva.studio.security import CSP, Guard, authorities, mint_token, url_for
from caterva.studio.static_files import StaticSite
from caterva.studio.workspace import Workspace

PORT = 18765
TOKEN = mint_token()
HOST = ("Host", f"127.0.0.1:{PORT}")
AUTH = (SESSION_HEADER, TOKEN)
INDEX = (f'<!doctype html><html><head><meta name="caterva-session" content="{TOKEN_PLACEHOLDER}">'
         '<script type="module" src="/assets/index-abc123.js"></script></head><body></body></html>')


def _capability_options():
    return dict(head=lambda host, timeout: None, literature_import=lambda: None, which=lambda name: None,
                is_executable=lambda path: False)


@pytest.fixture
def static_dir(tmp_path: Path) -> Path:
    root = tmp_path / "static"
    (root / "assets").mkdir(parents=True)
    (root / "index.html").write_text(INDEX, encoding="utf-8")
    (root / "assets" / "index-abc123.js").write_text("export const ok = true;\n", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("outside the static folder\n", encoding="utf-8")
    return root


def _app(tmp_path: Path, static_dir: Path, **kwargs) -> App:
    app = App(workspace=Workspace(tmp_path / "data"), port=PORT, token=TOKEN, static_site=StaticSite(static_dir),
              registry=Registry(), capability_options=_capability_options(), **kwargs)
    app.start(apply_environment=False)
    return app


@pytest.fixture
def app(tmp_path: Path, static_dir: Path):
    app = _app(tmp_path, static_dir)
    yield app
    app.close()


@pytest.fixture
def dev_app(tmp_path: Path, static_dir: Path):
    app = _app(tmp_path, static_dir, dev_origin="http://127.0.0.1:18766")
    yield app
    app.close()


def get(app: App, target: str, *headers) -> "object":
    return app.dispatch(Request("GET", target, list(headers)))


def post(app: App, target: str, body: bytes, *headers, content_type="application/json"):
    head = [HOST, AUTH, ("Content-Length", str(len(body)))]
    if content_type is not None:
        head.append(("Content-Type", content_type))
    return app.dispatch(Request("POST", target, head + list(headers), body))


def error_code(response) -> str:
    return response.json()["error"]["code"]


# -- the token ----------------------------------------------------------------


def test_each_launch_mints_a_different_unguessable_token():
    tokens = {mint_token() for _ in range(50)}
    assert len(tokens) == 50
    assert all(len(t) >= 43 for t in tokens)  # 32 random bytes, URL-safe base64


def test_the_guard_never_shows_its_token_in_its_repr():
    assert TOKEN not in repr(Guard("127.0.0.1", PORT, TOKEN))


# -- rule 2: the Host header ---------------------------------------------------


def test_a_request_naming_the_bound_address_is_served(app):
    assert get(app, "/api/health", HOST, AUTH).status == 200
    assert get(app, "/api/health", ("Host", f"localhost:{PORT}"), AUTH).status == 200


@pytest.mark.parametrize("host", [f"evil.example:{PORT}", f"127.0.0.1:{PORT + 1}", "127.0.0.1", f"0.0.0.0:{PORT}",
                                  f"[::1]:{PORT}", f"127.0.0.1.nip.io:{PORT}", ""])
def test_a_rebinding_page_is_refused_by_its_host_header(app, host):
    response = get(app, "/api/health", ("Host", host), AUTH)
    assert response.status == 403
    assert error_code(response) == "forbidden"
    assert host not in response.body.decode() or host == ""


def test_the_page_itself_is_refused_to_a_forged_host_because_it_carries_the_token(app):
    response = get(app, "/", ("Host", f"evil.example:{PORT}"))
    assert response.status == 403
    assert TOKEN.encode() not in response.body


def test_a_request_without_a_host_or_with_two_is_refused(app):
    assert get(app, "/api/health", AUTH).status == 403
    assert get(app, "/api/health", HOST, ("Host", f"evil.example:{PORT}"), AUTH).status == 403


def test_the_authorities_for_each_loopback_host():
    assert authorities("127.0.0.1", 5) == {"127.0.0.1:5", "localhost:5"}
    assert authorities("::1", 5) == {"[::1]:5", "localhost:5"}
    assert authorities("localhost", 5) == {"localhost:5", "127.0.0.1:5"}
    with pytest.raises(ValueError):
        authorities("0.0.0.0", 5)
    assert url_for("::1", 5) == "http://[::1]:5/"


# -- rule 3: Origin and Sec-Fetch-Site ------------------------------------------


def test_the_servers_own_origin_is_accepted(app):
    assert get(app, "/api/health", HOST, AUTH, ("Origin", f"http://127.0.0.1:{PORT}")).status == 200


@pytest.mark.parametrize("origin", ["https://evil.example", f"http://127.0.0.1:{PORT + 1}", "null",
                                    f"https://127.0.0.1:{PORT}", "http://127.0.0.1:18766"])
def test_a_foreign_origin_is_refused(app, origin):
    response = get(app, "/api/health", HOST, AUTH, ("Origin", origin))
    assert response.status == 403
    assert error_code(response) == "forbidden"


def test_a_cross_site_fetch_is_refused_whatever_its_origin_says(app):
    response = get(app, "/api/health", HOST, AUTH, ("Origin", f"http://127.0.0.1:{PORT}"),
                   ("Sec-Fetch-Site", "cross-site"))
    assert response.status == 403


def test_the_dev_origin_is_accepted_only_when_given(dev_app, app):
    dev = ("Origin", "http://127.0.0.1:18766")
    assert get(dev_app, "/api/health", HOST, AUTH, dev).status == 200
    assert get(app, "/api/health", HOST, AUTH, dev).status == 403


def test_no_response_ever_grants_cors(app):
    for response in (get(app, "/api/health", HOST, AUTH), get(app, "/api/health", HOST),
                     get(app, "/", HOST), app.dispatch(Request("OPTIONS", "/api/runs", [HOST, AUTH]))):
        assert not [k for k, _ in response.headers if k.lower().startswith("access-control-")]


def test_a_preflight_is_not_answered_as_one(app):
    response = app.dispatch(Request("OPTIONS", "/api/runs", [HOST, AUTH,
                                                            ("Access-Control-Request-Method", "POST")]))
    assert response.status == 405
    assert error_code(response) == "method_not_allowed"


# -- rule 4: the session token ---------------------------------------------------


def test_an_api_request_without_the_token_is_refused_before_routing(app):
    for target in ("/api/health", "/api/runs", "/api/no-such-route", "/api/runs/not-an-id"):
        response = get(app, target, HOST)
        assert response.status == 401, target
        assert error_code(response) == "unauthorized"


def test_a_wrong_or_doubled_token_is_refused(app):
    assert get(app, "/api/health", HOST, (SESSION_HEADER, TOKEN[:-1] + "x")).status == 401
    assert get(app, "/api/health", HOST, (SESSION_HEADER, "")).status == 401
    assert get(app, "/api/health", HOST, AUTH, AUTH).status == 401


def test_the_token_is_never_read_from_the_url_or_a_cookie(app):
    assert get(app, f"/api/health?{SESSION_HEADER}={TOKEN}", HOST).status == 401
    assert get(app, f"/api/health?token={TOKEN}", HOST).status == 401
    assert get(app, "/api/health", HOST, ("Cookie", f"{SESSION_HEADER}={TOKEN}")).status == 401


def test_static_files_need_no_token_and_the_page_carries_it(app):
    response = get(app, "/", HOST)
    assert response.status == 200
    body = response.body.decode()
    assert f'content="{TOKEN}"' in body and TOKEN_PLACEHOLDER not in body


def test_the_dev_session_exists_only_with_a_dev_origin(app, dev_app):
    assert get(app, "/api/dev/session", HOST).status == 401  # no such route, and no token
    assert get(app, "/api/dev/session", HOST, AUTH).status == 404
    response = get(dev_app, "/api/dev/session", HOST)
    assert response.status == 200
    assert response.json() == {"token": TOKEN, "api_version": 1}


@pytest.mark.parametrize("headers", [
    [("Origin", "http://127.0.0.1:18766")],
    [("Origin", f"http://127.0.0.1:{PORT}")],
    [("Sec-Fetch-Site", "same-origin")],
    [("Sec-Fetch-Site", "cross-site")],
])
def test_the_dev_session_is_never_given_to_a_web_page(dev_app, headers):
    response = get(dev_app, "/api/dev/session", HOST, *headers)
    assert response.status == 403
    assert TOKEN.encode() not in response.body


# -- rule 5: bodies -------------------------------------------------------------


def test_a_body_that_is_not_json_by_type_is_refused(app):
    for content_type in ("text/plain", "application/x-www-form-urlencoded", "multipart/form-data", None):
        response = post(app, "/api/runs", b'{"kind":"compose","request":{}}', content_type=content_type)
        assert response.status == 415, content_type
        assert error_code(response) == "unsupported_media_type"


def test_an_oversized_body_is_refused_from_its_length_before_it_is_read(app):
    reads = []

    def read(n):
        reads.append(n)
        return b"{}"

    response = app.dispatch(Request("POST", "/api/runs", [
        HOST, AUTH, ("Content-Type", "application/json"), ("Content-Length", str(MAX_BODY_BYTES + 1))], read))
    assert response.status == 413
    assert error_code(response) == "too_large"
    assert reads == []


def test_a_body_without_a_length_or_chunked_is_malformed(app):
    response = app.dispatch(Request("POST", "/api/runs", [HOST, AUTH, ("Content-Type", "application/json")],
                                    b"{}"))
    assert response.status == 400
    response = app.dispatch(Request("POST", "/api/runs", [HOST, AUTH, ("Content-Type", "application/json"),
                                                          ("Transfer-Encoding", "chunked")], b"{}"))
    assert response.status == 400


@pytest.mark.parametrize("body", [b"{", b"\xff\xfe", b'{"kind": NaN}', b'{"kind":"a","kind":"b"}',
                                  b"[" * 100000 + b"]" * 100000])
def test_a_body_that_is_not_one_json_document_is_malformed(app, body):
    response = post(app, "/api/runs", body)
    assert response.status == 400
    assert error_code(response) == "malformed"


def test_a_get_with_a_body_is_malformed(app):
    response = app.dispatch(Request("GET", "/api/health", [HOST, AUTH, ("Content-Length", "2")], b"{}"))
    assert response.status == 400


# -- rule 6 and 9: paths ----------------------------------------------------------


@pytest.mark.parametrize("target", [
    "/../secret.txt", "/assets/../../secret.txt", "/%2e%2e/secret.txt", "/%2E%2E/secret.txt",
    "/assets/%2e%2e/%2e%2e/secret.txt", "/..%2fsecret.txt", "/%2e%2e%2fsecret.txt", "/assets/..%5c..%5csecret.txt",
    "/.%2e/secret.txt", "/.hidden", "/assets/%00.js", "//etc/passwd",
])
def test_no_path_reaches_outside_the_static_folder(app, target):
    response = get(app, target, HOST)
    assert b"outside the static folder" not in response.body
    assert b"root:" not in response.body
    assert response.status in (200, 404)
    if response.status == 200:  # a client-side route: index.html, nothing else
        assert response.body.startswith(b"<!doctype html>")


def test_a_symlink_out_of_the_static_folder_is_not_followed(app, static_dir: Path, tmp_path: Path):
    (static_dir / "assets" / "leak.txt").symlink_to(tmp_path / "secret.txt")
    response = get(app, "/assets/leak.txt", HOST)
    assert response.status == 404
    assert b"outside" not in response.body


def test_a_directory_is_never_listed(app):
    response = get(app, "/assets/", HOST)
    assert b"index-abc123.js" not in response.body
    response = get(app, "/assets", HOST)
    assert b"index-abc123.js" not in response.body


def test_a_placeholder_that_does_not_match_its_pattern_is_404_and_not_echoed(app):
    for target in ("/api/runs/..%2f..%2fsettings.json", "/api/runs/<script>", "/api/runs/20260930-141502-compose-zz",
                   "/api/runs/20260930-141502-compose-3f9a0c1d/artifacts/..%2frun.json"):
        response = get(app, target, HOST, AUTH)
        assert response.status == 404, target
        assert b"script" not in response.body and b"settings" not in response.body


def test_an_unknown_api_path_is_404_and_a_known_one_with_another_method_is_405(app):
    assert get(app, "/api/nothing", HOST, AUTH).status == 404
    response = app.dispatch(Request("DELETE", "/api/health", [HOST, AUTH]))
    assert response.status == 405
    assert response.header("Allow") == "GET"


# -- rules 7 and 8: headers --------------------------------------------------------


REQUIRED = {
    "x-content-type-options": "nosniff",
    "referrer-policy": "no-referrer",
    "x-frame-options": "DENY",
    "cross-origin-opener-policy": "same-origin",
    "cross-origin-resource-policy": "same-origin",
    "permissions-policy": "camera=(), microphone=(), geolocation=()",
    "server": "caterva-studio",
}


def test_every_response_carries_the_security_headers_errors_included(app):
    responses = [
        get(app, "/api/health", HOST, AUTH), get(app, "/api/health", HOST), get(app, "/api/health", ("Host", "x:1")),
        get(app, "/", HOST), get(app, "/assets/index-abc123.js", HOST), get(app, "/missing.css", HOST),
        post(app, "/api/runs", b"{", ), app.dispatch(Request("PATCH", "/", [HOST])),
    ]
    for response in responses:
        headers = {k.lower(): v for k, v in response.headers}
        for name, value in REQUIRED.items():
            assert headers.get(name) == value, (response.status, name)
        assert len([k for k, _ in response.headers if k.lower() == "server"]) == 1


def test_api_responses_and_the_page_are_never_cached(app):
    assert get(app, "/api/health", HOST, AUTH).header("Cache-Control") == "no-store"
    assert get(app, "/api/health", HOST).header("Cache-Control") == "no-store"
    assert get(app, "/", HOST).header("Cache-Control") == "no-store"
    assert "immutable" in get(app, "/assets/index-abc123.js", HOST).header("Cache-Control")


def test_html_carries_the_strict_policy_and_nothing_looser(app):
    response = get(app, "/", HOST)
    assert response.header("Content-Security-Policy") == CSP
    assert "unsafe" not in CSP
    assert "frame-ancestors 'none'" in CSP and "script-src 'self'" in CSP


def test_the_not_built_page_allows_only_its_own_style_by_hash(tmp_path: Path):
    app = _app(tmp_path, tmp_path / "no-build")
    try:
        response = get(app, "/", HOST)
        policy = response.header("Content-Security-Policy")
        assert response.status == 200
        assert "style-src 'sha256-" in policy and "unsafe" not in policy and "script-src 'self'" in policy
        assert b"<script" not in response.body
        assert TOKEN.encode() not in response.body
    finally:
        app.close()


def test_an_error_never_carries_a_traceback(app, monkeypatch):
    def boom(call):
        raise RuntimeError("secret internal detail")

    monkeypatch.setattr(app, "_h_health", boom)
    response = get(app, "/api/health", HOST, AUTH)
    assert response.status == 500
    body = response.json()
    assert body == {"error": {"code": "crash", "message": "the server failed while answering: RuntimeError"}}
    assert "Traceback" not in json.dumps(body)
