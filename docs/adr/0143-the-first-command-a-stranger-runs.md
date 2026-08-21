# ADR 0143: The first command a stranger runs

**Status:** Accepted, implemented. **The guard is expected RED** until the
repository is published — see "Why this ships red".

**Date:** 2026-08-21

**Context:** `scripts/check_quickstart_clone_works.py`, `README.md`,
`START_HERE.md`, the seventeen `docs/readmes/*.md`

## The finding

`START_HERE.md` opens:

> You are in the right place whether you are an intern joining the team or a
> stranger who found this on GitHub. This is the only document you have to
> read before you do something useful.

Its first command is:

```bash
git clone https://github.com/Terrium-sim/main.git
```

That repository is **not readable anonymously**. A stranger following the
only document they are asked to read gets a username prompt and stops on
line one, having seen nothing.

Nineteen documents give that command — `README.md`, `START_HERE.md`, and all
seventeen split-repo READMEs. Behind the prompt sit 2,220 tests, 68 guards
and 141 architecture decisions, none of which anyone can reach.

## Why this went unnoticed through twenty-six audits

`check_published_repo_readmes.py` has guarded those seventeen READMEs for a
while. It checks **what they say** — that a stranger landing on one finds an
orientation, a licence, a non-affiliation notice. It never asked whether the
command inside them runs.

Every guard in this directory protects a claim made *inside* the product.
Not one protected the claim that has to be true before any of those matter:
**that the thing can be obtained.** The most-audited repository I have
worked in was failing at the first line of its own front door, and the
reason is that no check ever left the building.

## Verified rather than asserted, which took three tries today

`git ls-remote` on the documented URL returns
`could not read Username for 'https://github.com'`. On its own that
sentence proves nothing — it is what you also get with no network, a
proxy, or a typo in the probe.

Three times earlier in this same session a probe of mine reported "it is not
there" when it meant "I could not see": `antimony==2.14.0`, then
`python-libsedml`, then a `cffconvert` conflict that was really `docopt`
being sdist-only. Twice I was one commit from rewriting a correct pin.

So the probe was validated before its output was believed:

| repository | expected | got |
|---|---|---|
| `sys-bio/tellurium` | cloneable | cloneable |
| `pnpm/pnpm` | cloneable | cloneable |
| `Terrium-sim/main` | — | **not cloneable** |
| `math12345678/terrium` | — | **not cloneable** |

The controls pass, so the negative is a fact about the repository and not
about the probe.

## The guard

`check_quickstart_clone_works.py` extracts every `git clone` from the
newcomer-facing documents and runs `git ls-remote` with
`GIT_TERMINAL_PROMPT=0` — exactly what a stranger's shell does, with the
prompt made impossible so the guard cannot hang.

**It probes the controls first, and this is the whole design.** A network
probe cannot distinguish "this repository is private" from "this machine has
no network", and reporting the first when it means the second would be the
seventh instance of this project's most frequent bug. So:

- controls fail → **exit 3**, "could not check", explicitly neither answer
- a documented URL fails → exit 1, a real finding
- all resolve → exit 0

A **negative control** (`sys-bio/this-repository-does-not-exist-9f3a`) is
asserted unreachable in `--selftest`. Without it, a probe that returned
"cloneable" unconditionally would pass both positive controls and vouch for
every URL in the tree.

The CI step is written `... || [ $? -eq 3 ]`, so an outage at GitHub does not
redden the build while a genuinely unobtainable quickstart does.

## Why this ships red

This is the first guard in the project deliberately wired while failing.

The standing rule is not to wire an *unverified* guard into a shared build,
and that rule is intact: this one has a passing selftest, two positive
controls and a negative control. What it reports is **true**.

The alternatives were to baseline it or to leave it unwired, and both are
the same move — recording the problem instead of fixing it, which is what
`docs/undelivered-fields-baseline.txt` says a list that only grows amounts
to. The fix is not a code change and is not mine to make: the repository
becomes readable, or the quickstart points somewhere that is. On that day
this goes green with no edit.

Until then CI names it on every run, which is what a build is for.

## Consequences

- The repository's single most important sentence is now checked by
  something that can fail.
- Guard count 67 → 68.
- A new class is now covered: claims that must hold **outside** the
  building. Sibling questions this guard does not yet ask — whether the
  documented package installs, whether the linked landing page loads —
  are named here so the gap is visible rather than assumed closed.
- The eighth recorded instance of *a matcher narrower than the thing it
  measures* is in this document as the reason the probe has controls, not
  as another entry in the list.

## Related

- `scripts/check_published_repo_readmes.py` — guards what those READMEs
  say, and never asked whether the command in them runs
- [ADR 0140](0140-the-step-named-install-pnpm-installed-no-pnpm.md) — the
  other check that reported success without doing its work
