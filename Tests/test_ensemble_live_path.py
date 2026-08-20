"""The ensemble without a fixture — the path a student actually has.

`scientific ensemble --fixture some.html` was the only way in, and a student
does not have a saved BRENDA table. The command existed and was effectively
unrunnable by the person it is for, which is the same "capability nobody can
reach" shape ADR 0122 was written about, one level up.

So the resolver now carries a SCORED FRONTIER on every result
(`KineticResult.ensemble_candidates`) and the ensemble draws from that. These
tests pin the join: that the scores really arrive, that they are the same
grades `score_reliability` produces, and that a failed resolution is reported
as a resolution failure rather than as an empty band.

Network is stubbed at the provider seam the resolver already exposes — the
same seam `test_fallback_logic.py` uses — so this exercises the real
resolution logic without touching BRENDA.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import fallback_logic  # noqa: E402
from ensemble import candidates_from_scored, sample_ensemble  # noqa: E402

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "brenda_ldh_fixture.html"


def resolve(**overrides):
    html = FIXTURE.read_text(encoding="utf-8")
    kwargs = dict(
        enzyme_name="lactate dehydrogenase",
        html_provider=lambda *a, **k: html,
        uniprot_provider=lambda *a, **k: None,
        taxon_id_provider=lambda *a, **k: None,
        search_literature=False,
    )
    kwargs.update(overrides)
    return fallback_logic.resolve_kinetic_value(
        "1.1.1.27", "Homo sapiens", "pyruvate", **kwargs
    )


class TestTheScoredFrontierArrives:
    def test_a_resolution_carries_every_surviving_row(self) -> None:
        result = resolve()
        assert result.found is True
        # Both published human values, not just the winner.
        values = sorted(c["value"] for c in result.ensemble_candidates)
        assert values == [0.03, 0.398]

    def test_the_winner_is_among_them_rather_than_replacing_them(self) -> None:
        """`min()` picks 0.03. The ensemble must still see 0.398, or the
        weighting has nothing to weigh and this is a spread of one.
        """
        result = resolve()
        assert result.value == 0.03
        assert 0.398 in [c["value"] for c in result.ensemble_candidates]

    def test_every_candidate_carries_all_three_axes(self) -> None:
        for candidate in resolve().ensemble_candidates:
            assert set(candidate["grades"]) == {
                "assay_completeness",
                "condition_proximity",
                "organism_match",
            }

    def test_the_grades_are_the_ones_score_reliability_produces(self) -> None:
        """One implementation, not two. If `_score_frontier` ever grew its own
        grading, this is where the drift would show.
        """
        import reliability

        expected = reliability.score_reliability(
            ph=None, temperature_c=None, unreported=[],
            requested_organism="Homo sapiens", measured_organism="Homo sapiens",
        )
        grades = resolve().ensemble_candidates[0]["grades"]
        assert grades["assay_completeness"] == expected.assay_completeness.grade
        assert grades["organism_match"] == expected.organism_match.grade

    def test_a_candidate_keeps_its_reference_so_it_stays_checkable(self) -> None:
        refs = [c["reference_id"] for c in resolve().ensemble_candidates]
        assert all(refs), "a value with no reference cannot be looked up"


class TestTheJoinToTheSampler:
    def test_the_resolver_output_samples_without_a_fixture(self) -> None:
        result = resolve()
        drawn = sample_ensemble(
            candidates_from_scored(result.ensemble_candidates), draws=500, seed=1
        )
        assert set(drawn.draws) == {0.03, 0.398}
        assert drawn.summary()["fold_range"] == pytest.approx(13.2666, rel=1e-3)

    def test_the_adapter_preserves_what_a_reader_needs(self) -> None:
        candidates = candidates_from_scored(resolve().ensemble_candidates)
        for candidate in candidates:
            assert candidate.unit == "mM"
            assert candidate.organism == "Homo sapiens"
            assert candidate.reference_id

    def test_the_literature_layer_does_not_import_the_sampler(self) -> None:
        """`ensemble_candidates` is plain dicts on purpose.

        If the resolver imported `ensemble` to build its own `Candidate`
        objects, the literature layer would depend on the sampler — backwards,
        and a circular import waiting to happen. The adapter lives on the
        sampler's side of that line, and this asserts the line is still there.
        """
        source = (Path(__file__).resolve().parent / "fallback_logic.py").read_text()
        assert "import ensemble" not in source
        assert "from ensemble" not in source


class TestAFailedResolutionIsNotAnEmptyBand:
    def test_nothing_resolved_yields_no_candidates(self) -> None:
        """An empty list must read as "nothing was resolved", which the caller
        reports as a resolution failure — never as a band with no members.
        """
        result = resolve(html_provider=lambda *a, **k: "<html><body></body></html>")
        assert result.found is False
        assert result.ensemble_candidates == []

    def test_the_sampler_refuses_an_empty_pool_rather_than_returning_one(self) -> None:
        result = resolve(html_provider=lambda *a, **k: "<html><body></body></html>")
        with pytest.raises(ValueError, match="no candidates"):
            sample_ensemble(
                candidates_from_scored(result.ensemble_candidates), draws=10, seed=1
            )
