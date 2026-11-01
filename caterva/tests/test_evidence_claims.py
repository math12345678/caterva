"""The claims data model: identity follows the derivation, and a record cannot lie about itself.

What is pinned here (ADR 0179):

  * canonical JSON has one spelling per value and refuses floats, so the
    independent checker can repeat the digest from the stored fields;
  * a claim's id is the same whatever order its settings were given in, and
    identical inputs give identical ids;
  * a changed value changes a cited claim's id but not a computed one's,
    because a cited value IS what was read and a computed value is held to a
    tolerance instead;
  * every construction invariant raises EvidenceRefused, and a record built
    from JSON with an id its fields do not produce is refused;
  * a constructed record cannot be changed in place, settings included, so
    it cannot come to hold an id its contents do not produce;
  * to_dict / from_dict round-trip every field.

The order-independence properties are Hypothesis tests over permutations of
the keys (derandomized, so a run is repeatable): the order a mapping was
built in is exactly the input nobody thinks to vary by hand.
"""
from __future__ import annotations

import copy
import json
import pickle

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from caterva.evidence import canonical
from caterva.evidence.claims import (
    CHOSEN_STARTING_AMOUNT,
    COMPILE_MODEL,
    KINDS,
    PARSE_BRENDA_TABLE,
    RULES,
    SELECT_RESOLVER,
    Certificate,
    Claim,
    Derivation,
    EvidenceRefused,
    Refusal,
    Row,
    RuleRef,
    Snapshot,
    claim_from_dict,
    claim_id,
    claim_identity,
    make_claim,
    make_ref,
    make_row,
    make_snapshot,
    now_utc,
    ordinals_json,
    ref_digest,
    ref_kind,
    row_from_dict,
    row_id,
    snapshot_from_dict,
    to_dict,
)

PAGE = (
    '<div id="tab12r4sr0" class="row rgrey2"><div id="tab12r4sr0c0" class="cell"><span>6\n</span>'
    '</div><div class="cell"><span>D-glucose\n</span></div><div class="cell"><span>Homo sapiens\n</span>'
    '</div><div class="cell"><span>30°C, pH 7.5, wild-type\n</span></div>'
    '<div class="cell"><span><a href="x">641068</a>\n</span></div></div>'
).encode()


def snapshot() -> Snapshot:
    return make_snapshot(
        PAGE, source="brenda_enzyme", locator="https://www.brenda-enzymes.org/enzyme.php?ecno=2.7.1.1",
        retrieved_at="2026-10-17T05:00:00Z", licence="CC BY 4.0", served_from=None,
    )


def row(snap: Snapshot | None = None, **overrides) -> Row:
    snap = snap or snapshot()
    fields = dict(
        snapshot=snap.ref, parser=PARSE_BRENDA_TABLE,
        locator="brenda:2.7.1.1:km:Homo sapiens:D-glucose:641068:6:0", quantity="km",
        value_text="6", unit="mM", substrate="D-glucose", organism="Homo sapiens", accession=None,
        commentary="30°C, pH 7.5, wild-type", reference="641068",
    )
    fields.update(overrides)
    return make_row(**fields)


def span_of(text: str) -> tuple[int, int]:
    at = PAGE.find(text.encode("utf-8"))
    assert at >= 0, text
    return at, at + len(text.encode("utf-8"))


def certificate(snap: Snapshot, text: str) -> Certificate:
    return Certificate(snap.ref, span_of(text), text)


def cited(settings: dict | None = None, **overrides) -> Claim:
    snap = snapshot()
    r = row(snap)
    derivation = Derivation(
        SELECT_RESOLVER, inputs=(r.ref,),
        certificates=(certificate(snap, "641068"), certificate(snap, "30°C, pH 7.5, wild-type")),
        settings=settings if settings is not None else {"ordinals": "{}", "unit_factor": "1"},
    )
    fields = dict(kind="cited", subject="reaction_Km = Km(2.7.1.1, D-glucose, Homo sapiens)",
                  value_text="6", unit="mM", tolerance=None, derivation=derivation)
    fields.update(overrides)
    return make_claim(**fields)


def computed(value_text: str | None = None, inputs: tuple = (), **overrides) -> Claim:
    km = cited()
    derivation = Derivation(COMPILE_MODEL, inputs=inputs or (km.ref, "ir:" + canonical.digest(b"model")),
                            settings={"ir": canonical.digest(b"model")})
    fields = dict(kind="computed", subject="model", value_text=value_text, unit=None, tolerance="1e-9",
                  derivation=derivation)
    fields.update(overrides)
    return make_claim(**fields)


# ---------------------------------------------------------------------------
# Canonical JSON
# ---------------------------------------------------------------------------

class TestCanonicalJson:
    def test_the_definition_is_the_one_the_checker_repeats(self):
        obj = {"b": [1, "two", None, True], "a": {"z": "°C", "y": "x"}}
        expected = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                              allow_nan=False).encode("utf-8")
        assert canonical.canonical_bytes(obj) == expected
        assert canonical.canonical_bytes(obj) == '{"a":{"y":"x","z":"°C"},"b":[1,"two",null,true]}'.encode()

    def test_a_float_is_refused_wherever_it_hides(self):
        with pytest.raises(TypeError, match="float"):
            canonical.canonical_bytes(6.0)
        with pytest.raises(TypeError, match=r"\$\.fields\.value is a float"):
            canonical.canonical_bytes({"fields": {"value": 6.0}})
        with pytest.raises(TypeError, match=r"\$\.inputs\[1\]"):
            canonical.canonical_bytes({"inputs": ["row:x", 0.1]})

    def test_a_key_that_is_not_a_string_is_refused(self):
        with pytest.raises(TypeError, match="not a string"):
            canonical.canonical_bytes({1: "one"})

    def test_integers_booleans_and_none_are_exact_and_allowed(self):
        assert canonical.canonical_bytes({"n": 1, "b": False, "x": None}) == b'{"b":false,"n":1,"x":null}'

    @given(st.permutations([f"k{i}" for i in range(12)]))
    @settings(max_examples=60, deadline=None, derandomize=True)
    def test_key_order_does_not_change_the_bytes(self, keys):
        reference = canonical.canonical_bytes({f"k{i}": {"inner": f"k{i}", "list": [f"k{i}", "v"]}
                                               for i in range(12)})
        shuffled = {k: {"list": [k, "v"], "inner": k} for k in keys}
        assert list(shuffled) == keys
        assert canonical.canonical_bytes(shuffled) == reference

    def test_digests_are_sha256_with_the_prefix(self):
        d = canonical.digest(b"abc")
        assert d == "sha256:ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
        assert canonical.is_digest(d)
        assert canonical.digest_hex(d) == d[len("sha256:"):]
        assert not canonical.is_digest("sha256:short")
        assert not canonical.is_digest("md5:" + "0" * 64)
        with pytest.raises(ValueError, match="not a digest"):
            canonical.digest_hex("nope")


# ---------------------------------------------------------------------------
# References and rules
# ---------------------------------------------------------------------------

class TestReferences:
    def test_a_reference_splits_into_kind_and_digest(self):
        d = canonical.digest(b"x")
        assert ref_kind(make_ref("row", d)) == "row"
        assert ref_digest(make_ref("claim", d)) == d
        assert ref_kind("ir:" + d) == "ir"

    @pytest.mark.parametrize("bad", ["row", "row:sha256:zz", "page:" + canonical.digest(b"x"), "", "sha256:" + "0" * 64])
    def test_anything_else_is_refused(self, bad):
        with pytest.raises(EvidenceRefused):
            ref_kind(bad)

    def test_the_rule_table_names_version_and_adr(self):
        assert RULES["select.resolver"] == RuleRef("select.resolver", 1, "ADR 0047")
        assert RULES["parse.brenda_table"].adr == "ADR 0179"
        assert RULES["placeholder.motif_library"].adr == "ADR 0013"
        assert RULES["chosen.starting_amount"].adr == "ADR 0044"
        assert RULES["compile.model"].adr == "ADR 0179"
        assert RULES["parse.brenda_reference"].version == 1
        assert len(RULES) == 6

    def test_a_rule_without_an_adr_or_a_version_is_refused(self):
        with pytest.raises(EvidenceRefused, match="ADR"):
            RuleRef("x", 1, "")
        with pytest.raises(EvidenceRefused, match="positive integer"):
            RuleRef("x", 0, "ADR 0179")
        with pytest.raises(EvidenceRefused, match="positive integer"):
            RuleRef("x", True, "ADR 0179")


# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------

class TestIdentity:
    def test_identical_inputs_give_identical_ids(self):
        assert cited().id == cited().id
        assert computed().id == computed().id

    def test_the_id_is_the_digest_of_the_identity_dict(self):
        claim = cited()
        assert claim.id == canonical.digest(canonical.canonical_bytes(claim_identity(claim)))
        assert claim_id(claim) == claim.id
        r = row()
        assert r.id == row_id(r)

    @given(st.permutations([f"setting_{i}" for i in range(8)]))
    @settings(max_examples=40, deadline=None, derandomize=True)
    def test_settings_key_order_does_not_change_the_id(self, keys):
        reference = cited(settings={f"setting_{i}": f"vsetting_{i}" for i in range(8)}).id
        assert cited(settings={k: f"v{k}" for k in keys}).id == reference

    def test_holding_settings_read_only_left_the_id_as_it_was(self):
        """The id `cited()` had while Derivation held its settings as a
        plain dict, computed by that code: the read-only view digests the
        same bytes, so no bundle written before it changes meaning."""
        assert cited().id == "sha256:feab84ae6c76683adc7fcddc338fa756e7197d7b6c3f26ad0a62b9c24b39948d"

    def test_a_changed_value_changes_a_cited_claims_id(self):
        assert cited(value_text="6").id != cited(value_text="6.3").id

    def test_a_changed_float_output_does_not_change_a_computed_claims_id(self):
        assert computed("0.3").id == computed("0.3000000001").id == computed(None).id
        assert "value_text" not in claim_identity(computed("0.3"))
        assert claim_identity(cited())["value_text"] == "6"

    def test_unit_tolerance_rule_version_inputs_and_certificates_are_in_the_id(self):
        base = cited()
        assert cited(unit="uM").id != base.id
        assert cited(tolerance="1e-9").id != base.id
        assert cited(subject="reaction_Km = Km(2.7.1.1, D-fructose, Homo sapiens)").id != base.id
        bumped = Derivation(RuleRef("select.resolver", 2, "ADR 0047"), base.derivation.inputs,
                            base.derivation.certificates, base.derivation.settings)
        assert cited(derivation=bumped).id != base.id
        fewer = Derivation(SELECT_RESOLVER, base.derivation.inputs, base.derivation.certificates[:1],
                           base.derivation.settings)
        assert cited(derivation=fewer).id != base.id

    def test_a_snapshots_id_is_the_digest_of_its_bytes_and_not_its_date(self):
        a = snapshot()
        b = make_snapshot(PAGE, source="brenda_enzyme", locator=a.locator, retrieved_at="2026-10-18T00:00:00Z",
                          licence="CC BY 4.0", served_from="Tests/fixtures/recorded/x.gz")
        assert a.id == b.id == canonical.digest(PAGE)
        assert a.ref.startswith("snapshot:sha256:")

    def test_now_utc_is_iso_8601_utc(self):
        stamp = now_utc()
        assert len(stamp) == 20
        assert stamp.endswith("Z")
        assert stamp[10] == "T"


# ---------------------------------------------------------------------------
# Invariants
# ---------------------------------------------------------------------------

class TestInvariants:
    def test_the_kinds_are_the_five_of_the_plan(self):
        assert KINDS == ("cited", "chosen", "placeholder", "refused", "computed")
        with pytest.raises(EvidenceRefused, match="kind"):
            cited(kind="asserted")

    def test_a_cited_claim_needs_exactly_one_row_input(self):
        snap = snapshot()
        r = row(snap)
        certs = (certificate(snap, "641068"),)
        with pytest.raises(EvidenceRefused, match="exactly one input"):
            make_claim("cited", "x", "6", "mM", None, Derivation(SELECT_RESOLVER, (), certs))
        with pytest.raises(EvidenceRefused, match="exactly one input"):
            make_claim("cited", "x", "6", "mM", None, Derivation(SELECT_RESOLVER, (r.ref, r.ref), certs))
        other = cited()
        with pytest.raises(EvidenceRefused, match="exactly one input"):
            make_claim("cited", "x", "6", "mM", None, Derivation(SELECT_RESOLVER, (other.ref,), certs))

    def test_a_cited_claim_needs_a_certificate(self):
        r = row()
        with pytest.raises(EvidenceRefused, match="certificate"):
            make_claim("cited", "x", "6", "mM", None, Derivation(SELECT_RESOLVER, (r.ref,), ()))

    def test_a_cited_claim_carries_its_value(self):
        with pytest.raises(EvidenceRefused, match="carries the value"):
            cited(value_text=None)

    def test_a_placeholder_cites_no_row_and_names_its_table(self):
        r = row()
        rule = RULES["placeholder.motif_library"]
        with pytest.raises(EvidenceRefused, match="cites no row"):
            make_claim("placeholder", "x", "1", "mM", None, Derivation(rule, (r.ref,), (), {"table": "km"}))
        with pytest.raises(EvidenceRefused, match='settings\\["table"\\]'):
            make_claim("placeholder", "x", "1", "mM", None, Derivation(rule, (), (), {}))
        ok = make_claim("placeholder", "x", "1", "mM", None, Derivation(rule, (), (), {"table": "none"}))
        assert ok.kind == "placeholder"

    def test_a_chosen_value_cites_no_row(self):
        r = row()
        with pytest.raises(EvidenceRefused, match="cites no row"):
            make_claim("chosen", "x", "1", "mM", None, Derivation(CHOSEN_STARTING_AMOUNT, (r.ref,)))
        ok = make_claim("chosen", "x", "1", "mM", None, Derivation(CHOSEN_STARTING_AMOUNT))
        assert ok.value_text == "1"

    def test_a_refusal_is_a_claim_with_a_refusal_and_no_value(self):
        r = row()
        refusal = Refusal("Km(2.7.1.1, D-glucose, Homo sapiens)", "row_not_found_on_pinned_page",
                          (f"{r.ref} | value 18 is not 6",))
        with pytest.raises(EvidenceRefused, match="carries its Refusal"):
            make_claim("refused", "x", None, None, None, Derivation(SELECT_RESOLVER))
        with pytest.raises(EvidenceRefused, match="no value"):
            make_claim("refused", "x", "6", None, None, Derivation(SELECT_RESOLVER), refusal)
        with pytest.raises(EvidenceRefused, match="only a refused claim"):
            cited(refusal=refusal)
        ok = make_claim("refused", "x", None, None, None, Derivation(SELECT_RESOLVER), refusal)
        assert ok.refusal.candidates[0].startswith("row:sha256:")
        assert "refusal" in claim_identity(ok)

    def test_a_computed_claim_has_an_input(self):
        with pytest.raises(EvidenceRefused, match="at least one input"):
            make_claim("computed", "model", None, None, None, Derivation(COMPILE_MODEL))

    def test_settings_are_strings_only(self):
        with pytest.raises(EvidenceRefused, match="strings only"):
            Derivation(SELECT_RESOLVER, settings={"unit_factor": 1})
        with pytest.raises(EvidenceRefused, match="strings only"):
            Derivation(SELECT_RESOLVER, settings={"ordinals": {"a": "1"}})

    def test_a_value_text_must_be_a_finite_decimal_string(self):
        for bad in ("6.0e", "", "nan", "inf", "six"):
            with pytest.raises(EvidenceRefused):
                cited(value_text=bad)
        with pytest.raises(EvidenceRefused):
            row(value_text="abc")
        with pytest.raises(EvidenceRefused):
            cited(tolerance="loose")

    def test_a_certificate_span_must_cover_its_text(self):
        snap = snapshot()
        start, end = span_of("641068")
        with pytest.raises(EvidenceRefused, match="covers"):
            Certificate(snap.ref, (start, end + 1), "641068")
        with pytest.raises(EvidenceRefused, match="end > start"):
            Certificate(snap.ref, (end, start), "641068")
        with pytest.raises(EvidenceRefused, match="snapshot ref"):
            Certificate(row().ref, (start, end), "641068")
        ok = Certificate(snap.ref, [start, end], "641068")
        assert ok.span == (start, end)

    def test_a_record_cannot_hold_a_lying_id(self):
        claim = cited()
        with pytest.raises(EvidenceRefused, match="not the digest"):
            Claim(id=canonical.digest(b"lie"), kind=claim.kind, subject=claim.subject,
                  value_text=claim.value_text, unit=claim.unit, tolerance=claim.tolerance,
                  derivation=claim.derivation)
        r = row()
        with pytest.raises(EvidenceRefused, match="not the digest"):
            Row(id=canonical.digest(b"lie"), snapshot=r.snapshot, parser=r.parser, locator=r.locator,
                quantity=r.quantity, value_text=r.value_text, unit=r.unit, substrate=r.substrate,
                organism=r.organism)
        with pytest.raises(EvidenceRefused, match="not a digest"):
            Snapshot(id="nope", source="brenda_enzyme", locator="u", retrieved_at="t", licence="l")

    def test_a_claims_settings_cannot_be_changed_in_place(self):
        """A frozen dataclass stops `derivation.settings = ...`; a dict
        inside it did not stop `settings["k"] = ...`, after which the claim
        held an id its contents no longer produced, and nothing refused it."""
        claim = cited(settings={"ordinals": "{}", "unit_factor": "1"})
        with pytest.raises(TypeError):
            claim.derivation.settings["unit_factor"] = "1000"  # type: ignore[index]
        with pytest.raises(TypeError):
            del claim.derivation.settings["ordinals"]  # type: ignore[attr-defined]
        assert not hasattr(claim.derivation.settings, "update")
        assert claim.id == claim_id(claim)
        assert dict(claim.derivation.settings) == {"ordinals": "{}", "unit_factor": "1"}

    def test_the_callers_dict_changed_afterwards_does_not_reach_the_claim(self):
        given_settings = {"ordinals": "{}", "unit_factor": "1"}
        claim = cited(settings=given_settings)
        given_settings["unit_factor"] = "1000"
        assert claim.derivation.settings["unit_factor"] == "1"
        assert claim.id == claim_id(claim)

    def test_a_claim_still_copies_and_pickles_with_its_settings_still_read_only(self):
        claim = cited()
        for twin in (copy.deepcopy(claim), copy.copy(claim), pickle.loads(pickle.dumps(claim))):
            assert twin == claim
            assert twin.id == claim_id(twin)
            with pytest.raises(TypeError):
                twin.derivation.settings["unit_factor"] = "1000"  # type: ignore[index]

    def test_a_row_names_a_known_quantity_and_a_snapshot(self):
        with pytest.raises(EvidenceRefused, match="quantity"):
            row(quantity="vmax")
        with pytest.raises(EvidenceRefused, match="snapshot ref"):
            row(snapshot=cited().ref)
        with pytest.raises(EvidenceRefused, match="source"):
            make_snapshot(b"x", source="wikipedia", locator="u", retrieved_at="t", licence="l")
        with pytest.raises(EvidenceRefused, match="bytes"):
            make_snapshot("text", source="brenda_enzyme", locator="u", retrieved_at="t", licence="l")


# ---------------------------------------------------------------------------
# Serialisation
# ---------------------------------------------------------------------------

class TestSerialisation:
    def test_a_claim_round_trips_through_plain_json(self):
        claim = cited()
        data = json.loads(json.dumps(to_dict(claim)))
        assert claim_from_dict(data) == claim
        assert data["derivation"]["certificates"][0]["span"] == list(claim.derivation.certificates[0].span)
        assert data["derivation"]["rule"] == {"rule_id": "select.resolver", "version": 1, "adr": "ADR 0047"}

    def test_a_refused_claim_round_trips(self):
        r = row()
        refusal = Refusal("x", "row_not_found_on_pinned_page", (f"{r.ref} | value 18 is not 6",))
        claim = make_claim("refused", "x", None, None, None, Derivation(SELECT_RESOLVER), refusal)
        assert claim_from_dict(json.loads(json.dumps(to_dict(claim)))) == claim

    def test_rows_and_snapshots_round_trip(self):
        r = row()
        assert row_from_dict(json.loads(json.dumps(to_dict(r)))) == r
        s = snapshot()
        assert snapshot_from_dict(json.loads(json.dumps(to_dict(s)))) == s

    def test_a_tampered_record_is_refused_on_reading(self):
        data = to_dict(cited())
        data["value_text"] = "60"
        with pytest.raises(EvidenceRefused, match="not the digest"):
            claim_from_dict(data)
        data = to_dict(row())
        data["reference"] = "641067"
        with pytest.raises(EvidenceRefused, match="not the digest"):
            row_from_dict(data)

    def test_a_record_missing_a_field_is_refused_as_not_a_record(self):
        with pytest.raises(EvidenceRefused, match="not a claim record"):
            claim_from_dict({"id": "x"})
        with pytest.raises(EvidenceRefused, match="not a row record"):
            row_from_dict({"id": "x"})
        with pytest.raises(EvidenceRefused, match="not a snapshot record"):
            snapshot_from_dict({"id": "x"})


class TestOrdinalsJson:
    def test_the_text_has_one_spelling_and_strings_only(self):
        text = ordinals_json({"organism_match": "1", "assay_completeness": "2"},
                             {"6.3 mM ref 739603": {"assay_completeness": "2", "organism_match": None}})
        assert text == ('{"alternatives":{"6.3 mM ref 739603":{"assay_completeness":"2","organism_match":null}},'
                        '"chosen":{"assay_completeness":"2","organism_match":"1"}}')
        with pytest.raises(EvidenceRefused, match="decimal string"):
            ordinals_json({"assay_completeness": 2}, {})
        with pytest.raises(EvidenceRefused, match="decimal string"):
            ordinals_json({}, {"a": {"assay_completeness": 2}})
