# ADR 0061: GPL code leaves the default install

**Status:** Accepted, implemented

**Date:** 2026-08-15

**Relates to:** ADR 0001 (no Tellurium umbrella package), the Apache-2.0
relicensing recorded at the end of LICENSE, NOTICE

## Context

A licence audit of every direct dependency, read from the installed
distributions' own licence files rather than from memory or a package index:

| package | licence |
|---|---|
| libroadrunner | Apache-2.0 |
| antimony | MIT |
| **python-libsbml** | **LGPL-2.1-or-later** |
| numpy, scipy, lxml, httpx | BSD-3-Clause |
| requests | Apache-2.0 |
| beautifulsoup4, pydantic, pytest | MIT |
| hypothesis | MPL-2.0 |
| **stdpopsim** | **GPL-3.0-or-later** |

Caterva declares Apache-2.0. Two entries need more than a row in a table.

### stdpopsim

GPL-3.0-or-later, and it was pinned in `requirements.txt` — so `make setup`
placed GPLv3 code into the default environment of a project whose LICENSE
says Apache-2.0.

Those licences are compatible in one direction only. Apache-2.0 code may be
taken into a GPLv3 work; GPLv3 code cannot be folded into a work distributed
under Apache-2.0 without the combination becoming GPLv3.

**Nothing was being violated.** Caterva has never bundled stdpopsim: pip
fetches it onto the user's machine, and running two separately-installed
packages together is use, not distribution. The GPL's obligations attach on
conveyance.

The problem was smaller and more this-project-shaped. A reader would have
had to open two licence files and reason about their interaction to learn
what a default install had given them. Caterva's whole claim is that nothing
should require that.

### The code already disagreed with the manifest

`Tests/popgen_resolver.py`:

```python
try:
    import stdpopsim
except ImportError:
    return PopgenResult(
        found=False,
        search_log=["stdpopsim is not installed; mutation rate cannot be resolved"],
    )
```

The 19 popgen tests skip cleanly when it is absent, and `make check` already
reports that skip as a warning. Every layer treated stdpopsim as optional
except the file that declared it required.

## Decision

`stdpopsim` moves to **`requirements-popgen.txt`**, installed only on
request. `requirements.txt` keeps a comment where the pin was, explaining
that the removal is a licence decision rather than a packaging preference —
so someone wondering where it went finds the answer at the place they look.

The default install now contains no copyleft code except python-libsbml,
whose LGPL is specifically designed for this use and which is not conveyed
anyway.

### python-libsbml, and the fact the position rests on

LGPL-2.1-or-later. The "Lesser" is the point: a work may *use* the library
without becoming LGPL. Its obligations — notice, and a recipient's ability
to relink against a modified libSBML — attach when the library is conveyed.

Caterva does not convey it. Nothing is vendored, and as of today the
repository has one CI workflow, `tests.yml`, which publishes nothing.

That last sentence is the entire compliance position, and it was a fact
nobody was watching. `.devcontainer/Dockerfile` runs
`pip install -r requirements-dev.txt`, so an image built from it **contains**
libSBML. Building it locally is private use; pushing it is conveyance. The
day someone adds a release job — a reasonable thing to want — the
obligations attach silently, and the person adding it has no reason to know.

**A legal position that depends on an unwatched fact is a coincidence, not a
position.**

So `scripts/check_release_artifacts.py` watches it. If a workflow gains a
step that pushes an image, uploads to PyPI or creates a release, the guard
requires NOTICE to carry a conveyance section naming the LGPL and GPL
obligations. It does not attempt to decide whether they are *met* — that
needs a lawyer and a look at the artifact — and says so.

## Verification

`check_release_artifacts.py --selftest` exercises six publishing forms and
five non-publishing ones directly, because on a clean tree the guard reports
zero findings forever and a detector matching nothing would report zero too.

Two mutations against the live tree:

| Mutation | Result |
|---|---|
| add a `docker/build-push-action` job | detected, both markers, exit 0 with the reminder |
| add publishing **and** strip NOTICE's conveyance section | exit 1 |

`check_dependency_licenses.py` (written concurrently, and better than what
this ADR would have produced) requires every direct dependency to have a
recorded grant, defaulting to fail. Its manifest list was
`("requirements.txt", "requirements-dev.txt")` — so `requirements-popgen.txt`,
created the same day and carrying the one GPL dependency in the project, was
invisible to the guard written to find exactly that. Changed to a glob.

That is the **fourth** instance of this shape found on 2026-08-15 alone:
`check_documented_counts` on one document, `check_no_unsourced_ui_numbers` on
HTML only, `check_forbidden_packages` on three named manifests, and this. A
correct check on too narrow a scope, four times, in one day, by four
different authors.

## Consequences

- A default `make setup` is Apache-2.0-compatible throughout. Someone
  packaging Caterva commercially does not inherit a GPL question they did
  not know they had.
- Population genetics costs one extra command and is documented in three
  places a person might look: README, `requirements.txt` where the pin used
  to be, and `requirements-popgen.txt` itself.
- CI does not install `requirements-popgen.txt`, so the 19 popgen tests skip
  there. That is a real reduction in coverage and it is the cost of this
  decision. `check_no_silent_skips.py` counts them, so the reduction is
  visible rather than absorbed.

## What this is not

This is not legal advice, and this ADR is not a substitute for counsel. It
records what the licence files in this tree say, checked mechanically so the
record cannot drift.

Two questions are deliberately left open because they need a lawyer, not a
guard:

- whether a source distribution that *names* a GPL dependency in an optional
  requirements file creates any obligation at all (the position taken here is
  that it does not, which is the common reading and not a settled one)
- what `Business/INCORPORATION_CHECKLIST.md` should say about all of this at
  incorporation

## Still outstanding

`@replit/connectors-sdk` is declared in `Science-Agent-Pipeline/package.json`,
imported by no source file, and ships **no licence field and no LICENSE
file** — no grant of permission to use it at all. It is the one genuinely
unsafe item in a tree of 494 packages.

Three `@replit/vite-plugin-*` packages are the same, and their call sites
have already been removed. What remains in all four cases is the manifest
entry, which needs `pnpm remove` and a lockfile regeneration:

```bash
cd Science-Agent-Pipeline && pnpm remove @replit/connectors-sdk
```

This could not be done here: the sandbox has no pnpm store matching the
committed lockfile, and forcing a reinstall would risk breaking
`pnpm install --frozen-lockfile` in CI for everyone. It needs a real
development machine. `check_dependency_licenses.py` fails the build until it
is done, which is the correct state — the build should be red while an
unlicensed dependency is declared.
