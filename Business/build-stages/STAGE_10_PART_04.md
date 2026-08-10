# Stage 10, Part 4 — working the audit list: eight defects fixed

Stage: 10 · Part: 4 · 2026-08-09

Part 1 recorded 11 confirmed CRITICAL findings and fixed one. Part 3 fixed
a second and then stopped to ask which to do next — the wrong call, since
the list was already prioritised and the direction was already given. This
part works the list.

Every fix below was reproduced independently before being written, and
mutation-tested after. No fix is reported on the strength of an agent's
report alone.

## Engine

### 1. Lotka-Volterra: ADR 0023's defect was still reachable through the API

ADR 0023 corrected the transposed `gamma`/`delta` **defaults**. The
validator was never touched — it checked each rate against a wide
`[1e-4, 100]` band and nothing else — so any caller supplying their own
rates still got the identical failure: prey at `-5.79e-11` and 44% drift in
an exactly-conserved quantity, reported `flagged = False`.

Fixing a bad default without fixing the validator that permitted it leaves
the failure one HTTP request away.

The threshold is measured, not guessed. Varying `p0/(delta/gamma)`:

    ratio    min prey        drift in H
        1    +2.50e-01       0
        5    +8.72e-03       6.8e-09
       10    +1.14e-04       7.7e-08
       20    +1.03e-08       5.5e-05
       40    -5.73e-12       2.4e-01   <- NEGATIVE prey
       80    -5.16e-11       6.8e-01

`LV_EXCURSION_RATIO_FLAG_ABOVE = 20` is the last ratio whose drift leaves
the trajectory recognisably the modelled system. Checked on both species
and in both directions (1/40th of the fixed point is as extreme as 40x it).

9 tests; mutation-tested (5 fail with the check disabled).

### 2. The SSA ensemble mean was biased, and got worse with more replicates

`simulate_gillespie_ssa_replicates` placed each trajectory on the output
grid with `np.interp`. An SSA path is right-continuous and piecewise
**constant** — the count holds until the next event — so linear
interpolation reports counts the system never held. For a monotonically
decreasing species the error is one-sided: a systematic bias, not noise.

Measured against the exact closed form `E[a(t)] = a0*exp(-k*t)`:

    replicates   before                  after
           500   -0.66 mol,  -6.6 sigma  -0.17 mol,  -2.6 sigma
          2000   -0.53 mol, -10.9 sigma  -0.04 mol,  -1.7 sigma
          8000   -0.48 mol, -18.2 sigma  +0.01 mol,  -0.7 sigma

The bias plateaued while the standard error shrank, so **adding replicates
made the answer more conclusively wrong** — the opposite of what an
ensemble average is for. Replaced with a zero-order hold.

Why the existing guard missed it: that test checks four checkpoints at
3 sigma with a hardcoded `n_reps = 400`, where the error bars are still
wide enough to hide half a molecule. Its docstring claims it would catch
"an interpolation error between the endpoints". It would not, at that
sample size — **a tolerance stated in sigma silently loosens as the sample
shrinks.**

So the new test asserts the bias *shrinks* as the ensemble grows, which no
sample-size tuning can satisfy while a systematic offset remains. It also
pins that a single trajectory reports whole molecules; interpolation
produced fractional counts. 6 tests; mutation-tested (4 fail on the old
code).

### 3. Two-locus had no Rule 2 tier at all

`_validate_two_locus_params` built a `flagged: List[str]` that nothing ever
appended to, passed it into the **boolean** `flagged` field, and silenced
the type error with `# type: ignore[arg-type]`. An empty list is falsy and
`_serialise_result` wraps it in `bool(...)`, so every two-locus run
reported `flagged: false` regardless of input. It was the only domain in
the engine with no implausible-but-valid tier.

Population of 2, mutation rate 0.5, one replicate — all silently accepted,
while every other domain flags each. Thresholds are imported from the
single-locus domain rather than redefined, so the two cannot drift apart.
9 tests; mutation-tested (8 fail).

### 4. `Tellurium/__init__.py` was 25 names behind the engine

A hand-written import list plus a hand-written `__all__` — a second copy of
a list that already existed. Seven simulation domains were unreachable:
`import Tellurium; Tellurium.simulate_lotka_volterra` raised AttributeError
for a function the engine exports and the API dispatches.

Nothing caught it: `check_domain_parity.py` compares the runner, the
TypeScript union and the schemas; `test_boundary_contract.py` compares
DISPATCH against `__all__`. A package's own re-export list is not somewhere
anyone looks for drift, which is why it drifted.

Now derived programmatically (`from .tellurium_engine import *`, `__all__`
mirrored), so the two agree by construction rather than by vigilance —
ADR 0007's principle one level up. 12 tests, including that the submodule
binding the API bridge depends on survives the refactor.

## API

### 5. Every audit response identified itself as job `""`

`buildAuditReport` returned `jobId: ""` with the comment "will be set by
caller if needed". The caller never did. The route test asserted five other
properties and never looked at this one. Threaded through.

### 6. `strendaCompliant` was both always-false and applied to the wrong fields

Two defects at one call site. It gated on the **domain name**, so every
numeric parameter of an mm run got a STRENDA verdict — including `end` and
`points`. Reporting that an integration window is STRENDA non-compliant is
ADR 0021's error resurfacing at a route that bypassed the guard ADR 0021
installed. Now gated on `STRENDA_GOVERNED_FIELDS`.

And the call omitted the confidence bounds, forcing a Requirement-7
violation on every invocation and capping `score` at 3 where `compliant`
needs >= 4. The field could never be true, for any parameter, ever.

The honest resolution: `ParameterProvenance` genuinely carries no
confidence intervals, because neither BRENDA rows nor the ADR 0017 registry
supply them. So Requirement 7 is legitimately unmet and `false` is
legitimately correct — the defect was reporting a bare `false` with no way
to distinguish "we failed the standard" from "we never checked". The unmet
requirement numbers are now surfaced.

### 7. A placeholder was shipping inside `modelCitations`

`getDomainCitation` returned `` `Domain: ${domain}` `` for domains absent
from `DOMAIN_LITERATURE_MAP`, and callers pushed it straight into
`provenance.modelCitations`. A Monte Carlo run shipped
`"Domain: monte_carlo_pi"` to the client inside the list of citations
backing its result. A citations array is the one place a placeholder must
never appear.

`monte_carlo_pi` and `gillespie_ssa_replicates` now have real entries —
both were dispatchable and simulable with no literature entry at all.
Metropolis & Ulam (1949) is cited **without a DOI**: JASA 1949 predates DOI
assignment and sits outside PubMed's scope, so it could not be verified
from here, and inventing a plausible one is precisely what five other
citations in that file turned out to be. `sbml` is deliberately left
unmapped — the caller supplies the model, so Terrium has nothing to cite —
and the return type is now `string | undefined` so callers omit rather than
fabricate.

### 8. The dashboard called unverified defaults publication-ready

`publicationBlocked` tested `origin === "llm"` alone. The hard rule blocks
`default` and `llm` identically, and `runPipeline` assigns `default` to
every engine-added key. Now calls `unverifiedOriginKeys` — the hard rule's
own predicate — so the dashboard and the engine cannot disagree about what
"publication-ready" means.

9 tests covering 5-8, including one asserting that no
`defaultJustification` in the file ever again attributes default VALUES to
a paper.

## Verification

- 14 guards pass; `tsc --noEmit` clean.
- Engine: 1,014 tests. API: 30 files, 422 tests.
- Every fix mutation-tested; the mutation output is recorded in each test
  file's docstring rather than only in this report.

## Still open

From Part 1's list: `routes/metrics.ts` is wired to `metricsCollector`,
which no production code writes to (the pipeline records into
`verifiableMetricsCollector`), so `/api/snapshot` reports permanent zeros
with `llmSuccessRate: 100` fabricated from zero samples. And the ~20
fake-verification tests catalogued in Part 1 §3 — constants compared to
copies of themselves, bodies wrapped in `if` that pass when skipped — which
are worse than missing tests because they report coverage that does not
exist.
