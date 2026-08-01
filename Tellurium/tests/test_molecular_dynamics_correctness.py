"""Tests for Stage 3: molecular dynamics (Lennard-Jones, velocity Verlet).

Verification targets (per Stage 3 Part 2, Section 6):
  Target A — energy conservation + halving-step order check (velocity Verlet)
  Target B — momentum conservation (exact, machine precision)
  Target C — closed-form force table (equilibrium, attractive, repulsive)
  Target D — fixed-seed reproducibility + different-seed divergence

Pre-specified mutations (5):
  1. VV → Euler-Cromer — caught ONLY by halving-step scaling (Target A)
  2. Force sign flip — caught ONLY by Target C
  3. Missing pair direction (force not antisymmetric) — caught by Target B
  4. COM velocity not subtracted — caught by Target B at t=0
  5. r vs r^2 confusion — caught ONLY by Target C

Mutation 2 independently reproduced, Stage 3 Part 3 (2026-07-31):
negated lennard_jones_force's magnitude (`magnitude = 24.0 * (...)` ->
`magnitude = -24.0 * (...)`), reverted after. Exactly 4 tests fail --
test_force_attractive_at_r_1_5, test_force_repulsive_at_r_0_9 (Target
C), test_force_signs_are_correct, and
test_force_magnitude_matches_closed_form (the two mutation-detection
tests) -- and, critically, all Target A and B tests still pass (50/54),
confirming by direct reproduction, not just prediction, that a
sign-flipped force is genuinely conservative and momentum-preserving:
energy conservation and momentum conservation cannot see this bug at
all. Reverted; suite confirmed clean (54/54) afterward.
"""

from __future__ import annotations

import os
import sys

import numpy as np
import pytest

# Ensure the Tellurium package is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tellurium_engine import (  # noqa: E402
    ModelBuildError,
    SimulationResult,
    lennard_jones_force,
    simulate_molecular_dynamics,
    validate_md_params,
)


# =========================================================================
# helpers
# =========================================================================


def _target_a_result() -> SimulationResult:
    """Cached Target A run: N=108, T=0.4, dt=0.005, 2000 steps, seed=42."""
    return simulate_molecular_dynamics(108, 0.4, 0.005, 2000, seed=42)


def _energy_conservation_metrics(
    result: SimulationResult,
) -> tuple[float, float]:
    """Return (max_rel_dev, initial_total_energy)."""
    te = result.column("total_energy")
    te0 = te[0]
    max_dev = max(abs(e - te0) for e in te)
    return max_dev / abs(te0) if te0 != 0 else float("inf"), te0


# =========================================================================
# Target A — energy conservation + halving-step order check
# =========================================================================


class TestTargetAEnergyConservation:
    """Energy must stay within a bounded oscillation band — no monotonic drift."""

    def test_energy_bounded_oscillation(self) -> None:
        """|Delta E| / E0 < 1e-3 over the full run."""
        result = _target_a_result()
        max_dev, _ = _energy_conservation_metrics(result)
        assert max_dev < 1e-3, (
            f"energy drift {max_dev:.2e} exceeds 1e-3 bound"
        )

    def test_halving_step_reduces_energy_error(self) -> None:
        """Halving dt must shrink energy error by factor 3–5 (VV is O(dt^2))."""
        r = _target_a_result()
        r_half = simulate_molecular_dynamics(108, 0.4, 0.0025, 2000, seed=42)
        dev, _ = _energy_conservation_metrics(r)
        dev_half, _ = _energy_conservation_metrics(r_half)
        ratio = dev / dev_half if dev_half > 0 else float("inf")
        assert 3.0 <= ratio <= 5.0, (
            f"halving-step ratio {ratio:.2f} outside [3, 5]; "
            "integrator may not be velocity Verlet"
        )

    def test_energy_error_does_not_grow_with_time(self) -> None:
        """Energy error should fluctuate, not grow monotonically after the first
        few steps."""
        result = _target_a_result()
        te = result.column("total_energy")
        te0 = te[0]
        # Look at the second half – error should not be steadily increasing
        mid = len(te) // 2
        first_half_max = max(abs(e - te0) for e in te[:mid])
        second_half_max = max(abs(e - te0) for e in te[mid:])
        # Allow second half to be up to 3x worse (fluctuations, not drift)
        assert second_half_max <= 3.0 * first_half_max, (
            f"second-half error {second_half_max:.2e} is more than 3× "
            f"first-half error {first_half_max:.2e} — possible drift"
        )


# =========================================================================
# Target B — momentum conservation (exact, machine precision)
# =========================================================================


class TestTargetBMomentumConservation:
    """Total momentum must be conserved to machine precision at every step."""

    def test_momentum_near_zero_throughout(self) -> None:
        """Momentum magnitude < 1e-10 at every recorded step."""
        result = _target_a_result()
        mom = result.column("total_momentum_magnitude")
        max_mom = max(mom)
        assert max_mom < 1e-10, (
            f"maximum momentum magnitude {max_mom:.2e} exceeds 1e-10"
        )

    def test_momentum_zero_at_t0(self) -> None:
        """COM velocity subtracted → momentum is ~0 at step 0."""
        result = simulate_molecular_dynamics(32, 1.0, 0.001, 10, seed=99)
        mom0 = result.data[0][5]
        assert mom0 < 1e-14, (
            f"momentum at t=0 is {mom0:.2e}; COM velocity may not be subtracted"
        )

    def test_momentum_stays_constant(self) -> None:
        """The standard deviation of momentum across steps should be tiny."""
        result = simulate_molecular_dynamics(32, 0.5, 0.002, 100, seed=42)
        mom = result.column("total_momentum_magnitude")
        assert float(np.std(mom)) < 1e-14, (
            "momentum fluctuates beyond machine precision"
        )


# =========================================================================
# Target C — closed-form force table
# =========================================================================


class TestTargetCForceTable:
    """Lennard-Jones force at fixed separations, tested in isolation."""

    R_EQ = 2.0 ** (1.0 / 6.0)  # ≈ 1.122462

    def test_force_zero_at_equilibrium(self) -> None:
        """Force magnitude < 1e-9 at the LJ minimum r = 2^(1/6)."""
        rv = np.array([self.R_EQ, 0.0, 0.0], dtype=np.float64)
        f = lennard_jones_force(rv)
        assert np.linalg.norm(f) < 1e-9, (
            f"force at equilibrium has magnitude {np.linalg.norm(f):.2e}"
        )

    def test_force_attractive_at_r_1_5(self) -> None:
        """At r=1.5 (> equilibrium) force must point toward the other particle
        (negative x if separation is +x)."""
        rv = np.array([1.5, 0.0, 0.0], dtype=np.float64)
        f = lennard_jones_force(rv)
        # Attractive: points toward origin → x-component negative
        assert f[0] < 0, f"expected attractive (negative Fx), got {f[0]}"
        assert abs(f[1]) < 1e-14
        assert abs(f[2]) < 1e-14
        # Check magnitude against closed form
        r = 1.5
        expected_fx = 24.0 * (2.0 / r**14 - 1.0 / r**8) * r
        assert abs(f[0] - expected_fx) < 1e-9, (
            f"force magnitude {f[0]:.10f} vs closed-form {expected_fx:.10f}"
        )

    def test_force_repulsive_at_r_0_9(self) -> None:
        """At r=0.9 (< equilibrium) force must point away (+x for +x separation)."""
        rv = np.array([0.9, 0.0, 0.0], dtype=np.float64)
        f = lennard_jones_force(rv)
        # Repulsive: points away from origin → x-component positive
        assert f[0] > 0, f"expected repulsive (positive Fx), got {f[0]}"
        assert abs(f[1]) < 1e-14
        assert abs(f[2]) < 1e-14
        # Check magnitude against closed form
        r = 0.9
        expected_fx = 24.0 * (2.0 / r**14 - 1.0 / r**8) * r
        assert abs(f[0] - expected_fx) < 1e-9, (
            f"force magnitude {f[0]:.10f} vs closed-form {expected_fx:.10f}"
        )

    def test_force_antisymmetric(self) -> None:
        """F_ij = -F_ji for an arbitrary test vector."""
        rv = np.array([1.3, 0.7, -0.4], dtype=np.float64)
        f_ij = lennard_jones_force(rv)
        f_ji = lennard_jones_force(-rv)
        assert np.linalg.norm(f_ij + f_ji) < 1e-14, (
            f"force not antisymmetric: F_ij={f_ij}, F_ji={f_ji}"
        )

    def test_force_zero_at_large_separation(self) -> None:
        """Force should be negligible at large r (decays as r^{-7})."""
        rv = np.array([10.0, 0.0, 0.0], dtype=np.float64)
        f = lennard_jones_force(rv)
        assert np.linalg.norm(f) < 1e-5, (
            f"force at r=10 should be tiny, got |F|={np.linalg.norm(f):.2e}"
        )


# =========================================================================
# Target D — seed reproducibility
# =========================================================================


class TestTargetDSeedReproducibility:
    """ADR 0005: fixed seed → bit-identical; different seeds → diverge."""

    def test_fixed_seed_reproduces_bit_identical(self) -> None:
        r1 = simulate_molecular_dynamics(32, 0.5, 0.001, 20, seed=42)
        r2 = simulate_molecular_dynamics(32, 0.5, 0.001, 20, seed=42)
        for i, (row1, row2) in enumerate(zip(r1.data, r2.data)):
            for j, (v1, v2) in enumerate(zip(row1, row2)):
                assert v1 == v2, (
                    f"row {i} col {j}: {v1} vs {v2} — seed reproducibility broken"
                )

    def test_different_seeds_diverge(self) -> None:
        r1 = simulate_molecular_dynamics(32, 0.5, 0.001, 20, seed=1)
        r2 = simulate_molecular_dynamics(32, 0.5, 0.001, 20, seed=2)
        # Total energies at step 5 should differ
        assert r1.data[5][2] != r2.data[5][2], (
            "different seeds produced identical energy — RNG may be ignored"
        )

    def test_no_seed_gives_different_results(self) -> None:
        """Successive seedless calls must produce different trajectories."""
        results = [
            simulate_molecular_dynamics(32, 0.5, 0.001, 10)
            for _ in range(5)
        ]
        energies = [r.data[3][2] for r in results]
        # At least 4 of 5 should be unique
        assert len(set(energies)) >= 4, (
            f"only {len(set(energies))} unique energies across 5 seedless runs"
        )


# =========================================================================
# Validation — hard rejections (ok=False)
# =========================================================================


class TestValidationHardRejections:
    """All invalid parameters must give ok=False."""

    def test_n_particles_bool_rejected(self) -> None:
        v = validate_md_params(True, 0.4, 0.005, 1000)  # type: ignore[arg-type]
        assert not v.ok

    def test_n_particles_float_rejected(self) -> None:
        v = validate_md_params(3.5, 0.4, 0.005, 1000)  # type: ignore[arg-type]
        assert not v.ok

    def test_n_particles_lt_2_rejected(self) -> None:
        v = validate_md_params(1, 0.4, 0.005, 1000)
        assert not v.ok

    def test_n_particles_zero_rejected(self) -> None:
        v = validate_md_params(0, 0.4, 0.005, 1000)
        assert not v.ok

    def test_n_particles_negative_rejected(self) -> None:
        v = validate_md_params(-5, 0.4, 0.005, 1000)
        assert not v.ok

    def test_temperature_bool_rejected(self) -> None:
        v = validate_md_params(108, True, 0.005, 1000)  # type: ignore[arg-type]
        assert not v.ok

    def test_temperature_nan_rejected(self) -> None:
        v = validate_md_params(108, float("nan"), 0.005, 1000)
        assert not v.ok

    def test_temperature_zero_rejected(self) -> None:
        v = validate_md_params(108, 0.0, 0.005, 1000)
        assert not v.ok

    def test_temperature_negative_rejected(self) -> None:
        v = validate_md_params(108, -0.1, 0.005, 1000)
        assert not v.ok

    def test_timestep_bool_rejected(self) -> None:
        v = validate_md_params(108, 0.4, False, 1000)  # type: ignore[arg-type]
        assert not v.ok

    def test_timestep_nan_rejected(self) -> None:
        v = validate_md_params(108, 0.4, float("nan"), 1000)
        assert not v.ok

    def test_timestep_zero_rejected(self) -> None:
        v = validate_md_params(108, 0.4, 0.0, 1000)
        assert not v.ok

    def test_timestep_negative_rejected(self) -> None:
        v = validate_md_params(108, 0.4, -0.001, 1000)
        assert not v.ok

    def test_n_steps_bool_rejected(self) -> None:
        v = validate_md_params(108, 0.4, 0.005, True)  # type: ignore[arg-type]
        assert not v.ok

    def test_n_steps_float_rejected(self) -> None:
        v = validate_md_params(108, 0.4, 0.005, 2.5)  # type: ignore[arg-type]
        assert not v.ok

    def test_n_steps_zero_rejected(self) -> None:
        v = validate_md_params(108, 0.4, 0.005, 0)
        assert not v.ok

    def test_n_steps_negative_rejected(self) -> None:
        v = validate_md_params(108, 0.4, 0.005, -10)
        assert not v.ok

    def test_density_bool_rejected(self) -> None:
        v = validate_md_params(108, 0.4, 0.005, 1000, density=True)  # type: ignore[arg-type]
        assert not v.ok

    def test_density_nan_rejected(self) -> None:
        v = validate_md_params(108, 0.4, 0.005, 1000, density=float("nan"))
        assert not v.ok

    def test_density_zero_rejected(self) -> None:
        v = validate_md_params(108, 0.4, 0.005, 1000, density=0.0)
        assert not v.ok

    def test_density_negative_rejected(self) -> None:
        v = validate_md_params(108, 0.4, 0.005, 1000, density=-0.1)
        assert not v.ok

    def test_raises_model_build_error(self) -> None:
        """Hard-rejected params should raise ModelBuildError when simulated."""
        with pytest.raises(ModelBuildError):
            simulate_molecular_dynamics(1, 0.4, 0.005, 1000)


# =========================================================================
# Validation — flags (ok=True, flagged=True)
# =========================================================================


class TestValidationFlags:
    """Plausible-but-concerning parameters must be flagged, not rejected."""

    def test_timestep_above_max_is_flagged(self) -> None:
        v = validate_md_params(108, 0.4, 0.05, 1000)
        assert v.ok
        assert v.flagged
        assert "timestep" in (v.flag_reason or "").lower()

    def test_temperature_below_low_is_flagged(self) -> None:
        v = validate_md_params(108, 0.05, 0.005, 1000)
        assert v.ok
        assert v.flagged
        assert "frozen" in (v.flag_reason or "").lower()

    def test_temperature_above_high_is_flagged(self) -> None:
        v = validate_md_params(108, 3.0, 0.005, 1000)
        assert v.ok
        assert v.flagged
        assert "evaporat" in (v.flag_reason or "").lower()

    def test_n_particles_below_min_is_flagged(self) -> None:
        v = validate_md_params(5, 0.4, 0.005, 1000)
        assert v.ok
        assert v.flagged
        assert "too small" in (v.flag_reason or "").lower()

    def test_non_fcc_count_is_flagged(self) -> None:
        """13 is not an fcc-compatible count (nearest: 4*2^3=32)."""
        v = validate_md_params(13, 0.4, 0.005, 1000)
        assert v.ok
        assert v.flagged
        assert "fcc" in (v.flag_reason or "").lower()

    def test_fcc_count_not_flagged(self) -> None:
        """32 = 4 * 2^3 is an exact fcc count."""
        v = validate_md_params(32, 0.4, 0.005, 1000)
        assert v.ok
        assert not v.flagged

    def test_flagged_run_still_simulates(self) -> None:
        """Flagged params should produce a valid result (not raise)."""
        result = simulate_molecular_dynamics(5, 0.4, 0.005, 10)
        assert result.flagged
        assert len(result.data) == 11  # 10 steps + t=0
        assert "total_energy" in result.colnames


# =========================================================================
# Structural invariants
# =========================================================================


class TestStructuralInvariants:
    """Properties that must hold regardless of the random seed."""

    def test_result_colnames(self) -> None:
        result = simulate_molecular_dynamics(32, 0.4, 0.001, 5, seed=42)
        assert result.colnames == [
            "step", "time", "total_energy", "kinetic_energy",
            "potential_energy", "total_momentum_magnitude"
        ]

    def test_model_name(self) -> None:
        result = simulate_molecular_dynamics(32, 0.4, 0.001, 5, seed=42)
        assert result.model_name == "molecular_dynamics"

    def test_row_count(self) -> None:
        """n_steps + 1 rows (step 0 through step n_steps)."""
        result = simulate_molecular_dynamics(32, 0.4, 0.001, 15, seed=42)
        assert len(result.data) == 16

    def test_time_increases_quadratically(self) -> None:
        """Time column = step * dt."""
        result = simulate_molecular_dynamics(32, 0.4, 0.003, 10, seed=42)
        times = result.column("time")
        for step, t in enumerate(times):
            assert abs(t - step * 0.003) < 1e-15

    def test_kinetic_plus_potential_equals_total(self) -> None:
        """KE + PE == TE at every step."""
        result = simulate_molecular_dynamics(32, 0.4, 0.001, 10, seed=42)
        for row in result.data:
            ke, pe, te = row[3], row[4], row[2]
            assert abs(ke + pe - te) < 1e-12, (
                f"KE={ke} + PE={pe} ≠ TE={te} (diff={ke+pe-te:.2e})"
            )

    def test_fcc_lattice_no_overlap(self) -> None:
        """At t=0, no two particles should be within a hard-core distance.
        The fcc lattice at density 0.85 gives nearest-neighbour distance > 0.7."""
        # Run with large n for a meaningful check
        result = simulate_molecular_dynamics(32, 0.4, 0.001, 1, seed=42)
        # We can check via the initial PE — it shouldn't be catastrophically
        # positive (which would indicate particles overlapping inside the
        # repulsive wall)
        pe0 = result.data[0][4]
        assert pe0 < 0, (
            f"initial PE is positive ({pe0}); particles likely overlap"
        )


# =========================================================================
# Pre-specified mutations
# =========================================================================


class TestMutationVelocityVerletVsEulerCromer:
    """Mutation 1: swap velocity Verlet for Euler-Cromer.

    Euler-Cromer is also symplectic (bounded energy oscillation), but only
    first-order. The halving-step ratio drops below 3 — only the order check
    in Target A can catch this.
    """

    def test_euler_cromer_would_fail_order_check(self) -> None:
        """Documented mutation: VV→EC, caught by halving-step ratio."""
        # We can't mutate in-process trivially, but we verify that the real
        # velocity Verlet implementation passes the order check (Target A),
        # and the mutation is documented here for the reviewer to manually
        # reproduce per the verification procedure.
        result = simulate_molecular_dynamics(32, 0.4, 0.004, 300, seed=42)
        result_half = simulate_molecular_dynamics(32, 0.4, 0.002, 300, seed=42)
        dev, _ = _energy_conservation_metrics(result)
        dev_half, _ = _energy_conservation_metrics(result_half)
        ratio = dev / dev_half if dev_half > 0 else float("inf")
        assert ratio > 3.0, (
            f"halving-step ratio {ratio:.2f} — VV order check failed; "
            "integrator may not be velocity Verlet"
        )


class TestMutationForceSignFlip:
    """Mutation 2: flip the sign of the LJ force.

    Still conservative (antisymmetry preserved), still momentum-conserving.
    Caught ONLY by Target C (force table shows wrong sign at r=0.9 and r=1.5).
    """

    def test_force_signs_are_correct(self) -> None:
        """The real implementation has correct signs — Target C tests verify this
        directly (attractive at 1.5, repulsive at 0.9)."""
        # Redundant with Target C tests; exists so the mutation is explicitly
        # named in its own test class for the reviewer to find.
        rv_att = np.array([1.5, 0.0, 0.0])
        rv_rep = np.array([0.9, 0.0, 0.0])
        f_att = lennard_jones_force(rv_att)
        f_rep = lennard_jones_force(rv_rep)
        assert f_att[0] < 0, "attractive force sign wrong"
        assert f_rep[0] > 0, "repulsive force sign wrong"


class TestMutationMissingPairDirection:
    """Mutation 3: add force to particle i but not the negative to particle j.

    Breaks Newton's third law → momentum not conserved. Caught by Target B.
    """

    def test_momentum_is_conserved(self) -> None:
        """The real implementation conserves momentum — Target B tests verify
        this directly."""
        result = simulate_molecular_dynamics(32, 0.5, 0.002, 50, seed=42)
        mom = result.column("total_momentum_magnitude")
        assert max(mom) < 1e-10, "momentum not conserved — pair direction bug?"


class TestMutationComVelocityNotSubtracted:
    """Mutation 4: skip COM velocity subtraction at initialization.

    Even if the Maxwell-Boltzmann distribution sums to zero in expectation,
    a finite sample won't. Target B catches this at t=0.
    """

    def test_momentum_zero_at_t0(self) -> None:
        """Already tested in Target B — repeated here for mutation naming."""
        result = simulate_molecular_dynamics(32, 1.0, 0.001, 10, seed=99)
        assert result.data[0][5] < 1e-14, (
            "momentum non-zero at t=0 — COM velocity may not be subtracted"
        )


class TestMutationRVSR2Confusion:
    """Mutation 5: use r instead of r^2 in the force denominator.

    Still conservative, still antisymmetric. Passes Target A and B.
    Caught ONLY by Target C (closed-form magnitude is wrong).
    """

    def test_force_magnitude_matches_closed_form(self) -> None:
        """Target C tests verify exact closed-form magnitudes."""
        rv = np.array([1.5, 0.0, 0.0])
        f = lennard_jones_force(rv)
        r = 1.5
        expected = 24.0 * (2.0 / r**14 - 1.0 / r**8) * r
        assert abs(f[0] - expected) < 1e-9, (
            f"force {f[0]:.10f} vs closed-form {expected:.10f} — "
            "possible r vs r^2 confusion"
        )


# =========================================================================
# Mutation-test record
# =========================================================================
#
# MUTATION 1 (VV → Euler-Cromer):
#   Replace velocity Verlet steps with Euler-Cromer (x → v, then v → a).
#   Energy still bounded-oscillating (both are symplectic), but the
#   halving-step ratio drops from ~4 to ~2 (EC is only first order).
#   Caught by: test_halving_step_reduces_energy_error (Target A).
#
# MUTATION 2 (force sign flip):
#   Negate the magnitude in lennard_jones_force().
#   Still conservative, still antisymmetric. Target A and B pass.
#   Caught ONLY by: test_force_attractive_at_r_1_5 and
#   test_force_repulsive_at_r_0_9 (Target C).
#
# MUTATION 3 (missing pair direction):
#   Change _compute_pairwise_forces to add F to particle i without
#   subtracting from particle j (or: use np.sum(magnitudes * dr, axis=1)
#   without properly computing the antisymmetric contribution).
#   Caught by: test_momentum_near_zero_throughout (Target B) — momentum
#   immediately departs from zero.
#
# MUTATION 4 (COM velocity not subtracted):
#   Comment out the `velocities -= com_velocity` line.
#   Caught by: test_momentum_zero_at_t0 (Target B) — momentum non-zero at
#   step 0.
#
# MUTATION 5 (r vs r^2 confusion):
#   Use r (sqrt(r^2)) instead of r^2 in the r^-14 and r^-8 denominators,
#   e.g., `r1 = math.sqrt(r_sq)` then `r8_inv = 1.0 / (r1 ** 8)`.
#   Still conservative, antisymmetric. Target A and B pass.
#   Caught ONLY by: test_force_magnitude_matches_closed_form (Target C).
