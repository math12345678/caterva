"""Tests for competitive inhibition Michaelis-Menten domain.

Verify that the apparent Km under competitive inhibition is Km_app = Km*(1 + I/Ki)
and that the initial reaction rate matches Vmax * S / (Km_app + S). Also
check that at I=0 the kinetics reduce exactly to plain Michaelis-Menten.

Rule 1/2 edge cases (Constitution):
- Ki = 0 is physically impossible (division by zero in the inhibition term)
  and must be rejected with ok=False.
- Negative Km is physically impossible and must be rejected.
- Km outside the plausible bounds [1e-7, 1e3] mM must be flagged, not rejected.
"""


import pathlib
import sys

import pytest

from tellurium_engine import (
    ModelBuildError,
    simulate_mm_competitive_inhibition,
    simulate_michaelis_menten,
)

_REPO = pathlib.Path(__file__).resolve().parents[2]


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


def test_ki_zero_is_rejected():
    """Ki = 0 makes the inhibition term divide by zero; must be rejected."""
    with pytest.raises(ModelBuildError, match="Ki"):
        simulate_mm_competitive_inhibition(
            km=2.0, vmax=5.0, ki=0.0, s0=7.0, i=0.5, end=1e-4, points=3
        )


def test_negative_km_is_rejected():
    """Negative Km is physically impossible; must be rejected."""
    with pytest.raises(ModelBuildError, match="Km"):
        simulate_mm_competitive_inhibition(
            km=-1.0, vmax=5.0, ki=2.0, s0=7.0, i=0.5, end=1e-4, points=3
        )


def test_km_below_plausible_bound_is_flagged():
    """Km = 1e-8 mM is below the 1e-7 mM plausible floor; must be flagged."""
    res = simulate_mm_competitive_inhibition(
        km=1e-8, vmax=5.0, ki=2.0, s0=7.0, i=0.5, end=1e-4, points=3
    )
    assert res.flagged is True
    reason = res.validation.flag_reason or ""
    assert "below" in reason.lower() or "plausible" in reason.lower()


def test_km_above_plausible_bound_is_flagged():
    """Km = 2000 mM is above the 1000 mM plausible ceiling; must be flagged."""
    res = simulate_mm_competitive_inhibition(
        km=2000.0, vmax=5.0, ki=2.0, s0=7.0, i=0.5, end=1e-4, points=3
    )
    assert res.flagged is True
    reason = res.validation.flag_reason or ""
    assert "above" in reason.lower() or "plausible" in reason.lower()


def test_runner_rejects_a_request_with_no_vmax():
    """The API runner must not silently fall back to vmax = 5.0.

    resolveQuery()'s hard rule (RequiredParametersMissingError on any
    default-origin vmax) already stops any such request before the runner
    is spawned, so the fallback was dead code through the API. This test
    pins the runner-side rejection so the dead default cannot quietly
    become live again if the runner ever receives a bare request.
    """
    runner_dir = (
        _REPO
        / "Science-Agent-Pipeline"
        / "artifacts"
        / "api-server"
        / "src"
        / "lib"
    )
    if not runner_dir.is_dir():
        pytest.skip("api-server runner not present in this checkout")
    if str(runner_dir) not in sys.path:
        sys.path.insert(0, str(runner_dir))

    import tellurium_runner  # noqa: PLC0415

    with pytest.raises(ValueError, match="needs a Vmax"):
        tellurium_runner.run_mm_competitive_inhibition(
            {"km": 2.0, "ki": 1.0, "s0": 7.0, "i0": 0.5, "end": 1e-4, "points": 3}
        )
