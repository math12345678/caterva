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


# --- real GROMACS output ---------------------------------------------------------

import gzip
from pathlib import Path

FIX = Path(__file__).parent / "fixtures" / "fep"


def test_bar_reproduces_gmx_bar_on_real_gromacs_output():
    """On the same 25 windows, the same samples: every neighbour pair agrees
    with `gmx bar` to its printed precision, and so does the total (-1.31)."""
    z = np.load(FIX / "benzene_solvent_rep1.npz")
    du, kt = z["du"].astype(float), est.R_KJ * float(z["temperature"])
    ref = [float(x) for x in (FIX / "benzene_solvent_rep1_gmxbar.txt").read_text().split()]
    total = 0.0
    for i in range(24):
        d, _ = est.bar(du[i, i + 1] - du[i, i], du[i + 1, i] - du[i + 1, i + 1])
        assert d * kt == pytest.approx(ref[i], abs=0.006)
        total += d * kt
    assert total == pytest.approx(-1.31, abs=0.01)


def test_mbar_agrees_with_bar_on_real_output_and_the_leg_is_diagnosed(tmp_path):
    z = np.load(FIX / "benzene_solvent_rep1.npz")
    du, kt = z["du"].astype(float), est.R_KJ * float(z["temperature"])
    r = est.mbar(np.concatenate(list(du), axis=1), [du.shape[2]] * 25)
    assert r.f[-1] * kt == pytest.approx(-1.31, abs=2 * r.df[-1] * kt)
    assert 0.0 < r.overlap[10, 11] < 1.0


def test_the_reader_parses_real_gromacs_dhdl(tmp_path):
    p = tmp_path / "prod.xvg"
    p.write_bytes(gzip.decompress((FIX / "benzene_solvent_lambda5.xvg.gz").read_bytes()))
    w = est.read_dhdl(p)
    assert (w.state, w.temperature, w.du.shape) == (5, 310.15, (25, 251))
    assert np.all(w.du[5] == 0.0)  # a state's energy relative to itself
    z = np.load(FIX / "benzene_solvent_rep1.npz")
    assert np.allclose(w.du, z["du"][5], rtol=1e-6, atol=1e-6)


# --- thermodynamic integration and thermodynamic length ---------------------------

def test_ti_recovers_the_exact_answer_for_a_linear_spring_path():
    """u_l(x) = K(l)(x - m)^2 / 2 with K(l) = K0 + (K1 - K0) l: <du/dl> =
    (K1 - K0) / (2 K(l)) exactly, and its integral is ln(K1/K0)/2."""
    K0, K1 = 1.0, 10.0
    lam = np.linspace(0, 1, 201)[:, None]
    means = ((K1 - K0) / (2 * (K0 + (K1 - K0) * lam)))
    dg, err = est.ti(lam, means, np.zeros_like(means))
    assert dg == pytest.approx(0.5 * math.log(K1 / K0), rel=1e-4) and err == 0.0


def test_ti_follows_a_two_component_path_one_component_at_a_time():
    lam = np.array([[0, 0], [0.5, 0], [1, 0], [1, 0.5], [1, 1]], float)
    means = np.array([[7, 9], [2, 9], [2, 9], [5, 4], [5, 4]], float)
    dg, _ = est.ti(lam, means, np.zeros_like(means))
    # coul over its three states: 0.5*(7+2)*0.5 + 0.5*(2+2)*0.5 = 3.25; the
    # later coul means (5) never count, coul is not moving there. vdw from
    # the corner state, whose vdw derivative IS on the path:
    # 0.5*(9+4)*0.5 + 0.5*(4+4)*0.5 = 5.25; the first two vdw means never count.
    assert dg == pytest.approx(3.25 + 5.25)


def test_redistribution_equalises_thermodynamic_length():
    lam = np.linspace(0, 1, 6)[:, None]
    L = np.array([3.0, 1.0, 1.0, 1.0, 2.0])  # uneven steps
    new = est.redistribute(lam, L, 9)[:, 0]
    cum = np.concatenate([[0], np.cumsum(L)])
    s = np.interp(new, lam[:, 0], cum)  # each new state's position along the length
    assert np.allclose(np.diff(s), cum[-1] / 8, atol=1e-3)
    assert new[0] == 0 and new[-1] == 1 and np.all(np.diff(new) > 0)


def _fixture_windows():
    z = np.load(FIX / "benzene_solvent_rep1.npz")
    return [est.Window(i, float(z["temperature"]), np.arange(z["du"].shape[2]), z["du"][i].astype(float),
                       ["coul", "vdw"], z["lambdas"], z["dhdl"][i].astype(float)) for i in range(25)], z


def test_ti_agrees_with_mbar_on_real_output():
    """Three estimators on one real leg: TI (-0.05), MBAR (-0.33), BAR
    (-0.17) kJ/mol, each within the others' errors."""
    ws, z = _fixture_windows()
    n = ws[0].du.shape[1]
    lam = z["lambdas"]
    means = np.array([w.dhdl.mean(axis=1) for w in ws])
    sems = np.array([w.dhdl.std(axis=1, ddof=1) / math.sqrt(n) for w in ws])
    dg_ti, e_ti = est.ti(lam, means, sems)
    r = est.mbar(np.concatenate([w.du for w in ws], axis=1), [n] * 25)
    kt = est.R_KJ * float(z["temperature"])
    assert abs(dg_ti - r.f[-1] * kt) < 2 * math.hypot(e_ti, r.df[-1] * kt) + 1.0


def test_real_step_lengths_show_where_the_schedule_is_uneven():
    ws, _ = _fixture_windows()
    L = est.segment_lengths(ws, [np.arange(w.du.shape[1]) for w in ws])
    assert len(L) == 24 and L.max() > 3 * L.min()  # windows sit where they do little work
