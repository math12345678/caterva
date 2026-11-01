# ADR 0022: Three new ODE oscillator domains — Lotka-Volterra, cell cycle, repressilator

**Status:** Accepted

**Date:** 2026-08-09

**Relates to:** ADR 0004 (gamma reserved keyword), ADR 0005 (RNG convention),
ADR 0007 (engine/application boundary contract), ADR 0009 (Gillespie SSA),
ADR 0023 (the Lotka-Volterra default-transposition bug this ADR's defaults
already reflect the fix for)

**Note on ADR 0023's "carried forward" section:** it flagged that
`cell_cycle_oscillator` and `repressilator` shipped with no verification of
any kind, the same way the original Lotka-Volterra defaults had. Closed
directly by this ADR's own Verification section --
`test_cell_cycle_oscillator_correctness.py` and
`test_repressilator_correctness.py` exist, each with an independent-integrator
cross-check and the domain-specific qualitative signatures described below.

## Context

Three domains -- `lotka_volterra`, `cell_cycle_oscillator`, `repressilator`
-- appeared in `domain-literature.ts` (citations), `schemas.ts` (request
shape), and `catervaRunner.ts`/`caterva_runner.py` (API glue calling
`caterva_engine.simulate_lotka_volterra` /
`simulate_cell_cycle_oscillator` / `simulate_repressilator`) before any of
those three functions existed in the engine. The application layer had
been built ahead of the science it was meant to call, in the middle of
concurrent work from multiple agents on this codebase -- confirmed by
`grep`, which found no `simulate_lotka_volterra` etc. anywhere under
`caterva/`.

This ADR is the science layer those call sites needed, plus the closure of
the API-layer wiring, which itself had partially regressed (the TypeScript
`SimulationDomain` union and `caterva_runner.py`'s `DISPATCH` table were
each found, independently, in a state missing one or more of these three
domains, requiring re-synchronization -- the same class of drift ADR 0007's
boundary-contract test exists to catch, and does catch: adding these
domains without updating both sides of the contract fails
`caterva/tests/test_boundary_contract.py` immediately).

Two of the three domains needed literature verification before any code
was written. Reconstructing "how these oscillators tend to work" from
general knowledge and attributing it to a named 1991/2000 paper would be a
worse violation of this project's literature rule than shipping nothing:
a citation next to the wrong equations is actively misleading in a way an
absent citation is not. The exact equations and standard parameter values
were obtained from the curated BioModels SBML for both papers
(BIOMD0000000005/6 for Tyson 1991, BIOMD0000000012 for Elowitz & Leibler
2000 -- each SBML's `<annotation>` links directly to the paper's PubMed
ID) rather than reconstructed from memory, and cross-checked against a
university course exercise built directly around the Elowitz & Leibler
paper (Cornell Physics 7682) for the specific parameter point (Fig 2b's
"X") the paper itself identifies as oscillatory.

## Decision

**1. Lotka-Volterra** (Lotka 1925, *Elements of Physical Biology*; Volterra
1926, *Variations and fluctuations of the number of individuals in animal
species living together*, Nature 118:558-560):

    dP/dt = alpha*P - beta*P*V
    dV/dt = gamma*P*V - delta*V

Built via Antimony's direct rate-rule syntax (`P' = ...`), not a
mass-action reaction network -- there is no chemical species here, just
two coupled populations, so a rate rule is the faithful translation. The
`gamma` symbol collides with Antimony's built-in gamma function (the same
collision ADR 0004 documents for the SIR recovery rate), so the generated
model emits it as `gamma_rate`; the Python API still takes `gamma`.

Caller-supplied: `alpha, beta, gamma, delta, p0, v0` (all six, unlike the
other two domains below). `validate_lotka_volterra_params` rejects a zero
or negative rate constant (each collapses part of the defining
predator-prey feedback) and flags implausible-scale values or a zero
starting population, following the ok/flagged split ADR 0010 established.

**Defaults, and a bug found and fixed in them.** The shipped default
parameter set is `alpha=1.1, beta=0.4, gamma=0.1, delta=0.4, p0=10, v0=5`.
An earlier version of this default set (written concurrently with this
ADR, before its own test suite existed) transposed gamma and delta
(`gamma=0.4, delta=0.1`). The system has an exact first integral,

    H(P, V) = gamma*P - delta*ln(P) + beta*V - alpha*ln(V)

conserved for any true solution (every term of dH/dt cancels
algebraically -- this is a property of the rate laws, not of any specific
trajectory, and is independent of this codebase). With the transposed
defaults, the coexistence fixed point `(delta/gamma, alpha/beta)` sits at
`(0.25, 2.75)` while the prey starts at 10 -- a 40x excursion from
equilibrium. Integrating that orbit drove the prey population to
`-5.9e-11` (a negative population, not representable by the model) and
drifted the exactly-conserved H by 49%: the numerical trajectory had
stopped being a solution of the stated system. Biologically, the
transposed pair also described predators converting prey into offspring
four times faster than they die, the reverse of the ordinary case (and of
Volterra's own figures). Both were independently reproduced before the
fix: `python3 -c` with the transposed defaults reproduces the negative
population and the 49% drift exactly.

**2. Cell cycle oscillator** (Tyson 1991, "Modeling the cell division
cycle: cdc2 and cyclin interactions", PNAS 88(16):7328-7332, DOI
10.1073/pnas.88.16.7328). The paper presents a 6-variable mechanistic
model and Tyson's own 2-variable relaxation-oscillator reduction of it;
the reduction is used here (simpler, still the paper's own derivation, not
a third party's simplification):

    du/dt = k4*(v - u)*(alpha + u^2) - k6*u
    dv/dt = kappa - k6*u
    alpha = k4prime / k4

`u` = [active MPF]/[CT], `v` = ([cyclin]+[preMPF]+[active MPF])/[CT].
Standard oscillatory parameter set (identical across both curated
BioModels encodings): `kappa=0.015, k6=1, k4=180, k4prime=0.018`, giving
`alpha=0.0001`. No caller-supplied kinetic parameters -- every rate
constant is the literature's own standard set, the same treatment
`molecular_dynamics` gives its Lennard-Jones constants.

**3. Repressilator** (Elowitz & Leibler 2000, "A synthetic oscillatory
network of transcriptional regulators", Nature 403:335-338, DOI
10.1038/35002125), the "deterministic, continuous approximation" from
p.337 (three genes cyclically repressing, lacI -| tetR -| cI -| lacI):

    dm_i/dt = -m_i + alpha/(1 + p_j^n) + alpha0     (j represses i)
    dp_i/dt = -beta*(p_i - m_i)

Parameters `alpha=216, alpha0=0.216 (alpha0/alpha=0.001), beta=5, n=2` are
the point the paper's own Figure 2b identifies as producing spontaneous
oscillation. Initial conditions are deliberately asymmetric
(`m=(0,0,0), p=(1,2,3)`): the fully symmetric state is an unstable fixed
point of the deterministic system, not part of the reported dynamics, so
starting there would not show the oscillation the model demonstrates
(stochastic initial protein numbers played the same symmetry-breaking role
in the original experimental system).

All three are built via Antimony rate-rule syntax and integrated through
the existing `simulate_sbml` (roadrunner/CVODE) -- no changes to the
solver path itself were needed; rate-rule-declared quantities appear in
`runner.selections` and integrate identically to reaction-declared
species, confirmed directly before committing to the approach.

**ADR 0005 (RNG convention) scope.** `cell_cycle_oscillator` and
`repressilator` accept a `seed` parameter for call-signature symmetry with
the stochastic domains, but never use it: both are deterministic ODE
systems with no sampling anywhere. `lotka_volterra` has no `seed`
parameter at all, for the same reason. All three are listed in
`scripts/check_rng_convention.py`'s `EXCLUDED_FNS` with that
justification, rather than silently failing the AST-based compliance
check `caterva/tests/test_rng_convention.py` runs in CI.

## Verification

- **Lotka-Volterra:** the conserved quantity H held to `<1e-5` relative
  drift on two independent orbits (vs. 49% under the transposed-default
  bug); the coexistence fixed point is exactly stationary
  (`rtol=1e-6`); the linearised small-oscillation period
  `T = 2*pi/sqrt(alpha*delta)` matched the integrated period to 2%; an
  independent integrator (`scipy.integrate.solve_ivp`, sharing no code
  with roadrunner) matched the engine's trajectory to `rtol=1e-4`;
  populations stay strictly positive over a 40-time-unit run; a
  zero-predator initial condition reproduces the closed-form
  `P(t) = p0*exp(alpha*t)` exactly. `caterva/tests/test_lotka_volterra_correctness.py`.
- **Cell cycle oscillator:** matched an independent `scipy.integrate.solve_ivp`
  run of the literal two equations to `rtol=1e-3`; `u, v` stay
  non-negative; the trajectory shows repeated MPF spikes rather than
  settling to either of Tyson's two non-oscillatory steady states; the
  standard parameter set and the `alpha = k4prime/k4` relationship are
  pinned directly; deterministic reproducibility confirmed (bit-identical
  output across different `seed` values, since none is used).
  `caterva/tests/test_cell_cycle_oscillator_correctness.py`.
- **Repressilator:** matched an independent `scipy.integrate.solve_ivp` run
  of the literal six equations to `rtol=1e-3`; all six species stay
  non-negative (provable directly from each RHS at its own zero boundary);
  each protein shows at least 3 sustained oscillation peaks over the
  default window; the three proteins' peaks are measurably out of phase
  with each other (the repressilator's defining qualitative signature,
  distinct from three independent copies of the same oscillator running
  in sync) rather than near-zero or near-full-period offset; the standard
  parameter set is pinned directly; deterministic reproducibility
  confirmed. `caterva/tests/test_repressilator_correctness.py`.
- `caterva/tests/test_boundary_contract.py` updated (engine `__all__`
  and runner `DISPATCH` expected-set assertions) and passing: all three
  domains are dispatched, none are missing from either side.
- Full suite: 1237/1246 Python passing (the 9 failures are the
  long-documented, unrelated `stdpopsim` sandbox gap -- see ADR 0021 §
  "Closed by this ADR" for why that gap no longer hides defects); 404/404
  TypeScript (vitest); `tsc --noEmit -p .` clean.

## Consequences

**Easier.** A fourth ODE oscillator domain, if one is ever added, has a
worked pattern to follow: rate-rule Antimony (not reaction syntax) for a
system with no real chemical species, literature-sourced constants baked
in when the domain takes no caller-tunable kinetics, and independent
(non-solver) verification -- a conserved quantity, a fixed point, an
independent integrator, or a qualitative signature specific to the model
-- rather than only comparing the engine against itself.

**Harder.** Nothing new; the three `run_*` functions and `DISPATCH`
entries in `caterva_runner.py` follow the same shape as every other
domain.

**A pattern worth naming.** This is the second time in this project a
transposed pair of similarly-named constants produced a numerically
"successful" run (no exception, no NaN, a plausible-looking oscillating
plot) that was nonetheless not a solution of the stated model -- the first
was ADR 0021's STRENDA-governance bug. Both were caught by a property
derivable independently of the code under test (there, "does
`validateParameterProvenance`'s own adjacent rule agree with the
helper's behavior"; here, "does the model's own algebraic invariant hold
along the integrated trajectory") rather than by the domain's own
plausibility bounds, which had nothing to say about either bug -- the
values were individually well within range, just transposed.

## References

- Lotka, A.J. (1925). *Elements of Physical Biology*. Williams & Wilkins.
- Volterra, V. (1926). "Variations and fluctuations of the number of
  individuals in animal species living together." *Nature* 118, 558-560.
- Tyson, J.J. (1991). "Modeling the cell division cycle: cdc2 and cyclin
  interactions." *PNAS* 88(16), 7328-7332. DOI 10.1073/pnas.88.16.7328.
  Curated model: BioModels BIOMD0000000005 (6-variable),
  BIOMD0000000006 (2-variable reduction used here).
- Elowitz, M.B., Leibler, S. (2000). "A synthetic oscillatory network of
  transcriptional regulators." *Nature* 403, 335-338. DOI
  10.1038/35002125. Curated model: BioModels BIOMD0000000012. Parameter
  point cross-checked against Cornell Physics 7682 (Myers/Sethna/Mueller),
  "Simple Repressilator" exercise, built directly around this paper.
- ADR 0004 -- the same Antimony `gamma` keyword collision this ADR's
  Lotka-Volterra model hits again.
- ADR 0005 -- the RNG convention `cell_cycle_oscillator` and
  `repressilator` are exempted from, and why.
- ADR 0007 -- the engine/application boundary contract this ADR's wiring
  had to re-satisfy.
