"""The evidence store and the bundle: records round-trip, closures export, lies are refused.

Also the capture: a Recorder pins every page fetch_brenda_html returns, on
the recorded path and the live one, through the PAGE_OBSERVERS hook in
Tests/brenda_client.py; capture_reference pins a literature page through
http_retry.retry_get and says when a recording served it.

Offline: the live path is exercised with retry_get replaced by a stub, and
the recorded path with CATERVA_BRENDA_RECORDED set by this test to the
repository's recordings (the one place outside test configuration that may
name it is nowhere: Tests/test_recorded_env_is_test_only.py).
"""
from __future__ import annotations

import gzip
import hashlib
import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

from caterva.checkout import literature_module
from caterva.evidence import bundle as bundle_module
from caterva.evidence.bundle import Bundle, BundleUnreadable, read_bundle, write_bundle
from caterva.evidence.capture import Recorder, capture_reference, client_modules, enzyme_page_url
from caterva.evidence.claims import (
    COMPILE_MODEL,
    PARSE_BRENDA_TABLE,
    SELECT_RESOLVER,
    Certificate,
    Derivation,
    EvidenceRefused,
    make_claim,
    make_row,
)
from caterva.evidence.references import reference_url
from caterva.evidence.store import EvidenceStore, StoreUnreadable

REPO = Path(__file__).resolve().parents[2]
RECORDED = REPO / "Tests" / "fixtures" / "recorded"
HEXOKINASE_SHA256 = "3a69b492abcd7253b301d7a002f60d52a971ba9352a3a2559ec5f12f5060ef91"

PAGE = (
    b'<div id="tab12r4sr0" class="row rgrey2"><div class="cell"><span>6\n</span></div>'
    b'<div class="cell"><span>D-glucose\n</span></div><div class="cell"><span>Homo sapiens\n</span></div>'
    b'<div class="cell"><span>wild-type\n</span></div><div class="cell"><span><a href="x">641068</a>\n</span></div></div>'
)
REFERENCE_PAGE = b'<html><span class="reference__title">A title</span></html>'


def filled(path: Path):
    """A store holding one page, one row, one cited claim and one computed root."""
    store = EvidenceStore(path)
    snap = store.put_snapshot(PAGE, source="brenda_enzyme", locator=enzyme_page_url("2.7.1.1"),
                              retrieved_at="2026-10-17T05:00:00Z", licence="CC BY 4.0")
    row = store.put_row(make_row(
        snapshot=snap.ref, parser=PARSE_BRENDA_TABLE,
        locator="brenda:2.7.1.1:km:Homo sapiens:D-glucose:641068:6:0", quantity="km", value_text="6",
        unit="mM", substrate="D-glucose", organism="Homo sapiens", commentary="wild-type", reference="641068",
    ))
    at = PAGE.find(b"641068")
    km = store.put_claim(make_claim(
        "cited", "reaction_Km = Km(2.7.1.1, D-glucose, Homo sapiens)", "6", "mM", None,
        Derivation(SELECT_RESOLVER, (row.ref,), (Certificate(snap.ref, (at, at + 6), "641068"),)),
    ))
    root = store.put_claim(make_claim(
        "computed", "model", None, None, None,
        Derivation(COMPILE_MODEL, (km.ref, "ir:sha256:" + hashlib.sha256(b"m").hexdigest()),
                   settings={"ir": "sha256:" + hashlib.sha256(b"m").hexdigest()}),
    ))
    return store, snap, row, km, root


def _write_row_without_snapshot(tmp_path, row):
    """A root with no certificates and no row inputs, plus a row whose snapshot is absent."""
    lone = make_claim("computed", "model", None, None, None,
                      Derivation(COMPILE_MODEL, ("ir:sha256:" + hashlib.sha256(b"m").hexdigest(),)))
    write_bundle(tmp_path / "y", root=lone.ref, claims=[lone], rows=[row], snapshots=[], blobs={})


class TestStore:
    def test_a_snapshot_round_trips_and_is_identified_by_its_bytes(self, tmp_path):
        store = EvidenceStore(tmp_path / "s")
        first = store.put_snapshot(PAGE, source="brenda_enzyme", locator="u", retrieved_at="2026-10-17T05:00:00Z",
                                   licence="CC BY 4.0", served_from="a.gz")
        again = store.put_snapshot(PAGE, source="brenda_enzyme", locator="u", retrieved_at="2026-10-18T05:00:00Z",
                                   licence="CC BY 4.0")
        assert again == first, "the record of the first retrieval stands"
        assert store.snapshot_bytes(first.ref) == PAGE
        assert store.get(first.ref) == first
        assert store.snapshots() == [first]
        assert (tmp_path / "s" / "blobs" / (first.id[len("sha256:"):] + ".gz")).is_file()
        assert (tmp_path / "s" / "index.sqlite").is_file()

    def test_rows_and_claims_round_trip_and_need_their_inputs(self, tmp_path):
        store, _snap, row, km, root = filled(tmp_path / "s")
        assert store.get(row.ref) == row
        assert store.get(km.ref) == km
        assert store.get(root.ref) == root
        assert store.has(root.ref) and not store.has("claim:" + "sha256:" + "0" * 64)
        with pytest.raises(KeyError):
            store.get("row:sha256:" + "0" * 64)
        other = EvidenceStore(tmp_path / "empty")
        with pytest.raises(EvidenceRefused, match="does not hold"):
            other.put_row(row)
        with pytest.raises(EvidenceRefused, match="does not hold"):
            other.put_claim(km)
        assert store.claims(kind="cited") == [km]

    def test_dependents_is_the_transitive_reverse_index(self, tmp_path):
        store, snap, row, km, root = filled(tmp_path / "s")
        assert store.dependents(snap.ref) == [row.ref, km.ref, root.ref]
        assert store.dependents(row.ref) == [km.ref, root.ref]
        assert store.dependents(root.ref) == []
        assert store.inputs_of(root.ref) == [km.ref]
        # Depth first, the last input pushed is the first visited: the km
        # claim's edges are its row, then its certificate's page, so the page
        # comes before the row. The order is the contract because the bundle
        # writes its records in it, which is what makes an export the same
        # bytes each time (TestBundle).
        assert store.closure(root.ref) == [root.ref, km.ref, snap.ref, row.ref]

    def test_export_writes_the_closure_and_the_reference_page_for_the_cited_row(self, tmp_path):
        store, snap, row, km, root = filled(tmp_path / "s")
        paper = store.put_snapshot(REFERENCE_PAGE, source="brenda_reference",
                                   locator=reference_url("2.7.1.1", "641068"),
                                   retrieved_at="2026-10-17T05:00:00Z", licence="CC BY 4.0")
        unrelated = store.put_snapshot(b"other", source="brenda_reference",
                                       locator=reference_url("2.7.1.1", "739603"),
                                       retrieved_at="2026-10-17T05:00:00Z", licence="CC BY 4.0")
        out = store.export_bundle(root.ref, tmp_path / "bundle")
        read = read_bundle(out)
        assert read.root == root.ref
        assert set(read.claims) == {km.ref, root.ref}
        assert set(read.rows) == {row.ref}
        assert set(read.snapshots) == {snap.ref, paper.ref}, "the cited paper's page travels; an uncited one does not"
        assert unrelated.ref not in read.snapshots
        assert read.snapshot_bytes(snap.ref) == PAGE
        assert read.snapshot_bytes(paper.ref) == REFERENCE_PAGE
        assert read.get(km.ref) == km
        with pytest.raises(EvidenceRefused, match="root is a claim"):
            store.export_bundle(row.ref, tmp_path / "no")


class TestAnIndexThatIsNotAStores:
    """sqlite3 connects to any file and fails at the first statement, so a
    store opened on a file that is not its index raised a bare
    sqlite3.DatabaseError, which `caterva why --store` printed as a
    traceback. It is StoreUnreadable, naming the file; and a store opened
    read only writes nothing, so asking cannot turn another program's
    database into a store."""

    def test_a_text_file_named_index_sqlite_is_unreadable_in_either_mode(self, tmp_path):
        (tmp_path / "index.sqlite").write_text("not a database", encoding="utf-8")
        for read_only in (False, True):
            with pytest.raises(StoreUnreadable, match=r"index\.sqlite is not an evidence store's index"):
                EvidenceStore(tmp_path, read_only=read_only)
        assert issubclass(StoreUnreadable, EvidenceRefused)
        assert (tmp_path / "index.sqlite").read_text(encoding="utf-8") == "not a database"

    def test_read_only_needs_an_index_and_creates_nothing(self, tmp_path):
        with pytest.raises(StoreUnreadable, match=r"holds no index\.sqlite"):
            EvidenceStore(tmp_path / "nowhere", read_only=True)
        assert not (tmp_path / "nowhere").exists()

    def test_read_only_on_another_programs_database_leaves_it_as_it_was(self, tmp_path):
        other = sqlite3.connect(str(tmp_path / "index.sqlite"))
        other.execute("CREATE TABLE notes (text TEXT)")
        other.commit()
        other.close()
        before = (tmp_path / "index.sqlite").read_bytes()
        with pytest.raises(StoreUnreadable, match="without the snapshots, rows, claims, edges table"):
            EvidenceStore(tmp_path, read_only=True)
        assert (tmp_path / "index.sqlite").read_bytes() == before
        assert not (tmp_path / "blobs").exists()

    def test_read_only_reads_every_record_and_refuses_to_write(self, tmp_path):
        store, snap, row, km, root = filled(tmp_path / "s")
        store.close()
        before = (tmp_path / "s" / "index.sqlite").read_bytes()
        with EvidenceStore(tmp_path / "s", read_only=True) as reader:
            assert reader.get(root.ref) == root and reader.get(km.ref) == km and reader.get(row.ref) == row
            assert reader.snapshot_bytes(snap.ref) == PAGE
            assert reader.closure(root.ref) == [root.ref, km.ref, snap.ref, row.ref]
            with pytest.raises(EvidenceRefused, match="opened read only"):
                reader.put_snapshot(b"new bytes", source="brenda_enzyme", locator="u",
                                    retrieved_at="2026-10-17T05:00:00Z", licence="CC BY 4.0")
            with pytest.raises(EvidenceRefused, match="opened read only"):
                reader.put_claim(km)
        assert (tmp_path / "s" / "index.sqlite").read_bytes() == before
        assert sorted(p.name for p in (tmp_path / "s" / "blobs").iterdir()) == [snap.id[len("sha256:"):] + ".gz"]

    def test_a_record_that_is_not_json_is_unreadable_and_named(self, tmp_path):
        store, _snap, _row, km, _root = filled(tmp_path / "s")
        with store._db:  # noqa: SLF001 - the damage a hand edit or a cut-off write leaves
            store._db.execute("UPDATE claims SET json = ? WHERE id = ?", ("{cut off", km.id))  # noqa: SLF001
        with pytest.raises(StoreUnreadable, match=f"the claim record {km.id} in the store's index is not JSON"):
            store.get(km.ref)
        with pytest.raises(StoreUnreadable, match="is not JSON"):
            store.claims()

    def test_a_blob_that_is_not_its_snapshots_bytes_is_unreadable_and_named(self, tmp_path):
        """A bundle holds each blob to its id; the store handed back whatever
        the file held: other bytes as the snapshot's, or a gzip error."""
        store, snap, _row, _km, root = filled(tmp_path / "s")
        blob = tmp_path / "s" / "blobs" / (snap.id[len("sha256:"):] + ".gz")
        blob.write_bytes(gzip.compress(PAGE.replace(b"641068", b"641067"), mtime=0))
        with pytest.raises(StoreUnreadable, match=f"does not digest to {snap.ref}"):
            store.snapshot_bytes(snap.ref)
        with pytest.raises(StoreUnreadable, match="does not digest"):
            store.export_bundle(root.ref, tmp_path / "b")
        whole = gzip.compress(PAGE, mtime=0)
        # Not gzip (BadGzipFile), cut off (EOFError), a broken deflate block (zlib.error).
        for damaged in (b"not gzip at all", whole[:-12], whole[:10] + b"\xff" * 6 + whole[16:]):
            blob.write_bytes(damaged)
            with pytest.raises(StoreUnreadable, match=f"{blob.name} is not a gzip stream"):
                store.snapshot_bytes(snap.ref)
        blob.write_bytes(gzip.compress(PAGE, mtime=0))
        assert store.snapshot_bytes(snap.ref) == PAGE

    def test_a_blob_that_inflates_past_the_bound_is_refused_not_read_whole(self, tmp_path, monkeypatch):
        store, snap, _row, _km, root = filled(tmp_path / "s")
        bundle_dir = store.export_bundle(root.ref, tmp_path / "b")
        monkeypatch.setattr(bundle_module, "MAX_PAGE_BYTES", len(PAGE) - 1)
        blob = tmp_path / "s" / "blobs" / (snap.id[len("sha256:"):] + ".gz")
        with pytest.raises(StoreUnreadable, match=f"{blob.name}: it inflates past {len(PAGE) - 1} bytes"):
            store.snapshot_bytes(snap.ref)
        with pytest.raises(BundleUnreadable, match=f"it inflates past {len(PAGE) - 1} bytes"):
            read_bundle(bundle_dir).snapshot_bytes(snap.ref)
        monkeypatch.setattr(bundle_module, "MAX_PAGE_BYTES", len(PAGE))
        assert store.snapshot_bytes(snap.ref) == PAGE
        assert read_bundle(bundle_dir).snapshot_bytes(snap.ref) == PAGE


class TestBundle:
    def test_the_files_are_the_documented_format(self, tmp_path):
        store, snap, _row, _km, root = filled(tmp_path / "s")
        out = store.export_bundle(root.ref, tmp_path / "b")
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["format"] == "caterva-claims/1"
        assert manifest["root"] == root.ref
        assert manifest["written_at"].endswith("Z")
        assert manifest["caterva"] == bundle_module.caterva_version()
        for name in ("claims.jsonl", "rows.jsonl", "snapshots.jsonl"):
            lines = (out / name).read_text(encoding="utf-8").splitlines()
            assert all(json.loads(line)["id"].startswith("sha256:") for line in lines)
        blob = out / "snapshots" / (snap.id[len("sha256:"):] + ".gz")
        assert gzip.decompress(blob.read_bytes()) == PAGE
        assert hashlib.sha256(gzip.decompress(blob.read_bytes())).hexdigest() == snap.id[len("sha256:"):]

    def test_writing_the_same_blob_twice_gives_the_same_bytes(self, tmp_path):
        store, snap, _row, _km, root = filled(tmp_path / "s")
        a = store.export_bundle(root.ref, tmp_path / "a")
        b = store.export_bundle(root.ref, tmp_path / "b")
        name = snap.id[len("sha256:"):] + ".gz"
        assert (a / "snapshots" / name).read_bytes() == (b / "snapshots" / name).read_bytes()
        assert (a / "claims.jsonl").read_bytes() == (b / "claims.jsonl").read_bytes()

    def test_a_bundle_that_is_not_closed_is_not_written(self, tmp_path):
        _store, snap, row, km, root = filled(tmp_path / "s")
        blobs = {snap.id: PAGE}
        with pytest.raises(EvidenceRefused, match="not among the claims"):
            write_bundle(tmp_path / "x", root=km.ref, claims=[root], rows=[row], snapshots=[snap], blobs=blobs)
        with pytest.raises(EvidenceRefused, match="not in the bundle"):
            write_bundle(tmp_path / "x", root=root.ref, claims=[root], rows=[row], snapshots=[snap], blobs=blobs)
        with pytest.raises(EvidenceRefused, match="cites row"):
            write_bundle(tmp_path / "x", root=root.ref, claims=[root, km], rows=[], snapshots=[snap], blobs=blobs)
        with pytest.raises(EvidenceRefused, match=r"certifies a span in .* which is not in the bundle"):
            write_bundle(tmp_path / "x", root=root.ref, claims=[root, km], rows=[row], snapshots=[], blobs=blobs)
        with pytest.raises(EvidenceRefused, match="was read from"):
            _write_row_without_snapshot(tmp_path, row)
        with pytest.raises(EvidenceRefused, match="no bytes"):
            write_bundle(tmp_path / "x", root=root.ref, claims=[root, km], rows=[row], snapshots=[snap], blobs={})
        with pytest.raises(EvidenceRefused, match="not to its id"):
            write_bundle(tmp_path / "x", root=root.ref, claims=[root, km], rows=[row], snapshots=[snap],
                         blobs={snap.id: b"other bytes"})
        assert not (tmp_path / "x").exists()

    def test_a_directory_that_is_not_a_bundle_is_unreadable_not_failed(self, tmp_path):
        with pytest.raises(BundleUnreadable, match="not a claims bundle"):
            read_bundle(tmp_path)
        (tmp_path / "manifest.json").write_text('{"format": "something-else/9", "root": "x"}', encoding="utf-8")
        with pytest.raises(BundleUnreadable, match="declares format"):
            read_bundle(tmp_path)
        (tmp_path / "manifest.json").write_text("{not json", encoding="utf-8")
        with pytest.raises(BundleUnreadable, match="not JSON"):
            read_bundle(tmp_path)
        assert issubclass(BundleUnreadable, EvidenceRefused)

    def test_a_tampered_record_or_blob_is_refused_on_reading(self, tmp_path):
        store, snap, _row, _km, root = filled(tmp_path / "s")
        out = store.export_bundle(root.ref, tmp_path / "b")
        claims_file = out / "claims.jsonl"
        original = claims_file.read_text(encoding="utf-8")
        claims_file.write_text(original.replace('"value_text": "6"', '"value_text": "60"'), encoding="utf-8")
        with pytest.raises(BundleUnreadable, match="not the digest"):
            read_bundle(out)
        claims_file.write_text(original, encoding="utf-8")
        blob = out / "snapshots" / (snap.id[len("sha256:"):] + ".gz")
        blob.write_bytes(gzip.compress(PAGE.replace(b"641068", b"641067"), mtime=0))
        read = read_bundle(out)
        with pytest.raises(BundleUnreadable, match="does not digest"):
            read.snapshot_bytes(snap.ref)
        blob.unlink()
        with pytest.raises(BundleUnreadable, match="missing"):
            read.snapshot_bytes(snap.ref)

    def test_a_root_that_is_not_among_the_claims_is_unreadable(self, tmp_path):
        store, _snap, row, _km, root = filled(tmp_path / "s")
        out = store.export_bundle(root.ref, tmp_path / "b")
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        manifest["root"] = "claim:sha256:" + "0" * 64
        (out / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        with pytest.raises(BundleUnreadable, match="not among the bundle's claims"):
            read_bundle(out)
        manifest["root"] = row.ref
        (out / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        with pytest.raises(BundleUnreadable, match="not a claim ref"):
            read_bundle(out)

    def test_get_refuses_a_ref_the_bundle_does_not_hold(self, tmp_path):
        store, _snap, _row, _km, root = filled(tmp_path / "s")
        read = read_bundle(store.export_bundle(root.ref, tmp_path / "b"))
        assert isinstance(read, Bundle)
        with pytest.raises(KeyError):
            read.get("claim:sha256:" + "0" * 64)


# ---------------------------------------------------------------------------
# Capture
# ---------------------------------------------------------------------------

class TestRecorder:
    def test_the_recorded_path_is_pinned_with_the_recordings_path(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CATERVA_BRENDA_RECORDED", str(RECORDED))
        client = literature_module("brenda_client")
        store = EvidenceStore(tmp_path / "s")
        with Recorder(store) as recorder:
            copies = client_modules()
            assert client in copies
            assert all(recorder._observe in copy.PAGE_OBSERVERS for copy in copies)  # noqa: SLF001
            html = client.fetch_brenda_html("2.7.1.1")
        assert all(recorder._observe not in copy.PAGE_OBSERVERS for copy in copies)  # noqa: SLF001
        assert "2.7.1.1" in recorder.snapshots
        snap = recorder.snapshot_for("2.7.1.1")
        assert snap.id == "sha256:" + HEXOKINASE_SHA256
        assert snap.source == "brenda_enzyme"
        assert snap.locator == "https://www.brenda-enzymes.org/enzyme.php?ecno=2.7.1.1"
        assert snap.served_from == str(RECORDED / "brenda_2.7.1.1.html.gz")
        assert snap.licence == "CC BY 4.0"
        assert store.snapshot_bytes(snap.ref) == html.encode("utf-8")
        assert recorder._observe not in client.PAGE_OBSERVERS, "unregistered on exit"  # noqa: SLF001
        assert recorder.snapshot_for("1.1.1.27") is None

    def test_the_live_path_is_pinned_with_no_served_from(self, tmp_path, monkeypatch):
        monkeypatch.delenv("CATERVA_BRENDA_RECORDED", raising=False)
        client = literature_module("brenda_client")
        asked = []

        def fake_get(url, **kwargs):
            asked.append((url, kwargs.get("params")))
            return SimpleNamespace(text="<html>live page</html>", raise_for_status=lambda: None)

        monkeypatch.setattr(client, "retry_get", fake_get)
        store = EvidenceStore(tmp_path / "s")
        with Recorder(store) as recorder:
            assert client.fetch_brenda_html("9.9.9.9") == "<html>live page</html>"
        assert asked == [(client.BRENDA_ENZYME_URL, {"ecno": "9.9.9.9"})]
        snap = recorder.snapshot_for("9.9.9.9")
        assert snap.served_from is None
        assert snap.locator == "https://www.brenda-enzymes.org/enzyme.php?ecno=9.9.9.9"
        assert store.snapshot_bytes(snap.ref) == b"<html>live page</html>"
        assert recorder._observe not in client.PAGE_OBSERVERS  # noqa: SLF001

    def test_outside_the_block_nothing_is_observed(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CATERVA_BRENDA_RECORDED", str(RECORDED))
        client = literature_module("brenda_client")
        store = EvidenceStore(tmp_path / "s")
        recorder = Recorder(store)
        client.fetch_brenda_html("2.7.1.1")
        assert recorder.snapshots == {}
        assert store.snapshots() == []


class TestCaptureReference:
    def test_a_reference_page_is_fetched_through_retry_get_and_stored(self, tmp_path, monkeypatch):
        http_retry = literature_module("http_retry")
        monkeypatch.delenv(http_retry.RECORDED_ENV, raising=False)
        asked = []

        def fake_get(url, **kwargs):
            asked.append((url, kwargs["params"]))
            return SimpleNamespace(content=REFERENCE_PAGE, raise_for_status=lambda: None)

        monkeypatch.setattr(http_retry, "retry_get", fake_get)
        store = EvidenceStore(tmp_path / "s")
        snap = capture_reference("2.7.1.1", "641068", store)
        assert asked == [("https://www.brenda-enzymes.org/literature.php", {"e": "2.7.1.1", "r": "641068"})]
        assert snap.source == "brenda_reference"
        assert snap.locator == "https://www.brenda-enzymes.org/literature.php?e=2.7.1.1&r=641068"
        assert snap.served_from is None
        assert store.snapshot_bytes(snap.ref) == REFERENCE_PAGE

    def test_a_replayed_reference_page_says_which_recording_served_it(self, tmp_path, monkeypatch):
        import httpx

        http_retry = literature_module("http_retry")
        http_retry.clear_memo()
        url = "https://www.brenda-enzymes.org/literature.php"
        kwargs = {"params": {"e": "2.7.1.1", "r": "641068"}}
        key = http_retry.replay_key(url, kwargs)
        monkeypatch.setenv(http_retry.RECORD_ENV, str(tmp_path / "rec"))
        response = httpx.Response(200, headers={"content-type": "text/html"}, content=REFERENCE_PAGE,
                                  request=httpx.Request("GET", url))
        http_retry._record(key, response)  # noqa: SLF001
        monkeypatch.delenv(http_retry.RECORD_ENV)
        monkeypatch.setenv(http_retry.RECORDED_ENV, str(tmp_path / "rec"))

        def no_network(self, request):
            raise httpx.ConnectError("network disabled in this test", request=request)

        monkeypatch.setattr(httpx.HTTPTransport, "handle_request", no_network)
        try:
            store = EvidenceStore(tmp_path / "s")
            snap = capture_reference("2.7.1.1", "641068", store)
        finally:
            http_retry.clear_memo()
        assert snap.served_from == str(tmp_path / "rec" / http_retry.recording_name(key))
        assert store.snapshot_bytes(snap.ref) == REFERENCE_PAGE

    def test_an_error_answer_is_not_stored(self, tmp_path, monkeypatch):
        http_retry = literature_module("http_retry")
        monkeypatch.delenv(http_retry.RECORDED_ENV, raising=False)

        def failing():
            raise RuntimeError("500 from BRENDA")

        monkeypatch.setattr(http_retry, "retry_get",
                            lambda url, **kwargs: SimpleNamespace(content=b"", raise_for_status=failing))
        store = EvidenceStore(tmp_path / "s")
        with pytest.raises(RuntimeError, match="500"):
            capture_reference("2.7.1.1", "641068", store)
        assert store.snapshots() == []
