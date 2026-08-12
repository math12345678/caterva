"""Lennard-Jones molecular dynamics (velocity Verlet, ADR 0006)."""

from __future__ import annotations

import math
from typing import List, Tuple

import numpy as np
try:
    from Terium.core.data_structures import (ModelBuildError, SimulationResult)
except ModuleNotFoundError:  # flat mode: Terium/ on sys.path, no repo root
    from core.data_structures import (ModelBuildError, SimulationResult)  # type: ignore[no-redef]

try:
    from Terium.core.validation import validate_md_params
except ModuleNotFoundError:
    from core.validation import validate_md_params  # type: ignore[no-redef]

# Reduced units throughout: epsilon = sigma = mass = 1.
# ---------------------------------------------------------------------------


def lennard_jones_force(
    r_vec: np.ndarray,
) -> np.ndarray:
    """Lennard-Jones force vector on particle i from particle j.

    Args:
        r_vec: separation vector ``r_i - r_j``, shape ``(3,)``.

    Returns:
        force vector on particle i, shape ``(3,)``. The force on particle j
        is the negative of this vector (Newton's third law).

    With reduced units (:math:`\\varepsilon = \\sigma = 1`):

    .. math::

        \\mathbf{F}_{ij} = 24 \\left(
            \\frac{2}{r^{14}} - \\frac{1}{r^8}
        \\right) \\mathbf{r}_{ij}
    """
    r_sq = float(np.dot(r_vec, r_vec))
    if r_sq == 0.0:
        return np.zeros(3, dtype=np.float64)
    r2_inv = 1.0 / r_sq
    r6_inv = r2_inv ** 3
    r8_inv = r6_inv * r2_inv
    r14_inv = r8_inv * r6_inv
    magnitude = 24.0 * (2.0 * r14_inv - r8_inv)
    return magnitude * r_vec


def _fcc_lattice_positions(
    n_particles: int,
    density: float,
) -> Tuple[np.ndarray, int]:
    """Place particles on an fcc lattice and centre the cluster at the origin.

    The conventional fcc cell holds 4 particles. The number of cells per side
    ``k`` is chosen so ``4 * k**3 >= n_particles``. All ``4 * k**3``
    positions are returned (the count is rounded *up*, never truncated —
    per the spec, the simulation runs with the rounded-up count).

    Args:
        n_particles: requested particle count (may be rounded up).
        density: number density :math:`\\rho = N / V` in reduced units.

    Returns:
        ``(positions, actual_n)`` where ``positions`` has shape
        ``(actual_n, 3)`` and ``actual_n`` is the fcc-compatible count.
    """
    # Number of unit cells per dimension
    k = int(math.ceil((n_particles / 4.0) ** (1.0 / 3.0)))
    k = max(k, 1)
    actual_n = 4 * k ** 3

    # Lattice constant from density: rho = 4 / a^3  =>  a = (4 / rho)^{1/3}
    a = (4.0 / density) ** (1.0 / 3.0)

    # fcc conventional-cell basis (fractional coordinates)
    basis = np.array([
        [0.0, 0.0, 0.0],
        [0.5, 0.5, 0.0],
        [0.5, 0.0, 0.5],
        [0.0, 0.5, 0.5],
    ], dtype=np.float64)

    positions = np.empty((actual_n, 3), dtype=np.float64)
    idx = 0
    for ix in range(k):
        for iy in range(k):
            for iz in range(k):
                cell_origin = a * np.array([ix, iy, iz], dtype=np.float64)
                for b in basis:
                    positions[idx] = cell_origin + a * b
                    idx += 1

    # Centre at origin
    centroid = positions.mean(axis=0)
    positions -= centroid

    return positions, actual_n


# Mackay icosahedron shell vertices (cyclic permutations of (0, +/-1, +/-phi))
# with phi = (1+sqrt(5))/2.  Shared between _golden_section_lj13_scale and
# lj_cluster_positions to avoid duplication.
_ICOSAHEDRON_SHELL = np.array([
    [0.0, 1.0, (1.0 + math.sqrt(5.0)) / 2.0],
    [0.0, 1.0, -(1.0 + math.sqrt(5.0)) / 2.0],
    [0.0, -1.0, (1.0 + math.sqrt(5.0)) / 2.0],
    [0.0, -1.0, -(1.0 + math.sqrt(5.0)) / 2.0],
    [1.0, (1.0 + math.sqrt(5.0)) / 2.0, 0.0],
    [1.0, -(1.0 + math.sqrt(5.0)) / 2.0, 0.0],
    [-1.0, (1.0 + math.sqrt(5.0)) / 2.0, 0.0],
    [-1.0, -(1.0 + math.sqrt(5.0)) / 2.0, 0.0],
    [(1.0 + math.sqrt(5.0)) / 2.0, 0.0, 1.0],
    [(1.0 + math.sqrt(5.0)) / 2.0, 0.0, -1.0],
    [-(1.0 + math.sqrt(5.0)) / 2.0, 0.0, 1.0],
    [-(1.0 + math.sqrt(5.0)) / 2.0, 0.0, -1.0],
], dtype=np.float64)

def _golden_section_lj13_scale() -> float:
    """One-dimensional golden-section search for the Mackay icosahedron
    scale factor that minimises total LJ potential energy.

    Bracket [0.40, 0.80], ~200 iterations, fully deterministic.
    No scipy/no general-purpose optimizer — the search is hand-written
    so the engine stays numpy-only at runtime.
    """
    phi = (1.0 + math.sqrt(5.0)) / 2.0  # golden ratio (~1.618)
    inv_phi = phi - 1.0  # ~0.618

    lo, hi = 0.40, 0.80
    mid1 = hi - inv_phi * (hi - lo)
    mid2 = lo + inv_phi * (hi - lo)

    def _lj_total(scale: float) -> float:
        pos = np.vstack((np.zeros((1, 3), dtype=np.float64),
                         scale * _ICOSAHEDRON_SHELL))
        return _compute_lj_potential(pos, 13)

    e1 = _lj_total(mid1)
    e2 = _lj_total(mid2)

    for _ in range(200):
        if e1 < e2:
            hi = mid2
            mid2 = mid1
            e2 = e1
            mid1 = hi - inv_phi * (hi - lo)
            e1 = _lj_total(mid1)
        else:
            lo = mid1
            mid1 = mid2
            e1 = e2
            mid2 = lo + inv_phi * (hi - lo)
            e2 = _lj_total(mid2)
        if hi - lo < 1e-12:
            break

    return (lo + hi) / 2.0


def lj_cluster_positions(n_particles: int) -> np.ndarray:
    """Known global-minimum geometry for small Lennard-Jones clusters,
    shape ``(n_particles, 3)``.

    Supports exactly ``n`` in ``{2, 3, 4, 13}``. Reduced units
    (``epsilon = sigma = 1``). Verified constant: ``r_min = 2^(1/6)``.

    * ``n=2`` — two particles separated by ``r_min`` along x.
    * ``n=3`` — equilateral triangle, side ``r_min``.
    * ``n=4`` — regular tetrahedron, edge ``r_min``.
    * ``n=13`` — centered Mackay icosahedron. The scale factor is
      determined by golden-section search over the LJ potential — the
      twelve shell vertices compress inward from their geometric
      positions to minimise total energy.

    Raises ``ModelBuildError`` for any other ``n_particles``.
    """
    r_min = 2.0 ** (1.0 / 6.0)  # LJ equilibrium separation

    if n_particles == 2:
        return np.array([
            [-r_min / 2.0, 0.0, 0.0],
            [r_min / 2.0, 0.0, 0.0],
        ], dtype=np.float64)

    if n_particles == 3:
        h = r_min * math.sqrt(3.0) / 2.0
        return np.array([
            [0.0, 0.0, 0.0],
            [r_min, 0.0, 0.0],
            [r_min / 2.0, h, 0.0],
        ], dtype=np.float64)

    if n_particles == 4:
        # Vertices (1,1,1),(1,-1,-1),(-1,1,-1),(-1,-1,1) scaled to edge r_min.
        # Native edge is 2*sqrt(2).
        scale = r_min / (2.0 * math.sqrt(2.0))
        v = np.array([
            [1.0, 1.0, 1.0],
            [1.0, -1.0, -1.0],
            [-1.0, 1.0, -1.0],
            [-1.0, -1.0, 1.0],
        ], dtype=np.float64)
        return scale * v

    if n_particles == 13:
        scale = _golden_section_lj13_scale()
        return np.vstack((
            np.zeros((1, 3), dtype=np.float64),
            scale * _ICOSAHEDRON_SHELL,
        ))

    raise ModelBuildError(
        f"lj_cluster_positions supports n in {{2, 3, 4, 13}}, "
        f"got {n_particles}")


def simulate_molecular_dynamics(
    n_particles: int,
    temperature: float,
    timestep: float,
    n_steps: int,
    density: float = 0.85,
    seed: int | None = None,
) -> SimulationResult:
    """Simulate an NVE Lennard-Jones cluster via velocity Verlet integration.

    Particles are placed on an fcc lattice at the requested density. Initial
    velocities are sampled from a Maxwell–Boltzmann distribution at the
    initialization temperature, then the centre-of-mass velocity is subtracted
    (else total momentum would be non-zero at t=0, violating the domain's
    own momentum-conservation verification target before the first step
    runs).

    Args:
        n_particles: requested particle count (rounded up to the next
            fcc-compatible count if necessary).
        temperature: initialization temperature in reduced units (must be > 0).
            This is the temperature of the Maxwell–Boltzmann velocity
            distribution at t=0, NOT the equilibrated temperature — the
            fcc lattice stores excess potential energy that converts to
            kinetic during relaxation, so T_init=0.1 equilibrates UP to
            ~0.288 while T_init=2.0 equilibrates DOWN to ~0.750. The
            validation flags warn based on this initialization temperature.
        timestep: integration step size :math:`\\Delta t` in reduced units.
        n_steps: number of velocity Verlet steps.
        density: number density :math:`\\rho` in reduced units, used to
            set the fcc lattice spacing.
        seed: optional RNG seed for velocity initialization (ADR 0005).

    Returns:
        SimulationResult with columns ``["step", "time", "total_energy",
        "kinetic_energy", "potential_energy", "total_momentum_magnitude"]``,
        one row per step from 0 to ``n_steps`` inclusive.

    Raises:
        ModelBuildError: if parameters are invalid.
    """
    validation = validate_md_params(
        n_particles, temperature, timestep, n_steps, density)
    validation.raise_if_invalid()

    # --- fcc lattice placement ---
    positions, actual_n = _fcc_lattice_positions(n_particles, density)

    # --- Maxwell–Boltzmann velocity initialization (ADR 0005) ---
    rng = np.random.default_rng(seed)
    velocities = rng.normal(
        loc=0.0,
        scale=math.sqrt(temperature),  # kB=1, m=1 => sigma = sqrt(kBT/m)
        size=(actual_n, 3),
    )
    # Subtract centre-of-mass velocity
    com_velocity = velocities.mean(axis=0)
    velocities -= com_velocity

    # --- Initial forces and energies ---
    forces = _compute_pairwise_forces(positions, actual_n)
    accelerations = forces  # m = 1

    ke_initial = 0.5 * float(np.sum(velocities ** 2))
    pe_initial = _compute_lj_potential(positions, actual_n)
    te_initial = ke_initial + pe_initial
    momentum_initial = float(np.linalg.norm(velocities.sum(axis=0)))

    # --- Integration loop ---
    cols = ["step", "time", "total_energy", "kinetic_energy",
            "potential_energy", "total_momentum_magnitude"]
    data: List[List[float]] = [
        [0.0, 0.0, te_initial, ke_initial, pe_initial, momentum_initial]
    ]

    for step in range(1, n_steps + 1):
        # Velocity Verlet step
        # 1. Update positions
        positions += velocities * timestep + 0.5 * accelerations * timestep ** 2

        # 2. Half-step velocities
        velocities += 0.5 * accelerations * timestep

        # 3. New forces / accelerations
        forces = _compute_pairwise_forces(positions, actual_n)
        accelerations = forces  # m = 1

        # 4. Complete velocity update
        velocities += 0.5 * accelerations * timestep

        # Energies and momentum
        ke = 0.5 * float(np.sum(velocities ** 2))
        pe = _compute_lj_potential(positions, actual_n)
        te = ke + pe
        momentum = float(np.linalg.norm(velocities.sum(axis=0)))

        # Divergence guard: a flagged-but-valid timestep (or a
        # high-temperature run) can drive two particles into the steep
        # r^{-12} wall, after which the trajectory explodes. Explosions
        # do NOT always produce NaN/inf — kinetic energy can grow by
        # tens of orders of magnitude while staying finite — so the
        # guard fires on either non-finite values or an energy that
        # grows far beyond the (conserved, bounded-oscillating) initial
        # scale. Stop early and report the truncation as a flag rather
        # than returning a result full of junk rows.
        if not (np.isfinite(positions).all() and np.isfinite(te)
                and np.isfinite(momentum)) or abs(te) > 10.0 * abs(te_initial) + 1e-6:
            validation.flagged = True
            divergence_note = (
                f"trajectory diverged at step {step} "
                f"(|E|={abs(te):.3e} vs |E0|={abs(te_initial):.3e}); "
                f"simulation stopped early after {step - 1} steps")
            validation.flag_reason = (
                f"{validation.flag_reason}; {divergence_note}"
                if validation.flag_reason else divergence_note)
            break

        t = step * timestep
        data.append([
            float(step),
            t,
            te,
            ke,
            pe,
            momentum,
        ])

    return SimulationResult(
        colnames=cols,
        data=data,
        model_name="molecular_dynamics",
        validation=validation,
    )


def _compute_pairwise_forces(
    positions: np.ndarray,
    n: int,
) -> np.ndarray:
    """Compute all pairwise Lennard-Jones forces via vectorised numpy.

    Each pair ``(i, j)`` with ``i < j`` is evaluated once; the force is
    added to particle ``i`` and the negative to particle ``j`` (Newton's
    third law). Self-interactions (``i == j``) are skipped.

    Uses broadcasting: ``dr`` shape ``(n, n, 3)``, then contracts over the
    ``j`` axis to get total force per particle.  Much faster than nested
    Python loops for teaching-scale N (≈ 100–500).

    Args:
        positions: shape ``(n, 3)`` particle positions.
        n: number of particles (redundant with ``positions.shape[0]`` but
            kept for caller convenience).

    Returns:
        forces: shape ``(n, 3)`` total force on each particle.
    """
    # All pairwise displacement vectors  (n, n, 3)
    dr = positions[:, None, :] - positions[None, :, :]

    # Squared distances  (n, n)
    r2 = np.sum(dr * dr, axis=2)

    # Suppress self-interaction (divide-by-zero safe by using inf)
    np.fill_diagonal(r2, np.inf)

    r2_inv = 1.0 / r2
    r6_inv = r2_inv ** 3
    r8_inv = r6_inv * r2_inv
    r14_inv = r8_inv * r6_inv

    # Force magnitudes  (n, n)
    magnitudes = 24.0 * (2.0 * r14_inv - r8_inv)

    # Force vectors  (n, n, 3); contract over j-axis → (n, 3)
    forces = np.sum(magnitudes[:, :, None] * dr, axis=1)
    return forces.astype(np.float64, copy=False)  # type: ignore[return-value]


def _compute_lj_potential(
    positions: np.ndarray,
    n: int,
) -> float:
    """Compute total Lennard-Jones potential energy (sum over i<j).

    Args:
        positions: shape ``(n, 3)`` particle positions.
        n: number of particles.

    Returns:
        total potential energy in reduced units.
    """
    dr = positions[:, None, :] - positions[None, :, :]
    r2 = np.sum(dr * dr, axis=2)
    np.fill_diagonal(r2, np.inf)

    r6_inv = 1.0 / (r2 ** 3)
    r12_inv = r6_inv ** 2

    # Full matrix (symmetric); divide by 2 to get sum over i < j
    pe_matrix = 4.0 * (r12_inv - r6_inv)
    return float(np.sum(pe_matrix) * 0.5)
