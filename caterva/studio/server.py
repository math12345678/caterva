"""The socket layer: bytes from a loopback socket into `App.dispatch`, and the answer back out.

WHY IT DOES SO LITTLE
---------------------
Every rule (Host, Origin, token, body limits, routes, errors) lives in
`dispatch.py`, which is a function of the request and can be tested
without a port. This module only reads a request off the socket into a
`dispatch.Request`, writes the `Response` back, and, for an event stream,
writes each frame as the iterator yields it and flushes, so a frame
reaches the page when it happens rather than when a buffer fills.

WHAT THE STANDARD LIBRARY WOULD OTHERWISE DO, AND IS STOPPED FROM DOING
-----------------------------------------------------------------------
- `HTTPServer.server_bind` looks the bound address up with
  `socket.getfqdn`, which on a laptop with a confused resolver can take
  seconds before the server listens; the name is not used, so the lookup
  is skipped.
- `BaseHTTPRequestHandler` names the Python version in `Server` and
  answers its own errors (a request line too long, a method it has no
  `do_` for) with an HTML page that carries none of the security headers;
  both are replaced, so every answer, even to a malformed request, is a
  JSON ErrorBody with the headers of CONTRACT.md 3.7.
- A body the dispatch layer refused without reading (a request without
  the token, a body over the limit) would stay in the socket and be read
  as the next request on a kept-alive connection; the connection is closed
  instead.
- It logs every request to stderr. Here requests go to the `caterva.studio`
  logger (stderr and studio.log) at debug level, path without its query.
  Nothing here can log the session token: it travels only in a header,
  and headers are not logged.

WHAT IT REFUSES TO HOLD OPEN
----------------------------
At most limits.MAX_CONNECTIONS connections are served at once: one more is
answered at once with a 503 and a Retry-After and closed, before a thread
is spent on it. A request must arrive within limits.HEADER_DEADLINE_S of its
first byte and its body within limits.BODY_DEADLINE_S of the start of the
body (limits.DeadlineReader): a client that sends one byte every few
seconds is cut off, where a per-read timeout alone would let it hold a
thread forever. Event streams are capped in the dispatch layer
(limits.MAX_STREAMS).

HOW A CLOSED PAGE IS NOTICED
----------------------------
An event stream is written to until the page goes away. A write to a
socket whose peer has closed raises (BrokenPipeError, ConnectionResetError);
the iterator is then closed, which ends its wait. While a run is quiet the
stream writes a keep-alive comment every 15 s (jobs.KEEPALIVE_S), so a
stream whose page has gone is noticed within that time, not when the run
ends hours later.
"""
from __future__ import annotations

import http.server
import logging
import socket
import socketserver
import sys
import threading
from email.utils import formatdate
from typing import Any, List, Optional, Tuple

from caterva.studio import limits
from caterva.studio.dispatch import App, Request, Response, error_response, json_body
from caterva.studio.security import BASE_HEADERS

log = logging.getLogger("caterva.studio.server")

#: How long a connection may sit without sending a request line, in seconds.
#: An event stream is written to at least every jobs.KEEPALIVE_S, well inside it.
IDLE_TIMEOUT_S = 60.0


#: What a socket raises when the other end has gone: never a fault of the server's.
PEER_GONE = (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, socket.timeout)


def busy_response() -> bytes:
    """The whole answer to a connection refused for being over the ceiling."""
    body = json_body({"error": {"code": "unavailable", "message": (
        f"the studio is already serving {limits.MAX_CONNECTIONS} connections, the most it will; "
        "try again in a moment")}})
    head = ["HTTP/1.1 503 Service Unavailable", "Content-Type: application/json; charset=utf-8",
            "Cache-Control: no-store", f"Retry-After: {limits.RETRY_AFTER_S}", f"Content-Length: {len(body)}",
            "Connection: close"]
    head += [f"{k}: {v}" for k, v in BASE_HEADERS]
    return ("\r\n".join(head) + "\r\n\r\n").encode("ascii") + body


def bind_address(host: str) -> Tuple[socket.AddressFamily, str]:
    """(address family, numeric address) for a --host value.

    `localhost` is bound as 127.0.0.1 rather than resolved: a resolver
    could answer anything, and what is bound must be loopback."""
    if host == "::1":
        return socket.AF_INET6, "::1"
    if host in ("127.0.0.1", "localhost"):
        return socket.AF_INET, "127.0.0.1"
    raise ValueError(f"{host!r} is not a loopback host the studio binds")


class StudioHTTPServer(http.server.ThreadingHTTPServer):
    """ThreadingHTTPServer on a loopback address, with the app attached
    after binding (the app's Host rules need the port the OS chose)."""

    daemon_threads = True
    #: Restarting the app at once must not fail on a port still in TIME_WAIT.
    allow_reuse_address = True

    def __init__(self, host: str, port: int, *, max_connections: int = limits.MAX_CONNECTIONS) -> None:
        family, address = bind_address(host)
        self.address_family = family
        self.app: Optional[App] = None
        self.connections = limits.Gate(max_connections)
        super().__init__((address, port), StudioRequestHandler, bind_and_activate=True)

    def process_request(self, request: Any, client_address: Any) -> None:
        if not self.connections.enter():
            self._refuse_busy(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self.connections.leave()
            raise

    def process_request_thread(self, request: Any, client_address: Any) -> None:
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.connections.leave()

    def _refuse_busy(self, request: Any) -> None:
        """Answer a connection over the ceiling with a 503 and close it,
        without spending a thread on it."""
        try:
            request.settimeout(1.0)
            request.sendall(busy_response())
        except OSError:
            pass
        finally:
            self.shutdown_request(request)

    def server_bind(self) -> None:
        # HTTPServer.server_bind would call socket.getfqdn (module docstring).
        socketserver.TCPServer.server_bind(self)
        self.server_name = str(self.server_address[0])
        self.server_port = int(self.server_address[1])

    @property
    def port(self) -> int:
        return int(self.server_address[1])

    def handle_error(self, request: Any, client_address: Any) -> None:
        # A page that navigates away, or a browser dropping a kept-alive
        # connection, resets the socket while the handler waits for the next
        # request line. That is the peer leaving, not a fault here; a
        # traceback for it at ERROR buries the faults in studio.log.
        peer = client_address[0] if client_address else "?"
        if isinstance(sys.exc_info()[1], PEER_GONE):
            log.debug("a connection from %s closed from its end", peer)
            return
        log.exception("a connection from %s ended with an error", peer)


class StudioRequestHandler(http.server.BaseHTTPRequestHandler):
    """Moves one request at a time between the socket and App.dispatch."""

    server: StudioHTTPServer
    protocol_version = "HTTP/1.1"
    timeout = IDLE_TIMEOUT_S

    def setup(self) -> None:
        super().setup()
        self.rfile = limits.DeadlineReader(  # type: ignore[assignment]
            self.rfile, self.connection, idle_s=IDLE_TIMEOUT_S, header_s=limits.HEADER_DEADLINE_S)

    def handle_one_request(self) -> None:
        reader = self.rfile
        if isinstance(reader, limits.DeadlineReader):
            reader.begin()
        super().handle_one_request()

    def version_string(self) -> str:
        return "caterva-studio"

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 - the standard library's name
        log.debug("%s %s", self.address_string(), format % args)

    def log_request(self, code: Any = "-", size: Any = "-") -> None:
        path = (getattr(self, "path", "") or "").split("?", 1)[0][:200]
        log.debug("%s %s %s", getattr(self, "command", "-"), path, code)

    # -- every method goes to dispatch ---------------------------------------

    def do_GET(self) -> None:
        self._handle()

    do_HEAD = do_POST = do_PUT = do_DELETE = do_PATCH = do_OPTIONS = do_GET

    def __getattr__(self, name: str) -> Any:
        # A method http.server has no do_ for (TRACE, CONNECT, PROPFIND) still
        # gets the dispatch layer's answer (a JSON 405 or 404), not an HTML 501.
        if name.startswith("do_") and name[3:].isupper():
            return self._handle
        raise AttributeError(name)

    def send_error(self, code: int, message: Optional[str] = None, explain: Optional[str] = None) -> None:
        """The standard library's own refusals (a request line too long, a
        malformed header block), answered as JSON with the security headers."""
        code_name = {400: "malformed", 404: "not_found", 405: "method_not_allowed", 413: "too_large",
                     414: "malformed", 431: "malformed"}.get(code, "malformed")
        status = code if code in (400, 404, 405, 413) else 400
        reason = message or "the request could not be read"
        self.close_connection = True
        if getattr(self, "request_version", "HTTP/0.9") == "HTTP/0.9":
            # A request line too broken to name its version: answer in 1.0,
            # or http.server would send the body with no status line.
            self.request_version = "HTTP/1.0"
        try:
            self._write(error_response(status, code_name, reason), head=False)
        except OSError:
            pass

    # -- the work ------------------------------------------------------------

    def _handle(self) -> None:
        app = self.server.app
        if app is None:  # pragma: no cover - the app is attached before serving starts
            self.send_error(503, "the studio is starting")
            return
        declared = 0
        lengths = self.headers.get_all("Content-Length") or []
        if len(lengths) == 1 and lengths[0].strip().isdigit():
            declared = int(lengths[0].strip())
        elif lengths or self.headers.get("Transfer-Encoding"):
            declared = -1  # unreadable framing: never reuse this connection
        consumed = [0]

        def read(n: int) -> bytes:
            data = self.rfile.read(n)
            consumed[0] += len(data)
            return data

        reader = self.rfile
        if isinstance(reader, limits.DeadlineReader):
            reader.arm(limits.BODY_DEADLINE_S)
        request = Request(self.command, self.path, list(self.headers.items()), read)
        response = app.dispatch(request)
        if isinstance(reader, limits.DeadlineReader):
            reader.disarm()
        if declared and consumed[0] != declared:
            self.close_connection = True
        self._write(response, head=self.command == "HEAD")

    def _write(self, response: Response, *, head: bool) -> None:
        self.send_response_only(response.status)
        self.send_header("Date", formatdate(usegmt=True))
        headers: List[Tuple[str, str]] = [(k, v) for k, v in response.headers if k.lower() != "content-length"]
        for name, value in headers:
            self.send_header(name, value)
        if response.stream is not None:
            try:
                self.send_header("Connection", "close")
                self.end_headers()
                self.close_connection = True
            except BaseException:
                close = getattr(response.stream, "close", None)
                if callable(close):
                    close()
                raise
            self._stream(response)
            return
        self.send_header("Content-Length", str(len(response.body)))
        if self.close_connection:
            self.send_header("Connection", "close")
        self.end_headers()
        if not head and response.body:
            self.wfile.write(response.body)
        self.wfile.flush()

    def _stream(self, response: Response) -> None:
        frames = response.stream
        assert frames is not None
        try:
            self.wfile.flush()
            for frame in frames:
                self.wfile.write(frame)
                self.wfile.flush()
        except PEER_GONE:
            log.debug("an event stream's page went away")
        finally:
            close = getattr(frames, "close", None)
            if callable(close):
                close()


class Serving:
    """A bound server running `serve_forever` on its own thread."""

    def __init__(self, server: StudioHTTPServer) -> None:
        self.server = server
        self.thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.2},
                                       name="caterva-studio-http", daemon=True)

    def start(self) -> "Serving":
        self.thread.start()
        return self

    def stop(self) -> None:
        """Stop accepting, wait for the loop to end, close the socket."""
        if self.thread.is_alive():
            self.server.shutdown()
            self.thread.join(timeout=10)
        self.server.server_close()


__all__ = ["IDLE_TIMEOUT_S", "Serving", "StudioHTTPServer", "StudioRequestHandler", "bind_address"]
