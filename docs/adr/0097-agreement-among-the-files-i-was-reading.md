# ADR 0097: Agreement among the files I was reading

**Status:** Accepted

**Date:** 2026-08-16

## Context

ADR 0093 found the clone URL stated three different ways and made
`README.md`, `START_HERE.md` and `CONTRIBUTING.md` agree. It picked
`Terrium-sim/terrium` because that is what `README.md` happened to say, and
closed with the claim that the entry points now agreed.

They did. The repository did not.

| spelling | references |
|---|---|
| `Terrium-sim/main` | **126** |
| `Terrium-sim/terrium` | 3 (all three written by that repair) |
| `math12345678/terrium` | 1 (`git remote get-url origin`) |

**The repair normalised onto the minority spelling and left the repository
more inconsistent than it found it**, while reporting the problem as fixed.
One `grep -c` across the tree would have shown which was load-bearing. It
was never run, because the audit was reading three files and those three
files were the whole of the evidence it consulted.

The 126 include the two surfaces that matter most:

- **`.github/ISSUE_TEMPLATE/config.yml`** — the five `contact_links` on the
  GitHub *New issue* page, routing people to `SUPPORT.md`, `START_HERE.md`,
  `docs/FIRST_TASKS.md`, `SECURITY.md` and `docs/INBOUND_LICENSE.md`. A
  would-be contributor reaches that page **before cloning anything**, and
  every one of those links 404s if the repo is not where they say.
- **`docs/REPO_MAP.md`** — still carrying
  `git clone --recursive https://github.com/Terrium-sim/main.git`: both
  halves of the defect ADR 0093 had just fixed, including the `--recursive`
  flag removed for doing nothing, in a document
  `DOCUMENTATION_INDEX.md` offers as *"find my way around the tree"*.

`config.yml` is YAML. An audit looking at markdown never saw it. **A
contributor-facing surface is not always a document.**

### The drafted public READMEs

`docs/readmes/` holds 17 READMEs for the repositories the split in
`docs/PUBLISHING.md` would create. `main.md` advertised:

```
make test      # 1,291 tests (1,014 engine + 277 literature)
```

against real figures of 1,997 / 1,142 / 855, and "23 ADRs" against 94.
Nothing checked them, on the reasoning that they are not live yet — which
is backwards. A stale number in an internal document costs a contributor an
hour. A stale number in a published README is the first paragraph a
stranger reads.

`docs/REPO_MAP.md` had a second defect of the same kind: it opened *"Terrium
**is** published as 18 repositories"*, present tense, for a split that has
not happened. A newcomer looking for `backend-main` goes hunting for a
repository that does not exist and concludes they have lost it.

## Decision

**`https://github.com/Terrium-sim/main` is the published location**,
confirmed by the owner. Every self-reference says so. `origin` remains
`math12345678/terrium`; both are true at once, and `START_HERE.md` says so
rather than leaving a newcomer to find the difference in `git remote -v`.

**A self-reference is identified by evidence, not by name.** A
`https://github.com/OWNER/REPO/blob/REF/PATH` URL whose `PATH` resolves to a
file *in this tree* is a claim about this repository, whoever it says owns
it. That rule correctly leaves the eighteen planned split repos alone:
`Terrium-sim/frontend-main/blob/main/src/...` names files that are not
these files.

**The scan reads every surface that names the repository**, not the three
documents someone was reading: `SUPPORT.md`, `SECURITY.md`,
`docs/REPO_MAP.md`, `.github/ISSUE_TEMPLATE/config.yml` and
`.github/PULL_REQUEST_TEMPLATE.md` alongside the entry points.

**`docs/readmes/` is checked like live documentation** and `--write` reaches
it. Adding 17 files to the guard while leaving them out of the fixer would
have turned one hand-edit into eighteen — the barrier ADR 0095 removed,
reintroduced by widening the check.

**Test counts are checked without guessing which suite they mean.**
`docs/readmes/terium.md` says `1,014 tests.` with no antecedent on the line.
The rule is that a figure must match *some* current suite; a number matching
none is stale whatever it referred to. `--write` does not correct these
outside the README, because picking a suite would be inventing an
attribution.

Two things that must not be flagged, both real sentences in the tree:

- `docs/readmes/business.md` — *"a guard that printed 'every collected test
  ran' while 275 tests failed"*. A count of tests that failed is not a count
  of tests.
- `docs/FIRST_TASKS.md` — cites *"22 guards and 1,291 tests"* as the defect
  it is warning about. The project already had the convention for this,
  used by `is_quoted`: **write a count plainly to assert it, quote it to
  cite it.** The sentence now uses the quotes and says why.

## Consequences

- The five links on the New Issue page point where the clone command points,
  and a test fails if they diverge.
- `docs/REPO_MAP.md` describes the split as a plan, and `--recursive` returns
  automatically — `test_recursive_is_not_promised_without_submodules` starts
  *requiring* it the moment a `.gitmodules` appears.
- 27 documents are now scanned for counts, up from 10.
- `docs/RENAME_PLAN.md` no longer carries the URL as an open question.

### What this does not fix

Whether `Terrium-sim/main` resolves is still unverifiable from here — no
network. What is now checked is that the repository has one answer, and that
the answer is the one the owner gave.

## Mutations

```
python3 scripts/mutate.py --set docs/mutations/adr-0097-agreement-among-the-files-i-was-reading.json
```

| id | mutation | result |
|---|---|---|
| S1 | the scan narrows to the three entry points | caught |
| S2 | a self-link is accepted without checking the path resolves here | **escaped first** |
| S3 | `clone_commands()` reads only the entry points | **four readings** |
| C4 | "275 tests failed" is read as a suite size | caught |
| C5 | the matcher stops honouring quotation | caught |
| C6 | an uncollected suite makes every count look stale | caught |
| C7 | the drafted public READMEs leave the checked set | caught |

**S2 escaped.** Deleting the path-existence check — the rule that makes this
evidence rather than a name match — passed all 23 tests, because every blob
URL in the real files happens to resolve. The rule was doing its job
invisibly and could have been removed without anything objecting.
`extract_self_links()` was split out so it could be tested on synthetic
input.

**S3 took four runs, and each wrong answer was wrong differently.**

1. `INDETERMINATE` — the search string matched two functions whose opening
   lines are identical. The harness refused to guess which it had edited.
2. `NOT CAUGHT`, **correctly**. Once `docs/REPO_MAP.md` was fixed there was
   nothing left for the wider scope to catch, so the scope could be reverted
   and the suite would agree. *Coverage that exists only while a defect
   exists is not coverage.* The scope is now asserted directly.
3. `NOT CAUGHT` again, **wrongly**. That new assertion took the union of
   `clone_commands()` and `self_links()`, so narrowing either one alone was
   still satisfied by the other — an assertion satisfied by the half that
   had not been broken. They are asserted separately now.
4. `NOT CAUGHT` a third time, and unreproducible: applying the identical
   edit by hand *did* fail the test. It went away after
   `rm -rf Tests/__pycache__`. **Stale bytecode produces a false NOT CAUGHT
   that is indistinguishable from a real gap** — the class of harness lie
   ADR 0069 exists to prevent, appearing in a new form.

## Related

- ADR 0093 — the repair this corrects
- ADR 0095 — `--write`, and the previous instance of a check widened while
  leaving an exemption inside it
- ADR 0069 — why mutation results ship as re-runnable set files
