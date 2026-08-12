# ADR 0006: Model molecular dynamics as direct Python (velocity Verlet), not through antimony/roadrunner

**Status:** Accepted

## Context

Every continuous-time domain implemented so far (Michaelis-Menten
kinetics, SIR/SEIR epidemiology) is a small system of coupled
concentration ODEs built the same way: define the model in antimony,
translate to SBML, integrate with roadrunner. It would have been
consistent to force molecular dynamics through the same pipeline.

MD is continuous-time, but its structure is different in two ways that
matter. First, its state is not a handful of species concentrations —
it is positions and velocities for N particles in 3D, evolved under
pairwise forces (Lennard-Jones). Second, the correctness criterion for
a long MD trajectory is *energy conservation*, and the integrator is
chosen specifically for it: velocity Verlet is symplectic, so its
energy error is bounded and oscillating, scaling as the square of the
step size rather than growing with simulation length. A general-purpose
adaptive-step solver — what roadrunner uses — does not have this
property. Adaptive step sizing trades energy conservation for local
error control: it is accurate per step and wrong over long trajectories,
the deterministic-domain equivalent of the population-genetics fixation
problem found in Stage 2 — a subtly wrong tool producing
plausible-looking but incorrect long-run behavior. This is a
continuous-time domain, but the antimony → SBML → roadrunner pipeline
is the wrong engine for it, for the same category of reason ADR 0002
gave for PCR — extended here from a discrete process to a continuous
one.

## Decision

Implement the Stage 3 MD domain as direct Python in
`terium_engine.py` (validation contract, particle initialization,
Lennard-Jones force calculation, velocity Verlet integration step, full
run) using numpy only. No antimony, no SBML, no roadrunner, no external
MD engine (OpenMM, LAMMPS, etc.). Fixed step size, no adaptive stepping.
Verification is against exact invariants (total energy with
step-size-scaled bounded error; total momentum conserved to machine
precision) and a closed-form force table at fixed configurations —
not against reference-solver output. The stochastic part of the domain
(initial Maxwell–Boltzmann velocity sampling) follows ADR 0005's RNG
convention: `numpy.random.default_rng(seed)`, `seed: int | None = None`.

## Consequences

- Correctness tests assert invariant properties of the trajectory and
  closed-form force values, with one test type the pipeline domains
  never needed: an integrator-order check (halving the step must shrink
  the energy-error amplitude by ~4x, distinguishing velocity Verlet
  from the symplectic-but-first-order Euler-Cromer).
- This domain doesn't get SBML export, roadrunner-based features
  (steady-state solving, parameter scanning) for free. A future MD
  extension that needs them would have to implement them itself or
  reconsider this ADR.
- Extends ADR 0002's precedent: "is this actually a continuous-time ODE
  system solvable by a general integrator?" is now asked explicitly of
  every domain — and the answer is no for MD despite the domain being
  continuous. The pipeline question is per-domain, not per-category.
- Establishes the invariant-based verification pattern for future
  deterministic dynamical-systems domains (e.g., celestial mechanics,
  rigid-body dynamics), and makes the box/thermostat/barostat family of
  features explicitly later-stage extensions, not silently-implemented
  scope growth.
