# Stage 10, Part 12 — a fleet audit for checks that cannot fail

Stage: 10 · Part: 12 · 2026-08-11

## 1. Method

A subagent swept `Tellurium/`, `Tests/`, `scripts/` and the api-server for
ONE defect class — *a check whose verdict cannot depend on its input* — with
the seven known instances from Parts 5–11 as worked examples. It returned
nine findings, six of them real and unfixed.

Every finding below was **independently reproduced before being touched**.
One was a false positive of my own framing and is recorded as such.

## 2. Every kcat BRENDA returned was labelled a concentration

**The most serious finding.** `Tests/brenda_client.py` serves three BRENDA
tables through one parser, selecting units by table:

```python
if table_label == TURNOVER_TABLE_LABEL:
    _quantity, _unit = "kcat", "1/s"
elif table_label == KI_TABLE_LABEL:
    _quantity, _unit = "Ki", "mM"
else:
    _quantity, _unit = "Km", "mM"
```

and then constructed every entry with a hardcoded `unit="mM"`. `_unit`
reached only the plausibility-flag message, never the returned object.

Reproduced against the real AChE fixture:

```
kcat=118.0    unit='mM'
kcat=6500.0   unit='mM'     <- 6500 s^-1, ADR 0019's golden value
kcat=35.0     unit='mM'
```

A turnover number emitted as a millimolar concentration. It travelled
through `KineticResult.unit` → `science_agent_runner.py` → the API
response, so `{"kcat": 6500, "unit": "mM"}` reached callers. And because
the field was a *constant*, any downstream unit check reading `.unit` was
structurally incapable of failing — which is how it survived.

It survived for a second reason: `test_fallback_logic.py` asserts the kcat
path's value, source, organism and citation, but never its unit.

Fixed to `unit=_unit`. New `Tests/test_brenda_units.py` (5 tests) asserts
the unit follows the table label, including the parametrised property that
a hardcoded unit can only satisfy one case. Mutation-verified: restoring
`unit="mM"` fails 3 of them.

## 3. `/api/dashboard/health` could not report anything but healthy

```ts
const healthy =
  metrics.completedJobs >= 0 &&   // counter, starts at 0, only ++
  metrics.avgLatencyMs >= 0 &&    // mean of elapsed times, or 0
  jobs.length >= 0;               // Array.length is a uint32
```

Three tautologies on quantities that are non-negative by construction, so
`healthy` was a compile-time `true` and the 503 branch was unreachable.
`checks.literature` was the string literal `"ok"` — no literature was
consulted.

This is the unfixed twin of the bug Part 5 corrected in
`routes/metrics.ts`; only this copy was missed. It now uses the same
three-tier shape (`no_data` / `healthy` / `degraded`), publishes
`sampleCount` alongside the rate, and reports `literature:
"not_checked_here"` rather than claiming a check it does not perform.

### The tests were asserting the unreachable branch

`routes.test.ts` asserted `status === 200` twice. That passed only because
the endpoint could not return anything else. With real logic it returns
**503 in the full suite** — correctly: `verifiableMetricsCollector` is a
module singleton, and by the time these tests run, earlier ones have
recorded failed jobs, so `degraded` is the right answer. The tests now
assert the contract (status ∈ the three tiers, code agrees with status,
rate present only with a non-zero denominator) instead of one status code
that depended on accumulated global state.

## 4. A cited 100% success rate from zero observations

`getSuccessRateWithConfidence()` returned `{ rate: 1 }` on an empty sample
— the `n > 0 ? x/n : 1` pattern verbatim. `getSnapshot()` in the same file
was fixed for this in Part 5; **this method, the one the dashboard actually
reads, was not**. It surfaced at `/api/dashboard/overview` as
`successRate.rate` with a Wilson (1927) citation attached, and
`exportWithCitations()` rendered it `"100.00"`.

`rate` is now `number | null`, with `sampleCount` published beside it. null
rather than 0, because zero successes out of zero trials is not a 0% rate
either — there is simply no rate. Changing the type surfaced both silent
consumers at compile time, which is the point of using it rather than a
sentinel.

## 5. A guard whose loop could not record a violation

`scripts/check_plausibility_constants.py::check_constant_usage` — two
`continue`s and no `errors.append` anywhere inside the loop. For any
readable `validation.py` it returned `[]` regardless of contents: deleting
every use of every plausibility bound would still have printed its OK line.

Rewritten to check what its name claims — that a bound is actually *read*
somewhere, not merely defined. Three refinements, each forced by a mutation
that survived the previous version:

1. **Scope.** Scanning only `Tellurium/` flagged the kcat bounds, which are
   genuinely used one layer over in `Tests/brenda_client.py`. My first
   version's finding here was a **false positive** — the cross-layer
   duplication is deliberate (ADR 0003) and already guarded by
   `check_constants_consistency`.
2. **Tests are not users.** A bound referenced only by a test asserting it
   exists is wired into nothing. Counting tests let a mutation that inlined
   the kcat bounds pass.
3. **Assignment vs reference, not file-level exclusion.**
   `brenda_client.py` both defines the kcat bounds and is their only
   production reader, so excluding "definition files" hid its own use and
   failed a correctly-wired constant.

Mutation-verified end to end: green at baseline, fails when the only
production reader is inlined away, green again on revert.

## 6. Verification

- Root tree: **179 / 179** passing, 11 suites, `tsc` clean.
- api-server: **422 / 422** passing, `tsc` clean.
- Python engine: **285 passed**, the same 9 `test_popgen_resolver` failures
  from `stdpopsim` being uninstallable in the review sandbox (unchanged
  across this work).
- Every fix above mutation-tested individually.

## 7. Reported but NOT yet fixed

Recorded rather than quietly dropped:

- **`check_citation_format.py` prints OK when it parses zero citations.**
  If `ARRAY_RE` stops matching (field renamed, entries moved to a const,
  template literals instead of `"..."`), `extract_entries` returns `[]`, the
  loop never runs, and an empty parse reports a clean tree. Two sibling
  guards — `check_domain_parity.py` and `check_literature_inventory.py` —
  already emit "parsed ZERO … Refusing to report success"; this one never
  got that treatment.
- **`auditForPublication` treats `flagged` as publication-ready.**
  `readyToPublish = counts.pending === 0 && (verified + flagged > 0)`.
  `unverifiable` (what `origin: "default"` and `"user"` produce) is counted,
  named in the summary, then ignored by the boolean. The per-parameter gate
  that *does* require evidence, `canPublish`, is never called by it — so the
  aggregate can say ready while every individual parameter fails.
- **Vacuous test** in `kcatProvenance.test.ts:84-93`: the only assertion is
  inside `if (provenance)`, and provenance is `undefined` for those keys by
  design, so it never executes.
- **Locator consistency is opt-in** (`provenance.ts:322`): every locator
  check is nested under `citationLocators !== undefined`, and nothing
  requires a `resolved` entry to carry locators.
- **Four latent silent skips** in `verify_citations_live.py` (`if not
  path.is_file(): continue`) — dormant today, all five paths exist, but the
  same shape as the citation-format hole.
