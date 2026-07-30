# Stage 2, Part 2 — Domain Spec: Population Genetics (Wright-Fisher Neutral Drift)

## 0. A divergence, resolved before this part could even be written

While this part was being drafted, a spec for this exact domain — and
`docs/adr/0005-rng-convention.md` — appeared in the repo already written,
independently, resolving Stage 2 Part 1's three open items on its own.
This is the same situation Stage 1 Part 4 defined a procedure for
(independent outputs converging on the same task), just applied to a spec
and an ADR instead of to code, which Part 2's own earlier draft flagged as
an open question ("extending divergence resolution to a document, not
just code"). Resolving it here, following that exact procedure:

**Is the divergence cosmetic or substantive?** Function naming differs
(`simulate_wright_fisher` / `validate_wright_fisher_params` in the
existing file versus `simulate_population_genetics_drift` /
`validate_population_genetics_params` in this document's earlier draft) —
cosmetic, and `wright_fisher` is the better name: it names the actual
model, the way `simulate_pcr` and `simulate_monte_carlo_pi` name their
actual models rather than their general category. Adopted.

Two things in the existing spec are substantively *better* than what this
part would otherwise have specified, not just different:

1. **`replicate_runs` as an explicit public parameter**, rather than an
   implementation detail chosen by whichever tool builds this. This
   makes the number of replicate populations a controllable, testable
   part of the API — a caller (or a test) can ask for exactly 5,000
   replicates and get exactly that, rather than the verification-only
   replicate count Part 1's draft left implicit. This is a real
   improvement in the actual contract, not just phrasing.

2. **ADR 0005 caught something Part 1's draft ADR text did not**: `numpy.
   random.default_rng`'s default BitGenerator is not fixed across numpy
   major versions — PCG64 under numpy 1.x, Philox under numpy 2.x — so a
   fixed seed reproduces bit-identical output only within a single numpy
   installation, not across numpy versions. This is exactly the kind of
   thing Rule 1 (verify against ground truth) and Rule 9 (flag judgment
   calls) exist to surface, and it's a materially more honest statement
   of what "reproducible" actually guarantees here than this stage's own
   earlier ADR draft claimed. Adopted as the canonical ADR 0005 without
   modification — reproducing this exact finding via a different route
   would waste effort that's already correctly spent.

**Resolution, per Stage 1 Part 4's procedure**: no re-implementation
needed, no code was ever in question (nothing had been built yet — this
was two spec-writing attempts converging, not two competing
implementations). The existing spec and ADR 0005 are adopted as the
canonical Stage 2 artifacts. What's added below is the one piece neither
document yet had: the actual ready-to-paste implementation prompt.

## 1. The domain spec (adopted from the existing repo file, reproduced here for a single-source-of-truth reference)

## 1. ONE-SENTENCE DEFINITION

Simulate neutral genetic drift in a diploid Wright-Fisher population at a
single biallelic locus, tracking allele frequency trajectories,
heterozygosity decay, and fixation outcomes across many independent
replicate populations.

## 2. GOVERNING MODEL

**Wright-Fisher model, diploid, single locus, two alleles (A and a),
neutral drift only (no selection, mutation, or migration).**

Each generation $t$, the next generation's $2N$ allele copies are formed
by binomial sampling with replacement from the current generation's allele
pool. If the current frequency of allele $A$ is $p_t$, then the number of
$A$ copies in the next generation is:

$$X_{t+1} \sim \text{Binomial}(2N, p_t)$$

and the next generation's frequency is $p_{t+1} = X_{t+1} / 2N$.

Heterozygosity $H_t = 2 p_t (1-p_t)$ decays under pure neutral drift
according to:

$$E[H_t] = H_0 \left(1 - \frac{1}{2N}\right)^t$$

exactly, following directly from the binomial sampling variance. Fixation
probability for a neutral allele starting at frequency $p_0$ is exactly
$P(\text{fixation}) = p_0$ (Kimura, 1962), from the martingale property of
allele frequency under neutral drift.

## 3. CONTINUOUS OR DISCRETE — AND WHY

**Discrete.** No continuous-time state between generations. Same category
as PCR (ADR 0002) and Monte Carlo. Direct Python + numpy, using
`numpy.random.Generator.binomial`, per ADR 0005's RNG convention.

## 4. PUBLIC FUNCTION SIGNATURES

```python
def validate_wright_fisher_params(
    population_size: int,
    starting_frequency: float,
    generations: int,
    replicate_runs: int = 1,
) -> ParameterValidation: ...

def simulate_wright_fisher(
    population_size: int,
    starting_frequency: float,
    generations: int,
    replicate_runs: int = 1,
    seed: int | None = None,
) -> SimulationResult: ...
```

`SimulationResult` columns: `generation`, `mean_frequency`,
`heterozygosity`, `n_A_fixed`, `n_a_fixed` — one row per generation,
aggregated across all replicate populations. Once a replicate fixes, its
frequency holds at that value for all subsequent generations (no
mutation reintroduces variation).

## 5. VALIDATION CONTRACT

Hard rejections (`ok=False`): `population_size` not an integer >= 1 (bool
explicitly excluded — same guard Monte Carlo used, since `bool` is an
`int` subclass in Python). `starting_frequency` not a finite float in
[0, 1]. `generations` not an integer >= 1. `replicate_runs` not an
integer >= 1.

Flags (`ok=True, flagged=True`): `population_size < 10` (drift extremely
rapid, valid but likely not the intended scenario). `starting_frequency`
exactly 0.0 or 1.0 (valid but degenerate — allele already lost/fixed).
`generations > 10_000` (valid, may be slow). `replicate_runs < 10` (valid,
but standard error of mean heterozygosity will be large).

## 6. VERIFICATION TARGET

**Target A — heterozygosity decay, exact rate.**
`simulate_wright_fisher(N=100, p0=0.5, generations=200,
replicate_runs=5000, seed=42)`; check heterozygosity at generations 0, 50,
100, 150, 200 within 0.02 absolute of $H_0(1-1/(2N))^t$ — derived as
roughly 3 standard errors given 5,000 replicates
($\sqrt{0.25/5000} \approx 0.007$).

**Target B — fixation probability equals $p_0$ (Kimura).**
`simulate_wright_fisher(N=20, p0=0.4, generations=500,
replicate_runs=2000, seed=42)` (500 generations ≈ 12.5×$2N$, long enough
for near-complete fixation); check
`n_A_fixed / (n_A_fixed + n_a_fixed)` within 0.04 of $p_0$ — roughly 3.6
standard errors given 2,000 replicates.

**Target C — fixed-seed bit-identical reproducibility.** **Target D —
different seeds produce different trajectories.**

**Pre-specified mutation** (per Stage 2 Part 1's resolution): change the
binomial sampling size from $2N$ to $N$ — the classic diploid
off-by-factor-of-2 error. Target A must catch this (the decay rate shifts
from $(1-1/(2N))$ to $(1-1/N)$, a detectable difference at the tested
checkpoints).

## 7. RELEVANT ADRs

ADR 0002 (discrete, not continuous) — directly applicable. ADR 0005 (RNG
convention) — directly applicable; also documents the numpy-version
BitGenerator caveat on reproducibility (Section 0 above). ADR 0001, 0003,
0004 — not applicable, noted explicitly rather than silently skipped.

## 8. SHARED-CONSTRAINT CHECK

RNG convention (ADR 0005) is the shared constraint with Monte Carlo — the
second domain following it, formalized now rather than deferred to a
third. Not yet enforced by an automated test (an AST-based guard
analogous to `scripts/check_dependencies_declared.py`, checking for
`default_rng` usage, is a plausible future addition if a third stochastic
domain makes manual review insufficient — noted, not built now, since
building it wasn't asked for by this spec).

## 9. OUT OF SCOPE FOR THIS STAGE

No selection, mutation, migration, multiple loci/linkage, coalescent
simulation, or external population-genetics libraries. No effective
population size ($N_e$) corrections — census size $N$ only. No changes
outside `Tellurium/tellurium_engine.py` and its tests. No new runtime
dependency (`numpy` already declared).

## 10. DELIVERABLES CHECKLIST

- [ ] `validate_wright_fisher_params()`, `simulate_wright_fisher()` in
      `Tellurium/tellurium_engine.py`, exported in `__all__`.
- [ ] Tests in `Tellurium/tests/test_popgen_correctness.py`: Targets A-D,
      all validation rejections/flags, structural invariants.
- [ ] Pre-specified `2N`-vs-`N` mutation test, documented, plus at least
      one additional implementer-discovered mutation.
- [ ] Independent reproduction of at least one mutation test by the
      reviewer during Part 4 — not taken on the implementer's report.

## 2. The full, ready-to-paste implementation prompt

`docs/CONSTITUTION.md` Section 3's preamble, verbatim, followed by the
spec above — the single block of text sent, identically, to both OpenCode
and FreeBuff, exactly matching Monte Carlo's pattern from Stage 1 Part 2:

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

Also read docs/adr/0005-rng-convention.md before starting — this domain
is the second to use the RNG convention it formalizes, and your
implementation must comply with it exactly (numpy.random.default_rng(seed),
seed: int | None = None, bit-identical reproducibility within a fixed
numpy installation).

---

DOMAIN SPEC — Population genetics (Wright-Fisher neutral drift)
Stage: 2   Part: 2

[Sections 1 through 10 from this document, pasted in full]
```

## 3. What Part 3 covers

Part 3 is the implementation step: this exact prompt sent to OpenCode and
FreeBuff independently. Given that a spec-level divergence already
happened and was resolved in Part 2 itself (Section 0 above), Part 3's
job is squarely the code-level verification Stage 1 already established —
run the full suite, the dependency guard, reproduce the pre-specified
`2N`-vs-`N` mutation independently, and check for any *new* divergence at
the implementation level, separate from the spec-level divergence already
closed out here.
