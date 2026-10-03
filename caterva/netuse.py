"""Real network use, noted as it happens, so a status display can be honest.

The commands that reach a database (the literature layer's BRENDA, UniProt,
NCBI and PubMed calls, the structure search, `caterva prepare`) call
`answered(url)` when a host answered and `failed(url, reason)` when it could
not be reached. Nothing here makes a request or decides anything: it passes
the fact to whoever subscribed. Caterva Studio subscribes, so its status bar
can say "reachable, as of the last BRENDA lookup" instead of "not checked"
after a lookup just worked.

An HTTP error status is an answer: the host was reached. A refused
connection, a failed name lookup or a timeout is `failed`. A response
replayed from a recording or a memo touched no network and is never noted.
"""
from __future__ import annotations

import threading
from typing import Callable, List, Optional
from urllib.parse import urlsplit

#: (host, reached, why not). Called on the thread that made the request.
Listener = Callable[[str, bool, Optional[str]], None]

_lock = threading.Lock()
_listeners: List[Listener] = []


def subscribe(listener: Listener) -> Callable[[], None]:
    """Be told of every later request outcome. Returns the call that stops it."""
    with _lock:
        _listeners.append(listener)

    def unsubscribe() -> None:
        with _lock:
            if listener in _listeners:
                _listeners.remove(listener)

    return unsubscribe


def _notify(url: str, reached: bool, reason: Optional[str]) -> None:
    host = urlsplit(url).hostname or ""
    if not host:
        return
    with _lock:
        listeners = list(_listeners)
    for listener in listeners:
        try:
            listener(host, reached, reason)
        except Exception:  # noqa: BLE001 - a status display must never break a lookup
            pass


def answered(url: str) -> None:
    """The host at `url` answered (with any status)."""
    _notify(url, True, None)


def failed(url: str, reason: object) -> None:
    """The host at `url` could not be reached."""
    text = str(reason).strip() or type(reason).__name__
    _notify(url, False, text)


__all__ = ["answered", "failed", "subscribe"]
