# Stage 10, Part 21 — the README, and nineteen tests that stopped running

Stage: 10 · Part: 21 · 2026-08-11

## 1. The tool was undocumented

The README's opening line promises exactly what the CLI now does — *"resolves
the real parameters from the literature, runs the simulation, and shows its
work"* — and then never showed anyone how. It mentioned `history`,
`sensitivity`, `--model` and `scientificCLI` **zero times** between them.

For something meant to be picked up and used, that is the largest remaining
gap: five commands built over the last six parts that a new reader had no
way to discover.

Added a **Using it** section covering `resolve`, `simulate --resolve`,
`--sensitivity`, `--model`, `sweep` and `history`, with real verified output
rather than invented examples, plus the environment variables and — the part
that matters most — the three exit codes and why they are three:

| exit | meaning |
|---|---|
| 0 | found |
| 2 | the literature genuinely has nothing |
| 1 | the lookup could not be performed |

## 2. Nineteen tests had stopped running

Updating the documented test count surfaced something better than a
documentation fix: the count had gone **down**, 294 → 275.

`Tests/test_popgen_resolver.py` now begins with

```python
pytest.importorskip("stdpopsim", reason="stdpopsim not installed; see requirements.txt")
```

added by a concurrent agent with a careful, well-argued comment. And it is
the right call: 19 hard failures for a missing system library are noise, not
signal. `stdpopsim` needs `libgsl-dev` and is genuinely absent in some
environments — ADR 0021 already records the review sandbox as one.

But the comment's premise is not quite right. It calls stdpopsim "a heavy,
**optional** package". It is pinned at `stdpopsim==0.3.0` in
`requirements.txt`, and `Tests/popgen_resolver.py` uses it as the literature
source for mutation rates. Its absence is a broken environment, not an
optional state.

**What the skip leaves behind is the problem.** A clean skip is invisible in
a CI summary. The population-genetics literature path can go entirely
untested for months and still read as green — which is precisely the failure
mode the comment says it wants to avoid ("indistinguishable, from a CI
summary, from an actual regression"), just relocated.

And `scripts/check_env.py` — the thing `make check` runs, which verifies
roadrunner, antimony, libsbml, numpy, scipy, pytest and hypothesis — did
**not** check stdpopsim. So nothing anywhere reported the gap.

The skip stays. What was missing is the other half:

```
Literature resolvers
  WARN  stdpopsim (population-genetics mutation rates) missing --
        popgen mutation-rate resolution is UNTESTED and unavailable;
        test_popgen_resolver.py will skip silently.
        Install with: pip install stdpopsim (needs libgsl-dev on Debian/Ubuntu)
```

A warning rather than a failure: the engine and every other resolver work
without it, and `make check` is the gate for "is this stack usable". But the
gap is now reported **once, clearly, in the place people look** — rather
than as nineteen tests that quietly stopped running.

The README says so too, next to the test count, so the number and its
caveat travel together.

## 3. Why the count guard earned its place

`check_documented_counts.py` is a guard I have twice found mildly annoying —
it fails the build when a README number drifts from reality. It has now
twice been the thing that caught something real:

- Part 15: I had added tests without updating the count.
- Here: it caught nineteen tests that had *silently stopped running*.

The second is the interesting one. Nothing else in the repository would have
noticed. The suite was green, the guards were green, and a whole domain's
literature path had gone dark.

## 4. Verification

- `check_documented_counts.py`: passes (1,289 = 1,014 engine + 275
  literature).
- `check_env.py`: reports the stdpopsim gap; exits 0, since it is a warning.
- `check_citation_format.py`, `check_guard_wiring.py`: pass.
- `check_no_orphan_modules.py`: still reports the three known duplicates,
  which is the correct state.

## 5. Open

Unchanged from Part 20: the vacuous `kcatProvenance.test.ts` assertion,
opt-in locator consistency in `provenance.ts`, and four dormant silent skips
in `verify_citations_live.py`. Plus the three duplicate modules, which are
read and understood and can be retired whenever you like.
