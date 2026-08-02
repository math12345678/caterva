# Stage 7, Part 3 — close

Stage: 7 (a second SSA regime) · Part: 3 (close) · 2026-08-02

## 1. What Stage 7 was

Stage 6's close named three candidates and committed to none: a second SSA
regime, widening literature resolution to a second domain, or the queued
"resolved value through the LLM path" question. Stage 7 took the first.

- **Part 1** — the bimolecular domain `A + B → C`, second-order propensity
  `k·a·b`, wired through engine, runner, API, CLI, DB enum, OpenAPI codegen
  and provenance, with a hand-verified golden trajectory pinned at three
  levels.
- **Part 2** — an independent audit that re-derived Part 1's claims without
  reading its suite for the answers. **No defects found.**
- **Part 3** — this close, plus the defect the close itself uncovered.

Stage 7 also absorbed the ADR 0010 STRENDA work that landed mid-stage
(assay-condition plumbing, the golden tuple, 16 → 0 vitest failures). That
is recorded in STAGE_05_PART_07 §10–11 where the contract lives.

## 2. The domain, verified independently

Part 2's evidence in one line each:

- **Golden trajectory** — `u₁ = 0.22733602246716966` and
  `τ₁ = −ln(u₁)/(k·a₀·b₀) = 0.06172192003509486` reproduce from first
  principles to the last digit.
- **Conservation** — `a+c = 60` and `b+c = 40` on every row; `c ≤ min(a₀,b₀)`.
- **ODE agreement** — worst-case relative error **0.68 %** over 400 seeds
  against `a(t) = (a₀−b₀)/(1 − (b₀/a₀)e^{−k(a₀−b₀)t})`.
- **Runtime ceiling** — fires before simulating; exact at the boundary
  (1,000,000 runs, 1,000,001 raises). The Stage 4 MD defect does not
  reproduce, because an SSA's event count really is bounded by initial
  population.
- **Narrowness** — `RESOLVABLE_FIELDS` still `{ mm: ["km"] }`.

## 3. The defect this close found

Writing a close means restating the project's totals, which is when I
compared them against the repository:

| Claim in README.md | Stated | Actual |
|---|---|---|
| `make test` | 524 | **1,040** |
| `Tellurium/tests/` | 833 | **858** |
| `Tests/` | 124 | **182** |
| simulation domains (line 8) | "Eight" | **Ten** |
| simulation domains (line 69) | "Ten" | Ten |

Four wrong numbers, and the domain count stated **twice in the same file
with two different values**. The prose count had never been updated after
Wright-Fisher and the bimolecular domain landed.

None of this is dangerous on its own. What matters is the mechanism: these
are factual claims about the repository, and **no executable check covered
any of them**, so nothing objected as they went stale. That is the citation
guard's failure mode exactly (Stage 4 Part 5), and the Stage 4 amendment
applies verbatim — *a guard is not delivered until something runs it
unasked.*

Note also which direction the error ran. Every stale number **understated**
the work: 524 against 1,040 tests. A project this careful about not
overclaiming had been quietly underclaiming for several stages, because the
same absence of a check permits drift in both directions.

## 4. The fix: `scripts/check_documented_counts.py`

The counts are collected from pytest itself (`--collect-only`), not
recomputed by a parallel implementation that could drift in its own way.

Two checks, deliberately different in kind:

1. **Test counts** are compared against reality. Ground truth exists, so it
   is used.
2. **Domain counts** are checked for *internal consistency* only. `DISPATCH`
   has 12 entries, but `gillespie_ssa_replicates` is a run mode and `sbml` a
   generic ingest path — neither is a teaching domain. Any automatic count
   would silently encode that judgment call, so the guard verifies the
   README agrees with itself and leaves the number to a human. **Ten** is
   the defensible figure and both claims now state it.

A missing dependency yields `OK (partial)` rather than a spurious mismatch:
an environment problem must not be reported as a documentation defect.

### Mutation-tested, and the exit code checked

Three mutations, each detected:

```
runs all 999 tests      -> FAIL  make_test: README says 999, actual is 1,040
line 8 "Eight"          -> FAIL  conflicting domain counts (line 8: 8, line 69: 10)
tests/  833 tests       -> FAIL  engine: README says 833, actual is 858
```

The second reproduces the original defect exactly. Exit status confirmed
directly (`1` on failure, `0` on pass) rather than read off a piped `tail` —
the specific mistake made when verifying the citation guard in Stage 4.

### Wired into three layers

- `scripts/verify_domain.sh` — Step 2c-2
- `.github/workflows/tests.yml` — its own step, failing fast
- `scripts/verify_build.py --quick` — confirmed to fail the **aggregate**
  (exit 1) with a mutated README, not merely print a warning

## 5. Verification totals

- **vitest: 188 passed, 10 files, 0 failed** — includes the 21 STRENDA tests
  and the 3 added closing ADR 0010.
- **pytest (engine): 858 collected.** The SSA/validation/boundary/guard
  subset runs **269 passed, 0 failed**.
- **pytest (literature): 182 passed.**
- **All six guards exit 0**: citation format, documented counts,
  plausibility constants, dependencies, engine contract, RNG convention.
- `verify_build.py --quick` — ALL CHECKS PASSED.
- `tsc --strict` clean.

**Not verified here:** the full 858-test engine suite does not complete in
the review sandbox (the MD file runs long and background processes do not
survive between shell invocations). Stated rather than papered over. To
close it locally:

```bash
cd ~/Desktop/Coding/Terrium
python3 -m pytest Tellurium/tests -q     # expect 857 passed, 1 skipped
make test                                # both suites, 1,040 total
```

## 6. Deliberate decisions

1. **The audit reported no defects in Part 1.** Every prior audit found
   something, which creates real pressure to manufacture a finding. Part 1
   was carefully built and the report says so.
2. **Domain counts are checked for consistency, not correctness.** Encoding
   "is `sbml` a teaching domain?" into a guard would freeze a judgment call
   behind a green check.
3. **The counts guard reads pytest's own collection** rather than walking
   the AST for `def test_`, which would drift from parametrisation.
4. **`OK (partial)` on collection failure.** A guard that cannot run must
   say so, not fail closed and train people to ignore it.

## 7. Carried forward

1. **`vmax` / `kcat` have no lookup path.** They sit in
   `STRENDA_GOVERNED_FIELDS` so the requirement applies automatically the
   moment one is added (ADR 0010 carried item 3).
2. **The two untaken Stage 6 candidates remain open:** widening literature
   resolution to a second domain, and "resolved value through the LLM path"
   (Stage 4 Part 6).
3. **README's per-domain prose** is hand-maintained. The guard now catches
   count drift but not a domain described inaccurately.

## 8. References

- **Gillespie, D. T. (1977).** Exact stochastic simulation of coupled
  chemical reactions. *J. Phys. Chem.* **81**(25), 2340–2361.
  DOI 10.1021/j100540a008. Verified against the published record.
- **ADR 0009** + bimolecular amendment; **ADR 0005** (RNG convention);
  **ADR 0010** (STRENDA assay conditions).
- `docs/CONSTITUTION.md` — Rule 1 (independent ground truth), Rule 9
  (flag judgment calls), and the Stage 4 amendment on guard delivery.
