"""The studio's pure dispatch layer: (method, target, headers, body) in, a response out.

WHY IT IS A FUNCTION AND NOT A REQUEST HANDLER
----------------------------------------------
Every security rule, every error code and every handler has to be tested,
and the machines these are written on cannot always bind a port (a
sandbox refuses `listen` with EPERM). So nothing in here touches a socket:
`App.dispatch(Request)` takes the method, the raw request target, the
headers as a list of pairs and the body (bytes, or a function that reads
n bytes, so a body over the limit is refused before it is read) and
returns a `Response`. `server.py` only moves bytes between the socket and
this call, and writes an event stream's frames as its iterator yields
them. The tests call `dispatch` directly; the socket tests run the same
thing over a real port where one can be bound.

THE ORDER THE RULES RUN IN (docs/studio/CONTRACT.md section 3)
--------------------------------------------------------------
Host (403), then Origin and Sec-Fetch-Site (403), for every path, static
files included (the page itself holds no token: static_files.py). Then, for /api/:
the session token (401), the body rules (415, 413, 400), and only then the
route (404, 405), so a request without the token learns nothing about
which paths exist. A handler runs last, and anything it raises that is not
one of the contract's refusals is a 500 whose message names the exception
type; the traceback goes to the log, not to the page.

A path parameter that does not match its pattern (a run id, an artifact
name, a PDB id) never matches a route, so it is a 404 and the value is
never echoed back.
"""
from __future__ import annotations

import json
import logging
import re
import secrets
import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterator, List, Mapping, Optional, Sequence, Tuple, Union
from urllib.parse import parse_qsl, unquote, urlsplit

from caterva.studio import limits, routes
from caterva.studio.adapters import EndpointRequest, load_registry
from caterva.studio.capabilities import NOT_BUILT_YET, CapabilityProbe
from caterva.studio.contract import (
    MAX_BODY_BYTES, RUN_KINDS, RUN_STATUSES, SESSION_HEADER, STUDIO_API_VERSION, Malformed, NotFound, Unavailable,
)
from caterva.studio.jobs import Conflict, JobManager, QueueFull
from caterva.studio.security import ARTIFACT_CSP, BASE_HEADERS, CSP, Guard, bootstrap_url, mint_token, url_for
from caterva.studio.static_files import NotFromThisPackage, StaticSite
from caterva.studio.workspace import (
    DEFAULT_LIMIT, MAX_LIMIT, TERMINAL_STATUSES, RunNotFound, Workspace, iso, summary_of, utc_now, validate_settings,
)

log = logging.getLogger("caterva.studio.dispatch")

JSON_TYPE = "application/json; charset=utf-8"
_MEDIA_TYPE = re.compile(r"^[a-z0-9][a-z0-9!#$&^_.+-]*/[a-z0-9][a-z0-9!#$&^_.+-]*(?:\s*;\s*charset=[a-z0-9_-]+)?$", re.I)
MAX_TITLE = 200


# ---------------------------------------------------------------------------
# Requests and responses
# ---------------------------------------------------------------------------


@dataclass
class Request:
    method: str
    #: The raw request target: a path with an optional query, as received.
    target: str
    headers: Sequence[Tuple[str, str]] = ()
    #: The body as bytes, or a function returning the next n bytes of it.
    body: Union[bytes, Callable[[int], bytes], None] = None

    def header_all(self, name: str) -> List[str]:
        lower = name.lower()
        return [v for k, v in self.headers if k.lower() == lower]

    def header(self, name: str) -> Optional[str]:
        values = self.header_all(name)
        return values[0] if values else None

    def read(self, n: int) -> bytes:
        if self.body is None:
            return b""
        if isinstance(self.body, (bytes, bytearray)):
            return bytes(self.body[:n])
        return self.body(n)


@dataclass
class Response:
    status: int
    headers: List[Tuple[str, str]] = field(default_factory=list)
    body: bytes = b""
    #: An event stream: frames the socket layer writes and flushes as they
    #: come, then closes the connection. None for an ordinary response.
    stream: Optional[Iterator[bytes]] = None

    def header(self, name: str) -> Optional[str]:
        lower = name.lower()
        for k, v in self.headers:
            if k.lower() == lower:
                return v
        return None

    def json(self) -> Any:
        return json.loads(self.body.decode("utf-8"))


class ApiFailure(Exception):
    """A refusal a handler raises; becomes an ErrorBody response."""

    def __init__(self, status: int, code: str, message: str, *, field: Optional[str] = None,
                 headers: Sequence[Tuple[str, str]] = ()) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.field = field
        self.headers = tuple(headers)


@dataclass
class _Call:
    route: routes.Route
    params: Dict[str, str]
    query: Dict[str, str]
    body: Any
    request: Request


def json_body(obj: Any) -> bytes:
    return json.dumps(obj, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")


def _with_security(headers: List[Tuple[str, str]]) -> List[Tuple[str, str]]:
    present = {k.lower() for k, _ in headers}
    return headers + [(k, v) for k, v in BASE_HEADERS if k.lower() not in present]


def error_response(status: int, code: str, message: str, *, field: Optional[str] = None,
                   headers: Sequence[Tuple[str, str]] = ()) -> Response:
    error: Dict[str, Any] = {"code": code, "message": message}
    if field is not None:
        error["field"] = field
    return Response(status, _with_security([("Content-Type", JSON_TYPE), ("Cache-Control", "no-store"),
                                            *headers]),
                    json_body({"error": error}))


def json_response(obj: Any, status: int = 200) -> Response:
    return Response(status, _with_security([("Content-Type", JSON_TYPE), ("Cache-Control", "no-store")]),
                    json_body(obj))


def _reject_constant(name: str) -> Any:
    raise ValueError(f"{name} is not a JSON number")


def _no_duplicate_keys(pairs: List[Tuple[str, Any]]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise ValueError(f"the key {key!r} appears twice")
        out[key] = value
    return out


# ---------------------------------------------------------------------------
# The application
# ---------------------------------------------------------------------------


class App:
    """One running studio: its workspace, security guard, runs and page."""

    def __init__(
        self,
        *,
        workspace: Workspace,
        port: int,
        host: str = "127.0.0.1",
        token: Optional[str] = None,
        dev_origin: Optional[str] = None,
        static_site: Optional[StaticSite] = None,
        registry: Any = None,
        instance_id: Optional[str] = None,
        job_options: Optional[Mapping[str, Any]] = None,
        capability_options: Optional[Mapping[str, Any]] = None,
    ) -> None:
        self.ws = workspace
        self.guard = Guard(host, port, token or mint_token(), dev_origin)
        self.static = static_site or StaticSite()
        self.registry = load_registry() if registry is None else registry
        self.instance_id = instance_id or secrets.token_hex(8)
        self.started_at = iso(utc_now())
        self._settings_lock = threading.Lock()
        self._settings, self.settings_note = workspace.load_settings()
        self.manager = JobManager(workspace, self.registry, instance_id=self.instance_id,
                                  parallel=lambda: self.settings()["max_parallel_runs"],
                                  offline=lambda: bool(self.settings().get("offline")),
                                  keep_runs=lambda: int(self.settings().get("keep_runs") or 200),
                                  **dict(job_options or {}))
        #: The bounds on work a request can start (limits.py), one set per server.
        self.finder = limits.SearchGuard()
        self.streams = limits.Gate(limits.MAX_STREAMS)
        self.capabilities = CapabilityProbe(registry=self.registry, workspace=workspace, static_site=self.static,
                                            dev_origin=dev_origin, settings=self.settings,
                                            **dict(capability_options or {}))

    @property
    def token(self) -> str:
        return self.guard.token

    @property
    def url(self) -> str:
        """The server's address, without the token: safe to log."""
        return url_for(self.guard.host, self.guard.port)

    @property
    def bootstrap_url(self) -> str:
        """The address a launcher opens: `url` and the token in the URL
        fragment. Never logged."""
        return bootstrap_url(self.guard.host, self.guard.port, self.token)

    def settings(self) -> Dict[str, Any]:
        with self._settings_lock:
            return dict(self._settings)

    def start(self, *, apply_environment: bool = True) -> List[str]:
        """Before serving: hold this server's claim on the data folder, mark
        runs whose server has gone interrupted, and point $GMX where the
        settings say. Returns the ids of the runs marked interrupted."""
        self.ws.ensure()
        self.ws.claim(self.instance_id)
        swept = self.manager.sweep_interrupted()
        if apply_environment:
            self.capabilities.apply_gromacs_to_environment()
            if self.settings().get("gromacs_path"):
                threading.Thread(target=self.capabilities.refresh_gromacs, name="caterva-gmx-check",
                                 daemon=True).start()
        return swept

    def close(self) -> None:
        """After serving: unfinished runs are marked interrupted and every
        event stream ends."""
        self.manager.shutdown()
        self.capabilities.close()
        self.ws.release()

    # -- dispatch ------------------------------------------------------------

    def dispatch(self, request: Request) -> Response:
        try:
            return self._dispatch(request)
        except ApiFailure as failure:
            return error_response(failure.status, failure.code, failure.message, field=failure.field,
                                  headers=failure.headers)
        except Exception as exc:  # noqa: BLE001 - the contract's 500: named, logged, never a traceback to the page
            log.exception("%s %s failed", request.method, _loggable(request.target))
            return error_response(500, "crash", f"the server failed while answering: {type(exc).__name__}")

    def _dispatch(self, request: Request) -> Response:
        method = request.method.upper()
        if not request.target.startswith("/"):
            return error_response(400, "malformed", "the request target must be a path")
        split = urlsplit(request.target)
        try:
            path = unquote(split.path, errors="strict")
        except UnicodeDecodeError:
            return error_response(400, "malformed", "the path is not UTF-8 once percent-decoded")

        refusal = self.guard.refuse_host(request.header_all("Host"))
        if refusal:
            return error_response(403, "forbidden", refusal)
        refusal = self.guard.refuse_origin(request.header_all("Origin"), request.header_all("Sec-Fetch-Site"))
        if refusal:
            return error_response(403, "forbidden", refusal)

        if path == "/api" or path.startswith("/api/"):
            return self._api(method, path, split.query, request)
        return self._static(method, path)

    # -- the page ------------------------------------------------------------

    def _static(self, method: str, path: str) -> Response:
        if method not in ("GET", "HEAD"):
            return error_response(405, "method_not_allowed", f"{method} is not served for the page",
                                  headers=[("Allow", "GET, HEAD")])
        try:
            answer = self.static.serve(path)
        except NotFromThisPackage as exc:
            log.error("%s", exc)
            return error_response(500, "crash", str(exc))
        if answer.status == 404:
            # A refused or missing path: the same ErrorBody as everywhere else
            # (CONTRACT.md 6), and the path is not echoed.
            return error_response(404, "not_found", "there is no such file in the page")
        headers = [("Content-Type", answer.content_type), ("Cache-Control", answer.cache_control)]
        if answer.csp:
            headers.append(("Content-Security-Policy", answer.csp))
        return Response(answer.status, _with_security(headers), answer.body)

    # -- the API -------------------------------------------------------------

    def _api(self, method: str, path: str, query_string: str, request: Request) -> Response:
        dev = self.guard.dev_origin is not None
        route, params, matched = routes.find(method, path, dev=dev)
        if not (route is not None and not route.token):
            if not self.guard.token_matches(request.header_all(SESSION_HEADER)):
                return error_response(
                    401, "unauthorized",
                    f"this request needs the session token from the address `caterva studio` printed, in the "
                    f"{SESSION_HEADER} header",
                )
        if route is not None and route.handler == "dev_session":
            refusal = self.guard.refuse_dev_session(request.header_all("Origin"),
                                                    request.header_all("Sec-Fetch-Site"))
            if refusal:
                return error_response(403, "forbidden", refusal)

        body = self._body(method, request)

        if route is None:
            if matched:
                allowed = sorted({r.method for r in routes.ROUTES
                                  if (dev or not r.dev_only) and routes.compile_path(r.path).match(path)})
                return error_response(405, "method_not_allowed", f"{method} is not allowed here",
                                      headers=[("Allow", ", ".join(allowed))])
            return error_response(404, "not_found", "there is no such route in the studio's API")

        call = _Call(route, params, _query(query_string), body, request)
        if route.owner == "core":
            response = getattr(self, f"_h_{route.handler}")(call)
        else:
            response = self._adapter_endpoint(call)
        if response.header("Cache-Control") is None:
            response.headers.append(("Cache-Control", "no-store"))
        return response

    def _body(self, method: str, request: Request) -> Any:
        """The parsed JSON body of a POST or PUT, None otherwise (rule 3.5)."""
        encodings = request.header_all("Transfer-Encoding")
        lengths = request.header_all("Content-Length")
        if method not in ("POST", "PUT"):
            if encodings or any(v.strip() not in ("", "0") for v in lengths):
                raise ApiFailure(400, "malformed", f"a {method} request carries no body")
            return None
        media = (request.header("Content-Type") or "").split(";")[0].strip().lower()
        if media != "application/json":
            raise ApiFailure(415, "unsupported_media_type", f"a {method} body must be application/json")
        if encodings:
            raise ApiFailure(400, "malformed", "a body must be sent with Content-Length, not Transfer-Encoding")
        if len(lengths) != 1 or not lengths[0].strip().isdigit():
            raise ApiFailure(400, "malformed", "a request body needs exactly one Content-Length")
        size = int(lengths[0].strip())
        if size > MAX_BODY_BYTES:
            raise ApiFailure(413, "too_large", f"a request body may be at most {MAX_BODY_BYTES:,} bytes; "
                                               f"this one declares {size:,}")
        raw = request.read(size)
        if len(raw) != size:
            raise ApiFailure(400, "malformed", "the body ended before its Content-Length")
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            raise ApiFailure(400, "malformed", "the body is not UTF-8") from None
        try:
            return json.loads(text, parse_constant=_reject_constant, object_pairs_hook=_no_duplicate_keys)
        except RecursionError:
            raise ApiFailure(400, "malformed", "the body nests too deeply to be a request") from None
        except ValueError as exc:
            raise ApiFailure(400, "malformed", f"the body is not valid JSON: {exc}") from None

    def _adapter_endpoint(self, call: _Call) -> Response:
        fn = self.registry.endpoint(call.route.handler)
        if fn is None:
            return error_response(503, "unavailable",
                                  f"{call.route.method} {call.route.path}: {NOT_BUILT_YET}")
        endpoint_request = EndpointRequest(params=call.params, query=call.query, body=call.body,
                                           data_dir=self.ws.root, capabilities=self._what_is_known)
        try:
            if call.route.handler == "find_enzymes":
                # The finder spends CPU on every string it has not seen: at most a few at once, answers
                # kept by normalised query, and a time budget per request (limits.py).
                # The answer also says whether UniProt may be asked, which follows what the studio last
                # learned about the network, so what it learned is part of the key.
                known = self._what_is_known()
                asked = (bool(known["offline"]), (known["network"].get("hosts") or {}).get("rest.uniprot.org") is True,
                         bool((known["literature"] or {}).get("available")))
                key = (limits.normalise_text(call.query.get("q")), limits.normalise_text(call.query.get("organism")),
                       call.query.get("limit"), asked)
                answer = self.finder.run(key, lambda: fn(endpoint_request))
            else:
                answer = fn(endpoint_request)
        except Malformed as exc:
            return error_response(400, "malformed", str(exc), field=exc.field)
        except NotFound as exc:
            return error_response(404, "not_found", str(exc))
        except Unavailable as exc:
            ask = limits.retry_after(exc)
            return error_response(503, "unavailable", str(exc), headers=[ask] if ask else ())
        return json_response(answer)

    def _what_is_known(self) -> Dict[str, Any]:
        """What an adapter's endpoint may ask about this installation without
        a probe: the literature layer and the network as last learned."""
        return {"literature": self.capabilities.literature(), "network": self.capabilities.network(),
                "offline": bool(self.settings().get("offline"))}

    # -- meta handlers -------------------------------------------------------

    def _h_health(self, call: _Call) -> Response:
        _only(call.query, ())
        from caterva import __version__

        return json_response({"ok": True, "version": __version__, "api_version": STUDIO_API_VERSION,
                              "started_at": self.started_at})

    def _h_capabilities(self, call: _Call) -> Response:
        _only(call.query, ("probe",))
        probe = call.query.get("probe")
        if probe is not None and probe != "network":
            raise ApiFailure(400, "malformed", "probe takes one value: network", field="probe")
        return json_response(self.capabilities.snapshot(probe_network=probe == "network"))

    def _h_refresh_capabilities(self, call: _Call) -> Response:
        _only(call.query, ())
        if call.body != {}:
            raise ApiFailure(400, "malformed", "refreshing takes an empty object: {}")
        return json_response(self.capabilities.snapshot(refresh_gromacs=True))

    def _h_get_settings(self, call: _Call) -> Response:
        _only(call.query, ())
        return json_response(self.settings())

    def _h_put_settings(self, call: _Call) -> Response:
        _only(call.query, ())
        with self._settings_lock:
            try:
                settings = validate_settings(call.body, self._settings)
            except Malformed as exc:
                raise ApiFailure(400, "malformed", str(exc), field=exc.field) from None
            self.ws.save_settings(settings)
            self._settings = settings
        self.capabilities.apply_gromacs_to_environment()
        if settings.get("gromacs_path"):
            self.capabilities.refresh_gromacs()
        self.manager.pump()
        return json_response(settings)

    def _h_dev_session(self, call: _Call) -> Response:
        _only(call.query, ())
        return json_response({"token": self.token, "api_version": STUDIO_API_VERSION})

    # -- run handlers --------------------------------------------------------

    def _h_create_run(self, call: _Call) -> Response:
        _only(call.query, ())
        body = call.body
        if not isinstance(body, dict):
            raise ApiFailure(400, "malformed", "the body must be an object: {kind, request, title?}")
        unknown = sorted(set(body) - {"kind", "request", "title"})
        if unknown:
            raise ApiFailure(400, "malformed", f"{unknown[0]!r} is not part of a run request", field=unknown[0])
        kind = body.get("kind")
        if kind not in RUN_KINDS:
            raise ApiFailure(400, "malformed", f"kind must be one of {', '.join(RUN_KINDS)}", field="kind")
        request = body.get("request")
        if not isinstance(request, dict):
            raise ApiFailure(400, "malformed", "request must be an object", field="request")
        title = body.get("title")
        if title is not None and (not isinstance(title, str) or not title.strip() or len(title) > MAX_TITLE):
            raise ApiFailure(400, "malformed", f"title must be text of 1 to {MAX_TITLE} characters", field="title")
        try:
            record = self.manager.submit(kind, request, title.strip() if title else None)
        except Malformed as exc:
            raise ApiFailure(400, "malformed", str(exc), field=exc.field) from None
        except QueueFull as exc:
            raise ApiFailure(503, "unavailable", str(exc),
                             headers=[("Retry-After", str(exc.retry_after_s))]) from None
        except Unavailable as exc:
            raise ApiFailure(503, "unavailable", str(exc)) from None
        return json_response({"run": record}, status=202)

    def _h_list_runs(self, call: _Call) -> Response:
        query = call.query
        _only(query, ("kind", "status", "limit", "cursor"))
        kind = query.get("kind")
        if kind is not None and kind not in RUN_KINDS:
            raise ApiFailure(400, "malformed", f"kind must be one of {', '.join(RUN_KINDS)}", field="kind")
        status = query.get("status")
        if status is not None and status not in RUN_STATUSES:
            raise ApiFailure(400, "malformed", f"status must be one of {', '.join(RUN_STATUSES)}", field="status")
        limit = DEFAULT_LIMIT
        if "limit" in query:
            text = query["limit"]
            if not text.isdigit() or not 1 <= int(text) <= MAX_LIMIT:
                raise ApiFailure(400, "malformed", f"limit must be a whole number from 1 to {MAX_LIMIT}",
                                 field="limit")
            limit = int(text)
        try:
            rows, next_cursor = self.ws.list_runs(kind=kind, status=status, limit=limit,
                                                  cursor=query.get("cursor"))
        except Malformed as exc:
            raise ApiFailure(400, "malformed", str(exc), field=exc.field) from None
        return json_response({"runs": rows, "next_cursor": next_cursor})

    def _record(self, run_id: str) -> Dict[str, Any]:
        try:
            return self.manager.record(run_id)
        except RunNotFound:
            raise ApiFailure(404, "not_found", "there is no run with that id") from None

    def _h_get_run(self, call: _Call) -> Response:
        _only(call.query, ())
        return json_response(self._record(call.params["id"]))

    def _h_delete_run(self, call: _Call) -> Response:
        _only(call.query, ())
        run_id = call.params["id"]
        record = self._record(run_id)
        if record["status"] not in TERMINAL_STATUSES or self.manager.is_live(run_id):
            raise ApiFailure(409, "conflict", f"the run is {record['status']}; cancel it before deleting it")
        try:
            self.ws.trash(run_id)
        except RunNotFound:
            raise ApiFailure(404, "not_found", "there is no run with that id") from None
        return json_response(summary_of(record))

    def _h_get_result(self, call: _Call) -> Response:
        _only(call.query, ())
        run_id = call.params["id"]
        record = self._record(run_id)
        if record["status"] not in TERMINAL_STATUSES:
            raise ApiFailure(409, "conflict", f"the run is {record['status']}; its result exists once it is done")
        if (record.get("error") or {}).get("type") == "UnreadableRun":
            raise ApiFailure(404, "not_found", "this version of Caterva Studio cannot read that run")
        try:
            data = self.ws.result_path(run_id).read_bytes()
        except FileNotFoundError:
            raise ApiFailure(404, "not_found", _why_no_result(record)) from None
        return Response(200, _with_security([("Content-Type", JSON_TYPE), ("Cache-Control", "no-store")]), data)

    def _h_run_events(self, call: _Call) -> Response:
        _only(call.query, ())
        run_id = call.params["id"]
        self._record(run_id)
        after = 0
        values = call.request.header_all("Last-Event-ID")
        if values:
            text = values[-1].strip()
            if not text.isdigit():
                raise ApiFailure(400, "malformed", "Last-Event-ID must be a whole number", field="Last-Event-ID")
            after = int(text)
        headers = _with_security([("Content-Type", "text/event-stream; charset=utf-8"),
                                  ("Cache-Control", "no-store"), ("X-Accel-Buffering", "no")])
        if not self.streams.enter():
            raise ApiFailure(503, "unavailable",
                             f"{self.streams.ceiling} event streams are already open (the most the studio serves "
                             "at once); close a tab or wait a moment",
                             headers=[("Retry-After", str(limits.RETRY_AFTER_S))])
        try:
            frames = self.manager.events(run_id, after)
        except BaseException:
            self.streams.leave()
            raise
        return Response(200, headers, stream=limits.GuardedStream(frames, self.streams))

    def _h_cancel_run(self, call: _Call) -> Response:
        _only(call.query, ())
        if call.body != {}:
            raise ApiFailure(400, "malformed", "cancelling takes an empty object: {}")
        try:
            record = self.manager.cancel(call.params["id"])
        except RunNotFound:
            raise ApiFailure(404, "not_found", "there is no run with that id") from None
        except Conflict as exc:
            raise ApiFailure(409, "conflict", str(exc)) from None
        return json_response(record, status=202)

    def _h_get_artifact(self, call: _Call) -> Response:
        _only(call.query, ())
        run_id, name = call.params["id"], call.params["name"]
        record = self._record(run_id)
        info = next((a for a in record.get("artifacts") or [] if isinstance(a, dict) and a.get("name") == name),
                    None)
        if info is None:
            raise ApiFailure(404, "not_found", "the run recorded no file by that name")
        try:
            data = self.ws.artifact_path(run_id, name).read_bytes()
        except (OSError, ValueError):
            raise ApiFailure(404, "not_found", "the run's file is no longer in the workspace") from None
        ctype = info.get("content_type")
        if not isinstance(ctype, str) or not _MEDIA_TYPE.match(ctype):
            ctype = "application/octet-stream"
        return Response(200, _with_security([
            ("Content-Type", ctype),
            ("Content-Disposition", f'attachment; filename="{name}"'),
            ("Content-Security-Policy", ARTIFACT_CSP),
            ("Cache-Control", "no-store"),
        ]), data)

    def _h_get_bundle(self, call: _Call) -> Response:
        _only(call.query, ("redact_paths", "diagnostics"))
        run_id = call.params["id"]
        self._record(run_id)
        flags = {}
        for key, default in (("redact_paths", True), ("diagnostics", False)):
            value = call.query.get(key)
            if value is None:
                flags[key] = default
            elif value in ("true", "false"):
                flags[key] = value == "true"
            else:
                raise ApiFailure(400, "malformed", f"{key} takes true or false", field=key)
        try:
            data = self.ws.bundle(run_id, **flags)
        except RunNotFound:
            raise ApiFailure(404, "not_found", "there is no run with that id") from None
        return Response(200, _with_security([
            ("Content-Type", "application/zip"),
            ("Content-Disposition", f'attachment; filename="caterva-{run_id}.zip"'),
            ("Cache-Control", "no-store"),
        ]), data)


def _query(query_string: str) -> Dict[str, str]:
    if not query_string:
        return {}
    try:
        pairs = parse_qsl(query_string, keep_blank_values=True, strict_parsing=True, errors="strict")
    except (ValueError, UnicodeDecodeError):
        raise ApiFailure(400, "malformed", "the query string cannot be read") from None
    out: Dict[str, str] = {}
    for key, value in pairs:
        if key in out:
            raise ApiFailure(400, "malformed", f"the query key {key!r} is given twice", field=key)
        out[key] = value
    return out


def _only(query: Mapping[str, str], allowed: Sequence[str]) -> None:
    for key in query:
        if key not in allowed:
            raise ApiFailure(400, "malformed", f"{key!r} is not a query key this route reads", field=key)


def _why_no_result(record: Mapping[str, Any]) -> str:
    status = record.get("status")
    outcome = record.get("outcome") or {}
    if status == "done" and outcome.get("reason"):
        return f"the run finished without a result: {outcome['reason']}"
    error = record.get("error") or {}
    if error.get("message"):
        return f"the run ended {status} without a result: {error.get('type')}: {error['message']}"
    return f"the run ended {status} without a result"


def _loggable(target: str) -> str:
    """The path for the log, without its query."""
    return target.split("?", 1)[0][:200]


__all__ = ["ApiFailure", "App", "CSP", "JSON_TYPE", "Request", "Response", "error_response", "json_body",
           "json_response"]
