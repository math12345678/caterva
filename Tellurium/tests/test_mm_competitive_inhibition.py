"""Tests for competitive inhibition Michaelis-Menten domain.

Verify that the apparent Km under competitive inhibition is Km_app = Km*(1 + I/Ki)
and that the initial reaction rate matches Vmax * S / (Km_app + S). Also
check that at I=0 the kinetics reduce exactly to plain Michaelis-Menten.
"""


import pytest

from tellurium_engine import (
    simulate_mm_competitive_inhibition,
    simulate_michaelis_menten,
)


def approx_initial_rate(res):
    # estimate initial dS/dt by finite difference over a short interval
    s = res.column("S")
    dt = res.time[1] - res.time[0]
    dsdt = (s[1] - s[0]) / dt
    return -dsdt


def test_initial_rate_matches_apparent_km():
    km, vmax, ki, s0, i = 2.0, 5.0, 2.0, 7.0, 0.5
    km_app = km * (1.0 + i / ki)
    expected = vmax * s0 / (km_app + s0)
    res = simulate_mm_competitive_inhibition(km=km, vmax=vmax, ki=ki, s0=s0, i=i,
                                             end=1e-4, points=3)
    initial_rate = approx_initial_rate(res)
    assert initial_rate == pytest.approx(expected, rel=1e-3)


def test_i_zero_reduces_to_plain_mm():
    km, vmax, s0 = 2.0, 5.0, 7.0
    res_comp = simulate_mm_competitive_inhibition(km=km, vmax=vmax, ki=1.0, s0=s0, i=0.0,
                                                  end=1e-4, points=3)
    res_mm = simulate_michaelis_menten(km=km, vmax=vmax, s0=s0, end=1e-4, points=3)
    # compare initial rate
    rate_comp = approx_initial_rate(res_comp)
    rate_mm = approx_initial_rate(res_mm)
    assert rate_comp == pytest.approx(rate_mm, rel=1e-6)
