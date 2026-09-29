"""How many replicas a question needs, from the spread they show.

Checked by hand against printed t tables: t(0.975, 1) = 12.706, t(0.975, 8)
= 2.306, t(0.975, 9) = 2.262. For a replica SD of 0.067 nm: two replicas give
a 95% interval of 12.706 x 0.067 / sqrt(2) = 0.602 nm; nine give 0.0515 nm,
still above 0.05; ten give 0.0479 nm. So ten are needed for +/- 0.05 nm.
"""
from __future__ import annotations

import math

import pytest

from caterva.md import convergence as cv


def test_student_t_matches_the_printed_table():
    assert cv.t_quantile(1) == pytest.approx(12.706, abs=1e-3)
    assert cv.t_quantile(8) == pytest.approx(2.306, abs=1e-3)
    assert cv.t_quantile(1000) == pytest.approx(1.962, abs=1e-3)


def test_interval_and_replicas_needed_by_hand():
    assert cv.ci_halfwidth(0.067, 2) == pytest.approx(0.602, abs=1e-3)
    assert cv.ci_halfwidth(0.067, 9) == pytest.approx(0.0515, abs=1e-4)
    assert cv.replicas_needed(0.067, 0.05, have=2) == 10


def test_edge_cases():
    assert math.isnan(cv.ci_halfwidth(0.1, 1))
    assert cv.replicas_needed(float("nan"), 0.05, have=2) is None
    assert cv.replicas_needed(0.0, 0.05, have=3) == 3
    assert cv.replicas_needed(100.0, 1e-6, have=2, cap=50) is None


def _summary(means):
    series = [(f"rep{i + 1}", [m] * 40) for i, m in enumerate(means)]
    return cv.summarise(series, "distance", "nm")


def test_the_summary_carries_the_interval_into_its_report():
    s = _summary([0.30, 0.31, 0.29])
    assert s.ci95 == pytest.approx(cv.t_quantile(2) * 0.01 / math.sqrt(3))
    assert "95% confidence interval of the mean" in "\n".join(cv.report(s))
    assert s.replicas_for(1.0) == 3  # already enough


def test_one_replica_has_no_interval():
    s = _summary([0.3])
    assert math.isnan(s.ci95) and s.replicas_for(0.05) is None
