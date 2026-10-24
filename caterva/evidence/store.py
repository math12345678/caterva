"""Where a run's evidence is kept: snapshots, rows, claims, and the edges between them.

WHY A STORE AND NOT ONLY A BUNDLE
---------------------------------
A bundle (bundle.py) is one model's closure, written once. A run of
`caterva compose --claims DIR` pins every page the resolver read as it reads
it (capture.py), before anybody knows which rows will be cited; the rows and
claims come later. The store takes records as they arrive, keeps the
reverse index (`dependents`: which rows came from this page, which claims
from those rows), and exports the closure of one root claim as a bundle.

SQLite, standard library, one file plus a blob directory:

    <path>/index.sqlite   snapshots(id, json), rows(id, snapshot, json),
                          claims(id, kind, subject, json), edges(src_ref, dst_ref)
    <path>/blobs/<hex>.gz the raw bytes of each snapshot, gzipped (mtime 0)

WHAT IS REFUSED
---------------
A row whose snapshot the store does not hold; a claim whose row or claim
inputs it does not hold (an `ir:` input names a compiled source by digest
and is never stored). A snapshot is identified by its bytes alone, so putting
the same bytes twice is one snapshot, and the record of the FIRST retrieval
stands: the later fetch read nothing new.
"""
from __future__ import annotations

import gzip
import json
import sqlite3
from pathlib import Path

try:
    from caterva.evidence.bundle import write_bundle
    from caterva.evidence.canonical import digest_hex
    from caterva.evidence.claims import (
        Claim,
        EvidenceRefused,
        Row,
        Snapshot,
        claim_from_dict,
        make_snapshot,
        ref_digest,
        ref_kind,
        row_from_dict,
        snapshot_from_dict,
        to_dict,
    )
except ImportError:  # pragma: no cover - flat layout
    from evidence.bundle import write_bundle  # type: ignore[no-redef]
    from evidence.canonical import digest_hex  # type: ignore[no-redef]
    from evidence.claims import (  # type: ignore[no-redef]
        Claim,
        EvidenceRefused,
        Row,
        Snapshot,
        claim_from_dict,
        make_snapshot,
        ref_digest,
        ref_kind,
        row_from_dict,
        snapshot_from_dict,
        to_dict,
    )

INDEX = "index.sqlite"
BLOBS = "blobs"

_SCHEMA = (
    "CREATE TABLE IF NOT EXISTS snapshots (id TEXT PRIMARY KEY, json TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS rows (id TEXT PRIMARY KEY, snapshot TEXT NOT NULL, json TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS claims (id TEXT PRIMARY KEY, kind TEXT NOT NULL, subject TEXT NOT NULL, json TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS edges (src_ref TEXT NOT NULL, dst_ref TEXT NOT NULL, PRIMARY KEY (src_ref, dst_ref))",
    "CREATE INDEX IF NOT EXISTS edges_dst ON edges (dst_ref)",
)


class EvidenceStore:
    """Records at `<path>`, created on first use."""

    def __init__(self, path: str | Path) -> None:
        """Open (creating if absent) the store at `path`."""
        self.path = Path(path)
        self.path.mkdir(parents=True, exist_ok=True)
        (self.path / BLOBS).mkdir(exist_ok=True)
        self._db = sqlite3.connect(str(self.path / INDEX))
        with self._db:
            for statement in _SCHEMA:
                self._db.execute(statement)

    def close(self) -> None:
        self._db.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # -- snapshots -----------------------------------------------------------

    def _blob_path(self, snapshot_id: str) -> Path:
        return self.path / BLOBS / (digest_hex(snapshot_id) + ".gz")

    def put_snapshot(
        self,
        data: bytes,
        *,
        source: str,
        locator: str,
        retrieved_at: str,
        licence: str,
        release: str | None = None,
        served_from: str | None = None,
    ) -> Snapshot:
        """Store `data` and its metadata; the stored record wins when the bytes are already held."""
        snapshot = make_snapshot(
            data, source=source, locator=locator, retrieved_at=retrieved_at,
            licence=licence, release=release, served_from=served_from,
        )
        existing = self._db.execute("SELECT json FROM snapshots WHERE id = ?", (snapshot.id,)).fetchone()
        if existing is not None:
            # The first retrieval's record stands; a lost blob is rewritten
            # from the same bytes, which is all its id promises.
            if not self._blob_path(snapshot.id).is_file():
                self._blob_path(snapshot.id).write_bytes(gzip.compress(bytes(data), mtime=0))
            return snapshot_from_dict(json.loads(existing[0]))
        self._blob_path(snapshot.id).write_bytes(gzip.compress(bytes(data), mtime=0))
        with self._db:
            self._db.execute(
                "INSERT OR REPLACE INTO snapshots (id, json) VALUES (?, ?)",
                (snapshot.id, json.dumps(to_dict(snapshot), sort_keys=True, ensure_ascii=False)),
            )
        return snapshot

    def snapshot_bytes(self, ref: str) -> bytes:
        if ref_kind(ref) != "snapshot":
            raise EvidenceRefused(f"{ref!r} is not a snapshot ref")
        path = self._blob_path(ref_digest(ref))
        if not path.is_file():
            raise KeyError(ref)
        return gzip.decompress(path.read_bytes())

    def snapshots(self, *, source: str | None = None) -> list[Snapshot]:
        """Every snapshot held, or those of one source, in insertion order."""
        rows = self._db.execute("SELECT json FROM snapshots ORDER BY rowid").fetchall()
        found = [snapshot_from_dict(json.loads(text)) for (text,) in rows]
        return [s for s in found if source is None or s.source == source]

    # -- rows and claims -----------------------------------------------------

    def put_row(self, row: Row) -> Row:
        if not isinstance(row, Row):
            raise EvidenceRefused("put_row takes a Row")
        if not self.has(row.snapshot):
            raise EvidenceRefused(f"row {row.ref} was read from {row.snapshot}, which this store does not hold")
        with self._db:
            self._db.execute(
                "INSERT OR REPLACE INTO rows (id, snapshot, json) VALUES (?, ?, ?)",
                (row.id, row.snapshot, json.dumps(to_dict(row), sort_keys=True, ensure_ascii=False)),
            )
            self._db.execute(
                "INSERT OR IGNORE INTO edges (src_ref, dst_ref) VALUES (?, ?)", (row.ref, row.snapshot),
            )
        return row

    def put_claim(self, claim: Claim) -> Claim:
        """Store a claim and one edge from it to each input it depends on."""
        if not isinstance(claim, Claim):
            raise EvidenceRefused("put_claim takes a Claim")
        for input_ref in claim.derivation.inputs:
            if ref_kind(input_ref) != "ir" and not self.has(input_ref):
                raise EvidenceRefused(
                    f"claim {claim.ref} ({claim.subject}) depends on {input_ref}, which this store does not hold"
                )
        for certificate in claim.derivation.certificates:
            if not self.has(certificate.snapshot):
                raise EvidenceRefused(
                    f"claim {claim.ref} ({claim.subject}) certifies a span in {certificate.snapshot}, "
                    "which this store does not hold"
                )
        with self._db:
            self._db.execute(
                "INSERT OR REPLACE INTO claims (id, kind, subject, json) VALUES (?, ?, ?, ?)",
                (claim.id, claim.kind, claim.subject,
                 json.dumps(to_dict(claim), sort_keys=True, ensure_ascii=False)),
            )
            for input_ref in claim.derivation.inputs:
                if ref_kind(input_ref) != "ir":
                    self._db.execute(
                        "INSERT OR IGNORE INTO edges (src_ref, dst_ref) VALUES (?, ?)", (claim.ref, input_ref),
                    )
            for certificate in claim.derivation.certificates:
                self._db.execute(
                    "INSERT OR IGNORE INTO edges (src_ref, dst_ref) VALUES (?, ?)",
                    (claim.ref, certificate.snapshot),
                )
        return claim

    # -- reading -------------------------------------------------------------

    def _record(self, ref: str):
        kind = ref_kind(ref)
        table = {"snapshot": "snapshots", "row": "rows", "claim": "claims"}.get(kind)
        if table is None:
            return None
        found = self._db.execute(f"SELECT json FROM {table} WHERE id = ?", (ref_digest(ref),)).fetchone()
        return None if found is None else json.loads(found[0])

    def has(self, ref: str) -> bool:
        return self._record(ref) is not None

    def get(self, ref: str):
        """The Snapshot, Row or Claim a ref names; KeyError when the store does not hold it."""
        data = self._record(ref)
        if data is None:
            raise KeyError(ref)
        return {"snapshot": snapshot_from_dict, "row": row_from_dict, "claim": claim_from_dict}[ref_kind(ref)](data)

    def claims(self, *, kind: str | None = None) -> list[Claim]:
        rows = self._db.execute("SELECT json FROM claims ORDER BY rowid").fetchall()
        found = [claim_from_dict(json.loads(text)) for (text,) in rows]
        return [c for c in found if kind is None or c.kind == kind]

    def inputs_of(self, ref: str) -> list[str]:
        """The refs `ref` points to (its inputs, or a row's snapshot)."""
        return [dst for (dst,) in self._db.execute(
            "SELECT dst_ref FROM edges WHERE src_ref = ? ORDER BY rowid", (ref,),
        ).fetchall()]

    def dependents(self, ref: str) -> list[str]:
        """Everything that depends on `ref`, transitively: the rows read from a
        page and the claims built on them, in breadth-first order."""
        seen: list[str] = []
        frontier = [ref]
        while frontier:
            current = frontier.pop(0)
            for (src,) in self._db.execute(
                "SELECT src_ref FROM edges WHERE dst_ref = ? ORDER BY rowid", (current,),
            ).fetchall():
                if src not in seen and src != ref:
                    seen.append(src)
                    frontier.append(src)
        return seen

    # -- export --------------------------------------------------------------

    def closure(self, root_ref: str) -> list[str]:
        """`root_ref` and everything it depends on, transitively, depth first."""
        if not self.has(root_ref):
            raise KeyError(root_ref)
        order: list[str] = []
        stack = [root_ref]
        while stack:
            current = stack.pop()
            if current in order:
                continue
            order.append(current)
            stack.extend(dst for dst in self.inputs_of(current) if dst not in order)
        return order

    def export_bundle(self, root_ref: str, directory: str | Path) -> Path:
        """Write the closure of `root_ref` as a bundle, with the reference pages
        (source brenda_reference) captured for the rows it cites, found by
        locator since a row does not point at the paper's page."""
        if ref_kind(root_ref) != "claim":
            raise EvidenceRefused(f"a bundle's root is a claim, not {root_ref!r}")
        refs = self.closure(root_ref)
        claims = [self.get(r) for r in refs if ref_kind(r) == "claim"]
        rows = [self.get(r) for r in refs if ref_kind(r) == "row"]
        snapshots = [self.get(r) for r in refs if ref_kind(r) == "snapshot"]
        held = {s.id for s in snapshots}
        wanted = _reference_locators(rows)
        for snapshot in self.snapshots(source="brenda_reference"):
            if snapshot.locator in wanted and snapshot.id not in held:
                snapshots.append(snapshot)
                held.add(snapshot.id)
        blobs = {s.id: self.snapshot_bytes(s.ref) for s in snapshots}
        return write_bundle(
            directory, root=root_ref, claims=claims, rows=rows, snapshots=snapshots, blobs=blobs,
        )


def _reference_locators(rows: list[Row]) -> set[str]:
    try:
        from caterva.evidence.references import reference_url
        from caterva.evidence.rows import locator_ec
    except ImportError:  # pragma: no cover - flat layout
        from evidence.references import reference_url  # type: ignore[no-redef]
        from evidence.rows import locator_ec  # type: ignore[no-redef]
    wanted = set()
    for row in rows:
        ec = locator_ec(row.locator)
        if row.reference and ec:
            wanted.add(reference_url(ec, row.reference))
    return wanted


__all__ = ["BLOBS", "INDEX", "EvidenceStore"]
