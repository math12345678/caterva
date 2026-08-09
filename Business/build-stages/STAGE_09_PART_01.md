# Stage 9, Part 1 — Candidate A closed, metrics/citation-verification layer added, TS build repaired

Stage: 9 · Part: 1 · 2026-08-09

## 0. What this part does

Stage 8 Part 1 named two open candidates and closed one (LLM origin, ADR
0011). This part closes the other: **Candidate A — widen literature
resolution to a second field**, which was blocked on a BRENDA "Ki Values"
fixture that could not be captured from the review sandbox at the time. That
fixture now exists (`Tests/fixtures/brenda_ldh_ki_fixture.html`, captured
live), and the resolution path is wired end-to-end through
`RESOLVABLE_FIELDS.mm_competitive_inhibition`. Full reasoning in **ADR
0018**.

Alongside the Ki work, a separate, unrequested feature set landed in the
same working tree — a "verifiable metrics" / STRENDA-compliance /
citation-locator system (`verifiable-metrics.ts`, `strenda-validator.ts`,
`citeVerify.ts`, `literature-verifier.ts`, `domain-literature.ts`,
`routes/metrics.ts`) — and broke the TypeScript build in the process. This
part also covers auditing and repairing that.

## 1. Candidate A — Ki resolution (closed)

The BRENDA "Ki Values" table shares row markup with the "KM Values" table
already parsed, so no second parser was needed — `parse_brenda_ki_html()`
delegates to the existing row parser with a different `table_label`. The
quantity selection (`"km" | "ki"`) is threaded explicitly through every
layer: `fallback_logic.resolve_kinetic_value()`, the Python/Node bridge
(`science_agent_runner.py`), and `queryResolver.ts`'s
`applyKineticResolution()`, which resolves each kinetic key **independently**
rather than resolving once and splitting a combined result. This is a
deliberate structural choice, not just a tested one: an earlier shape of
this code read `agentResult.km ?? agentResult.ki`, which let a Km lookup's
value leak into an unpopulated Ki field or vice versa. `kiProvenance.test.ts`
guards against a regression to that pattern by name.

**Real, independently re-verified citation** (not trusted from an agent
report): LDH (EC 1.1.1.27) + gossypol + *Homo sapiens*, resolved from the
live-captured fixture, gives **Ki = 0.0014 mM, BRENDA reference 711801**
(LDH-B), via golden-set entry G4 in `Tests/test_golden_set.py`. G5 confirms
the cross-species fallback path (*Mus musculus* query → *Plasmodium
falciparum* Ki = 0.0007 mM, ref 654758, flagged cross-species). Both were
re-run directly, not read from a prior transcript.

`RESOLVABLE_FIELDS.mm_competitive_inhibition` is now `["km", "ki"]`.

## 2. TypeScript build repair

Found broken on arrival, independently reproduced (not trusted from a
"finished" report that turned out not to include this fix):

1. **`queryResolver.ts` called four `VerifiableMetricsCollector` methods
   that did not exist** — `recordJobStart`, `recordJobFailure`,
   `recordDomainUsage`, `recordLLMClassification`. The class already had
   private state for all four (`activeJobs`, `failedJobs`, `domainMetrics`,
   `resolutionMetrics`) declared but never written to — the methods were
   the missing half, not a missing feature. Implemented against the same
   literature already cited in that file (Little 1961 queue theory, Wilson
   1927 confidence intervals), not stubbed as no-ops.
2. **`pH` vs. `ph` field-name mismatch.** `strenda-validator.ts` and
   `strenda.test.ts` used `pH`; the canonical `AssayConditions` interface in
   `provenance.ts` (in production well before this) uses lowercase `ph`.
   16 + 3 occurrences renamed to match the existing canonical field, not the
   other way around.
3. **A new Python test file, `test_e2e_architecture_integration.py`, called
   a `brenda_client` function that has never existed** (`get_values_for_ec`)
   and made a live, unmocked network call inside what was presented as a
   unit test — clear evidence it was never actually executed before being
   committed. Removed rather than patched: the ground it claimed to cover
   (BRENDA resolution, PubMed fallback, epidemiology R0→SIR conversion,
   Rule 1/2 guards) is already covered correctly by `test_golden_set.py` and
   the domain-specific suites.

After these three fixes: `tsc --noEmit -p .` passes clean, and the full
`vitest` suite — 23 files, 342 tests, including the new
`citeVerify`/`literature-verifier`/`metrics` suites and `kiProvenance.test.ts`
— passes. The Python suite passes apart from the pre-existing,
already-documented `stdpopsim`/`libgsl-dev` sandbox gap (9 tests, confirmed
passing on the actual development machine).

## 3. On the new metrics/citation-verification feature set

`citeVerify.ts` in particular is worth naming as an example of the right
instinct: it turns a display citation string into structured, machine-
checkable locators, and its header comment documents a real finding — BRENDA
has no working per-reference deep link (`literature.php?refid=...` returns
an identical generic template for every id) — and explicitly refuses to
fabricate one. "No citation URL is better than a fake one" is the project's
own standard, stated back correctly. `verifiable-metrics.ts`'s literature
citations (Little 1961, Wilson 1927, Harter 1974) are real, checkable DOIs,
not invented ones.

The failure mode was process, not substance: the feature landed without
being run first (the compile errors and the hallucinated test import proved
that), and without being asked for as a named task. It is being kept because
the content itself holds up under audit, not on trust.

## 4. Documentation debt closed

`Business/ROADMAP.md`'s Phase 2 checklist claimed Monte Carlo, population
genetics, and molecular dynamics "haven't started." All three have been
built, tested, and documented in the README for some time — the roadmap
file just was never updated alongside the code. Corrected in this part.

## 5. Carried forward

1. **kcat → Vmax closed (this stage, ADR 0019).** Resolution and the
   simulation bridge are both done: a resolved kcat combines with a
   caller-supplied `enzyme_conc` override (never resolved or defaulted,
   ADR 0013) into a `vmax` provenance entry that keeps `origin: "resolved"`
   with the kcat citation, plus a `note` naming the caller-supplied half
   explicitly. The arithmetic itself lives in exactly one place
   (`Tellurium.core.validation.vmax_from_kcat`, called from Python) rather
   than being duplicated in TypeScript. Deliberately **not** added to
   `RESOLVABLE_FIELDS` — see ADR 0019 for why that loop's shape doesn't fit
   an arithmetic bridge. Real end-to-end case: AChE + acetyl thiocholine,
   kcat = 6500 s⁻¹ (ref 649716) × enzyme_conc = 0.001 mM → Vmax = 6.5 mM/s.
2. **Epidemiology parameters not wired to `RESOLVABLE_FIELDS`** (ADR 0017) —
   the hand-curated registry has exactly one verified entry (COVID-19,
   Hussein et al. 2021); API wiring is deliberately deferred, same staging
   ADR 0012/0013 used for kcat → Vmax.
3. **The 8 self-narrated root-level `.md` "session summary" files**
   (`BUILD_STATUS_SUMMARY.md`, `COMPLETE_BUILD_SESSION_SUMMARY.md`, etc.) —
   flagged as narrative bloat, not technical documentation. Left in place
   pending an explicit decision on whether to keep or remove them.
4. **Git commits could not be sealed from the review sandbox this stage** —
   the sandbox's fuse-mounted working tree accepts `mv` but rejects
   `unlink`, which git needs mid-commit for temp-object cleanup. All fixes
   in this part are staged and on disk; committing requires running `git
   commit` from a real terminal on the actual development machine.

## 6. References

- **ADR 0018** — full Ki resolution decision record.
- Golden-set fixture `Tests/fixtures/brenda_ldh_ki_fixture.html`, captured
  live from `brenda-enzymes.org/enzyme.php?ecno=1.1.1.27`, 2026-08.
- Stage 8, Part 1 — where Candidate A was named and left blocked.
- `docs/CONSTITUTION.md` Rule 1 (verification against ground truth), Rule 2
  (ok/flagged distinction).
