"""Pin what the resolver reads, as it reads it.

WHY AN OBSERVER AND NOT A WRAPPER
---------------------------------
Tests/fallback_logic.py binds `fetch_brenda_html` as a default argument of
`resolve_kinetic_value`, so a function that wrapped `fetch_brenda_html`
after import would never see the resolver's calls. Tests/brenda_client.py
therefore calls every function in `PAGE_OBSERVERS` with
`(ec_number, html, served_from)` at the end of `fetch_brenda_html`, on the
live path and the recorded one, and the `Recorder` below registers one for
the length of a `with` block. Outside that block nothing is observed and
the literature layer runs exactly as before (ADR 0179).

WHAT IS PINNED
--------------
The page's text as the parser received it, encoded as UTF-8, with the
enzyme page URL, the moment, BRENDA's licence (CC BY 4.0) and, when a test
replayed a recording, the recording's path in `served_from`. For a page
fetched live `served_from` is None. The snapshot is a dated record of what
was read; the product still fetches live, and nothing here serves a
snapshot back as a current answer (Tests/fixtures/recorded/README.md).

`capture_reference` pins the literature page for one (enzyme, reference)
through `http_retry.retry_get`, the one function every other literature GET
goes through, so a test's recordings apply to it; the bytes stored are the
response's own.
"""
from __future__ import annotations

import importlib
import os
from pathlib import Path
from typing import Any

try:
    from caterva.checkout import literature_module
    from caterva.evidence.claims import EvidenceRefused, Snapshot, now_utc
    from caterva.evidence.references import LITERATURE_URL, reference_url
except ImportError:  # pragma: no cover - flat layout
    from checkout import literature_module  # type: ignore[no-redef]
    from evidence.claims import EvidenceRefused, Snapshot, now_utc  # type: ignore[no-redef]
    from evidence.references import LITERATURE_URL, reference_url  # type: ignore[no-redef]

ENZYME_URL = "https://www.brenda-enzymes.org/enzyme.php"
BRENDA_LICENCE = "CC BY 4.0"


def enzyme_page_url(ec: str) -> str:
    """The URL `fetch_brenda_html` asks for: the enzyme page of `ec`."""
    return f"{ENZYME_URL}?ecno={ec}"


def client_modules() -> list[Any]:
    """Every loaded copy of brenda_client, so an observer misses no fetch.

    One file can be two module objects: `literature_module` tries the package
    form `Tests.brenda_client` and the flat form `brenda_client`, and which one
    answers depends on whether `Tests/` was already on `sys.path` when it was
    asked (the package form's own flat imports need it there). The resolver
    (Tests/fallback_logic.py) binds `fetch_brenda_html` from the flat form.
    An observer registered on the other copy would see nothing, and a run
    would report its pages pinned when none were. So both forms are imported
    where they can be, and the observer goes on each one's PAGE_OBSERVERS.
    """
    found = [literature_module("brenda_client")]
    for name in ("brenda_client", "Tests.brenda_client"):
        try:
            module = importlib.import_module(name)
        except ImportError:
            continue
        if all(module is not known for known in found):
            found.append(module)
    return found


class Recorder:
    """Register a page observer for a `with` block; `snapshots` maps EC -> Snapshot."""

    def __init__(self, store: Any) -> None:
        """`store` is the EvidenceStore every observed page is put into."""
        self.store = store
        self.snapshots: dict[str, Snapshot] = {}
        self._clients: list[Any] = []

    def _observe(self, ec_number: str, html: str, served_from: str | None) -> None:
        snapshot = self.store.put_snapshot(
            html.encode("utf-8"), source="brenda_enzyme", locator=enzyme_page_url(ec_number),
            retrieved_at=now_utc(), licence=BRENDA_LICENCE,
            served_from=str(served_from) if served_from else None,
        )
        self.snapshots[str(ec_number)] = snapshot

    def __enter__(self):
        self._clients = client_modules()
        for client in self._clients:
            observers = getattr(client, "PAGE_OBSERVERS", None)
            if observers is None:
                raise EvidenceRefused(
                    f"{client.__name__} has no PAGE_OBSERVERS hook, so nothing can pin the "
                    "pages the resolver reads (ADR 0179)"
                )
            observers.append(self._observe)
        return self

    def __exit__(self, *exc: object) -> None:
        for client in self._clients:
            observers = getattr(client, "PAGE_OBSERVERS", [])
            while self._observe in observers:
                observers.remove(self._observe)
        self._clients = []

    def snapshot_for(self, ec: str) -> Snapshot | None:
        """The page pinned for `ec` in this block, or None when none was read."""
        return self.snapshots.get(str(ec))


def _served_from(http_retry: Any, url: str, kwargs: dict) -> str | None:
    """The recording that will answer this request, when a test set one up.

    Read through http_retry's own constant so the snapshot can say it was
    served from a file: this module never sets the variable, and outside a
    test it is unset and the answer is None.
    """
    directory = os.environ.get(getattr(http_retry, "RECORDED_ENV", ""))
    if not directory:
        return None
    key = http_retry.replay_key(url, kwargs)
    if key is None:
        return None
    path = Path(directory) / http_retry.recording_name(key)
    return str(path) if path.is_file() else None


def capture_reference(ec: str, ref: str, store: Any, *, timeout: float = 15) -> Snapshot:
    """Fetch the literature page for (ec, ref) and store it as a brenda_reference snapshot.

    Raises `httpx.HTTPStatusError` (from `raise_for_status`) when BRENDA
    answers with an error, and whatever `retry_get` raises when it cannot
    reach the service: a page that was not captured is not pretended to be.
    """
    http_retry = literature_module("http_retry")
    params = {"e": str(ec), "r": str(ref)}
    kwargs = {"params": params, "timeout": timeout}
    served_from = _served_from(http_retry, LITERATURE_URL, kwargs)
    response = http_retry.retry_get(LITERATURE_URL, **kwargs)
    response.raise_for_status()
    return store.put_snapshot(
        bytes(response.content), source="brenda_reference", locator=reference_url(ec, ref),
        retrieved_at=now_utc(), licence=BRENDA_LICENCE, served_from=served_from,
    )


__all__ = ["BRENDA_LICENCE", "ENZYME_URL", "Recorder", "capture_reference", "client_modules", "enzyme_page_url"]
