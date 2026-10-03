"""Server-side bounds on work a request can start, and on connections.

WHY THEY ARE HERE
-----------------
Everything that answers a request on this server is plain Python on a few
threads. The enzyme finder spends 0.3 to 0.6 s of CPU on a query it has not
seen (and, for short Unicode strings, several seconds when the machine is
busy), and keeps answers only per exact query, so a page, or anything else
that can reach the port with the session token, can keep every core busy by
asking for new strings. A connection that sends a byte a minute can hold a
thread forever. These limits do not make the work cheaper; they make it
impossible to start without bound:

- `SearchGuard`: at most `concurrent` searches at once, answers kept per
  NORMALISED query (case, accents of compatibility form, spacing), and a
  wall-clock budget per request. A search that outlasts the budget is not
  abandoned: it finishes in its own thread, its answer is kept, and the
  request that gave up is told to ask again in a moment, which then costs
  nothing.
- `Gate`: a counting gate for connections and event streams, which refuses
  rather than waits.
- `DeadlineReader`: wraps a connection's read side so a request must arrive
  within a total time, not merely with no pause longer than the idle limit.

None of this decides what an answer says. The finder's own module is not
changed: the dispatch layer wraps the endpoint (dispatch._adapter_endpoint).
"""
from __future__ import annotations

import copy
import socket
import threading
import time
import unicodedata
from collections import OrderedDict
from typing import Any, Callable, Dict, Hashable, Optional, Tuple

from caterva.studio.contract import Unavailable

#: Finder searches that may run at once.
FINDER_CONCURRENCY = 2
#: How long one request waits for its answer, in seconds, before it is told to ask again.
FINDER_BUDGET_S = 4.0
#: How long a request waits for a free search slot, in seconds, before it is refused.
FINDER_QUEUE_WAIT_S = 1.0
#: Answers kept, by normalised query.
FINDER_CACHE_SIZE = 512
#: What a refused request is told to wait, in seconds.
RETRY_AFTER_S = 2

#: Connections the server serves at once, and event streams among them.
MAX_CONNECTIONS = 64
MAX_STREAMS = 16
#: A request line and its headers must arrive within this many seconds of its first byte, its body within this many
#: of the start of the body, and a connection may sit idle between requests this long.
HEADER_DEADLINE_S = 10.0
BODY_DEADLINE_S = 30.0
IDLE_S = 60.0


class Busy(Unavailable):
    """Too much is already being worked on: HTTP 503 with Retry-After."""

    def __init__(self, message: str, retry_after_s: int = RETRY_AFTER_S) -> None:
        super().__init__(message)
        self.retry_after_s = retry_after_s


def normalise_text(text: Any) -> str:
    """A query as the finder will treat it: compatibility-normalised (so a
    full-width or accented spelling and its plain one share an entry),
    case-folded, with runs of whitespace as one space."""
    if not isinstance(text, str):
        return ""
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


class _Pending:
    """One search in flight: its waiters, and its answer when it ends."""

    def __init__(self) -> None:
        self.done = threading.Event()
        self.value: Any = None
        self.error: Optional[BaseException] = None


class SearchGuard:
    """Run `fn` for a key under the bounds in the module docstring."""

    def __init__(self, *, concurrent: int = FINDER_CONCURRENCY, budget_s: float = FINDER_BUDGET_S,
                 queue_wait_s: float = FINDER_QUEUE_WAIT_S, cache_size: int = FINDER_CACHE_SIZE) -> None:
        self._slots = threading.Semaphore(concurrent)
        self.concurrent = concurrent
        self.budget_s = budget_s
        self.queue_wait_s = queue_wait_s
        self._cache_size = cache_size
        self._cache: "OrderedDict[Hashable, Any]" = OrderedDict()
        self._inflight: Dict[Hashable, _Pending] = {}
        self._lock = threading.Lock()
        self.started = 0  # searches actually run: what a test counts

    def run(self, key: Hashable, fn: Callable[[], Any]) -> Any:
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                return copy.deepcopy(self._cache[key])
            pending = self._inflight.get(key)
            owner = pending is None
            if owner:
                pending = self._inflight[key] = _Pending()
        assert pending is not None
        if owner:
            if not self._slots.acquire(timeout=self.queue_wait_s):
                with self._lock:
                    self._inflight.pop(key, None)
                pending.error = Busy("the enzyme search is busy with other requests; try again in a moment")
                pending.done.set()
                raise pending.error
            threading.Thread(target=self._work, args=(key, fn, pending), name="caterva-finder-search",
                             daemon=True).start()
        if not pending.done.wait(self.budget_s):
            raise Busy(f"the enzyme search took longer than {self.budget_s:g} s; it is still working, so ask "
                       "again in a moment and the answer will be ready")
        if pending.error is not None:
            raise pending.error
        return copy.deepcopy(pending.value)

    def _work(self, key: Hashable, fn: Callable[[], Any], pending: _Pending) -> None:
        try:
            self.started += 1
            pending.value = fn()
            with self._lock:
                self._cache[key] = copy.deepcopy(pending.value)
                self._cache.move_to_end(key)
                while len(self._cache) > self._cache_size:
                    self._cache.popitem(last=False)
        except BaseException as exc:  # noqa: BLE001 - handed to every waiter, which re-raises it
            pending.error = exc
        finally:
            with self._lock:
                self._inflight.pop(key, None)
            self._slots.release()
            pending.done.set()


class Gate:
    """A counter with a ceiling: `enter()` is False at the ceiling, never a wait."""

    def __init__(self, ceiling: int) -> None:
        self.ceiling = ceiling
        self._count = 0
        self._lock = threading.Lock()

    def enter(self) -> bool:
        with self._lock:
            if self._count >= self.ceiling:
                return False
            self._count += 1
            return True

    def leave(self) -> None:
        with self._lock:
            self._count = max(0, self._count - 1)

    @property
    def count(self) -> int:
        with self._lock:
            return self._count


class GuardedStream:
    """An event stream that holds a slot of `gate` until it is closed, ends,
    or raises. Closing is idempotent, and works on a stream never started
    (a generator closed before its first step would not run its `finally`)."""

    def __init__(self, frames: Any, gate: Gate) -> None:
        self._frames = iter(frames)
        self._source = frames
        self._gate = gate
        self._open = True
        self._lock = threading.Lock()

    def __iter__(self) -> "GuardedStream":
        return self

    def __next__(self) -> bytes:
        try:
            return next(self._frames)
        except BaseException:
            self.close()
            raise

    def close(self) -> None:
        with self._lock:
            if not self._open:
                return
            self._open = False
        try:
            close = getattr(self._source, "close", None)
            if callable(close):
                close()
        finally:
            self._gate.leave()

    def __del__(self) -> None:  # a stream dropped without being closed still gives its slot back
        try:
            self.close()
        except Exception:  # noqa: BLE001 - never raise from a finaliser
            pass


class DeadlineReader:
    """The read side of a connection, with total deadlines.

    `socket.settimeout` bounds each wait, so a client that sends a byte every
    few seconds keeps a request open for as long as it likes. This wraps the
    connection's file object: `begin()` marks the start of a request (waiting
    for its first line is idle time, up to `idle_s`), the first line arriving
    arms `header_s`, and `arm(seconds)` sets another total (the body). When a
    deadline passes the next read raises `socket.timeout` and the handler
    closes the connection."""

    def __init__(self, raw: Any, sock: socket.socket, *, idle_s: float = IDLE_S, header_s: float = HEADER_DEADLINE_S,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self._raw = raw
        self._sock = sock
        self._idle_s = idle_s
        self._header_s = header_s
        self._clock = clock
        self._deadline: Optional[float] = None
        self._first_line = False

    def begin(self) -> None:
        self._deadline = None
        self._first_line = True

    def arm(self, seconds: float) -> None:
        self._deadline = self._clock() + seconds

    def disarm(self) -> None:
        self._deadline = None

    def _limit(self) -> None:
        wait = self._idle_s
        if self._deadline is not None:
            remaining = self._deadline - self._clock()
            if remaining <= 0:
                raise socket.timeout("the request did not arrive in time")
            wait = min(wait, remaining)
        self._sock.settimeout(wait)

    def readline(self, size: int = -1) -> bytes:
        self._limit()
        line = self._raw.readline(size)
        if self._first_line and line:
            self._first_line = False
            self.arm(self._header_s)
        return line

    def read(self, size: int = -1) -> bytes:
        self._limit()
        return self._raw.read(size)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._raw, name)


def retry_after(exc: BaseException) -> Optional[Tuple[str, str]]:
    """The Retry-After header an exception asks for, if it asks."""
    seconds = getattr(exc, "retry_after_s", None)
    return ("Retry-After", str(int(seconds))) if seconds is not None else None


__all__ = ["BODY_DEADLINE_S", "Busy", "DeadlineReader", "FINDER_BUDGET_S", "FINDER_CONCURRENCY", "Gate",
           "GuardedStream", "HEADER_DEADLINE_S", "IDLE_S", "MAX_CONNECTIONS", "MAX_STREAMS", "RETRY_AFTER_S",
           "SearchGuard", "normalise_text", "retry_after"]
