"""Monte Carlo pi estimation (stochastic, ADR 0005 RNG convention)."""

from __future__ import annotations


def _package_path_missing(exc: ModuleNotFoundError) -> bool:
    """See Terium/core/import_mode.py. Inlined deliberately: this
    guards the import machinery itself, so it cannot import a
    helper to do its job."""
    name = getattr(exc, "name", None)
    return bool(name) and (name == "Terium" or name.startswith("Terium."))


from typing import List

import numpy as np
try:
    from Terium.core.data_structures import (SimulationResult)
except ModuleNotFoundError as _exc:  # flat mode: Terium/ on sys.path, no repo root
    if not _package_path_missing(_exc):
        # A missing THIRD-PARTY dependency. Flat mode cannot fix it,
        # and retrying replaces the real reason with a confusing
        # 'No module named core'. See Terium/core/import_mode.py.
        raise
    from core.data_structures import (SimulationResult)  # type: ignore[no-redef]

try:
    from Terium.core.validation import validate_monte_carlo_params
except ModuleNotFoundError as _exc:
    if not _package_path_missing(_exc):
        # A missing THIRD-PARTY dependency. Flat mode cannot fix it,
        # and retrying replaces the real reason with a confusing
        # 'No module named core'. See Terium/core/import_mode.py.
        raise
    from core.validation import validate_monte_carlo_params  # type: ignore[no-redef]

def simulate_monte_carlo_pi(
    n_samples: int,
    seed: int | None = None,
) -> SimulationResult:
    """Estimate pi via Monte Carlo sampling with a reported standard error.

    Draw ``n_samples`` points uniformly in [-1, 1] x [-1, 1] and compute
    pi_estimate = 4 * (fraction landing inside the unit circle).
    The standard error is 4 * sqrt(p_hat * (1 - p_hat) / N)
    where p_hat is the sample proportion inside the circle.

    The result includes convergence-checkpoint rows (log-spaced sample counts
    with running estimate and standard error) so callers can plot how the
    estimate stabilizes as samples accumulate.

    Args:
        n_samples: number of random points to draw (must be >= 1)
        seed: optional seed for reproducibility; passed to
            ``numpy.random.default_rng``

    Returns:
        SimulationResult with columns ``["n", "estimate", "se"]``, one row
        per convergence checkpoint. The final row contains the full-sample
        estimate and standard error.

    Raises:
        ModelBuildError: if ``n_samples`` is invalid
    """
    validation = validate_monte_carlo_params(n_samples)
    validation.raise_if_invalid()

    rng = np.random.default_rng(seed)

    # Sample points uniformly in [-1, 1] x [-1, 1]
    xs = rng.uniform(-1.0, 1.0, size=n_samples)
    ys = rng.uniform(-1.0, 1.0, size=n_samples)

    # Indicator: 1.0 if (x, y) falls inside the unit circle, 0.0 otherwise
    inside = (xs ** 2 + ys ** 2) <= 1.0

    # Running estimate of pi at each sample index
    cumulative_n = np.arange(1, n_samples + 1, dtype=np.float64)
    cumulative_p_hat = np.cumsum(inside, dtype=np.float64) / cumulative_n
    cumulative_estimate = 4.0 * cumulative_p_hat

    # Running standard error: SE = 4 * sqrt(p_hat * (1 - p_hat) / n)
    cumulative_se = 4.0 * np.sqrt(
        cumulative_p_hat * (1.0 - cumulative_p_hat) / cumulative_n
    )

    # Build convergence checkpoints: log-spaced integers plus explicit
    # milestones so the first few data points are always visible.
    milestones: set[int] = {1, 2, 5, 10, 20, 50, 100, 200, 500,
                            1_000, 2_000, 5_000, 10_000, 20_000, 50_000,
                            100_000, 200_000, 500_000, 1_000_000}
    milestones = {m for m in milestones if m <= n_samples}
    milestones.add(n_samples)

    if n_samples > 1:
        log_points = np.geomspace(1, n_samples,
                                  num=min(150, n_samples),
                                  dtype=int)
        milestones.update(int(p) for p in log_points)

    checkpoints = sorted(milestones)

    # Build data rows
    data: List[List[float]] = []
    for n in checkpoints:
        idx = n - 1  # 0-based
        data.append([
            float(n),
            float(cumulative_estimate[idx]),
            float(cumulative_se[idx]),
        ])

    return SimulationResult(
        colnames=["n", "estimate", "se"],
        data=data,
        model_name="monte_carlo_pi",
        validation=validation,
    )
