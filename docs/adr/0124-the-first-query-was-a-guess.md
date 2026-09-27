# ADR 0124: The first query was a guess

**Status:** Accepted, implemented

**Date:** 2026-08-18

**Context:** `Tests/enzyme_catalog.py`, `scripts/report_enzyme_catalog.py`,
`src/cli/scientificCLI.ts`

**Relates to:** ADR 0118 (a miss names the substrates), ADR 0120 (which
corrected it), ADR 0116 (a refusal hands you the next command), ADR 0122
(fifteen domains nobody could find — the same problem, one level up)

## The friction

Measured through the real resolver:

```
substrate="lactate"    -> found, 10.73
substrate="L-lactate"  -> found=False
```

BRENDA's label is `(S)-lactate`.

A student's first query guesses **three things at once**: the substrate's
exact label, an organism that actually has rows, and whether the enzyme
holds that quantity at all. A wrong guess on any of the three produces the
same `not_found`, and `not_found` is indistinguishable from *the literature
has nothing*.

ADR 0118 made the miss name the substrates, which helps — after a failure,
and only about one of the three. ADR 0116 hands you the next command after a
refusal. Both are repairs to the moment of failure. Neither removes the
reason the first command fails.

That is a fair description of a tool that does not feel like it fixes a
problem: its whole value is finding literature values, and finding out what
exists was left as the user's job.

## Decision

`scientific catalog <ec-number>` reports what one BRENDA page holds, per
quantity:

```
EC 1.1.1.27 — what BRENDA reports:
  km    8 row(s); substrates: (S)-lactate, NAD+, oxamate, pyruvate
  ki    no 'Ki Values' table on this page
  kcat  no 'Turnover Numbers' table on this page
  organisms: Homo sapiens, Sus scrofa
These are BRENDA's own labels. Use them exactly — Caterva does not
substitute a similar name, because a similar name can be a different
molecule.
```

Three properties are load-bearing.

**A missing table is `reported=False`, not an empty list.** ADR 0120 is
exactly what happens when that distinction is missing: the parser falls back
to whole-page scanning when a label is absent, so parsing anyway reports
another table's contents under this quantity's name. A catalog is the worst
possible place for that error, because a catalog is what a reader trusts
before they know anything.

**One fetch.** The three tables are on one page. `html_provider` is called
once and the result parsed three times, and a test asserts the count. Jeske
asked that tools be gentle with DSMZ's servers — it is why the bulk-download
route was adopted at all — and a discovery command that made three requests
to answer one question would be a poor way to honour that, with nothing in
the output to reveal it.

**No recommendation.** It reports; it does not rank, score or suggest which
substrate to use. That judgement is the reader's, and every other refusal in
this project exists to keep it there.

## What it does not fix

The catalog needs an EC number. A student who knows only "lactate
dehydrogenase" still resolves the name through UniProt first, and that path
has its own failure modes. Naming this because the temptation is to describe
the feature as though the guessing problem is now solved: one of the three
guesses is removed outright, one is answered, and the third — the enzyme's
identity — is untouched.

## Consequences

- The first command a student runs can succeed, and the substrate hint in
  ADR 0118 becomes the safety net it should always have been rather than
  the primary route to the database's vocabulary.
- The summary sentence is built in Python, where the wording was argued
  over, and the CLI prints it rather than rebuilding it — two renderers of
  one fact drift (ADR 0003).
- Four mutations, all caught: parsing a table that is not there, fetching
  the page once per quantity, calling a present-but-empty table usable, and
  dropping a quantity from the map.
- `check_scripts_reachable.py` is satisfied: the script is named by the CLI,
  and a jest test spawns the real command rather than importing the module.
