# ADR 0062: Permission is a licence, not an absence

**Status:** Accepted

**Date:** 2026-08-15

**Related:** ADR 0001 (no tellurium umbrella package), Constitution Rule 7,
`NOTICE` (BRENDA CC BY), `docs/LICENSING.md`, `docs/RENAME_PLAN.md`

## The question

"Take out all code related to Tellurium. I don't want to use things I don't
have permission for."

Taken literally, the first sentence deletes the project. Terrium's ODE
integration is libRoadRunner and its models are generated as Antimony, both
from the Sauro lab at the University of Washington — the group behind
Tellurium. 218 references across 25 files, underpinning all 15 domains.

## Decision

**Keep libRoadRunner and Antimony. Attribute them properly. Remove the four
packages that grant nothing.**

The reasoning turns on one distinction the request itself contains: a
licence **is** permission. libRoadRunner's own licence file says so in
plain English:

> You CAN freely download and use this software, in whole or in part, for
> personal, company internal, or commercial purposes;
>
> You CAN use the software in packages or distributions that you create.

Removing software whose authors have written an explicit invitation to use
it would not make Terrium safer. It would cost the integrator underneath
every domain and invalidate the closed-form and independent-integrator
correctness tests, and buy nothing.

The real exposure is the opposite case: software with **no** licence.
Silence is not permission.

## What the audit found

Verified rather than assumed:

- **No `tellurium` dependency** in any of the three manifests. Rule 7 holds.
- **No copied source.** No file carries a University of Washington,
  Caltech, Sauro or Analog Machine copyright header.
- **No vendored tree.** No `vendor/`, `third_party/`, `external/`.
- **Import only** — all use goes through public package APIs.

Two vestigial references removed: a dead `TELLURIUM_DIR` constant in
`verify_build.py` pointing at a directory that has never existed, and a
comment describing the engine as "Tellurium/libRoadRunner", which was false
and is exactly the sort of sentence that manufactures an impression of
affiliation on its own.

### The four that granted nothing

`@replit/connectors-sdk`, `@replit/vite-plugin-cartographer`,
`@replit/vite-plugin-dev-banner`, `@replit/vite-plugin-runtime-error-modal`
— each ships **no `license` field, no LICENSE file, no repository URL**.

One was never imported. The other three were, and
`vite-plugin-runtime-error-modal` was **not** gated on `REPL_ID` as the
other two were: it ran on every build of `terrium-landing` and
`mockup-sandbox`, production included. My first draft of the guard's
explanation claimed all three were gated. Reading the config disproved it,
and the recorded reason was corrected before it shipped.

All four call sites are removed, so no unlicensed code executes. Four
manifest entries remain, which need a `pnpm remove` this environment cannot
run — the lockfile must regenerate or `--frozen-lockfile` fails in CI. That
is the one outstanding action item, recorded in `docs/LICENSING.md` and
pinned by a test rather than a TODO.

## Making it checkable

`scripts/check_dependency_licenses.py` holds every direct dependency and
the grant it rests on, read from the licence text shipped in the installed
distribution rather than a package-index summary. **A dependency with no
entry fails.** The default is "go and look it up", not "assume it's fine".

It reports **three states, not two**: permission on record, installed and
declaring nothing, and not installed here so unverifiable. The first draft
collapsed the last two and accused `autoprefixer` — plainly MIT, merely
absent from this checkout — of the same defect as the `@replit` packages.
Reporting missing evidence as a finding is how a guard loses the
credibility it needs on the day it is right.

## Verification

Re-derivable as a set file — `docs/mutations/adr-0062-dependency-licences.json`:

```
python3 scripts/mutate.py --set docs/mutations/adr-0062-dependency-licences.json
```

All eight rows come back `caught` under the harness — the seven below
plus one added afterwards, that a recorded outstanding item must not
block `make guards`. The run needs `--only` to fit a time-limited
shell; nine suite runs is about 180 s. Original hand-run:

Seven mutations, `cmp`-verified backups:

| Mutation | Caught |
| --- | --- |
| An unlicensed package re-imported into a vite config | 1 failed |
| A `NO_GRANT` entry loses its reason | 2 failed |
| `libroadrunner` moved to `NO_GRANT` (deletes the engine) | 2 failed |
| A `PERMISSION` entry names a licence but records no grant | 1 failed |
| "Declares nothing" conflated with "not installed" | **NOT caught** |
| — after fix | 1 failed |
| Detector reports everything as unlicensed | 2 failed |

**Two self-inflicted defects worth recording.**

The first: reverting the three-state return passed all seven tests, because
the only assertion was `undeclared_now <= KNOWN_UNLICENSED` — vacuously
true when the detector finds nothing. Fixed by asserting the positive
direction first: the detector must actually *see* the four known offenders.

The second is worse, because it was in a test file whose whole subject is
this failure mode. The original pin read:

```python
assert still_present == KNOWN_UNLICENSED - (KNOWN_UNLICENSED - declared)
```

Both sides are `KNOWN_UNLICENSED & declared`. A set identity. It could not
fail under any input. Found by reading it back rather than by any tool.

## What this does not settle

The name. Terrium against Tellurium, two letters apart, same field, built
on the other project's libraries, with one documented instance of an expert
reading a cold email as a false claim of credit.

Licensing is settled and favourable. Trademark is not, and it is now the
larger exposure. `docs/RENAME_PLAN.md` costs it out: 452 files, 2,651
occurrences, and — a finding of its own — **two spellings already in use**,
`Terium` for the Python package you import and `Terrium` for everything
else, so you `pip install terrium` and then `import Terium`.

I first recorded that split as a live bug: that following the docs would
produce an ImportError. Checking it before acting showed otherwise. No
document tells anyone to `import Terrium`; all 17 `python -m Terium.cli`
invocations are correct. It is a cosmetic inconsistency, and the correction
matters because it changes the recommendation from "fix this now" to "fold
it into the rename" — a directory move is the most disruptive edit
available in a shared tree, and this one buys nothing urgent.

Nothing is on PyPI or npm and nothing carries a DOI, so every external cost
of renaming is currently zero and begins accruing at first publication.
That is an argument for deciding soon, not for deciding here. It is a
lawyer's call, and this document is not legal advice.
