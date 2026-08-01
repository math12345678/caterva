# Stage 3, Part 1 — Domain Choice and Grounding

Stage 3 of 100. 97 remain after this one closes.

## 1. Domain: molecular dynamics setup

The standing candidate since Stage 2 Part 1, and the one Stage 2's
closing report (Part 5) pointed to explicitly: everything built so far
(Michaelis-Menten, SIR, SEIR via antimony/roadrunner; PCR, Monte Carlo,
Wright-Fisher as direct Python) has landed on one of two patterns —
continuous-time ODE or discrete-stochastic recurrence. Neither is
molecular dynamics. MD is a different kind of continuous-time system:
not a small system of coupled ODEs solved by a general integrator, but
Newtonian mechanics over many interacting particles, governed by a force
field, integrated with a scheme built for that specific structure
(velocity Verlet, not an adaptive-step general ODE solver like
roadrunner uses). This is a genuine test of Rule 3 (continuous vs.
discrete is a decision, made explicitly, per domain) from a new angle:
it's continuous, but the antimony → SBML → roadrunner pipeline is the
wrong tool for it, for reasons worth stating plainly rather than
discovering mid-implementation.

## 2. Why antimony/roadrunner is the wrong engine here

Antimony/SBML model compartments, species, and reactions — the right
abstraction for a handful of coupled concentration ODEs (kinetics,
epidemiology). MD's state is positions and velocities for N particles in
3D, evolved under pairwise forces (Lennard-Jones, or a simple harmonic
bond model for a teaching-scale system), with a symplectic integrator
chosen specifically because it conserves energy over long trajectories —
a property a general-purpose adaptive-step ODE solver does not
guarantee, and actively working against it (adaptive step sizing trades
energy conservation for local error control) would be the deterministic
domain equivalent of the population-genetics fixation problem just found
in Stage 2: a subtly wrong tool producing plausible-looking but
incorrect long-run behavior. This is a discrete-time domain in the same
category as PCR and Wright-Fisher: direct Python, a fixed integration
scheme, no general solver.

This decision is recorded as its own ADR (0006, drafted in this part),
following ADR 0002's precedent: PCR refused the ODE pipeline because the
domain's structure made it the wrong tool. MD is the first *continuous*
domain to refuse it for the same reason — which is exactly why Rule 3's
decision has to be made per domain, not once per pipeline.

## 3. The actual science, grounded before any spec gets written

### 3.1 The model: N particles in 3D, Lennard-Jones pairs, velocity Verlet

State: positions $\mathbf{x}_i \in \mathbb{R}^3$ and velocities
$\mathbf{v}_i$ for $i = 1 \dots N$, mass $m$. Pairwise Lennard-Jones
potential between particles at separation $r$:

$$V(r) = 4\varepsilon\left[\left(\frac{\sigma}{r}\right)^{12} - \left(\frac{\sigma}{r}\right)^{6}\right]$$

with the classic implementation form of the force (a central,
pairwise-antisymmetric vector force, $\mathbf{F}_{ij} = -\mathbf{F}_{ji}$):

$$\mathbf{F}_{ij} = \frac{24\varepsilon}{\sigma^2}\left[2\left(\frac{\sigma}{r}\right)^{14} - \left(\frac{\sigma}{r}\right)^{8}\right]\mathbf{r}_{ij}$$

Two closed-form facts worth exploiting in the verification contract:
the force is exactly zero at the equilibrium separation $r = 2^{1/6}\sigma$
(minimum of $V$), and attractive/repulsive beyond/below it. A
closed-form force-table test at a few fixed configurations pins the
force function itself — see Section 3.3 — because the two global
invariants below *cannot* distinguish a wrong force from a right one.

Integration is velocity Verlet (positions and velocities staggered by
half a step):

1. $\mathbf{x}(t+\Delta t) = \mathbf{x}(t) + \mathbf{v}(t)\Delta t + \tfrac{1}{2}\mathbf{a}(t)\Delta t^2$
2. $\mathbf{v}(t+\tfrac{\Delta t}{2}) = \mathbf{v}(t) + \tfrac{1}{2}\mathbf{a}(t)\Delta t$
3. $\mathbf{a}(t+\Delta t) = \mathbf{F}(\mathbf{x}(t+\Delta t))/m$
4. $\mathbf{v}(t+\Delta t) = \mathbf{v}(t+\tfrac{\Delta t}{2}) + \tfrac{1}{2}\mathbf{a}(t+\Delta t)\Delta t$

Symplectic and time-reversible; global error $O(\Delta t^2)$; energy
error bounded and oscillating, scaling $O(\Delta t^2)$ in amplitude —
not growing with simulation length.

### 3.2 The two invariants, and what each one can and cannot detect

The brief named two verification targets. Both are right, and both need
their *precise* requirement stated, because one of them is subtler than
it looks and both have detection blind spots that determine what else
the verification contract must contain:

**Invariant 1 — total energy conserved up to step-size-scaled error.**
Correct as stated, with one correction to the brief's own framing: it
claims "a naive Euler-Cromer or explicit-Euler scheme would drift in
energy monotonically." Explicit (forward) Euler does — its energy error
grows monotonically, unboundedly. But **Euler-Cromer (semi-implicit
Euler) is also symplectic**: its energy error is bounded and oscillating
too, exactly like Verlet's — just one order worse ($O(\Delta t)$, vs
Verlet's $O(\Delta t^2)$). A drift-vs-fluctuation test alone therefore
cannot tell velocity Verlet from Euler-Cromer. The test that can: halve
$\Delta t$ and require the energy-error amplitude to shrink by a factor
of $\approx 4$ (second order), not $\approx 2$ (first order). Part 2's
spec must include this scaling assertion, or the invariant as written
accepts a subtly wrong integrator — the exact failure mode this brief
was written to avoid.

**Invariant 2 — total momentum conserved.** True, and exact to machine
precision, for *any* pairwise central-force scheme (Newton's third law,
$\mathbf{F}_{ij} = -\mathbf{F}_{ji}$, cancels pairwise), *any*
integrator, *any* step size. Its strength is that it's cheap and
continuous; its blind spot is that it tests only the force *loop* —
pairing (every $i<j$ once), antisymmetry, no self-interaction — and the
initial conditions. It cannot detect a wrong-but-still-antisymmetric
force (sign flip, wrong power law) — momentum's antisymmetry is
independent of the force law's correctness (see Section 3.3 for what
the energy invariant can and cannot catch instead). And it has one hard
scope consequence the brief didn't
resolve: **a reflecting box breaks momentum conservation** (walls exert
impulses on the system). The brief lists "periodic or reflecting box" as
the starting container *and* momentum conservation as invariant #2 —
those two cannot hold simultaneously. Since periodic boundary conditions
are out of scope, the primary test system must be **unbounded**: a
compact Lennard-Jones cluster (e.g., a few hundred particles on an fcc
lattice), where both invariants hold exactly. A box mode, if any, waives
invariant #2 and inherits its own wall-handling energy-error sources.

**Initial conditions are part of the contract.** A common setup:
particles on an fcc lattice (no overlap — the flagged "particles start
overlapping" case in the brief is a real failure mode of random
placement), velocities sampled from a Maxwell–Boltzmann distribution at
a target temperature $T^*$, with the center-of-mass velocity subtracted
(else invariant #2 fails at $t=0$). The Maxwell–Boltzmann sampling is
stochastic → ADR 0005's `numpy.random.default_rng(seed)` convention
applies to the *initialization step* even though the integrator itself
is deterministic — this is a genuine new instance of a shared
constraint (Rule 4), flagged in Section 4.

### 3.3 Why the verification contract needs a third piece: the force-table test

A first-pass intuition says a wrong-but-antisymmetric force (sign
flipped, so particles accelerate *up* the repulsive wall; or an $r$ vs
$r^2$ confusion in the denominator) would "integrate a different
system" and sail through the invariants. The corrected statement,
derived before implementation: the energy invariant *does* catch gross
force errors, because the computed energy is always $E = T + V$ with
the *true* potential, and

$$\frac{dE}{dt} = \sum_i \mathbf{v}_i \cdot \left(\mathbf{F}_i^{\text{(implemented)}} + \nabla_i V\right)$$

so $E$ is conserved along a trajectory if and only if the implemented
force equals $-\nabla V$ exactly. A sign-flipped force conserves
$T - V$, not $T + V$: the computed energy drifts (and a sign-flipped
cluster is unstable to explosion). An $r$ vs $r^2$ confusion likewise
breaks the identity. The blind spot is one of *precision and
localization*, not principle: a force wrong by a fraction of a percent
drifts $E$ slowly enough to sit under a $10^{-3}$ tolerance over a
finite 2000-step run, and a force bug buried inside an integrated
trajectory is diagnosed only by bisection. The closed-form force table
pins the force law to $10^{-9}$ at fixed configurations, in isolation:
$F = 0$ at $r = 2^{1/6}\sigma$ (equilibrium), known magnitude and
direction at, say, $r = 1.5\sigma$ (attractive) and $r = 0.9\sigma$
(repulsive). This is the same Rule 1 standard used everywhere else:
closed-form ground truth, not "the trajectory looks plausible." The
division of labor, stated plainly for Part 2: the **force-table test
owns the force function at closed-form precision**; the **energy
invariant owns the integration loop and doubles as a gross-error guard
on the force law**; the **momentum invariant owns the force loop's
antisymmetry and the initial conditions**. Each test catches what the
others cannot, and the mutation contract in Part 2 records which tests
actually fire for each mutation — not which ones we predicted.

### 3.4 Units and plausible numbers (targets for Part 2/3 calibration, not promises)

Reduced units throughout ($\varepsilon = \sigma = m = 1$) — the
teaching-standard LJ convention. Target values for the verification
contract, to be locked by calibration in Part 3: $\Delta t^* \approx
0.005$, $T^* \approx 0.3$–$0.5$ (solid-cluster regime, so the cluster
doesn't evaporate over the run), $N \approx 125$–$256$ (fcc lattice),
$10^4$ steps. Energy fluctuation amplitude $|\Delta E|/E$ on the order
of $10^{-4}$ at $\Delta t^* = 0.005$; halving the step gives $\approx
\times 4$ smaller amplitude (the order check of Section 3.2). Momentum
invariant: $|\sum \mathbf{p}| / \sum |\mathbf{p}_i| \lesssim 10^{-12}$
(machine precision accumulation) at all times.

## 4. Applying the nine constitution rules to this domain

**Rule 1 (independent verification)** — satisfied by Section 3: two
exact invariants (one of which, momentum, is exact to machine
precision; energy is bounded-fluctuating with a closed-form $\Delta
t^2$ scaling law) plus a closed-form force table. This is a stronger
ground truth than Monte Carlo's convergence claims: nothing here
depends on "close enough" comparisons to a reference implementation.

**Rule 2 (`ok`/`flagged` contract)** — genuinely new plausibility
questions, none answered by existing bounds: what is an implausible
timestep for a teaching lab ($\Delta t^*$ above $\sim 0.05$ risks the
$r^{-12}$ wall — particles overlapping → explosion), what is an
implausible temperature ($T^*$ so high the cluster evaporates
instantly, so low nothing moves), what is a degenerate particle count
($N=1$: no pairs, no forces — valid but useless; $N \le 0$:
`ok=False`), and the overlap rule if a box mode exists. Part 2 must
decide each bound explicitly.

**Rule 3 (continuous vs. discrete, explicit)** — the decision this
part exists to make: continuous-time, but *not* through the antimony →
SBML → roadrunner pipeline. Same category as PCR and Wright-Fisher
(direct Python), but the first *continuous* domain in that category —
ADR 0002 refused the pipeline for a discrete process; this stage
refuses it for a continuous one whose structure (pairwise forces,
symplectic integration, energy conservation as the correctness
criterion) is incompatible with a general adaptive-step solver. ADR
0006 records this.

**Rule 4 (shared constraints enforced by test)** — two instances. (1)
ADR 0005's RNG convention: MD's integrator is deterministic, but its
velocity initialization is stochastic, so the public API takes
`seed: int | None = None` and uses `numpy.random.default_rng(seed)` —
the existing `scripts/check_rng_convention.py` should now cover this
domain too. (2) The "no umbrella package" constraint applies directly
here (Rule 7's checklist item, *not* silent): an MD *engine* library is
the umbrella-package temptation this domain has that the others didn't.

**Rule 5 (dependency declarations)** — `numpy` only, already declared;
nothing else is needed for O(N²) pairwise forces on teaching scale.
This stays in the spec as an explicit statement, not an assumption.

**Rule 6 (mutation testing)** — pre-specified, in Part 2's spec, per
the Stage 2 improvement: (a) **velocity Verlet → Euler-Cromer
substitution** — caught *only* by the $\times 4$ halving-step scaling
assertion, not by drift-vs-fluctuation; (b) **force sign flip** — the
computed energy $E = T + V$ is conserved iff $F = -\nabla V$ exactly
(Section 3.3), so this drifts/explodes the energy and Target A catches
it at gross-error sensitivity — but Target C pins it at closed-form
precision in isolation, which is where the real diagnostic value sits;
(c) **missing pair direction** (force
computed for $j>i$ but only added once, or self-interaction included)
— caught by momentum; (d) **COM-velocity not removed at init** —
caught by momentum at $t=0$; (e) **$r$ vs $r^2$ confusion** in the
force denominator — drifts the energy (Target A catches it) and the
force table catches it at precision. The predicted mapping is a
*contract*, not a promise: Part 2's implementation records which tests
actually fired for each mutation, the way Stage 2's mutation docstring
entries did.

**Rule 7 (no umbrella `tellurium` package)** — not applicable, but
noted explicitly per the checklist: no antimony/roadrunner/SBML at all.
The MD-shaped temptation is an external *engine* (OpenMM, LAMMPS) —
explicitly out of scope, Section 6.

**Rule 8 (ADRs for architecturally significant decisions)** — ADR 0006
drafted in this part (the decision this part is about), on ADR 0002's
precedent. No further ADR is anticipated in Part 2 unless
implementation surfaces one (then it's written *at the time*, per this
brief's own audit-finding instruction).

**Rule 9 (conservative defaults, judgment calls flagged)** — three
judgment calls made here explicitly: (1) single-component LJ only (no
bonded terms, no mixtures) in the core spec; (2) unbounded cluster as
the primary test system, box mode deferred (Section 3.2's momentum
argument — this is a *recommendation carried to Part 2*, not a silent
override of the brief's "reflecting or unbounded" wording); (3) reduced
units, with $T^*$ in the solid regime so the cluster survives the run.

## 5. What's genuinely new here versus Stages 1–2

Already settled, inherited without re-litigation: the
`ParameterValidation`/`SimulationResult` contract shape, the
direct-Python-bypasses-antimony pattern (now with a *continuous*
precedent, not just discrete), the RNG convention, the mutation-test
discipline, the five-part stage structure. Genuinely new: the first
deterministic-core domain (stochastic only at initialization — a new
shape for ADR 0005's scope), the first verification target that is a
*scaling law* (energy-error $\propto \Delta t^2$) rather than a
closed-form value, the first continuous domain with a mandatory
"wrong tool" argument on record, and the first domain where the
invariant pair is load-bearing for *different* things (energy owns the
integrator; momentum owns the force loop and initial conditions;
neither owns the force function — the force table does).

## 6. Explicitly out-of-scope boundary — written tighter this time

Stage 2's audit just found that an implicit, loosely-enforced
out-of-scope boundary gets outgrown quietly. Stating this one more
narrowly and more operationally:

Out of scope for Stage 3: periodic boundary conditions with
minimum-image convention (the primary system is an **unbounded
cluster** — the box question is Section 7's open item 1, resolved in
Part 2 with a stated reason either way), neighbor lists / cell lists
for performance (a small teaching-scale N doesn't need O(N) force
calculation, only O(N²) pairwise, which is fine), thermostats or
barostats (NVE only — no temperature or pressure coupling), bonded
potentials beyond a simple harmonic option (no angle or dihedral
terms), multi-species mixtures and electrostatics/charges (single-
component LJ only), rigid-body or constraint dynamics, any external MD
engine (OpenMM, LAMMPS, etc. — direct Python only, same reasoning as
ADR 0001's antimony-umbrella-package decision), and GPU/vectorization
concerns beyond straightforward numpy. If any of these turns out to be
needed mid-implementation, the correct action is an ADR or a spec
amendment written *at the time*, matching this stage's own audit
finding — not silence until the next audit catches it.

## 7. What Part 2 has to resolve, inherited from this part

Four open items, carried forward explicitly rather than left implicit
for Part 2's spec to silently paper over:

1. **Box mode: in or out.** Recommendation: unbounded cluster only in
   Part 2's core spec; reflecting-box mode deferred. Stated reason:
   walls break invariant #2, and the wall-handling logic has its own
   energy-error sources. If Part 2 keeps a box mode anyway, it must
   state which invariants apply per mode and which tolerances loosen.
2. **Exact `ok`/`flagged` bounds** (Rule 2): $\Delta t^*$ flag
   threshold (instability/explosion risk), $T^*$ range for velocity
   sampling, $N$ range, and the overlap rule for any container mode.
3. **The verification contract's three parts, with numerical
   tolerances**: energy fluctuation amplitude + the mandatory
   halving-step $\times 4$ order assertion (the *only* test that
   distinguishes velocity Verlet from Euler-Cromer); momentum
   machine-precision bound; the closed-form force-table test at
   $r = 2^{1/6}\sigma$ (zero force), $r = 1.5\sigma$ (attractive),
   $r = 0.9\sigma$ (repulsive) — mandatory because the energy
   invariant's gross-error sensitivity (Section 3.3) can miss slow,
   small force deviations that a 2000-step run under $10^{-3}$ sits on
   top of, and the force table pins the law to $10^{-9}$ in isolation.
4. **The pre-specified mutation list** (Rule 6, Section 4): the five
   mutations named there, each mapped to the test(s) expected to catch
   it — so the spec ships with its mutation contract written down, the
   Stage 2 process improvement applied again. The implementation
   records which tests actually fired, correcting the prediction where
   it's wrong (it already corrected one: the force-blind-spot claim of
   Section 3.3 was itself wrong and was fixed *before* implementation,
   not after).

Part 2 writes the full 10-field domain spec using the template already
fixed in `docs/CONSTITUTION.md` Section 4, resolving all four of the
above, ready to hand to OpenCode and FreeBuff exactly the way Stage 2's
Part 2 did — including the ready-to-paste implementation prompt for
both implementers.
