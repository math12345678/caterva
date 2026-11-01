"""`caterva rates`: every rate law recovers known constants, and agrees with scipy.

SYNTHETIC DATA, AND ONLY FOR THIS
---------------------------------
Every dataset in this file is SYNTHETIC: rates computed from a rate law at
stated constants, with seeded noise where there is noise. That is allowed
here because the tests check parameter recovery and agreement with an
independent fitter, and for nothing else: none of these numbers is a
measurement, and none appears in an example, a document or an output.

What is checked:
  * noise-free rates give back the constants they were made from, for all
    seven laws;
  * with seeded noise, every law's estimates and standard errors equal those
    of scipy.optimize.curve_fit, an independent implementation (different
    parameterisation, different Jacobian, different optimiser), fitted with
    the same weights to the rate laws written out again in this file
    (TEXTBOOK), not to the command's own;
  * the complex-step Jacobian equals the analytic derivative of
    Michaelis-Menten to rounding error.
"""
from __future__ import annotations

import math

import numpy as np
import pytest
from scipy.optimize import curve_fit

from caterva.rates.fit import FitRefused, build_problem, fit, profile_all
from caterva.rates.models import LAWS, law_for
from caterva.rates.table import read_table
from caterva.rates.uncertainty import resolve

#: Constants the synthetic rates are generated at. Arbitrary, stated, and
#: in the units of the synthetic columns (mM, uM/min).
TRUE = {
    "michaelis-menten": {"Vmax": 12.0, "Km": 0.8},
    "substrate-inhibition": {"Vmax": 20.0, "Km": 0.5, "Ksi": 5.0},
    "hill": {"Vmax": 10.0, "K_half": 2.0, "n": 2.5},
    "competitive": {"Vmax": 10.0, "Km": 1.0, "Ki": 0.5},
    "uncompetitive": {"Vmax": 10.0, "Km": 1.0, "Ki_prime": 2.0},
    "noncompetitive": {"Vmax": 10.0, "Km": 1.0, "Ki": 0.7},
    "mixed": {"Vmax": 10.0, "Km": 1.0, "Ki": 0.5, "Ki_prime": 2.0},
}

SUBSTRATE = {
    "michaelis-menten": np.geomspace(0.1, 10.0, 8),
    "substrate-inhibition": np.geomspace(0.05, 50.0, 10),
    "hill": np.geomspace(0.2, 20.0, 9),
}
#: The seven laws written out again, from the textbook forms (Cornish-Bowden,
#: Fundamentals of Enzyme Kinetics, 4th ed. 2012; Segel 1975), and NOT from
#: caterva/rates/models.py. The synthetic rates are made with these and the
#: curve_fit cross-check fits these, so a slip in a law in models.py makes
#: the command disagree with both instead of agreeing with itself.
TEXTBOOK = {
    "michaelis-menten": lambda c, s, i: c["Vmax"] * s / (c["Km"] + s),
    "substrate-inhibition": lambda c, s, i: c["Vmax"] * s / (c["Km"] + s + s ** 2 / c["Ksi"]),
    "hill": lambda c, s, i: c["Vmax"] * s ** c["n"] / (c["K_half"] ** c["n"] + s ** c["n"]),
    "competitive": lambda c, s, i: c["Vmax"] * s / (c["Km"] * (1 + i / c["Ki"]) + s),
    "uncompetitive": lambda c, s, i: c["Vmax"] * s / (c["Km"] + s * (1 + i / c["Ki_prime"])),
    "noncompetitive": lambda c, s, i: c["Vmax"] * s / ((c["Km"] + s) * (1 + i / c["Ki"])),
    "mixed": lambda c, s, i: c["Vmax"] * s / (c["Km"] * (1 + i / c["Ki"])
                                             + s * (1 + i / c["Ki_prime"])),
}

INHIBITION_S = np.geomspace(0.1, 10.0, 6)
INHIBITION_I = np.array([0.0, 0.5, 1.5, 4.5])


def design(name):
    """(substrate, inhibitor) of the synthetic design for a law."""
    if name in SUBSTRATE:
        s = SUBSTRATE[name]
        return s, np.zeros_like(s)
    s, i = np.meshgrid(INHIBITION_S, INHIBITION_I)
    return s.ravel(), i.ravel()


def table(s, i, v, sd, inhibitor):
    header = "substrate (mM),rate (uM/min),sigma (uM/min)" + (",inhibitor (mM)" if inhibitor else "")
    lines = [header]
    for k in range(len(s)):
        row = f"{float(s[k])!r},{float(v[k])!r},{float(sd[k])!r}"
        if inhibitor:
            row += f",{float(i[k])!r}"
        lines.append(row)
    return read_table("synthetic.csv", text="\n".join(lines) + "\n")


def synthetic(name, noise=0.0, seed=0, replicates=1):
    law = law_for(name)
    s, i = design(name)
    s, i = np.repeat(s, replicates), np.repeat(i, replicates)
    v = TEXTBOOK[name](TRUE[name], s, i)
    sd = 0.02 * v + 0.01
    rng = np.random.default_rng(seed)
    observed = v + noise * sd * rng.standard_normal(len(v))
    return table(s, i, observed, sd, law.needs_inhibitor)


@pytest.mark.parametrize("name", list(LAWS))
def test_noise_free_rates_give_back_the_constants_they_were_made_from(name):
    data = synthetic(name)
    law = law_for(name)
    fitted = fit(build_problem(law, data, resolve(data, None)))
    got = dict(zip(law.names, fitted.values))
    for constant, value in TRUE[name].items():
        assert got[constant] == pytest.approx(value, rel=1e-6), constant
    assert fitted.chi2 < 1e-12


@pytest.mark.parametrize("name", list(LAWS))
def test_estimates_and_errors_equal_scipy_curve_fit_with_the_same_weights(name):
    """curve_fit fits the constants themselves (not their logarithms), with
    its own finite-difference Jacobian, to TEXTBOOK's law, from the true values; absolute_sigma
    takes the file's standard deviations as known, as this command does."""
    data = synthetic(name, noise=1.0, seed=7, replicates=2)
    law = law_for(name)
    fitted = fit(build_problem(law, data, resolve(data, None)))
    s = np.asarray(data.substrate)
    i = np.zeros_like(s) if data.inhibitor is None else np.asarray(data.inhibitor)
    v = np.asarray(data.rate)
    sd = np.asarray(data.sigma)

    def model(x, *p):
        return TEXTBOOK[name](dict(zip(law.names, p)), x[0], x[1])

    start = [TRUE[name][c] for c in law.names]
    popt, pcov = curve_fit(model, np.vstack([s, i]), v, p0=start, sigma=sd, absolute_sigma=True,
                           maxfev=20000)
    np.testing.assert_allclose(fitted.values, popt, rtol=1e-5)
    np.testing.assert_allclose(fitted.se, np.sqrt(np.diag(pcov)), rtol=1e-3)


def test_the_complex_step_jacobian_is_the_analytic_derivative():
    """d v / d log Km = -Vmax S Km / (Km + S)^2 and d v / d log Vmax = v:
    the complex step must give both to rounding error, where a finite
    difference could not."""
    data = synthetic("michaelis-menten")
    law = law_for("michaelis-menten")
    problem = build_problem(law, data, resolve(data, None))
    theta = np.log([12.0, 0.8])
    s = np.asarray(data.substrate)
    v = 12.0 * s / (0.8 + s)
    analytic = np.column_stack([v, -12.0 * s * 0.8 / (0.8 + s) ** 2]) / np.asarray(data.sigma)[:, None]
    np.testing.assert_allclose(-problem.jacobian(theta), analytic, rtol=1e-13)


def test_a_law_with_more_constants_than_conditions_is_refused():
    lines = ["substrate (mM),rate (uM/min),sigma (uM/min)", "1,5,0.1", "1,5.2,0.1"]
    data = read_table("two.csv", text="\n".join(lines) + "\n")
    with pytest.raises(FitRefused, match="1 distinct condition"):
        fit(build_problem(law_for("michaelis-menten"), data, resolve(data, None)))


def test_sigma_from_residuals_needs_more_rows_than_constants():
    lines = ["substrate (mM),rate (uM/min)", "1,5", "2,7"]
    data = read_table("two.csv", text="\n".join(lines) + "\n")
    with pytest.raises(FitRefused, match="nothing to estimate the scatter from"):
        fit(build_problem(law_for("michaelis-menten"), data, resolve(data, "residuals")))


def test_a_profile_interval_contains_its_estimate_and_is_asymmetric_for_km():
    data = synthetic("michaelis-menten", noise=1.0, seed=3, replicates=2)
    fitted = fit(build_problem(law_for("michaelis-menten"), data, resolve(data, None)))
    fitted, intervals = profile_all(fitted, 0.95)
    km = intervals[1]
    assert km.low < km.estimate < km.high
    # Asymmetric: the upper arm is longer than the lower, as a profile on a
    # constant that enters as a denominator should be.
    assert (km.high - km.estimate) > (km.estimate - km.low)
    assert not math.isclose(km.high - km.estimate, km.estimate - km.low, rel_tol=1e-3)
