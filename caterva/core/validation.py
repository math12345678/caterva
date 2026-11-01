"""Parameter validation for every domain. Shared contract: ok/flagged/flag_reason."""

from __future__ import annotations


def _package_path_missing(exc: ModuleNotFoundError) -> bool:
    """See caterva/core/import_mode.py. Inlined deliberately: this
    guards the import machinery itself, so it cannot import a
    helper to do its job."""
    name = getattr(exc, "name", None)
    return bool(name) and (name == "caterva" or name.startswith("caterva."))


import math
from typing import Any, List, Sequence

import numpy as np
try:
    from caterva.core.data_structures import (ParameterValidation, KM_PLAUSIBLE_MIN_MM, KM_PLAUSIBLE_MAX_MM, R0_IMPLAUSIBLE_ABOVE, PCR_MIN_EFFICIENCY, PCR_MAX_EFFICIENCY, PCR_PLAUSIBLE_LOW_EFFICIENCY, MC_PLAUSIBLE_MIN_SAMPLES, WF_PLAUSIBLE_MIN_POPULATION_SIZE, WF_PLAUSIBLE_MAX_GENERATIONS, WF_PLAUSIBLE_MIN_REPLICATE_RUNS, WF_PLAUSIBLE_MAX_MUTATION_RATE, WF_PLAUSIBLE_MAX_SELECTION_COEFFICIENT, MD_PLAUSIBLE_MIN_PARTICLES, MD_PLAUSIBLE_MAX_TIMESTEP, MD_PLAUSIBLE_TEMPERATURE_LOW, MD_PLAUSIBLE_TEMPERATURE_HIGH, SSA_PLAUSIBLE_MIN_POPULATION, SSA_PLAUSIBLE_MAX_RATE, SSA_BIMOLECULAR_PLAUSIBLE_MAX_RATE, SSA_PLAUSIBLE_MIN_REPLICATES, ENZYME_CONC_MM_RATIO_FLAG_ABOVE, LV_PLAUSIBLE_MIN_RATE, LV_PLAUSIBLE_MAX_RATE, LV_EXCURSION_RATIO_FLAG_ABOVE)
except ModuleNotFoundError as _exc:  # flat mode: caterva/ on sys.path, no repo root
    if not _package_path_missing(_exc):
        # A missing THIRD-PARTY dependency. Flat mode cannot fix it,
        # and retrying replaces the real reason with a confusing
        # 'No module named core'. See caterva/core/import_mode.py.
        raise
    from core.data_structures import (ParameterValidation, KM_PLAUSIBLE_MIN_MM, KM_PLAUSIBLE_MAX_MM, R0_IMPLAUSIBLE_ABOVE, PCR_MIN_EFFICIENCY, PCR_MAX_EFFICIENCY, PCR_PLAUSIBLE_LOW_EFFICIENCY, MC_PLAUSIBLE_MIN_SAMPLES, WF_PLAUSIBLE_MIN_POPULATION_SIZE, WF_PLAUSIBLE_MAX_GENERATIONS, WF_PLAUSIBLE_MIN_REPLICATE_RUNS, WF_PLAUSIBLE_MAX_MUTATION_RATE, WF_PLAUSIBLE_MAX_SELECTION_COEFFICIENT, MD_PLAUSIBLE_MIN_PARTICLES, MD_PLAUSIBLE_MAX_TIMESTEP, MD_PLAUSIBLE_TEMPERATURE_LOW, MD_PLAUSIBLE_TEMPERATURE_HIGH, SSA_PLAUSIBLE_MIN_POPULATION, SSA_PLAUSIBLE_MAX_RATE, SSA_BIMOLECULAR_PLAUSIBLE_MAX_RATE, SSA_PLAUSIBLE_MIN_REPLICATES, ENZYME_CONC_MM_RATIO_FLAG_ABOVE, LV_PLAUSIBLE_MIN_RATE, LV_PLAUSIBLE_MAX_RATE, LV_EXCURSION_RATIO_FLAG_ABOVE)  # type: ignore[no-redef]

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
                (f"kcat {kcat:g} 1/s x [E]0 {enzyme_conc:g} mM overflowed to a "
                 "non-finite Vmax")
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


