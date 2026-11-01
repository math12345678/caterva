"""The showcase bundle: the hexokinase claims, built offline, re-readable to the byte.

Built once per module with every network send made impossible; the bundle
is the one ADR 0179 shows and `caterva/tests/test_verify_mutations.py`
mutates.
"""
from __future__ import annotations

import hashlib
import json

import httpx
import pytest

from caterva.evidence import showcase
from caterva.evidence.bundle import read_bundle
from caterva.evidence.claims import ref_kind
from caterva.evidence.references import parse_reference_page, reference_url
from caterva.evidence.store import EvidenceStore


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


def claims_by_subject(bundle):
    return {c.subject.split(" = ")[0]: c for c in bundle.claims.values()}


class TestTheBundle:
    def test_the_root_is_a_computed_model_whose_inputs_include_km_and_kcat(self, built):
        out, root = built
        bundle = read_bundle(out)
        assert bundle.root == root
        model = bundle.get(root)
        assert model.kind == "computed"
        assert model.derivation.rule.rule_id == "compile.model"
        by = claims_by_subject(bundle)
        assert by["reaction_Km"].ref in model.derivation.inputs
        assert by["reaction_kcat"].ref in model.derivation.inputs
        assert by["reaction_S"].ref in model.derivation.inputs
        ir = "sha256:" + hashlib.sha256(b"michaelis_menten").hexdigest()
        assert model.derivation.settings["ir"] == ir
        assert f"ir:{ir}" in model.derivation.inputs
        assert "stand-in" in model.derivation.settings["ir_is"]
        assert model.value_text is None

    def test_the_km_claim_is_cited_from_the_six_mm_row_of_641068(self, built):
        out, _ = built
        bundle = read_bundle(out)
        km = claims_by_subject(bundle)["reaction_Km"]
        assert km.kind == "cited"
        assert km.subject == "reaction_Km = Km(2.7.1.1, D-glucose, Homo sapiens)"
        assert km.value_text == "6"
        assert km.unit == "mM"
        assert km.derivation.rule.rule_id == "select.resolver"
        assert km.derivation.rule.adr == "ADR 0047"
        (row_ref,) = km.derivation.inputs
        row = bundle.get(row_ref)
        assert row.reference == "641068"
        assert row.value_text == "6"
        assert row.commentary == "30°C, pH 7.5, wild-type"
        assert row.locator == "brenda:2.7.1.1:km:Homo sapiens:D-glucose:641068:6:0"
        assert [c.matched for c in km.derivation.certificates][:3] == ["641068", "6", "30°C, pH 7.5, wild-type"]

    def test_the_kcat_claim_is_cited_from_the_forty_point_one_row_of_739603(self, built):
        """The page holds 40.1 1/s for reference 739603, "wild-type, pH 7.6, 25 °C"."""
        out, _ = built
        bundle = read_bundle(out)
        kcat = claims_by_subject(bundle)["reaction_kcat"]
        assert kcat.value_text == "40.1"
        assert kcat.unit == "1/s"
        row = bundle.get(kcat.derivation.inputs[0])
        assert row.reference == "739603"
        assert row.commentary == "wild-type, pH 7.6, 25 °C"
        assert row.quantity == "kcat"

    def test_every_certificate_decodes_from_the_pinned_bytes(self, built):
        out, _ = built
        bundle = read_bundle(out)
        counted = 0
        for claim in bundle.claims.values():
            for certificate in claim.derivation.certificates:
                page = bundle.snapshot_bytes(certificate.snapshot)
                assert page[certificate.span[0]:certificate.span[1]].decode("utf-8") == certificate.matched
                counted += 1
        assert counted >= 6

    def test_the_enzyme_page_is_the_recorded_one_and_says_so(self, built):
        out, _ = built
        bundle = read_bundle(out)
        enzyme = [s for s in bundle.snapshots.values() if s.source == "brenda_enzyme"]
        assert len(enzyme) == 1
        assert enzyme[0].id == "sha256:3a69b492abcd7253b301d7a002f60d52a971ba9352a3a2559ec5f12f5060ef91"
        assert enzyme[0].locator == "https://www.brenda-enzymes.org/enzyme.php?ecno=2.7.1.1"
        assert enzyme[0].retrieved_at == "2026-09-28"
        assert enzyme[0].licence == "CC BY 4.0"
        assert enzyme[0].served_from == "Tests/fixtures/recorded/brenda_2.7.1.1.html.gz"

    def test_the_cited_papers_pages_travel_with_the_bundle(self, built):
        out, _ = built
        bundle = read_bundle(out)
        papers = {s.locator: s for s in bundle.snapshots.values() if s.source == "brenda_reference"}
        assert set(papers) == {reference_url("2.7.1.1", "641068"), reference_url("2.7.1.1", "739603")}
        found = parse_reference_page(bundle.snapshot_bytes(papers[reference_url("2.7.1.1", "641068")].ref).decode("utf-8"))
        assert found.pmid == "7730377"
        assert papers[reference_url("2.7.1.1", "641068")].retrieved_at == "2026-10-17"

    def test_the_ordinals_are_computed_and_name_the_frontier(self, built):
        out, _ = built
        bundle = read_bundle(out)
        km = claims_by_subject(bundle)["reaction_Km"]
        assert "dominance" not in km.derivation.settings
        ordinals = json.loads(km.derivation.settings["ordinals"])
        assert ordinals["chosen"] == {"assay_completeness": "2", "variant_statement": "2", "organism_match": "1"}
        assert set(ordinals["alternatives"]) == {"6.3 mM ref 739603"}
        kcat = claims_by_subject(bundle)["reaction_kcat"]
        alternatives = json.loads(kcat.derivation.settings["ordinals"])["alternatives"]
        assert set(alternatives) == {"60.4 1/s ref 703624", "74 1/s ref 702282", "101 1/s ref 702282"}

    def test_the_chosen_amount_cites_nothing(self, built):
        out, _ = built
        bundle = read_bundle(out)
        chosen = claims_by_subject(bundle)["reaction_S"]
        assert chosen.kind == "chosen"
        assert chosen.value_text == "1" and chosen.unit == "mM"
        assert chosen.derivation.inputs == ()
        assert chosen.derivation.rule.adr == "ADR 0044"

    def test_the_counts_per_kind(self, built):
        out, _ = built
        bundle = read_bundle(out)
        kinds = sorted(c.kind for c in bundle.claims.values())
        assert kinds == ["chosen", "cited", "cited", "computed"]
        assert len(bundle.rows) == 2
        assert len(bundle.snapshots) == 3
        assert all(ref_kind(r) == "row" for r in bundle.rows)

    def test_the_store_beside_the_bundle_holds_the_same_root(self, built):
        out, root = built
        store = EvidenceStore(out / "store")
        try:
            assert store.get(root) == read_bundle(out).get(root)
            assert len(store.dependents("snapshot:sha256:3a69b492abcd7253b301d7a002f60d52a971ba9352a3a2559ec5f12f5060ef91")) == 5
        finally:
            store.close()


class TestDeterminism:
    def test_two_builds_give_the_same_root_id(self, built, tmp_path):
        _, root = built
        again = showcase.showcase_bundle(tmp_path / "again")
        assert again == root
        assert read_bundle(tmp_path / "again").claims.keys() == read_bundle(built[0]).claims.keys()

    def test_the_root_is_a_claim_ref(self, built):
        _, root = built
        assert ref_kind(root) == "claim"
