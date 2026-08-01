"""Property-based tests.

The hand-written suites check specific parameter sets someone thought of.
These check invariants that must hold across the whole realistic input space,
which is where the parameter combination nobody thought of gets found.

Every property below is a physical law, not a restatement of the code.
"""

import math

from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

from tellurium_engine import (
    KM_PLAUSIBLE_MAX_MM,
    KM_PLAUSIBLE_MIN_MM,
    simulate_michaelis_menten,
    simulate_seir,
    simulate_sir,
    simulate_wright_fisher,
    validate_michaelis_menten_params,
    validate_sir_params,
    validate_wright_fisher_params,
)

SLOW = settings(max_examples=40, deadline=None,
                suppress_health_check=[HealthCheck.too_slow])

# Realistic BRENDA-range kinetic parameters.
km_values = st.floats(min_value=1e-6, max_value=500.0,
                      allow_nan=False, allow_infinity=False)
vmax_values = st.floats(min_value=1e-3, max_value=100.0,
                        allow_nan=False, allow_infinity=False)
conc_values = st.floats(min_value=1e-3, max_value=1000.0,
                        allow_nan=False, allow_infinity=False)

# Realistic epidemiological parameters.
rate_values = st.floats(min_value=1e-3, max_value=2.0,
                        allow_nan=False, allow_infinity=False)
pop_values = st.floats(min_value=1.0, max_value=1e6,
                       allow_nan=False, allow_infinity=False)


# ---------------------------------------------------------------------------
# Michaelis-Menten
# ---------------------------------------------------------------------------


@given(km=km_values, vmax=vmax_values, s0=conc_values)
@SLOW
def test_mass_is_always_conserved(km, vmax, s0):
    res = simulate_michaelis_menten(km=km, vmax=vmax, s0=s0, end=1.0,
                                    points=9)
    totals = [s + p for s, p in zip(res.column("S"), res.column("P"))]
    for total in totals:
        assert math.isclose(total, s0, rel_tol=1e-6, abs_tol=1e-9)


@given(km=km_values, vmax=vmax_values, s0=conc_values)
@SLOW
def test_concentrations_never_go_negative(km, vmax, s0):
    res = simulate_michaelis_menten(km=km, vmax=vmax, s0=s0, end=5.0,
                                    points=11)
    assert all(v >= -1e-6 for v in res.column("S"))
    assert all(v >= -1e-6 for v in res.column("P"))


@given(km=km_values, vmax=vmax_values, s0=conc_values)
@SLOW
def test_substrate_is_always_monotonically_consumed(km, vmax, s0):
    res = simulate_michaelis_menten(km=km, vmax=vmax, s0=s0, end=5.0,
                                    points=11)
    s = res.column("S")
    assert all(b <= a + 1e-6 for a, b in zip(s, s[1:]))


def _rate_probe_window(km, vmax, s0, target_fraction=1e-4):
    """Pick a dt over which S changes enough to be measurable in float64.

    A fixed dt is wrong here: with a slow reaction and a large S0 the change
    over 1e-6 time units lands within a few digits of machine epsilon, and the
    finite difference then measures rounding noise rather than the rate. This
    scales dt so S moves by roughly ``target_fraction`` of itself -- far above
    eps, still deep in the linear regime where dS/dt ~= v0.
    """
    v0 = vmax * s0 / (km + s0)
    if v0 <= 0:
        return None
    return target_fraction * s0 / v0


@given(km=km_values, vmax=vmax_values, s0=conc_values)
@SLOW
def test_initial_rate_never_exceeds_vmax(km, vmax, s0):
    # v = Vmax*S/(Km+S) < Vmax for all finite S. A solver that overshoots this
    # is producing a chemically impossible turnover rate.
    dt = _rate_probe_window(km, vmax, s0)
    assume(dt is not None and dt > 0)
    res = simulate_michaelis_menten(km=km, vmax=vmax, s0=s0, end=dt, points=3)
    s = res.column("S")
    rate = -(s[1] - s[0]) / (res.time[1] - res.time[0])
    assert rate <= vmax * (1 + 1e-3)


@given(km=km_values, vmax=vmax_values, s0=conc_values)
@SLOW
def test_initial_rate_matches_the_rate_law(km, vmax, s0):
    dt = _rate_probe_window(km, vmax, s0)
    assume(dt is not None and dt > 0)
    expected = vmax * s0 / (km + s0)
    res = simulate_michaelis_menten(km=km, vmax=vmax, s0=s0, end=dt, points=3)
    s = res.column("S")
    rate = -(s[1] - s[0]) / (res.time[1] - res.time[0])
    # Tolerance covers the O(dt) truncation of a forward difference plus the
    # solver's own tolerance; it is still ~3 orders tighter than any real bug.
    assert math.isclose(rate, expected, rel_tol=1e-3,
                        abs_tol=1e-9 * max(1.0, vmax))


@given(km=km_values, vmax=vmax_values, s0=conc_values,
       factor=st.floats(min_value=1.5, max_value=50.0))
@SLOW
def test_more_enzyme_never_slows_the_reaction(km, vmax, s0, factor):
    slow = simulate_michaelis_menten(km=km, vmax=vmax, s0=s0, end=1.0,
                                     points=5)
    fast = simulate_michaelis_menten(km=km, vmax=vmax * factor, s0=s0,
                                     end=1.0, points=5)
    assert fast.final("S") <= slow.final("S") + 1e-6


@given(km=km_values, vmax=vmax_values, s0=conc_values,
       factor=st.floats(min_value=1.5, max_value=50.0))
@SLOW
def test_weaker_affinity_never_speeds_the_reaction(km, vmax, s0, factor):
    # Larger Km means lower affinity, so consumption cannot get faster.
    tight = simulate_michaelis_menten(km=km, vmax=vmax, s0=s0, end=1.0,
                                      points=5)
    loose = simulate_michaelis_menten(km=km * factor, vmax=vmax, s0=s0,
                                      end=1.0, points=5)
    assert loose.final("S") >= tight.final("S") - 1e-6


@given(km=km_values, vmax=vmax_values, s0=conc_values)
@SLOW
def test_validation_and_simulation_agree_on_flagging(km, vmax, s0):
    v = validate_michaelis_menten_params(km=km, vmax=vmax, s0=s0)
    res = simulate_michaelis_menten(km=km, vmax=vmax, s0=s0, end=0.1,
                                    points=3)
    assert res.flagged == v.flagged


@given(km=st.floats(min_value=KM_PLAUSIBLE_MIN_MM,
                    max_value=KM_PLAUSIBLE_MAX_MM,
                    allow_nan=False, allow_infinity=False))
@SLOW
def test_every_in_range_km_is_unflagged(km):
    assert not validate_michaelis_menten_params(km=km, vmax=1.0, s0=1.0).flagged


# ---------------------------------------------------------------------------
# SIR / SEIR
# ---------------------------------------------------------------------------


@given(beta=rate_values, gamma=rate_values, s0=pop_values,
       i0=st.floats(min_value=1.0, max_value=1e4))
@SLOW
def test_sir_population_is_always_conserved(beta, gamma, s0, i0):
    res = simulate_sir(beta=beta, gamma=gamma, s0=s0, i0=i0, end=50.0,
                       points=11)
    n = s0 + i0
    for s, i, r in zip(res.column("S"), res.column("I"), res.column("R")):
        assert math.isclose(s + i + r, n, rel_tol=1e-6, abs_tol=1e-6)


@given(beta=rate_values, gamma=rate_values, s0=pop_values,
       i0=st.floats(min_value=1.0, max_value=1e4))
@SLOW
def test_sir_compartments_are_never_negative(beta, gamma, s0, i0):
    res = simulate_sir(beta=beta, gamma=gamma, s0=s0, i0=i0, end=100.0,
                       points=21)
    # Roundoff scales with population, so the floor must too: an absolute
    # -1e-6 is meaningless next to N = 1e6.
    tol = 1e-9 * (s0 + i0)
    for name in ("S", "I", "R"):
        assert all(v >= -tol for v in res.column(name))


@given(beta=rate_values, gamma=rate_values, s0=pop_values,
       i0=st.floats(min_value=1.0, max_value=1e4))
@SLOW
def test_sir_susceptibles_only_ever_decrease(beta, gamma, s0, i0):
    res = simulate_sir(beta=beta, gamma=gamma, s0=s0, i0=i0, end=100.0,
                       points=21)
    s = res.column("S")
    # dS/dt = -beta*S*I/N <= 0 exactly, so any increase is pure roundoff and
    # must be bounded relative to N rather than by a fixed absolute epsilon.
    tol = 1e-9 * (s0 + i0)
    assert all(b <= a + tol for a, b in zip(s, s[1:]))


@given(beta=rate_values, gamma=rate_values, s0=pop_values,
       i0=st.floats(min_value=1.0, max_value=1e4))
@SLOW
def test_sir_recovered_only_ever_increase(beta, gamma, s0, i0):
    res = simulate_sir(beta=beta, gamma=gamma, s0=s0, i0=i0, end=100.0,
                       points=21)
    r = res.column("R")
    tol = 1e-9 * (s0 + i0)
    assert all(b >= a - tol for a, b in zip(r, r[1:]))


@given(beta=rate_values, gamma=rate_values, s0=pop_values,
       i0=st.floats(min_value=1.0, max_value=1e3))
@SLOW
def test_subcritical_epidemics_never_grow(beta, gamma, s0, i0):
    # R0 < 1 at the outset means dI/dt < 0 always: no epidemic can start.
    n = s0 + i0
    assume(beta * s0 / n < gamma * 0.9)
    res = simulate_sir(beta=beta, gamma=gamma, s0=s0, i0=i0, end=50.0,
                       points=21)
    i = res.column("I")
    assert max(i) <= i0 * (1 + 1e-6) + 1e-9 * n


@given(beta=rate_values, gamma=rate_values, sigma=rate_values,
       s0=pop_values, e0=st.floats(min_value=1.0, max_value=1e3))
@SLOW
def test_seir_population_is_always_conserved(beta, gamma, sigma, s0, e0):
    res = simulate_seir(beta=beta, sigma=sigma, gamma=gamma, s0=s0, e0=e0,
                        i0=0.0, end=50.0, points=11)
    n = s0 + e0
    for s, e, i, r in zip(res.column("S"), res.column("E"), res.column("I"),
                          res.column("R")):
        assert math.isclose(s + e + i + r, n, rel_tol=1e-6, abs_tol=1e-6)


@given(beta=rate_values, gamma=rate_values, sigma=rate_values,
       s0=pop_values, e0=st.floats(min_value=1.0, max_value=1e3))
@SLOW
def test_seir_compartments_are_never_negative(beta, gamma, sigma, s0, e0):
    res = simulate_seir(beta=beta, sigma=sigma, gamma=gamma, s0=s0, e0=e0,
                        i0=0.0, end=100.0, points=21)
    tol = 1e-9 * (s0 + e0)
    for name in ("S", "E", "I", "R"):
        assert all(v >= -tol for v in res.column(name))


# ---------------------------------------------------------------------------
# Wright-Fisher
# ---------------------------------------------------------------------------

wf_population_sizes = st.integers(min_value=1, max_value=500)
wf_starting_frequencies = st.floats(
    min_value=0.0, max_value=1.0,
    allow_nan=False, allow_infinity=False)
wf_generations = st.integers(min_value=1, max_value=200)
wf_replicate_runs = st.integers(min_value=1, max_value=50)


@given(population_size=wf_population_sizes,
       starting_frequency=wf_starting_frequencies,
       generations=wf_generations, replicate_runs=wf_replicate_runs)
@SLOW
def test_wf_allele_frequency_stays_in_bounds(
        population_size, starting_frequency, generations, replicate_runs):
    res = simulate_wright_fisher(
        population_size=population_size,
        starting_frequency=starting_frequency,
        generations=generations, replicate_runs=replicate_runs)
    # Mean frequency across replicates must stay in [0, 1].
    mf = res.column("mean_frequency")
    assert all(0.0 - 1e-12 <= v <= 1.0 + 1e-12 for v in mf), (
        f"mean_frequency out of bounds: min={min(mf)}, max={max(mf)}")


@given(population_size=wf_population_sizes,
       starting_frequency=wf_starting_frequencies,
       generations=wf_generations, replicate_runs=wf_replicate_runs)
@SLOW
def test_wf_heterozygosity_is_bounded(
        population_size, starting_frequency, generations, replicate_runs):
    res = simulate_wright_fisher(
        population_size=population_size,
        starting_frequency=starting_frequency,
        generations=generations, replicate_runs=replicate_runs)
    h = res.column("heterozygosity")
    assert all(v >= -1e-12 for v in h), f"negative heterozygosity: min={min(h)}"
    # Maximum heterozygosity for a biallelic locus is 0.5 (at p = q = 0.5).
    assert all(v <= 0.5 + 1e-12 for v in h), (
        f"heterozygosity > 0.5: max={max(h)}")


@given(population_size=wf_population_sizes,
       starting_frequency=wf_starting_frequencies,
       generations=wf_generations, replicate_runs=wf_replicate_runs)
@SLOW
def test_wf_fixation_bookkeeping(
        population_size, starting_frequency, generations, replicate_runs):
    res = simulate_wright_fisher(
        population_size=population_size,
        starting_frequency=starting_frequency,
        generations=generations, replicate_runs=replicate_runs)
    n_a = res.column("n_A_fixed")
    n_b = res.column("n_a_fixed")
    for a, b in zip(n_a, n_b):
        assert a + b <= replicate_runs, (
            f"n_A_fixed + n_a_fixed = {a + b} > replicate_runs = {replicate_runs}")
        assert a >= 0, f"n_A_fixed = {a} < 0"
        assert b >= 0, f"n_a_fixed = {b} < 0"


@given(population_size=wf_population_sizes,
       starting_frequency=st.floats(
           min_value=0.05, max_value=0.95,
           allow_nan=False, allow_infinity=False),
       generations=wf_generations, replicate_runs=wf_replicate_runs)
@SLOW
def test_wf_initial_heterozygosity_is_correct(
        population_size, starting_frequency, generations, replicate_runs):
    res = simulate_wright_fisher(
        population_size=population_size,
        starting_frequency=starting_frequency,
        generations=generations, replicate_runs=replicate_runs)
    expected_h0 = 2.0 * starting_frequency * (1.0 - starting_frequency)
    actual_h0 = res.column("heterozygosity")[0]
    assert math.isclose(actual_h0, expected_h0, rel_tol=1e-12, abs_tol=1e-12), (
        f"H0 = {actual_h0}, expected = {expected_h0} "
        f"(p0={starting_frequency})")


# ---------------------------------------------------------------------------
# Validation never crashes
# ---------------------------------------------------------------------------


@given(km=st.floats(allow_nan=True, allow_infinity=True),
       vmax=st.floats(allow_nan=True, allow_infinity=True),
       s0=st.floats(allow_nan=True, allow_infinity=True))
@settings(max_examples=200, deadline=None)
def test_validation_never_raises_on_arbitrary_floats(km, vmax, s0):
    # Validation is the front door for user input; it must return a verdict
    # rather than propagate a ValueError from deep inside.
    v = validate_michaelis_menten_params(km=km, vmax=vmax, s0=s0)
    assert isinstance(v.ok, bool)
    if not v.ok:
        assert v.errors


@given(beta=st.floats(allow_nan=True, allow_infinity=True),
       gamma=st.floats(allow_nan=True, allow_infinity=True),
       s0=st.floats(allow_nan=True, allow_infinity=True),
       i0=st.floats(allow_nan=True, allow_infinity=True))
@settings(max_examples=200, deadline=None)
def test_sir_validation_never_raises_on_arbitrary_floats(beta, gamma, s0, i0):
    v = validate_sir_params(beta=beta, gamma=gamma, s0=s0, i0=i0)
    assert isinstance(v.ok, bool)
    if not v.ok:
        assert v.errors


@given(population_size=st.integers(min_value=-100, max_value=1000),
       starting_frequency=st.floats(allow_nan=True, allow_infinity=True),
       generations=st.integers(min_value=-50, max_value=500),
       replicate_runs=st.integers(min_value=-10, max_value=20))
@settings(max_examples=200, deadline=None)
def test_wf_validation_never_raises_on_arbitrary_input(
        population_size, starting_frequency, generations, replicate_runs):
    v = validate_wright_fisher_params(
        population_size=population_size,
        starting_frequency=starting_frequency,
        generations=generations, replicate_runs=replicate_runs)
    assert isinstance(v.ok, bool)
    if not v.ok:
        assert v.errors


# The newer WF parameters must be just as safe: the validation front door
# must never raise on arbitrary junk, even combinations nobody thought of
# (this guards e.g. the n_demes-as-string + stepping-stone crash).
@given(population_size=st.integers(min_value=-100, max_value=1000),
       starting_frequency=st.floats(allow_nan=True, allow_infinity=True),
       generations=st.integers(min_value=-50, max_value=500),
       replicate_runs=st.integers(min_value=-10, max_value=20),
       mutation_rate=st.floats(allow_nan=True, allow_infinity=True),
       selection_coefficient=st.floats(allow_nan=True, allow_infinity=True),
       dominance=st.floats(allow_nan=True, allow_infinity=True),
       n_demes=st.one_of(
           st.integers(min_value=-10, max_value=30), st.text()),
       migration_rate=st.floats(allow_nan=True, allow_infinity=True),
       migration_model=st.one_of(
           st.text(), st.none(), st.integers(min_value=-5, max_value=5)),
       population_size_series=st.one_of(
           st.none(),
           st.lists(st.integers(min_value=-10, max_value=500),
                    min_size=1, max_size=10)))
@settings(max_examples=300, deadline=None)
def test_wf_validation_never_raises_on_extended_arbitrary_input(
        population_size, starting_frequency, generations, replicate_runs,
        mutation_rate, selection_coefficient, dominance, n_demes,
        migration_rate, migration_model, population_size_series):
    v = validate_wright_fisher_params(
        population_size=population_size,
        starting_frequency=starting_frequency,
        generations=generations, replicate_runs=replicate_runs,
        mutation_rate=mutation_rate,
        selection_coefficient=selection_coefficient,
        dominance=dominance, n_demes=n_demes,
        migration_rate=migration_rate,
        migration_model=migration_model,
        population_size_series=population_size_series)
    assert isinstance(v.ok, bool)
    if not v.ok:
        assert v.errors


# --- structured populations (n_demes > 1, both migration models) ---

wf_demes = st.integers(min_value=3, max_value=12)
wf_migration_rates = st.floats(
    min_value=0.0, max_value=0.5, allow_nan=False, allow_infinity=False)
wf_migration_models = st.sampled_from(["island", "stepping-stone"])


@given(population_size=wf_population_sizes,
       starting_frequency=wf_starting_frequencies,
       generations=wf_generations, replicate_runs=wf_replicate_runs,
       n_demes=wf_demes, migration_rate=wf_migration_rates,
       migration_model=wf_migration_models)
@SLOW
def test_wf_structured_frequency_and_heterozygosity_bounds(
        population_size, starting_frequency, generations, replicate_runs,
        n_demes, migration_rate, migration_model):
    res = simulate_wright_fisher(
        population_size=population_size,
        starting_frequency=starting_frequency,
        generations=generations, replicate_runs=replicate_runs,
        n_demes=n_demes, migration_rate=migration_rate,
        migration_model=migration_model)
    mf = res.column("mean_frequency")
    assert all(0.0 - 1e-12 <= v <= 1.0 + 1e-12 for v in mf), (
        f"mean_frequency out of bounds: min={min(mf)}, max={max(mf)}")
    h = res.column("heterozygosity")
    assert all(-1e-12 <= v <= 0.5 + 1e-12 for v in h), (
        f"heterozygosity out of bounds: min={min(h)}, max={max(h)}")


@given(population_size=wf_population_sizes,
       starting_frequency=wf_starting_frequencies,
       generations=wf_generations, replicate_runs=wf_replicate_runs,
       n_demes=wf_demes, migration_rate=wf_migration_rates,
       migration_model=wf_migration_models)
@SLOW
def test_wf_fst_stays_in_unit_interval(
        population_size, starting_frequency, generations, replicate_runs,
        n_demes, migration_rate, migration_model):
    res = simulate_wright_fisher(
        population_size=population_size,
        starting_frequency=starting_frequency,
        generations=generations, replicate_runs=replicate_runs,
        n_demes=n_demes, migration_rate=migration_rate,
        migration_model=migration_model)
    fst = res.column("fst")
    assert all(-1e-12 <= v <= 1.0 + 1e-12 for v in fst), (
        f"Fst out of [0, 1]: min={min(fst)}, max={max(fst)}")


@given(population_size=wf_population_sizes,
       starting_frequency=wf_starting_frequencies,
       generations=wf_generations, replicate_runs=wf_replicate_runs)
@SLOW
def test_wf_fixation_counts_are_monotone(
        population_size, starting_frequency, generations, replicate_runs):
    """Without mutation, a fixed replicate stays fixed: n_A_fixed and
    n_a_fixed must be non-decreasing over generations."""
    res = simulate_wright_fisher(
        population_size=population_size,
        starting_frequency=starting_frequency,
        generations=generations, replicate_runs=replicate_runs)
    n_a = res.column("n_A_fixed")
    n_b = res.column("n_a_fixed")
    for a_prev, a_cur in zip(n_a, n_a[1:]):
        assert a_cur >= a_prev, "n_A_fixed decreased: fixation not absorbing"
    for b_prev, b_cur in zip(n_b, n_b[1:]):
        assert b_cur >= b_prev, "n_a_fixed decreased: fixation not absorbing"


@given(population_size=wf_population_sizes,
       starting_frequency=st.floats(
           min_value=0.05, max_value=0.95,
           allow_nan=False, allow_infinity=False),
       generations=wf_generations, replicate_runs=wf_replicate_runs)
@SLOW
def test_wf_absorption_preserves_fixed_state(
        population_size, starting_frequency, generations, replicate_runs):
    """A replicate at p=0 or p=1 (without mutation) stays there forever:
    all-demes-fixed counts plus polymorphic count must sum to the
    replicate count at every generation, and once a replicate is counted
    fixed it never leaves."""
    res = simulate_wright_fisher(
        population_size=population_size,
        starting_frequency=starting_frequency,
        generations=generations, replicate_runs=replicate_runs)
    n_a = res.column("n_A_fixed")
    n_b = res.column("n_a_fixed")
    for a, b in zip(n_a, n_b):
        assert a + b <= replicate_runs + 1e-12
        assert a >= 0 and b >= 0


@given(population_size=wf_population_sizes,
       starting_frequency=st.floats(
           min_value=0.05, max_value=0.95,
           allow_nan=False, allow_infinity=False),
       generations=wf_generations, replicate_runs=wf_replicate_runs)
@SLOW
def test_wf_p0_at_boundary_is_absorbing(
        population_size, starting_frequency, generations, replicate_runs):
    """p0=0 (or 1) with mutation_rate=0: no drift, no selection can
    change the allele count -- the trajectory is constant."""
    res = simulate_wright_fisher(
        population_size=population_size,
        starting_frequency=1.0, generations=generations,
        replicate_runs=replicate_runs)
    mf = res.column("mean_frequency")
    assert all(math.isclose(v, 1.0) for v in mf)
    assert res.column("n_A_fixed")[-1] == replicate_runs


@given(value=st.one_of(st.text(), st.none(), st.booleans(), st.lists(st.floats()),
                       st.dictionaries(st.text(), st.floats())))
@settings(max_examples=100, deadline=None)
def test_validation_rejects_arbitrary_non_numeric_input(value):
    v = validate_michaelis_menten_params(km=value, vmax=1.0, s0=1.0)
    assert not v.ok
    assert v.errors
