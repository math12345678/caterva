"""`caterva rates`: do the 95% profile intervals contain the truth 95% of the time?

A SEEDED COVERAGE STUDY ON SYNTHETIC DATA
-----------------------------------------
Every dataset here is SYNTHETIC: rates computed from a rate law at stated
constants plus normal noise of a stated size, drawn from
numpy.random.default_rng with a fixed seed (ADR 0005), 300 datasets per
case. That is what a coverage study is, and it is the only place such data
are used. Each case refits every dataset exactly as the command does (the
multi-start fit, then the profile) and counts how often the interval holds
the constant the rates were made from.

With 300 datasets the count's own binomial standard error at 0.95 is
sqrt(0.95 * 0.05 / 300) = 0.0126, so a correct procedure lands within
3 of those (0.912 to 0.988) except about 3 times in a thousand.

WHAT THIS STUDY CANNOT CATCH
----------------------------
A band that wide does not tell the normal quantile from Student's t at
these sample sizes. With sigma from the residuals (12 rows, 2 constants,
10 degrees of freedom) a z threshold on a t(10) statistic covers with
probability 2 * P(T10 < 1.96) - 1 = 0.922, inside the band; with sigma from
replicates (6 degrees of freedom) it is 0.902, just below it, and a draw of
300 still lands inside about a quarter of the time. Telling those apart by
coverage would take thousands of datasets per case. So the choice of
quantile is checked directly instead, by
test_the_threshold_is_students_t_on_the_degrees_of_freedom_of_sigma below:
deterministic, and exact for that defect. The coverage study checks what
only simulation can: that the profile, the multi-start fit and the
quantile together give intervals near their nominal level.

The cases are one per source of sigma, for Michaelis-Menten at 6
concentrations in duplicate (0.2 to 10 Km), and one for an inhibition
constant: Ki of a competitive inhibitor at 5 substrate and 3 inhibitor
concentrations, sigma known.
"""
from __future__ import annotations

import math

import numpy as np
import pytest

from caterva.rates.fit import build_problem, fit, profile, profile_all
from caterva.rates.models import law_for
from caterva.rates.table import Dataset, read_unit
from caterva.rates.uncertainty import resolve

DATASETS = 300
LEVEL = 0.95
BAND = 3 * math.sqrt(LEVEL * (1 - LEVEL) / DATASETS)
SEED = 20260930

UNITS = {
    "substrate": read_unit("substrate", "mM", "substrate"),
    "rate": read_unit("rate", "uM/min", "rate"),
    "sigma": read_unit("sigma", "uM/min", "sigma"),
    "inhibitor": read_unit("inhibitor", "mM", "inhibitor"),
}
TRUE = {"Vmax": 10.0, "Km": 1.0, "Ki": 0.5}
NOISE = 0.3  # uM/min: 3% of Vmax


def synthetic_rates(law, s, i, rng, with_sigma):
    """One SYNTHETIC dataset: the law at TRUE plus normal noise of NOISE."""
    v = law.rate(TRUE, s, i)
    observed = v + NOISE * rng.standard_normal(len(v))
    return Dataset("synthetic", tuple(s), tuple(observed), UNITS, tuple(range(len(s))),
                   sigma=tuple([NOISE] * len(s)) if with_sigma else None,
                   inhibitor=tuple(i) if law.needs_inhibitor else None)


@pytest.mark.parametrize("source", [None, "residuals", "replicates"],
                         ids=["sigma-known", "sigma-from-residuals", "sigma-from-replicates"])
def test_michaelis_menten_profile_intervals_cover_at_the_nominal_rate(source):
    law = law_for("michaelis-menten")
    s = np.repeat([0.2, 0.5, 1.0, 2.0, 5.0, 10.0], 2)
    rng = np.random.default_rng(SEED)
    hits = {"Vmax": 0, "Km": 0}
    for _ in range(DATASETS):
        data = synthetic_rates(law, s, np.zeros_like(s), rng, with_sigma=source is None)
        fitted, intervals = profile_all(fit(build_problem(law, data, resolve(data, source))), LEVEL)
        for name, interval in zip(law.names, intervals):
            hits[name] += interval.contains(TRUE[name])
    for name, count in hits.items():
        coverage = count / DATASETS
        assert abs(coverage - LEVEL) <= BAND, (name, coverage)


def test_a_competitive_ki_interval_covers_at_the_nominal_rate():
    law = law_for("competitive")
    s, i = np.meshgrid([0.2, 0.5, 1.0, 2.0, 5.0], [0.0, 0.5, 1.5])
    s, i = s.ravel(), i.ravel()
    rng = np.random.default_rng(SEED + 1)
    hits = 0
    for _ in range(DATASETS):
        data = synthetic_rates(law, s, i, rng, with_sigma=True)
        fitted = fit(build_problem(law, data, resolve(data, None)))
        interval = profile(fitted, {law.names.index("Ki"): 1.0}, LEVEL, "Ki")
        hits += interval.contains(TRUE["Ki"])
    coverage = hits / DATASETS
    assert abs(coverage - LEVEL) <= BAND, coverage


@pytest.mark.parametrize("source, dof", [(None, None), ("residuals", 10), ("replicates", 6)],
                         ids=["sigma-known", "sigma-from-residuals", "sigma-from-replicates"])
def test_the_threshold_is_students_t_on_the_degrees_of_freedom_of_sigma(source, dof):
    """The quantile the intervals are built on (module docstring): normal for
    a stated sigma, t on n - p for the residuals, t on the replicates' pooled
    degrees of freedom. Checked against scipy.stats, which the code does not
    call for it; one SYNTHETIC dataset of the design above."""
    from scipy import stats as scipy_stats

    law = law_for("michaelis-menten")
    s = np.repeat([0.2, 0.5, 1.0, 2.0, 5.0, 10.0], 2)
    data = synthetic_rates(law, s, np.zeros_like(s), np.random.default_rng(SEED),
                           with_sigma=source is None)
    fitted = fit(build_problem(law, data, resolve(data, source)))
    expected = (scipy_stats.norm.ppf(0.975) if dof is None
                else scipy_stats.t.ppf(0.975, dof))
    assert fitted.critical(LEVEL) == pytest.approx(expected, rel=1e-9)
    assert fitted.threshold(LEVEL) == pytest.approx(expected ** 2, rel=1e-9)
