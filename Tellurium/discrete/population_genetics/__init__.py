"""Wright-Fisher population genetics: simulation core, analysis, Markov-chain
probability machinery, theoretical results, and the two-locus model."""

try:
    from Tellurium.discrete.population_genetics.core import (
        simulate_wright_fisher,
        _clamp_wf_fst_roundoff,
    )
    from Tellurium.discrete.population_genetics.analysis import (
        wright_fisher_sweep,
        expected_loss_time,
    )
    from Tellurium.discrete.population_genetics.probability import (
        wright_fisher_transition_matrix,
        wright_fisher_fixation_probability,
        wright_fisher_expected_fixation_time,
        wright_fisher_expected_loss_time,
        wright_fisher_expected_absorption_time,
        wright_fisher_stationary_vector,
        wright_stationary_distribution,
    )
    from Tellurium.discrete.population_genetics.theoretical import (
        kimura_fixation_probability,
        expected_fixation_time,
        estimate_ne_from_heterozygosity,
        effective_size_harmonic_mean,
        theoretical_fst,
        expected_fst_after_split,
    )
    from Tellurium.discrete.population_genetics.two_locus import (
        TwoLocusResult,
        simulate_two_locus_wright_fisher,
        theoretical_ld_decay,
    )
except ModuleNotFoundError:  # flat mode
    from discrete.population_genetics.core import (
        simulate_wright_fisher,
        _clamp_wf_fst_roundoff,
    )
    from discrete.population_genetics.analysis import (
        wright_fisher_sweep,
        expected_loss_time,
    )
    from discrete.population_genetics.probability import (
        wright_fisher_transition_matrix,
        wright_fisher_fixation_probability,
        wright_fisher_expected_fixation_time,
        wright_fisher_expected_loss_time,
        wright_fisher_expected_absorption_time,
        wright_fisher_stationary_vector,
        wright_stationary_distribution,
    )
    from discrete.population_genetics.theoretical import (
        kimura_fixation_probability,
        expected_fixation_time,
        estimate_ne_from_heterozygosity,
        effective_size_harmonic_mean,
        theoretical_fst,
        expected_fst_after_split,
    )
    from discrete.population_genetics.two_locus import (
        TwoLocusResult,
        simulate_two_locus_wright_fisher,
        theoretical_ld_decay,
    )
