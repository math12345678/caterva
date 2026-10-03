"""Runs as jobs: accepted or refused up front, queued, run on worker threads, followed through events on disk.

WHY A RUN IS REFUSED BEFORE IT EXISTS
-------------------------------------
A malformed question (the CLI's exit 2) must never become a run that sits
in History looking like it was asked. So `submit` does all of its
refusing first: the kind must be registered and able to run here (else
Unavailable, 503), the adapter turns the request into the CLI's argv
(Malformed, 400), and that argv goes through the command's own parser
(`adapters.parse_cli`: argparse's own refusal, 400). Only then is a run id
minted on disk.

WHY EVENTS GO TO A FILE FIRST
-----------------------------
Every event is appended to the run's `events.jsonl` before anyone is told,
and a stream reads the file, so a page that opens a run late, reconnects
after a sleep, or opens a run another `caterva studio` owns sees the same
history in the same order (CONTRACT.md 8.4). Live runs of this server wake
their streams through a condition; a run owned by another server is
polled.

HOW MANY RUN AT ONCE
--------------------
At most `settings.max_parallel_runs`, started in submission order. A kind
whose AdapterSpec says `serial` (it drives roadrunner, antimony or libsbml,
none of which documents concurrent calls from two threads as supported)
also needs the one engine lock, so two such runs never overlap; a
network-bound run queued behind a waiting serial run starts beside it
rather than waiting too.

WHAT CANCELLING DOES, AND WHAT IT CANNOT
----------------------------------------
Python cannot stop a thread. Cancelling sets a flag and the run's status
becomes `cancelling`, which is not an end: the adapter's next
`check_cancelled()` (and every `stage()`, which is a stage boundary) raises
`Cancelled`, a library loop that polls the flag (the SSA's `should_stop`)
stops inside the call, and only when the thread really has stopped is the
run `cancelled`, keeping no result. A library call that does not poll
finishes first. If the run has not stopped within CANCEL_GRACE_S, the
server gives up waiting: the run ends `abandoned` (never `cancelled`),
its error says the call may still be running in the background, its slot
goes to the next run, and whatever the call returns later is discarded. A
serial run keeps the engine lock until its call really returns, because the
engine is still busy; the message says so.

The same machinery bounds a stuck run: a run still going after its kind's
timeout (KIND_TIMEOUTS_S: each kind's own bound, far beyond its measured
duration, so it catches a network call that never returns rather than a
slow computation) is asked to stop and then abandoned, and ends `failed`
with the error type `TimedOut`, saying which of the two happened.

HOW MANY MAY WAIT, AND HOW MANY ARE KEPT
----------------------------------------
At most MAX_PENDING runs may be queued; one more is refused at submission
(503, Retry-After) rather than accepted into a queue that grows without end.
When a run is accepted, finished runs beyond `settings.keep_runs` (oldest
first, never one still going) are moved to <data dir>/trash/, the same
reversible move deleting a run makes.

WHAT A RUN PRINTS
-----------------
The library prints (compose notes, refusals counted on stderr). While the
server runs, `sys.stdout` and `sys.stderr` are an OutputRouter: what a
run's worker thread writes becomes that run's `log` events (at most
KEEP_LOG_LINES, then one line counting the rest), and everything else goes
to stderr. Stdout itself carries only the `CATERVA_STUDIO_URL=` line the
macOS shell reads.
"""
from __future__ import annotations

import copy
import importlib
import io
import json
import logging
import math
import os
import re
import secrets
import shlex
import threading
import time
import traceback
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Mapping, Optional, Sequence, TextIO, Tuple

from caterva.studio.adapters import AdapterOutcome, AdapterSpec, Artifact, Cancelled, RunContext, parse_cli, request_needs
from caterva.studio.contract import RUN_RECORD_SCHEMA, Malformed, Unavailable, outcome_for
from caterva.studio.routes import ARTIFACT_NAME_PATTERN
from caterva.studio.workspace import (
    INTERRUPTED_MESSAGE, TERMINAL_STATUSES, RunNotFound, UnreadableRun, Workspace, iso, json_bytes, utc_now,
    write_bytes_atomic,
)

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows
    fcntl = None  # type: ignore[assignment]

log = logging.getLogger("caterva.studio.jobs")

#: An adapter whose argv must name a path inside the run's own directory
#: (md.setup's default `--out <run dir>/md-setup`, structure's
#: `--chimerax <run dir>/artifacts/structure.cxc`) writes this string where
#: the directory goes. The run directory does not exist when `argv` runs,
#: so the server puts its absolute path in before parsing and recording.
RUN_DIR_PLACEHOLDER = "@RUN_DIR@"

#: `log` events kept per run (CONTRACT.md 8.4).
KEEP_LOG_LINES = 2000
#: How long a cancelled run may take to reach its next check before it is
#: abandoned.
CANCEL_GRACE_S = 20.0
#: How long a run of a kind may take before it is stopped as stuck (module
#: docstring), in seconds. Each is a long multiple of the kind's measured
#: duration: the bound is for a call that never returns. `analyze` reads
#: whole trajectories and runs GROMACS steps, so it gets the longest.
KIND_TIMEOUTS_S: Mapping[str, float] = {
    "compose": 30 * 60.0,
    "constants": 10 * 60.0,
    "sim": 10 * 60.0,
    "bind": 10 * 60.0,
    "structure": 10 * 60.0,
    "prepare": 15 * 60.0,
    "md.setup": 10 * 60.0,
    "md.summarise": 30 * 60.0,
    "analyze": 2 * 60 * 60.0,
    "fep.status": 30 * 60.0,
    "complex.check": 30 * 60.0,
    "rates": 30 * 60.0,
}
#: For a kind not in the table above.
RUN_TIMEOUT_S = 60 * 60.0
#: Runs that may wait in the queue (module docstring).
MAX_PENDING = 32
#: What a refused submission tells the page to wait, in seconds.
QUEUE_RETRY_AFTER_S = 30
#: Seconds between keep-alive comments on an idle event stream.
KEEPALIVE_S = 15.0
#: How often a stream re-reads the file of a run another server owns.
POLL_S = 0.5


class Conflict(Exception):
    """The request is right but the run's state forbids it: HTTP 409."""


class QueueFull(Unavailable):
    """Too many runs are waiting: HTTP 503 with Retry-After."""

    retry_after_s = QUEUE_RETRY_AFTER_S


_UNSET: Any = object()


def make_run_id(kind: str, moment: Optional[Any] = None) -> str:
    """yyyymmdd-hhmmss-<kind, dots as dashes>-<8 hex>, UTC (routes.RUN_ID_PATTERN)."""
    moment = moment or utc_now()
    return f"{moment:%Y%m%d-%H%M%S}-{kind.replace('.', '-')}-{secrets.token_hex(4)}"


def cli_prefix(spec: AdapterSpec) -> Tuple[str, ...]:
    """The argv words before the adapter's own: its `cli_prefix`, or
    ("caterva", <command>) read from `command` when it set none."""
    if spec.cli_prefix:
        return tuple(spec.cli_prefix)
    words = spec.command.split()
    if words and words[0] == "caterva":
        words = words[1:]
    return ("caterva", words[0]) if words else ("caterva",)


def sse_frame(seq: int, name: str, data: Mapping[str, Any]) -> bytes:
    """One Server-Sent Event: id, event name, one line of JSON, blank line."""
    payload = json.dumps(dict(data), ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    return f"id: {seq}\nevent: {name}\ndata: {payload}\n\n".encode("utf-8")


KEEPALIVE_FRAME = b": keep-alive\n\n"


# ---------------------------------------------------------------------------
# Where a run's printed output goes
# ---------------------------------------------------------------------------


class _LineSink:
    """Collects text a run's thread writes and hands it on a line at a time."""

    def __init__(self, emit: Callable[[str], None]) -> None:
        self._emit = emit
        self._buffer = ""
        self._lock = threading.Lock()

    def write(self, text: str) -> None:
        lines: List[str] = []
        with self._lock:
            self._buffer += text
            while "\n" in self._buffer:
                line, self._buffer = self._buffer.split("\n", 1)
                lines.append(line.rstrip("\r"))
        for line in lines:
            self._emit(line)

    def flush_partial(self) -> None:
        with self._lock:
            rest, self._buffer = self._buffer, ""
        if rest.strip():
            self._emit(rest.rstrip("\r"))


class _Sinks:
    """Thread -> the sink of the run that thread is working on."""

    def __init__(self) -> None:
        self._sinks: Dict[int, _LineSink] = {}
        self._lock = threading.Lock()

    def register(self, sink: _LineSink) -> None:
        with self._lock:
            self._sinks[threading.get_ident()] = sink

    def unregister(self) -> None:
        with self._lock:
            self._sinks.pop(threading.get_ident(), None)

    def current(self) -> Optional[_LineSink]:
        return self._sinks.get(threading.get_ident())


SINKS = _Sinks()


class OutputRouter(io.TextIOBase):
    """Stands in for sys.stdout or sys.stderr while the server runs: a run
    thread's writes become that run's log lines, anything else goes to
    `fallback` (module docstring, "What a run prints")."""

    def __init__(self, fallback: TextIO) -> None:
        super().__init__()
        self._fallback = fallback

    def writable(self) -> bool:
        return True

    def write(self, text: str) -> int:
        sink = SINKS.current()
        if sink is None:
            return self._fallback.write(text)
        sink.write(text)
        return len(text)

    def flush(self) -> None:
        if SINKS.current() is None:
            self._fallback.flush()

    def isatty(self) -> bool:
        return False

    def fileno(self) -> int:
        return self._fallback.fileno()

    @property
    def encoding(self) -> str:  # type: ignore[override]
        return getattr(self._fallback, "encoding", None) or "utf-8"


class RunLogHandler(logging.Handler):
    """Warnings a library logs from a run's thread become that run's log
    lines too (they still reach studio.log through the other handlers)."""

    def __init__(self) -> None:
        super().__init__(logging.WARNING)

    def emit(self, record: logging.LogRecord) -> None:
        if record.name.startswith("caterva.studio"):
            return
        sink = SINKS.current()
        if sink is None:
            return
        try:
            message = record.getMessage()
        except Exception:  # noqa: BLE001 - a malformed log call must not end the run
            return
        sink.write(message + "\n")


# ---------------------------------------------------------------------------
# One run this server owns
# ---------------------------------------------------------------------------


class _Job:
    def __init__(self, manager: "JobManager", spec: AdapterSpec, request: Mapping[str, Any],
                 run_dir: Path, record: Dict[str, Any]) -> None:
        self.run_id: str = record["id"]
        self.kind: str = record["kind"]
        self.spec = spec
        self.request = request
        self.run_dir = run_dir
        self.record = record
        self.cancel = threading.Event()
        self.cancel_deadline: Optional[float] = None
        self.timed_out = False
        self.started: Optional[float] = None
        self.finished = False
        self.thread: Optional[threading.Thread] = None
        self.thread_done = False
        self.seq = 0
        self.log_count = 0
        self.log_omitted = 0
        self.progress = _Progress(manager, self)


class _Progress:
    """What an adapter reports through (adapters.Progress)."""

    def __init__(self, manager: "JobManager", job: _Job) -> None:
        self._manager = manager
        self._job = job

    def stage(self, key: str, label: str, fraction: Optional[float] = None) -> None:
        if not isinstance(key, str) or not key:
            raise ValueError("a stage needs a key")
        if not isinstance(label, str):
            raise ValueError("a stage label is text")
        if fraction is not None:
            fraction = float(fraction)
            if not (0.0 <= fraction <= 1.0):  # NaN fails this too
                raise ValueError(f"a stage fraction is between 0 and 1, or None; got {fraction!r}")
        self.check_cancelled()  # a stage boundary is a place to stop
        self._manager._stage(self._job, key, label, fraction)

    def log(self, line: str) -> None:
        for part in str(line).splitlines():
            self._manager._log_line(self._job, part)

    def check_cancelled(self) -> None:
        if self._job.cancel.is_set():
            raise Cancelled(self._job.run_id)

    def is_cancelled(self) -> bool:
        return self._job.cancel.is_set()


# ---------------------------------------------------------------------------
# The manager
# ---------------------------------------------------------------------------


class JobManager:
    """Owns this server's runs: submitting, scheduling, events, cancelling."""

    def __init__(
        self,
        workspace: Workspace,
        registry: Any,
        *,
        instance_id: str,
        parallel: Callable[[], int] = lambda: 2,
        offline: Callable[[], bool] = lambda: False,
        cancel_grace_s: float = CANCEL_GRACE_S,
        timeout_s: Optional[float] = _UNSET,
        max_pending: int = MAX_PENDING,
        keep_runs: Callable[[], int] = lambda: 200,
        keepalive_s: float = KEEPALIVE_S,
        poll_s: float = POLL_S,
        tick_s: float = 0.25,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        from caterva import __version__

        self.ws = workspace
        self.registry = registry
        self.instance_id = instance_id
        self.version = __version__
        self._parallel = parallel
        self._offline = offline
        self.cancel_grace_s = cancel_grace_s
        #: One bound for every kind when given (tests, a caller that wants one);
        #: by default each kind has its own (KIND_TIMEOUTS_S).
        self.timeout_s = timeout_s
        self.max_pending = max_pending
        self._keep_runs = keep_runs
        self.keepalive_s = keepalive_s
        self.poll_s = poll_s
        self.tick_s = tick_s
        self._clock = clock
        self._lock = threading.RLock()
        self._cond = threading.Condition(self._lock)
        self._jobs: Dict[str, _Job] = {}
        self._pending: List[_Job] = []
        self._active: set = set()
        self._engine_holder: Optional[str] = None
        self._last_seq: Dict[str, int] = {}
        self._stopping = False
        self._watchdog: Optional[threading.Thread] = None

    # -- submitting ----------------------------------------------------------

    def submit(self, kind: str, request: Mapping[str, Any], title: Optional[str] = None) -> Dict[str, Any]:
        """Accept a run and queue it, or refuse it without writing anything."""
        from caterva.studio.capabilities import NOT_BUILT_YET, OFFLINE_REASON

        if self._stopping:
            raise Unavailable("the studio is stopping; the run was not started")
        with self._lock:
            waiting = len(self._pending)
        if waiting >= self.max_pending:
            raise QueueFull(f"{waiting} runs are already waiting to start (at most {self.max_pending} may); "
                            "wait for some to finish, or cancel some, and try again")
        spec = self.registry.get(kind)
        if spec is None:
            raise Unavailable(f"{kind}: {NOT_BUILT_YET}")
        try:
            reason = spec.unavailable()
        except Exception as exc:  # noqa: BLE001 - an adapter check that raised cannot vouch for the kind
            reason = f"could not tell whether {kind} can run here: {type(exc).__name__}: {exc}"
        if reason:
            raise Unavailable(reason)
        run_id = self._new_run_id(kind)
        run_dir = self.ws.run_dir(run_id)
        argv = spec.argv(request)
        if not isinstance(argv, (list, tuple)) or not all(isinstance(a, str) for a in argv):
            raise TypeError(f"the {kind} adapter's argv() returned {type(argv).__name__}, not a list of strings")
        if spec.check_paths is not None:
            spec.check_paths(request, self.ws.root)
        if self._offline() and "network" in request_needs(spec, request):
            raise Unavailable(f"{kind}: {OFFLINE_REASON}")
        argv = [a.replace(RUN_DIR_PLACEHOLDER, str(run_dir)) for a in argv]
        prefix = cli_prefix(spec)
        _parse_with_command_parser(prefix, argv)
        cli = [*prefix, *argv]

        now = iso(utc_now())
        record: Dict[str, Any] = {
            "schema": RUN_RECORD_SCHEMA,
            "id": run_id,
            "kind": kind,
            "title": title if title is not None else _describe(spec, request, cli),
            "status": "queued",
            "created_at": now,
            "started_at": None,
            "finished_at": None,
            "caterva_version": self.version,
            "cli": cli,
            "request": copy.deepcopy(dict(request)),
            "outcome": None,
            "error": None,
            "artifacts": [],
            "progress": None,
        }
        self._prune()
        self.ws.create_run(record, record["request"], owner=self.instance_id)
        job = _Job(self, spec, record["request"], run_dir, record)
        with self._lock:
            self._jobs[run_id] = job
            self._emit(job, "status", {"status": "queued"})
            accepted = copy.deepcopy(record)
            self._pending.append(job)
            self._start_watchdog()
            self._pump()
        log.info("run %s accepted (%s)", run_id, kind)
        return accepted

    def _prune(self) -> None:
        """Move finished runs beyond `keep_runs` (oldest first) to the trash."""
        try:
            keep = max(1, int(self._keep_runs()))
        except Exception:  # noqa: BLE001 - a settings read that failed must not stop a run being accepted
            return
        try:
            ids = self.ws.run_ids()
        except OSError:
            return
        if len(ids) <= keep:
            return
        finished = []
        for run_id in sorted(ids, reverse=True):  # ids sort by time, newest first
            with self._lock:
                if run_id in self._jobs:
                    continue  # still queued or running, or not yet cleaned up
            try:
                status = self.ws.summary(run_id)["status"]
            except Exception:  # noqa: BLE001 - an unreadable run is left where it is
                continue
            if status in TERMINAL_STATUSES:
                finished.append(run_id)
        for run_id in finished[keep:]:
            try:
                self.ws.trash(run_id)
                log.info("run %s moved to the trash: History keeps %d finished runs", run_id, keep)
            except (RunNotFound, OSError) as exc:
                log.warning("run %s could not be moved to the trash: %s", run_id, exc)

    def _timeout_for(self, job: "_Job") -> Optional[float]:
        if self.timeout_s is not _UNSET:
            return self.timeout_s
        return KIND_TIMEOUTS_S.get(job.kind, RUN_TIMEOUT_S)

    def _new_run_id(self, kind: str) -> str:
        while True:
            run_id = make_run_id(kind)
            if not self.ws.exists(run_id):
                return run_id

    # -- reading -------------------------------------------------------------

    def record(self, run_id: str) -> Dict[str, Any]:
        """The run's record: from memory for this server's runs, else from
        disk (RunNotFound when there is none)."""
        with self._lock:
            job = self._jobs.get(run_id)
            if job is not None:
                return copy.deepcopy(job.record)
        return self.ws.record_or_unreadable(run_id)

    def is_live(self, run_id: str) -> bool:
        with self._lock:
            job = self._jobs.get(run_id)
            return job is not None and not job.finished

    # -- scheduling ----------------------------------------------------------

    def pump(self) -> None:
        """Start whatever may start now (after a settings change, say)."""
        with self._lock:
            self._pump()

    def _limit(self) -> int:
        try:
            return max(1, min(8, int(self._parallel())))
        except Exception:  # noqa: BLE001 - a settings read that failed must not stop scheduling
            return 1

    def _pump(self) -> None:
        if self._stopping:
            return
        limit = self._limit()
        i = 0
        while len(self._active) < limit and i < len(self._pending):
            job = self._pending[i]
            if job.spec.serial and self._engine_holder is not None:
                i += 1
                continue
            del self._pending[i]
            self._active.add(job.run_id)
            if job.spec.serial:
                self._engine_holder = job.run_id
            job.thread = threading.Thread(target=self._work, args=(job,), name=f"caterva-run-{job.run_id}",
                                          daemon=True)
            job.thread.start()

    def _work(self, job: _Job) -> None:
        sink = _LineSink(lambda line: self._log_line(job, line))
        SINKS.register(sink)
        try:
            with self._lock:
                if job.finished:
                    return
                job.started = self._clock()
                job.record["status"] = "running"
                job.record["started_at"] = iso(utc_now())
                self._save(job)
                self._emit(job, "status", {"status": "running"})
            context = RunContext(run_id=job.run_id, run_dir=job.run_dir, data_dir=self.ws.root,
                                 progress=job.progress)
            try:
                outcome = job.spec.run(job.request, context)
            except Cancelled:
                sink.flush_partial()
                self._stopped_by_request(job)
            except Malformed as exc:
                sink.flush_partial()
                self._finish_failed(job, "Malformed", str(exc), None)
            except BaseException as exc:  # noqa: BLE001 - any escape from an adapter is the run's crash
                sink.flush_partial()
                text = traceback.format_exc()
                log.error("run %s (%s) crashed\n%s", job.run_id, job.kind, text)
                self._finish_failed(job, type(exc).__name__, str(exc), text)
            else:
                sink.flush_partial()
                self._finish_done(job, outcome)
        finally:
            SINKS.unregister()
            with self._lock:
                job.thread_done = True
                if self._engine_holder == job.run_id:
                    self._engine_holder = None
                self._active.discard(job.run_id)
                if job.finished:
                    self._jobs.pop(job.run_id, None)
                self._pump()
                self._cond.notify_all()

    # -- progress from the adapter -------------------------------------------

    def _stage(self, job: _Job, key: str, label: str, fraction: Optional[float]) -> None:
        with self._lock:
            if job.finished:
                return
            job.record["progress"] = {"stage": key, "label": label, "fraction": fraction}
            self._save(job)
            self._emit(job, "stage", {"stage": key, "label": label, "fraction": fraction})

    def _log_line(self, job: _Job, line: str) -> None:
        if not line.strip():
            return
        with self._lock:
            if job.finished:
                return
            if job.log_count >= KEEP_LOG_LINES:
                job.log_omitted += 1
                return
            job.log_count += 1
            self._emit(job, "log", {"line": line})

    # -- finishing -----------------------------------------------------------

    def _finish_done(self, job: _Job, outcome: Any) -> None:
        try:
            result_bytes, artifacts, verdict = _prepare(job.kind, outcome)
        except (TypeError, ValueError) as exc:
            self._finish_failed(job, "ContractViolation",
                                f"the {job.kind} adapter returned an outcome the contract refuses: {exc}", None)
            return
        # Written before the lock (they may be large); only this run writes here.
        written: List[Path] = []
        try:
            if result_bytes is not None:
                write_bytes_atomic(self.ws.result_path(job.run_id), result_bytes)
                written.append(self.ws.result_path(job.run_id))
            infos = []
            for artifact in artifacts:
                size = self.ws.write_artifact(job.run_id, artifact.name, artifact.content)
                written.append(self.ws.artifact_path(job.run_id, artifact.name))
                infos.append({"name": artifact.name, "content_type": artifact.content_type, "bytes": size,
                              "description": artifact.description})
        except OSError as exc:
            self._finish_failed(job, type(exc).__name__, f"the result could not be saved: {exc}", None)
            return
        with self._lock:
            if job.finished:
                # Abandoned while the call ran: a cancelled run keeps no result.
                for path in written:
                    try:
                        path.unlink()
                    except OSError:
                        pass
                log.info("run %s returned after it was abandoned; its result was discarded", job.run_id)
                return
            if job.cancel.is_set():
                self._emit_log(job, "The run finished before it reached a point where it could stop, "
                                    "so it kept its result.")
            self._flush_omitted(job)
            job.record["outcome"] = verdict
            job.record["artifacts"] = infos
            job.record["status"] = "done"
            job.record["finished_at"] = iso(utc_now())
            self._emit(job, "result", {"outcome": verdict})
            self._save(job)
            self._emit(job, "status", {"status": "done", "outcome": verdict})
            self._end(job)
        log.info("run %s done: %s", job.run_id, verdict["meaning"])

    def _finish_failed(self, job: _Job, error_type: str, message: str, text: Optional[str]) -> None:
        with self._lock:
            if job.finished:
                return
            self._flush_omitted(job)
            error = {"type": error_type, "message": message, "traceback": text}
            job.record["error"] = error
            job.record["status"] = "failed"
            job.record["finished_at"] = iso(utc_now())
            self._emit(job, "error", {"error": error})
            self._save(job)
            self._emit(job, "status", {"status": "failed"})
            self._end(job)
        log.info("run %s failed: %s", job.run_id, error_type)

    def _finish_cancelled(self, job: _Job, note: str) -> None:
        with self._lock:
            if job.finished:
                return
            self._emit_log(job, note)
            self._flush_omitted(job)
            job.record["status"] = "cancelled"
            job.record["finished_at"] = iso(utc_now())
            self._save(job)
            self._emit(job, "status", {"status": "cancelled"})
            self._end(job)
        log.info("run %s cancelled", job.run_id)

    def _finish_abandoned(self, job: _Job, detail: str) -> None:
        """A cancel the thread did not obey in time: not `cancelled`, because
        the thread is still running, and the record says so."""
        with self._lock:
            if job.finished:
                return
            warning = f"Abandoned, not stopped: {detail}"
            self._emit_log(job, warning)
            self._flush_omitted(job)
            job.record["error"] = {"type": "Abandoned", "message": warning, "traceback": None}
            job.record["status"] = "abandoned"
            job.record["finished_at"] = iso(utc_now())
            self._emit(job, "error", {"error": job.record["error"]})
            self._save(job)
            self._emit(job, "status", {"status": "abandoned"})
            self._end(job)
        log.warning("run %s abandoned: its thread is still running", job.run_id)

    def _finish_interrupted(self, job: _Job) -> None:
        with self._lock:
            if job.finished:
                return
            job.record["error"] = {"type": "Interrupted", "message": INTERRUPTED_MESSAGE, "traceback": None}
            job.record["status"] = "interrupted"
            job.record["finished_at"] = iso(utc_now())
            self._save(job)
            self._emit(job, "status", {"status": "interrupted"})
            self._end(job)

    def _end(self, job: _Job) -> None:
        """The last event; the run's slot goes to the next run."""
        self._emit(job, "end", {"status": job.record["status"]})
        job.finished = True
        if job in self._pending:
            self._pending.remove(job)
        self._active.discard(job.run_id)
        if job.thread is None or job.thread_done:
            self._jobs.pop(job.run_id, None)
        self._pump()

    def _stopped_by_request(self, job: _Job) -> None:
        if job.timed_out:
            self._finish_failed(job, "TimedOut", f"the run took longer than {_duration(self._timeout_for(job))} "
                                                  "and was stopped at its next check", None)
        else:
            self._finish_cancelled(job, "Cancelled: the run stopped at its next check and keeps no result.")

    def _abandon(self, job: _Job) -> None:
        stage = (job.record.get("progress") or {}).get("label") or "its first stage"
        engine = (" The engine stays busy until that call returns, so the next engine run waits for it."
                  if job.spec.serial else "")
        detail = (f"the library call in progress ({stage}) did not reach a point where it could stop within "
                  f"{self.cancel_grace_s:g} s, so the run was abandoned: the call finishes in the background "
                  f"and whatever it returns is discarded.{engine}")
        if job.timed_out:
            self._finish_failed(job, "TimedOut",
                                f"the run took longer than {_duration(self._timeout_for(job))}, and {detail}", None)
        else:
            self._finish_abandoned(job, detail)

    # -- cancelling ----------------------------------------------------------

    def cancel(self, run_id: str) -> Dict[str, Any]:
        """Ask a run to stop (202). Conflict when it has finished, or when it
        belongs to another server on the same data folder."""
        with self._lock:
            job = self._jobs.get(run_id)
            if job is None or job.finished:
                record = self.ws.record_or_unreadable(run_id)  # RunNotFound -> 404
                if record["status"] in TERMINAL_STATUSES:
                    raise Conflict(f"the run has already finished ({record['status']})")
                raise Conflict("the run belongs to another caterva studio serving the same data folder; "
                               "cancel it from that one")
            if job in self._pending:
                self._finish_cancelled(job, "Cancelled before it started.")
            elif not job.cancel.is_set():
                job.cancel.set()
                job.cancel_deadline = self._clock() + self.cancel_grace_s
                if job.record["status"] == "running":
                    job.record["status"] = "cancelling"
                    self._save(job)
                    self._emit(job, "status", {"status": "cancelling"})
                self._emit_log(job, "Cancel requested: the run stops at its next check.")
                self._cond.notify_all()
            return copy.deepcopy(job.record)

    # -- the watchdog --------------------------------------------------------

    def _start_watchdog(self) -> None:
        if self._watchdog is None:
            self._watchdog = threading.Thread(target=self._watch, name="caterva-run-watchdog", daemon=True)
            self._watchdog.start()

    def _watch(self) -> None:
        with self._lock:
            while not self._stopping:
                now = self._clock()
                for job in list(self._jobs.values()):
                    if job.finished or job.started is None:
                        continue
                    timeout = self._timeout_for(job)
                    if timeout is not None and not job.timed_out and now - job.started > timeout:
                        job.timed_out = True
                        if not job.cancel.is_set():
                            job.cancel.set()
                            job.cancel_deadline = now + self.cancel_grace_s
                        self._emit_log(job, f"The run has taken longer than {_duration(timeout)}; "
                                            "asking it to stop.")
                    if job.cancel.is_set() and job.cancel_deadline is not None and now >= job.cancel_deadline:
                        self._abandon(job)
                self._cond.wait(self.tick_s)

    # -- stopping the server -------------------------------------------------

    def shutdown(self) -> None:
        """Mark every unfinished run of this server interrupted, and end
        every stream."""
        with self._lock:
            for job in list(self._jobs.values()):
                if not job.finished:
                    self._finish_interrupted(job)
            self._stopping = True
            self._pending.clear()
            self._cond.notify_all()

    def sweep_interrupted(self) -> List[str]:
        """At startup: every run left queued or running by a server that is
        no longer running is marked interrupted (never resumed)."""
        swept = []
        for run_id in self.ws.run_ids():
            try:
                record = self.ws.read_record(run_id)
            except (RunNotFound, UnreadableRun):
                continue
            if record["status"] not in ("queued", "running", "cancelling"):
                continue
            if self.ws.owner_alive(self.ws.owner_of(run_id)):
                continue
            if self.mark_interrupted_on_disk(run_id):
                swept.append(run_id)
        if swept:
            log.info("marked %d run(s) interrupted: %s", len(swept), ", ".join(swept))
        return swept

    def mark_interrupted_on_disk(self, run_id: str) -> bool:
        """Mark a run whose server has gone interrupted, once, even when two
        servers find it at the same moment."""
        run_dir = self.ws.run_dir(run_id)
        with _run_dir_lock(run_dir):
            try:
                record = self.ws.read_record(run_id)
            except (RunNotFound, UnreadableRun):
                return False
            if record["status"] not in ("queued", "running", "cancelling"):
                return False
            if self.ws.owner_alive(self.ws.owner_of(run_id)):
                return False
            seq = self.ws.last_seq(run_id)
            now = iso(utc_now())
            record["status"] = "interrupted"
            record["finished_at"] = now
            record["error"] = {"type": "Interrupted", "message": INTERRUPTED_MESSAGE, "traceback": None}
            self.ws.write_record(record)
            for name, payload in (("status", {"status": "interrupted"}), ("end", {"status": "interrupted"})):
                seq += 1
                self.ws.append_event(run_id, name, {"run_id": run_id, "seq": seq, "at": now, **payload})
            return True

    # -- events --------------------------------------------------------------

    def _emit(self, job: _Job, name: str, payload: Mapping[str, Any]) -> None:
        """Append one event to the run's file, then wake its streams. The
        caller holds the lock."""
        job.seq += 1
        data = {"run_id": job.run_id, "seq": job.seq, "at": iso(utc_now()), **payload}
        try:
            self.ws.append_event(job.run_id, name, data)
        except OSError as exc:
            log.error("run %s: event %d (%s) could not be written: %s", job.run_id, job.seq, name, exc)
        self._last_seq[job.run_id] = job.seq
        self._cond.notify_all()

    def _emit_log(self, job: _Job, line: str) -> None:
        """A line of the studio's own about the run, past the per-run limit."""
        self._emit(job, "log", {"line": line})

    def _flush_omitted(self, job: _Job) -> None:
        if job.log_omitted:
            self._emit_log(job, f"{job.log_omitted} more lines of output were not kept (a run keeps "
                                f"{KEEP_LOG_LINES:,}).")
            job.log_omitted = 0

    def _save(self, job: _Job) -> None:
        try:
            self.ws.write_record(job.record)
        except OSError as exc:
            log.error("run %s: run.json could not be written: %s", job.run_id, exc)

    def events(self, run_id: str, after: int = 0) -> Iterator[bytes]:
        """The run's events as SSE frames: its history from seq `after` on,
        then live, then closed after `end` (CONTRACT.md 8.4). Idle streams
        get a keep-alive comment every `keepalive_s`."""
        offset = 0
        last = after
        quiet_since = self._clock()
        draining = False
        while True:
            try:
                events, offset = self.ws.read_events(run_id, offset)
            except ValueError:
                return
            for name, data in events:
                seq = data.get("seq")
                if isinstance(seq, int) and seq > last:
                    yield sse_frame(seq, name, data)
                    last = seq
                    quiet_since = self._clock()
                if name == "end":
                    return
            if draining:
                return
            with self._lock:
                if self._stopping:
                    # Shutdown wrote each unfinished run's last events just
                    # before it set the flag: read the file once more so the
                    # stream ends with them rather than stopping short.
                    draining = True
                    continue
                live = run_id in self._jobs and not self._jobs[run_id].finished
            if not live and not events:
                if not self._foreign_run_may_continue(run_id):
                    return
            waited = self._wait_for_event(run_id, last, live, quiet_since)
            if not waited and self._clock() - quiet_since >= self.keepalive_s:
                yield KEEPALIVE_FRAME
                quiet_since = self._clock()

    def _foreign_run_may_continue(self, run_id: str) -> bool:
        """For a run this server is not running: whether more events may
        still come (another live server owns it)."""
        try:
            record = self.ws.read_record(run_id)
        except (RunNotFound, UnreadableRun):
            return False
        if record["status"] in TERMINAL_STATUSES:
            return False
        if self.ws.owner_alive(self.ws.owner_of(run_id)):
            return True
        # Its server has gone since this one started: mark it, and let the
        # stream read the events that marking wrote.
        self.mark_interrupted_on_disk(run_id)
        return True

    def _wait_for_event(self, run_id: str, last: int, live: bool, quiet_since: float) -> bool:
        """Wait for a new event of the run; True if one arrived."""
        remaining = max(0.0, self.keepalive_s - (self._clock() - quiet_since))
        timeout = remaining if live else min(self.poll_s, remaining)
        with self._lock:
            return self._cond.wait_for(lambda: self._stopping or self._last_seq.get(run_id, 0) > last,
                                       timeout=timeout)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_with_command_parser(prefix: Sequence[str], argv: List[str]) -> None:
    """Run the argv through the `caterva <command>` module's own
    `build_parser(prog)` when it has one (CONTRACT.md 12.2); argparse's
    refusal is Malformed. A command without one (a script such as cite.py)
    is parsed by its adapter's argv."""
    if len(prefix) < 2 or prefix[0] != "caterva":
        return
    from caterva.app import COMMANDS

    entry = COMMANDS.get(prefix[1])
    if entry is None:
        return
    module = importlib.import_module(entry[0])
    build = getattr(module, "build_parser", None)
    if callable(build):
        parse_cli(build, argv, f"caterva {prefix[1]}")


def _describe(spec: AdapterSpec, request: Mapping[str, Any], cli: Sequence[str]) -> str:
    if spec.describe is not None:
        try:
            text = spec.describe(request)
            if isinstance(text, str) and text.strip():
                return text.strip()
        except Exception as exc:  # noqa: BLE001 - a title is not worth refusing a run over
            log.warning("describe() of %s raised %s; titled by its command line", spec.kind, exc)
    return shlex.join(cli)


def _prepare(kind: str, outcome: Any) -> Tuple[Optional[bytes], Tuple[Artifact, ...], Dict[str, Any]]:
    """Check an AdapterOutcome against the contract before any of it is kept."""
    if not isinstance(outcome, AdapterOutcome):
        raise TypeError(f"run() returned {type(outcome).__name__}, not an AdapterOutcome")
    if not isinstance(outcome.summary, str):
        raise TypeError("the summary is not text")
    verdict = outcome_for(kind, outcome.exit_code, outcome.summary, outcome.refusal, outcome.name_refusal,
                          has_result=outcome.result is not None)
    result_bytes: Optional[bytes] = None
    if outcome.result is not None:
        if not isinstance(outcome.result, Mapping):
            raise TypeError(f"the result is {type(outcome.result).__name__}, not an object")
        result_bytes = json_bytes(dict(outcome.result))  # ValueError on NaN, TypeError on unknown types
    names = set()
    for artifact in outcome.artifacts:
        if not isinstance(artifact, Artifact):
            raise TypeError(f"an artifact is {type(artifact).__name__}, not an Artifact")
        if artifact.name in names:
            raise ValueError(f"two artifacts are called {artifact.name!r}")
        if not re.fullmatch(ARTIFACT_NAME_PATTERN, artifact.name):
            raise ValueError(f"{artifact.name!r} is not an artifact name")
        if not isinstance(artifact.content, (bytes, bytearray)):
            raise TypeError(f"artifact {artifact.name!r} holds {type(artifact.content).__name__}, not bytes")
        names.add(artifact.name)
    return result_bytes, tuple(outcome.artifacts), dict(verdict)


def _duration(seconds: Optional[float]) -> str:
    if seconds is None:
        return "no limit"
    if seconds >= 3600 and math.isclose(seconds % 3600, 0.0, abs_tol=1e-9):
        hours = int(seconds // 3600)
        return f"{hours} hour{'s' if hours != 1 else ''}"
    if seconds >= 60 and math.isclose(seconds % 60, 0.0, abs_tol=1e-9):
        minutes = int(seconds // 60)
        return f"{minutes} minute{'s' if minutes != 1 else ''}"
    return f"{seconds:g} s"


class _run_dir_lock:
    """An exclusive lock on one run directory, across processes."""

    def __init__(self, run_dir: Path) -> None:
        self._path = run_dir / ".sweep.lock"
        self._fd: Optional[int] = None

    def __enter__(self) -> "_run_dir_lock":
        if fcntl is not None and self._path.parent.is_dir():
            fd = os.open(self._path, os.O_CREAT | os.O_RDWR, 0o600)
            fcntl.flock(fd, fcntl.LOCK_EX)
            self._fd = fd
        return self

    def __exit__(self, *exc: Any) -> None:
        if self._fd is not None:
            os.close(self._fd)  # closing drops the lock
            self._fd = None


__all__ = [
    "CANCEL_GRACE_S", "Conflict", "JobManager", "KEEPALIVE_FRAME", "KEEPALIVE_S", "KEEP_LOG_LINES",
    "KIND_TIMEOUTS_S", "MAX_PENDING", "OutputRouter", "POLL_S", "QueueFull", "RUN_DIR_PLACEHOLDER", "RUN_TIMEOUT_S",
    "RunLogHandler", "SINKS", "cli_prefix",
    "make_run_id", "sse_frame",
]
