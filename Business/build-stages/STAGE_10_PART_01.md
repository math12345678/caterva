# Stage 10, Part 1 — full-repo agent audit; the hard rule was bypassable

Stage: 10 · Part: 1 · 2026-08-09

## 0. What this part does

Two audit agents were dispatched across the engine and the API server, each
given `docs/AGENT_BRIEF.md` and scoped to **find and report, not write** —
every finding then re-verified here before anything was changed. That
division is deliberate: this session's recurring failure has been agents
landing plausible code nobody checked.

They returned 11 CRITICAL findings between them, all evidence-backed. One
of them invalidates the project's central claim, and is fixed here. The
rest are triaged below.

## 1. CRITICAL — the hard rule was bypassable. Fixed.

`PARAMETER_PATTERN` in `queryResolver.ts` was **unanchored**, and applied
per whitespace-delimited token. So a parameter name occurring anywhere
inside a word was harvested as a user-supplied override. `k` is a parameter
name. Protein names are `<letters><digit>`.

Independently reproduced before fixing:

```
gillespie decay of CDK1 a0=100 end=10  ->  {"k":1,"a0":100,"end":10}
gillespie decay of ERK2 a0=100 end=10  ->  {"k":2,"a0":100,"end":10}
simulate backend2 gillespie a0=10      ->  {"end":2,"a0":10}
gillespie decay of protein a0=100 ...  ->  {"a0":100,"end":10}   <- control, correct
```

**The rate constant was being read off the protein's name.** `CDK1` gives
k=1, `ERK2` gives k=2 — two queries differing only in which protein is
named produce different physics.

The values were stamped `origin: "user"`, so `unverifiedOriginKeys()` saw
nothing to block and `RequiredParametersMissingError` never fired. That is
precisely the laundering the hard rule exists to prevent: the rule says no
value nobody chose reaches the engine, and this minted values out of
arbitrary text while reporting them as deliberate user input. The identical
query with a name lacking an embedded key+digit is correctly rejected —
so the bug made the system *appear* to work in exactly the cases where it
should have refused.

Worst available failure mode: it changed the scientific answer silently
rather than failing loudly.

**Fix:** the pattern is now anchored (`^...$`). This costs nothing real —
callers already split on whitespace before it runs, so a delimiter-less
pair ("km 5") could never reach it anyway, and `queryOverrides.test.ts`
already pins that it returns `{}`.

**Verification:** 8 new tests in `parameterLaundering.test.ts`, including
one asserting that two queries differing only in protein name produce
identical overrides. Mutation-tested — removing the anchors fails 5 of 8,
while both "still extracts genuine overrides" tests keep passing,
confirming the fix is targeted rather than a blanket disable. Full suite:
30 files, 413 tests, all green; 13 guards pass.

## 2. Confirmed findings not yet fixed

Re-verified from the agents' evidence, ordered by severity. Each needs its
own change and its own mutation test; batching them into one commit would
make the diff unreviewable.

**Engine:**

1. **SEIR skips its own R0 check when `i0 == 0` — the API's default.**
   `validate_sir_params` returns early before computing `beta/gamma`. In
   SEIR `i0=0` is not inert (`e0=10` seeds a full epidemic), so the bound
   is disabled at the domain's normal operating point. Demonstrated:
   `beta=100, gamma=0.1` → R0=1000, `flagged=False`, epidemic peaks at
   I=499.
2. **ADR 0023's Lotka-Volterra defect is still reachable via the API.**
   Only the *default* was fixed. `validate_lotka_volterra_params` has no
   check on the excursion ratio `p0/(delta/gamma)`, so passing the old
   values through the API still yields `min P = -5.79e-11` and 44% drift
   in the conserved quantity, un-flagged. The test suite pins only the
   signature defaults.
3. **`simulate_gillespie_ssa_replicates` returns a biased ensemble mean.**
   `np.interp` linearly interpolates a right-continuous step function, so
   the bias is systematic: it plateaus at ≈ −0.45 molecules while the
   standard error keeps shrinking. Accuracy *degrades* as replicates
   increase (−1.8σ at 500 reps, −7.4σ at 8000). The guarding test is
   under-powered at its hardcoded 400 reps.
4. `TwoLocusResult.flagged` is a `list`, not a `bool` — the two-locus
   domain has no Rule 2 tier at all, and `_serialise_result`'s `bool(...)`
   masks it so the API always reports `flagged: false`.
5. `Tellurium/__init__.py` is 25 names behind `tellurium_engine.__all__`;
   `import Tellurium; Tellurium.simulate_lotka_volterra` raises
   AttributeError. `check_domain_parity.py` does not inspect it.

**API:**

6. `/api/simulate/:jobId/audit` always returns `jobId: ""`.
7. `strendaCompliant` in that audit can never be true (the call site omits
   the confidence bounds, guaranteeing a Requirement-7 violation), and is
   stamped on non-kinetic parameters like `end` and `points` — the ADR
   0021 error resurfacing at a route that bypasses the guard.
   `publicationReady` is also true while every parameter is `unverifiable`.
8. `routes/metrics.ts` is wired to `metricsCollector`, which **no
   production code writes to** — the pipeline records into
   `verifiableMetricsCollector`. `/api/snapshot` therefore reports
   permanent zeros with `llmSuccessRate: 100` fabricated from zero
   samples, and `/api/metrics/health` cannot ever return `degraded`.
9. `getDomainCitation` emits the placeholder `"Domain: monte_carlo_pi"`
   into `modelCitations` as though it were a citation, for the three
   domains absent from `DOMAIN_LITERATURE_MAP`.
10. `routes/dashboard.ts`'s `publicationBlocked` checks only
    `origin === "llm"`, ignoring `default` — which the hard rule treats
    identically.
11. **A dangling ADR reference:** `model_building.py` cites `docs/adr/0024`
    twice as authority for the repressilator `beta` correction. ADR 0024
    does not exist (0005–0023 only). No guard validates ADR references.

## 3. Fake verification found across the test suites

The API agent identified ~20 tests that assert nothing meaningful. The
recurring shapes:

- **Constant vs. a literal copy of itself.** `metrics.test.ts`'s "tracks
  all 13 domains" compares a literal array against `DOMAINS` — and the
  array has 12 entries, so it cannot notice the collector tracks 12 of the
  engine's 16 dispatchable domains.
- **Conditional bodies that pass when skipped.** Three
  `literature-backed-e2e.test.ts` tests wrap every assertion in
  `if (result.domain === "…")`; `cachedProvenance.test.ts` returns early
  on `if (!first)`, silently skipping the ADR 0016 regression it exists to
  guard in exactly the conditions where it matters.
- **Values computed and never asserted** (`literature-backed-e2e.test.ts`
  binds `message` and `hasDomainCitation`, asserts neither).
- **Testing the dependency, not the code.** `rateLimit.test.ts` builds its
  own limiter and never imports the project's — which is untestable anyway,
  since `lib/rateLimit.ts` disables itself under `NODE_ENV=test`.
- **`verifiable-metrics.ts` has no test file at all.** The Wilson interval
  and Harter percentiles that two endpoints publish are called by zero
  tests.

These are worse than missing tests: they report coverage that does not
exist, and the suite being green is what let items 1–11 survive.

## 4. What the audits confirmed as genuinely sound

Recording this because it matters as much as the defects, and because
"everything is broken" would be as inaccurate as the green suite was.

- Every `simulate_*` has a real external anchor — closed form, conserved
  quantity, independent integrator, or published value. No domain is
  verified only against itself.
- All 16 DISPATCH domains execute end to end through the Python bridge;
  the phantom-domain failure has not recurred.
- The Lotka-Volterra defaults are now correct (first integral drifts
  2.9e-8; agrees with `scipy` LSODA to 1.2e-7).
- Repressilator `beta = 0.2` is right, re-derived independently: the
  Jacobian at the fixed point has `max Re(λ) = +0.042` (genuine limit
  cycle), and all four constants match `BIOMD0000000012` exactly.
- All five DOIs in the Tellurium tree resolve to the right papers with
  matching volume/issue/pages, checked live against CrossRef.
- Rule 1 rejection is complete across all 11 validators (6×N battery of
  negative/NaN/inf/bool/str/zero found no impossible value accepted).
- The hard rule itself, where it is reached, is correctly implemented —
  §1 was upstream of the check, not a flaw in it.

## 5. Next

Items 1–11 in §2, each as its own change with its own mutation test. §3's
fake tests should be fixed or deleted, not left as decoration. The agent
transcripts are retained (`a28c2dfad45437ab3`, `a3e2ff9fced320b90`) and can
be resumed for detail.
