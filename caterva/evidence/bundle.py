"""The exchange format: a directory a checker can read with the standard library.

WHY A DIRECTORY OF JSON LINES AND GZIPPED PAGES
-----------------------------------------------
`caterva verify` (ADR 0179) re-checks a model's claims without importing a
line of the code that wrote them, so the format has to be readable with
`json`, `gzip` and `hashlib` alone, and every object has to be addressable by
the digest that is its identity. One record per line, one blob per snapshot
named by its digest's hex, and a manifest naming the root claim:

    <dir>/manifest.json       {"format": "caterva-claims/1", "root": "claim:sha256:...",
                               "written_at": "...", "caterva": "<version>"}
    <dir>/claims.jsonl        one Claim per line
    <dir>/rows.jsonl          one Row per line
    <dir>/snapshots.jsonl     one Snapshot per line (metadata)
    <dir>/snapshots/<hex>.gz  the raw bytes, gzipped (mtime 0, so bytes are stable)

WHAT IS REFUSED
---------------
Writing a bundle that is not closed: a root not among the claims, a claim
whose row or claim input is missing, a row whose snapshot is missing, a
snapshot without its bytes or with bytes that do not digest to its id.
Reading a bundle any of whose records fails its own invariants (`claim_from_
dict` recomputes the id), or whose manifest is not this format. A bundle
that cannot be read raises `BundleUnreadable`, which the commands report as
"malformed" (exit 2) rather than as a failed check (exit 3): a file that is
not a bundle has not been checked and found wanting; it has not been checked.
"""
from __future__ import annotations

import gzip
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

try:
    from caterva.evidence.canonical import digest, digest_hex
    from caterva.evidence.claims import (
        Claim,
        EvidenceRefused,
        Row,
        Snapshot,
        claim_from_dict,
        now_utc,
        ref_digest,
        ref_kind,
        row_from_dict,
        snapshot_from_dict,
        to_dict,
    )
except ImportError:  # pragma: no cover - flat layout
    from evidence.canonical import digest, digest_hex  # type: ignore[no-redef]
    from evidence.claims import (  # type: ignore[no-redef]
        Claim,
        EvidenceRefused,
        Row,
        Snapshot,
        claim_from_dict,
        now_utc,
        ref_digest,
        ref_kind,
        row_from_dict,
        snapshot_from_dict,
        to_dict,
    )

FORMAT = "caterva-claims/1"
MANIFEST = "manifest.json"
CLAIMS = "claims.jsonl"
ROWS = "rows.jsonl"
SNAPSHOTS = "snapshots.jsonl"
BLOBS = "snapshots"


class BundleUnreadable(EvidenceRefused):
    """The directory is not a bundle of this format, or a record in it lies."""


def caterva_version() -> str:
    """The package version for the manifest; "unknown" where the package is not importable."""
    try:
        from caterva import __version__
    except ImportError:  # pragma: no cover - flat layout
        return "unknown"
    return str(__version__)


@dataclass
class Bundle:
    """A bundle read from disk: records by ref, bytes on demand."""

    directory: Path
    manifest: dict
    claims: dict[str, Claim] = field(default_factory=dict)
    rows: dict[str, Row] = field(default_factory=dict)
    snapshots: dict[str, Snapshot] = field(default_factory=dict)

    @property
    def root(self) -> str:
        return str(self.manifest["root"])

    def get(self, ref: str):
        """The Claim, Row or Snapshot a ref names; KeyError when absent."""
        kind = ref_kind(ref)
        table = {"claim": self.claims, "row": self.rows, "snapshot": self.snapshots}.get(kind)
        if table is None or ref not in table:
            raise KeyError(ref)
        return table[ref]

    def blob_path(self, ref: str) -> Path:
        return self.directory / BLOBS / (digest_hex(ref_digest(ref)) + ".gz")

    def snapshot_bytes(self, ref: str) -> bytes:
        """The raw bytes of a snapshot, held to its id."""
        if ref_kind(ref) != "snapshot":
            raise EvidenceRefused(f"{ref!r} is not a snapshot ref")
        path = self.blob_path(ref)
        if not path.is_file():
            raise BundleUnreadable(f"{path} is missing: the bundle names a snapshot it does not hold")
        data = gzip.decompress(path.read_bytes())
        if digest(data) != ref_digest(ref):
            raise BundleUnreadable(f"{path} does not digest to {ref}: the bytes are not the snapshot's")
        return data


def _check_closed(
    root: str, claims: Mapping[str, Claim], rows: Mapping[str, Row],
    snapshots: Mapping[str, Snapshot], blobs: Mapping[str, bytes],
) -> None:
    if ref_kind(root) != "claim" or root not in claims:
        raise EvidenceRefused(f"the root {root!r} is not among the claims being written")
    for ref, claim in claims.items():
        for input_ref in claim.derivation.inputs:
            kind = ref_kind(input_ref)
            if kind == "row" and input_ref not in rows:
                raise EvidenceRefused(f"{ref} ({claim.subject}) cites row {input_ref}, which is not in the bundle")
            if kind == "claim" and input_ref not in claims:
                raise EvidenceRefused(f"{ref} ({claim.subject}) depends on {input_ref}, which is not in the bundle")
            if kind == "snapshot" and input_ref not in snapshots:
                raise EvidenceRefused(f"{ref} ({claim.subject}) names {input_ref}, which is not in the bundle")
        for certificate in claim.derivation.certificates:
            if certificate.snapshot not in snapshots:
                raise EvidenceRefused(f"{ref} certifies a span in {certificate.snapshot}, which is not in the bundle")
    for ref, row in rows.items():
        if row.snapshot not in snapshots:
            raise EvidenceRefused(f"row {ref} was read from {row.snapshot}, which is not in the bundle")
    for ref, snapshot in snapshots.items():
        data = blobs.get(snapshot.id)
        if data is None:
            raise EvidenceRefused(f"{ref} has no bytes to write")
        if digest(data) != snapshot.id:
            raise EvidenceRefused(f"the bytes given for {ref} digest to {digest(data)}, not to its id")


def _by_ref(records: Iterable, kind: str) -> dict:
    out = {}
    for record in records:
        out[f"{kind}:{record.id}"] = record
    return out


def write_bundle(
    directory: str | Path,
    *,
    root: str,
    claims: Iterable[Claim],
    rows: Iterable[Row],
    snapshots: Iterable[Snapshot],
    blobs: Mapping[str, bytes],
) -> Path:
    """Write a closed bundle to `directory` (created if absent). Returns the path.

    `blobs` maps each snapshot's id (the digest) to its raw bytes.
    """
    claims_by_ref = _by_ref(claims, "claim")
    rows_by_ref = _by_ref(rows, "row")
    snapshots_by_ref = _by_ref(snapshots, "snapshot")
    _check_closed(root, claims_by_ref, rows_by_ref, snapshots_by_ref, blobs)

    target = Path(directory)
    target.mkdir(parents=True, exist_ok=True)
    (target / BLOBS).mkdir(exist_ok=True)
    manifest = {
        "format": FORMAT, "root": root, "written_at": now_utc(), "caterva": caterva_version(),
    }
    (target / MANIFEST).write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    for name, table in ((CLAIMS, claims_by_ref), (ROWS, rows_by_ref), (SNAPSHOTS, snapshots_by_ref)):
        lines = [json.dumps(to_dict(record), sort_keys=True, ensure_ascii=False) for record in table.values()]
        (target / name).write_text("".join(line + "\n" for line in lines), encoding="utf-8")
    for snapshot in snapshots_by_ref.values():
        path = target / BLOBS / (digest_hex(snapshot.id) + ".gz")
        path.write_bytes(gzip.compress(blobs[snapshot.id], mtime=0))
    return target


def _records(path: Path, reader, what: str) -> list:
    if not path.is_file():
        raise BundleUnreadable(f"{path} is missing")
    out = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            data = json.loads(line)
        except ValueError as exc:
            raise BundleUnreadable(f"{path}:{number} is not JSON: {exc}") from exc
        try:
            out.append(reader(data))
        except EvidenceRefused as exc:
            raise BundleUnreadable(f"{path}:{number}: {what} refused: {exc}") from exc
    return out


def read_bundle(directory: str | Path) -> Bundle:
    """Read a bundle, recomputing every record's id; BundleUnreadable when it is not one."""
    target = Path(directory)
    manifest_path = target / MANIFEST
    if not manifest_path.is_file():
        raise BundleUnreadable(f"{manifest_path} is missing: {target} is not a claims bundle")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise BundleUnreadable(f"{manifest_path} is not JSON: {exc}") from exc
    if not isinstance(manifest, dict) or manifest.get("format") != FORMAT:
        raise BundleUnreadable(
            f"{manifest_path} declares format {manifest.get('format') if isinstance(manifest, dict) else manifest!r}, "
            f"not {FORMAT}"
        )
    root = manifest.get("root")
    try:
        if ref_kind(str(root)) != "claim":
            raise BundleUnreadable(f"the manifest's root {root!r} is not a claim ref")
    except EvidenceRefused as exc:
        raise BundleUnreadable(f"the manifest's root {root!r} is not a claim ref") from exc
    bundle = Bundle(directory=target, manifest=manifest)
    bundle.claims = _by_ref(_records(target / CLAIMS, claim_from_dict, "claim"), "claim")
    bundle.rows = _by_ref(_records(target / ROWS, row_from_dict, "row"), "row")
    bundle.snapshots = _by_ref(_records(target / SNAPSHOTS, snapshot_from_dict, "snapshot"), "snapshot")
    if root not in bundle.claims:
        raise BundleUnreadable(f"the manifest's root {root} is not among the bundle's claims")
    return bundle


__all__ = [
    "BLOBS",
    "CLAIMS",
    "FORMAT",
    "MANIFEST",
    "ROWS",
    "SNAPSHOTS",
    "Bundle",
    "BundleUnreadable",
    "caterva_version",
    "read_bundle",
    "write_bundle",
]
