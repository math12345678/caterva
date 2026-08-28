"""Provenance has to survive leaving Terrium, or it did not happen.

The first test in this file is the one that motivates the module: it
demonstrates the loss rather than asserting the fix. Antimony comments —
Sauro's mechanism, and the right one for a file a person reads — are
deleted wholesale by translation to SBML, which is the format every other
tool actually consumes.
"""

from __future__ import annotations

import pathlib

import antimony
import libsbml
import pytest

from Terium.core.model_provenance import ParameterProvenance, annotate_antimony
from Terium.core.sbml_provenance import (
    SbmlParameterProvenance,
    annotate_sbml,
    audit_annotations,
    cross_species_parameters,
    read_back,
)

PLAIN_MODEL = """model michaelis_menten
  S = 10; P = 0;
  Km = 2.5;
  Vmax = 0.25;
  J0: S -> P; Vmax * S / (Km + S);
end"""


def to_sbml(antimony_text: str) -> str:
    antimony.clearPreviousLoads()
    assert antimony.loadAntimonyString(antimony_text) >= 0, antimony.getLastError()
    return antimony.getSBMLString(antimony.getMainModuleName())


def identity_uris(sbml_text: str) -> dict[str, list[str]]:
    """`read_back`, minus the evidence class.

    Two different kinds of annotation ride on the same parameter and
    `read_back` is qualifier-blind, so it returns both:

      identity  -- WHICH paper, WHICH organism (pubmed, doi, taxonomy)
      evidence  -- HOW the value is known (an ECO term)

    The tests below are about the first. Asserting on the union made them
    fail the moment the second was added (ADR 0187), which is not a defect
    they were written to detect. Separating the categories is a narrowing of
    scope, not a weakening: `test_a_resolved_parameter_carries_an_evidence_code`
    asserts the evidence term directly, so nothing here stops watching it.
    """
    return {
        name: [u for u in uris if "identifiers.org/eco/" not in u]
        for name, uris in read_back(sbml_text).items()
    }

@pytest.fixture
def base_sbml() -> str:
    return to_sbml(PLAIN_MODEL)


def test_antimony_comments_do_not_survive_translation_to_sbml():
    """The measurement this module was built on.

    Kept as a test, not a comment, because it is the entire justification
    for the module existing. If a future Antimony gains comment-preserving
    translation this test fails, and the right response is to re-examine
    whether the SBML annotator is still needed — not to delete the test.

    IT FAILED, AND THE RE-EXAMINATION IS BELOW
    ------------------------------------------
    It fired on 2026-08-25, and the cause was not a change in Antimony. It
    was ADR 0182: `annotate_antimony` now emits a `notes` statement beside
    each comment, and notes DO survive translation — so the strings this
    test watched for started arriving in the SBML by a route it did not
    know about.

    The premise is intact. Comments are still discarded; the module was
    never built on "provenance cannot reach SBML from Antimony", it was
    built on "comments cannot". So the test now uses a plain comment rather
    than the annotator's output, which measures the stated claim instead of
    a by-product of how the annotator happens to be written today.

    Is the SBML annotator still needed? Yes, and for a reason notes cannot
    address. A note is prose. `annotate_sbml` writes CVTerms — a PubMed
    identifier as a resolvable URI under `bqbiol:isDescribedBy`, a taxon
    under `bqbiol:hasTaxon` — which is what lets a consumer follow a
    citation rather than read one. Frank Bergmann's advice (ADR 0181) is
    exactly this split: identifiers in CVTerms, prose in notes. Notes made
    the human-readable half durable; they did not make it machine-readable.
    """
    sbml = to_sbml(
        PLAIN_MODEL.replace(
            "  Km = 2.5;",
            "  Km = 2.5;  // BRENDA ref 649716, Homo sapiens",
        )
    )
    for lost in ("BRENDA", "649716", "Homo sapiens"):
        assert lost not in sbml, (
            f"{lost!r} survived into SBML; this module's premise may no longer hold"
        )


def test_a_note_reaches_sbml_where_a_comment_does_not():
    """The other half, so the pair says something the first cannot alone.

    Without this, the test above passes on a translator that dropped
    everything, and would keep passing if `annotate_antimony`'s notes
    silently stopped being emitted — which is the failure ADR 0182 exists
    to prevent, going unnoticed in the file that documents the loss.
    """
    annotated = annotate_antimony(
        PLAIN_MODEL,
        {
            "Km": ParameterProvenance(
                origin="resolved",
                citation="BRENDA ref 649716",
                organism="Homo sapiens",
            )
        },
    )
    sbml = to_sbml(annotated.text)
    for kept in ("649716", "Homo sapiens"):
        assert kept in sbml, (
            f"{kept!r} did not reach SBML; the Antimony notes of ADR 0182 "
            f"are not being emitted or are no longer surviving translation"
        )


class TestWhatSurvives:
    def test_a_pmid_becomes_a_resolvable_annotation(self, base_sbml):
        out = annotate_sbml(
            base_sbml,
            {"km": SbmlParameterProvenance(origin="resolved", citation="PMID 12345678")},
        )
        assert identity_uris(out.sbml)["Km"] == ["https://identifiers.org/pubmed:12345678"]

    def test_a_taxon_is_annotated_only_when_it_was_actually_resolved(self, base_sbml):
        # An organism NAME is not an identifier. Deriving taxonomy:9606 from
        # the string "Homo sapiens" would make the model assert a taxon
        # nobody looked up.
        without = annotate_sbml(
            base_sbml,
            {"km": SbmlParameterProvenance(origin="resolved", organism="Homo sapiens")},
        )
        assert identity_uris(without.sbml)["Km"] == []

        with_id = annotate_sbml(
            base_sbml,
            {
                "km": SbmlParameterProvenance(
                    origin="resolved", organism="Homo sapiens", taxon_id="9606"
                )
            },
        )
        assert "https://identifiers.org/taxonomy:9606" in read_back(with_id.sbml)["Km"]

    def test_the_annotated_model_still_integrates(self, base_sbml):
        # An annotation that breaks the model is not an improvement. This
        # runs the real engine on the annotated document.
        roadrunner = pytest.importorskip("roadrunner")
        out = annotate_sbml(
            base_sbml,
            {"km": SbmlParameterProvenance(origin="resolved", citation="PMID 12345678")},
            ec_number="1.1.1.27",
            model_taxon_id="9606",
        )
        result = roadrunner.RoadRunner(out.sbml).simulate(0, 5, 6)
        assert result[0][1] == pytest.approx(10.0)
        assert result[-1][1] < 10.0  # substrate is consumed

    def test_the_annotated_document_has_no_libsbml_errors(self, base_sbml):
        out = annotate_sbml(
            base_sbml,
            {"km": SbmlParameterProvenance(origin="resolved", citation="PMID 12345678")},
            ec_number="1.1.1.27",
        )
        document = libsbml.readSBMLFromString(out.sbml)
        document.checkConsistency()
        fatal = [
            document.getError(i).getMessage()
            for i in range(document.getNumErrors())
            if document.getError(i).getSeverity() >= libsbml.LIBSBML_SEV_ERROR
        ]
        assert fatal == []


class TestWhatIsRefusedRatherThanFaked:
    def test_a_brenda_reference_travels_as_text_and_is_reported_as_such(self, base_sbml):
        out = annotate_sbml(
            base_sbml,
            {
                "km": SbmlParameterProvenance(
                    origin="resolved", citation="BRENDA ref 649716"
                )
            },
        )
        # No fabricated URI...
        assert identity_uris(out.sbml)["Km"] == []
        assert "identifiers.org/brenda" not in out.sbml
        # ...but the reference is not lost either.
        assert "649716" in out.sbml
        # ...and the caller is told, rather than left to infer it from an
        # absence.
        assert any("649716" in accession for _, accession, _ in out.refused_uris)

    def test_a_parameter_with_no_provenance_is_marked_not_left_blank(self, base_sbml):
        out = annotate_sbml(base_sbml, {})
        assert sorted(out.unannotated) == ["Km", "Vmax"]
        assert "NO PROVENANCE RECORDED" in out.sbml

    def test_keys_differing_only_by_case_are_refused_not_guessed(self, base_sbml):
        # SBML ids are case-sensitive. Folding `km` and `Km` together would
        # attach one value's source to another parameter, which is the
        # precise failure this module exists to prevent.
        with pytest.raises(ValueError, match="case-sensitive"):
            annotate_sbml(
                base_sbml,
                {
                    "km": SbmlParameterProvenance(origin="resolved", citation="PMID 1"),
                    "KM": SbmlParameterProvenance(origin="resolved", citation="PMID 2"),
                },
            )

    def test_unparseable_input_raises_rather_than_returning_it_unchanged(self):
        # Returning the input would let a caller write an unannotated file
        # believing it annotated.
        with pytest.raises(ValueError):
            annotate_sbml("<not-sbml/>", {})


class TestCrossSpeciesIsMachineDetectable:
    """The warning has to survive being processed by something that never
    shows notes to a human."""

    def _annotated(self, base_sbml, *, model_taxon):
        return annotate_sbml(
            base_sbml,
            {
                "km": SbmlParameterProvenance(
                    origin="resolved", organism="Homo sapiens", taxon_id="9606"
                ),
                "vmax": SbmlParameterProvenance(
                    origin="resolved",
                    organism="Oryctolagus cuniculus",
                    taxon_id="9986",
                    cross_species=True,
                ),
            },
            model_taxon_id=model_taxon,
        )

    def test_a_mismatched_taxon_is_found_from_the_file_alone(self, base_sbml):
        out = self._annotated(base_sbml, model_taxon="9606")
        mismatches = cross_species_parameters(out.sbml)
        assert [name for name, _, _ in mismatches] == ["Vmax"]
        assert mismatches[0][1] == "https://identifiers.org/taxonomy:9986"
        assert mismatches[0][2] == "https://identifiers.org/taxonomy:9606"

    def test_the_matching_parameter_is_not_flagged(self, base_sbml):
        out = self._annotated(base_sbml, model_taxon="9606")
        assert "Km" not in [name for name, _, _ in cross_species_parameters(out.sbml)]

    def test_no_model_taxon_means_the_question_was_not_asked(self, base_sbml):
        # Empty must NOT be read as "nothing is cross-species". The
        # docstring says so; this pins it, because the difference between
        # "checked and clean" and "never checked" is the distinction this
        # whole codebase is organised around.
        out = self._annotated(base_sbml, model_taxon=None)
        assert cross_species_parameters(out.sbml) == []
        # The prose warning is still present, so the fact is not lost —
        # only the machine-readable form is absent.
        assert "CROSS-SPECIES" in out.sbml

    def test_the_prose_warning_is_present_alongside_the_structure(self, base_sbml):
        out = self._annotated(base_sbml, model_taxon="9606")
        assert "CROSS-SPECIES" in out.sbml
        assert "not a measurement of your organism" in out.sbml


class TestNotesCarryWhatRdfCannot:
    def test_a_user_supplied_value_says_it_is_not_literature(self, base_sbml):
        out = annotate_sbml(
            base_sbml, {"km": SbmlParameterProvenance(origin="user", note="you typed this")}
        )
        assert "Supplied by the user" in out.sbml
        assert "Not a literature value" in out.sbml

    def test_a_user_citation_is_not_dressed_as_a_verified_one(self, base_sbml):
        out = annotate_sbml(
            base_sbml,
            {
                "km": SbmlParameterProvenance(
                    origin="user_cited", citation="Smith 2019"
                )
            },
        )
        assert "unverified by Terrium" in out.sbml

    def test_reliability_axes_are_listed_separately_not_totalled(self, base_sbml):
        out = annotate_sbml(
            base_sbml,
            {
                "km": SbmlParameterProvenance(
                    origin="resolved",
                    reliability=(
                        ("assay completeness", "complete", "Reports pH and temperature."),
                        ("organism match", "exact", "Measured in the organism asked about."),
                    ),
                )
            },
        )
        assert "assay completeness: complete" in out.sbml
        assert "organism match: exact" in out.sbml
        assert "not commensurable" in out.sbml
        # The REASON travels too. A grade is a token; the reason is the
        # sentence someone learns from, and it was being dropped here.
        assert "Reports pH and temperature." in out.sbml
        assert "Measured in the organism asked about." in out.sbml

    def test_notes_containing_xml_metacharacters_do_not_break_the_document(self, base_sbml):
        # Citations are free text from external sources. `Smith & Jones
        # <1999>` must not produce an unparseable file.
        out = annotate_sbml(
            base_sbml,
            {"km": SbmlParameterProvenance(origin="resolved", citation="Smith & Jones <1999>")},
        )
        document = libsbml.readSBMLFromString(out.sbml)
        assert document.getModel() is not None
        assert "Smith &amp; Jones" in out.sbml


class TestStructuredIdentifiersBeatReparsingProse:
    """The defect the first end-to-end run exposed.

    Unit tests fed the annotator `"PubMed 12345678"`. The CLI actually
    formats `"PubMed ref 12345678"`. The free-text pattern allowed four
    non-digit characters between the registry name and the number; `" ref "`
    is five. Result: a real CLI run wrote **zero** MIRIAM annotations while
    every unit test passed.

    The fix is not a wider regex. It is to stop re-deriving identifiers from
    a string Terrium itself formatted, and pass the structured fields the
    caller already split out.
    """

    def test_structured_fields_are_used_in_preference_to_the_text(self, base_sbml):
        out = annotate_sbml(
            base_sbml,
            {
                "km": SbmlParameterProvenance(
                    origin="resolved",
                    citation="PubMed ref 12345678",
                    citation_source="PubMed",
                    reference_id="12345678",
                )
            },
        )
        assert identity_uris(out.sbml)["Km"] == ["https://identifiers.org/pubmed:12345678"]

    def test_the_exact_string_the_cli_formats_is_handled(self, base_sbml):
        # Belt and braces: even WITHOUT the structured fields, the spelling
        # the CLI actually produces must not silently yield nothing.
        out = annotate_sbml(
            base_sbml,
            {"km": SbmlParameterProvenance(origin="resolved", citation="PubMed ref 12345678")},
        )
        assert identity_uris(out.sbml)["Km"] == ["https://identifiers.org/pubmed:12345678"]

    def test_a_brenda_registry_still_yields_no_uri_through_the_structured_path(
        self, base_sbml
    ):
        # The structured path must not become a way to smuggle in a
        # namespace the registry does not support.
        out = annotate_sbml(
            base_sbml,
            {
                "km": SbmlParameterProvenance(
                    origin="resolved",
                    citation="BRENDA ref 649716",
                    citation_source="BRENDA",
                    reference_id="649716",
                )
            },
        )
        assert identity_uris(out.sbml)["Km"] == []
        assert "identifiers.org/brenda" not in out.sbml

    def test_an_unknown_registry_falls_back_to_scanning_the_text(self, base_sbml):
        # A registry Terrium does not map, whose citation still names a PMID.
        # Returning nothing here would lose a real, resolvable identifier.
        out = annotate_sbml(
            base_sbml,
            {
                "km": SbmlParameterProvenance(
                    origin="resolved",
                    citation="SABIO-RK entry 42, from PMID 12345678",
                    citation_source="SABIO-RK",
                    reference_id="42",
                )
            },
        )
        assert identity_uris(out.sbml)["Km"] == ["https://identifiers.org/pubmed:12345678"]


class TestAnIndependentReaderCanUseTheAnnotations:
    """`read_back()` is libSBML reading libSBML. This is not.

    The whole reason for writing MIRIAM rather than something
    Terrium-shaped is that other tools read it. Verifying the writer with
    the matching reader from the same library establishes that the round
    trip is self-consistent and nothing about whether anyone else can use
    the file — the parity-test failure, applied to a dependency instead of
    to two of our own implementations.
    """

    def test_an_independent_parse_finds_the_expected_triples(self, base_sbml):
        out = annotate_sbml(
            base_sbml,
            {
                "km": SbmlParameterProvenance(
                    origin="resolved",
                    citation="PMID 12345678",
                    organism="Homo sapiens",
                    taxon_id="9606",
                )
            },
            model_taxon_id="9606",
        )
        audit = audit_annotations(out.sbml)
        assert audit.ok, audit.problems

        by_owner = {(owner, qualifier) for owner, qualifier, _ in audit.triples}
        assert ("Km", "isDescribedBy") in by_owner
        assert ("Km", "hasTaxon") in by_owner

    def test_orphaned_rdf_is_caught_where_libsbml_says_nothing(self, base_sbml):
        """The measured blind spot.

        An `rdf:about` naming a metaid no element carries is dropped
        silently by `read_back()`, and `checkConsistency()` reports **zero**
        errors. Measured, not assumed — the numbers are in the pass notes.
        So the guard the other tests lean on cannot see an annotation that
        has come unmoored from what it describes.
        """
        out = annotate_sbml(
            base_sbml,
            {"km": SbmlParameterProvenance(origin="resolved", citation="PMID 12345678")},
        )
        broken = out.sbml.replace('rdf:about="#terrium_Km"', 'rdf:about="#nothing_here"')

        # libSBML: no complaint, and the annotation simply disappears.
        document = libsbml.readSBMLFromString(broken)
        document.checkConsistency()
        fatal = [
            document.getError(i).getMessage()
            for i in range(document.getNumErrors())
            if document.getError(i).getSeverity() >= libsbml.LIBSBML_SEV_ERROR
        ]
        assert fatal == [], "if libSBML started flagging this, say so here"
        assert read_back(broken)["Km"] == []

        # The independent reader names it.
        audit = audit_annotations(broken)
        assert not audit.ok
        assert any("names no element" in problem for problem in audit.problems)

    def test_a_qualifier_with_no_resource_is_caught(self, base_sbml):
        # An empty qualifier asserts a relationship to nothing, and is the
        # shape a partially-written annotation takes.
        out = annotate_sbml(
            base_sbml,
            {"km": SbmlParameterProvenance(origin="resolved", citation="PMID 12345678")},
        )
        import re

        stripped = re.sub(r"<rdf:li[^>]*/>", "", out.sbml)
        audit = audit_annotations(stripped)
        assert not audit.ok
        assert any("no resource" in problem for problem in audit.problems)

    def test_an_unannotated_model_audits_clean_rather_than_erroring(self, base_sbml):
        # No annotations is not a defect. A checker that cannot tell
        # "nothing to check" from "something is wrong" is useless on the
        # common case.
        audit = audit_annotations(base_sbml)
        assert audit.ok
        assert audit.triples == []

    def test_a_document_that_is_not_SBML_does_not_audit_clean(self):
        """The line above draws the right distinction and stopped one short.

        "Nothing to check" and "something is wrong" are correctly separated.
        "This is not the document you think it is" was folded in with the
        first: measured before the fix, an HTML error page returned
        `ok=True`, no triples, no problems.

        The namespace needed to tell them apart was already being computed
        at the top of `audit_annotations` and thrown away — ruff's F841, a
        bug class this repository's lint guard lists and does not yet
        enforce.
        """
        for text in (
            "<html><body><p>404 Not Found</p></body></html>",
            "<foo><bar/></foo>",
        ):
            audit = audit_annotations(text)
            assert not audit.ok, f"{text!r} audited clean"
            assert any("is not SBML" in problem for problem in audit.problems)

    def test_a_real_sbml_level_2_document_is_still_read(self):
        """The stem is matched, not a list of full namespace URIs.

        This repository handles level3/version2/core from libSBML and
        level2/version3 and /version4 from BioModels. A check written
        against one of them would reject the others, which is how a
        correctness guard becomes a compatibility bug.
        """
        fixture = (
            pathlib.Path(__file__).resolve().parents[2]
            / "Tests" / "fixtures" / "biomodels_BIOMD0000000006.xml"
        )
        audit = audit_annotations(fixture.read_text(encoding="utf-8"))
        assert not any("is not SBML" in problem for problem in audit.problems)
        assert audit.triples, "a real annotated BioModels document yielded none"


class TestTheWriteIsReconciledWithAnIndependentRead:
    """`audit.ok` cannot see annotations that are simply absent.

    That is not a flaw in the audit — as a standalone reader it has no way
    of knowing how many annotations were meant to be there, which is exactly
    why `test_an_unannotated_model_audits_clean_rather_than_erroring` is
    right. `annotate_sbml` is the one place that knows both.
    """

    def test_the_two_counts_are_both_reported(self, base_sbml):
        out = annotate_sbml(
            base_sbml,
            {"km": SbmlParameterProvenance(origin="resolved", citation="PMID 12345678")},
            ec_number="1.1.1.27",
            model_taxon_id="9606",
        )
        # Four, and naming them is the point of asserting a number at all:
        #   pubmed:12345678        the paper           (bqbiol:isDescribedBy)
        #   eco/ECO:0000269        how it is known     (bqbiol:isDescribedBy)
        #   ec-code:1.1.1.27       the enzyme          (model level)
        #   taxonomy:9606          the organism        (bqbiol:hasTaxon)
        # It was three until the evidence term was added (ADR 0187). A bare
        # count that nobody can decompose is a number that drifts silently.
        assert out.cvterms_written == 4
        assert out.triples_read_back == 4
        assert "read back by an independent parser" in out.summary()

    def test_annotations_lost_in_writing_are_refused(self, base_sbml, monkeypatch):
        """The failure the audit alone reports as clean.

        Measured before this existed: strip every `<annotation>` block from a
        freshly annotated document and the audit returns
        `triples=0, ok=True, problems=[]` while `cvterms_written` stays 3.

        libSBML is monkeypatched at the serialisation boundary because that
        is where the loss the module documents actually occurs — libSBML
        reporting success on a write whose result it will not read back.
        """
        import re as _re

        from Terium.core import sbml_provenance

        real_write = sbml_provenance.libsbml.writeSBMLToString

        def lossy(document):
            return _re.sub(
                r"<annotation>.*?</annotation>", "", real_write(document), flags=_re.S
            )

        monkeypatch.setattr(
            sbml_provenance.libsbml, "writeSBMLToString", lossy, raising=True
        )

        with pytest.raises(ValueError, match="did not survive writing"):
            annotate_sbml(
                base_sbml,
                {
                    "km": SbmlParameterProvenance(
                        origin="resolved", citation="PMID 12345678"
                    )
                },
                ec_number="1.1.1.27",
                model_taxon_id="9606",
            )

    def test_writing_nothing_at_all_is_not_an_error(self, base_sbml):
        """The guard must not fire on the legitimate case.

        A model with no provenance writes no CVTerms, so an independent
        reader correctly finds none. `0 < 0` is false, and a guard that
        fired here would fire on the common case and be suppressed
        (ADR 0028).
        """
        out = annotate_sbml(base_sbml, {})
        assert out.cvterms_written == 0
        assert out.triples_read_back == 0


# ---------------------------------------------------------------------------
# How the value is known, as an ontology term (ADR 0181, Gennari)
# ---------------------------------------------------------------------------


def test_a_resolved_parameter_carries_an_evidence_code(base_sbml):
    """ECO:0000269 -- experimental evidence used in manual assertion.

    John Gennari, asked whether there is an accepted way to mark an
    annotation as computed rather than taken from a source, named evidence
    codes (personal communication, 2026-08-27). This is also the one CVTerm
    use Bergmann's advice endorses: he warned that provenance PROSE in a
    CVTerm changes their semantic intent because readers expect
    ontology-based terms. An ECO term is one.

    Asserted on the resolvable URI, not on the string "ECO", because the
    accession appears in the notes too and matching there would pass whether
    or not a CVTerm was written.
    """
    out = annotate_sbml(
        base_sbml,
        {"Km": SbmlParameterProvenance(
            origin="resolved", citation="PMID 16333295",
            citation_source="pubmed", reference_id="16333295",
        )},
    )
    assert "https://identifiers.org/eco/ECO:0000269" in out.sbml


def test_a_user_supplied_parameter_gets_no_evidence_code(base_sbml):
    """Not weak evidence -- not evidence.

    An s0 the student chose is a condition of the experiment, not a claim
    about the world, and an evidence ontology has nothing to say about it.
    ECO:0000035 ("no evidence data found") would be wrong: nobody looked,
    because none was called for. The notes already record that it was
    supplied, so silence here is the accurate statement rather than a gap.
    """
    out = annotate_sbml(
        base_sbml,
        {"Km": SbmlParameterProvenance(origin="user", note="chosen by you")},
    )
    assert "identifiers.org/eco/" not in out.sbml


def test_the_evidence_uri_uses_the_form_that_resolves(base_sbml):
    """`eco:ECO:0000269` is a double prefix and 404s.

    Measured against identifiers.org rather than assumed:

        https://identifiers.org/eco:ECO:0000269   -> 404
        https://identifiers.org/eco/ECO:0000269   -> 200

    The colon form is right for every other namespace Terrium mints, so this
    is an exception rather than a correction -- and emitting it without
    noticing would have put a dead link inside an annotation whose entire
    purpose is to be followable.

    Offline: this asserts the shape Terrium emits, not that the network
    answers. The resolution check that produced those numbers is recorded in
    `miriam.py` beside the exception.
    """
    out = annotate_sbml(
        base_sbml,
        {"Km": SbmlParameterProvenance(
            origin="resolved", citation="PMID 16333295",
            citation_source="pubmed", reference_id="16333295",
        )},
    )
    assert "eco:ECO:" not in out.sbml, "the double-prefix form does not resolve"
    assert "eco/ECO:0000269" in out.sbml


def test_an_uncited_resolved_value_gets_no_evidence_code(base_sbml):
    """ECO:0000269 says a person read an experiment. Name the experiment.

    A `resolved` parameter carrying no citation and no reference id was
    getting the term anyway, so the model asserted that a paper measured the
    value while naming no paper -- a provenance tool inventing evidence, in
    the field added to describe evidence.

    The refusal is REPORTED, not silent: a missing annotation is
    indistinguishable from a parameter nobody looked at, and the whole point
    of `refused_uris` is that a gap says why it is there.
    """
    out = annotate_sbml(
        base_sbml, {"Km": SbmlParameterProvenance(origin="resolved")}
    )
    assert "identifiers.org/eco/" not in out.sbml
    reasons = [why for _, acc, why in out.refused_uris if acc.startswith("ECO")]
    assert reasons, "the omission must be reported, not merely performed"
    assert "nothing here to have read" in reasons[0]


def test_a_resolved_value_with_only_a_brenda_reference_still_gets_one(base_sbml):
    """A BRENDA reference id is not a URI, and is still a citation.

    `mint()` refuses to build a link for it (ADR 0064: BRENDA's namespace
    covers EC numbers, not reference ids), so the row carries no
    isDescribedBy. That is a fact about identifiers.org, not about whether a
    curator read a paper -- and gating the evidence term on a *mintable*
    citation would drop it for exactly the rows Terrium sources most.
    """
    out = annotate_sbml(
        base_sbml,
        {"Km": SbmlParameterProvenance(
            origin="resolved", citation="BRENDA ref 740253",
            citation_source="BRENDA", reference_id="740253",
        )},
    )
    assert "eco/ECO:0000269" in out.sbml