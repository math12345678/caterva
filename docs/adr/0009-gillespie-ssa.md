# ADR 0009: Gillespie SSA domain — single first-order decay reaction (A → B)

**Status:** Accepted

## Context

Stage 6 adds the first stochastic *chemical* kinetics domain to Terrium
(the existing discrete domains — Monte Carlo, Wright-Fisher — are
statistical/population models, not reaction kinetics). The Gillespie
stochastic simulation algorithm (SSA), also called the exact stochastic
simulation algorithm or "Gillespie algorithm", is the canonical way to
simulate well-mixed chemical reaction systems exactly: instead of solving
the chemical master equation analytically, it samples the next reaction
event and its waiting time from the propensity function of each reaction.

The full SSA generalizes to an arbitrary reaction network. For a teaching
lab, the first SSA domain must choose a model. Two decisions are made
here: the reaction system and the algorithm's scope.

## Decision

**Model.** The domain simulates a single irreversible first-order decay
reaction

    A → B,   rate k per molecule (propensity k·a)

with `a` the number of A molecules and `b` the number of B molecules.
This is the simplest exact SSA model with a closed-form expectation —
`E[a(t)] = a₀·e^(−kt)` — which lets tests verify the stochastic engine
against theory (the count at time t is exactly Binomial(a₀, e^(−kt)) for
this linear death chain). Conservation `a + b = a₀` holds on every row.

**Algorithm.** Gillespie's exact Direct Method:

1. At state (t, a), the total propensity is α = k·a.
2. Draw two uniform variates u₁, u₂ ∈ (0,1] (from the ADR 0005 RNG).
3. Waiting time τ = −ln(u₁)/α; the event fires (a→a−1, b→b+1).
4. Advance t += τ and repeat while t < end and a > 0.

`k = 0` (no reaction) and complete decay (`a` reaches 0 before `end`)
are handled explicitly: the simulation stops early and snaps the final
row to t = end with the remaining counts, mirroring how the ODE domains
produce their final row at `end`.

**Scope.** The domain is deliberately narrow (per the Stage 5 narrowness
decision, ADR 0008): no reversible reactions, no second-order
bimolecular reactions, no multi-species networks in this stage. The
engine function signature (`simulate_gillespie_ssa(a0, k, end, seed)`)
leaves room for a later extension (a reaction-network variant), but the
Stage 6 domain is exactly this one reaction.

**Plausibility thresholds** (flagged, not rejected — a student may
genuinely want to see the behaviour):

- `a₀ < 30` molecules → flagged: stochastic effects dominate below this
  size, so trajectories differ wildly between seeds.
- `k > 10` (per-molecule rate) → flagged: events become so dense that
  the trajectory is a random walk far from the smooth closed form.

**Runtime ceiling** (ADR 0007 runtime-limit rule): SSA cost is
O(initial population) — each event consumes one A molecule, so the
event count is bounded by a₀. The API ceiling is
`MAX_API_SSA_POPULATION = 1_000_000` molecules, far above any teaching
request and a few seconds in the engine.

**API surface.** The domain name is `gillespie_ssa`; parameters are
`a0` (initial A molecules), `k` (per-molecule rate), `end` (simulation
time), and optional `seed` (ADR 0005). Defaults in
`DOMAIN_DEFAULTS`: a0=1000, k=0.5, end=10.

## Consequences

- Students can compare the exact stochastic trajectory against the
  deterministic closed form `a₀·e^(−kt)` and the ODE result from the
  existing continuous domains — the canonical first SSA teaching
  example.
- The engine exposes `simulate_gillespie_ssa` and
  `validate_ssa_params` in `__all__`; the runner dispatches
  `gillespie_ssa` (boundary contract, ADR 0007, test-enforced).
- RNG follows ADR 0005: `seed: int | None = None` +
  `np.random.default_rng(seed)`; compliance is enforced by
  `scripts/check_rng_convention.py`, which was upgraded in Stage 6
  Part 1 to scan all Terium submodules (previously it only scanned
  the engine file, which contains no `simulate_*` definitions, so that
  check would not have caught violations in other modules).
- Flag reasons surface through the standard `ok/flagged/flagReason`
  contract to the API.
- The narrow scope means no parameters beyond a0/k/end; a future
  reaction-network extension is a new ADR.

## Amendment (Stage 7): bimolecular association A + B → C

- The engine additionally exposes `simulate_gillespie_ssa_bimolecular(a0, b0, k, end, seed=None)` with the second-order propensity `k·a·b`, the Direct Method, columns `["time","a","b","c"]`, and conservation `a+c = a0`, `b+c = b0` on every row. The same ADR 0005 RNG and endpoint-snap conventions apply; `seed=12345, a0=60, b0=40, k=0.01, end=5` is the pinned golden trajectory (first event `0.06172192003509486`, final `[5, 24, 4, 36]`, 38 rows).
- Deterministic reference for the tests (ODE limit of the same reaction): for `a0 ≠ b0`, `a(t) = (a0−b0)/(1 − (b0/a0)·e^(−k(a0−b0)t))`; for `a0 = b0`, `a(t) = a0/(1 + k·a0·t)`.
- `validate_ssa_bimolecular_params` flags (not rejects) counts below `SSA_PLAUSIBLE_MIN_POPULATION` (30) and rates above the new `SSA_BIMOLECULAR_PLAUSIBLE_MAX_RATE` (0.1), where events become dense and the trajectory is a random walk far from the ODE reference.
- The runner dispatches `gillespie_ssa_bimolecular`; the API ceiling applies to the summed initial population `a0+b0 ≤ MAX_API_SSA_POPULATION` (event count is bounded by `min(a0,b0)`).
- Keyword resolution gives `gillespie_ssa_bimolecular` priority over `gillespie_ssa` (bimolecular/second-order/association keywords), so "bimolecular association reaction" never falls through to first-order decay.
