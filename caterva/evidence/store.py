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

An index that is not an evidence store's (not SQLite at all, or SQLite
without the four tables) raises `StoreUnreadable`, never a bare
`sqlite3.DatabaseError`, so a command can say which file it could not read;
so does a blob that is not gzip or does not digest to its snapshot's id,
since reading one is reading the snapshot.
`read_only=True` is for the commands that only ask (`caterva why --store`):
it opens an existing index without writing to it, so asking neither creates
a store nor adds tables to some other program's database.
"""
from __future__ import annotations

import gzip
import json
import sqlite3
import zlib
from pathlib import Path

try:
    from caterva.evidence.bundle import read_gzip, write_bundle
    from caterva.evidence.canonical import digest, digest_hex
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
    from evidence.bundle import read_gzip, write_bundle  # type: ignore[no-redef]
    from evidence.canonical import digest, digest_hex  # type: ignore[no-redef]
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

#: The tables _SCHEMA creates: an index without all four is not a store's.
_TABLES = ("snapshots", "rows", "claims", "edges")


class StoreUnreadable(EvidenceRefused):
    """The index at a store's path is not an evidence store's index."""


class EvidenceStore:
    """Records at `<path>`, created on first use."""

    def __init__(self, path: str | Path, *, read_only: bool = False) -> None:
        """Open (creating if absent) the store at `path`; with `read_only`,
        open an existing store and change nothing on disk."""
        self.path = Path(path)
        self.read_only = read_only
        index = self.path / INDEX
        if read_only:
            if not index.is_file():
                raise StoreUnreadable(f"{self.path} holds no {INDEX}: it is not an evidence store")
        else:
            self.path.mkdir(parents=True, exist_ok=True)
            (self.path / BLOBS).mkdir(exist_ok=True)
        self._db = _open_index(index, read_only=read_only)

    def close(self) -> None:
        self._db.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # -- snapshots -----------------------------------------------------------

    def _blob_path(self, snapshot_id: str) -> Path:
        return self.path / BLOBS / (digest_hex(snapshot_id) + ".gz")

    def _writable(self, what: str) -> None:
        # Refused before anything is written: put_snapshot writes the blob
        # first, and a read-only index would refuse only the row after it.
        if self.read_only:
            raise EvidenceRefused(f"{what}: the store at {self.path} was opened read only")

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
        self._writable("put_snapshot")
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
            return snapshot_from_dict(_json(existing[0], "snapshot", snapshot.id))
        self._blob_path(snapshot.id).write_bytes(gzip.compress(bytes(data), mtime=0))
        with self._db:
            self._db.execute(
                "INSERT OR REPLACE INTO snapshots (id, json) VALUES (?, ?)",
                (snapshot.id, json.dumps(to_dict(snapshot), sort_keys=True, ensure_ascii=False)),
            )
        return snapshot

    def snapshot_bytes(self, ref: str) -> bytes:
        """The raw bytes of a snapshot, held to its id as a bundle's are.

        A blob is a file anyone can overwrite, and the index never looks at
        it again, so a blob that is not gzip, or that holds other bytes, is
        StoreUnreadable naming the file. Unchecked, `caterva why --store`
        printed a traceback for the first and, for the second, the paper of a
        page that is not the one the snapshot's id names.
        """
        if ref_kind(ref) != "snapshot":
            raise EvidenceRefused(f"{ref!r} is not a snapshot ref")
        path = self._blob_path(ref_digest(ref))
        if not path.is_file():
            raise KeyError(ref)
        try:
            data = read_gzip(path)
        except ValueError as exc:
            raise StoreUnreadable(f"{path}: {exc}") from exc
        except (OSError, EOFError, zlib.error) as exc:  # BadGzipFile is an OSError
            raise StoreUnreadable(f"{path} is not a gzip stream: {exc}") from exc
        if digest(data) != ref_digest(ref):
            raise StoreUnreadable(f"{path} does not digest to {ref}: the bytes are not the snapshot's")
        return data

    def snapshots(self, *, source: str | None = None) -> list[Snapshot]:
        """Every snapshot held, or those of one source, in insertion order."""
        rows = self._db.execute("SELECT id, json FROM snapshots ORDER BY rowid").fetchall()
        found = [snapshot_from_dict(_json(text, "snapshot", key)) for (key, text) in rows]
        return [s for s in found if source is None or s.source == source]

    # -- rows and claims -----------------------------------------------------

    def put_row(self, row: Row) -> Row:
        if not isinstance(row, Row):
            raise EvidenceRefused("put_row takes a Row")
        self._writable("put_row")
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
        self._writable("put_claim")
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
        return None if found is None else _json(found[0], kind, ref_digest(ref))

    def has(self, ref: str) -> bool:
        return self._record(ref) is not None

    def get(self, ref: str):
        """The Snapshot, Row or Claim a ref names; KeyError when the store does not hold it."""
        data = self._record(ref)
        if data is None:
            raise KeyError(ref)
        return {"snapshot": snapshot_from_dict, "row": row_from_dict, "claim": claim_from_dict}[ref_kind(ref)](data)

    def claims(self, *, kind: str | None = None) -> list[Claim]:
        rows = self._db.execute("SELECT id, json FROM claims ORDER BY rowid").fetchall()
        found = [claim_from_dict(_json(text, "claim", key)) for (key, text) in rows]
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


def _json(text: str, kind: str, key: str) -> dict:
    """A stored record's JSON; StoreUnreadable naming the record when the
    index holds text that is not JSON (a record edited by hand, or cut off)."""
    try:
        return json.loads(text)
    except (TypeError, ValueError) as exc:
        raise StoreUnreadable(f"the {kind} record {key} in the store's index is not JSON: {exc}") from exc


def _open_index(index: Path, *, read_only: bool) -> sqlite3.Connection:
    """A connection to `index`, holding the store's four tables; StoreUnreadable
    when the file is not SQLite or (read only, where nothing is created)
    lacks a table. sqlite3 connects to any file and fails at the first
    statement, so the statements are run here, where the failure is named."""
    try:
        if read_only:
            db = sqlite3.connect(index.resolve().as_uri() + "?mode=ro", uri=True)
        else:
            db = sqlite3.connect(str(index))
    except sqlite3.DatabaseError as exc:  # cannot be opened at all
        raise StoreUnreadable(f"{index} cannot be opened as an evidence store's index: {exc}") from exc
    missing: list[str] = []
    try:
        if read_only:
            present = {name for (name,) in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
            missing = [table for table in _TABLES if table not in present]
        else:
            with db:
                for statement in _SCHEMA:
                    db.execute(statement)
    except sqlite3.DatabaseError as exc:
        db.close()
        raise StoreUnreadable(f"{index} is not an evidence store's index: {exc}") from exc
    except BaseException:
        db.close()
        raise
    if missing:
        db.close()
        raise StoreUnreadable(
            f"{index} is a SQLite database without the {', '.join(missing)} "
            "table(s): it is not an evidence store's index"
        )
    return db


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


__all__ = ["BLOBS", "INDEX", "EvidenceStore", "StoreUnreadable"]
