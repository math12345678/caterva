"""The free-energy estimators, checked where the answer is known exactly.

Harmonic oscillators: state k has reduced potential u_k(x) = K_k (x - m_k)^2 / 2,
its samples are drawn exactly (Gaussian, variance 1/K_k), and the reduced
free energy difference is f_k - f_0 = ln(K_k / K_0) / 2. An estimator is
right when it recovers that, and honest when its error bar covers the truth
as often as it claims to (about 95% within 2 sigma over many datasets).
"""
from __future__ import annotations

import math

import numpy as np
import pytest

from caterva.fep import estimators as est

K = np.array([1.0, 1.6, 2.5, 4.0, 6.3, 10.0])
M = np.array([0.0, 0.3, 0.6, 0.9, 1.2, 1.5])
EXACT = 0.5 * np.log(K / K[0])


def _harmonic(n, rng):
    x = np.concatenate([rng.normal(M[k], 1 / math.sqrt(K[k]), n) for k in range(len(K))])
    u = 0.5 * K[:, None] * (x[None, :] - M[:, None]) ** 2
    return u, [n] * len(K)


def test_mbar_recovers_the_exact_free_energies():
    u, n = _harmonic(4000, np.random.default_rng(1))
    r = est.mbar(u, n)
    assert np.allclose(r.f, EXACT, atol=4 * r.df.max() + 1e-12)
    assert np.all(np.abs(r.f - EXACT) <= 4 * np.maximum(r.df, 1e-9))


def test_mbar_error_bars_are_calibrated():
    """Over 200 independent datasets, the 2-sigma interval must cover the
    exact answer about 95% of the time: an error bar that covers 70% is a
    claim of precision the estimate does not have."""
    rng = np.random.default_rng(7)
    hits = total = 0
    for _ in range(200):
        u, n = _harmonic(300, rng)
        r = est.mbar(u, n)
        hits += int(np.sum(np.abs(r.f[1:] - EXACT[1:]) <= 2 * r.df[1:]))
        total += len(K) - 1
    assert 0.91 <= hits / total <= 0.99


def test_bar_matches_the_exact_answer_for_each_neighbour_pair():
    rng = np.random.default_rng(3)
    for i in range(len(K) - 1):
        x0 = rng.normal(M[i], 1 / math.sqrt(K[i]), 5000)
        x1 = rng.normal(M[i + 1], 1 / math.sqrt(K[i + 1]), 5000)
        u = lambda k, x: 0.5 * K[k] * (x - M[k]) ** 2
        d, e = est.bar(u(i + 1, x0) - u(i, x0), u(i, x1) - u(i + 1, x1))
        assert abs(d - (EXACT[i + 1] - EXACT[i])) < 4 * e


def test_bar_error_bars_are_calibrated():
    rng = np.random.default_rng(11)
    u = lambda k, x: 0.5 * K[k] * (x - M[k]) ** 2
    hits = 0
    for _ in range(300):
        x0 = rng.normal(M[2], 1 / math.sqrt(K[2]), 300)
        x1 = rng.normal(M[3], 1 / math.sqrt(K[3]), 300)
        d, e = est.bar(u(3, x0) - u(2, x0), u(2, x1) - u(3, x1))
        hits += abs(d - (EXACT[3] - EXACT[2])) <= 2 * e
    assert 0.91 <= hits / 300 <= 0.99


def test_the_overlap_matrix_is_stochastic_and_flags_a_gap():
    u, n = _harmonic(2000, np.random.default_rng(5))
    O = est.mbar(u, n).overlap
    assert np.allclose(O.sum(axis=1), 1.0, atol=1e-8)
    # Two states far apart barely overlap.
    far = np.array([1.0, 1.0]); m = np.array([0.0, 8.0])
    x = np.concatenate([np.random.default_rng(6).normal(mu, 1.0, 2000) for mu in m])
    uu = 0.5 * far[:, None] * (x[None, :] - m[:, None]) ** 2
    assert est.mbar(uu, [2000, 2000]).overlap[0, 1] < est.MIN_OVERLAP


# --- correlation ------------------------------------------------------------------

def _ar1(n, phi, rng):
    x = np.empty(n)
    x[0] = rng.normal()
    s = math.sqrt(1 - phi * phi)
    for i in range(1, n):
        x[i] = phi * x[i - 1] + s * rng.normal()
    return x


def test_statistical_inefficiency_of_a_known_process():
    """An AR(1) process with coefficient phi has g = (1 + phi) / (1 - phi)."""
    rng = np.random.default_rng(2)
    for phi in (0.0, 0.5, 0.8):
        g = np.mean([est.statistical_inefficiency(_ar1(20000, phi, rng)) for _ in range(5)])
        assert g == pytest.approx((1 + phi) / (1 - phi), rel=0.15)


def test_an_equilibration_transient_is_detected_and_dropped():
    rng = np.random.default_rng(4)
    x = _ar1(2000, 0.3, rng)
    x[:200] += np.linspace(8, 0, 200)  # a relaxing start
    t0, g, _ = est.detect_equilibration(x, nskip=5)
    assert 120 <= t0 <= 260


def test_subsampling_never_repeats_and_stays_in_range():
    idx = est.subsample(101, 3.7)
    assert idx[0] == 0 and idx[-1] <= 100 and len(np.unique(idx)) == len(idx)
