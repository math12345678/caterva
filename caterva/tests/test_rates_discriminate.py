"""`caterva rates`: mechanism tests, what the data determine, and the design advice.

SYNTHETIC DATA, AND ONLY FOR THIS
---------------------------------
Every rate here is SYNTHETIC, computed from a stated law at stated constants
with seeded noise, because these tests check that known structure is
recovered: a competitive inhibitor is called competitive, a boundary test's
p-value is half the ordinary one, a dataset that cannot fix Km says so. None
of these numbers is a measurement or appears in any output.

The p-values of the tests are checked against hand calculations that share
no code with the command: the chi-square(1) tail as erfc(sqrt(x/2)), and
the F(1, nu) tail through scipy.stats rather than the scipy.special function
the command uses.
"""
from __future__ import annotations

import math

import numpy as np
import pytest
from scipy import stats as scipy_stats

from caterva.rates import stats
from caterva.rates.analysis import Options, analyse
from caterva.rates.discriminate import aicc
from caterva.rates.models import law_for
from caterva.rates.report import render
from caterva.rates.table import read_table
from caterva.rates.uncertainty import resolve

S_GRID = np.geomspace(0.1, 10.0, 6)
I_GRID = np.array([0.0, 0.5, 1.5, 4.5])
TRUE = {"Vmax": 10.0, "Km": 1.0, "Ki": 0.5, "Ki_prime": 2.0, "Ksi": 5.0}


def rates(name, s, i, *, noise=1.0, seed=0, replicates=2, sigma_column=True, constants=None):
    """A SYNTHETIC table: `name`'s law at TRUE (or `constants`), with seeded
    noise of 3% of the rate plus a floor."""
    law = law_for(name)
    values = dict(TRUE)
    values.update(constants or {})
    s = np.repeat(np.asarray(s, dtype=float), replicates)
    i = np.repeat(np.asarray(i, dtype=float), replicates)
    v = law.rate(values, s, i)
    sd = 0.03 * v + 0.02
    rng = np.random.default_rng(seed)
    observed = v + noise * sd * rng.standard_normal(len(v))
    header = "substrate (mM),rate (uM/min)" + (",sigma (uM/min)" if sigma_column else "")
    header += ",inhibitor (mM)" if law.needs_inhibitor else ""
    lines = [header]
    for k in range(len(s)):
        row = f"{float(s[k])!r},{float(observed[k])!r}"
        if sigma_column:
            row += f",{float(sd[k])!r}"
        if law.needs_inhibitor:
            row += f",{float(i[k])!r}"
        lines.append(row)
    return read_table(f"synthetic-{name}.csv", text="\n".join(lines) + "\n")


def inhibited(name, **kw):
    s, i = np.meshgrid(S_GRID, I_GRID)
    return rates(name, s.ravel(), i.ravel(), **kw)


# ---------------------------------------------------------------------------
# The reference distributions
# ---------------------------------------------------------------------------


def test_f_on_one_degree_is_the_square_of_t():
    for nu in (3, 11, 40):
        for f in (0.5, 2.0, 7.3):
            assert stats.f_tail(f, 1, nu) == pytest.approx(2 * scipy_stats.t.sf(math.sqrt(f), nu),
                                                           rel=1e-10)


def test_chi_square_tail_has_its_closed_forms():
    for x in (0.1, 2.0, 9.0):
        assert stats.chi2_tail(x, 2) == pytest.approx(math.exp(-x / 2), rel=1e-12)
        assert stats.chi2_tail(x, 1) == pytest.approx(math.erfc(math.sqrt(x / 2)), rel=1e-10)


def test_a_boundary_p_value_is_half_the_ordinary_one_and_one_at_zero():
    assert stats.boundary_tail(0.1, 2.706) == 0.05
    assert stats.boundary_tail(1.0, 0.0) == 1.0
    # 2.706 is the chi-square(1) 90th percentile: ordinary p 0.10, boundary 0.05.
    assert stats.boundary_tail(stats.chi2_tail(2.705543454, 1), 2.705543454) == pytest.approx(
        0.05, rel=1e-6)


def test_t_quantile_is_students():
    assert stats.t_for(0.95, 10) == pytest.approx(scipy_stats.t.ppf(0.975, 10), rel=1e-12)
    assert stats.z_for(0.95) == pytest.approx(1.959963985, rel=1e-9)


# ---------------------------------------------------------------------------
# Mechanism discrimination
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name, out", [
    ("competitive", {"uncompetitive", "noncompetitive"}),
    ("uncompetitive", {"competitive", "noncompetitive"}),
    ("noncompetitive", {"competitive", "uncompetitive"}),
])
def test_each_mechanism_is_recovered_and_the_others_ruled_out(name, out):
    data = inhibited(name, seed=11)
    result = analyse(data, resolve(data, None), Options()).results[0]
    assert result.verdict.reported == [name]
    assert set(result.verdict.ruled_out) == out
    assert result.tests[name].p > 0.05


def test_mixed_inhibition_is_recovered_when_every_restriction_is_ruled_out():
    data = inhibited("mixed", seed=5)
    result = analyse(data, resolve(data, None), Options()).results[0]
    assert result.verdict.reported == ["mixed"]
    assert set(result.verdict.ruled_out) == {"competitive", "uncompetitive", "noncompetitive"}
    ki = result.laws["mixed"].interval("Ki")
    kip = result.laws["mixed"].interval("Ki'")
    assert ki.contains(TRUE["Ki"]) and kip.contains(TRUE["Ki_prime"])


def test_boundary_and_interior_p_values_equal_the_hand_calculation_with_sigma_known():
    data = inhibited("competitive", seed=2)
    result = analyse(data, resolve(data, None), Options()).results[0]
    chi_m = result.laws["mixed"].fit.chi2
    for special, boundary in (("competitive", True), ("uncompetitive", True),
                              ("noncompetitive", False)):
        rise = max(result.laws[special].fit.chi2 - chi_m, 0.0)
        ordinary = math.erfc(math.sqrt(rise / 2)) if rise > 0 else 1.0
        expected = (0.5 * ordinary if rise > 0 else 1.0) if boundary else ordinary
        test = result.tests[special]
        assert test.nesting.boundary is boundary
        assert test.statistic == pytest.approx(rise, rel=1e-12, abs=1e-12)
        assert test.p == pytest.approx(expected, rel=1e-8, abs=1e-300)


def test_boundary_p_value_equals_the_hand_calculation_with_sigma_from_residuals():
    data = inhibited("competitive", seed=4, sigma_column=False)
    result = analyse(data, resolve(data, "residuals"), Options()).results[0]
    mixed = result.laws["mixed"].fit
    comp = result.laws["competitive"].fit
    dof = mixed.n - 4
    f = (comp.chi2 - mixed.chi2) / (mixed.chi2 / dof)
    expected = 0.5 * scipy_stats.f.sf(f, 1, dof) if f > 0 else 1.0
    assert result.tests["competitive"].reference == f"F(1, {dof})"
    assert result.tests["competitive"].p == pytest.approx(expected, rel=1e-8)


def test_the_general_law_never_fits_worse_than_a_law_it_contains():
    """The mixed fit is started from each restricted optimum, so a likelihood
    ratio cannot come out negative because the search missed the boundary."""
    for name in ("competitive", "uncompetitive", "noncompetitive"):
        data = inhibited(name, seed=9)
        result = analyse(data, resolve(data, None), Options()).results[0]
        mixed = result.laws["mixed"].fit.chi2
        for special in ("competitive", "uncompetitive", "noncompetitive"):
            assert mixed <= result.laws[special].fit.chi2 * (1 + 1e-9) + 1e-9


def test_a_competitive_inhibitor_leaves_ki_prime_unbounded_in_the_mixed_fit():
    data = inhibited("competitive", seed=11)
    result = analyse(data, resolve(data, None), Options()).results[0]
    kip = result.laws["mixed"].interval("Ki'")
    assert kip.high is None and kip.low is not None
    assert "Ki'" in result.laws["mixed"].determination.undetermined
    assert any("cannot be excluded" in s for s in result.verdict.sentences)


def test_when_the_design_cannot_separate_mechanisms_the_verdict_says_so_and_names_the_measurement():
    """Inhibited rates at a single [S], equal to Km: competitive, uncompetitive
    and noncompetitive each fit them, since each has one inhibitor constant
    and there is one inhibited condition shape."""
    s = list(S_GRID) + [1.0, 1.0]
    i = [0.0] * len(S_GRID) + [0.5, 1.5]
    data = rates("competitive", s, i, seed=3)
    result = analyse(data, resolve(data, None), Options()).results[0]
    verdict = result.verdict
    assert {"competitive", "uncompetitive", "noncompetitive"} <= set(verdict.standing)
    assert verdict.sentences[0].startswith("The data cannot tell")
    assert len(verdict.reported) >= 2
    advice = " ".join(verdict.advice)
    assert "5 Km or more" in advice and "0.2 Km or less" in advice
    described = " ".join(verdict.described)
    assert "not a test" in described and "AICc" in described


def test_substrate_inhibition_is_detected_against_michaelis_menten():
    data = rates("substrate-inhibition", np.geomspace(0.05, 50.0, 10), np.zeros(10), seed=1)
    result = analyse(data, resolve(data, None), Options()).results[0]
    assert "michaelis-menten" in result.verdict.ruled_out
    assert result.verdict.reported[0] == "substrate-inhibition"
    assert result.tests["substrate-inhibition"].nesting.boundary
    ksi = result.laws["substrate-inhibition"].interval("Ksi")
    assert ksi.contains(TRUE["Ksi"])


def test_michaelis_menten_rates_keep_michaelis_menten():
    data = rates("michaelis-menten", np.geomspace(0.1, 10.0, 8), np.zeros(8), seed=21)
    result = analyse(data, resolve(data, None), Options()).results[0]
    assert result.verdict.reported == ["michaelis-menten"]
    assert result.verdict.sentences[0].startswith("Michaelis-Menten: the data give no evidence")


def test_aicc_is_the_textbook_formula():
    data = inhibited("competitive", seed=2)
    result = analyse(data, resolve(data, None), Options()).results[0]
    fitted = result.laws["competitive"].fit
    n, k = fitted.n, 3
    assert aicc(fitted) == pytest.approx(fitted.chi2 + 2 * k + 2 * k * (k + 1) / (n - k - 1),
                                         rel=1e-12)
    data = inhibited("competitive", seed=2, sigma_column=False)
    fitted = analyse(data, resolve(data, "residuals"), Options()).results[0].laws["competitive"].fit
    k = 4
    assert aicc(fitted) == pytest.approx(
        n * math.log(fitted.chi2 / n) + 2 * k + 2 * k * (k + 1) / (n - k - 1), rel=1e-12)


# ---------------------------------------------------------------------------
# What the data determine
# ---------------------------------------------------------------------------


def test_rates_far_below_km_determine_only_vmax_over_km():
    # Noise-free: whether a design can fix Km is a property of the design,
    # and a noisy draw would add the 5% of datasets whose noise mimics a
    # curve the design cannot see.
    s = np.array([0.001, 0.002, 0.004, 0.008, 0.016])  # at most 1.6% of Km
    data = rates("michaelis-menten", s, np.zeros(5), noise=0.0,
                 constants={"Vmax": 100.0, "Km": 1.0})
    analysis = analyse(data, resolve(data, None), Options(model="michaelis-menten"))
    law = analysis.results[0].laws["michaelis-menten"]
    vmax, km = law.intervals
    assert km.high is None and vmax.high is None
    assert set(law.determination.undetermined) == {"Vmax", "Km"}
    [ratio] = law.determination.products
    assert ratio.label == "Vmax/Km" and ratio.bounded
    assert ratio.contains(100.0)
    assert ratio.high / ratio.low < 1.3  # within a factor of 1.3, where Km is unbounded
    text = render(analysis)
    assert "Every substrate concentration is well below Km" in text
    assert "| Vmax | not determined |" in text and "| Km | not determined |" in text
    assert "Extend the highest concentration" in text


def test_rates_far_above_km_determine_vmax_and_only_bound_km():
    # At 1e4 Km and above, Km moves every rate by at most 1e-4 of itself,
    # far inside the 3% noise.
    s = np.array([1e4, 2e4, 4e4, 8e4, 1.6e5])
    data = rates("michaelis-menten", s, np.zeros(5), noise=0.0,
                 constants={"Vmax": 100.0, "Km": 1.0})
    analysis = analyse(data, resolve(data, None), Options(model="michaelis-menten"))
    law = analysis.results[0].laws["michaelis-menten"]
    vmax, km = law.intervals
    assert vmax.bounded and vmax.contains(100.0)
    assert km.low is None and km.high is not None
    assert law.determination.undetermined == ["Km"]
    assert "Every substrate concentration is well above Km" in law.determination.findings[0]
    assert "Bring the lowest concentration down" in " ".join(analysis.results[0].design.text)


def test_a_range_that_misses_km_gets_eight_log_spaced_concentrations_around_it():
    s = np.geomspace(2.0, 30.0, 6)
    data = rates("michaelis-menten", s, np.zeros(6), seed=13)
    design = analyse(data, resolve(data, None), Options(model="michaelis-menten")).results[0].design
    assert not design.brackets and design.below == 0
    assert len(design.recommended) == 8
    ratios = [b / a for a, b in zip(design.recommended, design.recommended[1:])]
    assert max(ratios) / min(ratios) < 1.3  # log-spaced, to two significant figures
    assert design.recommended[0] == pytest.approx(0.2 * design.km_low, rel=0.05)
    assert design.recommended[-1] == pytest.approx(5 * design.km_high, rel=0.05)
