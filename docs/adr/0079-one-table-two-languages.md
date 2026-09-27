# ADR 0079: One licence table, read by both languages

**Status:** Accepted, implemented

**Date:** 2026-08-15

**Relates to:** ADR 0063 (attribution travels with the model), ADR 0003 (two
copies of a numeric bound drifted), ADR 0027 (one score implemented twice),
ADR 0050 (provenance rides with the CSV), and Jeske's CC BY 4.0 obligations

## Context

ADR 0063 put BRENDA's attribution into the exported Antimony model and then,
on measuring, into SBML as well — because `NOTICE` stays in the repository
and those files leave.

**The trajectory CSV leaves too.** Its own module docstring says so:

> That file is the artifact which OUTLIVES THE SESSION. It gets opened in
> Excel, plotted, pasted into a lab report, mailed to a supervisor.

ADR 0050 gave it a full provenance header — origin, citation, organism,
assay conditions, every pool-level flag. It carried the resolved Km with
`BRENDA ref 740253` beside it and **no licence at all**.

### Why this could not just be fixed in place

The model exports are built in Python; the CSV is built in TypeScript.
Writing the licence into a TypeScript constant would be a second copy of it.

That is ADR 0003 (two copies of one numeric bound, drifted) and ADR 0027
(one reliability score implemented twice, the copies computing different
things) with a licence attached. A licence is a worse thing to be wrong
about than either: the failure is silent, and the party harmed is not the
person running the code.

Generating the TypeScript from the Python was considered and rejected.
`check_no_generated_files_tracked.py` puts the reason plainly — *"Every
serious defect this project has found lived in a copy nobody was watching"*
— and a generated, committed copy is still a copy.

## Decision

`docs/data-sources.json` is the table. Both languages **read** it at
runtime; neither owns it, and it is not generated, so it is a source file
rather than committed build output.

- `caterva/core/data_sources.py` loads it for the Antimony and SBML exports.
- `Science-Agent-Pipeline/.../lib/dataSources.ts` loads it for the CSV.
- `NOTICE` stays authoritative prose; every field is transcribed from it,
  and the existing guard fails when the two disagree.

Both readers refuse to degrade quietly: a missing or empty table raises
rather than returning nothing. Returning an empty list would strip
attribution from every export while every test asserting *"a file with no
resolved values credits nobody"* kept passing, and the first sign would be a
shipped file with no licence on it.

The CSV block obeys the same rule as the model block: a source is named only
when it supplied a value in **that** export. A CSV built from user-supplied
values credits nobody, and an unrecorded source produces a line saying its
terms are unknown rather than silence.

### The guard that keeps it one table

Reading one file only helps while both readers keep reading it. The failure
mode is a hurried edit inlining `"CC BY 4.0"` into one language *just for
now*, after which the two agree until the day they do not.

`check_data_source_attribution.py` now fails when either renderer contains a
licence **value** as a literal — creator, licence URI, or source URI. Clause
references in comments (`§3(a)(1)`, `§2(a)(6)`) are documentation and are
excluded, which required distinguishing code from prose: Python is parsed so
docstrings are excluded structurally, TypeScript has its comments stripped.

## Verification

`src/__tests__/dataSources.test.ts` (10) and the existing
`caterva/tests/test_data_sources.py` (16), asserting the CC BY clauses rather
than the wording so the block can be rephrased but not thinned.

Two tests exist specifically because the CSV is *data*:

- every attribution line begins with `#`, so `read_csv(comment="#")` skips it;
- stripping the `#` lines yields data byte-identical to a run without
  attribution — the licence notice cannot corrupt the file it is in.

Three mutations on the CSV path, all caught:

| Mutation | Failures |
|---|---|
| the block never reaches the CSV | 2 |
| every source credited regardless of contribution | 3 |
| attribution lines lose their `#` prefix | 2 |

### The literal-check shipped unable to catch its own case

Mutation: inline `https://creativecommons.org/licenses/by/4.0/` into the
TypeScript renderer. **The guard passed it.**

Its TypeScript comment-stripper was `re.sub(r"//.*$", "", line)` — and `//`
is both the comment marker and half of every URL. It deleted from the `//`
in `https://` onward, removing the licence URI from the very text being
searched for the licence URI.

That is the **fourth** time in this session that `//` handling has eaten a
URL: a test helper flattening Antimony comments, this guard's own
`_flatten`, and now its comment-stripper. In a codebase where every licence
and citation carries a URL, `//` is not safely a comment marker. Fixed with
`(?<!:)//`, and both renderers now fail the guard when mutated.

Found by mutation. Not by reading, and not by the guard's selftest — which
passes on the real tree, where no literal exists to find.

## Consequences

- Three export formats — Antimony, SBML, CSV — state one licence from one
  table. A fourth format reads the same file.
- Adding a source is adding a JSON object; no code changes in either
  language.
- `docs/data-sources.json` is a source file, not build output, so
  `check_no_generated_files_tracked.py` is unaffected.
- The Python and TypeScript renderers still format independently — one emits
  `//` comments and one `#` comments, with different wrapping. They share the
  facts, not the presentation, and only the facts are guarded.
