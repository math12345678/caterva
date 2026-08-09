"""Scientific verification for the repressilator domain.

Elowitz MB, Leibler S, "A synthetic oscillatory network of transcriptional
regulators", Nature 403:335-338, 2000, DOI 10.1038/35002131. The
dimensionless "deterministic, continuous approximation" (p.337):

    dm_i/dt = -m_i + alpha/(1 + p_j^n) + alpha0    (j represses i)
    dp_i/dt = -beta*(p_i - m_i)

for the cyclic repression lacI -| tetR -| cI -| lacI. Parameter values
(alpha=216, alpha0/alpha=0.001, beta=5, n=2) are the point the paper's own
Figure 2b identifies as producing spontaneous oscillation, transcribed from
a course exercise built directly around this paper (Cornell Physics 7682)
-- see docs/adr/0022.

As with the cell cycle oscillator, this domain takes no caller-supplied
kinetic parameters, so verification is against independently derivable
properties of the fixed system rather than a swept parameter space:

1. An independent integrator (scipy's `solve_ivp`) given literally the
   same six equations.
2. Non-negativity of every mRNA and protein concentration -- provable
   directly from the RHS at the boundary.
3. Sustained oscillation with the three genes visibly out of phase with
   each other -- the repressilator's defining qualitative signature,
   distinguishing it from three independent copies of the same
   oscillator running in sync.
4. The literature parameter values are pinned.
"""

from __future__ import annotations

import pathlib
import sys

import numpy as np
import pytest

_HERE = pathlib.Path(__file__).resolve().parent
for _p in (str(_HERE.parent), str(_HERE.parent.parent)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from tellurium_engine import simulate_repressilator  # noqa: E402
from continuous.model_building import (  # noqa: E402
    REPRESSILATOR_ALPHA,
    REPRESSILATOR_ALPHA0,
    REPRESSILATOR_BETA,
    REPRESSILATOR_N,
)


def _columns(result):
    data = np.asarray(result.data, dtype=float)
    idx = {name: i for i, name in enumerate(result.colnames)}
    order = ["time", "m1", "m2", "m3", "p1", "p2", "p3"]
    return [data[:, idx[name]] for name in order]


class TestLiteratureParameterValues:
    def test_standard_oscillatory_parameter_set(self):
        assert REPRESSILATOR_ALPHA == 216.0
        assert REPRESSILATOR_BETA == 5.0
        assert REPRESSILATOR_N == 2.0

    def test_alpha0_is_the_papers_leakiness_ratio(self):
        # Fig 2b's "X" point: alpha0/alpha = 0.001.
        assert REPRESSILATOR_ALPHA0 / REPRESSILATOR_ALPHA == pytest.approx(0.001)


class TestAgainstIndependentIntegrator:
    def test_trajectory_matches_scipy(self):
        scipy_integrate = pytest.importorskip("scipy.integrate")

        end, points = 200.0, 2001
        result = simulate_repressilator(end=end, points=points)
        t, m1, m2, m3, p1, p2, p3 = _columns(result)

        alpha, alpha0 = REPRESSILATOR_ALPHA, REPRESSILATOR_ALPHA0
        beta, n = REPRESSILATOR_BETA, REPRESSILATOR_N

        def rhs(_t, y):
            m1_, m2_, m3_, p1_, p2_, p3_ = y
            return [
                -m1_ + alpha / (1 + p3_ ** n) + alpha0,
                -m2_ + alpha / (1 + p1_ ** n) + alpha0,
                -m3_ + alpha / (1 + p2_ ** n) + alpha0,
                -beta * (p1_ - m1_),
                -beta * (p2_ - m2_),
                -beta * (p3_ - m3_),
            ]

        y0 = [0.0, 0.0, 0.0, 1.0, 2.0, 3.0]
        reference = scipy_integrate.solve_ivp(
            rhs, (0.0, end), y0, t_eval=t,
            method="LSODA", rtol=1e-10, atol=1e-12,
        )
        assert reference.success

        for observed, ref in zip((m1, m2, m3, p1, p2, p3), reference.y):
            assert np.allclose(observed, ref, rtol=1e-3, atol=1e-6)


class TestNonNegativity:
    """Provable directly from the RHS at the boundary.

    At m_i=0: dm_i/dt = alpha/(1+p_j^n) + alpha0 > 0 always (alpha,
    alpha0 > 0) -- m_i cannot cross zero downward.
    At p_i=0: dp_i/dt = beta*m_i >= 0 whenever m_i >= 0 -- p_i cannot
    cross zero downward either, given the mRNA bound above.
    """

    def test_all_six_species_stay_non_negative(self):
        result = simulate_repressilator(end=200.0, points=2001)
        _, m1, m2, m3, p1, p2, p3 = _columns(result)
        for name, col in (("m1", m1), ("m2", m2), ("m3", m3),
                          ("p1", p1), ("p2", p2), ("p3", p3)):
            assert col.min() >= -1e-6, f"{name} went negative: {col.min():.3e}"


class TestSustainedOscillationOutOfPhase:
    def _peak_times(self, t, series, threshold):
        return [
            t[i] for i in range(1, len(series) - 1)
            if series[i] > series[i - 1] and series[i] > series[i + 1]
            and series[i] > threshold
        ]

    def test_each_protein_oscillates_repeatedly(self):
        result = simulate_repressilator(end=200.0, points=2001)
        t, _, _, _, p1, p2, p3 = _columns(result)
        for name, col in (("p1", p1), ("p2", p2), ("p3", p3)):
            peaks = self._peak_times(t, col, threshold=col.max() * 0.5)
            assert len(peaks) >= 3, (
                f"{name} shows fewer than 3 sustained oscillation peaks "
                f"over the default window ({len(peaks)})"
            )

    def test_the_three_proteins_are_not_in_phase(self):
        # The repressilator's defining signature: p1, p2, p3 peak in a
        # staggered sequence (each represses the next), not simultaneously.
        # If they were in phase, the peak-time lists would coincide.
        result = simulate_repressilator(end=200.0, points=2001)
        t, _, _, _, p1, p2, p3 = _columns(result)
        peaks1 = self._peak_times(t, p1, threshold=p1.max() * 0.5)
        peaks2 = self._peak_times(t, p2, threshold=p2.max() * 0.5)
        assert len(peaks1) >= 2 and len(peaks2) >= 2
        # Nearest-peak offset between p1 and p2 should be a meaningful
        # fraction of the period, not near-zero (in phase) or near-full
        # period (aliased back to in phase).
        period = float(np.mean(np.diff(peaks1)))
        offset = min(abs(peaks1[0] - p2t) for p2t in peaks2) % period
        assert period * 0.15 < offset < period * 0.85, (
            f"p1/p2 peaks are nearly in phase (offset {offset:.2f} of "
            f"period {period:.2f}); expected a staggered cyclic pattern"
        )

    def test_phase_offsets_are_exactly_one_and_two_thirds_of_a_period(self):
        """The exact prediction, not merely "staggered".

        The repressilator's three genes are wired as a symmetric ring: each
        represses the next, with identical kinetic constants. The system is
        therefore *equivariant* under the cyclic permutation
        (1->2->3->1) combined with a time shift -- the only periodic
        solution consistent with that symmetry has the three proteins
        separated by exactly one third of a period.

        This is a structural consequence of the ring's symmetry, derivable
        without integrating anything, which is what makes it usable as a
        check on the integrator. The looser test above (offset somewhere
        between 0.15 and 0.85 of a period) is satisfied by almost any
        non-degenerate waveform; this one is satisfied only by the correct
        one, and it fails if any single gene's parameters drift away from
        the others' -- the most likely way to break a symmetric ring by
        accident.
        """
        result = simulate_repressilator(end=400.0, points=16001)
        t, _, _, _, p1, p2, p3 = _columns(result)

        # Discard the transient: the ring starts from an asymmetric initial
        # condition and settles onto the limit cycle, where the symmetry
        # argument applies.
        settled = t > 100.0
        t_s = t[settled]

        def peak_times(series):
            y = series[settled]
            return np.array([
                t_s[i]
                for i in range(1, len(y) - 1)
                if y[i] > y[i - 1] and y[i] >= y[i + 1] and y[i] > 0.5 * y.max()
            ])

        pk1, pk2, pk3 = peak_times(p1), peak_times(p2), peak_times(p3)
        assert len(pk1) >= 3, "not enough settled cycles to measure phase"

        period = float(np.mean(np.diff(pk1)))

        def phase_of(peaks):
            return float(((peaks[0] - pk1[0]) % period) / period)

        # p2 and p3 sit at 1/3 and 2/3 of a period from p1 (in whichever
        # order the ring's orientation produces -- the orientation is a
        # labelling convention, the spacing is not).
        observed = sorted([phase_of(pk2), phase_of(pk3)])
        assert observed[0] == pytest.approx(1 / 3, abs=0.01), (
            f"nearest phase offset {observed[0]:.4f} of a period, expected "
            f"1/3 = {1/3:.4f}"
        )
        assert observed[1] == pytest.approx(2 / 3, abs=0.01), (
            f"far phase offset {observed[1]:.4f} of a period, expected "
            f"2/3 = {2/3:.4f}"
        )


class TestDeterministicReproducibility:
    def test_repeated_calls_are_bit_identical(self):
        r1 = simulate_repressilator(end=50.0, points=51, seed=1)
        r2 = simulate_repressilator(end=50.0, points=51, seed=999)
        assert r1.data == r2.data


class TestIntegrationWindow:
    def test_points_below_two_is_rejected(self):
        from tellurium_engine import SimulationError

        with pytest.raises(SimulationError):
            simulate_repressilator(end=10.0, points=1)

    def test_end_before_start_is_rejected(self):
        from tellurium_engine import SimulationError

        with pytest.raises(SimulationError):
            simulate_repressilator(start=10.0, end=1.0, points=10)
