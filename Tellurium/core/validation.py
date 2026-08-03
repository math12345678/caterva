"""Parameter validation for every domain. Shared contract: ok/flagged/flag_reason."""

from __future__ import annotations

import math
from typing import Any, List, Sequence

import numpy as np
try:
    from Tellurium.core.data_structures import (ParameterValidation, KM_PLAUSIBLE_MIN_MM, KM_PLAUSIBLE_MAX_MM, R0_IMPLAUSIBLE_ABOVE, PCR_MIN_EFFICIENCY, PCR_MAX_EFFICIENCY, PCR_PLAUSIBLE_LOW_EFFICIENCY, MC_PLAUSIBLE_MIN_SAMPLES, WF_PLAUSIBLE_MIN_POPULATION_SIZE, WF_PLAUSIBLE_MAX_GENERATIONS, WF_PLAUSIBLE_MIN_REPLICATE_RUNS, WF_PLAUSIBLE_MAX_MUTATION_RATE, WF_PLAUSIBLE_MAX_SELECTION_COEFFICIENT, MD_PLAUSIBLE_MIN_PARTICLES, MD_PLAUSIBLE_MAX_TIMESTEP, MD_PLAUSIBLE_TEMPERATURE_LOW, MD_PLAUSIBLE_TEMPERATURE_HIGH, SSA_PLAUSIBLE_MIN_POPULATION, SSA_PLAUSIBLE_MAX_RATE, SSA_BIMOLECULAR_PLAUSIBLE_MAX_RATE, SSA_PLAUSIBLE_MIN_REPLICATES, ENZYME_CONC_MM_RATIO_FLAG_ABOVE)
except ModuleNotFoundError:  # flat mode: Tellurium/ on sys.path, no repo root
    from core.data_structures import (ParameterValidation, KM_PLAUSIBLE_MIN_MM, KM_PLAUSIBLE_MAX_MM, R0_IMPLAUSIBLE_ABOVE, PCR_MIN_EFFICIENCY, PCR_MAX_EFFICIENCY, PCR_PLAUSIBLE_LOW_EFFICIENCY, MC_PLAUSIBLE_MIN_SAMPLES, WF_PLAUSIBLE_MIN_POPULATION_SIZE, WF_PLAUSIBLE_MAX_GENERATIONS, WF_PLAUSIBLE_MIN_REPLICATE_RUNS, WF_PLAUSIBLE_MAX_MUTATION_RATE, WF_PLAUSIBLE_MAX_SELECTION_COEFFICIENT, MD_PLAUSIBLE_MIN_PARTICLES, MD_PLAUSIBLE_MAX_TIMESTEP, MD_PLAUSIBLE_TEMPERATURE_LOW, MD_PLAUSIBLE_TEMPERATURE_HIGH, SSA_PLAUSIBLE_MIN_POPULATION, SSA_PLAUSIBLE_MAX_RATE, SSA_BIMOLECULAR_PLAUSIBLE_MAX_RATE, SSA_PLAUSIBLE_MIN_REPLICATES, ENZYME_CONC_MM_RATIO_FLAG_ABOVE)  # type: ignore[no-redef]

def _finite_positive(value: Any, label: str, errors: List[str],
                     allow_zero: bool = False) -> bool:
    """Validate that a value is a finite, non‑negative number.
    
    Args:
        value: The value to validate
        label: Human‑readable name for the value (used in error messages)
        errors: List to which error messages should be appended
        allow_zero: Whether zero is allowed (used for population/counts)
        
    Returns:
        False if the value is invalid, True if valid
    """
    if isinstance(value, (bool, np.bool_)):
        errors.append(f"{label} must be a number, not a boolean")
        return False
    
    if not isinstance(value, (int, float, np.integer, np.floating)):
        errors.append(f"{label} must be a number, got {type(value).__name__}")
        return False
    
    if math.isnan(value):
        errors.append(f"{label} must not be NaN")
        return False
    
    if math.isinf(value):
        errors.append(f"{label} must be finite")
        return False
    
    if value < 0:
        errors.append(f"{label} must be non‑negative (got {value})")
        return False
    
    if value == 0 and not allow_zero:
        errors.append(f"{label} must be greater than zero")
        return False
    
    return True


def validate_michaelis_menten_params(km: float, vmax: float,
                                     s0: float) -> ParameterValidation:
    """Check a Michaelis-Menten parameter set.

    Km and Vmax must be strictly positive (Km = 0 makes the rate law
    degenerate; Vmax = 0 gives a model that provably cannot turn over).
    Initial substrate may legitimately be zero.
    """
    errors: List[str] = []

    _finite_positive(km, "Km", errors, allow_zero=False)
    _finite_positive(vmax, "Vmax", errors, allow_zero=False)
    _finite_positive(s0, "S0", errors, allow_zero=True)

    if errors:
        return ParameterValidation(ok=False, errors=errors)

    v = ParameterValidation()

    if km < KM_PLAUSIBLE_MIN_MM:
        v.flagged = True
        v.flag_reason = (
            f"Km {km:g} mM is below the plausible lower bound "
            f"{KM_PLAUSIBLE_MIN_MM:g} mM"
        )
    elif km > KM_PLAUSIBLE_MAX_MM:
        v.flagged = True
        v.flag_reason = (
            f"Km {km:g} mM is above the plausible upper bound "
            f"{KM_PLAUSIBLE_MAX_MM:g} mM"
        )
    return v


def validate_mm_competitive_params(km: float, vmax: float, ki: float,
                                   s0: float, i: float) -> ParameterValidation:
    """Check a competitive-inhibition Michaelis-Menten parameter set.

    Km, Vmax and Ki must be strictly positive (Ki = 0 makes the inhibition
    term divide by zero). Initial substrate and inhibitor concentration may
    legitimately be zero -- I = 0 must reduce exactly to plain MM.
    """
    errors: List[str] = []

    _finite_positive(km, "Km", errors, allow_zero=False)
    _finite_positive(vmax, "Vmax", errors, allow_zero=False)
    _finite_positive(ki, "Ki", errors, allow_zero=False)
    _finite_positive(s0, "S0", errors, allow_zero=True)
    _finite_positive(i, "I", errors, allow_zero=True)

    if errors:
        return ParameterValidation(ok=False, errors=errors)

    v = ParameterValidation()

    # Reuse the Km plausibility bounds -- Ki has no dedicated bounds in this
    # project yet (BRENDA Ki reporting is being wired up separately); Km is
    # flagged the same way plain MM flags it, since it carries the same
    # physical meaning here.
    if km < KM_PLAUSIBLE_MIN_MM:
        v.flagged = True
        v.flag_reason = (
            f"Km {km:g} mM is below the plausible lower bound "
            f"{KM_PLAUSIBLE_MIN_MM:g} mM"
        )
    elif km > KM_PLAUSIBLE_MAX_MM:
        v.flagged = True
        v.flag_reason = (
            f"Km {km:g} mM is above the plausible upper bound "
            f"{KM_PLAUSIBLE_MAX_MM:g} mM"
        )
    return v


def vmax_from_kcat(
    kcat: float, enzyme_conc: float, km: float | None = None
) -> tuple[float, ParameterValidation]:
    """Convert a turnover number into a Vmax: ``Vmax = kcat * [E]0``.

    This is what makes a literature-resolved kcat simulable. kcat is a
    property of one enzyme molecule (s^-1); Vmax is a property of an assay
    containing some amount of enzyme (mM/s). The bridge between them is the
    total enzyme concentration, and nothing can supply it but the caller --
    BRENDA does not report it per row. See ADR 0012 and ADR 0013.

    Units: ``kcat`` in s^-1, ``enzyme_conc`` in mM, returned Vmax in mM/s,
    matching the mM convention Km already uses.

    Returns ``(vmax, validation)``. The validation is not decoration:

    - Non-finite or non-positive inputs are **rejected** (``ok=False``).
      A zero enzyme concentration gives Vmax = 0, which
      ``validate_michaelis_menten_params`` already rejects as a model that
      provably cannot turn over -- catching it here names the real cause.
    - ``[E]0`` above ``ENZYME_CONC_MM_RATIO_FLAG_ABOVE * Km`` is **flagged**,
      not rejected. The Michaelis-Menten rate law assumes [E]0 << Km; past
      that the ES complex sequesters a non-negligible share of substrate and
      the curve is quantitatively wrong (the tight-binding/Morrison regime,
      which this engine does not implement). The simulation still runs and
      still teaches something -- the student is simply told the
      approximation is being stretched.

    ``km`` is optional because the ratio check is only possible when a Km is
    known; the conversion itself does not need it.
    """
    errors: List[str] = []

    _finite_positive(kcat, "kcat", errors, allow_zero=False)
    _finite_positive(enzyme_conc, "enzyme_conc", errors, allow_zero=False)

    if errors:
        return 0.0, ParameterValidation(ok=False, errors=errors)

    vmax = kcat * enzyme_conc

    if not math.isfinite(vmax):
        return 0.0, ParameterValidation(
            ok=False,
            errors=[
                f"kcat {kcat:g} 1/s x [E]0 {enzyme_conc:g} mM overflowed to a "
                "non-finite Vmax"
            ],
        )

    v = ParameterValidation()

    if km is not None and math.isfinite(km) and km > 0:
        ratio = enzyme_conc / km
        if ratio > ENZYME_CONC_MM_RATIO_FLAG_ABOVE:
            v.flagged = True
            v.flag_reason = (
                f"[E]0 {enzyme_conc:g} mM is {ratio:.3g}x Km ({km:g} mM); the "
                "Michaelis-Menten rate law assumes [E]0 << Km, so above "
                f"{ENZYME_CONC_MM_RATIO_FLAG_ABOVE:g}x Km the free-substrate "
                "approximation is being stretched and the curve understates "
                "how much substrate is bound in the ES complex"
            )

    return vmax, v


def validate_sir_params(beta: float, gamma: float, s0: float, i0: float,
                        r0_recovered: float = 0.0) -> ParameterValidation:
    """Check an SIR parameter set.

    An epidemic model with zero initial infected is valid but inert, so it is
    flagged rather than rejected -- a student may genuinely want to see that
    nothing happens.
    """
    errors: List[str] = []

    _finite_positive(beta, "beta", errors, allow_zero=False)
    _finite_positive(gamma, "gamma", errors, allow_zero=False)
    _finite_positive(s0, "S0", errors, allow_zero=True)
    _finite_positive(i0, "I0", errors, allow_zero=True)
    _finite_positive(r0_recovered, "R0_recovered", errors, allow_zero=True)

    if errors:
        return ParameterValidation(ok=False, errors=errors)

    v = ParameterValidation()

    if (s0 + i0 + r0_recovered) <= 0:
        v.ok = False
        v.errors.append("total population must be greater than zero")
        return v

    if i0 == 0:
        v.flagged = True
        v.flag_reason = "I0 is zero: no outbreak can occur"
        return v

    basic_reproduction = beta / gamma
    if basic_reproduction > R0_IMPLAUSIBLE_ABOVE:
        v.flagged = True
        v.flag_reason = (
            f"R0 = beta/gamma = {basic_reproduction:g} exceeds "
            f"{R0_IMPLAUSIBLE_ABOVE:g}, higher than any well-documented "
            "human pathogen"
        )
    return v


def validate_seir_params(beta: float, sigma: float, gamma: float, s0: float,
                          e0: float, i0: float,
                          r0_recovered: float = 0.0) -> ParameterValidation:
    """Check an SEIR parameter set (adds the latent-progression rate sigma)."""
    errors: List[str] = []

    _finite_positive(beta, "beta", errors, allow_zero=False)
    _finite_positive(sigma, "sigma", errors, allow_zero=False)
    _finite_positive(gamma, "gamma", errors, allow_zero=False)
    _finite_positive(s0, "S0", errors, allow_zero=True)
    _finite_positive(i0, "I0", errors, allow_zero=True)
    _finite_positive(e0, "E0", errors, allow_zero=True)
    _finite_positive(r0_recovered, "R0_recovered", errors, allow_zero=True)

    if errors:
        return ParameterValidation(ok=False, errors=errors)

    v = ParameterValidation()

    if (s0 + i0 + r0_recovered + e0) <= 0:
        v.ok = False
        v.errors.append("total population must be greater than zero")
        return v

    if i0 == 0 and e0 == 0:
        v.flagged = True
        v.flag_reason = "both E0 and I0 are zero: no outbreak can occur"
        return v

    base_sir = validate_sir_params(beta, gamma, s0, i0, r0_recovered)
    v.flagged = base_sir.flagged and not (base_sir.flag_reason or "").startswith("I0")
    v.flag_reason = v.flag_reason or (base_sir.flag_reason if v.flagged else None)
    if v.flagged and v.flag_reason is None:
        v.flag_reason = base_sir.flag_reason
    return v

def validate_pcr_params(n0: float, efficiency: float,
                        cycles: int) -> ParameterValidation:
    """Check a PCR amplification parameter set.

    n0 must be a positive template copy number. efficiency is the fraction of
    template successfully doubled each cycle: 1.0 is ideal (copies exactly
    double), 0.0 is no amplification at all. Above 1.0 is physically
    impossible -- rejected, not flagged. Below
    ``PCR_PLAUSIBLE_LOW_EFFICIENCY`` is a real but poor reaction -- flagged so
    a student modeling a failing PCR still gets a plot, with a visible
    warning attached.
    """
    errors: List[str] = []

    _finite_positive(n0, "n0", errors, allow_zero=False)

    if isinstance(efficiency, bool) or not isinstance(efficiency, (int, float)):
        errors.append(
            f"efficiency must be a number, got {type(efficiency).__name__}")
    elif math.isnan(efficiency) or math.isinf(efficiency):
        errors.append("efficiency must be finite")
    elif efficiency < PCR_MIN_EFFICIENCY or efficiency > PCR_MAX_EFFICIENCY:
        errors.append(
            f"efficiency must be between {PCR_MIN_EFFICIENCY} and "
            f"{PCR_MAX_EFFICIENCY} (got {efficiency}) -- a single amplicon "
            "cannot be copied more than once per cycle")

    if isinstance(cycles, (bool, np.bool_)) or not isinstance(cycles, (int, np.integer)):
        errors.append(f"cycles must be an integer, got {type(cycles).__name__}")
    elif cycles <= 0:
        errors.append("cycles must be a positive integer")
    elif cycles > 60:
        errors.append(
            f"cycles must be <= 60 (got {cycles}) -- real qPCR protocols "
            "never run this many cycles; the template would be exhausted "
            "or the reaction would have plateaued long before this point")

    if errors:
        return ParameterValidation(ok=False, errors=errors)

    if isinstance(efficiency, (int, float)) and efficiency < PCR_PLAUSIBLE_LOW_EFFICIENCY:
        return ParameterValidation(
            ok=True, flagged=True,
            flag_reason=(
                f"efficiency {efficiency} is below "
                f"{PCR_PLAUSIBLE_LOW_EFFICIENCY} -- amplification will be "
                "real but poor (degraded template, weak primers, or "
                "inhibitors are the usual causes)"),
        )

    return ParameterValidation()


def validate_ssa_params(a0: float, k: float, end: float) -> ParameterValidation:
    """Check a Gillespie SSA parameter set (first-order decay A -> B).

    a0 is the initial molecule count of A and must be a positive integer —
    the SSA operates on whole molecules. k is the first-order rate constant
    per molecule per time unit; zero is physically valid (no reaction) but
    negative is impossible. Above ``SSA_PLAUSIBLE_MAX_RATE`` the trajectory
    becomes a dense random walk far from the deterministic closed form —
    flagged, not rejected. Below ``SSA_PLAUSIBLE_MIN_POPULATION`` molecules
    the stochastic trajectory visibly deviates from ``a0 * exp(-k t)`` —
    flagged, not rejected.
    """
    errors: List[str] = []

    if isinstance(a0, (bool, np.bool_)):
        errors.append("a0 must be an integer molecule count, not a boolean")
    elif not isinstance(a0, (int, np.integer)):
        errors.append(
            f"a0 must be an integer molecule count, got {type(a0).__name__}")
    elif a0 < 1:
        errors.append(
            f"a0 must be at least 1 molecule (got {a0}) -- an SSA needs "
            "something to react")

    if isinstance(k, (bool, np.bool_)):
        errors.append("k must be a number, not a boolean")
    elif not isinstance(k, (int, float, np.integer, np.floating)):
        errors.append(f"k must be a number, got {type(k).__name__}")
    elif math.isnan(k) or math.isinf(k):
        errors.append("k must be finite")
    elif k < 0:
        errors.append(
            f"k must be >= 0 (got {k}) -- a rate constant cannot be negative")

    _finite_positive(end, "end", errors)

    if errors:
        return ParameterValidation(ok=False, errors=errors)

    reasons: List[str] = []
    if a0 < SSA_PLAUSIBLE_MIN_POPULATION:
        reasons.append(
            f"a0={a0} is below {SSA_PLAUSIBLE_MIN_POPULATION} molecules -- "
            "stochastic effects dominate below this size")
    if k > SSA_PLAUSIBLE_MAX_RATE:
        reasons.append(
            f"k={k} exceeds {SSA_PLAUSIBLE_MAX_RATE} per time unit -- the "
            "trajectory will be a dense random walk far from the closed form")
    if reasons:
        return ParameterValidation(ok=True, flagged=True, flag_reason=" ".join(reasons))

    return ParameterValidation()


def validate_ssa_bimolecular_params(
    a0: float, b0: float, k: float, end: float
) -> ParameterValidation:
    """Check a Gillespie SSA parameter set (bimolecular A + B -> C).

    a0 and b0 are initial molecule counts and must be positive integers —
    the SSA operates on whole molecules. k is the second-order rate
    constant per molecule pair per time unit; zero is physically valid
    (no reaction) but negative is impossible. Flags, not rejections:
    either species below ``SSA_PLAUSIBLE_MIN_POPULATION`` molecules makes
    the trajectory noise-dominated; k above
    ``SSA_BIMOLECULAR_PLAUSIBLE_MAX_RATE`` makes events so dense the
    trajectory diverges from the ODE reference.
    """
    errors: List[str] = []

    for label, value in (("a0", a0), ("b0", b0)):
        if isinstance(value, (bool, np.bool_)):
            errors.append(
                f"{label} must be an integer molecule count, not a boolean")
        elif not isinstance(value, (int, np.integer)):
            errors.append(
                f"{label} must be an integer molecule count, "
                f"got {type(value).__name__}")
        elif value < 1:
            errors.append(
                f"{label} must be at least 1 molecule (got {value}) -- "
                "an SSA needs something to react")

    if isinstance(k, (bool, np.bool_)):
        errors.append("k must be a number, not a boolean")
    elif not isinstance(k, (int, float, np.integer, np.floating)):
        errors.append(f"k must be a number, got {type(k).__name__}")
    elif math.isnan(k) or math.isinf(k):
        errors.append("k must be finite")
    elif k < 0:
        errors.append(
            f"k must be >= 0 (got {k}) -- a rate constant cannot be negative")

    _finite_positive(end, "end", errors)

    if errors:
        return ParameterValidation(ok=False, errors=errors)

    reasons: List[str] = []
    for label, value in (("a0", a0), ("b0", b0)):
        if value < SSA_PLAUSIBLE_MIN_POPULATION:
            reasons.append(
                f"{label}={value} is below {SSA_PLAUSIBLE_MIN_POPULATION} "
                "molecules -- stochastic effects dominate below this size")
    if k > SSA_BIMOLECULAR_PLAUSIBLE_MAX_RATE:
        reasons.append(
            f"k={k} exceeds {SSA_BIMOLECULAR_PLAUSIBLE_MAX_RATE} per "
            "molecule pair per time unit -- events will be dense, a random "
            "walk far from the ODE reference")
    if reasons:
        return ParameterValidation(ok=True, flagged=True, flag_reason=" ".join(reasons))

    return ParameterValidation()


def validate_ssa_replicates_params(n_replicates: int) -> ParameterValidation:
    """Check the replicate count for the SSA ensemble view.

    ``n_replicates`` must be a positive integer -- the ensemble mean and
    standard deviation are defined over a whole number of independent
    trajectories. Fewer than ``SSA_PLAUSIBLE_MIN_REPLICATES`` (10)
    replicates makes the sample mean too noisy to compare against the
    deterministic reference; flagged, not rejected (a student may
    deliberately be exploring single-seed noise).
    """
    errors: List[str] = []

    if isinstance(n_replicates, (bool, np.bool_)):
        errors.append(
            "n_replicates must be an integer count, not a boolean")
    elif not isinstance(n_replicates, (int, np.integer)):
        errors.append(
            f"n_replicates must be an integer count, "
            f"got {type(n_replicates).__name__}")
    elif n_replicates < 1:
        errors.append(
            f"n_replicates must be at least 1 (got {n_replicates}) -- "
            "an ensemble needs at least one trajectory")

    if errors:
        return ParameterValidation(ok=False, errors=errors)

    if n_replicates < SSA_PLAUSIBLE_MIN_REPLICATES:
        return ParameterValidation(
            ok=True,
            flagged=True,
            flag_reason=(
                f"n_replicates={n_replicates} is below "
                f"{SSA_PLAUSIBLE_MIN_REPLICATES} -- fewer replicates gives "
                "a noisy estimate of the mean and standard deviation"),
        )

    return ParameterValidation()

def validate_monte_carlo_params(n_samples: int) -> ParameterValidation:
    """Check Monte Carlo pi-estimation parameters.

    ``n_samples`` must be a positive integer. Fewer than
    ``MC_PLAUSIBLE_MIN_SAMPLES`` (100) is flagged as implausible — the
    standard error will be too large for a meaningful estimate — but the
    simulation is still valid and will run.
    """
    errors: List[str] = []

    if isinstance(n_samples, (bool, np.bool_)):
        errors.append("n_samples must be an integer, not a boolean")
    elif not isinstance(n_samples, (int, np.integer)):
        errors.append(
            f"n_samples must be an integer, got {type(n_samples).__name__}")
    elif n_samples <= 0:
        errors.append("n_samples must be a positive integer")

    if errors:
        return ParameterValidation(ok=False, errors=errors)

    if n_samples < MC_PLAUSIBLE_MIN_SAMPLES:
        return ParameterValidation(
            ok=True, flagged=True,
            flag_reason=(
                f"n_samples={n_samples} is below "
                f"{MC_PLAUSIBLE_MIN_SAMPLES}; the standard error will be "
                "too large for a meaningful estimate"),
        )

    return ParameterValidation()

def validate_wright_fisher_params(
    population_size: int,
    starting_frequency: float,
    generations: int,
    replicate_runs: int = 1,
    mutation_rate: float = 0.0,
    selection_coefficient: float = 0.0,
    dominance: float | None = None,
    population_size_series: Sequence[int] | None = None,
    n_demes: int = 1,
    migration_rate: float = 0.0,
    migration_model: str = "island",
) -> ParameterValidation:
    """Check a Wright-Fisher neutral-drift parameter set.

    Hard rejections (``ok=False``):
        * ``population_size`` is boolean, not an integer, or < 1
        * ``starting_frequency`` is boolean, not a finite float, or outside [0, 1]
        * ``generations`` is boolean, not an integer, or < 1
        * ``replicate_runs`` is boolean, not an integer, or < 1
        * ``mutation_rate`` is boolean, NaN, infinite, < 0, or > 1
        * ``selection_coefficient`` is boolean, NaN, infinite, or <= -1
        * ``dominance`` is not None and not in [0, 2]
        * ``population_size_series`` elements are not positive integers, or
          its length does not match ``generations + 1``
        * ``n_demes`` is boolean, not an integer, or < 1
        * ``migration_rate`` is boolean, NaN, infinite, or outside [0, 1]
        * ``migration_model`` is not "island" or "stepping-stone"
        * ``migration_model="stepping-stone"`` with ``n_demes < 3``
          (a ring of fewer than 3 demes is degenerate)

    Flags (``ok=True, flagged=True``):
        * ``population_size < WF_PLAUSIBLE_MIN_POPULATION_SIZE`` — drift
          extremely rapid, valid but unlikely to be intended
        * ``starting_frequency`` exactly 0.0 or 1.0 — allele already
          lost or fixed, valid but degenerate
        * ``generations > WF_PLAUSIBLE_MAX_GENERATIONS`` — valid, may be slow
        * ``replicate_runs < WF_PLAUSIBLE_MIN_REPLICATE_RUNS`` — standard
          error of mean heterozygosity will be large
        * ``mutation_rate > WF_PLAUSIBLE_MAX_MUTATION_RATE`` — biologically
          implausible, mutation will dominate drift
        * ``|selection_coefficient| > WF_PLAUSIBLE_MAX_SELECTION_COEFFICIENT``
          — implausibly strong selection for most teaching scenarios
        * Any value in ``population_size_series`` below
          ``WF_PLAUSIBLE_MIN_POPULATION_SIZE`` — flagged (same as constant N)
        * ``migration_rate > WF_PLAUSIBLE_MAX_MUTATION_RATE`` — flagged
          (strong migration homogenises demes rapidly)
        * ``dominance > 1`` — overdominance (h > 1 with s > 0) or
          underdominance (h > 1 with s < 0); valid, but the heterozygote
          fitness is no longer intermediate between the homozygotes
    """
    errors: List[str] = []

    # --- population_size ---
    if isinstance(population_size, (bool, np.bool_)):
        errors.append("population_size must be an integer, not a boolean")
    elif not isinstance(population_size, (int, np.integer)):
        errors.append(
            f"population_size must be an integer, got "
            f"{type(population_size).__name__}")
    elif population_size < 1:
        errors.append(
            f"population_size must be >= 1 (got {population_size})")

    # --- starting_frequency ---
    if isinstance(starting_frequency, (bool, np.bool_)):
        errors.append("starting_frequency must be a number, not a boolean")
    elif not isinstance(starting_frequency, (int, float)):
        errors.append(
            f"starting_frequency must be a number, got "
            f"{type(starting_frequency).__name__}")
    elif math.isnan(starting_frequency):
        errors.append("starting_frequency must not be NaN")
    elif math.isinf(starting_frequency):
        errors.append("starting_frequency must be finite")
    elif not (0.0 <= starting_frequency <= 1.0):
        errors.append(
            f"starting_frequency must be in [0, 1] (got {starting_frequency})")

    # --- generations ---
    if isinstance(generations, (bool, np.bool_)):
        errors.append("generations must be an integer, not a boolean")
    elif not isinstance(generations, (int, np.integer)):
        errors.append(
            f"generations must be an integer, got "
            f"{type(generations).__name__}")
    elif generations < 1:
        errors.append(f"generations must be >= 1 (got {generations})")

    # --- replicate_runs ---
    if isinstance(replicate_runs, (bool, np.bool_)):
        errors.append("replicate_runs must be an integer, not a boolean")
    elif not isinstance(replicate_runs, (int, np.integer)):
        errors.append(
            f"replicate_runs must be an integer, got "
            f"{type(replicate_runs).__name__}")
    elif replicate_runs < 1:
        errors.append(
            f"replicate_runs must be >= 1 (got {replicate_runs})")

    # --- mutation_rate ---
    if isinstance(mutation_rate, (bool, np.bool_)):
        errors.append("mutation_rate must be a number, not a boolean")
    elif not isinstance(mutation_rate, (int, float, np.integer, np.floating)):
        errors.append(
            f"mutation_rate must be a number, got "
            f"{type(mutation_rate).__name__}")
    elif math.isnan(mutation_rate):
        errors.append("mutation_rate must not be NaN")
    elif math.isinf(mutation_rate):
        errors.append("mutation_rate must be finite")
    elif mutation_rate < 0.0:
        errors.append(
            f"mutation_rate must be >= 0 (got {mutation_rate})")
    elif mutation_rate > 1.0:
        errors.append(
            f"mutation_rate must be <= 1 (got {mutation_rate})")

    # --- selection_coefficient ---
    if isinstance(selection_coefficient, (bool, np.bool_)):
        errors.append("selection_coefficient must be a number, not a boolean")
    elif not isinstance(selection_coefficient, (int, float, np.integer, np.floating)):
        errors.append(
            f"selection_coefficient must be a number, got "
            f"{type(selection_coefficient).__name__}")
    elif math.isnan(selection_coefficient):
        errors.append("selection_coefficient must not be NaN")
    elif math.isinf(selection_coefficient):
        errors.append("selection_coefficient must be finite")
    elif selection_coefficient <= -1.0:
        errors.append(
            f"selection_coefficient must be > -1 (got "
            f"{selection_coefficient})")

    # --- dominance ---
    if dominance is not None:
        if isinstance(dominance, (bool, np.bool_)):
            errors.append("dominance must be a number, not a boolean")
        elif not isinstance(dominance, (int, float, np.integer, np.floating)):
            errors.append(
                f"dominance must be a number, got "
                f"{type(dominance).__name__}")
        elif math.isnan(dominance):
            errors.append("dominance must not be NaN")
        elif math.isinf(dominance):
            errors.append("dominance must be finite")
        elif not (0.0 <= dominance <= 2.0):
            errors.append(
                f"dominance must be in [0, 2] (got {dominance})")

    # --- n_demes ---
    if isinstance(n_demes, (bool, np.bool_)):
        errors.append("n_demes must be an integer, not a boolean")
    elif not isinstance(n_demes, (int, np.integer)):
        errors.append(
            f"n_demes must be an integer, got {type(n_demes).__name__}")
    elif n_demes < 1:
        errors.append(f"n_demes must be >= 1 (got {n_demes})")

    # --- migration_rate ---
    if isinstance(migration_rate, (bool, np.bool_)):
        errors.append("migration_rate must be a number, not a boolean")
    elif not isinstance(migration_rate, (int, float, np.integer, np.floating)):
        errors.append(
            f"migration_rate must be a number, got "
            f"{type(migration_rate).__name__}")
    elif math.isnan(migration_rate):
        errors.append("migration_rate must not be NaN")
    elif math.isinf(migration_rate):
        errors.append("migration_rate must be finite")
    elif migration_rate < 0.0 or migration_rate > 1.0:
        errors.append(
            f"migration_rate must be in [0, 1] (got {migration_rate})")

    # --- migration_model ---
    if not isinstance(migration_model, str):
        errors.append(
            f"migration_model must be a string, got "
            f"{type(migration_model).__name__}")
    elif migration_model not in ("island", "stepping-stone"):
        errors.append(
            f"migration_model must be 'island' or 'stepping-stone' "
            f"(got {migration_model!r})")
    elif migration_model == "stepping-stone" and (
            isinstance(n_demes, (int, float, np.integer, np.floating))
            and n_demes < 3):
        errors.append(
            "migration_model='stepping-stone' requires n_demes >= 3 "
            "(a ring of fewer than 3 demes is degenerate)")

    # --- population_size_series ---
    if population_size_series is not None:
        if not isinstance(population_size_series, (list, tuple, np.ndarray)):
            errors.append(
                f"population_size_series must be a list or tuple, got "
                f"{type(population_size_series).__name__}")
        else:
            series_list = list(population_size_series)
            if len(series_list) != generations + 1:
                errors.append(
                    f"population_size_series length ({len(series_list)}) "
                    f"must equal generations+1 ({generations + 1})")
            for i, val in enumerate(series_list):
                if isinstance(val, (bool, np.bool_)):
                    errors.append(
                        f"population_size_series[{i}] must be an integer, "
                        f"not a boolean")
                elif not isinstance(val, (int, np.integer)):
                    errors.append(
                        f"population_size_series[{i}] must be an integer, "
                        f"got {type(val).__name__}")
                elif val < 1:
                    errors.append(
                        f"population_size_series[{i}] must be >= 1 "
                        f"(got {val})")

    if errors:
        return ParameterValidation(ok=False, errors=errors)

    v = ParameterValidation()
    flag_reasons: List[str] = []

    if population_size_series is None:
        if population_size < WF_PLAUSIBLE_MIN_POPULATION_SIZE:
            v.flagged = True
            flag_reasons.append(
                f"population_size={population_size} is below "
                f"{WF_PLAUSIBLE_MIN_POPULATION_SIZE}; drift will be "
                "extremely rapid")
    else:
        min_n = min(population_size_series)
        if min_n < WF_PLAUSIBLE_MIN_POPULATION_SIZE:
            v.flagged = True
            flag_reasons.append(
                f"population_size_series minimum ({min_n}) is below "
                f"{WF_PLAUSIBLE_MIN_POPULATION_SIZE}; some generations "
                "will have extremely rapid drift")
    if starting_frequency == 0.0:
        v.flagged = True
        flag_reasons.append(
            "starting_frequency is 0.0; the allele is already lost "
            "and no drift can occur")
    if starting_frequency == 1.0:
        v.flagged = True
        flag_reasons.append(
            "starting_frequency is 1.0; the allele is already fixed "
            "and no drift can occur")
    if generations > WF_PLAUSIBLE_MAX_GENERATIONS:
        v.flagged = True
        flag_reasons.append(
            f"generations={generations} exceeds "
            f"{WF_PLAUSIBLE_MAX_GENERATIONS}; simulation may be "
            "noticeably slow")
    if replicate_runs < WF_PLAUSIBLE_MIN_REPLICATE_RUNS:
        v.flagged = True
        flag_reasons.append(
            f"replicate_runs={replicate_runs} is below "
            f"{WF_PLAUSIBLE_MIN_REPLICATE_RUNS}; the standard error "
            "of mean heterozygosity will be large")
    if mutation_rate > WF_PLAUSIBLE_MAX_MUTATION_RATE:
        v.flagged = True
        flag_reasons.append(
            f"mutation_rate={mutation_rate} exceeds "
            f"{WF_PLAUSIBLE_MAX_MUTATION_RATE}; mutation will "
            "dominate drift")
    if abs(selection_coefficient) > WF_PLAUSIBLE_MAX_SELECTION_COEFFICIENT:
        v.flagged = True
        flag_reasons.append(
            f"|selection_coefficient|={abs(selection_coefficient)} "
            f"exceeds {WF_PLAUSIBLE_MAX_SELECTION_COEFFICIENT}; "
            "selection will dominate drift")
    if dominance is not None and dominance > 1.0:
        v.flagged = True
        flag_reasons.append(
            f"dominance={dominance} exceeds 1; heterozygote fitness is "
            "not intermediate between the homozygotes "
            "(overdominance if s > 0, underdominance if s < 0)")
    if migration_rate > WF_PLAUSIBLE_MAX_MUTATION_RATE:
        v.flagged = True
        flag_reasons.append(
            f"migration_rate={migration_rate} exceeds "
            f"{WF_PLAUSIBLE_MAX_MUTATION_RATE}; migration will "
            "homogenise demes rapidly")

    if flag_reasons:
        v.flag_reason = "; ".join(flag_reasons)
    return v

def validate_md_params(
    n_particles: int,
    temperature: float,
    timestep: float,
    n_steps: int,
    density: float = 0.85,
) -> ParameterValidation:
    """Check molecular dynamics parameter set.

    Hard rejections (``ok=False``):
        * ``n_particles`` is boolean, not an integer, or < 2
        * ``temperature`` is boolean, not a finite float, or <= 0
        * ``timestep`` is boolean, not a finite float, or <= 0
        * ``n_steps`` is boolean, not an integer, or < 1
        * ``density`` is boolean, not a finite float, or <= 0

    Flags (``ok=True, flagged=True``):
        * ``timestep > MD_PLAUSIBLE_MAX_TIMESTEP`` — energy conservation risk
        * ``initialization temperature`` outside ``[MD_PLAUSIBLE_TEMPERATURE_LOW,
          MD_PLAUSIBLE_TEMPERATURE_HIGH]`` — frozen or evaporating cluster
        * ``n_particles`` not an exact fcc count — rounded up; actual_n differs
        * ``n_particles < MD_PLAUSIBLE_MIN_PARTICLES`` — too small for
          meaningful cluster dynamics
    """
    errors: List[str] = []

    # --- n_particles ---
    if isinstance(n_particles, (bool, np.bool_)):
        errors.append("n_particles must be an integer, not a boolean")
    elif not isinstance(n_particles, (int, np.integer)):
        errors.append(
            f"n_particles must be an integer, got "
            f"{type(n_particles).__name__}")
    elif n_particles < 2:
        errors.append(
            f"n_particles must be >= 2 (need at least a pair for a force; "
            f"got {n_particles})")

    # --- temperature ---
    _finite_positive(temperature, "temperature", errors,
                     allow_zero=False)

    # --- timestep ---
    _finite_positive(timestep, "timestep", errors,
                     allow_zero=False)

    # --- n_steps ---
    if isinstance(n_steps, (bool, np.bool_)):
        errors.append("n_steps must be an integer, not a boolean")
    elif not isinstance(n_steps, (int, np.integer)):
        errors.append(
            f"n_steps must be an integer, got {type(n_steps).__name__}")
    elif n_steps < 1:
        errors.append(
            f"n_steps must be >= 1 (got {n_steps})")

    # --- density ---
    _finite_positive(density, "density", errors,
                     allow_zero=False)

    if errors:
        return ParameterValidation(ok=False, errors=errors)

    # --- Flags (ok=True; ALL applicable flags accumulate, matching the
    # corrected WF-validator pattern — flags must not be mutually exclusive) ---
    v = ParameterValidation()
    flag_reasons: List[str] = []

    # fcc rounding
    k = int(math.ceil((n_particles / 4.0) ** (1.0 / 3.0)))
    k = max(k, 1)
    actual_n = 4 * k ** 3
    if actual_n != n_particles:
        v.flagged = True
        flag_reasons.append(
            f"n_particles={n_particles} is not an exact fcc count; "
            f"rounded up to {actual_n}")

    if timestep > MD_PLAUSIBLE_MAX_TIMESTEP:
        v.flagged = True
        flag_reasons.append(
            f"timestep {timestep} > {MD_PLAUSIBLE_MAX_TIMESTEP}: "
            "energy conservation at risk — the r^{-12} repulsive wall "
            "is under-resolved")

    if (temperature < MD_PLAUSIBLE_TEMPERATURE_LOW
            or temperature > MD_PLAUSIBLE_TEMPERATURE_HIGH):
        v.flagged = True
        flag_reasons.append(
            f"initialization temperature {temperature} is outside "
            f"[{MD_PLAUSIBLE_TEMPERATURE_LOW}, "
            f"{MD_PLAUSIBLE_TEMPERATURE_HIGH}]: "
            f"{'cluster is effectively frozen' if temperature < MD_PLAUSIBLE_TEMPERATURE_LOW else 'cluster will evaporate within the run — initialization temperatures above this lose particles'}")

    if n_particles < MD_PLAUSIBLE_MIN_PARTICLES:
        v.flagged = True
        flag_reasons.append(
            f"n_particles={n_particles} < {MD_PLAUSIBLE_MIN_PARTICLES}: "
            "too small for meaningful cluster dynamics")

    if flag_reasons:
        v.flag_reason = "; ".join(flag_reasons)

    return v
