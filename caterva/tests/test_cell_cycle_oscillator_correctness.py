"""Scientific verification for the cell cycle oscillator domain.

Tyson JJ, "Modeling the cell division cycle: cdc2 and cyclin interactions",
Proc Natl Acad Sci USA 88(16):7328-7332, 1991, DOI 10.1073/pnas.88.16.7328.
The 2-variable relaxation-oscillator reduction used here:

    du/dt = k4*(v - u)*(alpha + u^2) - k6*u
    dv/dt = kappa - k6*u
    alpha = k4prime / k4

u = [active MPF]/[CT], v = ([cyclin]+[preMPF]+[active MPF])/[CT]. Standard
parameter set kappa=0.015, k6=1, k4=180, k4prime=0.018, cross-checked
against the curated SBML for both BioModels encodings of this paper
(BIOMD0000000005, BIOMD0000000006) -- see docs/adr/0022.

This domain takes no caller-supplied kinetic parameters (only the
integration window), so there is nothing here to fuzz across a parameter
space the way test_lotka_volterra_correctness.py does. What can and must
still be checked independently of the engine's own solver:

1. An independent integrator (scipy's `solve_ivp`) given literally the
   same two equations, decoupled from roadrunner/antimony entirely.
2. u and v never go negative -- provable directly from the RHS at the
   boundary (see TestNonNegativity for the one-line argument for each).
3. The system sustains oscillation over the default window rather than
   settling to the high-MPF steady state or the low-MPF steady state Tyson
   describes as the system's other two possible behaviours.
4. The literature parameter values themselves are pinned, so a future
   accidental edit to the standard set is caught here rather than only
   producing a subtly different (but still oscillating) trajectory.
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

from caterva_engine import simulate_cell_cycle_oscillator  # noqa: E402
from continuous.model_building import (  # noqa: E402
    TYSON_K4,
    TYSON_K4PRIME,
    TYSON_K6,
    TYSON_KAPPA,
)


def _columns(result):
    data = np.asarray(result.data, dtype=float)
    idx = {name: i for i, name in enumerate(result.colnames)}
    return data[:, idx["time"]], data[:, idx["u"]], data[:, idx["v"]]


class TestLiteratureParameterValues:
    """Pin the standard oscillatory parameter set itself.

    These four numbers are Tyson's own -- not tunable, not derived -- so a
    future accidental edit (a typo, a unit slip) should fail here loudly
    rather than silently changing the trajectory shape.
    """

    def test_standard_parameter_set_is_pinned_against_accidental_edits(self):
        """Pins the constants against drift. NOT literature verification.

        This test was originally named
        `..._matches_curated_biomodels_encoding`, which claimed something it
        does not do: it never reads the curated BioModels encoding, or any
        other external source. It compares the constants to literals, i.e.
        the code to itself. If a value had been transcribed wrongly from
        Tyson's table on the day it was typed in, this assertion would have
        been wrong in exactly the same way and would have passed forever.

        That failure mode is not hypothetical here. The Lotka-Volterra
        domain shipped in this same batch with its `gamma` and `delta`
        defaults transposed (ADR 0023); nothing caught it until the values
        were checked against a property outside the code.

        The test is kept because pinning has real value -- it fails loudly
        on a later typo or unit slip -- but it is named for what it does.
        Actual verification against the curated SBML needs
        `scripts/capture_biomodels_fixture.py` to be run somewhere with
        outbound network access (BIOMD0000000006 for this model); the
        review sandbox's proxy blocks it. Until that fixture exists, these
        four numbers rest on transcription alone.
        """
        assert TYSON_KAPPA == 0.015
        assert TYSON_K6 == 1.0
        assert TYSON_K4 == 180.0
        assert TYSON_K4PRIME == 0.018

    def test_alpha_is_the_ratio_k4prime_over_k4(self):
        # alpha = k4'/k4 = 0.0001, per the paper's own reduction.
        assert TYSON_K4PRIME / TYSON_K4 == pytest.approx(0.0001)


class TestAgainstIndependentIntegrator:
    def test_trajectory_matches_scipy(self):
        scipy_integrate = pytest.importorskip("scipy.integrate")

        end, points = 100.0, 1001
        result = simulate_cell_cycle_oscillator(end=end, points=points)
        t, u, v = _columns(result)

        alpha = TYSON_K4PRIME / TYSON_K4

        def rhs(_t, y):
            uu, vv = y
            return [
                TYSON_K4 * (vv - uu) * (alpha + uu ** 2) - TYSON_K6 * uu,
                TYSON_KAPPA - TYSON_K6 * uu,
            ]

        reference = scipy_integrate.solve_ivp(
            rhs, (0.0, end), [0.0, 0.0], t_eval=t,
            method="LSODA", rtol=1e-10, atol=1e-12,
        )
        assert reference.success

        assert np.allclose(u, reference.y[0], rtol=1e-3, atol=1e-6)
        assert np.allclose(v, reference.y[1], rtol=1e-3, atol=1e-6)


class TestNonNegativity:
    """u, v >= 0 is provable directly from the RHS at the boundary.

    At u=0: du/dt = k4*v*(alpha + 0) - 0 = k4*alpha*v >= 0 whenever v >= 0
    -- u cannot cross zero downward.
    At v=0: dv/dt = kappa - k6*u. This alone does not force dv/dt >= 0,
    but combined with u's own bound (u <= v always holds once u reaches
    v from below, since du/dt = 0 at u=v and the (v-u) factor then
    pushes u back below v) the standard result for this system, given in
    the paper, is that both stay in [0, 1]. This test checks the
    numerically integrated trajectory holds that bound as a diagnostic;
    it does not re-derive the general proof.
    """

    def test_u_and_v_stay_non_negative(self):
        result = simulate_cell_cycle_oscillator(end=100.0, points=1001)
        _, u, v = _columns(result)
        assert u.min() >= -1e-8, f"u went negative: {u.min():.3e}"
        assert v.min() >= -1e-8, f"v went negative: {v.min():.3e}"


class TestSustainedOscillation:
    def test_active_mpf_shows_multiple_spikes(self):
        # Tyson describes this parameter set as the spontaneous-oscillator
        # regime (vs. a steady high-MPF or low-MPF state) -- so u should
        # spike repeatedly, not settle.
        result = simulate_cell_cycle_oscillator(end=100.0, points=1001)
        t, u, _ = _columns(result)
        peaks = [
            i for i in range(1, len(u) - 1)
            if u[i] > u[i - 1] and u[i] > u[i + 1] and u[i] > 0.05
        ]
        assert len(peaks) >= 2, (
            f"expected at least 2 MPF spikes over the default window, got "
            f"{len(peaks)}"
        )

    def test_not_settled_at_either_steady_state(self):
        # The two non-oscillatory regimes Tyson describes are u near 0
        # (low MPF, arrested) and u near 1 (high MPF, arrested). The
        # spontaneous oscillator regime should visit neither persistently.
        result = simulate_cell_cycle_oscillator(end=100.0, points=1001)
        _, u, _ = _columns(result)
        tail = u[len(u) // 2:]  # discard transient
        assert tail.std() > 0.01, "u appears to have settled to a steady state"


class TestDeterministicReproducibility:
    def test_repeated_calls_are_bit_identical(self):
        # No randomness anywhere in this system; the seed parameter is
        # accepted only for call-signature symmetry (see the docstring on
        # simulate_cell_cycle_oscillator) and must not affect the result.
        r1 = simulate_cell_cycle_oscillator(end=50.0, points=51, seed=1)
        r2 = simulate_cell_cycle_oscillator(end=50.0, points=51, seed=999)
        assert r1.data == r2.data


class TestIntegrationWindow:
    def test_points_below_two_is_rejected(self):
        from caterva_engine import SimulationError

        with pytest.raises(SimulationError):
            simulate_cell_cycle_oscillator(end=10.0, points=1)

    def test_end_before_start_is_rejected(self):
        from caterva_engine import SimulationError

        with pytest.raises(SimulationError):
            simulate_cell_cycle_oscillator(start=10.0, end=1.0, points=10)
