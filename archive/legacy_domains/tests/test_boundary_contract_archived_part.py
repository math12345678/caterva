# Parts of caterva/tests/test_boundary_contract.py that exercised domains
# archived on 2026-09-27. Kept for reference; not collected.

        "sir": {"beta": 0.3, "gamma": 0.1, "s0": 990.0, "i0": 10.0, "end": 10.0, "points": 4},
        "seir": {"beta": 0.3, "sigma": 0.2, "gamma": 0.1, "e0": 10.0, "end": 10.0, "points": 4},
        "pcr": {"n0": 100.0, "efficiency": 0.95, "cycles": 5},
        "monte_carlo_pi": {"n_samples": 64},
        "wright_fisher": {
            "population_size": 40, "starting_frequency": 0.5, "generations": 5,
            "replicate_runs": 3,
        },
        "two_locus_wright_fisher": {
            "population_size": 40, "generations": 5, "recombination_rate": 0.1,
            "replicate_runs": 3,
        },
        "molecular_dynamics": {
            "n_particles": 13, "temperature": 0.4, "timestep": 0.005, "n_steps": 5,
        },

    # ---- MD quadratic-cost ceiling -------------------------------------
    #
    # n_steps alone does not bound an MD request: cost is O(N^2 * steps) and
    # the engine ACCEPTS n_particles=5000 (ok=True, merely flagged, then
    # rounded up to 5324). Measured before the fix: 800 particles at 200
    # steps -- 4% of the step ceiling -- already cost 9.94s, and 5000
    # particles at the step ceiling is roughly six hours.
    def test_md_pair_step_budget_rejects_large_particle_counts(self):
        """A request under every scalar ceiling but quadratically huge."""
        with pytest.raises(ValueError, match="pair-steps"):
            runner.run_molecular_dynamics({"n_particles": 5000, "n_steps": 100})

    def test_md_pair_step_budget_rejects_at_step_ceiling(self):
        with pytest.raises(ValueError, match="pair-steps"):
            runner.run_molecular_dynamics(
                {"n_particles": 5000, "n_steps": runner.MAX_API_MD_STEPS})

    def test_md_documented_reference_case_stays_within_budget(self):
        """108 particles x 10k steps is the documented case and must remain
        allowed -- a budget that rejects it would be miscalibrated."""
        actual = runner._fcc_particle_count(108)  # noqa: SLF001
        assert actual * actual * runner.MAX_API_MD_STEPS <= runner.MAX_API_MD_PAIR_STEPS

    def test_fcc_round_up_matches_engine(self):
        """The budget must use the count the engine actually simulates.

        Rounding is always upward, so budgeting on the requested count would
        systematically underestimate cost.
        """
        assert runner._fcc_particle_count(108) == 108      # 4 * 3^3  # noqa: SLF001
        assert runner._fcc_particle_count(5000) == 5324    # 4 * 11^3  # noqa: SLF001
        assert runner._fcc_particle_count(1) == 4          # smallest cell  # noqa: SLF001
        for requested in (5, 33, 100, 500, 900):
            actual = runner._fcc_particle_count(requested)  # noqa: SLF001
            assert actual >= requested
            k = round((actual / 4) ** (1 / 3))
            assert actual == 4 * k**3
            assert 4 * (k - 1) ** 3 < requested  # k is the smallest sufficient

