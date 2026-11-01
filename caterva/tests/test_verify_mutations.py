"""One change to the showcase bundle per test, and the check that catches it names the claim.

WHY THESE TESTS
---------------
ADR 0179 says a claim cannot be altered and keep its id, that a certificate
is a span in the bytes of the row it cites, and that a page may change
elsewhere and the derivation still re-apply. Those are claims about
`caterva verify`, and the only way to hold the checker to them is to damage
a bundle in one known place and read which check fails. A checker only ever
seen passing is indistinguishable from one that checks nothing (ADR 0015).

Each test copies the showcase bundle (caterva/evidence/showcase.py, built
once per test session with the network made impossible, by
evidence_showcase_offline.py), applies ONE mutation, and asserts that the
failing check names the claim it damaged. Where the mutation is a changed
derivation rather than a lying id -- the row swap, the stated unit factor,
the rewritten snapshot id, the certificates moved to another row -- the id
is recomputed with the producer's own `make_claim`, so that identity is not
the check that fires and the one under test is.

The plan's step 5 is the one mutation that must PASS: a byte changed in a
table row no claim cites -- a neighbour of the cited kcat row, in the same
table -- with the snapshot's id rewritten to the new bytes (and, as the
trivial case, a byte of the page's <title>, outside every row). The ids do
not survive that (a row's snapshot is one of its fields, and a claim's
inputs name the row), so what the test shows is that the same derivations
re-apply to the changed page under the recomputed ids and every check
passes: a page may change elsewhere and the derivation stands.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import re
from typing import TYPE_CHECKING

import pytest

from caterva.check import verify
from caterva.evidence.claims import RuleRef, make_row, to_dict
from caterva.evidence.rows import certificates_for, rows_from_page
from evidence_showcase_offline import copy_bundle, recomputed, records, showcase_built, write_records, zeros_gzip

if TYPE_CHECKING:
    from pathlib import Path

PAGE_HASH = "sha256:3a69b492abcd7253b301d7a002f60d52a971ba9352a3a2559ec5f12f5060ef91"


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    return showcase_built(tmp_path_factory)


@pytest.fixture
def bundle(built, tmp_path) -> Path:
    """A fresh copy of the showcase bundle to damage (the store is not copied)."""
    return copy_bundle(built[0], tmp_path)


# ---------------------------------------------------------------------------
# Reading and rewriting records
# ---------------------------------------------------------------------------

_records = records
_write = write_records
_recomputed = recomputed


def _claim_named(directory: Path, identifier: str) -> dict:
    return next(r for r in _records(directory / "claims.jsonl") if r["subject"].startswith(identifier + " = "))


def _save_claim(directory: Path, record: dict) -> None:
    """Write `record` back over the claim with the same id (the id left as it is: a lie, on purpose)."""
    claims = _records(directory / "claims.jsonl")
    _write(directory / "claims.jsonl", [record if r["id"] == record["id"] else r for r in claims])


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


def test_swapping_the_km_rows_input_for_the_kcat_row_fails_the_row_locator_and_the_certificate(bundle):
    """The value no longer matches, and the spans the claim kept are the Km
    row's, not the row it now cites."""
    km = _claim_named(bundle, "reaction_Km")
    kcat = _claim_named(bundle, "reaction_kcat")
    km["derivation"]["inputs"] = list(kcat["derivation"]["inputs"])
    new_ref = _replace_claim(bundle, km)
    failing = _failing(bundle)
    assert [(c.name, c.claim) for c in failing] == [("row locator", new_ref), ("certificate", new_ref)]
    assert "cites 6 mM but the row holds 40.1 1/s" in failing[0].detail
    assert "reaction_Km" in failing[0].detail
    assert failing[1].detail.startswith("reaction_Km: ")
    assert "does not hold the cited row brenda:2.7.1.1:kcat:Homo sapiens:D-glucose:739603:40.1:0" in failing[1].detail


# ---------------------------------------------------------------------------
# Certificates held to the cited row
# ---------------------------------------------------------------------------

#: Two human Km rows of the pinned page with the same value, 0.63 mM: one
#: for D-glucose (reference 702314) and one for ATP from the Km row's own
#: paper and conditions (reference 641068, "30°C, pH 7.5, wild-type").
GLUCOSE_063 = "brenda:2.7.1.1:km:Homo sapiens:D-glucose:702314:0.63:0"
ATP_063 = "brenda:2.7.1.1:km:Homo sapiens:ATP:641068:0.63:0"


def _two_same_value_rows(directory: Path):
    """The page and the two 0.63 mM rows, parsed by the producer and added to rows.jsonl."""
    page = _page(directory)
    parsed = rows_from_page(page.decode("utf-8"), ec="2.7.1.1", table="km", organism="Homo sapiens",
                            snapshot_ref="snapshot:" + PAGE_HASH)
    glucose = next(r for r in parsed if r.locator == GLUCOSE_063)
    atp = next(r for r in parsed if r.locator == ATP_063)
    _write(directory / "rows.jsonl", [*_records(directory / "rows.jsonl"), to_dict(glucose), to_dict(atp)])
    return page, glucose, atp


def _cite(directory: Path, row, certificates: list[dict]) -> str:
    """The Km claim made to cite `row` at its value with `certificates`, id recomputed; the new ref."""
    km = _claim_named(directory, "reaction_Km")
    km["value_text"] = row.value_text
    km["derivation"]["inputs"] = [row.ref]
    km["derivation"]["certificates"] = certificates
    return _replace_claim(directory, km)


def test_citing_a_same_value_row_with_its_own_spans_passes(bundle):
    """The premise of the next test: the row, its value and its spans are a good citation."""
    page, glucose, _ = _two_same_value_rows(bundle)
    _cite(bundle, glucose, to_dict(certificates_for(glucose, page)))
    assert verify.verify_bundle(bundle).ok


def test_citing_a_row_with_another_same_value_rows_spans_fails_the_certificate(bundle):
    """The review's case, on the recorded page: before the row tie this
    passed every check, because the value matched and every span read."""
    page, glucose, atp = _two_same_value_rows(bundle)
    new_ref = _cite(bundle, glucose, to_dict(certificates_for(atp, page)))
    failing = _failing(bundle)
    assert [(c.name, c.claim) for c in failing] == [("certificate", new_ref)]
    assert failing[0].detail.startswith("reaction_Km: 5 span(s) read as their text: '641068', '0.63'")
    assert f"which does not hold the cited row {GLUCOSE_063}" in failing[0].detail


#: Two kcat rows of one paper with the same value and conditions, 53.2 1/s
#: at "37°C, pH 7.4, wild-type enzyme" in Mus musculus (reference 674800):
#: one for ATP, one for D-glucose. Only the substrate tells them apart.
GLUCOSE_532 = "brenda:2.7.1.1:kcat:Mus musculus:D-glucose:674800:53.2:0"
ATP_532 = "brenda:2.7.1.1:kcat:Mus musculus:ATP:674800:53.2:0"


def _spans_in_own_row(page: bytes, row) -> list[dict]:
    """The row's five texts as whole cells of the table row the checker finds
    for it, found here by hand so the test does not lean on the producer's
    choice of table row (which is what is under test)."""
    fields = verify.RowRecord(
        id=row.id, snapshot=row.snapshot, parser={}, locator=row.locator, quantity=row.quantity,
        value_text=row.value_text, unit=row.unit, substrate=row.substrate, organism=row.organism,
        accession=row.accession, commentary=row.commentary, reference=row.reference,
    )
    start, end = verify.find_row_region(page, **verify.row_cells(fields))
    spans = []
    for text in (row.reference, row.value_text, row.commentary, row.substrate, row.organism):
        needle = b">" + text.encode("utf-8")
        at = page.find(needle, start, end)
        while at >= 0 and page[at + len(needle):at + len(needle) + 1] not in (b"\n", b"<"):
            at = page.find(needle, at + 1, end)
        assert at >= 0, f"{text!r} is not a whole cell of the row at [{start}, {end})"
        spans.append({"snapshot": row.snapshot, "span": [at + 1, at + len(needle)], "matched": text})
    return spans


def _two_rows_of_one_paper(directory: Path):
    """The page and the two 53.2 1/s rows, parsed by the producer and added to rows.jsonl."""
    page = _page(directory)
    parsed = rows_from_page(page.decode("utf-8"), ec="2.7.1.1", table="kcat", organism="Mus musculus",
                            snapshot_ref="snapshot:" + PAGE_HASH)
    glucose = next(r for r in parsed if r.locator == GLUCOSE_532)
    atp = next(r for r in parsed if r.locator == ATP_532)
    _write(directory / "rows.jsonl", [*_records(directory / "rows.jsonl"), to_dict(glucose), to_dict(atp)])
    return page, glucose, atp


def _cite_as_kcat(directory: Path, row, certificates: list[dict]) -> str:
    """The kcat claim made to cite `row` at its value with `certificates`, id recomputed; the new ref."""
    kcat = _claim_named(directory, "reaction_kcat")
    kcat["value_text"] = row.value_text
    kcat["derivation"]["inputs"] = [row.ref]
    kcat["derivation"]["certificates"] = certificates
    return _replace_claim(directory, kcat)


def test_citing_one_of_two_rows_of_one_paper_with_its_own_spans_passes(bundle):
    """The premise of the next test, and the row locator finds the D-glucose
    row's own table row, not the ATP row that shares its other three texts."""
    page, glucose, _ = _two_rows_of_one_paper(bundle)
    new_ref = _cite_as_kcat(bundle, glucose, _spans_in_own_row(page, glucose))
    report = verify.verify_bundle(bundle)
    assert report.ok, [c.detail for c in report.failed()]
    located = next(c for c in report.checks if c.name == "row locator" and c.claim == new_ref)
    assert f"row {GLUCOSE_532} found in bytes [2139765, 2140513)" in located.detail


def test_citing_a_row_with_the_spans_of_a_row_sharing_its_reference_value_and_commentary_fails(bundle):
    """Found reviewing the row tie: holding the spans' row to the reference,
    value and commentary passed this, a D-glucose claim certified by the ATP
    row's bytes, one span reading 'ATP'. The substrate is a cell of the row too."""
    page, glucose, atp = _two_rows_of_one_paper(bundle)
    new_ref = _cite_as_kcat(bundle, glucose, _spans_in_own_row(page, atp))
    failing = _failing(bundle)
    assert [(c.name, c.claim) for c in failing] == [("certificate", new_ref)]
    assert "'674800', '53.2', '37°C, pH 7.4, wild-type enzyme', 'ATP', 'Mus musculus'" in failing[0].detail
    assert (
        f"the spans lie in the table row at bytes [2076961, 2077702), which does not hold the cited row "
        f"{GLUCOSE_532} (reference '674800', value '53.2', commentary '37°C, pH 7.4, wild-type enzyme', "
        "substrate 'D-glucose', organism 'Mus musculus')"
    ) in failing[0].detail


def test_a_claim_whose_only_span_is_the_page_title_fails_the_certificate(bundle):
    page = _page(bundle)
    at = page.find(b"<title>") + len(b"<title>")
    km = _claim_named(bundle, "reaction_Km")
    km["derivation"]["certificates"] = [
        {"snapshot": "snapshot:" + PAGE_HASH, "span": [at, at + 4], "matched": page[at:at + 4].decode("utf-8")},
    ]
    new_ref = _replace_claim(bundle, km)
    failing = _failing(bundle)
    assert [(c.name, c.claim) for c in failing] == [("certificate", new_ref)]
    assert f"span [{at}, {at + 4})" in failing[0].detail and "lies outside every table row" in failing[0].detail


def test_spans_from_two_table_rows_fail_the_certificate(bundle):
    km = _claim_named(bundle, "reaction_Km")
    kcat = _claim_named(bundle, "reaction_kcat")
    km["derivation"]["certificates"].append(kcat["derivation"]["certificates"][0])
    new_ref = _replace_claim(bundle, km)
    failing = _failing(bundle)
    assert [(c.name, c.claim) for c in failing] == [("certificate", new_ref)]
    assert "the spans lie in 2 different table rows ([1980173, 1980928), [2129348, 2130166))" in failing[0].detail


def test_dropping_the_value_span_with_the_id_recomputed_fails_the_certificate(bundle):
    """Every span then lies in the cited row, and none of them says its value."""
    km = _claim_named(bundle, "reaction_Km")
    km["derivation"]["certificates"] = [c for c in km["derivation"]["certificates"] if c["matched"] != "6"]
    new_ref = _replace_claim(bundle, km)
    failing = _failing(bundle)
    assert [(c.name, c.claim) for c in failing] == [("certificate", new_ref)]
    assert "no span certifies the cited row's value '6'" in failing[0].detail


def test_a_cited_claim_with_no_span_at_all_fails_the_certificate(bundle):
    """The producer refuses to make one (a citation with no span is a label);
    a hand-edited bundle can still hold one, so its id is recomputed here by
    the checker's own definition and the root re-pointed."""
    km = _claim_named(bundle, "reaction_Km")
    old_id = km["id"]
    km["derivation"]["certificates"] = []
    _save_claim(bundle, km)
    km["id"] = verify.claim_id(verify.read_bundle_files(bundle).claims["claim:" + old_id])
    _write(bundle / "claims.jsonl", [km if r["id"] == old_id else r for r in _records(bundle / "claims.jsonl")])
    new_ref = _rebuild_claims(bundle, {"claim:" + old_id: "claim:" + km["id"]}, {})["claim:" + old_id]
    failing = _failing(bundle)
    assert [(c.name, c.claim) for c in failing] == [("certificate", new_ref)]
    assert failing[0].detail.startswith("reaction_Km: certifies no span; a cited claim's spans are its row's")


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


def _cited_regions(directory: Path, page: bytes) -> set[tuple[int, int]]:
    """The table rows any certificate of the bundle lies in."""
    starts = verify.row_regions(page)
    return {
        verify.region_of(c["span"][0], starts, len(page))
        for claim in _records(directory / "claims.jsonl")
        for c in claim["derivation"]["certificates"]
        if c["snapshot"] == "snapshot:" + PAGE_HASH
    }


_TABLE_GROUP = re.compile(rb'<div id="(tab\d+r\d+)')


def _in_a_neighbouring_row(directory: Path) -> int:
    """The last digit of "60.4" in the 60.4 1/s row of reference 703624: the
    alternative the kcat ordinals name, in the same table group as the cited
    40.1 1/s row (tab44r5 on the recorded page), and cited by nothing."""
    page = _page(directory)
    region = verify.find_row_region(page, reference="703624", value_text="60.4", commentary=None)
    assert region is not None
    assert region not in _cited_regions(directory, page)
    kcat = next(c for c in _claim_named(directory, "reaction_kcat")["derivation"]["certificates"] if c["matched"] == "40.1")
    cited = verify.region_of(kcat["span"][0], verify.row_regions(page), len(page))
    assert _TABLE_GROUP.match(page, region[0]).group(1) == _TABLE_GROUP.match(page, cited[0]).group(1)
    at = page.find(b">60.4\n", region[0], region[1]) + len(b">60.")
    assert region[0] < at < region[1] and page[at:at + 1] == b"4"
    return at


def _in_the_title(directory: Path) -> int:
    """A byte of the page's <title>, before the first table row: the trivial case."""
    page = _page(directory)
    at = page.find(b"<title>") + len(b"<title>")
    assert verify.region_of(at, verify.row_regions(page), len(page)) is None
    return at


@pytest.mark.parametrize("where", [_in_a_neighbouring_row, _in_the_title], ids=["a neighbouring row", "the title"])
def test_one_byte_in_an_uncited_part_of_the_page_with_the_id_rewritten_re_derives_and_every_check_passes(bundle, where):
    """The plan's step 5: a page may change elsewhere and the derivation
    stands. The ids do change (the snapshot id is a field of every row read
    from it), so what passes is the same derivation re-applied to the changed
    page under the recomputed ids."""
    at = where(bundle)
    page = bytearray(_page(bundle))
    page[at] = ord("5") if page[at] != ord("5") else ord("6")
    km_before = _km_ref(bundle)
    mapping = _rebind_snapshot(bundle, PAGE_HASH, bytes(page))
    assert mapping["snapshot:" + PAGE_HASH] != "snapshot:" + PAGE_HASH
    assert mapping[km_before] == _km_ref(bundle) != km_before
    report = verify.verify_bundle(bundle)
    assert report.ok
    assert report.failed() == []
    located = {c.claim for c in report.checks if c.name == "row locator" and c.status == "ok"}
    assert located == {_km_ref(bundle), "claim:" + _claim_named(bundle, "reaction_kcat")["id"]}


def test_a_gzip_bomb_in_place_of_the_page_fails_the_snapshot_bytes_naming_the_claims(bundle):
    """A shared bundle whose small blob inflates past MAX_PAGE_BYTES is
    refused as that snapshot's failure, read no further than the bound."""
    blob = bundle / "snapshots" / (PAGE_HASH[len("sha256:"):] + ".gz")
    zeros_gzip(blob, verify.MAX_PAGE_BYTES + 1)
    failing = _failing(bundle)
    snapshot = [c for c in failing if c.name == "snapshot bytes"]
    assert len(snapshot) == 1 and snapshot[0].detail.startswith(f"snapshot:{PAGE_HASH}: ")
    assert "inflates past 67,108,864 bytes (MAX_PAGE_BYTES)" in snapshot[0].detail
    assert f"reaction_Km ({_km_ref(bundle)})" in snapshot[0].detail and "reaction_kcat" in snapshot[0].detail
    assert {c.name for c in failing} == {"snapshot bytes", "row locator", "certificate"}


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
