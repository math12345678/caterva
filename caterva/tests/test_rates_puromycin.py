"""`caterva rates` on real data: the puromycin rates of Treloar (1974).

THE DATA
--------
examples/rates/puromycin.csv holds the initial rates of galactosyltransferase
in Golgi membranes from cells treated with puromycin and from untreated
cells: Treloar MA (1974), M.Sc. thesis, University of Toronto, published in
Bates DM & Watts DG (1988) Nonlinear Regression Analysis and Its
Applications, Wiley, Appendix A1.3, and distributed as R's
datasets::Puromycin. `PUBLISHED` below is that table; the first test holds
the committed file to it.

THE REFERENCE NUMBERS
---------------------
`R_NLS` is R 4.6.0's own output on datasets::Puromycin, run on 2026-09-30:

    nls(rate ~ Vm * conc/(K + conc), data = Puromycin,
        subset = state == "treated", start = c(Vm = 200, K = 0.05))

(and the same for "untreated"), with summary() for the standard errors and
the residual standard error, and confint() for the profile intervals. The
Hill-against-Michaelis-Menten F tests are anova() of the two nls fits. R's
confint interpolates a spline through the profile and stops its search at a
tolerance, so its interval ends agree with an exact root to about 1e-4
relative; the tolerance below is 2e-3.

The shared-Km comparison (Bates & Watts' own question of these data: does
puromycin change Vm only?) is ALSO computed here independently, with
scipy.optimize.curve_fit on the combined table, and the command's F test
must equal the one built from those two independent fits.
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest
from scipy import stats as scipy_stats
from scipy.optimize import curve_fit

from caterva.rates.analysis import Options, analyse
from caterva.rates.fit import build_problem, fit, profile_all
from caterva.rates.groups import compare_groups
from caterva.rates.models import law_for
from caterva.rates.table import read_table
from caterva.rates.uncertainty import resolve

EXAMPLE = Path(__file__).resolve().parents[2] / "examples" / "rates" / "puromycin.csv"

#: Bates & Watts (1988) Appendix A1.3; R datasets::Puromycin.
PUBLISHED = {
    "treated": ([0.02, 0.02, 0.06, 0.06, 0.11, 0.11, 0.22, 0.22, 0.56, 0.56, 1.10, 1.10],
                [76, 47, 97, 107, 123, 139, 159, 152, 191, 201, 207, 200]),
    "untreated": ([0.02, 0.02, 0.06, 0.06, 0.11, 0.11, 0.22, 0.22, 0.56, 0.56, 1.10],
                  [67, 51, 84, 86, 98, 115, 131, 124, 144, 158, 160]),
}

#: R 4.6.0 nls/summary/confint on datasets::Puromycin (module docstring).
R_NLS = {
    "treated": {"Vm": 212.68358, "K": 0.06412102739, "se_Vm": 6.947146256, "se_K": 0.00828092242,
                "sigma": 10.93365819, "df": 10, "deviance": 1195.448815,
                "ci_Vm": (197.30212847588, 229.29006489262), "ci_K": (0.04692516839, 0.08615995299)},
    "untreated": {"Vm": 160.2800737, "K": 0.04770822713, "se_Vm": 6.480247495,
                  "se_K": 0.007781880802, "sigma": 9.773003029, "df": 9, "deviance": 859.6042938,
                  "ci_Vm": (145.63695396382, 176.54440120384),
                  "ci_K": (0.03137459811, 0.07006130623)},
}
#: R 4.6.0: nls(rate ~ (Vm + delV*(state=="treated"))*conc/(K + conc)), and
#: anova() of it against the model with delK: F 1.7182 on 1 and 19, p 0.2056.
R_SHARED_K = {"Vm_untreated": 166.6039661, "delV": 42.02590928, "K": 0.05797156925,
              "se_K": 0.005910153767, "deviance": 2240.891439, "F": 1.7182, "p": 0.2056}
#: R 4.6.0: anova(MM fit, Hill fit) for each group.
R_HILL_F = {"treated": (4.285, 0.06836), "untreated": (7.8438, 0.02317)}
#: R 4.6.0: summary(nls(rate ~ Vm*conc^n/(K^n + conc^n), subset untreated,
#: start = list(Vm = 160, K = 0.05, n = 1))): estimates and standard errors,
#: residual standard error 7.366 on 8 degrees of freedom.
R_HILL_UNTREATED = {"Vmax": (195.12798093011, 25.36946332310),
                    "K_half": (0.08241413045, 0.03928334243),
                    "n": (0.62070109088, 0.13043974530), "sigma": 7.366}


@pytest.fixture(scope="module")
def data():
    return read_table(EXAMPLE, group="state")


def test_the_committed_file_is_the_published_table(data):
    assert data.units["substrate"].text == "ppm"
    assert data.units["rate"].text == "counts/min/min"
    assert not data.units["substrate"].convertible
    for state, (conc, rate) in PUBLISHED.items():
        rows = data.rows_of(state)
        assert [data.substrate[r] for r in rows] == conc
        assert [data.rate[r] for r in rows] == rate
    assert len(data) == 23
    assert "Bates DM & Watts DG (1988)" in " ".join(data.comments)


@pytest.mark.parametrize("state", ["treated", "untreated"])
def test_sigma_from_residuals_reproduces_r_nls(data, state):
    law = law_for("michaelis-menten")
    problem = build_problem(law, data, resolve(data, "residuals"), rows=data.rows_of(state))
    fitted, intervals = profile_all(fit(problem), 0.95)
    ref = R_NLS[state]
    vmax, km = fitted.values
    assert vmax == pytest.approx(ref["Vm"], rel=1e-5)
    assert km == pytest.approx(ref["K"], rel=1e-4)
    assert fitted.se[0] == pytest.approx(ref["se_Vm"], rel=1e-4)
    assert fitted.se[1] == pytest.approx(ref["se_K"], rel=1e-4)
    assert fitted.residual_se == pytest.approx(ref["sigma"], rel=1e-6)
    assert fitted.dof == ref["df"]
    assert fitted.chi2 == pytest.approx(ref["deviance"], rel=1e-8)
    for iv, key in zip(intervals, ("ci_Vm", "ci_K")):
        assert iv.low == pytest.approx(ref[key][0], rel=2e-3)
        assert iv.high == pytest.approx(ref[key][1], rel=2e-3)
    # The profile interval for Km is asymmetric, as a Wald interval is not.
    ci = intervals[1]
    assert (ci.high - km) / (km - ci.low) > 1.2


def _independent_shared_k():
    """The shared-Km fit and the separate fits, by scipy.optimize.curve_fit on
    the published table, sharing no code with the command."""
    conc = np.array(PUBLISHED["treated"][0] + PUBLISHED["untreated"][0])
    rate = np.array(PUBLISHED["treated"][1] + PUBLISHED["untreated"][1], dtype=float)
    treated = np.array([1.0] * 12 + [0.0] * 11)

    def shared(x, vm, dv, k):
        return (vm + dv * x[1]) * x[0] / (k + x[0])

    popt, _ = curve_fit(shared, np.vstack([conc, treated]), rate, p0=[160, 40, 0.05])
    ss_shared = float(((rate - shared(np.vstack([conc, treated]), *popt)) ** 2).sum())

    def mm(x, vm, k):
        return vm * x / (k + x)

    ss_separate = 0.0
    for state in ("treated", "untreated"):
        c, r = (np.asarray(a, dtype=float) for a in PUBLISHED[state])
        p, _ = curve_fit(mm, c, r, p0=[200, 0.05])
        ss_separate += float(((r - mm(c, *p)) ** 2).sum())
    f = (ss_shared - ss_separate) / (ss_separate / (23 - 4))
    return popt, ss_shared, ss_separate, f, float(scipy_stats.f.sf(f, 1, 19))


def test_the_shared_km_test_matches_an_independent_fit_and_r(data):
    law = law_for("michaelis-menten")
    uncertainty = resolve(data, "residuals")
    per_group = {g: fit(build_problem(law, data, uncertainty, rows=data.rows_of(g)))
                 for g in ("treated", "untreated")}
    comparison = compare_groups(law, data, uncertainty, per_group, 0.95, 0.05)
    shared_k = next(t for t in comparison.tests if t.constant == "Km")
    popt, ss_shared, ss_separate, f, p = _independent_shared_k()

    labels = shared_k.fit.problem.labels
    values = dict(zip(labels, shared_k.fit.values))
    assert values["Vmax [untreated]"] == pytest.approx(popt[0], rel=1e-5)
    assert values["Vmax [treated]"] == pytest.approx(popt[0] + popt[1], rel=1e-5)
    assert values["Km"] == pytest.approx(popt[2], rel=1e-5)
    assert shared_k.fit.chi2 == pytest.approx(ss_shared, rel=1e-7)
    assert comparison.separate.chi2 == pytest.approx(ss_separate, rel=1e-7)
    assert shared_k.statistic == pytest.approx(f, rel=1e-6)
    assert shared_k.p == pytest.approx(p, rel=1e-6)
    assert shared_k.df == (1, 19)
    assert not shared_k.rejected

    # And R's own numbers for the same question.
    assert values["Km"] == pytest.approx(R_SHARED_K["K"], rel=1e-4)
    assert values["Vmax [treated]"] - values["Vmax [untreated]"] == pytest.approx(
        R_SHARED_K["delV"], rel=1e-4)
    assert shared_k.fit.se[labels.index("Km")] == pytest.approx(R_SHARED_K["se_K"], rel=1e-3)
    assert shared_k.statistic == pytest.approx(R_SHARED_K["F"], abs=1e-4)
    assert shared_k.p == pytest.approx(R_SHARED_K["p"], abs=1e-4)

    # Vmax differs, which is what puromycin does to this enzyme's rates.
    shared_v = next(t for t in comparison.tests if t.constant == "Vmax")
    assert shared_v.rejected and shared_v.p < 1e-3


def test_hill_against_michaelis_menten_matches_r_anova(data):
    analysis = analyse(data, resolve(data, "residuals"), Options())
    for result in analysis.results:
        test = result.tests["hill"]
        f, p = R_HILL_F[result.group]
        assert test.statistic == pytest.approx(f, rel=1e-4)
        assert test.p == pytest.approx(p, rel=1e-3)
        assert not test.nesting.boundary
    untreated = next(r for r in analysis.results if r.group == "untreated")
    hill = untreated.laws["hill"].fit
    for name, value, se in zip(hill.problem.constants, hill.values, hill.se):
        assert value == pytest.approx(R_HILL_UNTREATED[name][0], rel=1e-5), name
        assert se == pytest.approx(R_HILL_UNTREATED[name][1], rel=1e-4), name
    assert hill.residual_se == pytest.approx(R_HILL_UNTREATED["sigma"], abs=5e-4)


def _independent_hill_ss(fixed: str, value: float) -> float:
    """The least residual sum of squares of the untreated Hill fit with one
    constant held at `value` (None: nothing held) and the others free and
    UNBOUNDED: scipy's Levenberg-Marquardt from a grid of starts, in its own
    parameterisation (log Vmax, log K0.5, n), sharing no code with the
    command."""
    from scipy.optimize import least_squares

    c, r = (np.asarray(a, dtype=float) for a in PUBLISHED["untreated"])

    def rate(log_v, log_k, n):
        return np.exp(log_v) * c ** n / (np.exp(n * log_k) + c ** n)

    if fixed == "n":
        unpack = lambda x: (x[0], x[1], value)  # noqa: E731
        starts = [[lv, lk] for lv in (5, 8, 12) for lk in (-2, 2, 10, 30)]
    elif fixed == "Vmax":
        unpack = lambda x: (math.log(value), x[0], x[1])  # noqa: E731
        starts = [[lk, n] for lk in (-2, 2, 6, 10) for n in (0.2, 0.3, 0.6)]
    else:
        unpack = lambda x: x  # noqa: E731
        starts = [[5.3, -2.5, 0.6], [5.0, -3.0, 1.0]]
    found = []
    for x0 in starts:
        with np.errstate(all="ignore"):
            try:
                out = least_squares(lambda x: r - rate(*unpack(x)), x0, method="lm", max_nfev=5000)
            except ValueError:
                continue
        if np.isfinite(out.cost):
            found.append(2 * out.cost)
    return min(found)


@pytest.mark.parametrize("source", ["replicates", "residuals"])
def test_hill_profile_bounds_equal_an_independent_unbounded_profile(source):
    """The untreated rates fitted with the Hill law. R's confint cannot profile
    this fit (R 4.6.0 stops at its iteration limit), so the command's
    intervals are held to an independent profile instead: the other two
    constants refitted without bounds at each value, and the crossing of the
    same threshold found by root-finding.

    It is also the case that found a defect. With sigma from the duplicates,
    n profiled downwards crosses the threshold near 0.25 with K0.5 near 2e3
    ppm, well inside the search's box, but a long step past that point sends
    K0.5 beyond the box's edge (1e8 times the data), and the edge used to be
    read as the data being silent: n was reported with no lower bound. The
    bound is where the profile crosses, and the crossing is inside the box."""
    from scipy.optimize import brentq

    data = read_table(EXAMPLE, group="state")
    problem = build_problem(law_for("hill"), data, resolve(data, source),
                            rows=data.rows_of("untreated"))
    fitted, intervals = profile_all(fit(problem), 0.95)
    vmax, _k_half, n = intervals
    minimum = _independent_hill_ss(None, None)
    if source == "replicates":
        scale, dof = 1094.5 / 11, 11  # the duplicates' pure error, by hand
    else:
        scale, dof = minimum / 8, 8  # R's residual variance on n - p = 8
    threshold = scipy_stats.t.ppf(0.975, dof) ** 2

    def excess(which, value):
        return (_independent_hill_ss(which, value) - minimum) / scale - threshold

    assert n.bounded and vmax.bounded
    assert n.low == pytest.approx(brentq(lambda x: excess("n", x), 0.2, 0.45), rel=1e-4)
    assert n.high == pytest.approx(brentq(lambda x: excess("n", x), 0.8, 1.2), rel=1e-4)
    assert vmax.low == pytest.approx(brentq(lambda x: excess("Vmax", x), 140.0, 190.0), rel=1e-4)
    assert vmax.high == pytest.approx(brentq(lambda x: excess("Vmax", x), 300.0, 3000.0),
                                      rel=1e-4)


def test_sigma_from_replicates_pools_the_duplicates_and_states_the_degrees_of_freedom(data):
    u = resolve(data, "replicates")
    # Pure error by hand: each duplicate pair contributes (a - b)^2 / 2.
    pairs = [(76, 47), (97, 107), (123, 139), (159, 152), (191, 201), (207, 200),
             (67, 51), (84, 86), (98, 115), (131, 124), (144, 158)]
    ss = sum((a - b) ** 2 / 2 for a, b in pairs)
    assert ss == 1094.5
    assert u.dof == 11 and u.sets == 11
    assert u.pooled == pytest.approx(math.sqrt(ss / 11), rel=1e-12)


def test_the_lack_of_fit_test_runs_and_matches_the_hand_calculation(data):
    analysis = analyse(data, resolve(data, "replicates"), Options(model="michaelis-menten"))
    by_group = {r.group: r.laws["michaelis-menten"].lack_of_fit for r in analysis.results}
    # treated: pure error 697.5 on 6 df; residual SS 1195.448815 (R); 6 - 2 = 4 df.
    expected_t = ((1195.448815 - 697.5) / 4) / (697.5 / 6)
    # untreated: pure error 397 on 5 df; residual SS 859.6042938 (R).
    expected_u = ((859.6042938 - 397.0) / 4) / (397.0 / 5)
    assert by_group["treated"].ss_pe == pytest.approx(697.5 / (1094.5 / 11), rel=1e-12)
    assert by_group["treated"].f == pytest.approx(expected_t, rel=1e-6)
    assert by_group["untreated"].f == pytest.approx(expected_u, rel=1e-6)
    assert (by_group["treated"].df_lof, by_group["treated"].df_pe) == (4, 6)
    assert by_group["treated"].p == pytest.approx(scipy_stats.f.sf(expected_t, 4, 6), rel=1e-6)
    # Scale-free: the same F whatever sigma is.
    residual = analyse(data, resolve(data, "residuals"), Options(model="michaelis-menten"))
    assert residual.results[0].laws["michaelis-menten"].lack_of_fit.f == pytest.approx(
        by_group["treated"].f, rel=1e-9)
