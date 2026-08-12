# Stage 10, Part 18 — `sweep`, and a compiled copy of the whole source tree

Stage: 10 · Part: 18 · 2026-08-11

## 1. `dist/` was committed

The previous commit added **41 compiled `.js` files** to version control,
after `tsconfig.json` gained an `outDir` and lost `noEmit`.

That is the largest possible instance of the problem this codebase has
spent seventeen parts removing. `dist/src/units.js` is a second copy of
`src/units.ts` that goes stale the instant anyone edits the TypeScript, and
a reader who opens it gets a confident, wrong answer to "what does this
module do". Every serious defect this project has found lived in a copy
nobody was watching — a compiled mirror of the entire tree is that,
multiplied by the file count.

It is the third time in one session that derived files entered or nearly
entered git: `node_modules/` was untracked but unignored, `coverage/`
appeared after a coverage run, and now `dist/` was actually committed. None
of these is careless in isolation. They are what happens when several
agents move fast and `git add -A` is the habit.

So `scripts/check_no_generated_files_tracked.py` (guard #17) now fails the
build when git is TRACKING anything under a known-generated path. It reads
`git ls-files`, so it reflects the index rather than the filesystem —
building is fine, committing the build is not.

```bash
git rm -r --cached dist        # required: the guard fails until this runs
```

## 2. `sweep` — the analytics orphan, wired

`advanced-analytics.ts` was 363 lines of correlation, trend and outlier
detection that nothing imported. It now backs `scientific sweep`:

```
$ scientific sweep mm --parameter s0 --range 2:10:2 --km 0.5mM --vmax 0.1mM/s

Sweep: s0 from 2 to 10 step 2

      2  1.2393
      4  3.1236
      6  5.0829
      8  7.0623
     10  9.0499

  shape  ▁▃▄▆█
  trend  increasing  (slope 1.96e+0)
  range  1.2393 … 9.0499   mean 5.1116  sd 2.7663
```

A sweep that prints a column of numbers is a spreadsheet. The interpretation
is what makes it worth having, and here it shows real saturation kinetics:
a slope of ~0.98 per unit of s0 means nearly all additional substrate is
left unconsumed, because the enzyme is saturated. Outliers are flagged
separately, since a point that breaks the pattern is usually where the
model stops behaving like the rest of the range — worth looking at rather
than averaging away.

### Three defects fixed in `parameterSweep` before wiring it

1. **It passed only the swept parameter.** `parameters[parameter] = value`
   on an otherwise empty object, so km, vmax and s0 were absent from every
   run. Validation failed at every point, the `catch` swallowed it, and the
   function returned `[]` — which reads as "the sweep found nothing" rather
   than "the sweep never ran".
2. **Failures vanished.** A point that could not be computed was logged and
   skipped, making it indistinguishable from one that was computed and
   happened to sit on the trend line. They are now recorded with their
   reason and drawn as `·` in the shape line.
3. **Floating-point accumulation.** `for (let v = min; v <= max; v += step)`
   drifts; a sweep from 0 to 1 by 0.1 can stop at 0.9. Now indexed.

## 3. The validator was wrong about user-supplied values

The first sweep failed with `Parameter 'km': NO_LITERATURE` — for a Km the
user had typed on the command line.

That is the category error from Part 16 in a new form. Terrium's rule is
**an unsourced number must never be presented as sourced.** It is not *a
number you typed yourself may never be used*. Refusing to run made the tool
unusable for exactly the person it exists for: someone with their own bench
data, or a student deliberately exploring a range.

Layer 1 now distinguishes them by `origin`:

- `origin: 'user'` with no citation → **warning**, and the provenance table
  already reports it as user-supplied
- anything claiming to be *resolved* with no citation → **still a hard
  failure**, because that is a claim without evidence rather than an honest
  input

The distinction is carried on `ParameterMetadata.origin`, threaded through
`buildParameterMetadata`. Without it every unsourced parameter looked
identical to the validator, and an honest hand-entered Km was rejected as
harshly as a fabricated citation.

## 4. Verification

- `tsc --noEmit -p .`: 0 errors.
- Orphan Module Guard: **7 orphans (2,016 lines) → 3 (820 lines)** across
  Parts 16–18.
- Guard Wiring: **17 guards**, all reachable from a harness.
- `sweep` verified end to end against the real engine.
- 39 tests passing in the suites that could be run (`src/__tests__`,
  `src/execution`).

**Honest limitation, unchanged from Part 17:** this sandbox's filesystem
has degraded to where a single `ts-node` spawn takes ~30s, so jest suites
that spawn subprocesses exceed the 120s tool ceiling. Run `npx jest`
locally.

## 5. The three orphans that remain

| module | lines | why it is still here |
|---|---|---|
| `brenda-real.ts` | 235 | a second BRENDA client |
| `real-literature-service.ts` | 330 | a second literature service |
| `tellurium-real.py` | 255 | a second Python engine bridge |

These are the ones where "make it useful" and "one source of truth" pull
hardest against each other. Each duplicates a path that already works and
is tested. Giving them their own entry point would recreate precisely the
duplicate-source problem that produced a kcat labelled "mM", a `verifyDOI`
that returned true for anything, and a reproducibility verifier that could
not fail.

The useful move for these three is **harvest, not wire**: read each for
anything it does better than the incumbent — a parser that handles a case
the real one misses, a retry the real one lacks — fold that into the
working path, and retire the shell. That is a reading task rather than a
wiring task, and it should be done deliberately rather than to clear a
guard.
