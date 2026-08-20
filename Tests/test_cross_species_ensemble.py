"""Sauro's ensemble, where the value is genuinely unknown.

    I thought you'd decided to build an ensemble when values are unknown?
        — Herbert Sauro, asked whether to default a missing value or refuse

That reply dissolves the question rather than answering it, and it is the
second professor to point at an ensemble after Barbara Bakker. The two are
talking about different situations:

    Bakker  values EXIST and disagree      -> ADR 0111 (the tie)
    Sauro   no value for THIS organism     -> here

Three existing options, all of them bad:

    default 0.5     invents a number
    refuse          gives a student nothing
    proxy           presents a rabbit's Km as a human's — Jeske's objection

Running the model at every organism's MEASURED value is none of the three,
and the refusal already held those values: `broad` carried them and only the
organism names survived.
"""
from __future__ import annotations

import pytest

from fallback_logic import resolve_kinetic_value
from fixture_lineages import fixture_lineage_provider
from selection_tie import TiedCandidate
from spread_consequence import consequence_of
from test_fallback_logic import (
    fake_taxon_id_provider,
    fake_uniprot_provider,
    load_fixture,
    make_html_provider,
)

LDH = "1.1.1.27"


def withheld():
    """A real withheld result: *Danio rerio* has no Km in this fixture."""
    return resolve_kinetic_value(
        LDH, "Danio rerio", "pyruvate",
        html_provider=make_html_provider(
            {LDH: load_fixture("brenda_ldh_fixture.html")}
        ),
        uniprot_provider=fake_uniprot_provider,
        taxon_id_provider=fake_taxon_id_provider,
        search_literature=False,
        allow_cross_species=False,
        quantity="km",
        lineage_provider=fixture_lineage_provider,
    )


# ---------------------------------------------------------------------------
# The refusal knew the numbers
# ---------------------------------------------------------------------------


def test_the_withheld_result_carries_values_not_just_organism_names():
    result = withheld()
    assert result.source == "cross_species_withheld"
    assert result.cross_species_candidates, (
        "the rows these organism names came from carried values, and the "
        "refusal discarded them"
    )
    assert all(c.value is not None for c in result.cross_species_candidates)


def test_every_candidate_is_checkable():
    """A named alternative can be argued with; a bare number cannot.

    Same reasoning as `TiedCandidate.reference_id`: a reader offered an
    ensemble needs to be able to go and read the papers it was built from.
    """
    for candidate in withheld().cross_species_candidates:
        assert candidate.organism
        assert candidate.reference_id, f"{candidate.value} has no reference"


def test_the_names_and_the_values_agree():
    """Two fields describing one set of rows.

    An organism named with no value behind it, or a value from an organism
    the list does not mention, would be two answers to one question — the
    drift ADR 0003 exists about.
    """
    result = withheld()
    from_candidates = sorted(
        {c.organism for c in result.cross_species_candidates if c.organism}
    )
    assert from_candidates == sorted(result.cross_species_organisms_available)


# ---------------------------------------------------------------------------
# Nothing is presented as the requested organism's value
# ---------------------------------------------------------------------------


def test_the_refusal_still_refuses():
    """The ensemble is offered INSTEAD of a substitution, not as one.

    Jeske's objection was to a rabbit's Km being returned as a human's.
    Carrying the rabbit's number so a student can see what it does is a
    different act from returning it as the answer, and the difference has
    to survive in the fields: `found` stays False and `value` stays None.
    """
    result = withheld()
    assert result.found is False
    assert result.value is None
    assert result.organism is None


def test_no_candidate_is_marked_selected():
    """`selected` means "this is the row that was returned". Nothing was."""
    assert not any(c.selected for c in withheld().cross_species_candidates)


# ---------------------------------------------------------------------------
# One ensemble mechanism, two sources of candidates
# ---------------------------------------------------------------------------


def test_the_tie_machinery_consumes_these_unchanged():
    """The property that makes this one mechanism rather than two.

    `spread_consequence.consequence_of` was written for ADR 0111's tie —
    several values the evidence ranked equal. These are several values from
    different organisms. Both are "the literature reports these numbers and
    Terrium will not pick between them", so both go through the same code,
    and `cross_species_candidates` is shaped as `TiedCandidate` for exactly
    that reason.

    A second ensemble implementation would be a second place the reasoning
    could drift.
    """
    result = withheld()
    verdict = consequence_of(
        result.cross_species_candidates, parameter="km", vmax=0.25, s0=10.0
    )

    assert verdict.is_assessed
    assert len(verdict.outcomes) == len(result.cross_species_candidates)
    # The values simulated are the measured ones, and no others.
    assert sorted(o.value for o in verdict.outcomes) == sorted(
        c.value for c in result.cross_species_candidates
    )


def test_the_ensemble_still_refuses_to_invent_the_experiment():
    """Sauro's ensemble does not exempt anything from ADR 0111's refusals.

    `s0` is the student's experiment, not the enzyme's property, and an
    ensemble over organisms does not make it knowable.
    """
    verdict = consequence_of(
        withheld().cross_species_candidates, parameter="km", vmax=0.25
    )
    assert verdict.status == "not_assessed"
    assert "s0 not supplied" in verdict.reason


def test_one_cross_species_value_is_not_an_ensemble():
    """Nothing turned on the choice, so there is nothing to propagate.

    An "ensemble" over a single value would report a spread of zero and
    look like a result.
    """
    one = [TiedCandidate(value=0.5, organism="Homo sapiens", reference_id="1")]
    verdict = consequence_of(one, parameter="km", vmax=0.25, s0=10.0)
    assert verdict.status == "not_assessed"
    assert "Nothing turned on the choice" in verdict.reason


# ---------------------------------------------------------------------------
# It stays quiet when it does not apply
# ---------------------------------------------------------------------------


def test_a_resolved_result_carries_no_cross_species_candidates():
    """The requested organism had a value. There is no ensemble to offer,
    and offering one would imply a doubt the evidence does not support."""
    result = resolve_kinetic_value(
        LDH, "Homo sapiens", "pyruvate",
        html_provider=make_html_provider(
            {LDH: load_fixture("brenda_ldh_fixture.html")}
        ),
        uniprot_provider=fake_uniprot_provider,
        taxon_id_provider=fake_taxon_id_provider,
        search_literature=False,
        allow_cross_species=False,
        quantity="km",
        lineage_provider=fixture_lineage_provider,
    )
    assert result.found
    assert result.cross_species_candidates == []
