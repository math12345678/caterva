# Stage 3, Part 2 — Domain Spec: Molecular Dynamics (Lennard-Jones, Velocity Verlet)

## 0. Amendments, recorded at implementation time

> **See also Section 13** — three further amendments (2026-07-31) from a
> literature-verification pass: one measured correction to a validation
> bound that shipped too permissive, one retraction of an incorrect
> claim made during that same pass, and a new literature-backed
> verification target (published LJ cluster global minima).

Two clarifications landed while the implementation was being reviewed,
recorded here so both implementers share the same contract (the Stage 2
lesson: write the amendment *at the time*, not silently):

1. **Flags accumulate, never mutually exclusive.** `validate_md_params`
   reports *all* applicable flags (joined with "; "), not the first one
   that fires — this is the exact bug class fixed in Stage 2
   (commit e1568e4, "Fix elif-chain bug in validate_wright_fisher_params
   (flags were mutually exclusive)") and the MD validator must not
   reintroduce it.
2. **Divergence guard.** The spec's own flag ("timestep > 0.01 — risk
   of ... outright numerical explosion") implies explosions must be
   handled meaningfully. A flagged-but-valid timestep can drive two
   particles into the r^{-12} wall; the simulation then stops early at
   the first non-finite state, sets `flagged=True`, appends
   "trajectory diverged at step k ..." to `flag_reason`, and returns
   the finite prefix of the trajectory — never a result silently full
   of NaN rows.

## 1. ONE-SENTENCE DEFINITION

Simulate an unbounded cluster of N identical particles interacting via
the Lennard-Jones pairwise potential, integrated with velocity Verlet,
verified against exact energy-scaling and momentum invariants plus a
closed-form force table.

## 2. GOVERNING MODEL

Positions $\mathbf{x}_i \in \mathbb{R}^3$ and velocities $\mathbf{v}_i$
for $i = 1 \dots N$, unit mass ($m=1$, reduced units). Pairwise
Lennard-Jones potential and force between particles $i,j$ at separation
$r = |\mathbf{r}_{ij}|$:

$$V(r) = 4\varepsilon\left[\left(\frac{\sigma}{r}\right)^{12} - \left(\frac{\sigma}{r}\right)^{6}\right], \qquad
\mathbf{F}_{ij} = \frac{24\varepsilon}{\sigma^2}\left[2\left(\frac{\sigma}{r}\right)^{14} - \left(\frac{\sigma}{r}\right)^{8}\right]\mathbf{r}_{ij}$$

with $\mathbf{F}_{ji} = -\mathbf{F}_{ij}$ (Newton's third law; every pair
computed once, $i<j$, applied to both). Reduced units throughout
($\varepsilon = \sigma = 1$). Initialization: particles on an fcc
lattice (no overlap), velocities sampled from a Maxwell–Boltzmann
distribution at target temperature $T^*$, then the center-of-mass
velocity is subtracted from every particle (else total momentum is
nonzero at $t=0$, violating the domain's own verification target before
the first step runs).

Velocity Verlet integration, fixed step $\Delta t$:

1. $\mathbf{x}(t+\Delta t) = \mathbf{x}(t) + \mathbf{v}(t)\Delta t + \tfrac{1}{2}\mathbf{a}(t)\Delta t^2$
2. $\mathbf{v}(t+\tfrac{\Delta t}{2}) = \mathbf{v}(t) + \tfrac{1}{2}\mathbf{a}(t)\Delta t$
3. $\mathbf{a}(t+\Delta t) = \mathbf{F}(\mathbf{x}(t+\Delta t))/m$
4. $\mathbf{v}(t+\Delta t) = \mathbf{v}(t+\tfrac{\Delta t}{2}) + \tfrac{1}{2}\mathbf{a}(t+\Delta t)\Delta t$

## 3. CONTINUOUS OR DISCRETE — AND WHY

**Continuous-time, but direct Python — not antimony/SBML/roadrunner.**
Recorded in ADR 0006: MD's correctness criterion (energy conservation
over long trajectories) requires a symplectic, fixed-step integrator;
a general adaptive-step solver like roadrunner trades energy
conservation for local error control, which is the wrong property for
this domain. Same category of decision as ADR 0002 (PCR), extended from
a discrete process to a continuous one — the pipeline choice is
per-domain, not per-category (Rule 3).

## 4. PUBLIC FUNCTION SIGNATURES

```python
def validate_md_params(
    n_particles: int,
    temperature: float,
    timestep: float,
    n_steps: int,
    density: float = 0.85,
) -> ParameterValidation: ...

def simulate_molecular_dynamics(
    n_particles: int,
    temperature: float,
    timestep: float,
    n_steps: int,
    density: float = 0.85,
    seed: int | None = None,
) -> SimulationResult: ...

def lennard_jones_force(
    r_vec: np.ndarray,  # separation vector, shape (3,)
) -> np.ndarray:  # force vector, shape (3,), reduced units eps=sigma=1
    ...
```

`lennard_jones_force` is exported separately from the main simulation
function specifically so the force-table test (Section 6, Target C)
can pin the force law in isolation, independent of the integrator or
particle-initialization logic — the same reasoning that keeps
`validate_*` separate from `simulate_*` everywhere else in this file.

`SimulationResult` columns: `step`, `time`, `total_energy`,
`kinetic_energy`, `potential_energy`, `total_momentum_magnitude` — one
row per recorded step (recording every step for teaching-scale N and
step counts; no subsampling in this spec).

Particles are placed on an fcc lattice sized to the smallest cube of
unit cells accommodating `n_particles` (4 particles per conventional
fcc cell); `n_particles` values that aren't an exact fcc-compatible
count are rounded up to the next valid size, with `flagged=True` if
that differs from what was requested — noted in Section 5, not silently
substituted.

## 5. VALIDATION CONTRACT

Hard rejections (`ok=False`):
`n_particles` not an integer, or `< 2` (need at least a pair for any
force to exist — matches the domain's own logic, not an arbitrary
floor). `temperature` not a finite float, or `<= 0` (zero or negative
temperature has no physical Maxwell–Boltzmann sampling distribution).
`timestep` not a finite float, or `<= 0`. `n_steps` not an integer, or
`< 1`. `density` not a finite float, or `<= 0` (density sets the fcc
lattice spacing; non-positive is meaningless).

Flags (`ok=True, flagged=True`):
`timestep > 0.01` (reduced units) — risk of energy-conservation failure
or outright numerical explosion from the steep $r^{-12}$ repulsive
wall if two particles are ever driven close together by an
under-resolved step. `temperature` outside `[0.1, 2.0]` — below this,
the cluster is essentially frozen (numerically valid, scientifically
inert); above it, the cluster evaporates within the run, which is valid
physics but likely not the intended teaching scenario (a solid or
liquid LJ cluster). `n_particles` requested value not exactly
achievable on an fcc lattice (rounded up, actual count differs).
`n_particles < 10` — too small for the density/temperature
plausibility framing to mean much, but not physically invalid.

If the trajectory diverges mid-run (non-finite positions or energies —
the flagged-timestep explosion case), the simulation stops early,
sets `flagged=True` with a "trajectory diverged at step k" reason, and
returns the finite prefix of the trajectory (Amendment 2).

## 6. VERIFICATION TARGET

**Target A — energy conservation, with the mandatory order check.**
`simulate_molecular_dynamics(n_particles=108, temperature=0.4,
timestep=0.005, n_steps=2000, seed=42)`; total energy at each recorded
step must stay within a bounded oscillation band around its initial
value — no monotonic drift. Concretely: compute
$|\Delta E|/E_0 = \max_t |E(t) - E(0)| / |E(0)|$ over the whole run;
assert it stays below $10^{-3}$ (loose enough to tolerate one specific
seed/configuration's fluctuation size, tight enough to catch a
non-symplectic integrator's drift). **Mandatory companion assertion,
the one that actually distinguishes velocity Verlet from a merely
plausible-looking substitute**: rerun with `timestep=0.0025` (half),
and assert the new $|\Delta E|/E_0$ is smaller by a factor of
$3.0$–$5.0$ (allowing slop around the theoretical $4\times$ for a
finite-length stochastic-initial-condition run) — this is what
Section 3.2 of Part 1 established: energy fluctuation alone cannot
distinguish velocity Verlet ($O(\Delta t^2)$) from Euler-Cromer
($O(\Delta t)$, also symplectic, also bounded-oscillating); only the
halving-step scaling law can.

**Target B — momentum conservation, exact.**
Same run as Target A. `total_momentum_magnitude` at every recorded step,
normalized by $\sum_i |\mathbf{p}_i|$ at $t=0$, must stay below
$10^{-10}$ (machine-precision accumulation over 2000 steps, not a
physics tolerance — this should be far tighter than Target A's bound
because it's an algebraic identity of the force loop, not a numerical-
integration property).

**Target C — closed-form force table.**
Call `lennard_jones_force` directly (not through the full simulation)
at three fixed separations along the x-axis, $\varepsilon=\sigma=1$:
$r = 2^{1/6} \approx 1.1225$ (equilibrium): force magnitude $< 10^{-9}$
(exactly zero analytically). $r = 1.5$: force must point in the
*attractive* direction (toward the other particle) — sign check, plus
magnitude within $10^{-9}$ of the closed-form value
$\mathbf{F} = 24[2(1/1.5)^{14} - (1/1.5)^8] \cdot \mathbf{r}_{ij}$
evaluated directly from the potential's definition, computed
independently of whatever internal form the implementation uses
internally. $r = 0.9$: force must point in the *repulsive* direction
(away), same closed-form check. This target exists because the energy
invariant's sensitivity to a wrong force is limited by its own
tolerance: a force wrong by a fraction of a percent drifts $E$ slowly
enough to sit under $10^{-3}$ over a 2000-step run, and a force bug
buried in an integrated trajectory is diagnosed only by bisection.
The force table pins the law to $10^{-9}$ at fixed configurations, in
isolation — the precise, localized owner of the force function
(Part 1, Section 3.3, which was corrected *before* implementation: a
sign-flipped force does NOT pass Target A, since $E = T + V$ is
conserved iff $F = -\nabla V$ exactly).

**Target D — fixed-seed bit-identical reproducibility, and
different-seeds-diverge** — same pattern as every other stochastic
domain (ADR 0005), applied here to the Maxwell–Boltzmann velocity
initialization specifically, since the integrator itself is
deterministic once initial conditions are fixed.

**Pre-specified mutations** (five, per Part 1 Section 4/7, each mapped
to the test(s) expected to catch it — this is the spec shipping with
its mutation contract, per the Stage 2 process improvement; the
implementation records which tests actually fired, correcting the
prediction where it's wrong):

1. Velocity Verlet → Euler-Cromer substitution. Caught **only** by
   Target A's halving-step scaling assertion (both are symplectic;
   drift-vs-fluctuation alone cannot tell them apart).
2. Force sign flip (attractive becomes repulsive or vice versa).
   Does NOT pass Target A: the computed energy $E = T + V$ is
   conserved iff $F = -\nabla V$ exactly, so a sign-flipped force
   drifts $E$ (and the cluster is unstable to explosion). Caught by
   Target A at gross-error sensitivity and by Target C at closed-form
   precision — Target C is the precise, localized catch.
3. Missing pair direction (force added to particle $i$ but not $-$force
   to particle $j$, or a self-interaction term included). Caught by
   Target B (breaks exact momentum conservation immediately).
4. Center-of-mass velocity not subtracted at initialization. Caught by
   Target B failing at $t=0$, before any integration even happens.
5. $r$ vs $r^2$ confusion in the force denominator (e.g., using
   $(r^2)^{-1}$ where $(r^2)^{-3}$ belongs). Drifts the computed energy
   (Target A catches it — any deviation from $-\nabla V$ breaks the
   $E = T + V$ identity) and fails the force table at closed-form
   precision (Target C, the precise catch).

## 7. RELEVANT ADRs

ADR 0006 (this domain: direct Python, not antimony/roadrunner) —
directly applicable, drafted in Part 1. ADR 0005 (RNG convention) —
applicable to the Maxwell–Boltzmann initialization step only; the
integrator itself takes no seed-dependent behavior after $t=0$. ADR
0001, 0002, 0003, 0004 — not applicable, noted explicitly.

## 8. SHARED-CONSTRAINT CHECK

RNG convention (ADR 0005): this is the third domain to use
`numpy.random.default_rng(seed)`. `scripts/check_rng_convention.py`
checks every `simulate_*` function *except* those explicitly listed in
its `EXCLUDED_FNS` allowlist (the continuous ODE domains that
legitimately have no RNG at all). `simulate_molecular_dynamics` is not
on that allowlist, so it will be checked automatically without any
script change — as long as its signature includes `seed: int | None =
None` and its body calls `np.random.default_rng(seed)`, both already in
Section 4's signature above. Verify this actually passes in Part 3/4
rather than assuming it from this description.

## 9. OUT OF SCOPE FOR THIS STAGE

Per Part 1 Section 6, unchanged: periodic boundary conditions, neighbor/
cell lists, thermostats or barostats (NVE only), bonded potentials
(angle/dihedral terms), multi-species mixtures or electrostatics,
rigid-body or constraint dynamics, any external MD engine, GPU/
vectorization beyond plain numpy, and any reflecting-box mode (deferred
per Part 1 Section 7 item 1 — the primary and only system in this
stage's spec is the unbounded cluster, because a box breaks Target B).
No changes outside `Tellurium/tellurium_engine.py` and its tests. No new
runtime dependency (`numpy` already declared).

## 10. DELIVERABLES CHECKLIST

- [ ] `validate_md_params()`, `simulate_molecular_dynamics()`,
      `lennard_jones_force()` in `Tellurium/tellurium_engine.py`,
      exported in `__all__`.
- [ ] Tests in `Tellurium/tests/test_molecular_dynamics_correctness.py`
      (or a name matching this domain, verified against the spec
      directly rather than assumed — Stage 2's `verify_domain.sh`
      naming-convention lesson applies here too): Targets A-D, all
      validation rejections/flags, structural invariants (fcc
      placement has no overlapping particles, COM velocity is zero at
      $t=0$).
- [ ] All five pre-specified mutations, documented with which exact
      test(s) catch each, matching Section 6 above.
- [ ] Independent reproduction of at least one mutation test by the
      reviewer during Part 4 — not taken on the implementer's report.
      The single-coverage mutations are 1 (Euler-Cromer: caught only
      by the scaling assertion) and 4 (COM removal: caught only by
      Target B); mutations 2 and 5 have redundant coverage (A + C).
      Reproducing one of the single-coverage ones is the highest-value
      independent check — the others' predictions were also corrected
      before implementation (see Section 6), so trust none without
      reproduction.

## 11. The full, ready-to-paste implementation prompt

`docs/CONSTITUTION.md` Section 3's preamble, verbatim, followed by the
spec above — sent identically to OpenCode and FreeBuff, per the
two-implementer model:

```
You are implementing a piece of Terrium, a scientific simulation engine
for teaching labs. Before you write any code, internalize these
non-negotiable standards — they exist because each one was learned from a
real bug in this exact codebase, not as generic best practice:

1. Every numerical claim you implement must be checked, in a test, against
   an exact closed-form solution, a known-correct independent solver, or a
   physical invariant. "The output looks like a reasonable curve" is not
   verification and will be rejected in review.

2. Distinguish physically-impossible parameters (reject with ok=False,
   raise ModelBuildError, never simulate) from physically-possible-but-
   implausible parameters (ok=True, flagged=True, flag_reason set,
   simulation still runs). Use exactly these field names. Do not collapse
   this distinction in either direction.

3. Before writing any simulation logic, explicitly state whether this
   domain is continuous-time (belongs in the antimony -> SBML -> roadrunner
   pipeline) or discrete (belongs as a direct Python recurrence, no ODE
   solver). Do not default to whichever pattern the last domain used
   without checking it's actually correct for this domain's physics.

4. If this domain shares any constraint (a bound, a unit, a name) with
   another part of the system, that sync must be enforced by an executable
   test that would fail if the two drifted apart — not just a comment.

5. Every new import needs a corresponding line added to requirements.txt
   (or package.json) in the same change. Do not leave this for CI to catch.

6. After writing your tests, perform at least one mutation test:
   deliberately break your own implementation in a specific, realistic way,
   confirm the relevant test fails, then revert and confirm the suite is
   clean again. Document exactly what you broke and which test caught it.

7. Never `pip install tellurium` (the umbrella package) or suggest it.
   Use libroadrunner, antimony, and python-libsbml directly.

8. If antimony model generation is involved, check every new
   variable/parameter name against antimony's reserved words before using
   it directly — `gamma` is one known collision, there may be others.

9. If you're making a decision that a different, equally-reasonable
   engineer might have made differently (not just a variable name, but a
   real architectural choice), flag it explicitly in your final report
   rather than silently picking one.

10. Report back explicitly: what you implemented, what closed-form/
    invariant/solver you verified against, what mutation test you ran and
    what it caught, and any judgment call you made that wasn't fully
    specified in the task. A bare "tests pass" is not sufficient.

This domain is continuous-time but does NOT use antimony/SBML/roadrunner
-- see ADR 0006 (docs/adr/0006-md-direct-python-not-roadrunner.md) for why.
Also read docs/adr/0005-rng-convention.md before starting -- the velocity
initialization step uses numpy.random.default_rng(seed) even though the
integrator itself is deterministic.

IMPORTANT: this domain ships with five pre-specified mutations, each
mapped to the test(s) expected to catch it (Section 6 of the spec
below). The mapping was corrected BEFORE implementation, after a
derivation error in an earlier draft: a wrong-but-antisymmetric force
(sign flip, r-vs-r^2 confusion) does NOT pass the energy invariant,
because the computed energy E = T + V is conserved iff F = -grad(V)
exactly -- a wrong force drifts E (a sign flip even explodes the
cluster). The invariants catch force errors only at their own
tolerance (10^-3 over 2000 steps), which is exactly why the
closed-form force-table test (Target C) exists: it pins the force law
to 10^-9 at fixed configurations, in isolation. Do not treat "energy
and momentum both look fine" as sufficient evidence the force law is
correct at precision -- and do not assume the invariants miss gross
force errors, either. Record which tests actually fire for each
mutation in your report; the prediction is a contract, not a promise.

---

DOMAIN SPEC — Molecular dynamics (Lennard-Jones cluster, velocity Verlet)
Stage: 3   Part: 2

[Sections 1 through 10 from this document, pasted in full]
```

## 13. Amendments from literature verification (2026-07-31)

A pass over this spec against the published Lennard-Jones literature.
Three amendments: one measured correction to a shipped validation bound,
one retraction of a claim made during this same pass that measurement
disproved, and one new verification target.

### 13.1 Amendment 3 — `MD_PLAUSIBLE_TEMPERATURE_HIGH = 2.0` is too permissive

**The problem.** The shipped bound declares any `temperature` in
`[0.1, 2.0]` plausible and unflagged. The flag's own message promises to
warn when "the cluster will evaporate within the run." But the published
melting range for Lennard-Jones clusters is far below the upper bound:
core melting for LJ55 occurs at roughly `T* ≈ 0.26–0.30`, with surface
melting of the Mackay overlayer beginning lower still. A bound of `2.0`
is roughly seven times the melting temperature.

**Measured, not asserted.** Rather than argue from the literature alone,
the shipped configuration (`n=108`, `ρ*=0.85`, `Δt=0.005`, 3000 steps,
`seed=42`) was re-implemented independently and run across the
temperature range, tracking the cluster's radius of gyration and
counting particles that escape beyond `3×` the initial `Rg`:

| `T*_init` | `T*_equil` | `Rg` growth | escaped |
|---|---|---|---|
| 0.1 | 0.288 | 0.93× | 0 |
| 0.4 | 0.332 | 0.95× | 0 |
| 0.6 | 0.392 | 0.97× | 0 |
| 0.8 | 0.451 | 0.98× | 0 |
| **1.0** | 0.496 | **1.60×** | **1** |
| 1.5 | 0.612 | 2.59× | 3 |
| 2.0 | 0.750 | **3.69×** | **9** |

The break is sharp and sits between `0.8` and `1.0`. At the shipped
upper bound of `2.0`, the cluster loses nine particles and nearly
quadruples in radius — it is not a cluster any more. The validation
contract currently certifies that state as plausible and unflagged,
which is precisely the failure the `ok`/`flagged` distinction exists to
prevent.

**Recommendation:** `MD_PLAUSIBLE_TEMPERATURE_HIGH = 0.8` — the highest
value measured to leave the cluster fully intact. `1.0` is defensible as
a looser alternative but already shows evaporation onset. This is a
one-constant change plus its test; it is *not* urgent enough to justify
re-running the whole domain, and it does not invalidate any existing
test result (Target A's working temperature is unaffected — see 13.2).

### 13.2 Amendment 4 — retraction: `temperature=0.4` in Target A is fine

Honesty about a wrong call made during this same pass. On first reading
the published melting range (`T* ≈ 0.26–0.30`), the conclusion drawn was
that Target A's `temperature=0.4` is above melting and would evaporate
the cluster mid-run — and that Part 1's earlier `T* = 0.3–0.5`
suggestion was therefore an error to correct.

Measurement disproved that. At `T*_init = 0.4` the cluster is stable:
`Rg` growth `0.95×`, zero escapes. The reasoning missed that `T*_init`
is not the equilibrated temperature — the fcc lattice at `ρ* = 0.85` is
not at the relaxed potential minimum, so kinetic and potential energy
redistribute during the first relaxation. The measured relationship is
not a simple halving in either direction: at `T*_init = 0.1` the
equilibrated `T*_equil = 0.288` (*higher* than the initial value, as
excess lattice potential energy converts to kinetic), while at
`T*_init = 2.0` it is `0.750` (much lower). **Target A's parameters
stand unchanged.** No test needs to move.

Two things worth keeping from this: the published melting temperature
applies to `T*_equil`, not `T*_init`, and the two are not interchangeable
— a distinction the spec should state wherever it quotes a temperature.
And the general lesson, which is this project's own standing rule: a
literature value plus a plausible-sounding inference is not a finding
until it is measured.

### 13.3 Amendment 5 — new Target E: published cluster global-minimum energies

**The gap.** Every current target (A, B, C, D) is either an invariant, a
scaling law, or a self-consistency check. None compares Terrium's output
to an absolute number that Terrium did not itself produce. The
Lennard-Jones literature supplies exactly that, freely, and using it
costs nothing.

**Target E — potential energy of known LJ cluster global minima.**
Evaluate the potential-energy function on a known global-minimum
geometry and compare to the published value:

| `N` | Published `E/ε` | Tolerance | Basis |
|---|---|---|---|
| 2 | `-1.000000` | `1e-12` | analytic: one pair at `r_min` |
| 3 | `-3.000000` | `1e-12` | analytic: 3 pairs, equilateral triangle, all at `r_min` |
| 4 | `-6.000000` | `1e-12` | analytic: 6 pairs, regular tetrahedron, all at `r_min` |
| 13 | `-44.326801` | `1e-6` | Hoare & Pal (1971), via Cambridge Cluster Database |

Three properties make this target unusually strong. All three were
confirmed numerically before being written here:

1. **`N = 2, 3, 4` are exact by two independent routes.** They are
   analytically derivable — a regular tetrahedron places all six pairs
   simultaneously at `r_min`, giving exactly `6 × (−ε)` — *and* they
   appear in the published table as `-1.000000`, `-3.000000`,
   `-6.000000`. Independent derivation and published value agree
   exactly. `N = 5` is the first size where geometric frustration makes
   this impossible (`-9.103852`, not `-10`), which is a useful docstring
   fact in its own right.
2. **`LJ13`'s global minimum is a *perfect* icosahedron**, so only its
   overall scale is free. It is reproducible from the golden ratio plus
   a one-dimensional golden-section scale search — **no downloaded
   coordinate file, no general-purpose optimizer, no new dependency.**
   Confirmed: `−44.326801419534` at scale `0.568756044521143` against
   the published `−44.326801`; the `4.2e-07` residual is entirely the
   published table's six-decimal rounding, which is why the tolerance is
   `1e-6` and not tighter.
3. **The structure carries a checkable physical signature.** In the
   relaxed LJ13 icosahedron the twelve centre-to-shell distances are
   *compressed* to `≈ 1.0818 σ` (below `r_min = 1.1225 σ`) while the
   nearest shell-to-shell distances are *stretched* to `≈ 1.1375 σ`
   (above it). That frustration is real physics, and asserting it catches
   a "scale applied to the wrong quantity" bug that a total-energy check
   alone could absorb.

**Scope note, per this stage's own discipline:** Target E needs a
geometry constructor that the current spec does not have (Section 4
ships `_fcc_lattice_positions` only). That is an addition to the
deliverables, stated here rather than slipped in silently — the exact
failure mode Stage 2's audit caught. The one-dimensional scale search
must be hand-written in the engine module; `scipy` stays a test-only
dependency and the engine's runtime surface stays `numpy` (Rule 5).

### 13.4 References

Verified directly during this pass:

- **Cambridge Cluster Database**, table of Lennard-Jones global minima
  for `N ≤ 150` (D. J. Wales, J. P. K. Doye *et al.*),
  <https://www-wales.ch.cam.ac.uk/~jon/structures/LJ/tables.150.html>
  — source of `LJ13 = −44.326801`, and of the `LJ2/3/4` values that
  independently confirm the analytic derivation.
- **Hoare, M. R. & Pal, P.** (1971), *Adv. Phys.* **20**, 161 — credited
  by the database above as the first report of the `LJ13` and `LJ55`
  icosahedral global minima.
- **Swope, W. C., Andersen, H. C., Berens, P. H. & Wilson, K. R.**
  (1982), *J. Chem. Phys.* **76**, 637–649 — the original publication of
  the velocity Verlet algorithm (in the Appendix). This is the primary
  citation for Section 2's integrator.
- **LJ cluster melting**, `T* ≈ 0.26–0.30` core melting for LJ55 with
  surface melting lower — Cambridge/Doye cluster-thermodynamics
  literature. Basis for Amendment 3.

Cited from the database's own reference key, not independently
retrieved: Gomez & Romero (1994); Pillardy & Piela, *J. Phys. Chem.*
**99**, 11805 (1995); Doye, Wales & Berry, *J. Chem. Phys.* **103**,
4234 (1995) — for the `LJ38` truncated-octahedron minimum
(`−173.928427`), not used by any target above.

Background, not load-bearing: Verlet, L. (1967), *Phys. Rev.* **159**,
98 — the original Verlet integrator.

## 12. What Part 3 covers

Part 3 is the implementation step: this exact prompt sent to OpenCode and
FreeBuff independently, following the same procedure Stage 2 used —
check whether any implementation or test-file work has already landed
externally in parallel (as happened repeatedly in Stage 2) before
assuming both implementers are starting from a clean slate.
