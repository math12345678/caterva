"""What must survive the trip out of Caterva, and what must never make it.

An export is the point where a model stops being Caterva's and becomes a
file somebody else reads in COPASI six months later. Two things have to hold
at that boundary and they pull in opposite directions:

    the STRUCTURE must arrive intact -- every species, every reaction, or
    the exported model is a different model from the one that was analysed;

    the PROVENANCE must arrive intact -- or an illustrative placeholder
    arrives looking exactly like a measured constant, wearing the authority
    of the tool it passed through.

The first is the ordinary thing an exporter is tested for. The second is the
one this project exists for, and it is the one an export gets wrong
silently: a file with the right species counts and no provenance passes
every structural check there is.

Most of what follows is checked against answers that are known in closed
form. A `catalytic_step` declares three ports and two parameters, so a
composition of one has exactly three species, one reaction, two constants,
and exactly two of its numbers are unmeasured -- no tolerance, no fixture
recorded from a previous run.
"""

from __future__ import annotations

import csv
import io
import sys
from types import SimpleNamespace

import pytest

from caterva.compose.builder import Composition, chain
from caterva.compose.library import (
    CATALYTIC_STEP, HILL_REPRESSION, PHOSPHORYLATION_CYCLE,
)
from caterva.compose.export import (
    CHOSEN_MARKER, CSV_COLUMNS, MEASURED_MARKER, ORIGIN_CHOSEN,
    ORIGIN_MEASURED, ORIGIN_PLACEHOLDER, PLACEHOLDER_MARKER,
    SBML_INSTALL_INSTRUCTION, ExportRefused, Measurement, ParameterOrigin,
    provenance_of, to_antimony, to_methods_paragraph, to_parameter_csv,
    to_sbml,
)
from caterva.compose.export import _antimony_source, measured_from_search
from caterva.compose.pipeline import compose
from caterva.core.model_provenance import strip_annotations
from caterva.core.network import compile_to_antimony


def _sbml_toolchain_present() -> bool:
    try:
        import antimony  # noqa: F401
        import libsbml  # noqa: F401
    except ImportError:
        return False
    return True


#: The SBML half needs two optional libraries. Skipped rather than failed
#: when they are absent, because their absence is exactly the case
#: `TestAMissingDependencyRefuses` covers deliberately -- and a skip is
#: visible in the summary line while a green pass would not be.
needs_sbml = pytest.mark.skipif(
    not _sbml_toolchain_present(),
    reason="python-libsbml and antimony are needed to export SBML",
)


# -- the models under test --------------------------------------------------
#
# TWO ENZYMES COMPETING FOR ONE SUBSTRATE, one of whose four constants has
# been resolved. Chosen because it exercises every branch at once: shared
# species, repeated motifs, a measured value, and three placeholders left
# over. Module-scoped because the SBML export runs an Antimony translation
# and eight tests want the same one.

CITATION = "PubMed 12345678"


def _competition() -> Composition:
    composition = Composition("competition")
    composition.add(CATALYTIC_STEP, "e1")
    composition.add(CATALYTIC_STEP, "e2", bindings={"S": "e1_S"})
    return composition


@pytest.fixture(scope="module")
def partly_measured():
    """A model with BOTH a measured parameter and unmeasured ones.

    The premise is asserted here rather than assumed, because five tests
    below are of the form "every placeholder is marked" and each one is a
    filter asserted empty. A model with no placeholders would satisfy all
    five while the marking code was entirely broken -- they would be green
    in precisely the case they exist to rule out.
    """
    composition = provenance_of(
        _competition(),
        measured={
            "e1_Km": Measurement(
                value=0.032,
                unit="mM",
                citation=CITATION,
                organism="Homo sapiens",
                source="brenda/km",
                citation_source="pubmed",
                reference_id="12345678",
                assay_ph=7.4,
                assay_temperature_c=30.0,
                assay_unreported=("buffer",),
            )
        },
    )
    measured = [
        p for p in composition.network.parameters
        if composition.origin_of(p.id).origin == ORIGIN_MEASURED
    ]
    placeholders = [
        p for p in composition.network.parameters
        if composition.origin_of(p.id).origin != ORIGIN_MEASURED
    ]
    assert measured, "nothing was measured, so 'measured' means nothing below"
    assert placeholders, (
        "nothing is a placeholder, so every 'marks every placeholder' test "
        "below would pass without the marking code running at all"
    )
    return composition


@pytest.fixture(scope="module")
def sbml(partly_measured):
    return to_sbml(partly_measured)


@pytest.fixture(scope="module")
def antimony_text(partly_measured):
    return to_antimony(partly_measured)


@pytest.fixture(scope="module")
def csv_text(partly_measured):
    return to_parameter_csv(partly_measured)


@pytest.fixture(scope="module")
def methods(partly_measured):
    return to_methods_paragraph(partly_measured)


def _rows(csv_text: str) -> dict:
    return {
        row["identifier"]: row
        for row in csv.DictReader(io.StringIO(csv_text))
    }


def _sbml_model(text: str):
    import libsbml

    document = libsbml.readSBMLFromString(text)
    return document, document.getModel()


class TestTheOriginsAreReadOffTheMotif:
    """The classification, against an answer the library states.

    `catalytic_step` declares kcat as a rate constant, Km as an affinity and
    S, P, E as ports. So the origins are not a judgement call: two
    placeholders and three choices, exactly, and the same for every copy.
    """

    def test_one_catalytic_step_has_exactly_two_gaps_and_three_choices(self) -> None:
        composition = Composition("one")
        composition.add(CATALYTIC_STEP, "e1")
        model = provenance_of(composition)
        by_origin = {}
        for origin in model.origins:
            by_origin.setdefault(origin.origin, set()).add(origin.identifier)
        assert by_origin == {
            ORIGIN_PLACEHOLDER: {"e1_kcat", "e1_Km"},
            ORIGIN_CHOSEN: {"e1_S", "e1_P", "e1_E"},
        }

    def test_an_enzyme_concentration_is_a_choice_and_never_a_gap(self) -> None:
        """The distinction ADR 0013 turns on.

        A placeholder is a measurement that is missing. An enzyme amount is
        not missing: no paper reports how much is in your tube, so it is
        nobody's to supply but the modeller's. Reporting it as a gap would
        send a researcher to the literature for something that is not there.
        """
        composition = Composition("one")
        composition.add(CATALYTIC_STEP, "e1")
        model = provenance_of(composition)
        assert model.origin_of("e1_E").origin == ORIGIN_CHOSEN
        assert model.origin_of("e1_E").resolvable is False

    def test_a_hill_exponent_is_a_choice_and_the_rate_constants_are_not(self) -> None:
        composition = Composition("repression")
        composition.add(HILL_REPRESSION, "h")
        model = provenance_of(composition)
        assert model.origin_of("h_n").origin == ORIGIN_CHOSEN
        assert {o.identifier for o in model.placeholders} == {"h_ks", "h_K", "h_kd"}

    def test_a_resolved_value_replaces_the_placeholder_in_the_model_itself(
        self, partly_measured
    ) -> None:
        # Not only in the provenance table. If the network still carried
        # 0.1 while the CSV said 0.032, the audit trail would describe a
        # model nobody exported.
        values = {p.id: p.value for p in partly_measured.network.parameters}
        assert values["e1_Km"] == 0.032
        assert values["e2_Km"] == 0.1
        assert partly_measured.origin_of("e1_Km").origin == ORIGIN_MEASURED

    def test_every_number_in_the_model_has_exactly_one_origin(
        self, partly_measured
    ) -> None:
        network = partly_measured.network
        declared = {o.identifier for o in partly_measured.origins}
        assert declared == {s.id for s in network.species} | {
            p.id for p in network.parameters
        }
        assert len(partly_measured.origins) == len(declared)


class TestTheStructureSurvivesEveryExport:
    """Species and reaction counts, which are known exactly.

    Two catalytic steps sharing a substrate: e1_S, e1_P, e1_E, e2_P, e2_E
    and two catalysis reactions. Five and two, in every artefact.
    """

    def test_the_network_itself_is_the_expected_shape(self, partly_measured) -> None:
        network = partly_measured.network
        assert [s.id for s in network.species] == [
            "e1_S", "e1_P", "e1_E", "e2_P", "e2_E"
        ]
        assert len(network.reactions) == 2

    def test_the_antimony_declares_every_species(self, partly_measured, antimony_text) -> None:
        declaration = next(
            line for line in antimony_text.splitlines()
            if line.strip().startswith("species ")
        )
        declared = {
            name.strip()
            for name in declaration.strip()[len("species "):].rstrip(";").split(",")
        }
        assert declared == {s.id for s in partly_measured.network.species}

    def test_annotating_the_antimony_changes_no_value(
        self, partly_measured, antimony_text
    ) -> None:
        """The property the whole Antimony exporter rests on.

        `strip_annotations` is `annotate_antimony`'s asserted inverse, so
        the round trip is exact rather than approximately equal. If
        annotation ever alters a model, this is what catches it -- and a
        provenance comment that silently changed a number would be the most
        embarrassing defect this module could have.
        """
        assert strip_annotations(antimony_text) == _antimony_source(partly_measured)

    @needs_sbml
    def test_the_sbml_has_the_same_species_and_reaction_counts(
        self, partly_measured, sbml
    ) -> None:
        _document, model = _sbml_model(sbml)
        species = {model.getSpecies(i).getId() for i in range(model.getNumSpecies())}
        parameters = {
            model.getParameter(i).getId() for i in range(model.getNumParameters())
        }
        assert species == {s.id for s in partly_measured.network.species}
        assert parameters == {p.id for p in partly_measured.network.parameters}
        assert model.getNumReactions() == len(partly_measured.network.reactions)

    @needs_sbml
    def test_the_sbml_is_level_three(self, sbml) -> None:
        document, _model = _sbml_model(sbml)
        assert document.getLevel() == 3

    @needs_sbml
    def test_the_sbml_has_no_consistency_errors(self, sbml) -> None:
        import libsbml

        document, _model = _sbml_model(sbml)
        document.checkConsistency()
        errors = [
            document.getError(i).getMessage().strip()
            for i in range(document.getNumErrors())
            if document.getError(i).getSeverity() >= libsbml.LIBSBML_SEV_ERROR
        ]
        assert errors == []

    @needs_sbml
    def test_without_the_species_declaration_the_enzyme_would_be_lost(
        self, partly_measured
    ) -> None:
        """The defect the extra `species` line exists to close.

        `compile_to_antimony` emits no species declaration, so Antimony
        infers them from the reactions -- and a motif's enzyme appears only
        in rate laws. Translated as-is, a five-species model reaches SBML
        with three species and two enzymes turned into parameters, which is
        the model a lab would open.

        Run against the unpatched compiler output, so this fails if the
        exporter ever stops adding the line.
        """
        import antimony

        antimony.clearPreviousLoads()
        antimony.loadAntimonyString(compile_to_antimony(partly_measured.network))
        naive = antimony.getSBMLString(antimony.getMainModuleName())
        _document, model = _sbml_model(naive)
        without = {model.getSpecies(i).getId() for i in range(model.getNumSpecies())}
        assert "e1_E" not in without

        _exported, exported_model = _sbml_model(to_sbml(partly_measured))
        with_declaration = {
            exported_model.getSpecies(i).getId()
            for i in range(exported_model.getNumSpecies())
        }
        assert "e1_E" in with_declaration

    def test_the_methods_paragraph_states_the_same_counts(
        self, partly_measured, methods
    ) -> None:
        network = partly_measured.network
        assert f"{len(network.species)} species" in methods
        assert f"{len(network.reactions)} reaction(s)" in methods

    def test_a_longer_composition_exports_at_its_own_size(self) -> None:
        """Nothing here is tuned to a two-motif model.

        Three phosphorylation cycles chained head to tail: the counts come
        from the motif's own declaration, so this is still a closed-form
        answer and not a recorded one.
        """
        composition = Composition("cascade")
        chain(
            composition, PHOSPHORYLATION_CYCLE, 3,
            prefix="tier", upstream_port="Xp", downstream_port="kinase",
            shared=("phosphatase",),
        )
        model = provenance_of(composition)
        rows = _rows(to_parameter_csv(model))
        assert set(rows) == {o.identifier for o in model.origins}
        assert len(model.placeholders) == 3 * len(PHOSPHORYLATION_CYCLE.parameters)


class TestTheAuditTrail:
    """The CSV, which is the artefact whose subject IS the provenance."""

    def test_the_header_is_the_declared_columns(self, csv_text) -> None:
        assert csv_text.splitlines()[0] == ",".join(CSV_COLUMNS)

    def test_every_quantity_is_named_with_its_origin_and_none_is_missing(
        self, partly_measured, csv_text
    ) -> None:
        rows = _rows(csv_text)
        assert {name: row["origin"] for name, row in rows.items()} == {
            "e1_S": ORIGIN_CHOSEN,
            "e1_P": ORIGIN_CHOSEN,
            "e1_E": ORIGIN_CHOSEN,
            "e2_P": ORIGIN_CHOSEN,
            "e2_E": ORIGIN_CHOSEN,
            "e1_kcat": ORIGIN_PLACEHOLDER,
            "e1_Km": ORIGIN_MEASURED,
            "e2_kcat": ORIGIN_PLACEHOLDER,
            "e2_Km": ORIGIN_PLACEHOLDER,
        }

    def test_the_row_count_is_the_model_and_nothing_else(self, partly_measured, csv_text) -> None:
        # No summary row, no blank line, no commented preamble: a reader
        # must be able to count the rows against the model and find them
        # equal, and a `csv.reader` must not trip over prose.
        network = partly_measured.network
        assert len(_rows(csv_text)) == len(network.species) + len(network.parameters)

    def test_every_row_carries_a_unit(self, csv_text) -> None:
        rows = _rows(csv_text)
        assert [name for name, row in rows.items() if not row["unit"]] == []

    def test_the_measured_row_carries_the_citation_and_the_resolved_value(
        self, csv_text
    ) -> None:
        row = _rows(csv_text)["e1_Km"]
        assert row["citation"] == CITATION
        assert float(row["value"]) == 0.032
        assert row["organism"] == "Homo sapiens"

    def test_a_placeholder_row_has_no_citation_and_says_so(self, csv_text) -> None:
        row = _rows(csv_text)["e2_Km"]
        assert row["citation"] == ""
        assert PLACEHOLDER_MARKER in row["provenance"]

    def test_the_assay_conditions_reach_the_audit_trail(self, csv_text) -> None:
        """Jeske's point, in columns rather than prose.

        A Km measured at pH 7.4 and one measured at pH 5 are not
        interchangeable, so a cited value whose conditions were dropped on
        export is a number a reader cannot judge -- and it looks exactly
        like one that was checked.
        """
        row = _rows(csv_text)["e1_Km"]
        assert row["assay_ph"] == "7.4"
        assert row["assay_temperature_c"] == "30"
        assert row["assay_not_reported_by_source"] == "buffer"

    def test_a_condition_the_source_never_stated_is_named_not_omitted(
        self, csv_text
    ) -> None:
        # "The paper did not report a buffer" is permanent and sends
        # somebody to the bench. "Caterva has no buffer" might be our parser
        # failing. The conclusion is the same; the action is not.
        row = _rows(csv_text)["e1_Km"]
        assert row["assay_buffer"] == ""
        assert "buffer" in row["assay_not_reported_by_source"]

    def test_the_csv_says_which_table_would_close_each_gap(self, csv_text) -> None:
        # The difference between "go and measure this" and "look this up".
        assert _rows(csv_text)["e2_Km"]["source_table"] == "km"
        assert _rows(csv_text)["e1_kcat"]["source_table"] == "kcat"


class TestNoArtefactPresentsAPlaceholderAsMeasured:
    """The property the module exists for, asserted in each format.

    A marker four exporters spell four ways is a marker three of them can
    lose, so every one of them is checked for the same string.
    """

    def test_the_antimony_marks_every_placeholder(self, partly_measured, antimony_text) -> None:
        for origin in partly_measured.placeholders:
            assert f"{origin.identifier} = " in antimony_text
        marked = [
            line for line in antimony_text.splitlines()
            if PLACEHOLDER_MARKER in line and " = " in line
        ]
        assert len(marked) >= len(partly_measured.placeholders)

    def test_the_csv_marks_every_placeholder(self, partly_measured, csv_text) -> None:
        rows = _rows(csv_text)
        unmarked = [
            origin.identifier
            for origin in partly_measured.placeholders
            if PLACEHOLDER_MARKER not in rows[origin.identifier]["provenance"]
        ]
        assert unmarked == []

    def test_the_methods_paragraph_marks_and_names_every_placeholder(
        self, partly_measured, methods
    ) -> None:
        assert PLACEHOLDER_MARKER in methods
        missing = [
            origin.identifier
            for origin in partly_measured.placeholders
            if f"`{origin.identifier}`" not in methods
        ]
        assert missing == []

    def test_the_methods_paragraph_does_not_list_a_placeholder_as_measured(
        self, partly_measured, methods
    ) -> None:
        """The section boundary, checked rather than trusted.

        The literature-derived list comes first and the placeholder
        paragraph after it. If a placeholder appeared before that boundary
        it would be sitting in the list a reader takes as cited, which is
        the exact misreading this artefact is written to prevent.
        """
        before_placeholders = methods.split(PLACEHOLDER_MARKER + "S")[0]
        assert MEASURED_MARKER in before_placeholders
        leaked = [
            origin.identifier
            for origin in partly_measured.placeholders
            if origin.identifier in before_placeholders
        ]
        assert leaked == []

    def test_the_methods_paragraph_reproduces_the_motif_basis(self, methods) -> None:
        # The assumption the model rests on, in the library's own words --
        # a paraphrase would be a different claim about the approximation.
        assert CATALYTIC_STEP.basis in methods

    @needs_sbml
    def test_the_sbml_marks_every_placeholder_in_its_own_notes(
        self, partly_measured, sbml
    ) -> None:
        _document, model = _sbml_model(sbml)
        notes = {
            model.getParameter(i).getId(): model.getParameter(i).getNotesString()
            for i in range(model.getNumParameters())
        }
        unmarked = [
            origin.identifier
            for origin in partly_measured.placeholders
            if PLACEHOLDER_MARKER not in notes[origin.identifier]
        ]
        assert unmarked == []

    @needs_sbml
    def test_the_sbml_does_not_put_the_citation_on_a_placeholder(self, sbml) -> None:
        _document, model = _sbml_model(sbml)
        notes = {
            model.getParameter(i).getId(): model.getParameter(i).getNotesString()
            for i in range(model.getNumParameters())
        }
        assert CITATION in notes["e1_Km"]
        assert CITATION not in notes["e2_Km"]
        assert CITATION not in notes["e1_kcat"]

    @needs_sbml
    def test_the_sbml_names_the_placeholders_on_the_model_itself(
        self, partly_measured, sbml
    ) -> None:
        # A reader who opens the file and reads nothing but the model notes
        # must already know which numbers are not measurements.
        _document, model = _sbml_model(sbml)
        model_notes = model.getNotesString()
        missing = [
            origin.identifier
            for origin in partly_measured.placeholders
            if origin.identifier not in model_notes
        ]
        assert missing == []
        assert PLACEHOLDER_MARKER in model_notes

    @needs_sbml
    def test_the_citation_survives_as_machine_readable_rdf(self, sbml) -> None:
        """Notes are prose; a pipeline does not read prose.

        The point of writing MIRIAM rather than a Caterva format is that a
        consumer which never renders notes to anyone still sees where the
        value came from. Read back by `audit_annotations`, which parses the
        RDF WITHOUT libSBML -- the producer verified against itself would
        establish nothing about a third-party reader.
        """
        from caterva.core.sbml_provenance import audit_annotations

        audit = audit_annotations(sbml)
        assert audit.ok, audit.problems
        assert any("12345678" in uri for _element, _qualifier, uri in audit.triples)

    def test_the_assay_conditions_reach_the_antimony(self, antimony_text) -> None:
        assert "pH 7.4" in antimony_text
        assert "NOT REPORTED by the source: buffer" in antimony_text

    @needs_sbml
    def test_the_assay_conditions_reach_the_sbml_notes(self, sbml) -> None:
        _document, model = _sbml_model(sbml)
        notes = {
            model.getParameter(i).getId(): model.getParameter(i).getNotesString()
            for i in range(model.getNumParameters())
        }
        assert "pH 7.4" in notes["e1_Km"]
        assert "Not reported by the source: buffer" in notes["e1_Km"]

    @needs_sbml
    def test_the_sbml_says_it_carries_no_units(self, sbml) -> None:
        # A limitation stated only in a docstring is a trap for whoever
        # receives the file.
        _document, model = _sbml_model(sbml)
        assert "declares no units" in model.getNotesString()

    def test_the_species_are_marked_as_choices_in_every_artefact(
        self, partly_measured, antimony_text, csv_text, methods
    ) -> None:
        rows = _rows(csv_text)
        assert CHOSEN_MARKER in antimony_text
        assert CHOSEN_MARKER in methods
        assert CHOSEN_MARKER in rows["e1_E"]["provenance"]


class TestAMissingDependencyRefuses:
    """The SBML path, with the libraries taken away.

    `sys.modules[name] = None` is how CPython records a blocked import, so
    `import libsbml` inside the exporter raises ImportError exactly as it
    would on a machine that never had the wheel. Nothing is monkeypatched
    inside the module under test, so this exercises the real import.
    """

    def test_a_missing_libsbml_refuses_and_names_the_install(
        self, partly_measured, monkeypatch
    ) -> None:
        monkeypatch.setitem(sys.modules, "libsbml", None)
        with pytest.raises(ExportRefused) as refusal:
            to_sbml(partly_measured)
        message = str(refusal.value)
        assert "python-libsbml" in message
        assert SBML_INSTALL_INSTRUCTION in message

    def test_a_missing_antimony_refuses_and_names_the_install(
        self, partly_measured, monkeypatch
    ) -> None:
        monkeypatch.setitem(sys.modules, "antimony", None)
        with pytest.raises(ExportRefused) as refusal:
            to_sbml(partly_measured)
        assert "antimony" in str(refusal.value)
        assert SBML_INSTALL_INSTRUCTION in str(refusal.value)

    def test_it_refuses_rather_than_writing_xml_of_its_own(
        self, partly_measured, monkeypatch
    ) -> None:
        # The refusal is the feature. A hand-rolled SBML file that is
        # subtly invalid still opens in COPASI, and a model that loads
        # wrong is worse than one that does not load.
        monkeypatch.setitem(sys.modules, "libsbml", None)
        with pytest.raises(ExportRefused) as refusal:
            to_sbml(partly_measured)
        assert "hand-write" in str(refusal.value)

    def test_the_other_three_exporters_do_not_need_the_libraries(
        self, partly_measured, monkeypatch
    ) -> None:
        """The refusal must cost only the format that needs the library.

        A model whose SBML cannot be written still has an audit trail worth
        having, and losing the CSV because a wheel is missing would be the
        wrong trade.
        """
        monkeypatch.setitem(sys.modules, "libsbml", None)
        monkeypatch.setitem(sys.modules, "antimony", None)
        assert PLACEHOLDER_MARKER in to_antimony(partly_measured)
        assert PLACEHOLDER_MARKER in to_parameter_csv(partly_measured)
        assert PLACEHOLDER_MARKER in to_methods_paragraph(partly_measured)


class TestRefusalsThatKeepTheArtefactsHonest:
    def test_a_measurement_without_a_citation_cannot_be_built(self) -> None:
        with pytest.raises(ExportRefused) as refusal:
            Measurement(value=0.1, unit="mM", citation="   ")
        assert "citation" in str(refusal.value)

    def test_a_starting_amount_cannot_be_given_a_citation(self) -> None:
        composition = Composition("one")
        composition.add(CATALYTIC_STEP, "e1")
        with pytest.raises(ExportRefused) as refusal:
            provenance_of(
                composition,
                measured={"e1_S": Measurement(1.0, "mM", CITATION)},
            )
        assert "concentration is never a literature quantity" in str(refusal.value)

    def test_a_hill_exponent_cannot_be_given_a_citation(self) -> None:
        composition = Composition("repression")
        composition.add(HILL_REPRESSION, "h")
        with pytest.raises(ExportRefused) as refusal:
            provenance_of(
                composition,
                measured={"h_n": Measurement(2.0, "dimensionless", CITATION)},
            )
        assert "exponent" in str(refusal.value)

    def test_a_unit_mismatch_is_refused_rather_than_converted(self) -> None:
        composition = Composition("one")
        composition.add(CATALYTIC_STEP, "e1")
        with pytest.raises(ExportRefused) as refusal:
            provenance_of(
                composition,
                measured={"e1_Km": Measurement(32.0, "uM", CITATION)},
            )
        assert "does not convert" in str(refusal.value)

    def test_a_measured_value_for_a_quantity_the_model_lacks_is_refused(self) -> None:
        # The resolver and the model disagreeing about what was built is a
        # fact the caller has to see, not one to drop on the floor behind an
        # artefact that looks complete.
        composition = Composition("one")
        composition.add(CATALYTIC_STEP, "e1")
        with pytest.raises(ExportRefused) as refusal:
            provenance_of(
                composition,
                measured={"e9_Km": Measurement(0.1, "mM", CITATION)},
            )
        assert "does not contain" in str(refusal.value)

    def test_identifiers_differing_only_in_case_are_refused(self) -> None:
        """Both annotators fold case, so `a_Km` and `A_Km` are one key.

        SBML ids are case-sensitive and these are two different quantities;
        letting the fold pick one would attach a measured value's origin to
        a placeholder, which is the failure arriving by the back door.
        """
        composition = Composition("clash")
        composition.add(CATALYTIC_STEP, "a")
        composition.add(CATALYTIC_STEP, "A")
        with pytest.raises(ExportRefused) as refusal:
            provenance_of(composition)
        assert "differ only in case" in str(refusal.value)

    def test_a_bare_network_cannot_be_exported(self) -> None:
        composition = Composition("one")
        composition.add(CATALYTIC_STEP, "e1")
        with pytest.raises(ExportRefused) as refusal:
            provenance_of(composition.to_network())
        assert "Composition" in str(refusal.value)

    def test_an_origin_marked_measured_must_carry_its_measurement(self) -> None:
        with pytest.raises(ExportRefused) as refusal:
            ParameterOrigin(
                identifier="e1_Km",
                origin=ORIGIN_MEASURED,
                kind="affinity",
                value=0.1,
                unit="mM",
                role="parameter",
            )
        assert "no Measurement" in str(refusal.value)

    def test_an_unknown_origin_is_refused_rather_than_rendered(self) -> None:
        with pytest.raises(ExportRefused) as refusal:
            ParameterOrigin(
                identifier="e1_Km",
                origin="probably_fine",
                kind="affinity",
                value=0.1,
                unit="mM",
                role="parameter",
            )
        assert "not one of" in str(refusal.value)


class TestTheEntryPointACallerActuallyUses:
    """`compose(...)` then export, which is the whole path end to end."""

    def test_a_composed_model_from_the_pipeline_exports(self) -> None:
        model = compose("two enzymes competing for the same substrate")
        record = provenance_of(model)
        rows = _rows(to_parameter_csv(record))
        assert set(rows) == {
            "enzyme1_S", "enzyme1_P", "enzyme1_E", "enzyme2_P", "enzyme2_E",
            "enzyme1_kcat", "enzyme1_Km", "enzyme2_kcat", "enzyme2_Km",
        }
        assert record.query == "two enzymes competing for the same substrate"

    def test_an_ungrounded_model_says_every_constant_is_a_placeholder(self) -> None:
        """No enzyme named means nothing was searched for.

        Four constants, four placeholders, and the methods paragraph has to
        say so in the sentence a reader takes as the model's warrant --
        because this is the commonest state a composed model is in.
        """
        record = provenance_of(compose("two enzymes competing for the same substrate"))
        assert len(record.measured) == 0
        assert len(record.placeholders) == 4
        assert "No constant in this model was taken from the literature" in (
            to_methods_paragraph(record)
        )

    def test_the_composition_notes_reach_the_methods_paragraph(self) -> None:
        # "two catalytic steps competing for one S" is not recoverable from
        # the stoichiometry afterwards, so a methods section that dropped it
        # would describe a model nobody could rebuild.
        record = provenance_of(compose("two enzymes competing for the same substrate"))
        assert "competing for one S" in to_methods_paragraph(record)


class TestTheAgentSearchAdapter:
    """`measured_from_search`, which is duck-typed against `ParameterSource`.

    Stubs rather than a live agent run: the function reads five documented
    attributes and nothing else, and pinning it to a real search would test
    the resolver instead of the conversion.
    """

    def test_a_cited_resolution_becomes_a_measurement(self) -> None:
        build = _stub_build(
            c1_Km=_stub_source(
                value=0.05, unit="mM", citation="PubMed 999",
                organism="Escherichia coli", ph=7.0, temperature_c=25.0,
                explicitly_unreported=("buffer",),
            )
        )
        measured = measured_from_search(build)
        assert measured["c1_Km"].citation == "PubMed 999"
        assert measured["c1_Km"].value == 0.05
        assert measured["c1_Km"].assay_ph == 7.0
        assert measured["c1_Km"].assay_unreported == ("buffer",)

    def test_a_resolution_with_no_citation_is_refused(self) -> None:
        build = _stub_build(
            c1_Km=_stub_source(value=0.05, unit="mM", citation=None)
        )
        with pytest.raises(ExportRefused) as refusal:
            measured_from_search(build)
        assert "no citation recorded" in str(refusal.value)

    def test_an_unresolved_quantity_is_left_out_rather_than_invented(self) -> None:
        build = _stub_build(c1_Km=None)
        assert measured_from_search(build) == {}

    def test_a_search_that_chose_no_model_is_refused(self) -> None:
        """`ModelSearch.build` is None when no single organism completes it.

        Exporting the first pass instead would hand a lab a model whose
        constants come from two animals, which is the object the whole
        agent architecture exists to refuse.
        """
        with pytest.raises(ExportRefused) as refusal:
            measured_from_search(SimpleNamespace(build=None))
        assert "no single model" in str(refusal.value)


def _stub_source(**fields):
    defaults = {
        "value": 0.0, "unit": "mM", "citation": None, "organism": None,
        "cross_species": False, "origin": "literature",
        "ph": None, "temperature_c": None, "buffer": None,
        "explicitly_unreported": (),
    }
    defaults.update(fields)
    return SimpleNamespace(**defaults)


def _stub_build(**resolutions):
    return SimpleNamespace(
        resolutions={
            quantity: SimpleNamespace(source=source)
            for quantity, source in resolutions.items()
        }
    )
