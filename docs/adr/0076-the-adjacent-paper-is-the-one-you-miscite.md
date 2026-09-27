# ADR 0076: The adjacent paper is the one you miscite

**Status:** Accepted, implemented

**Date:** 2026-08-15

**Relates to:** ADR 0073 (cite the model, not the database), ADR 0008
(what `modelCitations` means), and the three DOI corrections recorded in
`verify_citations_live.py`

## Context

`verify_citations_live.py` asks CrossRef for the registered title of every
DOI Caterva cites and compares it to the title our own source claims. That
comparison is the strongest citation check in the project — the difference
between *the DOI resolves* and *the DOI is the paper we said it was*.

Its own file records three citations it exists to catch:

- a **fabricated** Michaelis-Menten DOI (`10.1111/j.1432-1033.1913...`) whose
  prefix belongs to a journal founded 54 years after the paper;
- a **recombination-rate** DOI cited to justify a **mutation** rate, which
  resolved cleanly and so passed an existence-only check;
- an Elowitz & Leibler DOI that was **wrong in five files at once**.

The comparison was:

```python
return len(claimed_words & registered_words) >= 2
```

### That threshold cannot catch the error that actually happens

Nobody mis-cites a paper about an unrelated subject. They cite the
**adjacent** paper — same author, same topic, a year apart — and adjacent
papers share vocabulary by construction.

Measured offline on two real papers this repository cites:

```
claimed:    "A general method for numerically simulating the stochastic
             time evolution of coupled chemical reactions"
                                        (Gillespie 1976, J. Comput. Phys.)
registered: "Exact stochastic simulation of coupled chemical reactions"
                                        (Gillespie 1977, J. Phys. Chem.)

shared content words: {chemical, coupled, reactions, stochastic}
                      4 >= 2  ->  "same paper"
```

The check catches the implausible error and passes the plausible one.

This is not hypothetical for this repository. `queryResolver.ts` cites
Gillespie **1977** for the SSA domains and `domain-literature.ts` cites
Gillespie **1976** — two defensible answers, in two files, for one model.
Whether the DOI recorded beside the 1976 title is the 1976 paper could not
be settled here: this environment cannot reach CrossRef (`httpx` needs
`socksio` for the sandbox proxy), and it is **not claimed either way**.
The ADR 0035 precedent applies — a claim measured off nothing is not a
claim.

### And "could not compare" read as "fine"

```python
if not claimed_words or not registered_words:
    return True  # nothing to compare -- do not manufacture a failure
```

Returning `True` makes an unmade comparison indistinguishable from a passed
one. That inversion is the defect class this repository has found more than
any other, sitting inside the citation checker.

## Decision

`compare_titles()` returns four states, not two:

| state | meaning |
|---|---|
| `match` | same work, allowing for our decorated titles |
| `mismatch` | fewer than two shared content words — the original check |
| `ambiguous` | shared vocabulary, **and each title carries distinctive words the other lacks** |
| `unknown` | one side had no comparable words; nothing was established |

Ambiguity requires a distinctive remainder **on both sides**, threshold two.
One extra word is punctuation or a subtitle; our stored titles append
journal/volume text and bracket translated originals, so the registered
title is routinely a subset of ours. Calling those ambiguous would flood the
report and get it muted — the cry-wolf reasoning of ADR 0028.

`_titles_overlap` is kept as a boolean wrapper where only `mismatch` is
False, so the pass/fail column keeps its meaning: an ambiguous pair is not
evidence of a wrong citation. It is surfaced in its own section, with both
titles, for a human to settle.

### What this does not do

It does not decide the Gillespie question. It makes the pair *visible*,
which it was not before, and says plainly that the automated comparison
cannot settle it.

## Verification

`Tests/test_citation_title_comparison.py` (11), and they need **no
network** — the titles are recorded fixtures from papers this repository
actually cites. That matters: the logic previously ran only behind `--live`,
so it was exercised only with a network and only when someone remembered.

Three mutations, all caught:

| Mutation | Failures |
|---|---|
| ambiguity collapses back to `match` (the original blind spot) | 1 |
| `unknown` reverts to a pass | 4 |
| `mismatch` softened to `ambiguous` | 1 |

`test_the_old_boolean_could_not_see_it` pins the gap itself rather than
describing it in prose, so a future change that makes the boolean strict
fails here and the reasoning gets re-read instead of silently outliving its
cause.

## Consequences

- The live report gains an ambiguity section. Exit status is unchanged —
  the script is a report, not a gate, by prior decision, and ambiguity is
  not evidence of error.
- The comparison logic is now testable and tested offline, independent of
  whether anyone runs `--live`.
- **Still unresolved, and deliberately not papered over:** the DOI↔title
  check is a *permanent* truth — DOIs do not rot — yet it lives in a script
  gated behind `--live` on the grounds that literature pages move. That
  justification is correct for URL reachability and does not transfer to
  DOI identity. Separating the stable half so it can run unasked needs a
  recorded CrossRef answer committed to the repository, which cannot be
  produced from this environment.
- `queryResolver.ts` and `domain-literature.ts` still give different years
  for the Gillespie SSA. Both are real papers and both are defensible; the
  project should say one thing.
