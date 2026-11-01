# ADR 0067: A denial is not an attribution

**Status:** Accepted

**Date:** 2026-08-15

**Related:** ADR 0062 (permission is a licence), `docs/RENAME_PLAN.md`,
`NOTICE`, Constitution Rule 7

## The gap

The Tellurium non-affiliation notice lived in exactly two files: `README.md`
and `NOTICE`. Both stay in the repository.

Someone who runs `pip install caterva` never sees either. Nor does a
reference manager ingesting `CITATION.cff`, nor someone copying a BibTeX
entry off the landing page — which is precisely the moment a person decides
whose name goes in a paper.

That is the same shape as the BRENDA attribution before 2026-08-13: a real
obligation, correctly understood, present nowhere a downstream user would
encounter it. The notice was true and unreachable.

## Decision

The notice now reaches seven surfaces, chosen because each either travels
with the software or is read by someone deciding what to credit:

| surface | why |
|---|---|
| `NOTICE` | Apache 2.0 §4(d) makes it travel with redistribution |
| `README.md` | the repository front page |
| `CITATION.cff` | what a citation manager ingests |
| `pyproject.toml` | what PyPI displays |
| `package.json` | what npm displays |
| `caterva/__init__.py` | what `help(Caterva)` prints — travels with the *installed* package, which a README does not |
| `HowToCiteSection.tsx` | the landing page, where a reader picks whose name to write down |

`scripts/check_non_affiliation_notice.py` fails when any of them stops
saying it. A listed surface that has *disappeared* is a failure rather than
a skip: deleting the file is the easiest way to pass a checklist, and a
guard that shrugs at a missing file rewards exactly that.

## The distinction the title names

The guard requires two different things, and conflating them was the design
mistake worth recording.

**Disclaiming** — "Caterva is not Tellurium, and is unaffiliated with it" —
is Caterva's own problem. It protects the Sauro lab from being credited
with work that is not theirs, and protects Caterva from looking like it is
claiming otherwise.

**Attributing** — "Caterva runs on libRoadRunner (Apache 2.0, University of
Washington) and generates Antimony (MIT)" — is what those licences actually
ask for.

A surface that does only the first looks compliant and is not. It says who
Caterva is *not* built by while staying silent on who it *is* built on.
`MUST_CREDIT` requires libRoadRunner to be named alongside the disclaimer on
the five surfaces with room for a sentence; the two one-line package
descriptions carry the disclaimer only, because a PyPI summary field is not
where an attribution belongs and `NOTICE` ships in the same distribution.

## `NOTICE` in the distribution

`pyproject.toml` now declares `license-files = ["LICENSE", "NOTICE"]`
explicitly.

setuptools' default glob already includes `NOTICE*` — verified in its
`dist.py`, patterns `LICEN[CS]E*`, `COPYING*`, `NOTICE*`, `AUTHORS*` — so
this changes nothing today, and I checked before claiming a gap rather than
after. It is declared anyway because Apache 2.0 §4(d) is a licence
obligation, and an obligation that holds by default is one that a
setuptools change or a later explicit `license-files` entry could drop in
silence. This is the one file where "it works by default" is not a good
enough answer.

## Verification

Re-derivable as a set file — `docs/mutations/adr-0067-non-affiliation-notice.json`:

```
python3 scripts/mutate.py --set docs/mutations/adr-0067-non-affiliation-notice.json
```

All five `caught` under the harness. Original run:

Five mutations, `cmp`-verified backups, all caught:

| Mutation | Caught |
| --- | --- |
| The notice edited out of `CITATION.cff` | 1 failed |
| The package docstring loses it | 2 failed |
| A missing surface skipped instead of failed | 1 failed |
| The credit requirement dropped — denial without attribution passes | 1 failed |
| The checklist gutted to one surface | 1 failed |

The failing branches are exercised on constructed input via `monkeypatch`
rather than only against the live tree, because the tree is clean today: a
test asserting `main() == 0` would pass just as happily if the guard
stopped guarding. That lesson is from ADR 0062, where a mutation removing a
guard's entire purpose passed all seven of its tests for exactly that
reason.

## What this does not do

It does not resolve the trademark question. A disclaimer reduces confusion;
it does not create a right to the name. `docs/RENAME_PLAN.md` holds the
cost and the facts for an attorney, and the name remains unchosen.
