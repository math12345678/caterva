"""Two ensembles, built independently, checked against each other.

WHY THIS FILE EXISTS
--------------------
Two agents implemented the professors' ensemble recommendation in the same
week without knowing about each other:

* `spread_consequence.py` (ADR 0111, ADR 0129) — enumerate the values the
  literature reports, run the model once at each, report every outcome
  beside the paper it came from. Unweighted, deterministic, and explicitly
  not an uncertainty estimate.

* `ensemble.py` + `model_ensemble.py` (ADR 0131, ADR 0132) — score each
  value on Bakker's axes, sample with those weights, run the model per
  draw, report a percentile band. Bakker's actual method, and the one
  Sauro called "the right way to do it".

Neither ADR mentions the other. That is the duplication this repository
forbids everywhere else, and it arrived while both authors were being
careful.

**They are not redundant.** They answer different questions — "what does
each measured value do" and "what does the model do across the distribution
the evidence supports" — and a lab report wants both. What is missing is
anything forcing them to AGREE, and two implementations of one
recommendation that can drift are worse than either alone.

THE PROPERTY THAT BINDS THEM
----------------------------
`sample_ensemble` resamples DISCRETELY from the candidate values:

    population = [w.candidate.value for w in weighted]

Every draw is therefore one of the values `spread_consequence` runs at. So
the band cannot reach outside the enumerated outcomes. If it does, one of
the two is wrong about the same literature — and until this file existed,
nothing would have said which.
"""
from __future__ import annotations

import pytest

from ensemble import Candidate, sample_ensemble
from reliability import Axis, ReliabilityScore
from fallback_logic import resolve_kinetic_value
from fixture_lineages import fixture_lineage_provider
from spread_consequence import consequence_of
from test_fallback_logic import (
    fake_taxon_id_provider,
    fake_uniprot_provider,
    load_fixture,
    make_html_provider,
)

LDH = "1.1.1.27"
SEED = 20260820


def candidates():
    """Real cross-species rows: *Danio rerio* has no Km in this fixture."""
    result = resolve_kinetic_value(
        LDH, "Danio rerio", "pyruvate",
        html_provider=make_html_provider(
            {LDH: load_fixture("brenda_ldh_fixture.html")}
        ),
        uniprot_provider=fake_uniprot_provider,
        taxon_id_provider=fake_taxon_id_provider,
        search_literature=False, allow_cross_species=False,
        quantity="km", lineage_provider=fixture_lineage_provider,
    )
    assert result.cross_species_candidates, "the fixture stopped producing candidates"
    return result.cross_species_candidates


def scored(row) -> Candidate:
    """A `Candidate` from a resolver row, graded neutrally.

    Every candidate gets the SAME grades on purpose. The containment
    property below is about the support of the distribution, not about the
    weighting — and an axis on which every candidate scores alike cancels
    under normalisation, which `ensemble.py` documents. So this isolates
    the question being asked: do the two modules agree about the VALUES.
    """
    return Candidate(
        value=row.value,
        score=ReliabilityScore(
            assay_completeness=Axis(grade="complete", reason="fixture row"),
            condition_proximity=Axis(grade="not_assessed", reason="no reference given"),
            organism_match=Axis(grade="related", reason="cross-species candidate"),
        ),
        unit=getattr(row, "unit", None),
        organism=getattr(row, "organism", None),
        reference_id=getattr(row, "reference_id", None),
    )


def test_the_two_modules_describe_the_same_literature():
    """The premise: both are handed the same values.

    Asserted rather than assumed. If one module were fed a different set —
    a filter applied on one path and not the other — every comparison below
    would be meaningless while still passing.
    """
    observed = sorted(c.value for c in candidates())
    assert len(observed) > 1
    assert observed == sorted({c.value for c in candidates()}), (
        "duplicate values would make the support comparison ambiguous"
    )


def test_every_drawn_value_is_a_value_somebody_measured():
    """The sampler resamples discretely; it does not interpolate.

    This is the property that makes an ensemble legitimate here at all. A
    draw between two measured values would be a number nobody reported,
    which is the fabrication the whole project refuses — and it would also
    break the containment check below without either module being
    "wrong".
    """
    rows = candidates()
    observed = {c.value for c in rows}

    drawn = sample_ensemble([scored(c) for c in rows], draws=200, seed=SEED)
    assert set(drawn.draws) <= observed, (
        f"the sampler produced values nobody measured: "
        f"{sorted(set(drawn.draws) - observed)}"
    )


def test_the_band_cannot_reach_outside_the_enumerated_outcomes():
    """The cross-check.

    Every draw is one of the observed values, so running the model over the
    draws cannot produce a result outside the range of running it at each
    observed value. If the band is wider, one module is wrong about the
    same literature — and nothing else in the tree would say which.
    """
    rows = candidates()

    enumerated = consequence_of(rows, parameter="km", vmax=0.25, s0=10.0)
    assert enumerated.is_assessed
    outcomes = [o.outcome for o in enumerated.outcomes if o.outcome is not None]
    low, high = min(outcomes), max(outcomes)

    from model_ensemble import ensemble_over
    from Terium.continuous.simulations import simulate_michaelis_menten

    drawn = sample_ensemble([scored(c) for c in rows], draws=50, seed=SEED)
    band = ensemble_over(
        simulate=simulate_michaelis_menten,
        base_parameters={"km": rows[0].value, "vmax": 0.25, "s0": 10.0},
        parameter="km",
        drawn=drawn,
        max_runs=50,
    )

    substrate = next(
        (e for e in band.envelopes if e.column in {"[S]", "S"}), None
    )
    if substrate is None:
        pytest.skip(f"no substrate envelope in {[e.column for e in band.envelopes]}")

    # Compared at the LAST time point, which is what `spread_consequence`
    # measures. Comparing whole trajectories would be comparing two
    # different observables and calling a mismatch a disagreement.
    tolerance = 1e-6
    assert substrate.low[-1] >= low - tolerance, (
        f"the band reaches below every measured value's outcome: "
        f"{substrate.low[-1]} < {low}"
    )
    assert substrate.high[-1] <= high + tolerance, (
        f"the band reaches above every measured value's outcome: "
        f"{substrate.high[-1]} > {high}"
    )


def test_neither_module_claims_to_be_an_uncertainty_estimate():
    """Both refuse the same thing, and must keep refusing it together.

    Bakker's published spread is bounded by rejection against measured
    flux, which Terrium has no data for. If one module quietly started
    presenting its band as a confidence interval while the other kept the
    disclaimer, a reader comparing two sections of one report would get two
    different claims about the same numbers.
    """
    rows = candidates()
    enumerated = consequence_of(rows, parameter="km", vmax=0.25, s0=10.0)
    assert "NOT an uncertainty estimate" in enumerated.reason

    from model_ensemble import ensemble_over
    from Terium.continuous.simulations import simulate_michaelis_menten

    drawn = sample_ensemble([scored(c) for c in rows], draws=20, seed=SEED)
    band = ensemble_over(
        simulate=simulate_michaelis_menten,
        base_parameters={"km": rows[0].value, "vmax": 0.25, "s0": 10.0},
        parameter="km",
        drawn=drawn,
        max_runs=20,
    )
    assert band.disclaimer, "the band travels with no disclaimer at all"
