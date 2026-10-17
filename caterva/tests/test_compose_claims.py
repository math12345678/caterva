"""`caterva compose --claims DIR`: the hexokinase run, offline, writes a bundle `caterva verify` accepts.

WHAT IS RUN
-----------
The real command, in-process, for

    caterva compose "Michaelis Menten" --subject 2.7.1.1 --organism human
        --substrate glucose --claims DIR

against the committed recording of BRENDA's page for EC 2.7.1.1 and the
recorded answers of the other services (Tests/fixtures/recorded/, README
there), plus the two literature pages the run captures for the references
it cites (caterva/tests/fixtures/compose_claims/, README there). Every
network send is made impossible first: a request no recording answers
raises, and the test that expects that says so.

WHAT IS HELD
------------
The report ends with a `## Claims` section naming the root claim, the
counts and the re-check line; the bundle's Km claim is cited from the row
with reference 641068 and value "6", its kcat from 739603 and "40.1", each
with certificates in the pinned page; the independent checker
(caterva/check/verify.py) passes every check; a second run into another
directory gives the same root id; the CSV export of that second run carries
each claim's id in a 28th column; a measured value whose row is NOT on the
pinned page gets a refused claim and never a citation; a reference page no
recording answers is a note and a refused claim, not a failed run; without
`--claims` nothing of the evidence layer is imported.
"""
from __future__ import annotations

import contextlib
import csv
import io
import json
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from caterva.compose.__main__ import build_parser, check_request, compose_report, main
from caterva.compose.export import CLAIM_COLUMN, Measurement, provenance_of
from caterva.compose.pipeline import compose
from caterva.evidence import compose_claims
from caterva.evidence.bundle import read_bundle
from caterva.evidence.claims import is_digest, ref_digest, ref_kind
from caterva.evidence.store import EvidenceStore

REPO = Path(__file__).resolve().parents[2]
RECORDED = REPO / "Tests" / "fixtures" / "recorded"
RECORDED_HTTP = RECORDED / "http"
LITERATURE_HTTP = Path(__file__).resolve().parent / "fixtures" / "compose_claims" / "http"
HEXOKINASE_SHA256 = "3a69b492abcd7253b301d7a002f60d52a971ba9352a3a2559ec5f12f5060ef91"

#: Port 9 (discard) on loopback: nothing listens, so a request through this
#: proxy fails at once instead of reaching a database.
CLOSED_PROXY = "http://127.0.0.1:9"
PROXY_VARIABLES = ("HTTPS_PROXY", "HTTP_PROXY", "ALL_PROXY", "https_proxy", "http_proxy", "all_proxy")

ARGS = ["Michaelis Menten", "--subject", "2.7.1.1", "--organism", "human",
        "--substrate", "glucose", "--no-simulate", "--no-ranking", "--no-analysis"]


# ---------------------------------------------------------------------------
# Offline
# ---------------------------------------------------------------------------

def _http_retry_copies():
    """Every loaded copy of http_retry, each with its own memo."""
    from caterva.checkout import literature_module

    literature_module("http_retry")
    return [sys.modules[n] for n in ("http_retry", "Tests.http_retry") if n in sys.modules]


def _replay_directory(target: Path, *sources: Path) -> Path:
    """One directory holding every recording of `sources`: the replay
    variable names one directory, and the literature-page recordings live
    apart from the runner's (fixtures/compose_claims/README.md)."""
    target.mkdir(parents=True, exist_ok=True)
    for source in sources:
        for path in sorted(source.glob("*.json.gz")):
            shutil.copy2(path, target / path.name)
    return target


@contextlib.contextmanager
def offline(replay: Path):
    """Recorded answers on, and httpx refusing to send anything else."""
    patch = pytest.MonkeyPatch()
    copies = _http_retry_copies()

    def refuse(url, *args, **kwargs):
        raise ConnectionError(f"no recording answers {url}; this test does not go live")

    def no_transport(self, request):
        raise httpx.ConnectError("network disabled in this test", request=request)

    patch.setenv("CATERVA_BRENDA_RECORDED", str(RECORDED))
    patch.setenv("CATERVA_HTTP_RECORDED", str(replay))
    patch.delenv("CATERVA_HTTP_RECORD", raising=False)
    patch.delenv("CATERVA_ENABLE_KEGG", raising=False)
    for name in PROXY_VARIABLES:
        patch.setenv(name, CLOSED_PROXY)
    patch.setenv("NO_PROXY", "")
    patch.setenv("no_proxy", "")
    patch.setattr(httpx, "get", refuse)
    patch.setattr(httpx.HTTPTransport, "handle_request", no_transport)
    for copy in copies:
        copy.clear_memo()
    try:
        yield
    finally:
        for copy in copies:
            copy.clear_memo()
        patch.undo()


def run_cli(argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(list(argv))
    return SimpleNamespace(code=code, out=out.getvalue(), err=err.getvalue())


def run_report(argv):
    """`compose_report` as `main` calls it, keeping the ComposedReport."""
    from caterva.compose.organisms import normalise_organism

    parser = build_parser()
    args = parser.parse_args(list(argv))
    check_request(parser, args)
    args.organism, note = normalise_organism(args.organism)
    out, err = io.StringIO(), io.StringIO()
    composed = compose_report(args, organism_note=note, stream=out, err=err)
    return SimpleNamespace(code=composed.code, out=out.getvalue(), err=err.getvalue(),
                           composed=composed)


# ---------------------------------------------------------------------------
# The showcase: two runs, once per module
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def showcase(tmp_path_factory):
    base = tmp_path_factory.mktemp("claims")
    replay = _replay_directory(base / "http", RECORDED_HTTP, LITERATURE_HTTP)
    first = base / "claims"
    second = base / "claims-again"
    with offline(replay):
        report = run_report([*ARGS, "--claims", str(first)])
        export = run_cli([*ARGS, "--claims", str(second), "--export", "csv"])
    return SimpleNamespace(first=first, second=second, replay=replay, report=report,
                           export=export)


def claims_by_identifier(bundle):
    return {c.subject.split(" = ", 1)[0]: c for c in bundle.claims.values()}


class TestTheReport:
    def test_the_run_exits_zero_with_nothing_on_stderr(self, showcase):
        assert showcase.report.code == 0
        assert showcase.report.err == ""

    def test_the_report_ends_with_a_claims_section_before_the_footer(self, showcase):
        out = showcase.report.out
        assert "\n## Claims\n" in out
        section = out.split("\n## Claims\n", 1)[1]
        assert "\n## " not in section, "the claims section is the last section"
        assert section.index("Re-check offline") < section.index("Built by Caterva")

    def test_the_section_names_the_root_the_counts_the_directory_and_the_recheck_line(self, showcase):
        section = showcase.report.out.split("\n## Claims\n", 1)[1]
        root = read_bundle(showcase.first).root
        assert f"Root claim: `{root}`" in section
        assert "2 cited" in section and "3 chosen" in section and "1 computed" in section
        assert "0 placeholder" in section and "0 refused" in section
        assert f"Bundle: {showcase.first}" in section
        assert compose_claims.RECHECK_LINE.format(directory=showcase.first) in section

    def test_the_section_lists_every_quantity_with_its_kind_and_ref(self, showcase):
        section = showcase.report.out.split("\n## Claims\n", 1)[1]
        by = claims_by_identifier(read_bundle(showcase.first))
        assert f"- `reaction_Km`: cited, 6 mM -- `{by['reaction_Km'].ref}`" in section
        assert f"- `reaction_kcat`: cited, 40.1 1/s -- `{by['reaction_kcat'].ref}`" in section
        assert f"- `reaction_S`: chosen, 1 mM -- `{by['reaction_S'].ref}`" in section

    def test_the_measured_values_in_the_report_are_the_cited_ones(self, showcase):
        out = showcase.report.out
        assert "| `reaction_Km` | 6.0 mM | literature (Homo sapiens) | BRENDA ref 641068 |" in out
        assert "| `reaction_kcat` | 40.1 1/s | literature (Homo sapiens) | BRENDA ref 739603 |" in out

    def test_the_studio_record_carries_the_claim_set(self, showcase):
        composed = showcase.report.composed
        assert composed.claims is not None
        assert composed.claims.root == read_bundle(showcase.first).root
        record = composed.sections.records[-1]
        assert record.key == "claims" and record.title == "Claims"
        assert record.data["claims"] is composed.claims
        assert composed.claims.by_identifier["reaction_Km"].startswith("claim:sha256:")


class TestTheBundle:
    def test_the_km_claim_is_cited_from_the_641068_row_with_value_6(self, showcase):
        bundle = read_bundle(showcase.first)
        km = claims_by_identifier(bundle)["reaction_Km"]
        assert km.kind == "cited"
        assert km.value_text == "6" and km.unit == "mM"
        assert km.subject == "reaction_Km = Km(2.7.1.1, D-glucose, Homo sapiens)"
        assert km.derivation.rule.rule_id == "select.resolver"
        assert km.derivation.rule.version == 1 and km.derivation.rule.adr == "ADR 0047"
        (row_ref,) = km.derivation.inputs
        row = bundle.get(row_ref)
        assert row.reference == "641068" and row.value_text == "6" and row.unit == "mM"
        assert row.commentary == "30°C, pH 7.5, wild-type"
        assert row.locator == "brenda:2.7.1.1:km:Homo sapiens:D-glucose:641068:6:0"
        assert row.snapshot == f"snapshot:sha256:{HEXOKINASE_SHA256}"

    def test_the_kcat_claim_is_cited_from_the_739603_row_with_value_40_1(self, showcase):
        bundle = read_bundle(showcase.first)
        kcat = claims_by_identifier(bundle)["reaction_kcat"]
        assert kcat.kind == "cited" and kcat.value_text == "40.1" and kcat.unit == "1/s"
        row = bundle.get(kcat.derivation.inputs[0])
        assert row.reference == "739603" and row.quantity == "kcat"
        assert row.commentary == "wild-type, pH 7.6, 25 °C"

    def test_each_cited_claim_certifies_its_reference_value_and_commentary_in_the_page(self, showcase):
        bundle = read_bundle(showcase.first)
        page = bundle.snapshot_bytes(f"snapshot:sha256:{HEXOKINASE_SHA256}")
        for identifier, texts in (
            ("reaction_Km", {"641068", "6", "30°C, pH 7.5, wild-type"}),
            ("reaction_kcat", {"739603", "40.1", "wild-type, pH 7.6, 25 °C"}),
        ):
            claim = claims_by_identifier(bundle)[identifier]
            matched = {c.matched for c in claim.derivation.certificates}
            assert texts <= matched, (identifier, matched)
            for certificate in claim.derivation.certificates:
                start, end = certificate.span
                assert page[start:end].decode("utf-8") == certificate.matched

    def test_the_ordinals_come_from_the_resolver_s_frontier(self, showcase):
        bundle = read_bundle(showcase.first)
        km = claims_by_identifier(bundle)["reaction_Km"]
        ordinals = json.loads(km.derivation.settings["ordinals"])
        assert ordinals["chosen"] == {
            "assay_completeness": "2", "condition_proximity": None, "organism_match": "2",
        }
        # The two other rows of the resolver's frontier for this request.
        assert set(ordinals["alternatives"]) == {"18 mM ref 641068", "6.3 mM ref 739603"}
        assert "unit_factor" not in km.derivation.settings, "the row is already in the model's unit"

    def test_the_root_is_the_computed_model_over_every_parameter_claim(self, showcase):
        bundle = read_bundle(showcase.first)
        root = bundle.get(bundle.root)
        assert root.kind == "computed"
        assert root.derivation.rule.rule_id == "compile.model"
        by = claims_by_identifier(bundle)
        refs = set(root.derivation.inputs)
        for identifier in ("reaction_Km", "reaction_kcat", "reaction_S", "reaction_P", "reaction_E"):
            assert by[identifier].ref in refs
        ir = root.derivation.settings["ir"]
        assert is_digest(ir) and f"ir:{ir}" in refs
        assert root.value_text is None and root.tolerance is None

    def test_the_ir_is_the_digest_of_the_annotation_free_antimony_of_this_model(self, showcase):
        # Rebuilt by hand from the two cited values: the source depends only
        # on the network, so it must digest to what the run recorded.
        model = compose("Michaelis Menten", subject="2.7.1.1", organism="Homo sapiens",
                        substrate="glucose")
        provenanced = provenance_of(model, measured={
            "reaction_Km": Measurement(6.0, "mM", "BRENDA ref 641068"),
            "reaction_kcat": Measurement(40.1, "1/s", "BRENDA ref 739603"),
        })
        bundle = read_bundle(showcase.first)
        root = bundle.get(bundle.root)
        assert root.derivation.settings["ir"] == compose_claims.ir_digest(provenanced)

    def test_the_enzyme_page_is_pinned_as_read_from_the_recording(self, showcase):
        bundle = read_bundle(showcase.first)
        page = bundle.get(f"snapshot:sha256:{HEXOKINASE_SHA256}")
        assert page.source == "brenda_enzyme"
        assert page.locator == "https://www.brenda-enzymes.org/enzyme.php?ecno=2.7.1.1"
        assert page.served_from == str(RECORDED / "brenda_2.7.1.1.html.gz")
        assert page.licence == "CC BY 4.0"

    def test_both_cited_references_literature_pages_are_captured_from_the_recordings(self, showcase):
        bundle = read_bundle(showcase.first)
        papers = {s.locator: s for s in bundle.snapshots.values() if s.source == "brenda_reference"}
        assert set(papers) == {
            "https://www.brenda-enzymes.org/literature.php?e=2.7.1.1&r=641068",
            "https://www.brenda-enzymes.org/literature.php?e=2.7.1.1&r=739603",
        }
        recordings = {p.name for p in LITERATURE_HTTP.glob("*.json.gz")}
        for snapshot in papers.values():
            assert Path(snapshot.served_from).name in recordings
            assert Path(snapshot.served_from).parent == showcase.replay

    def test_the_captured_page_for_641068_names_the_glucokinase_paper(self, showcase):
        from caterva.evidence.references import parse_reference_page

        bundle = read_bundle(showcase.first)
        (paper,) = [s for s in bundle.snapshots.values()
                    if s.locator.endswith("r=641068")]
        page = parse_reference_page(bundle.snapshot_bytes(paper.ref).decode("utf-8"))
        assert page.pmid == "7730377"
        assert page.title.startswith("Human beta-cell glucokinase")


class TestTheIndependentChecker:
    def test_verify_bundle_passes_every_check(self, showcase):
        from caterva.check.verify import verify_bundle

        report = verify_bundle(showcase.first)
        assert report.failed() == []
        assert report.ok
        names = {c.name for c in report.checks}
        assert {"snapshot bytes", "identity", "row locator", "certificate", "dominance",
                "inputs", "root"} <= names

    def test_the_checker_confirms_dominance_from_the_stated_ordinals(self, showcase):
        from caterva.check.verify import verify_bundle

        km = claims_by_identifier(read_bundle(showcase.first))["reaction_Km"]
        checks = [c for c in verify_bundle(showcase.first).checks
                  if c.name == "dominance" and c.claim == km.ref]
        assert len(checks) == 1 and checks[0].ok
        assert "not strictly dominated" in checks[0].detail


class TestDeterminismAndTheExport:
    def test_two_runs_into_two_directories_give_one_root_id(self, showcase):
        assert showcase.export.code == 0
        assert compose_claims.manifest_root(showcase.second) == compose_claims.manifest_root(showcase.first)
        first = claims_by_identifier(read_bundle(showcase.first))
        second = claims_by_identifier(read_bundle(showcase.second))
        assert {k: v.ref for k, v in first.items()} == {k: v.ref for k, v in second.items()}

    def test_the_csv_export_carries_each_claim_s_id_in_a_28th_column(self, showcase):
        # `--export` prints the artefact, so the text ends in print's newline
        # and csv.reader yields one empty row after the last quantity.
        rows = [row for row in csv.reader(io.StringIO(showcase.export.out)) if row]
        assert rows[0][-1] == CLAIM_COLUMN and len(rows[0]) == 28
        by = claims_by_identifier(read_bundle(showcase.second))
        cells = {row[0]: row[-1] for row in rows[1:]}
        assert set(cells) == set(by) - {"model"}
        assert cells["reaction_Km"] == by["reaction_Km"].ref
        assert cells["reaction_kcat"] == by["reaction_kcat"].ref
        assert cells["reaction_S"] == by["reaction_S"].ref
        assert ref_kind(cells["reaction_Km"]) == "claim" and is_digest(ref_digest(cells["reaction_Km"]))

    def test_the_export_writes_nothing_but_the_artefact(self, showcase):
        assert showcase.export.out.startswith("identifier,role,origin,")
        assert showcase.export.err == ""


# ---------------------------------------------------------------------------
# Refusals, never citations
# ---------------------------------------------------------------------------

def _page_bytes() -> bytes:
    import gzip

    return gzip.decompress((RECORDED / "brenda_2.7.1.1.html.gz").read_bytes())


def _pinned(store: EvidenceStore):
    """A recorder-shaped object whose one pinned page is the recorded one."""
    snapshot = store.put_snapshot(
        _page_bytes(), source="brenda_enzyme",
        locator="https://www.brenda-enzymes.org/enzyme.php?ecno=2.7.1.1",
        retrieved_at="2026-09-28T00:00:00Z", licence="CC BY 4.0",
        served_from=str(RECORDED / "brenda_2.7.1.1.html.gz"),
    )
    return SimpleNamespace(snapshot_for=lambda ec: snapshot if ec == "2.7.1.1" else None)


def _measured_model(km: Measurement):
    model = compose("Michaelis Menten", subject="2.7.1.1", organism="Homo sapiens",
                    substrate="glucose")
    model = model.with_measured({"reaction_Km": km})
    return provenance_of(model, measured=dict(model.measured)), model


class TestAValueTheRowDoesNotSupport:
    def test_a_value_not_on_the_pinned_page_gets_a_refused_claim_naming_the_candidates(self, tmp_path):
        # 641068 is a real reference on the page; 7.77 mM is not one of its values.
        provenanced, model = _measured_model(Measurement(
            7.77, "mM", "BRENDA ref 641068", organism="Homo sapiens",
            commentary="30°C, pH 7.5, wild-type",
        ))
        with EvidenceStore(tmp_path / "store") as store:
            claim_set = compose_claims.claims_for_model(provenanced, model, store, _pinned(store))
            km = next(c for c in claim_set.claims if c.subject.startswith("reaction_Km = "))
            assert km.kind == "refused" and km.value_text is None
            assert km.refusal.kind == compose_claims.ROW_NOT_FOUND
            assert "7.77 mM, reference 641068" in km.refusal.requested
            assert km.refusal.candidates, "the rows of reference 641068 are named"
            for candidate in km.refusal.candidates:
                ref, reason = candidate.split(" | ", 1)
                row = store.get(ref)
                assert row.reference == "641068" and row.quantity == "km"
                assert "not the value and commentary the resolver reported" in reason
            assert set(km.derivation.inputs) == {c.split(" | ", 1)[0] for c in km.refusal.candidates}
            assert claim_set.by_identifier["reaction_Km"] == km.ref
            assert claim_set.counts()["refused"] == 1 and claim_set.counts()["cited"] == 0
            written = compose_claims.write_bundle_for(claim_set, store, tmp_path / "bundle")
        from caterva.check.verify import verify_bundle

        report = verify_bundle(written.directory)
        assert report.failed() == []
        assert claims_by_identifier(read_bundle(written.directory))["reaction_Km"].kind == "refused"

    def test_a_search_that_pinned_no_page_gets_a_refused_claim_not_a_citation(self, tmp_path):
        provenanced, model = _measured_model(Measurement(6.0, "mM", "BRENDA ref 641068",
                                                         organism="Homo sapiens"))
        with EvidenceStore(tmp_path / "store") as store:
            nothing = SimpleNamespace(snapshot_for=lambda ec: None)
            claim_set = compose_claims.claims_for_model(provenanced, model, store, nothing)
            km = next(c for c in claim_set.claims if c.subject.startswith("reaction_Km = "))
            assert km.kind == "refused"
            assert km.refusal.kind == compose_claims.PAGE_NOT_PINNED
            assert "no BRENDA page for EC 2.7.1.1 was pinned" in km.derivation.settings["why"]
            assert km.refusal.candidates == ()


class TestAReferencePageNoRecordingAnswers:
    def test_it_is_a_note_and_a_refused_claim_and_the_run_still_succeeds(self, showcase, tmp_path):
        # The showcase's store, copied, with only the runner's recordings
        # on: the literature page is asked for again, nothing answers, and
        # httpx refuses to go live.
        store_dir = tmp_path / "store"
        shutil.copytree(showcase.first / compose_claims.STORE_DIR, store_dir)
        with EvidenceStore(store_dir) as store, offline(RECORDED_HTTP):
            cited = store.claims(kind="cited")
            assert len(cited) == 2
            claim_set = compose_claims.ClaimSet(root=cited[0].ref, claims=tuple(cited),
                                                by_identifier={})
            notes = compose_claims.capture_references(claim_set, store)
            assert len(notes) == 2
            for note in notes:
                assert note.startswith("reference page not captured for BRENDA ref ")
                assert "no recording answers" in note
                assert "`caterva why` will name the reference id, not the paper" in note
            refused = [c for c in store.claims(kind="refused")
                       if c.refusal.kind == compose_claims.REFERENCE_NOT_CAPTURED]
            assert {c.subject for c in refused} == {
                "reference 641068 = paper(2.7.1.1, 641068)",
                "reference 739603 = paper(2.7.1.1, 739603)",
            }
            assert all("no recording answers" in c.derivation.settings["why"] for c in refused)


# ---------------------------------------------------------------------------
# The flag's edges
# ---------------------------------------------------------------------------

class TestTheFlag:
    def test_without_the_flag_nothing_of_the_evidence_layer_is_imported(self):
        script = (
            "import contextlib, io, sys\n"
            "from caterva.compose.__main__ import main\n"
            "buffer = io.StringIO()\n"
            "with contextlib.redirect_stdout(buffer):\n"
            "    code = main(['Michaelis Menten', '--no-simulate', '--no-ranking', '--no-analysis'])\n"
            "loaded = sorted(m for m in sys.modules if m.startswith(('caterva.evidence', 'caterva.check')))\n"
            "print(code, loaded)\n"
        )
        result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True,
                                cwd=str(REPO), check=False)
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "0 []"

    def test_a_structure_only_model_still_gets_a_bundle_the_checker_accepts(self, tmp_path):
        from caterva.check.verify import verify_bundle

        result = run_cli(["Michaelis Menten", "--no-simulate", "--no-ranking", "--no-analysis",
                          "--claims", str(tmp_path / "claims")])
        assert result.code == 0
        bundle = read_bundle(tmp_path / "claims")
        counts = compose_claims.ClaimSet(root=bundle.root, claims=tuple(bundle.claims.values()),
                                         by_identifier={}).counts()
        assert counts == {"cited": 0, "chosen": 3, "placeholder": 2, "refused": 0, "computed": 1}
        km = claims_by_identifier(bundle)["reaction_Km"]
        assert km.derivation.settings["table"] == "km"
        assert km.derivation.rule.rule_id == "placeholder.motif_library"
        assert verify_bundle(tmp_path / "claims").ok
        assert "0 cited, 3 chosen, 2 placeholder, 0 refused, 1 computed" in result.out

    def test_claims_with_antimony_is_not_well_formed(self):
        out, err = io.StringIO(), io.StringIO()
        with pytest.raises(SystemExit) as raised, \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            main(["Michaelis Menten", "--antimony", "--claims", "x"])
        assert raised.value.code == 2
        assert "--export antimony --claims DIR" in err.getvalue()

    def test_an_empty_claims_directory_is_not_well_formed(self):
        out, err = io.StringIO(), io.StringIO()
        with pytest.raises(SystemExit) as raised, \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            main(["Michaelis Menten", "--claims", "  "])
        assert raised.value.code == 2
        assert "--claims needs a directory" in err.getvalue()

    def test_claims_and_export_are_allowed_together(self):
        parser = build_parser()
        args = parser.parse_args(["Michaelis Menten", "--export", "csv", "--claims", "dir"])
        check_request(parser, args)
        assert args.claims == "dir" and args.export == "csv"
