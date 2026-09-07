"""Whether a set of parameters belongs in one model.

WHY THIS IS THE INTERESTING TEST FILE
-------------------------------------
Every value in the scavenged fixture below has a real citation and would
pass every provenance check Terrium already has. Individually they are
clean. Together they describe no enzyme in any organism under any
condition.

That gap -- individually valid, jointly incoherent -- is what a postdoc
checks by hand and no software checks at all. These tests pin the judgement
that closes it, and pin equally hard the two ways it could become
dishonest: reporting silence as compatibility, and computing a correction
nobody measured.
"""

from __future__ import annotations

import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from model_compatibility import (  # noqa: E402
    PH_UNITS_SERIOUS,
    TEMPERATURE_C_SERIOUS,
    ParameterSource,
    assess,
)

HUMAN = "Homo sapiens"
ECOLI = "Escherichia coli"


def clean_pair() -> list[ParameterSource]:
    """Two values anybody would be happy to combine."""
    return [
        ParameterSource("Km", 6.0, "mM", organism=HUMAN, ph=7.4,
                        temperature_c=37.0, buffer="HEPES"),
        ParameterSource("kcat", 118.0, "1/s", organism=HUMAN, ph=7.4,
                        temperature_c=37.0, buffer="HEPES"),
    ]


class TestTheCleanCase:
    def test_a_coherent_set_is_reported_coherent(self) -> None:
        report = assess(clean_pair())
        assert report.coherent
        assert report.findings == ()
        assert "mutually compatible" in report.summary()

    def test_a_single_parameter_produces_no_spread_findings(self) -> None:
        # A spread needs two values. A version that compared a value with
        # itself, or with a default, would invent a finding out of nothing.
        report = assess([clean_pair()[0]])
        assert report.coherent
        assert report.findings == ()


class TestOrganismCoherence:
    def test_two_organisms_is_blocking_not_merely_serious(self) -> None:
        # No assay condition makes constants from two species commensurate,
        # so this is the one category that cannot be argued away by
        # matching conditions.
        sources = clean_pair()
        sources[1] = ParameterSource(
            "kcat", 118.0, "1/s", organism=ECOLI, ph=7.4,
            temperature_c=37.0, buffer="HEPES",
        )
        report = assess(sources)
        assert not report.coherent
        blocking = report.blocking
        assert len(blocking) == 1
        assert blocking[0].kind == "organism_mismatch"
        # Names BOTH organisms and which value came from which -- a finding
        # that said only "mismatch" would leave the reader to re-derive it.
        assert HUMAN in blocking[0].detail
        assert ECOLI in blocking[0].detail
        assert "kcat" in blocking[0].detail

    def test_a_transferred_value_is_flagged_even_when_alone(self) -> None:
        # ADR 0024's cross-species tier, carried up to the set. One value,
        # so there is no organism MISMATCH -- but it is still not the
        # organism that was asked about.
        report = assess([
            ParameterSource("Km", 6.0, "mM", organism=ECOLI, ph=7.4,
                            temperature_c=37.0, cross_species=True),
        ])
        kinds = {f.kind for f in report.findings}
        assert "cross_species_value" in kinds
        assert "organism_mismatch" not in kinds


class TestAssayConditions:
    def test_a_ph_gap_at_the_threshold_is_serious(self) -> None:
        sources = clean_pair()
        sources[1] = ParameterSource(
            "kcat", 118.0, "1/s", organism=HUMAN,
            ph=7.4 - PH_UNITS_SERIOUS, temperature_c=37.0, buffer="HEPES",
        )
        report = assess(sources)
        finding = next(f for f in report.findings if f.kind == "ph_mismatch")
        assert finding.severity == "serious"
        assert not report.coherent

    def test_a_ph_gap_below_the_threshold_is_not_reported(self) -> None:
        # The threshold has to bite in both directions, or it is not a
        # threshold and every model with any variation is flagged.
        sources = clean_pair()
        sources[1] = ParameterSource(
            "kcat", 118.0, "1/s", organism=HUMAN,
            ph=7.4 - PH_UNITS_SERIOUS * 0.5, temperature_c=37.0,
            buffer="HEPES",
        )
        report = assess(sources)
        assert not any(f.kind == "ph_mismatch" for f in report.findings)
        assert report.coherent

    def test_a_temperature_gap_is_serious_and_states_its_direction(self) -> None:
        sources = clean_pair()
        sources[1] = ParameterSource(
            "kcat", 118.0, "1/s", organism=HUMAN, ph=7.4,
            temperature_c=37.0 - TEMPERATURE_C_SERIOUS - 2, buffer="HEPES",
        )
        report = assess(sources)
        finding = next(
            f for f in report.findings if f.kind == "temperature_mismatch"
        )
        assert finding.severity == "serious"
        assert "12 C apart" in finding.detail
        # Q10 is the real, citable basis for saying what the gap means.
        assert "Q10" in finding.detail

    def test_it_reports_the_gap_and_refuses_to_correct_it(self) -> None:
        """The line between a finding and a fabrication.

        Multiplying a kcat by 2.3 and calling it temperature-corrected
        would be trivial and would produce a number nobody measured, since
        the true Q10 for a given enzyme is itself an unlooked-up quantity.
        The report must say so rather than quietly not doing it.
        """
        sources = clean_pair()
        sources[1] = ParameterSource(
            "kcat", 118.0, "1/s", organism=HUMAN, ph=7.4,
            temperature_c=25.0, buffer="HEPES",
        )
        report = assess(sources)
        finding = next(
            f for f in report.findings if f.kind == "temperature_mismatch"
        )
        assert "not corrected" in finding.detail
        # And no corrected value appears anywhere in the report.
        assert not hasattr(finding, "corrected_value")

    def test_different_buffers_are_reported(self) -> None:
        sources = clean_pair()
        sources[1] = ParameterSource(
            "kcat", 118.0, "1/s", organism=HUMAN, ph=7.4,
            temperature_c=37.0, buffer="phosphate",
        )
        report = assess(sources)
        assert any(f.kind == "buffer_mismatch" for f in report.findings)


class TestTheThirdCategory:
    """Silence is not compatibility. This is what STRENDA is for."""

    def test_unpublished_conditions_are_their_own_severity(self) -> None:
        sources = clean_pair()
        sources[1] = ParameterSource(
            "kcat", 118.0, "1/s", organism=HUMAN, ph=None,
            temperature_c=None, buffer="HEPES",
        )
        report = assess(sources)
        finding = next(
            f for f in report.findings if f.kind == "conditions_unpublished"
        )
        assert finding.severity == "unassessable"
        assert "kcat" in report.unassessable
        # Names what specifically was missing, so the reader knows what to
        # go and look for.
        assert "pH" in finding.detail and "temperature" in finding.detail

    def test_unassessable_is_neither_pass_nor_fail(self) -> None:
        """The judgement that would be easiest to get wrong in either
        direction.

        Counting it as failure makes every model with one under-reported
        source unusable. Counting it as success is the silence-as-
        compatibility error that lets a wrong model through quietly. It is
        reported and left to the reader, and `coherent` means only that
        nothing checkable was found wrong.
        """
        sources = clean_pair()
        sources[1] = ParameterSource(
            "kcat", 118.0, "1/s", organism=HUMAN, ph=None,
            temperature_c=None, buffer="HEPES",
        )
        report = assess(sources)
        assert report.coherent, "an unchecked condition is not a failure"
        assert report.unassessable, "and it must not vanish either"
        assert "could not be checked at all" in report.summary()


class TestUserMeasurements:
    def test_a_users_own_value_is_not_judged_against_a_paper(self) -> None:
        # Combining your own bench measurement with literature is the
        # normal case this tool exists to support, not a defect. A user
        # value carries no organism or conditions and must not therefore
        # count as a mismatch or as unassessable.
        sources = clean_pair()
        sources.append(
            ParameterSource("enzyme_conc", 5e-5, "mM", origin="user")
        )
        report = assess(sources)
        assert report.coherent
        assert "enzyme_conc" not in report.unassessable


class TestTheRealisticCase:
    def test_the_scavenged_model_is_caught_on_every_axis(self) -> None:
        """The case this module exists for.

        Every value below has a genuine citation and would pass each
        existing provenance check on its own.
        """
        scavenged = [
            ParameterSource("Km", 6.0, "mM", organism=HUMAN, ph=7.4,
                            temperature_c=37.0, buffer="HEPES",
                            citation="BRENDA ref 641068"),
            ParameterSource("kcat", 118.0, "1/s", organism=ECOLI, ph=6.0,
                            temperature_c=25.0, buffer="phosphate",
                            citation="BRENDA ref 12345", cross_species=True),
            ParameterSource("Ki", 0.4, "mM", organism=HUMAN,
                            citation="BRENDA ref 99999"),
            ParameterSource("enzyme_conc", 5e-5, "mM", origin="user"),
        ]
        report = assess(scavenged)
        kinds = {f.kind for f in report.findings}

        assert not report.coherent
        for expected in (
            "organism_mismatch",
            "cross_species_value",
            "ph_mismatch",
            "temperature_mismatch",
            "buffer_mismatch",
            "conditions_unpublished",
        ):
            assert expected in kinds, f"{expected} was not caught"

        # The user's own value is not one of the problems.
        assert "enzyme_conc" not in report.unassessable
        assert report.unassessable == ("Ki",)

    def test_nothing_is_reported_for_an_empty_set(self) -> None:
        report = assess([])
        assert report.findings == ()
        assert "No parameters" in report.summary()
