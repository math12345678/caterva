"""Tests moved from caterva/tests/test_numerical_robustness.py on 2026-09-27 with their domains."""

def test_century_long_epidemic_conserves_population():
    res = simulate_sir(beta=0.3, gamma=0.1, s0=1e6, i0=10.0, end=36500.0,
                       points=201)
    n = 1e6 + 10.0
    totals = [s + i + r for s, i, r in
              zip(res.column("S"), res.column("I"), res.column("R"))]
    np.testing.assert_allclose(totals, [n] * len(totals), rtol=1e-9)


def test_epidemic_does_not_revive_after_burnout():
    # Once I hits zero it must stay there; a solver that lets it go negative
    # and rebound would invent a second wave that does not exist.
    res = simulate_sir(beta=0.6, gamma=0.15, s0=1e5, i0=1.0, end=5000.0,
                       points=501)
    i = res.column("I")
    peak_index = i.index(max(i))
    tail = i[peak_index:]
    assert all(b <= a * (1 + 1e-6) + 1e-6 for a, b in zip(tail, tail[1:])), (
        "infections increased again after the epidemic peak")


@pytest.mark.parametrize("n", [1e3, 1e6, 1e9])
def test_epidemics_scale_to_large_populations(n):
    i0 = n * 1e-5
    res = simulate_sir(beta=0.4, gamma=0.1, s0=n - i0, i0=i0, end=200.0,
                       points=51)
    totals = [s + i + r for s, i, r in
              zip(res.column("S"), res.column("I"), res.column("R"))]
    np.testing.assert_allclose(totals, [n] * len(totals), rtol=1e-9)
    assert res.final("R") > i0, "an epidemic should have occurred"


def test_epidemic_shape_is_population_invariant():
    """The attack rate depends only on R0, not on absolute population size."""
    small = simulate_sir(beta=0.4, gamma=0.1, s0=1e3 - 1, i0=1, end=2000.0,
                         points=101)
    large = simulate_sir(beta=0.4, gamma=0.1, s0=1e6 - 1e3, i0=1e3,
                         end=2000.0, points=101)
    assert (small.final("R") / 1e3) == pytest.approx(
        large.final("R") / 1e6, rel=1e-2)


@pytest.mark.parametrize("points", [11, 501])
def test_epidemic_endpoint_is_independent_of_resolution(points):
    res = simulate_sir(beta=0.4, gamma=0.1, s0=999, i0=1, end=500.0,
                       points=points)
    assert res.final("S") == pytest.approx(19.8058, rel=1e-3)


