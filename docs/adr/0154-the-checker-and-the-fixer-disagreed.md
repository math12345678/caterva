# ADR 0154 — The checker and the fixer disagreed

**Date:** 2026-08-22
**Status:** Accepted

## Context

`check_documented_counts.py` has two halves: a **checker** that finds stale
numbers and a **fixer** (`--write`) that corrects them. They use different
pattern sets, and nothing compared the two.

That gap produced four separate failures, all found in one sitting.

### 1. `--write` could not fix the split-repo READMEs

The fixer passed `{}` instead of the real counts to every document except
README.md, disabling test-count rewriting there entirely. The stated reason
was sound — a bare `1,014 tests.` has no antecedent on its line, so which
suite it means is a judgement, and guessing invents an attribution.

But the conclusion was wider than the reason. *"Test counts are never
written outside README"* covered lines like:

```
make test      # 2,267 tests (1,182 engine + 1,085 literature)
| the literature layer — BRENDA/PubMed resolvers, 1,085 tests |
```

which say exactly which suite they mean. So every commit that added a test
reddened CI on three documents that could only be repaired by hand — **four
times in one session** before anyone asked why. The barrier `--write` exists
to remove, reintroduced by the fixer that removes it.

### 2. `--write` was gated on the checker finding something

```python
if failures and "--write" in sys.argv:
```

So staleness the checker could not see was also unfixable, **even when
`rewrite` knew exactly how to fix it**. Two numbers sat wrong behind that
gate for months.

### 3. The README's test counts were checked by nothing

The scan loop skips README to avoid double-reporting guard and ADR counts,
which `main()` handles. But `main()` never ran `test_count_failures` on it.
So the only README test counts under any scrutiny were the ones the fixer's
five patterns happened to reach — while the guard printed

> OK: README test counts and domain counts match the repository.

Two were wrong at that moment, both in the command reference, the most-read
block in the project:

| line | said | actual | out by |
|---|---|---|---|
| `make test # run all ...` | 2,003 | 2,278 | 275, **12%** |
| `make test-sim ... (...)` | 1,142 | 1,182 | 40 |

The skip's own comment warns about exactly this: *"it is NOT a statement
that the README is checked more thoroughly. That is what this comment used
to say, and it was how '23 decision records' survived."* The comment was
corrected. The gap it described was not.

### 4. `runs all` and `run all`

The quickstart says "runs all N tests"; the command reference says "run all
N tests". The pattern matched only the first. One letter, and 2,003 drifted
275 out of date while its twin stayed current.

## Decision

- Patterns that read an attribution **the line makes itself** — `make test #
  N tests`, `N engine tests`, `literature layer … N tests`, `simulation
  engine … N tests`, `N domains, N tests` — and `actual` passed to every
  document. The original rule survives: a bare `1,014 tests.` still matches
  nothing and is still reported and left.
- `--write` runs unconditionally.
- README's test counts are checked, with `skips its 19 tests` excluded as a
  claim about one file rather than a suite. Deliberately narrow: an
  exclusion list that grows to cover every awkward case is how a check stops
  checking.
- `docs/readmes/terium.md` reworded from a wrapped `1,182 tests.` to `1,182
  engine tests.` — making the document say what it means is better than
  teaching the fixer to guess.

## Verification

- `--selftest` still passes: `rewrite()` changes digits and nothing else.
  That property is what makes six new patterns safe to add at once.
- **Mutation:** falsifying the README total to 9,999 now fails the guard
  naming `README.md:587`. Before this it passed. Restore verified by `diff`.
- The legitimate `skips its 19 tests` does not fire.
- Seven numbers corrected across four files on the first run, including a
  `literature layer only (847 tests)` that was **22%** out.

## A correction: the api-server job is not red

Three ADRs and several passes of this document have carried *"the api-server
CI job, red since 2026-08-05, still not reproducible here"* as an open item.

**It has been green since 2026-08-21.** Checked, not assumed:

| run | api-server |
|---|---|
| 755f9a8, Aug 21 01:08 | Failed in 28s |
| 7f7d212, Aug 21 22:29 | **Succeeded in 1m33s** |
| a4414d2, Aug 22 01:02 | **Succeeded in 1m40s** |
| 39b00ed, Aug 22 01:16 | **Succeeded in 1m35s** |

ADR 0140's `corepack enable` fixed it. The claim was repeated for three
passes after it stopped being true, because it was carried forward instead
of rechecked — which is precisely what ADR 0145 was written about, committed
the same day, by the same author. Writing the principle down does not
install it.

Also measured while chasing it, and worth recording because each was a
plausible cause that turned out to be wrong: the lockfile matches all nine
workspace manifests exactly; `@esbuild/linux-x64` and
`@rollup/rollup-linux-x64-gnu` are both present, so no macOS-only
resolution; and all 55 api-server test files pass on Linux across four
shards. Three hypotheses, none of them the answer, and the answer was a fix
that had already landed.

## Consequences

- A commit that adds a test no longer reddens CI on four documents.
- The README's own numbers are checked for the first time.
- **Still red in CI, and deliberately:** `check_quickstart_clone_works`,
  until the repositories are published (ADR 0143).

## Related

- [ADR 0145](0145-the-notice-that-outlives-its-subject.md) — a true sentence
  left standing after its subject changed, which this ADR then did
- [ADR 0140](0140-the-step-named-install-pnpm-installed-no-pnpm.md) — the
  fix that had already made api-server green
