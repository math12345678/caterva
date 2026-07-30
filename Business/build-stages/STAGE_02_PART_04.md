# Stage 2, Part 4 — Verification and Divergence Resolution

Reminder for scale: this is Part 4 of Stage 2. There are 100 stages
total, 98 remaining after this one closes.

## 0. What was actually run, not what was claimed

Everything in this part reflects commands actually executed against the
real repository state during this session, not a description of the
procedure in the abstract. By the time verification started, the
implementation had already landed and been committed externally
(`608e072`, "Stage 2: population genetics domain — Wright-Fisher neutral
drift") — this part is the independent check of that commit's claims,
per the constitution's standing rule that a report claiming verification
happened is not itself sufficient (Rule 6, Section 6 Step 4).

## 1. Full suite

```
python3 -m pytest tests/test_popgen_correctness.py -q
```

45 passed. Running the repo-wide script:

```
bash scripts/verify_domain.sh wright_fisher
```

Step 1 (full `Tellurium/` + `Tests/` suite): pass. Step 2 (dependency
guard, `scripts/check_dependencies_declared.py`): pass — no new
dependency was introduced (numpy already declared, per Part 2's
out-of-scope statement). Step 3 (new-domain test file collects): the
script reported a **false failure** — it looks for
`test_wright_fisher_correctness.py` by naming convention, but the actual
file is `test_popgen_correctness.py` (matching the domain's spec name
"population genetics," not the model name "Wright-Fisher"). This is
cosmetic per Section 7's cosmetic/substantive distinction — the file
exists, is collected, and passes; the script's naming heuristic just
doesn't match this domain's chosen name. Worth a small fix to
`scripts/verify_domain.sh` to accept either naming pattern or take the
test file path as an argument, noted for Part 5, not fixed mid-review.

## 2. Independent mutation-test reproduction — two divergences found and corrected

Both of the record's two claimed mutations were reproduced independently
by hand (backup, mutate, run, confirm, revert, confirm clean — using `;`
separated steps, never `&&`, per the constitution's standing warning).
Both mutations are real and both are caught. But the specifics of what
gets caught didn't match the record as originally written, in two
separate ways — both now corrected in
`Tellurium/tests/test_popgen_correctness.py`'s own docstring, not just
noted here.

**Mutation 1 — the pre-specified `2N`-to-`N` off-by-factor-of-2.**
Applied: `two_n = 2 * population_size` → `two_n = population_size`. The
original record claimed 3 tests would fail ("decay target, fixation
target, and mutation-detection guard"). Independent reproduction found
exactly 2: `test_heterozygosity_decay_matches_exact_rate` and
`test_mutation_pre_specified_two_n_to_n_changes_decay_rate`. No
fixation-related test failed. The reason is structural, not a fluke: the
mutation-test invocation runs `simulate_wright_fisher` with Target A's
parameters (`population_size=100, generations=200`), not Target B's
(`population_size=20, generations=500`) — the two verification targets
are separate calls with separate parameter sets, so a mutation only trips
assertions in the specific call it actually touches. This is the same
category of overclaim Stage 1 caught in Monte Carlo (a report claiming
more tests would catch a mutation than actually did) — same root cause
too: it's easy to reason abstractly about what "should" break without
running the exact invocation and counting.

**Mutation 2 — skip the last generation** (`range(1, generations + 1)` →
`range(1, generations)`). The original record claimed 2 tests would fail.
Independent reproduction found 5:
`test_last_generation_is_present`, `test_n_rows_equals_generations_plus_one`,
`test_single_replicate_produces_valid_output`, and — incidentally —
both tests from mutation 1's set, because dropping generation 200
produces a `KeyError` in the decay-rate check at `t=200` before the
decay-rate assertion itself ever runs. This isn't the record naming the
wrong tests — both named tests do fail — it's the record understating
the mutation's actual blast radius by three tests it didn't anticipate.

Both corrections are now in the test file's docstring itself (the
"permanent record," per Section 7's requirement — not just in this
document), dated and attributed to this independent reproduction.

**Whether this reveals a process gap worth fixing generally, not just
this instance** (the question Section 7 requires asking every time): yes,
partially. Both overclaims share a pattern — reasoning about mutation
blast radius from first principles rather than actually running the
mutated suite and reading the output. This isn't a gap in the
constitution's *procedure* (Step 4 already requires independent
reproduction precisely because self-reported blast radius is unreliable)
— it's confirmation that the procedure is doing its job. No amendment
needed; the existing rule already catches exactly this class of error,
twice now across two different domains (Monte Carlo, Wright-Fisher).

## 3. Diff scope check

```
git show --stat 608e072
```

Seven files: `Tellurium/tellurium_engine.py`,
`Tellurium/tests/test_popgen_correctness.py`, `docs/adr/0005-rng-
convention.md`, `docs/adr/README.md` (index entry), and three
`Business/build-stages/STAGE_02_PART_0{1,2,3}.md` narrative files.
Matches Part 2's out-of-scope statement exactly — no changes outside
`tellurium_engine.py` and its tests, no new runtime dependency, nothing
touching the antimony/roadrunner pipeline (correctly, since this domain
is discrete per ADR 0002's pattern). Note: Part 3's committed version
(97 lines, three-implementer draft) is now stale relative to the
corrected two-implementer version edited in this conversation after the
commit — that correction hasn't been re-committed yet; it's a pending
follow-up for Part 5's close-out, not a discrepancy in the domain code
itself.

## 4. Result

Stage 2's implementation is verified: full suite passes, dependency guard
passes, both mutation tests independently reproduced (with the permanent
record corrected on both), diff scope matches spec. Ready to close in
Part 5.
