"""caterva/check/verify.py and `caterva verify`: the showcase bundle re-checks, and the checker's own definitions hold.

WHY THESE TESTS
---------------
The checker shares no code with the producer (ADR 0179), so the one thing
that must be proved first is that the two implementations agree on a bundle
nobody has touched: every row id and claim id the producer wrote recomputes
under the checker's own canonical JSON, every certificate reads, every cited
row is found within one table row. Then each definition the checker repeats
from the spec is pinned on its own: canonical bytes, dominance order
semantics, decimal tolerance, the row search. The mutations that must FAIL
are in `test_verify_mutations.py`.

The bundle is built once per module with every network send made
impossible, as `test_evidence_showcase.py` builds it.
"""
from __future__ import annotations

import io
import json
import shutil
import subprocess
import sys
from contextlib import redirect_stderr, redirect_stdout
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from caterva.check import verify
from caterva.check.__main__ import main
from caterva.evidence import showcase
from caterva.evidence.claims import Certificate, Derivation, RuleRef, make_claim, to_dict

REPO_ROOT = Path(__file__).resolve().parents[2]


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


def _run(args):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        try:
            code = main(args)
        except SystemExit as exc:  # argparse
            code = exc.code
    return code, out.getvalue(), err.getvalue()


def _records(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write(path: Path, records: list[dict]) -> None:
    path.write_text("".join(json.dumps(r, sort_keys=True, ensure_ascii=False) + "\n" for r in records), encoding="utf-8")


def _claim_named(records: list[dict], identifier: str) -> dict:
    return next(r for r in records if r["subject"].startswith(identifier + " = "))


def _recomputed(record: dict) -> dict:
    """The record with its id recomputed by the PRODUCER, so a test can state
    a changed derivation and leave identity out of what it tests."""
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


def _replace_claim(directory: Path, old_ref: str, record: dict) -> str:
    """Put `record` in place of the claim `old_ref`, re-pointing every claim
    that depended on it (ids recomputed, in dependency order) and the
    manifest root; the new ref."""
    claims = {"claim:" + r["id"]: r for r in _records(directory / "claims.jsonl")}
    mapping: dict[str, str] = {}
    done: dict[str, dict] = {}

    def rebuild(ref: str) -> str:
        if ref in mapping:
            return mapping[ref]
        current = record if ref == old_ref else claims[ref]
        inputs = current["derivation"]["inputs"]
        new_inputs = [rebuild(i) if i.startswith("claim:") else i for i in inputs]
        if ref == old_ref or new_inputs != inputs:
            current["derivation"]["inputs"] = new_inputs
            current = _recomputed(current)
        mapping[ref] = "claim:" + current["id"]
        done[ref] = current
        return mapping[ref]

    for ref in list(claims):
        rebuild(ref)
    _write(directory / "claims.jsonl", [done[ref] for ref in claims])
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    manifest["root"] = mapping[manifest["root"]]
    (directory / "manifest.json").write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return mapping[old_ref]


def _copy(built, tmp_path: Path) -> Path:
    target = tmp_path / "bundle"
    shutil.copytree(built[0], target, ignore=shutil.ignore_patterns("store"))
    return target


# ---------------------------------------------------------------------------
# The untouched bundle
# ---------------------------------------------------------------------------

class TestTheShowcaseBundle:
    def test_every_check_passes(self, built):
        report = verify.verify_bundle(built[0])
        assert report.ok
        assert report.failed() == []
        names = {c.name for c in report.checks}
        assert names == {
            "snapshot bytes", "identity", "row locator", "certificate", "dominance",
            "inputs", "root", "not checked",
        }

    def test_the_producers_ids_recompute_under_the_checkers_canonical_json(self, built):
        """The point of a second implementation: it agrees on an untouched bundle."""
        files = verify.read_bundle_files(built[0])
        assert len(files.claims) == 4 and len(files.rows) == 2
        for ref, claim in files.claims.items():
            assert verify.claim_id(claim) == claim.id, ref
        for ref, row in files.rows.items():
            assert verify.row_id(row) == row.id, ref

    def test_each_cited_claim_is_found_within_one_table_row(self, built):
        report = verify.verify_bundle(built[0])
        located = [c for c in report.checks if c.name == "row locator"]
        assert len(located) == 2
        for check in located:
            assert check.ok
            assert "found in bytes [" in check.detail
            assert "is the row's" in check.detail

    def test_the_certificates_read_as_their_text(self, built):
        report = verify.verify_bundle(built[0])
        certified = [c for c in report.checks if c.name == "certificate"]
        assert len(certified) == 2
        assert all(c.ok for c in certified)
        assert any("'641068', '6', '30°C, pH 7.5, wild-type'" in c.detail for c in certified)

    def test_dominance_ran_because_the_ordinals_were_carried(self, built):
        report = verify.verify_bundle(built[0])
        dominance = [c for c in report.checks if c.name == "dominance"]
        assert len(dominance) == 2
        assert all(c.ok and "not strictly dominated" in c.detail for c in dominance)

    def test_the_root_and_the_model_inputs(self, built):
        out, root = built
        report = verify.verify_bundle(out)
        by_name = {(c.name, c.claim): c for c in report.checks}
        assert by_name[("root", root)].ok
        assert by_name[("inputs", root)].ok and "4 input(s)" in by_name[("inputs", root)].detail

    def test_what_cannot_be_checked_is_listed(self, built):
        report = verify.verify_bundle(built[0])
        skipped = [c.detail for c in report.checks if c.name == "not checked"]
        assert len(skipped) == 2
        assert skipped[0].startswith("Antimony regeneration:")
        assert skipped[1].startswith("ODE replay:")
        assert all(c.ok for c in report.checks if c.name == "not checked")

    def test_snapshot_checks_name_the_bytes_and_the_date(self, built):
        report = verify.verify_bundle(built[0])
        snapshots = [c for c in report.checks if c.name == "snapshot bytes"]
        assert len(snapshots) == 3
        assert all(c.ok and c.claim is None for c in snapshots)
        assert any("3,725,554 bytes, brenda_enzyme, retrieved 2026-09-28" in c.detail for c in snapshots)


# ---------------------------------------------------------------------------
# The definitions the checker repeats
# ---------------------------------------------------------------------------

class TestCanonicalJson:
    def test_the_definition(self):
        assert verify.canonical_bytes({"b": [1, "é", None, True], "a": {"z": "1", "y": 2}}) == (
            '{"a":{"y":2,"z":"1"},"b":[1,"é",null,true]}'.encode()
        )

    def test_floats_are_refused_with_the_path(self):
        with pytest.raises(TypeError) as caught:
            verify.canonical_bytes({"fields": {"value": 6.0}})
        assert "$.fields.value" in str(caught.value)

    def test_a_digest_is_sha256_with_the_prefix(self):
        assert verify.digest(b"michaelis_menten") == (
            "sha256:b7722cc372b5ce0cf919dc6f8b304d392f6a29bc2e12232be1161687f24f8555"
        )
        assert verify.is_digest(verify.digest(b""))
        assert not verify.is_digest("sha256:short")
        assert verify.ref_kind("claim:" + verify.digest(b"")) == "claim"
        assert verify.ref_kind("bogus:" + verify.digest(b"")) is None


class TestDominance:
    """The order semantics of Tests/evidence_rank.py `dominates`, restated."""

    @pytest.mark.parametrize(
        ("chosen", "alternative", "expected"),
        [
            ({"a": "1", "b": "1"}, {"a": "2", "b": "1"}, True),
            ({"a": "1", "b": "1"}, {"a": "1", "b": "1"}, False),
            ({"a": "1", "b": "2"}, {"a": "2", "b": "1"}, False),
            ({"a": None, "b": "1"}, {"a": "0", "b": "2"}, True),
            ({"a": "5", "b": None}, {"a": "0", "b": "9"}, False),
            ({"a": None, "b": None}, {"a": "9", "b": "9"}, False),
            ({"a": "2"}, {"a": "10"}, True),
        ],
    )
    def test_strict_dominance_over_comparable_axes(self, chosen, alternative, expected):
        assert verify.dominated(chosen, alternative) is expected

    def test_a_dominated_pick_fails_the_check(self, built, tmp_path):
        target = _copy(built, tmp_path)
        claims = _records(target / "claims.jsonl")
        km = _claim_named(claims, "reaction_Km")
        km["derivation"]["settings"]["ordinals"] = json.dumps({
            "chosen": {"assay_completeness": "1", "variant_statement": "2", "organism_match": "1"},
            "alternatives": {"6.3 mM ref 739603": {"assay_completeness": "2", "variant_statement": "2", "organism_match": "1"}},
        }, sort_keys=True, separators=(",", ":"))
        new_ref = _replace_claim(target, "claim:" + km["id"], _recomputed(km))
        report = verify.verify_bundle(target)
        failing = report.failed()
        assert [(c.name, c.claim) for c in failing] == [("dominance", new_ref)]
        assert "strictly dominated by '6.3 mM ref 739603'" in failing[0].detail

    def test_without_ordinals_the_check_says_not_certified_and_does_not_fail(self, built, tmp_path):
        target = _copy(built, tmp_path)
        claims = _records(target / "claims.jsonl")
        km = _claim_named(claims, "reaction_Km")
        del km["derivation"]["settings"]["ordinals"]
        km["derivation"]["settings"]["dominance"] = "not certified: ordinals unavailable"
        new_ref = _replace_claim(target, "claim:" + km["id"], _recomputed(km))
        report = verify.verify_bundle(target)
        assert report.ok
        dominance = next(c for c in report.checks if c.name == "dominance" and c.claim == new_ref)
        assert dominance.ok and "not certified: ordinals unavailable" in dominance.detail


class TestUnitArithmetic:
    def test_within_tolerance(self):
        assert verify.within_tolerance(Decimal("6000"), Decimal("6000"), None)
        assert not verify.within_tolerance(Decimal("6000.001"), Decimal("6000"), None)
        assert verify.within_tolerance(Decimal("6000.001"), Decimal("6000"), "1e-6")
        assert not verify.within_tolerance(Decimal("6001"), Decimal("6000"), "1e-6")

    def test_a_stated_factor_with_the_right_value_passes(self, built, tmp_path):
        target = _copy(built, tmp_path)
        claims = _records(target / "claims.jsonl")
        km = _claim_named(claims, "reaction_Km")
        km["unit"] = "uM"
        km["value_text"] = "6000"
        km["derivation"]["settings"]["unit_factor"] = "1000"
        new_ref = _replace_claim(target, "claim:" + km["id"], _recomputed(km))
        report = verify.verify_bundle(target)
        assert report.ok
        arithmetic = next(c for c in report.checks if c.name == "unit arithmetic" and c.claim == new_ref)
        assert "6 mM × 1000 = 6000 uM" in arithmetic.detail
        located = next(c for c in report.checks if c.name == "row locator" and c.claim == new_ref)
        assert "compared under unit arithmetic" in located.detail


class TestFindingARow:
    @pytest.fixture(scope="class")
    def page(self, built):
        files = verify.read_bundle_files(built[0])
        enzyme = next(s for s in files.snapshots.values() if s.source == "brenda_enzyme")
        return verify.read_bundle_files(built[0]).blob_path(enzyme.id), enzyme

    def test_the_recorded_page_has_the_counted_row_openings(self, page):
        import gzip

        data = gzip.decompress(page[0].read_bytes())
        assert len(verify.row_regions(data)) == 4615

    def test_the_six_mm_row_is_found_by_reference_value_and_commentary(self, page):
        import gzip

        data = gzip.decompress(page[0].read_bytes())
        region = verify.find_row_region(data, reference="641068", value_text="6", commentary="30°C, pH 7.5, wild-type")
        assert region == (1980173, 1980928)
        assert data[region[0]:region[0] + 30] == b'<div id="tab12r13sr112" class='
        # The same number spelt otherwise is the same value; a wrong commentary or reference is not a row.
        assert verify.find_row_region(data, reference="641068", value_text="6.0", commentary="30°C, pH 7.5, wild-type") == region
        assert verify.find_row_region(data, reference="641068", value_text="6", commentary="30°C, pH 7.5, mutant") is None
        assert verify.find_row_region(data, reference="999999", value_text="6", commentary="30°C, pH 7.5, wild-type") is None

    def test_a_reference_inside_an_href_is_not_the_row_saying_it(self):
        row = (
            b'<div id="tab1r1" class="row">\n<div id="tab1r1c0" class="cell"><span>6\n</span></div>'
            b'<div id="tab1r1c5" class="cell"><span><a href="./literature.php?e=2.7.1.1&r=641068">other</a>\n</span></div>'
            b"</div>\n"
        )
        assert verify.find_row_region(row, reference="641068", value_text="6", commentary=None) is None
        spoken = row.replace(b">other<", b">641068<")
        assert verify.find_row_region(spoken, reference="641068", value_text="6", commentary=None) == (0, len(spoken))

    def test_a_number_inside_a_longer_number_is_not_the_value(self):
        row = b'<div id="tab1r1" class="row">\n<div id="tab1r1c0" class="cell"><span>16\n</span></div></div>\n'
        assert verify.find_row_region(row, reference=None, value_text="6", commentary=None) is None
        assert verify.find_row_region(row, reference=None, value_text="16", commentary=None) == (0, len(row))

    def test_region_of(self):
        starts = [10, 50, 90]
        assert verify.region_of(5, starts, 100) is None
        assert verify.region_of(10, starts, 100) == (10, 50)
        assert verify.region_of(70, starts, 100) == (50, 90)
        assert verify.region_of(95, starts, 100) == (90, 100)


# ---------------------------------------------------------------------------
# The command
# ---------------------------------------------------------------------------

class TestTheCommand:
    def test_one_line_per_check_and_exit_0(self, built):
        out, root = built
        code, stdout, stderr = _run([str(out)])
        assert code == 0 and stderr == ""
        lines = stdout.splitlines()
        assert lines[0].startswith("ok  snapshot bytes   snapshot:sha256:")
        assert any(line.startswith(f"ok  identity         {root}  model") for line in lines)
        assert any(line.startswith("ok  row locator      claim:sha256:") and "reaction_Km" in line for line in lines)
        assert any(line.startswith("ok  dominance        claim:sha256:") for line in lines)
        assert lines[-2].startswith("not checked: Antimony regeneration")
        assert lines[-1].startswith("18 checks: 18 ok, 0 failed; 2 not checked. Re-checkable:")

    def test_json_prints_the_report(self, built):
        code, stdout, _ = _run([str(built[0]), "--json"])
        assert code == 0
        report = json.loads(stdout)
        assert report["ok"] is True
        assert {c["name"] for c in report["checks"]} >= {"identity", "row locator", "certificate", "root"}
        assert all(set(c) == {"name", "claim", "ok", "detail"} for c in report["checks"])

    def test_a_failed_check_is_exit_3_naming_the_first_failing_claim(self, built, tmp_path):
        target = _copy(built, tmp_path)
        claims = _records(target / "claims.jsonl")
        km = _claim_named(claims, "reaction_Km")
        km["tolerance"] = "1e-6"
        _write(target / "claims.jsonl", claims)
        code, stdout, stderr = _run([str(target)])
        assert code == 3
        assert f"FAIL  identity         claim:{km['id']}  reaction_Km" in stdout
        assert stderr.startswith(f"Refused: identity did not hold for claim:{km['id']}: reaction_Km")
        assert "1 failed" in stdout.splitlines()[-1]

    def test_a_directory_that_is_not_a_bundle_is_exit_2(self, tmp_path):
        code, stdout, stderr = _run([str(tmp_path)])
        assert code == 2 and stdout == ""
        assert stderr.startswith("Not a claims bundle this checker can read:")
        assert "manifest.json is missing" in stderr

    def test_a_record_missing_a_field_is_malformed_not_failed(self, built, tmp_path):
        target = _copy(built, tmp_path)
        claims = _records(target / "claims.jsonl")
        del claims[0]["derivation"]
        _write(target / "claims.jsonl", claims)
        with pytest.raises(verify.BundleMalformed) as caught:
            verify.verify_bundle(target)
        assert "has no 'derivation'" in str(caught.value)
        assert _run([str(target)])[0] == 2

    def test_a_wrong_format_is_malformed(self, built, tmp_path):
        target = _copy(built, tmp_path)
        manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
        manifest["format"] = "caterva-claims/9"
        (target / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        with pytest.raises(verify.BundleMalformed, match="caterva-claims/9"):
            verify.verify_bundle(target)

    def test_help_uses_the_prog_it_was_given(self):
        code, stdout, _ = _run(["--help"])
        assert code == 0
        assert "--json" in stdout and "caterva verify ./claims" in stdout
        assert "verified" not in stdout.lower()

    def test_the_module_runs_from_a_terminal(self, built):
        result = subprocess.run(
            [sys.executable, "-m", "caterva.check", str(built[0])],
            capture_output=True, text=True, cwd=str(REPO_ROOT),
        )
        assert result.returncode == 0, result.stderr
        assert "Re-checkable" in result.stdout

    def test_the_app_dispatches_to_the_checker(self):
        from caterva.app import COMMANDS, main as app_main

        assert COMMANDS["verify"][0] == "caterva.check.__main__"
        out = io.StringIO()
        with redirect_stdout(out), pytest.raises(SystemExit) as exc:
            app_main(["verify", "--help"])
        assert exc.value.code == 0
        assert "caterva verify" in out.getvalue() and "--json" in out.getvalue()


def test_a_row_whose_value_prints_with_an_exponent_is_found_on_the_page(tmp_path):
    """BRENDA writes 0.00000023; the row's value text is 2.3e-07. Held numerically."""
    import gzip as _gzip

    from caterva.evidence import rows as rows_mod
    from caterva.evidence.store import EvidenceStore

    page = _gzip.decompress((Path(__file__).resolve().parents[2] / "Tests" / "fixtures" / "recorded"
                             / "brenda_2.7.1.1.html.gz").read_bytes())
    store = EvidenceStore(tmp_path / "store")
    snap = store.put_snapshot(page, source="brenda_enzyme",
                              locator="https://www.brenda-enzymes.org/enzyme.php?ecno=2.7.1.1",
                              retrieved_at="2026-09-28T00:00:00Z", licence="CC BY 4.0")
    rows = rows_mod.rows_from_page(page.decode("utf-8"), ec="2.7.1.1", table="km",
                                   organism="Homo sapiens", snapshot_ref=f"snapshot:{snap.id}")
    tiny = [r for r in rows if "e-" in r.value_text]
    assert tiny, "the pinned page holds sub-micromolar human Km rows"
    row = tiny[0]
    store.put_row(row)
    claim = make_claim("cited", f"reaction_Km = Km(2.7.1.1, {row.substrate}, Homo sapiens)",
                       row.value_text, row.unit, None,
                       Derivation(RuleRef("select.resolver", 1, "ADR 0047"), (f"row:{row.id}",),
                                  rows_mod.certificates_for(row, page), {}))
    store.put_claim(claim)
    out = tmp_path / "bundle"
    store.export_bundle(f"claim:{claim.id}", out)
    report = verify.verify_bundle(out)
    locator = [c for c in report.checks if c.name == "row locator"]
    assert locator and all(c.ok for c in locator), [c.detail for c in locator]
