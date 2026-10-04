"""`caterva studio`: the desktop app's local server.

    caterva studio                       serve on 127.0.0.1, a free port, open the browser
    caterva studio --port 0 --no-browser --print-url
                                         what the macOS app runs; prints one line
                                         CATERVA_STUDIO_URL=<url>#token=<token> once serving
    caterva studio --self-test           start, request /api/health and / over a real
                                         socket, print the result, exit 0 or 1

The flags are fixed by docs/studio/CONTRACT.md section 2, because the macOS
shell, the preview launch configurations and CI all pass them.

WHAT GOES TO STDOUT, AND WHY NOTHING ELSE DOES
----------------------------------------------
The macOS shell reads this process's stdout until it sees the
`CATERVA_STUDIO_URL=` line (the address with the session token in its URL
fragment: the token is in no document the server serves), and a stray line before it (a library's notice,
a warning) would be read as the answer or block the pipe. So once the
server is up, `sys.stdout` and `sys.stderr` are routed (jobs.OutputRouter):
what a run prints becomes that run's log events, and everything else goes
to stderr and `<data dir>/studio.log`. Stdout carries the one URL line.

HOW IT STOPS
------------
Ctrl-C (SIGINT) and SIGTERM stop it cleanly: unfinished runs are marked
interrupted, event streams end, the socket closes, exit 0. So does the
death of whoever launched it, which matters because an orphaned server
keeps a port and a data folder busy with nobody to quit it. Two signs are
watched: when stdin is a pipe (the macOS shell holds one open), its end of
file; and, always, the parent process id changing (the parent died and the
process was handed to init). A terminal's stdin is not a pipe, nor is
/dev/null, so neither stops a server started by hand or by a launcher that
gives it no input.

Exit codes follow the rest of Caterva: 0 served and stopped cleanly (or a
self-test passed), 1 a crash or a failed self-test, 2 a malformed command
line (a non-loopback --host, a port out of range), 3 refused and said why
(the data folder cannot be written, the port is in use, the operating
system refused to bind).
"""
from __future__ import annotations

import argparse
import errno
import html
import http.client
import json
import logging
import logging.handlers
import os
import re
import secrets
import signal
import stat
import sys
import tempfile
import threading
import webbrowser
from pathlib import Path
from typing import Any, Callable, Iterator, List, Optional, Sequence, TextIO, Tuple

#: The only hosts the server will bind. Anything else is refused: the
#: server has no authentication beyond a token a page on the same machine
#: can read, so it must not be reachable from another one.
LOOPBACK_HOSTS = ("127.0.0.1", "::1", "localhost")

#: A development origin is another loopback server (Vite), named exactly as
#: the browser will send it in `Origin`: scheme, loopback host, port, no path.
DEV_ORIGIN = re.compile(r"http://(?:127\.0\.0\.1|localhost):([0-9]{1,5})", re.ASCII)


def valid_dev_origin(text: str) -> bool:
    """Whether `text` is exactly a loopback origin with a port from 1 to 65535.

    `fullmatch`, because `$` also matches before a trailing newline, and a
    range check, because the pattern alone accepts port 0 and 99999."""
    match = DEV_ORIGIN.fullmatch(text)
    return match is not None and 1 <= int(match.group(1)) <= 65535

#: studio.log is rotated at this size, keeping one old copy (CONTRACT.md 11).
LOG_MAX_BYTES = 5 * 1024 * 1024

#: How often the parent process is checked for, in seconds.
PARENT_POLL_S = 1.0

log = logging.getLogger("caterva.studio")


def build_parser(prog: str = "caterva studio") -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog=prog,
        description=(
            "Serve Caterva Studio: a local page over the same engine the other "
            "commands run, with every number's origin beside it. Loopback only."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            f"  {prog}\n"
            f"  {prog} --port 0 --no-browser --print-url\n"
            f"  {prog} --self-test\n"
            "\nExit codes: 0 stopped cleanly or self-test passed, 2 malformed command line, "
            "3 refused and said why, 1 a crash or a failed self-test."
        ),
    )
    p.add_argument("--host", default="127.0.0.1",
                   help="loopback address to bind: 127.0.0.1 (default), ::1 or localhost")
    p.add_argument("--port", type=int, default=0,
                   help="port to bind; 0 (default) picks a free one")
    p.add_argument("--no-browser", action="store_true",
                   help="do not open the default browser")
    p.add_argument("--dev-origin", metavar="URL",
                   help="also accept requests from this origin (a Vite dev server); development only")
    p.add_argument("--data-dir", metavar="PATH",
                   help="where runs and settings are kept (default: the platform's application data folder)")
    p.add_argument("--print-url", action="store_true",
                   help="print CATERVA_STUDIO_URL=<url>#token=<token> on one line once serving")
    p.add_argument("--self-test", action="store_true",
                   help="start, request /api/health and / over a real socket, report, exit 0 or 1")
    return p


def main(argv: Optional[Sequence[str]] = None, prog: str = "caterva studio", *,
         stop: Optional[threading.Event] = None,
         on_serving: Optional[Callable[[Any], None]] = None) -> int:
    """Run `caterva studio`. `stop` and `on_serving` let a test stop a real
    server it started and see it once it listens; the command line passes
    neither."""
    parser = build_parser(prog)
    args = parser.parse_args(argv)
    if args.host not in LOOPBACK_HOSTS:
        parser.error(f"--host {args.host!r} is not a loopback address; the studio binds only "
                     f"{', '.join(LOOPBACK_HOSTS)}")
    if not 0 <= args.port <= 65535:
        parser.error(f"--port {args.port} is not a port number (0 picks a free one)")
    if args.dev_origin is not None and not valid_dev_origin(args.dev_origin):
        parser.error(f"--dev-origin {args.dev_origin!r} is not a loopback origin such as "
                     "http://127.0.0.1:18741 (scheme, host and a port from 1 to 65535, nothing else)")
    if args.data_dir is not None and not args.data_dir.strip():
        parser.error("--data-dir needs a path")

    if args.self_test:
        return self_test(args, prog, sys.stdout, sys.stderr)
    return serve(args, prog, sys.stdout, sys.stderr, stop=stop, on_serving=on_serving)


# ---------------------------------------------------------------------------
# Serving
# ---------------------------------------------------------------------------


class Refused(Exception):
    """Exit 3: the server cannot start here, and the message says why."""


def _workspace(data_dir: Optional[str]) -> Any:
    from caterva.studio.workspace import Workspace, WorkspaceError, default_data_dir

    root = Path(os.path.expanduser(data_dir)) if data_dir else default_data_dir()
    workspace = Workspace(root)
    try:
        workspace.ensure()
    except WorkspaceError as exc:
        raise Refused(str(exc)) from None
    return workspace


def _bind(host: str, port: int) -> Any:
    from caterva.studio.server import StudioHTTPServer

    try:
        return StudioHTTPServer(host, port)
    except OSError as exc:
        if exc.errno == errno.EADDRINUSE:
            raise Refused(f"port {port} on {host} is already in use; pass --port 0 to pick a free one") from None
        raise Refused(f"the operating system refused to let the studio listen on {host}:{port}: "
                      f"{exc.strerror or exc}") from None


class _Logging:
    """The studio's log handlers for as long as it serves: stderr and
    <data dir>/studio.log (rotated), plus run threads' library warnings as
    those runs' log lines. Removed again on exit, so main() can be called
    twice in one process (the tests do)."""

    def __init__(self, log_path: Optional[Path], stderr: TextIO) -> None:
        from caterva.studio.jobs import RunLogHandler

        formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
        self.handlers: List[logging.Handler] = []
        console = logging.StreamHandler(stderr)
        console.setFormatter(formatter)
        self.handlers.append(console)
        self.file_reason: Optional[str] = None
        if log_path is not None:
            try:
                if not log_path.exists():
                    os.close(os.open(log_path, os.O_CREAT | os.O_WRONLY | os.O_APPEND, 0o600))
                handler = logging.handlers.RotatingFileHandler(
                    log_path, maxBytes=LOG_MAX_BYTES, backupCount=1, encoding="utf-8")
                handler.setFormatter(formatter)
                self.handlers.append(handler)
            except OSError as exc:
                self.file_reason = f"{log_path} cannot be written ({exc.strerror or exc}); logging to stderr only"
        self.run_lines = RunLogHandler()
        self.root = logging.getLogger()
        self.studio = log
        self._levels = (self.root.level, self.studio.level)

    def __enter__(self) -> "_Logging":
        for handler in self.handlers:
            self.root.addHandler(handler)
        self.root.addHandler(self.run_lines)
        if self.root.level == logging.NOTSET or self.root.level > logging.WARNING:
            self.root.setLevel(logging.WARNING)
        self.studio.setLevel(logging.INFO)
        if self.file_reason:
            log.warning("%s", self.file_reason)
        return self

    def __exit__(self, *exc: Any) -> None:
        for handler in [*self.handlers, self.run_lines]:
            self.root.removeHandler(handler)
            try:
                handler.close()
            except Exception:  # noqa: BLE001 - closing a log file must not mask the real exit
                pass
        self.root.setLevel(self._levels[0])
        self.studio.setLevel(self._levels[1])


class _RoutedOutput:
    """sys.stdout and sys.stderr routed while serving (module docstring)."""

    def __init__(self, stderr: TextIO) -> None:
        self._stderr = stderr
        self._saved: Optional[Tuple[Any, Any]] = None

    def __enter__(self) -> "_RoutedOutput":
        from caterva.studio.jobs import OutputRouter

        self._saved = (sys.stdout, sys.stderr)
        sys.stdout = OutputRouter(self._stderr)  # type: ignore[assignment]
        sys.stderr = OutputRouter(self._stderr)  # type: ignore[assignment]
        return self

    def __exit__(self, *exc: Any) -> None:
        if self._saved is not None:
            sys.stdout, sys.stderr = self._saved


class _Signals:
    """SIGINT and SIGTERM set `stop` while serving; the previous handlers
    come back afterwards. Only the main thread may install handlers, so
    elsewhere (a test's thread) the caller's `stop` is the only way out."""

    def __init__(self, stop: threading.Event) -> None:
        self._stop = stop
        self._saved: List[Tuple[int, Any]] = []

    def __enter__(self) -> "_Signals":
        if threading.current_thread() is not threading.main_thread():
            return self

        def handler(signum: int, frame: Any) -> None:
            log.info("stopping on %s", signal.Signals(signum).name)
            self._stop.set()

        for sig in (signal.SIGINT, signal.SIGTERM):
            self._saved.append((sig, signal.signal(sig, handler)))
        return self

    def __exit__(self, *exc: Any) -> None:
        for sig, previous in self._saved:
            signal.signal(sig, previous)


def stdin_is_pipe(fd: int = 0) -> bool:
    """Whether stdin is a pipe (the macOS shell's), not a terminal or /dev/null."""
    try:
        return stat.S_ISFIFO(os.fstat(fd).st_mode)
    except OSError:
        return False


def watch_parent(stop: threading.Event, *, stdin_fd: Optional[int] = 0,
                 getppid: Callable[[], int] = os.getppid, poll_s: float = PARENT_POLL_S) -> List[threading.Thread]:
    """Set `stop` when the launching process goes (module docstring, "How it stops")."""
    threads: List[threading.Thread] = []
    first = getppid()

    def parent() -> None:
        while not stop.wait(poll_s):
            if getppid() != first:
                log.info("stopping: the process that started the studio has exited")
                stop.set()

    threads.append(threading.Thread(target=parent, name="caterva-studio-parent", daemon=True))

    if stdin_fd is not None and stdin_is_pipe(stdin_fd):
        def pipe() -> None:
            try:
                while os.read(stdin_fd, 4096):
                    pass
            except OSError:
                pass
            if not stop.is_set():
                log.info("stopping: stdin closed (the app that started the studio has quit)")
                stop.set()

        threads.append(threading.Thread(target=pipe, name="caterva-studio-stdin", daemon=True))
    for thread in threads:
        thread.start()
    return threads


def serve(args: argparse.Namespace, prog: str, out: TextIO, err: TextIO, *,
          stop: Optional[threading.Event] = None,
          on_serving: Optional[Callable[[Any], None]] = None,
          watch: bool = True) -> int:
    from caterva.studio.contract import URL_LINE_PREFIX

    stop = stop or threading.Event()
    try:
        workspace = _workspace(args.data_dir)
    except Refused as exc:
        print(f"{prog}: refused: {exc}", file=err)
        return 3
    with _Logging(workspace.log_path, err):
        try:
            server = _bind(args.host, args.port)
        except Refused as exc:
            log.error("refused: %s", exc)
            print(f"{prog}: refused: {exc}", file=err)
            return 3
        try:
            from caterva.studio.dispatch import App
            from caterva.studio.server import Serving

            app = App(workspace=workspace, port=server.port, host=args.host, dev_origin=args.dev_origin)
            server.app = app
            swept = app.start()
        except Exception:
            server.server_close()
            log.exception("the studio could not start")
            return 1
        if app.settings_note:
            log.warning("%s", app.settings_note)
        serving = Serving(server)
        with _RoutedOutput(err), _Signals(stop):
            serving.start()
            log.info("serving %s (data folder %s%s)", app.url, workspace.root,
                     f"; {len(swept)} unfinished run(s) marked interrupted" if swept else "")
            if args.dev_origin:
                log.info("accepting requests from the development origin %s", args.dev_origin)
            if args.print_url:
                out.write(f"{URL_LINE_PREFIX}{app.bootstrap_url}\n")
                out.flush()
            if not args.no_browser:
                threading.Thread(target=_open_browser, args=(app, workspace.root), name="caterva-studio-browser",
                                 daemon=True).start()
            if watch:
                watch_parent(stop)
            if on_serving is not None:
                on_serving(app)
            code = 0
            try:
                while not stop.wait(0.5):
                    if not serving.thread.is_alive():
                        log.error("the HTTP server stopped unexpectedly")
                        code = 1
                        break
            finally:
                log.info("stopping")
                app.close()
                serving.stop()
        log.info("stopped")
    return code


#: How long the one-use launch page stays on disk, in seconds.
LAUNCH_PAGE_TTL_S = 30.0


def launch_page_html(url: str) -> str:
    """A page that sends the browser on to `url`, which carries the token."""
    escaped = html.escape(url, quote=True)
    return ('<!doctype html><meta charset="utf-8"><title>Caterva Studio</title>'
            f'<meta http-equiv="refresh" content="0;url={escaped}">'
            f'<p><a href="{escaped}">Open Caterva Studio</a></p>\n')


def write_launch_page(directory: Path, url: str) -> Path:
    """The launch page, in a file only this user can read, created exclusively
    (never through a link another process planted)."""
    path = directory / f".open-studio-{secrets.token_hex(8)}.html"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(launch_page_html(url))
    return path


def _open_browser(app: Any, directory: Path, *, opener: Callable[[str], bool] = webbrowser.open,
                  ttl_s: float = LAUNCH_PAGE_TTL_S) -> None:
    """Open the default browser on the address with the token in its fragment.

    A process's arguments are readable by every user on the machine, and the
    browser is started with the address as an argument. So the browser is
    given a file: URL to a page, readable only by this user and deleted
    after `ttl_s`, that forwards to the address; the token is never an
    argument of any process. If no browser can be opened the address is not
    logged: the user starts again with --print-url."""
    page: Optional[Path] = None
    try:
        page = write_launch_page(directory, app.bootstrap_url)
        if not opener(page.as_uri()):
            log.warning("no browser could be opened; run `caterva studio --no-browser --print-url` "
                        "and open the address it prints (%s plus the token)", app.url)
    except Exception as exc:  # noqa: BLE001 - a missing browser is reported, not fatal
        log.warning("no browser could be opened (%s); run `caterva studio --no-browser --print-url` "
                    "and open the address it prints (%s plus the token)", type(exc).__name__, app.url)
    finally:
        if page is not None:
            timer = threading.Timer(ttl_s, _remove_quietly, args=(page,))
            timer.daemon = True
            timer.start()


def _remove_quietly(path: Path) -> None:
    try:
        path.unlink()
    except OSError:
        pass


# ---------------------------------------------------------------------------
# The self-test
# ---------------------------------------------------------------------------


def self_test(args: argparse.Namespace, prog: str, out: TextIO, err: TextIO) -> int:
    """Start on a free port, check /api/health and / over a real socket,
    print one line per check, stop (CONTRACT.md 2). Uses --data-dir when
    given, else a temporary folder, so testing an install never writes to
    the user's data folder."""
    with tempfile.TemporaryDirectory(prefix="caterva-studio-self-test-") as scratch:
        data_dir = args.data_dir or scratch
        lines: List[Tuple[bool, str]] = []
        stop = threading.Event()
        ready = threading.Event()
        holder: List[Any] = []

        def serving(app: Any) -> None:
            holder.append(app)
            ready.set()

        quiet = argparse.Namespace(**{**vars(args), "port": 0, "no_browser": True, "print_url": False,
                                      "data_dir": data_dir})
        result: List[int] = []
        sink = _Collect()

        def run() -> None:
            result.append(serve(quiet, prog, sink, sink, stop=stop, on_serving=serving, watch=False))
            ready.set()

        thread = threading.Thread(target=run, name="caterva-studio-self-test", daemon=True)
        thread.start()
        ready.wait(120)
        if not holder:
            stop.set()
            thread.join(10)
            reason = sink.text().strip().splitlines()[-1:] or ["the server did not start within 120 s"]
            out.write(f"FAIL start: {reason[0]}\n")
            out.flush()
            return 1
        app = holder[0]
        out.write(f"ok   start: listening on {app.url}\n")
        try:
            for ok, line in _checks(app):
                lines.append((ok, line))
                out.write(("ok   " if ok else "FAIL ") + line + "\n")
        finally:
            stop.set()
            thread.join(30)
        stopped = bool(result) and result[0] == 0
        out.write("ok   stop: the server stopped cleanly\n" if stopped
                  else "FAIL stop: the server did not stop cleanly\n")
        out.flush()
        return 0 if stopped and all(ok for ok, _ in lines) else 1


class _Collect:
    """A text sink for the self-test's server, so its log stays out of the report."""

    def __init__(self) -> None:
        self._parts: List[str] = []
        self._lock = threading.Lock()

    def write(self, text: str) -> int:
        with self._lock:
            self._parts.append(text)
        return len(text)

    def flush(self) -> None:
        pass

    def text(self) -> str:
        with self._lock:
            return "".join(self._parts)


def _checks(app: Any) -> Iterator[Tuple[bool, str]]:
    from caterva.studio.contract import SESSION_HEADER, STUDIO_API_VERSION, TOKEN_FRAGMENT_KEY

    host, port = app.guard.host, app.guard.port
    connect_host = "::1" if host == "::1" else "127.0.0.1"

    def get(path: str, headers: Optional[dict] = None) -> Tuple[int, dict, bytes]:
        conn = http.client.HTTPConnection(connect_host, port, timeout=30)
        try:
            conn.request("GET", path, headers=headers or {})
            response = conn.getresponse()
            return response.status, {k.lower(): v for k, v in response.getheaders()}, response.read()
        finally:
            conn.close()

    try:
        status, _, body = get("/api/health", {SESSION_HEADER: app.token})
        health = json.loads(body.decode("utf-8")) if status == 200 else {}
        good = (status == 200 and health.get("ok") is True and health.get("api_version") == STUDIO_API_VERSION)
        yield good, (f"/api/health: {status}, version {health.get('version')}, api_version "
                     f"{health.get('api_version')}" if status == 200 else f"/api/health: HTTP {status}")
    except (OSError, ValueError, http.client.HTTPException) as exc:
        yield False, f"/api/health: {type(exc).__name__}: {exc}"

    try:
        status, _, _ = get("/api/health")
        yield status == 401, f"/api/health without the session token: HTTP {status} (401 expected)"
    except (OSError, http.client.HTTPException) as exc:
        yield False, f"/api/health without the session token: {type(exc).__name__}: {exc}"

    try:
        status, headers, body = get("/")
        text = body.decode("utf-8", errors="replace")
        built, reason = app.static.built()
        csp = "content-security-policy" in headers
        leaked = app.token in text
        if built:
            good = status == 200 and csp and not leaked
            yield good, (f"/: HTTP {status}, the built page, with no session token in it" if good
                         else f"/: HTTP {status}, the built page carries the session token" if leaked
                         else f"/: HTTP {status}, not the built page")
        else:
            good = status == 200 and csp and "the page is not built" in text and not leaked
            yield good, (f"/: HTTP {status}, the page is not built here, so the server's own page explaining "
                         "how to build it" if good else f"/: HTTP {status}, not the expected not-built page")
    except (OSError, http.client.HTTPException) as exc:
        yield False, f"/: {type(exc).__name__}: {exc}"

    url = app.bootstrap_url
    expected = f"{app.url}#{TOKEN_FRAGMENT_KEY}={app.token}"
    yield url == expected, "the address printed for the app carries the session token in its URL fragment" \
        if url == expected else "the address printed for the app does not carry the token in its fragment"


__all__ = ["DEV_ORIGIN", "LAUNCH_PAGE_TTL_S", "LOOPBACK_HOSTS", "build_parser", "launch_page_html", "main",
           "self_test", "serve", "stdin_is_pipe", "valid_dev_origin", "watch_parent", "write_launch_page"]


if __name__ == "__main__":
    sys.exit(main())
