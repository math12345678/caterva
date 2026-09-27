"""An archive is only reproducible if it actually reproduces.

The tests that matter here do not check that the SED-ML is well-formed —
libSEDML builds it, so of course it is. They open the archive, read the
experiment **out of the SED-ML**, run the model **out of the archive**, and
compare against the original trajectory.

A schema-valid experiment that reproduces a different curve is still a
broken export, and validation alone cannot tell the two apart.
"""

from __future__ import annotations

import zipfile

import libsbml
import pytest

from caterva.core.combine_archive import (
    BIBTEX,
    KISAO_CVODE,
    SBML_L3V2,
    SEDML_L1V3,
    ArchiveEntry,
    build_manifest,
    RecordedQuantity,
    build_sedml,
    recorded_quantities,
    resolve_targets,
    species_in,
    verify_archive,
    write_archive,
)

libsedml = pytest.importorskip("libsedml")
roadrunner = pytest.importorskip("roadrunner")
antimony = pytest.importorskip("antimony")

MODEL = """model michaelis_menten
  S = 10; P = 0;
  Km = 2.5;
  Vmax = 0.25;
  J0: S -> P; Vmax * S / (Km + S);
end"""


@pytest.fixture
def sbml() -> str:
    antimony.clearPreviousLoads()
    assert antimony.loadAntimonyString(MODEL) >= 0, antimony.getLastError()
    return antimony.getSBMLString(antimony.getMainModuleName())


def make_archive(tmp_path, sbml, *, end_time=20.0, points=101, recorded=None):
    # Default to whatever the MODEL declares, which is what the exporter
    # does. A test that always passed its own list would never exercise the
    # derivation the export actually relies on.
    sedml, errors = build_sedml(
        model_location="model.xml",
        model_id="caterva_model",
        end_time=end_time,
        points=points,
        recorded=(
            [RecordedQuantity(name, "species") for name in recorded]
            if recorded is not None
            else recorded_quantities(sbml)
        ),
    )
    assert errors == []
    destination = tmp_path / "run.omex"
    write_archive(
        destination,
        {
            "model.xml": (sbml, ArchiveEntry("model.xml", SBML_L3V2)),
            "simulation.sedml": (
                sedml,
                ArchiveEntry("simulation.sedml", SEDML_L1V3, master=True),
            ),
        },
    )
    return destination


class TestTheArchiveActuallyReproducesTheRun:
    """The claim, tested by doing it rather than by asserting the parts."""

    def test_replaying_from_the_archive_alone_matches_the_original(
        self, tmp_path, sbml
    ):
        original = roadrunner.RoadRunner(sbml).simulate(0, 20, 101)
        archive = make_archive(tmp_path, sbml)

        # From here on, pretend to know nothing but the file.
        with zipfile.ZipFile(archive) as opened:
            sedml_text = opened.read("simulation.sedml").decode()
            model_text = opened.read("model.xml").decode()

        document = libsedml.readSedMLFromString(sedml_text)
        simulation = document.getSimulation(0)
        replay = roadrunner.RoadRunner(model_text).simulate(
            simulation.getOutputStartTime(),
            simulation.getOutputEndTime(),
            simulation.getNumberOfPoints() + 1,
        )

        assert replay.shape == original.shape
        for row_original, row_replay in zip(original, replay):
            for a, b in zip(row_original, row_replay):
                assert float(a) == pytest.approx(float(b), abs=1e-9)

    def test_the_row_count_is_not_off_by_one(self, tmp_path, sbml):
        """SED-ML counts INTERVALS; Caterva reports ROWS.

        101 rows is 100 intervals. Get this wrong and every re-run lands
        its samples between the original's — the curve looks right, every
        number differs, and nothing errors.
        """
        archive = make_archive(tmp_path, sbml, points=101)
        with zipfile.ZipFile(archive) as opened:
            document = libsedml.readSedMLFromString(
                opened.read("simulation.sedml").decode()
            )
        assert document.getSimulation(0).getNumberOfPoints() == 100

    def test_the_algorithm_named_is_the_one_that_ran(self, tmp_path, sbml):
        # KiSAO is how SED-ML names a solver. A term that does not match
        # the solver describes an experiment nobody performed.
        archive = make_archive(tmp_path, sbml)
        with zipfile.ZipFile(archive) as opened:
            document = libsedml.readSedMLFromString(
                opened.read("simulation.sedml").decode()
            )
        assert document.getSimulation(0).getAlgorithm().getKisaoID() == KISAO_CVODE
        assert KISAO_CVODE == "KISAO:0000019"  # CVODE, what libRoadRunner uses


class TestTheManifestTellsTheTruth:
    def test_every_file_is_listed_and_every_listing_exists(self, tmp_path, sbml):
        outcome = verify_archive(make_archive(tmp_path, sbml))
        assert outcome.ok, outcome.problems
        assert set(outcome.listed) == set(outcome.present)

    def test_a_file_added_without_a_manifest_entry_is_caught(self, tmp_path, sbml):
        """The direction the obvious implementation misses.

        Walking the manifest and confirming each file exists passes an
        archive whose manifest omits half its contents — and a strict
        reader ignores unlisted entries, so the citations would vanish
        silently.
        """
        archive = make_archive(tmp_path, sbml)
        with zipfile.ZipFile(archive, "a") as opened:
            opened.writestr("citations.bib", "@misc{x}")

        outcome = verify_archive(archive)
        assert not outcome.ok
        assert any("not in the manifest" in problem for problem in outcome.problems)

    def test_a_manifest_entry_with_no_file_is_caught(self, tmp_path, sbml):
        sedml, _ = build_sedml(
            model_location="model.xml", model_id="m", end_time=1.0, points=2,
            recorded=[RecordedQuantity("S", "species")],
        )
        destination = tmp_path / "broken.omex"
        manifest = build_manifest(
            [
                ArchiveEntry("model.xml", SBML_L3V2),
                ArchiveEntry("simulation.sedml", SEDML_L1V3, master=True),
                ArchiveEntry("missing.bib", BIBTEX),
            ]
        )
        with zipfile.ZipFile(destination, "w") as opened:
            opened.writestr("manifest.xml", manifest)
            opened.writestr("model.xml", sbml)
            opened.writestr("simulation.sedml", sedml)

        outcome = verify_archive(destination)
        assert not outcome.ok
        assert any("missing.bib" in problem for problem in outcome.problems)

    def test_the_manifest_declares_itself_and_the_archive(self, tmp_path, sbml):
        # Required by the OMEX specification, and easy to forget because
        # nothing breaks locally when they are absent.
        with zipfile.ZipFile(make_archive(tmp_path, sbml)) as opened:
            manifest = opened.read("manifest.xml").decode()
        assert 'location="."' in manifest
        assert 'location="./manifest.xml"' in manifest


class TestWhatIsRefusedRatherThanGuessed:
    def test_exactly_one_master_entry_is_required(self, tmp_path, sbml):
        # The master is what a reader opens first. Zero means the reader
        # picks; two means it picks differently. Both make the archive's
        # behaviour depend on the tool rather than the file.
        with pytest.raises(ValueError, match="exactly one master"):
            write_archive(
                tmp_path / "none.omex",
                {"model.xml": (sbml, ArchiveEntry("model.xml", SBML_L3V2))},
            )

    def test_two_masters_are_refused_too(self, tmp_path, sbml):
        sedml, _ = build_sedml(
            model_location="model.xml", model_id="m", end_time=1.0, points=2,
            recorded=[RecordedQuantity("S", "species")],
        )
        with pytest.raises(ValueError, match="exactly one master"):
            write_archive(
                tmp_path / "two.omex",
                {
                    "model.xml": (sbml, ArchiveEntry("model.xml", SBML_L3V2, master=True)),
                    "simulation.sedml": (
                        sedml,
                        ArchiveEntry("simulation.sedml", SEDML_L1V3, master=True),
                    ),
                },
            )

    def test_the_sedml_is_the_master_not_the_model(self, tmp_path, sbml):
        # Opening the model first loses the experiment, which is the half
        # that was missing before this export existed.
        with zipfile.ZipFile(make_archive(tmp_path, sbml)) as opened:
            manifest = opened.read("manifest.xml").decode()
        master_line = next(
            line for line in manifest.splitlines() if 'master="true"' in line
        )
        assert "simulation.sedml" in master_line

    def test_bibtex_travels_as_a_media_type_not_an_invented_spec(self):
        # There is no COMBINE specification for BibTeX. Minting
        # `combine.specifications/bibtex` would be a fabricated identifier
        # in the one file whose job is saying truthfully what each entry is
        # — the same refusal as `miriam.py` makes for BRENDA.
        assert BIBTEX == "application/x-bibtex"
        assert "combine.specifications" not in BIBTEX


class TestTheSedmlDescribesSomethingWorthReading:
    def test_the_report_records_every_requested_species_and_time(self, tmp_path, sbml):
        with zipfile.ZipFile(make_archive(tmp_path, sbml, recorded=("S", "P"))) as opened:
            document = libsedml.readSedMLFromString(
                opened.read("simulation.sedml").decode()
            )
        report = document.getOutput(0)
        labels = {
            report.getDataSet(i).getLabel() for i in range(report.getNumDataSets())
        }
        assert labels == {"time", "S", "P"}

    def test_the_model_source_points_at_the_archived_file(self, tmp_path, sbml):
        # An absolute path or a URL here would make the archive depend on
        # the machine that produced it, which is the opposite of the point.
        with zipfile.ZipFile(make_archive(tmp_path, sbml)) as opened:
            document = libsedml.readSedMLFromString(
                opened.read("simulation.sedml").decode()
            )
            assert document.getModel(0).getSource() in opened.namelist()


class TestTheRecordedSpeciesComeFromTheModel:
    """The list used to be written at the call site: `["S", "P"]`.

    Correct for Michaelis-Menten and a standing invitation to be wrong for
    anything else. Reading it from the model means a new domain gets a
    correct report without anyone remembering to update a literal.

    A subtlety found while writing these, worth keeping because it is
    counter-intuitive: in the competitively-inhibited model the inhibitor
    `I` is an SBML **parameter**, not a species — Antimony classifies it
    that way because it never appears as a reactant or product. It is also
    constant, so it does not belong in a time-course report at all; its
    value is in the model file. `species_in` returning just `["S", "P"]`
    for that model is correct, and the first version of this test asserting
    otherwise was the test being wrong, not the code.
    """

    THREE_SPECIES = """model two_step
  S = 10; P = 0; Q = 0;
  k1 = 0.3;
  k2 = 0.1;
  J0: S -> P; k1 * S;
  J1: P -> Q; k2 * P;
end"""

    def test_species_are_read_from_the_model(self, sbml):
        assert species_in(sbml) == ["S", "P"]

    def test_a_third_species_is_picked_up_without_anyone_updating_a_list(self):
        antimony.clearPreviousLoads()
        assert antimony.loadAntimonyString(self.THREE_SPECIES) >= 0, antimony.getLastError()
        three = antimony.getSBMLString(antimony.getMainModuleName())

        # The hardcoded call site would have reported S and P and silently
        # dropped Q -- a reproducible answer to a different question.
        assert species_in(three) == ["S", "P", "Q"]

    def test_the_report_covers_every_species_the_model_declares(self, tmp_path):
        antimony.clearPreviousLoads()
        assert antimony.loadAntimonyString(self.THREE_SPECIES) >= 0, antimony.getLastError()
        three = antimony.getSBMLString(antimony.getMainModuleName())

        with zipfile.ZipFile(make_archive(tmp_path, three)) as opened:
            document = libsedml.readSedMLFromString(
                opened.read("simulation.sedml").decode()
            )
        report = document.getOutput(0)
        labels = {
            report.getDataSet(i).getLabel() for i in range(report.getNumDataSets())
        }
        # Two reactions in this model, and their fluxes are recorded too.
        assert labels == {"time", "S", "P", "Q", "J0", "J1"}

    def test_the_replay_of_a_three_species_model_still_matches(self, tmp_path):
        # Deriving the list must not break the property the archive exists
        # for. Same assertion as the headline test, on a model the old
        # hardcoded list would have got wrong.
        antimony.clearPreviousLoads()
        assert antimony.loadAntimonyString(self.THREE_SPECIES) >= 0, antimony.getLastError()
        three = antimony.getSBMLString(antimony.getMainModuleName())

        original = roadrunner.RoadRunner(three).simulate(0, 20, 101)
        with zipfile.ZipFile(make_archive(tmp_path, three)) as opened:
            document = libsedml.readSedMLFromString(
                opened.read("simulation.sedml").decode()
            )
            model_text = opened.read("model.xml").decode()
        simulation = document.getSimulation(0)
        replay = roadrunner.RoadRunner(model_text).simulate(
            simulation.getOutputStartTime(),
            simulation.getOutputEndTime(),
            simulation.getNumberOfPoints() + 1,
        )
        assert replay.shape == original.shape
        assert float(replay[-1][3]) == pytest.approx(float(original[-1][3]), abs=1e-9)

    def test_listing_species_on_a_document_with_no_model_raises(self):
        # Returning [] would produce an archive whose report is empty, which
        # runs and tells the reader nothing.
        with pytest.raises(ValueError, match="no model"):
            species_in("<sbml xmlns='http://www.sbml.org/sbml/level3/version2/core'/>")


class TestEverythingThatVariesIsRecorded:
    """Species are not the only quantities that move.

    `species_in` was correct for all four Caterva domains — verified, not
    assumed: none has a rule or a non-constant parameter. It would have gone
    on being correct until a model gained one, and then the report would
    have silently lost a curve. No error, no warning, just a figure missing
    a line.

    The XPath is the sharper half. `build_sedml` hardcoded the *species*
    path for every recorded name, so a parameter would have been given a
    target resolving to nothing — an archive that opens, runs, and reports
    an empty column.
    """

    WITH_RULE = """model with_assignment
  S = 10; P = 0;
  k = 0.3;
  total := S + P;
  J0: S -> P; k * S;
end"""

    WITH_VARYING_PARAMETER = """model with_rate_rule
  S = 10; P = 0;
  k = 0.3;
  k' = -0.01 * k;
  J0: S -> P; k * S;
end"""

    def to_sbml(self, text: str) -> str:
        antimony.clearPreviousLoads()
        assert antimony.loadAntimonyString(text) >= 0, antimony.getLastError()
        return antimony.getSBMLString(antimony.getMainModuleName())

    def test_species_and_the_reaction_that_moves_them(self, sbml):
        # Was `test_species_only_models_are_unchanged`, asserting exactly
        # ["S", "P"]. The flux J0 is now recorded too -- deliberately, and
        # the docstring in combine_archive.py measures how it differs from
        # the velocity Caterva prints. Renamed rather than loosened: the old
        # name would have claimed a no-op that stopped being one.
        quantities = recorded_quantities(sbml)
        assert [q.id for q in quantities] == ["S", "P", "J0"]
        assert [q.kind for q in quantities] == ["species", "species", "reaction"]

    def test_an_assignment_rule_target_is_recorded(self):
        quantities = recorded_quantities(self.to_sbml(self.WITH_RULE))
        assert "total" in [q.id for q in quantities], (
            "a quantity the model assigns every step is missing from the report"
        )

    def test_a_rate_rule_parameter_is_recorded(self):
        quantities = recorded_quantities(self.to_sbml(self.WITH_VARYING_PARAMETER))
        assert "k" in [q.id for q in quantities]

    def test_a_constant_parameter_is_not_recorded(self, sbml):
        # Km and Vmax do not vary. A flat line in a time-course report is
        # noise, and their values are in the model file.
        assert "Km" not in [q.id for q in recorded_quantities(sbml)]
        assert "Vmax" not in [q.id for q in recorded_quantities(sbml)]

    def test_a_parameter_gets_the_parameter_xpath_not_the_species_one(self):
        quantities = recorded_quantities(self.to_sbml(self.WITH_VARYING_PARAMETER))
        k = next(q for q in quantities if q.id == "k")
        assert "listOfParameters" in k.target
        assert "listOfSpecies" not in k.target

    def test_an_unknown_kind_refuses_rather_than_guessing_a_target(self):
        # This used "compartment", then "reaction". Both became real kinds,
        # and each time the test aged into asserting that a supported
        # feature was unsupported. Twice is a pattern: any *plausible* SBML
        # noun is a candidate for support later.
        #
        # So the placeholder is now deliberately not an SBML concept at
        # all, which is the only choice that cannot be overtaken.
        with pytest.raises(ValueError, match="Unknown quantity kind"):
            RecordedQuantity("x", "not-an-sbml-concept").target

    def test_the_archive_of_a_rule_model_still_replays(self, tmp_path):
        # The report gained a column; the trajectory must not change.
        model = self.to_sbml(self.WITH_RULE)
        original = roadrunner.RoadRunner(model).simulate(0, 20, 101)

        with zipfile.ZipFile(make_archive(tmp_path, model)) as opened:
            document = libsedml.readSedMLFromString(
                opened.read("simulation.sedml").decode()
            )
            model_text = opened.read("model.xml").decode()
        simulation = document.getSimulation(0)
        replay = roadrunner.RoadRunner(model_text).simulate(
            simulation.getOutputStartTime(),
            simulation.getOutputEndTime(),
            simulation.getNumberOfPoints() + 1,
        )
        assert replay.shape == original.shape
        assert float(replay[-1][1]) == pytest.approx(float(original[-1][1]), abs=1e-9)


class TestTheRuleLoopEarnsItsPlace:
    """Two mutations survived here, and the survival was the finding.

    Deleting the rule loop changed nothing; deleting the non-constant
    parameter loop changed nothing either. For species and parameters they
    cover identical ground, because **libSBML forbids a rule on a constant
    entity** — measured, not assumed:

        An assignment rule cannot assign an entity declared to be constant

    A comment in this module previously claimed the opposite. It was written
    from intuition, and checking it took one script.

    So the rule loop is redundant for species and parameters, and it stays
    only because of the case neither other loop reaches: a rule targeting a
    COMPARTMENT.
    """

    def varying_compartment_model(self) -> str:
        # Built through libSBML rather than Antimony: this needs a shape
        # Antimony does not express directly, and constructing it by hand
        # keeps the test about the thing under test.
        document = libsbml.SBMLDocument(3, 2)
        model = document.createModel()
        model.setId("growing_cell")

        compartment = model.createCompartment()
        compartment.setId("cell")
        compartment.setSize(1.0)
        compartment.setSpatialDimensions(3)
        compartment.setConstant(False)  # required: a rule assigns it

        species = model.createSpecies()
        species.setId("S")
        species.setCompartment("cell")
        species.setInitialConcentration(10.0)
        species.setConstant(False)
        species.setBoundaryCondition(False)
        species.setHasOnlySubstanceUnits(False)

        rule = model.createAssignmentRule()
        rule.setVariable("cell")
        rule.setMath(libsbml.parseL3Formula("1 + 0.1 * time"))

        return libsbml.writeSBMLToString(document)

    def test_libsbml_really_does_forbid_a_rule_on_a_constant_entity(self):
        """Pinning the fact the comment now rests on.

        If a future libSBML relaxes this, the parameter loop stops covering
        rule targets and this file's reasoning silently stops holding.
        """
        document = libsbml.SBMLDocument(3, 2)
        model = document.createModel()
        model.setId("probe")
        compartment = model.createCompartment()
        compartment.setId("c")
        compartment.setConstant(True)
        compartment.setSize(1)
        compartment.setSpatialDimensions(3)
        parameter = model.createParameter()
        parameter.setId("k")
        parameter.setValue(0.3)
        parameter.setConstant(True)
        rule = model.createAssignmentRule()
        rule.setVariable("k")
        rule.setMath(libsbml.parseL3Formula("2"))

        document.checkConsistency()
        messages = [
            document.getError(i).getShortMessage()
            for i in range(document.getNumErrors())
            if document.getError(i).getSeverity() >= libsbml.LIBSBML_SEV_ERROR
        ]
        assert any("constant" in message for message in messages), messages

    def test_a_varying_compartment_is_recorded(self):
        quantities = recorded_quantities(self.varying_compartment_model())
        by_id = {q.id: q.kind for q in quantities}
        assert by_id.get("cell") == "compartment", (
            "a compartment that changes size every step is missing from the "
            "report; neither the species nor the parameter loop reaches it"
        )
        assert by_id.get("S") == "species"

    def test_a_compartment_gets_its_own_xpath(self):
        quantities = recorded_quantities(self.varying_compartment_model())
        cell = next(q for q in quantities if q.id == "cell")
        assert "listOfCompartments" in cell.target
        assert "listOfSpecies" not in cell.target
        assert "listOfParameters" not in cell.target

    def test_a_constant_compartment_is_not_recorded(self, sbml):
        # The Michaelis-Menten model's default compartment never changes.
        assert "compartment" not in {q.kind for q in recorded_quantities(sbml)}


class TestTheFluxIsTheRateLawNotCatervasVelocity:
    """The archive's flux and Caterva's `velocity` are different quantities.

    `scientificPipeline.ts` derives velocity by backward finite difference
    on the concentration series (forward at t=0). The SED-ML target is the
    EXACT rate-law value. Both are defensible; they are not the same number,
    and a reader comparing the archive's curve against Caterva's screen will
    find a small difference.

    `combine_archive.py` states that difference as **at most 0.082%
    relative** on this model at 101 points. A measured number sitting in a
    comment with nothing checking it is the kind of claim this project has
    caught itself making before — so it is checked here.
    """

    def finite_difference(self, times, values):
        """Caterva's velocity, reimplemented from its documented rule."""
        out = []
        for index, (t, s) in enumerate(zip(times, values)):
            if index > 0:
                dt = t - times[index - 1]
                out.append((values[index - 1] - s) / dt if dt else 0.0)
            else:
                dt = times[1] - t
                out.append((s - values[1]) / dt if dt else 0.0)
        return out

    def test_the_quoted_difference_is_real(self, sbml):
        runner = roadrunner.RoadRunner(sbml)
        runner.selections = ["time", "S", "J0"]
        result = runner.simulate(0, 20, 101)

        times = [float(row[0]) for row in result]
        substrate = [float(row[1]) for row in result]
        exact = [float(row[2]) for row in result]
        approximate = self.finite_difference(times, substrate)

        worst = max(
            abs(a - b) / b for a, b in zip(approximate, exact) if b
        )
        # The docstring in combine_archive.py says 0.082%. Pinned with a
        # little headroom: this asserts the claim is not wildly optimistic,
        # not that the solver is deterministic to the last digit.
        assert worst < 0.001, f"relative difference {worst:.5%} exceeds the quoted 0.082%"
        # And they are genuinely NOT identical -- if they were, the caveat
        # in the module would be misleading in the other direction.
        assert worst > 0

    def test_the_flux_target_points_at_the_reaction_list(self, sbml):
        flux = next(q for q in recorded_quantities(sbml) if q.kind == "reaction")
        assert flux.id == "J0"
        assert "listOfReactions" in flux.target
        assert "listOfSpecies" not in flux.target

    def test_the_flux_reaches_the_report(self, tmp_path, sbml):
        with zipfile.ZipFile(make_archive(tmp_path, sbml)) as opened:
            document = libsedml.readSedMLFromString(
                opened.read("simulation.sedml").decode()
            )
        report = document.getOutput(0)
        labels = {
            report.getDataSet(i).getLabel() for i in range(report.getNumDataSets())
        }
        assert "J0" in labels, (
            "an enzyme-kinetics archive that cannot produce the rate curve is "
            "missing the point of the experiment"
        )


class TestTheTargetsActuallyResolve:
    """The property that makes the report meaningful, and had nothing checking it.

    libSEDML stores targets as strings and never resolves them — it does not
    have the model. So a one-character typo in a generated XPath produces a
    document libSEDML calls valid, an archive that opens, and a report whose
    every column selects nothing.

    Demonstrated before this class existed: changing `listOfSpecies` to
    `listOfSpeciez` in `combine_archive.py` left **all 37 archive tests
    passing**. The replay tests miss it too, because they run the SBML
    directly with libRoadRunner and never read a target.
    """

    def test_every_generated_target_selects_exactly_one_element(self, tmp_path, sbml):
        with zipfile.ZipFile(make_archive(tmp_path, sbml)) as opened:
            resolution = resolve_targets(
                opened.read("model.xml").decode(),
                opened.read("simulation.sedml").decode(),
            )
        assert resolution.ok, resolution.unresolved
        # Species, species, reaction. The time generator uses a symbol
        # rather than a target and is correctly not counted here.
        assert len(resolution.resolved) == 3

    def test_a_typo_in_the_path_is_caught(self, tmp_path, sbml):
        """The exact mutation that survived everything else."""
        sedml, _ = build_sedml(
            model_location="model.xml",
            model_id="m",
            end_time=1.0,
            points=2,
            recorded=[RecordedQuantity("S", "species")],
        )
        broken = sedml.replace("listOfSpecies", "listOfSpeciez")

        resolution = resolve_targets(sbml, broken)
        assert not resolution.ok
        assert resolution.unresolved[0][2] == 0, "expected the target to select nothing"

    def test_a_target_naming_a_species_the_model_lacks_is_caught(self, sbml):
        sedml, _ = build_sedml(
            model_location="model.xml",
            model_id="m",
            end_time=1.0,
            points=2,
            recorded=[RecordedQuantity("NotInTheModel", "species")],
        )
        resolution = resolve_targets(sbml, sedml)
        assert not resolution.ok

    def test_the_time_symbol_is_not_counted_as_resolved(self, tmp_path, sbml):
        # `urn:sedml:symbol:time` is not an XPath. Counting it would be a
        # check reporting on something it never evaluated.
        with zipfile.ZipFile(make_archive(tmp_path, sbml)) as opened:
            resolution = resolve_targets(
                opened.read("model.xml").decode(),
                opened.read("simulation.sedml").decode(),
            )
        assert all("time" not in target for _, target in resolution.resolved)

    def test_a_malformed_xpath_is_reported_not_raised(self, sbml):
        # A crash here would be indistinguishable from the guard being
        # broken. It has to come back as a finding.
        sedml, _ = build_sedml(
            model_location="model.xml", model_id="m", end_time=1.0, points=2,
            recorded=[RecordedQuantity("S", "species")],
        )
        resolution = resolve_targets(sbml, sedml.replace("/sbml:sbml", "//["))
        assert not resolution.ok

    def test_the_namespace_comes_from_the_model_not_a_constant(self, tmp_path, sbml):
        """An SBML level bump must not make every target look broken.

        Hardcoding `level3/version2` would turn every XPath into a
        non-match the day Antimony emits something else — and the failure
        would read as "the archive is broken" when in fact the checker had
        stopped understanding the model.
        """
        from caterva.core.combine_archive import SBML_NS_FALLBACK

        # The fixture really is L3V2, so the fallback and the document agree
        # today. The check below is that the code READS it rather than
        # assuming it.
        assert SBML_NS_FALLBACK in sbml

        # Same model and targets, re-namespaced to a different SBML level.
        # If the namespace were a constant, every target would select zero.
        other = sbml.replace("level3/version2", "level3/version1")
        sedml, _ = build_sedml(
            model_location="model.xml", model_id="m", end_time=1.0, points=2,
            recorded=[RecordedQuantity("S", "species")],
        )
        resolution = resolve_targets(other, sedml)
        assert resolution.ok, resolution.unresolved
