"""Sensitivity checked against closed form, and the audit that uses it.

WHY THE CLOSED-FORM TEST IS THE ONE THAT MATTERS
------------------------------------------------
This machinery produces a RANKING, and a ranking is exactly the kind of
output that looks right when it is wrong. Plausible orderings are easy to
generate; a sign error, a missing normalisation or a transposed index all
yield a list that a reader will nod at.

So the numerics are checked against a model whose sensitivities are
derivable by hand rather than against this implementation's own output.

For first-order decay, A' = -k*A, the solution is A(t) = A0*exp(-k*t), so:

    S(A, k)  = (dA/dk)(k/A)  = (-t*A0*e^-kt)(k / A0*e^-kt)  = -k*t
    S(A, A0) = (dA/dA0)(A0/A) = (e^-kt)(A0 / A0*e^-kt)      = 1

Both exact, both independent of the solver, and one of them varies with
time while the other does not -- so a bug that produced a constant, or that
lost the time dependence, fails one of them.

Measured: |S_k| at t=10, k=0.3 comes back 3.0000045 against an exact 3.0,
and S_A0 comes back 1.0000000002 against an exact 1. The k error is ~4.5e-6,
which is the O(h^2) truncation of a central difference at h=1e-3 relative
-- i.e. the error is the one the method is supposed to have, not a defect
hiding at the same magnitude.
"""

from __future__ import annotations

import pytest

from Terium.continuous.model_building import antimony_to_sbml
from Terium.continuous.simulations import simulate_sbml
from Terium.core.model_audit import (
    INFLUENCE_FLOOR,
    TIER_LITERATURE_FLAGGED,
    TIER_LITERATURE_MATCHED,
    TIER_MEASURED_HERE,
    TIER_UNSOURCED,
    audit,
    classify_source,
)
from Terium.core.network import (
    Parameter,
    Reaction,
    ReactionNetwork,
    Species,
    compile_to_antimony,
)
from Terium.core.network_provenance import QuantitySource
from Terium.core.sensitivity import analyse

K, A0, END, POINTS = 0.3, 100.0, 10.0, 51


def _simulate(network: ReactionNetwork):
    return simulate_sbml(
        antimony_to_sbml(compile_to_antimony(network)), 0.0, END, POINTS
    )


def _decay() -> ReactionNetwork:
    """A' = -k*A. Closed form: A(t) = A0*exp(-k*t)."""
    return ReactionNetwork(
        name="decay",
        species=(Species("A", A0),),
        parameters=(Parameter("k", K),),
        reactions=(Reaction("R", {"A": 1}, {}, "k * A"),),
    )


class TestAgainstClosedForm:
    def test_sensitivity_to_the_rate_constant_is_k_times_t(self) -> None:
        report = analyse(_decay(), _simulate)
        k = next(r for r in report.ranked if r.quantity == "k")
        # Exact: |S| = k*t, peaking at the end of the run.
        assert k.peak == pytest.approx(K * END, abs=1e-4)
        assert k.peak_time == pytest.approx(END)
        assert k.peak_species == "A"

    def test_sensitivity_to_the_initial_amount_is_exactly_one(self) -> None:
        report = analyse(_decay(), _simulate)
        a = next(r for r in report.ranked if r.quantity == "A")
        # Exact: S = 1 everywhere. A method that lost the normalisation
        # would return A0 (=100) here, and one that lost the time
        # dependence in the test above would still pass that one.
        assert a.peak == pytest.approx(1.0, abs=1e-6)

    def test_the_error_is_the_method_s_own_truncation(self) -> None:
        """Pins that the residual is O(h^2), not something else at that size.

        If a future change makes this fail, the question to ask is whether
        the step, the differencing scheme or the solver tolerance moved --
        not whether to widen the bound.
        """
        report = analyse(_decay(), _simulate)
        k = next(r for r in report.ranked if r.quantity == "k")
        error = abs(k.peak - K * END)
        assert error < 1e-4, "far larger than central-difference truncation"
        assert error > 1e-9, (
            "suspiciously exact for a finite difference -- check the "
            "perturbation is actually being applied"
        )


class TestRanking:
    def test_ranked_by_influence_descending(self) -> None:
        report = analyse(_decay(), _simulate)
        peaks = [r.peak for r in report.ranked]
        assert peaks == sorted(peaks, reverse=True)
        # k (|S| = 3) must outrank A0 (|S| = 1).
        assert report.ranked[0].quantity == "k"

    def test_a_quantity_the_result_does_not_depend_on_is_marked_negligible(
        self,
    ) -> None:
        # `spectator` appears in no rate law, so nothing can depend on it.
        network = ReactionNetwork(
            name="with_spectator",
            species=(Species("A", A0),),
            parameters=(Parameter("k", K), Parameter("spectator", 42.0)),
            reactions=(Reaction("R", {"A": 1}, {}, "k * A"),),
        )
        report = analyse(network, _simulate)
        spectator = next(r for r in report.ranked if r.quantity == "spectator")
        assert spectator.negligible
        assert spectator.peak == pytest.approx(0.0, abs=1e-9)

    def test_a_zero_valued_quantity_is_excluded_and_said_so(self) -> None:
        # A relative sensitivity is undefined at zero. Excluding it is
        # correct; excluding it SILENTLY would shrink the denominator.
        network = ReactionNetwork(
            name="with_zero",
            species=(Species("A", A0), Species("B", 0.0)),
            parameters=(Parameter("k", K),),
            reactions=(Reaction("R", {"A": 1}, {"B": 1}, "k * A"),),
        )
        report = analyse(network, _simulate)
        assert "B" not in {r.quantity for r in report.ranked}
        assert any("exactly zero" in c for c in report.caveats)

    def test_the_standing_caveats_are_always_attached(self) -> None:
        # A local ranking printed without them implies a global claim.
        report = analyse(_decay(), _simulate)
        blob = " ".join(report.caveats).lower()
        assert "local" in blob
        assert "not about nature" in blob or "wrong thing" in blob


class TestSourceClassification:
    def test_user_supplied_is_their_own_measurement(self) -> None:
        assert classify_source(QuantitySource("user")) == TIER_MEASURED_HERE

    def test_missing_is_unsourced(self) -> None:
        assert classify_source(None) == TIER_UNSOURCED

    def test_a_clean_citation_is_matched_literature(self) -> None:
        source = QuantitySource(
            "resolved", citation="BRENDA ref 641068, Homo sapiens, pH 7.4, 37 C"
        )
        assert classify_source(source) == TIER_LITERATURE_MATCHED

    @pytest.mark.parametrize(
        "citation",
        [
            "BRENDA ref 12345, flagged: assay temperature not reported",
            "BRENDA ref 641068 (cross-species: S. cerevisiae)",
            "BRENDA ref 99, cross species transfer",
        ],
    )
    def test_a_demoted_citation_is_flagged(self, citation: str) -> None:
        # Reads the vocabulary the rest of the codebase already uses
        # (ADR 0021's STRENDA demotion, ADR 0024's cross-species tier)
        # rather than re-deriving what "flagged" means.
        assert (
            classify_source(QuantitySource("resolved", citation=citation))
            == TIER_LITERATURE_FLAGGED
        )

    @pytest.mark.parametrize("origin", ["llm", "default"])
    def test_a_blocked_origin_is_unsourced(self, origin: str) -> None:
        # These never reach a compiled model, but an audit of a REJECTED
        # model should still read rather than raise.
        assert classify_source(QuantitySource(origin)) == TIER_UNSOURCED


class TestAudit:
    def _audited(self, sources):
        network = _decay()
        return audit(network, analyse(network, _simulate), sources)

    def test_influence_ranks_the_list_and_provenance_does_not(self) -> None:
        """The property that keeps this honest.

        The two orderings are made to DISAGREE, deliberately. `k` dominates
        (|S| = 3) and is the WORST sourced; `A` matters less (|S| = 1) and is
        the best sourced. Influence says [k, A]; provenance tier says
        [A, k]. The result must be [k, A].

        A first version had `k` both dominant and well-sourced, so the two
        orderings agreed and the test could not tell them apart -- sorting
        the audit by tier passed it unchanged. A test whose two hypotheses
        predict the same output is not testing between them.
        """
        result = self._audited(
            {
                # Most influential, worst sourced.
                "k": QuantitySource("resolved", citation="ref 9, flagged: no temperature"),
                # Least influential, best sourced.
                "A": QuantitySource(
                    "resolved", citation="BRENDA ref 1, Homo sapiens, pH 7.4, 37 C"
                ),
            }
        )
        assert [q.quantity for q in result.quantities] == ["k", "A"], (
            "ordering followed provenance rather than measured influence"
        )
        assert result.quantities[0].tier == TIER_LITERATURE_FLAGGED
        assert result.quantities[1].tier == TIER_LITERATURE_MATCHED

    def test_to_measure_is_influential_and_weakly_sourced(self) -> None:
        result = self._audited(
            {
                "k": QuantitySource("resolved", citation="ref 1, flagged: no temperature"),
                "A": QuantitySource("user"),
            }
        )
        # k is influential and flagged -> worth measuring.
        # A is influential and the user's own -> not this tool's business.
        assert [q.quantity for q in result.to_measure] == ["k"]

    def test_a_well_sourced_influential_quantity_is_not_busywork(self) -> None:
        result = self._audited(
            {
                "k": QuantitySource("resolved", citation="ref 1, Homo sapiens, pH 7.4"),
                "A": QuantitySource("user"),
            }
        )
        assert result.to_measure == ()
        assert "matched literature or your own" in result.summary()

    def test_a_negligible_quantity_is_never_recommended(self) -> None:
        """A report that only ever adds work gets closed.

        `spectator` is unsourced -- the worst tier -- but nothing depends on
        it, so telling someone to go and measure it would waste a morning.
        """
        network = ReactionNetwork(
            name="with_spectator",
            species=(Species("A", A0),),
            parameters=(Parameter("k", K), Parameter("spectator", 42.0)),
            reactions=(Reaction("R", {"A": 1}, {}, "k * A"),),
        )
        result = audit(
            network,
            analyse(network, _simulate),
            {"A": QuantitySource("user"), "k": QuantitySource("user")},
        )
        spectator = next(q for q in result.quantities if q.quantity == "spectator")
        assert spectator.tier == TIER_UNSOURCED
        assert not spectator.influential
        assert spectator not in result.to_measure

    def test_the_denominator_counts_the_whole_model(self) -> None:
        """The reporting defect this test exists for.

        A first version said "5 of 5 quantities control this result" for a
        model with seven, having silently dropped the two it could not
        rank. That reads as full coverage of a model that was
        two-sevenths unexamined.
        """
        network = ReactionNetwork(
            name="with_zero",
            species=(Species("A", A0), Species("B", 0.0)),
            parameters=(Parameter("k", K),),
            reactions=(Reaction("R", {"A": 1}, {"B": 1}, "k * A"),),
        )
        result = audit(
            network,
            analyse(network, _simulate),
            {q: QuantitySource("user") for q in network.quantity_ids()},
        )
        assert len(result.unranked) == 1
        assert result.unranked[0][0] == "B"
        summary = result.summary()
        assert "model's 3 quantities" in summary
        assert "could not be ranked" in summary

    def test_no_score_is_invented(self) -> None:
        """Pins the design decision, so a later 'improvement' has to argue.

        Combining measured influence with a categorical provenance tier
        needs weights nobody has measured. Adding a scoring system whose
        constants were invented, in order to rank the trustworthiness of
        measurements, would be the most ironic possible regression in this
        codebase.
        """
        result = self._audited({"k": QuantitySource("user"), "A": QuantitySource("user")})
        quantity = result.quantities[0]
        assert not hasattr(quantity, "score")
        assert not hasattr(quantity, "risk")
        assert any("never combined into a score" in c for c in result.caveats)

    def test_the_influence_floor_is_stated_not_buried(self) -> None:
        result = self._audited({"k": QuantitySource("user"), "A": QuantitySource("user")})
        assert any(str(INFLUENCE_FLOOR) in c for c in result.caveats)
