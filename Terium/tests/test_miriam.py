"""Minting identifiers.org URIs, and — the point of the module — refusing to.

The assertions that matter here are the refusals. A MIRIAM URI is a promise
that the accession resolves; minting one for something that does not is
worse than adding no annotation, because "machine-actionable" is exactly the
property that stops anyone checking it by hand.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from Terium.core.miriam import (
    MINTABLE,
    NAMESPACES,
    PATTERNS_CAPTURED_ON,
    identifiers_in,
    mint,
)

FIXTURE = (
    Path(__file__).resolve().parent.parent.parent
    / "Tests"
    / "fixtures"
    / "identifiers"
    / "identifiers_org_namespaces.json"
)


class TestTheBrendaTrap:
    """The case that justifies the whole module.

    BRENDA *has* an identifiers.org namespace, so the natural thing is to
    write `https://identifiers.org/brenda:649716` and move on. The registry
    says that namespace covers EC NUMBERS, sample id `1.1.1.1`. A BRENDA
    reference id matches nothing in it.
    """

    def test_a_brenda_reference_id_gets_no_uri(self):
        result = mint("brenda", "649716")
        assert not result.minted
        assert result.uri is None
        assert "EC numbers" in result.reason
        assert "reference ids" in result.reason

    def test_brenda_is_not_mintable_even_for_an_ec_number(self):
        # An EC number DOES match brenda's pattern. It is still refused,
        # because the only BRENDA accession Terrium holds is a reference
        # id, and a function that accepts both would hand a caller a URI
        # for one and silence for the other with no way to tell which.
        # EC numbers go through `ec-code`, which is what SBML annotators
        # expect anyway.
        assert "brenda" not in MINTABLE
        assert not mint("brenda", "1.1.1.1").minted

    def test_a_brenda_citation_string_yields_no_identifiers(self):
        assert identifiers_in("BRENDA ref 649716") == []


class TestRefusals:
    def test_a_malformed_pubmed_id_is_refused_with_a_sample(self):
        result = mint("pubmed", "not-a-number")
        assert not result.minted
        assert "16333295" in result.reason  # the registry's own sample
        assert "does not resolve" in result.reason

    def test_an_unknown_namespace_is_refused(self):
        result = mint("uniprot", "P00338")
        assert not result.minted
        assert "uniprot" in result.reason

    def test_an_empty_accession_is_refused_rather_than_minted_as_a_bare_prefix(self):
        # `https://identifiers.org/pubmed:` is a URL. It is not a citation.
        result = mint("pubmed", "")
        assert not result.minted
        assert result.uri is None

    def test_a_partial_ec_number_is_refused(self):
        # `1.1` is not an EC number. `1.1.-.-` is.
        assert not mint("ec-code", "1.1").minted
        assert mint("ec-code", "1.1.-.-").minted


class TestSuccesses:
    @pytest.mark.parametrize(
        "prefix,accession,expected",
        [
            ("pubmed", "12345678", "https://identifiers.org/pubmed:12345678"),
            ("taxonomy", "9606", "https://identifiers.org/taxonomy:9606"),
            ("ec-code", "1.1.1.27", "https://identifiers.org/ec-code:1.1.1.27"),
            ("ec-code", "1.1.1.n1", "https://identifiers.org/ec-code:1.1.1.n1"),
            ("doi", "10.1038/nbt1156", "https://identifiers.org/doi:10.1038/nbt1156"),
        ],
    )
    def test_well_formed_accessions_mint(self, prefix, accession, expected):
        assert mint(prefix, accession).uri == expected

    #: Namespaces whose registry entry contradicts itself, and how.
    #:
    #: Not a transcription error on our side -- checked against the live
    #: registry on 2026-08-28. identifiers.org publishes ECO with
    #: `pattern: ^ECO:\d{7}$` and `sampleId: 0000006`, and the sample does
    #: not match the pattern. The pattern is the one that is right: the
    #: published sample 404s and the pattern-conforming form resolves.
    #:
    #:     https://identifiers.org/eco/0000006       -> 404
    #:     https://identifiers.org/eco/ECO:0000006   -> 200
    #:
    #: The fixture keeps the registry's value verbatim. It is a CAPTURE, and
    #: editing it to be self-consistent would turn a record of what the
    #: registry says into a record of what we wish it said -- while quietly
    #: destroying the evidence for this exemption.
    _REGISTRY_SAMPLE_IS_INCONSISTENT = {
        "eco": "sampleId omits the ECO: prefix its own pattern requires",
    }

    def test_every_registry_sample_id_mints_in_its_own_namespace(self):
        # The registry publishes a sample for each namespace. If Terrium
        # cannot mint the registry's own example, Terrium's copy of the
        # pattern is wrong — this catches a transcription error in the
        # fixture without needing the network.
        for prefix in MINTABLE:
            sample = NAMESPACES[prefix].sample_id
            if prefix in self._REGISTRY_SAMPLE_IS_INCONSISTENT:
                # Asserted in the OTHER direction, so the exemption cannot
                # become a blind spot: the sample must still be rejected for
                # the documented reason. If the registry fixes its entry
                # this fails, and the exemption should then go.
                assert not mint(prefix, sample).minted, (
                    f"{prefix}'s sample now mints; the registry may have "
                    f"corrected its entry, so remove the exemption "
                    f"({self._REGISTRY_SAMPLE_IS_INCONSISTENT[prefix]})"
                )
                continue
            assert mint(prefix, sample).minted, f"{prefix} rejects its own sample {sample}"


class TestExtractionFromFreeText:
    """Citations arrive as human strings, because that is what resolvers emit."""

    def test_finds_a_pmid_in_several_spellings(self):
        for text in ["PMID 12345678", "pmid:12345678", "PubMed 12345678"]:
            assert identifiers_in(text) == [("pubmed", "12345678")], text

    def test_trailing_sentence_punctuation_is_not_part_of_the_doi(self):
        # `10.1038/nbt1156.` is a real DOI followed by a full stop.
        assert identifiers_in("See doi 10.1038/nbt1156.") == [
            ("doi", "10.1038/nbt1156")
        ]

    def test_the_same_identifier_named_twice_is_emitted_once(self):
        # Duplicate CVTerms are legal SBML and make a reader wonder which
        # is authoritative.
        assert identifiers_in("PMID 999; see also PMID 999") == [("pubmed", "999")]

    def test_a_mixed_citation_yields_both(self):
        found = identifiers_in("BRENDA ref 649716; PMID 12345678")
        assert found == [("pubmed", "12345678")]

    def test_empty_input_is_not_an_error(self):
        assert identifiers_in("") == []


class TestTheCaptureIsHonestAboutItsAge:
    def test_the_fixture_records_when_it_was_captured(self):
        # A pattern copied from a registry with no date is a pattern nobody
        # can tell is stale. Same discipline as the golden set.
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", PATTERNS_CAPTURED_ON)

    def test_the_module_and_the_fixture_cannot_drift(self):
        # The module reads the fixture at import rather than holding its own
        # copy of the patterns. Asserting it here means a future refactor
        # that inlines "just the defaults" fails this test.
        raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
        assert set(raw["namespaces"]) == set(NAMESPACES)
        for prefix, spec in raw["namespaces"].items():
            assert NAMESPACES[prefix].pattern.pattern == spec["pattern"]

    def test_the_fixture_explains_the_brenda_trap_to_the_next_reader(self):
        raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
        assert "649716" in raw["_why"], "the cautionary case must stay written down"