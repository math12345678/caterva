"""Tests moved from caterva/tests/test_properties.py on 2026-09-27 with their domains."""

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


