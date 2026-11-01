# ADR 0090: The capability nobody could reach

**Status:** Accepted, implemented

**Date:** 2026-08-15

**Context:** `scripts/check_exports_reach_a_caller.py`, `docs/unwired-exports.txt`

**Follows:** [ADR 0087](0087-the-analysis-nothing-called.md), which wired one
orphaned capability by hand and left the general question open.

## The class, found three times by hand

An exported function nothing calls was computed for nobody. That is
[ADR 0039](0039-computed-and-never-delivered.md)'s defect at the scale of a
capability rather than a value, and this project has now hit it three times
without ever checking for it:

1. **`sbml-builder.ts`** — 424 lines and a full test file, and nothing in the
   product called it. The sentence recording it is still in
   `inhibitionModels.test.ts`: *"an orphan that looked covered because it had
   tests."*

2. **`rankModelsByFit`** — the function answering *which mechanism does my
   bench data support*, unwired for the life of the engine (ADR 0087). It is
   also where [ADR 0060](0060-the-model-that-never-ran-was-the-best-fit.md)'s
   defect sat unnoticed, a model that never ran ranking **first**. **Code
   nobody calls has no symptoms.**

3. **`compareModelPair`** — still unwired, recorded rather than fixed.

Three by hand is the argument for a check. [ADR 0045](0045-a-guard-for-the-boundary.md)'s
guard walks `KineticResult` **fields** to a rendering surface and has nothing
to say about a **function** nobody calls: the same question — *was this
computed for anyone?* — one level up.

## What the check found

Of 46 exported functions in `src/engine` and `src/storage`:

| | |
|---|---|
| called by the product | 37 |
| called only inside their own file | 2 |
| **never called at all** | **7** |

Seven capabilities, a sixth of the engine's public surface, reachable only
from tests.

## Three states, not two

The first version reported nine orphans. Two of those —
`countSweepSimulations` and `findRepositoryRoot` — are **called inside their
own file**. They are live code with a surplus `export`, which is a smaller
and different problem: telling somebody to *wire* a function whose real issue
is that it should not be *exported* sends them to fix the wrong thing.

So the check reports three states, and only the last one fails the build.
Same discipline as `resolved` / `unresolvable` / `not_reported`, and the same
reason: two of these look identical and are not.

## Being on the list is a legitimate answer

`docs/unwired-exports.txt` records all seven **with a reason each**, not a
rubber stamp:

- `createBatchJobs` and `buildSBML` are **superseded** — the product uses
  `createMultiParamBatchJobs` and the four specific SBML builders. A
  dispatcher beside four direct callers is a second way to answer one
  question, which ADR 0027 is about.
- `getModel` / `listModels` are **deliberately** unwired: wiring them "would
  have been a FIFTH implementation of enzyme kinetics."
- `compareModelPair` needs a route nothing asks for. ADR 0087 declined to
  invent one, and inventing a caller to satisfy a check is worse than the gap.
- `buildQueryUrl` and `clearSweepBatchMetrics` are utilities whose only
  consumer would be a UI that does not exist, and the test suite,
  respectively.

What is *not* legitimate is leaving the decision to be inferred from silence,
which is precisely what the three hand-found cases cost.

## Verified against its own failure modes

| scenario | expected | result |
|---|---|---|
| a new exported function nothing calls | exit 1 | ok |
| recording it in the baseline | exit 0 | ok |
| a baselined symbol that gains a caller | exit 1, names it | ok |
| an empty scan | exit 1, not OK | ok |

The third matters as much as the first: a list that can be added to but never
emptied records a problem instead of fixing it, which is the same rule
`check_mutation_tables_reproducible.py` runs on. The fourth is the standing
trap — a guard that examined nothing must not print OK, the same shape as the
citation guard that parsed zero entries and reported success.

### These were hand-verified first, which was not enough

The four scenarios were run by hand when the guard was written, and left at
that. Hand-verification is evidence about one moment; the guard could drift
afterwards and nothing would notice.

That is the same failure this project has now recorded four times under
different names — ADR 0058's M3 (a filter's necessity argued in a comment and
untested), ADR 0072's set file, ADR 0079's comment-stripper, and here. **A
property defended only in prose is a property that stops being checked.**

They are now a `--selftest` that builds a temporary tree, runs all four, and
is wired into `verify_build.py` beside the guard itself.

## Conservative by construction

A symbol counts as called if its name appears in any non-test source file
other than its own. That over-counts callers and so **under-reports**
orphans. Deliberate: a false orphan wastes somebody's time and teaches them
to distrust the check, while a missed orphan is only the status quo, which
this improves on gradually rather than all at once.

## Consequences

- Scope is `src/engine` and `src/storage`. The Science-Agent-Pipeline tree
  has its own structure and is not covered; stated rather than implied.
- Scope was widened one pass after this record was written — see below.

## The stated limitation, acted on

This ADR originally shipped matching `export function` only, and said:
*"widening it should come with a re-run of the baseline rather than an
assumption that the counts still hold."*

That sentence is how a limitation quietly becomes the scope, so it was acted
on rather than carried. Classes and `export const … =>` are now matched, and
the assumption was **counted rather than guessed**: the extra forms add 5
symbols to 46. Small — but "small" was a guess until it was measured.

It found one new orphan, and the interesting part is which:

> **`KineticSimulator`** — the class in `kinetic-models.ts`, the same module
> whose `getModel` and `listModels` were already recorded as deliberately
> unwired.

So the baseline held **two thirds of one deliberate decision** and looked
complete. Nothing about the record said a third export of that module
existed; the matcher simply could not see classes, and the list inherited
that blind spot without saying so.

**A baseline is only as honest as the matcher that fills it.** That is the
same shape as ADR 0026's set file running a narrower suite than the record
cited, and as the confident-false-negative this guard's own docstring warns
about — a matcher built from one example finding 3 of 37 and reporting the
rest as clean.

Re-running at the wider scope: 50 exports, 38 called, 4 internal-only, 8
recorded. The self-test now creates a class and an arrow const too, so the
widened matcher is exercised rather than assumed to work.

## Related

- [ADR 0087](0087-the-analysis-nothing-called.md) — the instance that
  prompted this
- [ADR 0045](0045-a-guard-for-the-boundary.md) — the same question about
  fields rather than functions
- [ADR 0072](0072-evidence-that-can-be-re-derived.md) — the shrinking-baseline
  pattern reused here
