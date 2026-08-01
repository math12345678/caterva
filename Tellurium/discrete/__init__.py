"""Discrete/stochastic domains: PCR, Monte Carlo, molecular dynamics, and
population genetics (Wright-Fisher family)."""

try:
    from Tellurium.discrete.pcr import simulate_pcr
    from Tellurium.discrete.monte_carlo import simulate_monte_carlo_pi
    from Tellurium.discrete.molecular_dynamics import (
        lennard_jones_force,
        lj_cluster_positions,
        simulate_molecular_dynamics,
    )
    from Tellurium.discrete.population_genetics import (
        simulate_wright_fisher,
        wright_fisher_sweep,
        wright_fisher_transition_matrix,
        wright_fisher_fixation_probability,
        wright_fisher_expected_fixation_time,
        wright_fisher_expected_loss_time,
        wright_fisher_expected_absorption_time,
        wright_fisher_stationary_vector,
        wright_stationary_distribution,
        expected_loss_time,
        kimura_fixation_probability,
        expected_fixation_time,
        estimate_ne_from_heterozygosity,
        effective_size_harmonic_mean,
        theoretical_fst,
        expected_fst_after_split,
        TwoLocusResult,
        simulate_two_locus_wright_fisher,
        theoretical_ld_decay,
    )
except ModuleNotFoundError:  # flat mode
    from discrete.pcr import simulate_pcr
    from discrete.monte_carlo import simulate_monte_carlo_pi
    from discrete.molecular_dynamics import (
        lennard_jones_force,
        lj_cluster_positions,
        simulate_molecular_dynamics,
    )
    from discrete.population_genetics import (
        simulate_wright_fisher,
        wright_fisher_sweep,
        wright_fisher_transition_matrix,
        wright_fisher_fixation_probability,
        wright_fisher_expected_fixation_time,
        wright_fisher_expected_loss_time,
        wright_fisher_expected_absorption_time,
        wright_fisher_stationary_vector,
        wright_stationary_distribution,
        expected_loss_time,
        kimura_fixation_probability,
        expected_fixation_time,
        estimate_ne_from_heterozygosity,
        effective_size_harmonic_mean,
        theoretical_fst,
        expected_fst_after_split,
        TwoLocusResult,
        simulate_two_locus_wright_fisher,
        theoretical_ld_decay,
    )
