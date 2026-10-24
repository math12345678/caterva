"""One change to the showcase bundle per test, and the check that catches it names the claim.

WHY THESE TESTS
---------------
ADR 0179 says a claim cannot be altered and keep its id, that a certificate
is a span in bytes that were kept, and that a page may change elsewhere
without touching a claim. Those are claims about `caterva verify`, and the
only way to hold the checker to them is to damage a bundle in one known
place and read which check fails. A checker only ever seen passing is
indistinguishable from one that checks nothing (ADR 0015).

Each test copies the showcase bundle (caterva/evidence/showcase.py, built
once per module with the network made impossible), applies ONE mutation,
and asserts that the failing check names the claim it damaged. Where the
mutation is a changed derivation rather than a lying id -- the row swap,
the stated unit factor, the rewritten snapshot id -- the id is recomputed
with the producer's own `make_claim`, so that identity is not the check
that fires and the one under test is.

The plan's step 5 is the one test that must PASS: a byte changed outside
every cited row, with the snapshot's id rewritten to the new bytes, leaves
every claim standing.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import shutil
from typing import TYPE_CHECKING

import httpx
import pytest

from caterva.check import verify
from caterva.evidence import showcase
from caterva.evidence.claims import Certificate, Derivation, RuleRef, make_claim, make_row, to_dict

if TYPE_CHECKING:
    from pathlib import Path

PAGE_HASH = "sha256:3a69b492abcd7253b301d7a002f60d52a971ba9352a3a2559ec5f12f5060ef91"


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    out = tmp_path_factory.mktemp("showcase")
    patch = pytest.MonkeyPatch()

    def no_network(self, request):
        raise httpx.ConnectError("network disabled in this test", request=request)

    patch.setattr(httpx.HTTPTransport, "handle_request", no_network)
    patch.delenv("CATERVA_BRENDA_RECORDED", raising=False)
    patch.delenv("CATERVA_HTTP_RECORDED", raising=False)
    try:
        root = showcase.showcase_bundle(out)
    finally:
        patch.undo()
    return out, root


@pytest.fixture
def bundle(built, tmp_path) -> Path:
    """A fresh copy of the showcase bundle to damage (the store is not copied)."""
    target = tmp_path / "bundle"
    shutil.copytree(built[0], target, ignore=shutil.ignore_patterns("store"))
    return target


# ---------------------------------------------------------------------------
# Reading and rewriting records
# ---------------------------------------------------------------------------

def _records(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write(path: Path, records: list[dict]) -> None:
    path.write_text("".join(json.dumps(r, sort_keys=True, ensure_ascii=False) + "\n" for r in records), encoding="utf-8")


def _claim_named(directory: Path, identifier: str) -> dict:
    return next(r for r in _records(directory / "claims.jsonl") if r["subject"].startswith(identifier + " = "))


def _save_claim(directory: Path, record: dict) -> None:
    """Write `record` back over the claim with the same id (the id left as it is: a lie, on purpose)."""
    claims = _records(directory / "claims.jsonl")
    _write(directory / "claims.jsonl", [record if r["id"] == record["id"] else r for r in claims])


def _recomputed(record: dict) -> dict:
    derivation = record["derivation"]
    claim = make_claim(
        record["kind"], record["subject"], record["value_text"], record["unit"], record["tolerance"],
        Derivation(
            RuleRef(**derivation["rule"]), inputs=tuple(derivation["inputs"]),
            certificates=tuple(Certificate(c["snapshot"], tuple(c["span"]), c["matched"]) for c in derivation["certificates"]),
            settings=dict(derivation["settings"]),
        ),
    )
    return to_dict(claim)


def _row_recomputed(record: dict) -> dict:
    fields = {k: v for k, v in record.items() if k not in ("id", "parser")}
    return to_dict(make_row(parser=RuleRef(**record["parser"]), **fields))


def _rebuild_claims(directory: Path, mapping: dict[str, str], replaced: dict[str, dict]) -> dict[str, str]:
    """Recompute every claim whose inputs or certificates changed, in dependency order.

    `mapping` is old ref -> new ref for rows and snapshots already rewritten;
    `replaced` is old claim ref -> its new record. Returns the full mapping,
    claims included, and rewrites claims.jsonl and the manifest's root.
    """
    claims = {"claim:" + r["id"]: r for r in _records(directory / "claims.jsonl")}
    done: dict[str, dict] = {}

    def rebuild(ref: str) -> str:
        if ref in mapping:
            return mapping[ref]
        record = replaced.get(ref, claims[ref])
        derivation = record["derivation"]
        new_inputs = [rebuild(i) if i.startswith("claim:") else mapping.get(i, i) for i in derivation["inputs"]]
        changed = ref in replaced or new_inputs != derivation["inputs"]
        derivation["inputs"] = new_inputs
        for certificate in derivation["certificates"]:
            new_snapshot = mapping.get(certificate["snapshot"], certificate["snapshot"])
            changed = changed or new_snapshot != certificate["snapshot"]
            certificate["snapshot"] = new_snapshot
        if changed:
            record = _recomputed(record)
        mapping[ref] = "claim:" + record["id"]
        done[ref] = record
        return mapping[ref]

    for ref in list(claims):
        rebuild(ref)
    _write(directory / "claims.jsonl", [done[ref] for ref in claims])
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    manifest["root"] = mapping[manifest["root"]]
    (directory / "manifest.json").write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return mapping


def _replace_claim(directory: Path, record: dict) -> str:
    """Put a recomputed record in place of the claim it was made from; the new ref."""
    old_ref = "claim:" + record["id"]
    rebuilt = _recomputed(record)
    mapping = _rebuild_claims(directory, {}, {old_ref: rebuilt})
    return mapping[old_ref]


def _page(directory: Path) -> bytes:
    return gzip.decompress((directory / "snapshots" / (PAGE_HASH[len("sha256:"):] + ".gz")).read_bytes())


def _write_page(directory: Path, snapshot_id: str, data: bytes) -> None:
    (directory / "snapshots" / (snapshot_id[len("sha256:"):] + ".gz")).write_bytes(gzip.compress(data, mtime=0))


def _rebind_snapshot(directory: Path, old_id: str, data: bytes) -> dict[str, str]:
    """Rewrite the snapshot's id to the hash of `data` everywhere: the blob,
    snapshots.jsonl, the rows read from it (ids recomputed), the claims that
    cite those rows or certify spans in it (ids recomputed), the root."""
    new_id = "sha256:" + hashlib.sha256(data).hexdigest()
    (directory / "snapshots" / (old_id[len("sha256:"):] + ".gz")).unlink()
    _write_page(directory, new_id, data)
    snapshots = _records(directory / "snapshots.jsonl")
    for snapshot in snapshots:
        if snapshot["id"] == old_id:
            snapshot["id"] = new_id
    _write(directory / "snapshots.jsonl", snapshots)
    mapping = {"snapshot:" + old_id: "snapshot:" + new_id}
    rows = []
    for row in _records(directory / "rows.jsonl"):
        if row["snapshot"] == "snapshot:" + old_id:
            before = "row:" + row["id"]
            row["snapshot"] = "snapshot:" + new_id
            row = _row_recomputed(row)
            mapping[before] = "row:" + row["id"]
        rows.append(row)
    _write(directory / "rows.jsonl", rows)
    return _rebuild_claims(directory, mapping, {})


def _km_ref(directory: Path) -> str:
    return "claim:" + _claim_named(directory, "reaction_Km")["id"]


def _failing(directory: Path) -> list[verify.Check]:
    report = verify.verify_bundle(directory)
    assert not report.ok
    return report.failed()


# ---------------------------------------------------------------------------
# The mutations
# ---------------------------------------------------------------------------

def test_the_untouched_copy_passes(bundle):
    """The premise every test below rests on."""
    assert verify.verify_bundle(bundle).ok


def test_swapping_the_km_rows_input_for_the_kcat_row_fails_the_row_locator(bundle):
    km = _claim_named(bundle, "reaction_Km")
    kcat = _claim_named(bundle, "reaction_kcat")
    km["derivation"]["inputs"] = list(kcat["derivation"]["inputs"])
    new_ref = _replace_claim(bundle, km)
    failing = _failing(bundle)
    assert [(c.name, c.claim) for c in failing] == [("row locator", new_ref)]
    assert "cites 6 mM but the row holds 40.1 1/s" in failing[0].detail
    assert "reaction_Km" in failing[0].detail


def test_flipping_the_unit_without_a_factor_fails_identity(bundle):
    km = _claim_named(bundle, "reaction_Km")
    km["unit"] = "uM"
    _save_claim(bundle, km)
    failing = _failing(bundle)
    identity = [c for c in failing if c.name == "identity"]
    assert [c.claim for c in identity] == [_km_ref(bundle)]
    assert "stored id does not recompute" in identity[0].detail and "reaction_Km" in identity[0].detail


def test_a_factor_with_a_wrong_value_fails_unit_arithmetic(bundle):
    km = _claim_named(bundle, "reaction_Km")
    km["unit"] = "uM"
    km["derivation"]["settings"]["unit_factor"] = "1000"
    # value_text stays "6": the row says 6 mM, and 6 mM × 1000 is not 6 µM.
    new_ref = _replace_claim(bundle, km)
    failing = _failing(bundle)
    assert [(c.name, c.claim) for c in failing] == [("unit arithmetic", new_ref)]
    assert "6 mM × 1000 is 6000, not the cited 6 uM" in failing[0].detail


def _edit_the_value_byte(bundle: Path) -> bytes:
    """The page with the Km row's value cell changed from 6 to 7, at the byte the certificate names."""
    km = _claim_named(bundle, "reaction_Km")
    certificate = next(c for c in km["derivation"]["certificates"] if c["matched"] == "6")
    start, end = certificate["span"]
    page = bytearray(_page(bundle))
    assert page[start:end] == b"6"
    page[start:end] = b"7"
    return bytes(page)


def test_one_byte_inside_the_cited_row_fails_the_snapshot_bytes(bundle):
    _write_page(bundle, PAGE_HASH, _edit_the_value_byte(bundle))
    failing = _failing(bundle)
    snapshot = [c for c in failing if c.name == "snapshot bytes"]
    assert len(snapshot) == 1 and snapshot[0].claim is None
    assert snapshot[0].detail.startswith(f"snapshot:{PAGE_HASH}:")
    assert "not the snapshot's id" in snapshot[0].detail
    assert f"reaction_Km ({_km_ref(bundle)})" in snapshot[0].detail


def test_one_byte_inside_the_cited_row_with_the_id_rewritten_fails_the_certificate_or_the_row_locator(bundle):
    mapping = _rebind_snapshot(bundle, PAGE_HASH, _edit_the_value_byte(bundle))
    km_ref = _km_ref(bundle)
    assert km_ref in mapping.values()
    report = verify.verify_bundle(bundle)
    assert all(c.ok for c in report.checks if c.name == "snapshot bytes")
    failing = report.failed()
    assert failing
    assert {c.name for c in failing} <= {"certificate", "row locator"}
    assert {c.claim for c in failing} == {km_ref}
    assert any("reads '7', not '6'" in c.detail for c in failing if c.name == "certificate")


def test_one_byte_outside_every_cited_row_with_the_id_rewritten_leaves_every_claim_standing(bundle):
    """The plan's step 5: a page may change elsewhere and the claim stands."""
    page = bytearray(_page(bundle))
    offset = 100
    assert verify.region_of(offset, verify.row_regions(bytes(page)), len(page)) is None
    page[offset] = ord("Z") if page[offset] != ord("Z") else ord("Y")
    mapping = _rebind_snapshot(bundle, PAGE_HASH, bytes(page))
    assert "snapshot:" + PAGE_HASH in mapping
    report = verify.verify_bundle(bundle)
    assert report.ok
    assert report.failed() == []
    assert any(c.name == "row locator" and c.claim == _km_ref(bundle) for c in report.checks)


def test_bumping_the_rule_version_without_recomputing_the_id_fails_identity(bundle):
    km = _claim_named(bundle, "reaction_Km")
    assert km["derivation"]["rule"]["rule_id"] == "select.resolver"
    km["derivation"]["rule"]["version"] = 2
    _save_claim(bundle, km)
    failing = _failing(bundle)
    assert [(c.name, c.claim) for c in failing] == [("identity", _km_ref(bundle))]
    assert "reaction_Km" in failing[0].detail


def test_dropping_a_certificate_fails_identity(bundle):
    km = _claim_named(bundle, "reaction_Km")
    km["derivation"]["certificates"].pop()
    _save_claim(bundle, km)
    failing = _failing(bundle)
    assert [(c.name, c.claim) for c in failing] == [("identity", _km_ref(bundle))]


def test_editing_the_tolerance_fails_identity(bundle):
    km = _claim_named(bundle, "reaction_Km")
    assert km["tolerance"] is None
    km["tolerance"] = "1e-9"
    _save_claim(bundle, km)
    failing = _failing(bundle)
    assert [(c.name, c.claim) for c in failing] == [("identity", _km_ref(bundle))]
    assert "reaction_Km" in failing[0].detail
