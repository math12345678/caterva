"""`caterva why`: the derivation of a number, printed from the bundle down to the bytes.

The layout is ADR 0179's. The command reads the showcase bundle
(caterva/evidence/showcase.py, built once per module with the network made
impossible) from the sha-pinned recordings, so the numbers it prints are the
ones those pages produce. The expectations below type them in (the page's
hash, the certificate spans, the PMID). The hash and the spans are held to
the bytes as well as to the printout: the hash to the digest of the page the
bundle holds, each span to the text that page holds at it, so a printout
agreeing with a wrong expectation would fail the second check. The PMID is
the one test_evidence_references.py reads from the pinned literature page.
"""
from __future__ import annotations

import gzip
import hashlib
import io
import json
import shutil
import sqlite3
import subprocess
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import httpx
import pytest

from caterva.evidence import showcase
from caterva.evidence.bundle import read_bundle
from caterva.evidence.claims import SELECT_RESOLVER, Derivation, Refusal, make_claim
from caterva.evidence.references import reference_url
from caterva.evidence.store import EvidenceStore
from caterva.evidence.why import RULE_MEANINGS, main

REPO_ROOT = Path(__file__).resolve().parents[2]
PAGE_HASH = "sha256:3a69b492abcd7253b301d7a002f60d52a971ba9352a3a2559ec5f12f5060ef91"

#: Where the Km claim's certificates sit in the recorded hexokinase page.
KM_SPANS = (((1980757, 1980763), "641068"), ((1980265, 1980266), "6"),
            ((1980612, 1980636), "30°C, pH 7.5, wild-type"))


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


@pytest.fixture(scope="module")
def refs(built):
    bundle = read_bundle(built[0])
    return {c.subject.split(" = ")[0]: c.ref for c in bundle.claims.values()}


def _run(args):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        try:
            code = main(args)
        except SystemExit as exc:  # argparse
            code = exc.code
    return code, out.getvalue(), err.getvalue()


class TestTheLayout:
    def test_a_cited_claim_down_to_the_bytes(self, built, refs):
        code, out, err = _run([refs["reaction_Km"], "--bundle", str(built[0])])
        assert code == 0 and err == ""
        lines = out.splitlines()
        assert lines[0] == f"{refs['reaction_Km']}  cited  reaction_Km = Km(2.7.1.1, D-glucose, Homo sapiens)"
        assert "  value        6 mM" in lines
        assert "  rule         select.resolver v1 (ADR 0047): the row the resolver carried: weight-free dominance, then the minimum" in lines
        assert any(line.startswith("  input        row:sha256:") for line in lines)
        assert "    parser       parse.brenda_table v1 (ADR 0179): a row read from a BRENDA enzyme page by the literature layer's parser" in lines
        assert "    locator      brenda:2.7.1.1:km:Homo sapiens:D-glucose:641068:6:0" in lines
        assert "    value        6 mM   substrate D-glucose   organism Homo sapiens" in lines
        assert "    commentary   30°C, pH 7.5, wild-type" in lines
        assert "    reference    641068" in lines
        assert "  certificates 5, each a byte span of the snapshot that reads as its text" in lines
        page = read_bundle(built[0]).snapshot_bytes(f"snapshot:{PAGE_HASH}")
        assert "sha256:" + hashlib.sha256(page).hexdigest() == PAGE_HASH
        for (start, end), text in KM_SPANS:
            assert f"                 [{start}, {end})  {text!r}" in lines
            assert page[start:end].decode("utf-8") == text, "the span is where the pinned page holds the text"
        assert f"  snapshot     snapshot:{PAGE_HASH}  brenda_enzyme" in lines
        assert "    locator      https://www.brenda-enzymes.org/enzyme.php?ecno=2.7.1.1" in lines
        assert "    retrieved    2026-09-28   licence CC BY 4.0   release none stated" in lines
        assert "    served from  Tests/fixtures/recorded/brenda_2.7.1.1.html.gz" in lines
        assert "  reference    641068  PMID 7730377" in lines
        assert "                 Human beta-cell glucokinase. Dual role of Ser-151 in catalysis and hexose affinity" in lines
        assert any(line.startswith("                 Xu, L.Z.; Harrison, R.W.; Weber, I.T.; Pilkis, S.J. (1995)") for line in lines)

    def test_the_ordinals_are_printed_as_axes(self, built, refs):
        _, out, _ = _run([refs["reaction_Km"], "--bundle", str(built[0])])
        assert "  ordinals     chosen row  assay_completeness=2  organism_match=1  variant_statement=2  (higher is better)" in out
        assert "               alternative 6.3 mM ref 739603: assay_completeness=2  organism_match=1  variant_statement=2" in out

    def test_the_root_prints_every_input_claim_under_it(self, built, refs):
        code, out, _ = _run([built[1], "--bundle", str(built[0])])
        assert code == 0
        lines = out.splitlines()
        assert lines[0] == f"{built[1]}  computed  model = michaelis_menten(2.7.1.1, D-glucose, Homo sapiens)"
        assert "  rule         compile.model v1 (ADR 0179): " + RULE_MEANINGS["compile.model"] in lines
        assert "  value        not part of the identity: a computed claim is held to a tolerance (none stated), not to a number" in lines
        assert any(line.startswith("  input        ir:sha256:") and "named by digest; not stored" in line for line in lines)
        for identifier in ("reaction_Km", "reaction_kcat", "reaction_S"):
            assert any(line.startswith(f"    {refs[identifier]}  ") for line in lines), identifier
        assert "      value        1 mM" in lines
        assert "      rule         chosen.starting_amount v1 (ADR 0044): a starting amount or exponent somebody chose" in lines
        assert "      reference    739603  PMID 24723372" in lines

    def test_the_store_prints_the_same_derivation(self, built, refs):
        from_bundle = _run([refs["reaction_Km"], "--bundle", str(built[0])])
        from_store = _run([refs["reaction_Km"], "--store", str(built[0] / "store")])
        assert from_store[0] == 0
        assert from_store[1] == from_bundle[1]

    def test_a_refused_claim_prints_its_candidates(self, tmp_path):
        store = EvidenceStore(tmp_path / "store")
        try:
            snapshot = store.put_snapshot(
                b"<html>no such row</html>", source="brenda_enzyme",
                locator="https://www.brenda-enzymes.org/enzyme.php?ecno=1.1.1.27",
                retrieved_at="2026-10-17T00:00:00Z", licence="CC BY 4.0",
            )
            refused = store.put_claim(make_claim(
                "refused", "reaction_Ki = Ki(1.1.1.27, oxamate, Homo sapiens)", None, None, None,
                Derivation(SELECT_RESOLVER, inputs=(snapshot.ref,), settings={"requested_value": "0.0014"}),
                refusal=Refusal(
                    requested="0.0014 mM, ref 711801, commentary 'pH 7.4, 25°C'",
                    kind="row_not_found_on_pinned_page",
                    candidates=("row:" + PAGE_HASH + " | the commentary differs",),
                ),
            ))
        finally:
            store.close()
        code, out, _ = _run([refused.ref, "--store", str(tmp_path / "store")])
        assert code == 0
        assert f"{refused.ref}  refused  reaction_Ki = Ki(1.1.1.27, oxamate, Homo sapiens)" in out
        assert "  value        none: refused" in out
        assert "  refusal      row_not_found_on_pinned_page: requested 0.0014 mM, ref 711801, commentary 'pH 7.4, 25°C'" in out
        assert f"    candidate    row:{PAGE_HASH} | the commentary differs" in out
        assert "  snapshot     " + snapshot.ref + "  brenda_enzyme" in out
        assert "    served from  the live service" in out

    def test_a_row_whose_paper_is_not_in_the_bundle_says_so(self, built, refs, tmp_path):
        target = tmp_path / "bundle"
        shutil.copytree(built[0], target, ignore=shutil.ignore_patterns("store"))
        kept = [line for line in (target / "snapshots.jsonl").read_text(encoding="utf-8").splitlines()
                if '"brenda_reference"' not in line]
        (target / "snapshots.jsonl").write_text("\n".join(kept) + "\n", encoding="utf-8")
        code, out, _ = _run([refs["reaction_Km"], "--bundle", str(target)])
        assert code == 0
        assert "  reference    641068  (the paper's page https://www.brenda-enzymes.org/literature.php?e=2.7.1.1&r=641068 is not in the bundle" in out
        assert "PMID" not in out


class TestRefusals:
    def test_a_ref_not_in_the_bundle_is_exit_3(self, built):
        missing = "claim:sha256:" + "0" * 64
        code, out, err = _run([missing, "--bundle", str(built[0])])
        assert code == 3 and out == ""
        assert err.strip() == f"Refused: {missing} is not in the bundle {built[0]}"

    def test_a_ref_not_in_the_store_is_exit_3(self, built):
        missing = "claim:sha256:" + "f" * 64
        code, _, err = _run([missing, "--store", str(built[0] / "store")])
        assert code == 3
        assert err.startswith(f"Refused: {missing} is not in the store ")

    def test_a_malformed_ref_is_a_usage_error(self, built):
        code, _, err = _run(["row:sha256:" + "0" * 64, "--bundle", str(built[0])])
        assert code == 2 and "is not a claim ref" in err
        code, _, err = _run(["six millimolar", "--bundle", str(built[0])])
        assert code == 2 and "error" in err

    def test_a_directory_that_is_not_a_bundle_is_exit_2(self, refs, tmp_path):
        code, _, err = _run([refs["reaction_Km"], "--bundle", str(tmp_path)])
        assert code == 2 and err.startswith("Not a claims bundle:")
        code, _, err = _run([refs["reaction_Km"], "--store", str(tmp_path / "nowhere")])
        assert code == 2 and "is not an evidence store" in err
        assert not (tmp_path / "nowhere").exists(), "asking must not create a store"

    def test_a_store_whose_index_is_not_sqlite_is_exit_2_and_named(self, refs, tmp_path):
        """It was a sqlite3.DatabaseError traceback, exit 1."""
        (tmp_path / "index.sqlite").write_text("not a database", encoding="utf-8")
        code, out, err = _run([refs["reaction_Km"], "--store", str(tmp_path)])
        assert code == 2 and out == ""
        assert err.startswith("Not a claims bundle: ")
        assert f"{tmp_path / 'index.sqlite'} is not an evidence store's index: file is not a database" in err
        assert sorted(p.name for p in tmp_path.iterdir()) == ["index.sqlite"], "asking created nothing"

    def test_a_store_that_is_another_programs_database_is_exit_2_and_left_alone(self, refs, tmp_path):
        other = sqlite3.connect(str(tmp_path / "index.sqlite"))
        other.execute("CREATE TABLE notes (text TEXT)")
        other.commit()
        other.close()
        before = (tmp_path / "index.sqlite").read_bytes()
        code, _, err = _run([refs["reaction_Km"], "--store", str(tmp_path)])
        assert code == 2 and err.startswith("Not a claims bundle: ")
        assert "is not an evidence store's index" in err
        assert (tmp_path / "index.sqlite").read_bytes() == before, "no tables were added to it"

    def test_asking_a_store_changes_nothing_in_it(self, built, refs, tmp_path):
        target = tmp_path / "store"
        shutil.copytree(built[0] / "store", target)
        before = {p.name: p.read_bytes() for p in target.rglob("*") if p.is_file()}
        code, _, _ = _run([refs["reaction_Km"], "--store", str(target)])
        assert code == 0
        assert {p.name: p.read_bytes() for p in target.rglob("*") if p.is_file()} == before

    def test_a_store_record_that_does_not_produce_its_id_is_refused_not_a_traceback(self, built, refs, tmp_path):
        """A store is read record by record, so a hand-edited record is met
        while printing; it is refused (exit 3), as a bundle's blob that does
        not digest to its ref is."""
        target = tmp_path / "store"
        shutil.copytree(built[0] / "store", target)
        km = refs["reaction_Km"].split(":", 1)[1]
        db = sqlite3.connect(str(target / "index.sqlite"))
        (text,) = db.execute("SELECT json FROM claims WHERE id = ?", (km,)).fetchone()
        record = json.loads(text)
        record["value_text"] = "60"
        db.execute("UPDATE claims SET json = ? WHERE id = ?", (json.dumps(record), km))
        db.commit()
        db.close()
        code, out, err = _run([refs["reaction_Km"], "--store", str(target)])
        assert code == 3 and out == ""
        assert err.startswith(f"Refused: claim id {km} is not the digest of its derivation")

    def test_a_store_blob_that_is_not_its_pages_bytes_prints_no_paper_from_it(self, built, refs, tmp_path):
        """The store handed back whatever a blob file held: a blob that was
        not gzip was a traceback, and a page edited to another PMID printed
        that PMID as the paper. Both are now reported in the reference line,
        as a bundle reports a blob that does not digest to its ref."""
        target = tmp_path / "store"
        shutil.copytree(built[0] / "store", target)
        bundle = read_bundle(built[0])
        paper = next(s for s in bundle.snapshots.values() if s.locator == reference_url("2.7.1.1", "641068"))
        page = bundle.snapshot_bytes(paper.ref)
        forged = page.replace(b"7730377", b"1234567")
        assert forged != page
        blob = target / "blobs" / (paper.id[len("sha256:"):] + ".gz")
        for damaged, reason in ((gzip.compress(forged, mtime=0), "does not digest to"),
                                (b"not gzip at all", "is not a gzip stream")):
            blob.write_bytes(damaged)
            code, out, err = _run([refs["reaction_Km"], "--store", str(target)])
            assert code == 0 and err == ""
            assert "1234567" not in out and "PMID 7730377" not in out
            line = next(x for x in out.splitlines() if x.startswith("  reference    641068  page "))
            assert line.startswith(f"  reference    641068  page {paper.ref} pinned but unreadable: ")
            assert reason in line

    def test_one_location_exactly(self, built, refs):
        code, _, err = _run([refs["reaction_Km"]])
        assert code == 2 and "--bundle" in err
        code, _, err = _run([refs["reaction_Km"], "--bundle", str(built[0]), "--store", str(built[0] / "store")])
        assert code == 2 and "not allowed with" in err


class TestTheCommand:
    def test_help_uses_the_prog_it_was_given(self):
        code, out, _ = _run(["--help"])
        assert code == 0
        assert "caterva why claim:sha256:<hex> --bundle ./claims" in out
        assert "--store" in out

    def test_the_app_dispatches_to_the_command(self):
        from caterva.app import COMMANDS, main as app_main

        assert COMMANDS["why"][0] == "caterva.evidence.why"
        out = io.StringIO()
        with redirect_stdout(out), pytest.raises(SystemExit) as exc:
            app_main(["why", "--help"])
        assert exc.value.code == 0
        assert "caterva why" in out.getvalue() and "--bundle" in out.getvalue()

    def test_the_module_runs_from_a_terminal(self, built, refs):
        result = subprocess.run(
            [sys.executable, "-m", "caterva.evidence.why", refs["reaction_S"], "--bundle", str(built[0])],
            capture_output=True, text=True, cwd=str(REPO_ROOT),
        )
        assert result.returncode == 0, result.stderr
        assert "chosen  reaction_S = starting amount of D-glucose" in result.stdout

    def test_every_rule_of_the_slice_has_a_gloss(self):
        from caterva.evidence.claims import RULES

        assert set(RULE_MEANINGS) == set(RULES)
        for rule_id, meaning in RULE_MEANINGS.items():
            assert len(meaning) > 20, rule_id
