# ADR 0116: The refusal hands you the next command

**Status:** Accepted, implemented

**Date:** 2026-08-17

**Answers:** ADR 0024 Decision 2 (Sauro), which has been open since the
expert replies came back

**Relates to:** ADR 0070 (a suggested command that cannot run is worse than
none), ADR 0077 (`--json` is one document)

## What was found

Terrium was used the way a student uses it, from a standing start:

```
$ simulate "lactate dehydrogenase"
  -> Query does not name a domain this pipeline knows (mm, sir)

$ simulate "michaelis menten" --resolve --substrate pyruvate \
    --organism "Homo sapiens" --enzyme "lactate dehydrogenase"
  -> Cannot run. These are unresolved:
       vmax (needs --enzyme-conc: ...)
       s0 (an experimental condition — supply it, e.g. --s0 10mM)
```

**Three attempts and six flags before a single number**, and at each stop
the tool named what was missing without saying what to type.

Every refusal above is scientifically correct. That is the problem: the
correctness was doing no work for the person in front of it.

## This is Sauro's objection, and it was still open

ADR 0024 records four experts giving three incompatible answers to "what
should a tool do with an unsourced parameter". Jeske's (cross-species
opt-in) and Bakker's (three reliability axes) were built. Sauro's was not:

> a refusing tool pushes people to "hardcode a number with no warning at
> all"

That is exactly what the screen above produces. A student stuck on `[E]0`
searches for a plausible enzyme concentration, pastes it in, and now holds
an unsourced parameter with **no record of where it came from** — strictly
worse than what the refusal was protecting them from, because at least the
refusal was visible.

The tool was optimising for not being wrong, and had stopped being useful.
Those are different goals and it had only noticed one of them.

## Decision

**The refusal stands. Nothing is defaulted, nothing is invented.** What
changes is that the way forward is on screen rather than left as an
exercise.

And the two kinds of blocker are told apart, because they need opposite
responses and the old output made them look identical:

| kind | what it means | what to do |
|---|---|---|
| `condition` | `s0`, `i0`, `[E]0` — describes YOUR experiment | you choose it; no database can report it |
| `literature` | `km`, `vmax`, `ki` — a measured quantity | cite a source, or widen the search |

That distinction is the substance. Telling a student "vmax is unresolved"
and "s0 is unresolved" in the same list implies both are gaps in Terrium's
coverage. One is. The other is a value that is *theirs to pick*, and saying
so converts a dead end into a decision they are qualified to make.

For a literature gap, the guidance points at `--cite`, which already
existed and which nothing pointed at from the one screen where a student
needs it:

```
--cite vmax="Smith 2019, PMID 12345"
  Terrium does not verify the source; it records that you supplied it.
```

That is the answer to Sauro. The student who was going to paste a number
anyway now pastes it *with its provenance attached*, and every downstream
surface marks it `user_cited` rather than `resolved`.

## Structure, not parsed prose

`Blocker[]` is collected alongside the existing `unresolved: string[]`.
Recovering the parameter and flag by parsing those sentences would be
parsing our own output — the duplicate-source-of-truth defect with a
formatting step in between, which in this same file once produced **zero**
MIRIAM annotations because a regex allowed four characters where the data
had five.

## The assertion that matters

Not that a "What to do next" section appears. A section of
plausible-looking flags that do not work would satisfy that and be worse
than silence — ADR 0070 is the precedent, where the CLI's own `help`
examples could not run for months.

So `refusalTellsYouWhatToDo.test.ts` **extracts the suggested flags and runs
them**, and requires the run to reach a *different* blocker. A suggestion
that reproduces the same refusal did nothing. A further test drives the
chain to completion and checks the Km is still the BRENDA-cited one — the
guidance must not have quietly replaced a resolved value with a typed one.

Verified end to end: refusal → guidance → refusal → guidance → a run with
`km 10.73 mM brenda_exact BRENDA ref 740253`.

## Two bugs found in writing the test, both mine

1. **`[a-z-]` where the data had digits.** The flag extractor matched
   `--enzyme-conc` and silently skipped `--s0` and `--i0`. It returned one
   flag instead of two and looked like it had worked; the failure surfaced
   later as "the suggestion did not fix s0". A pattern that matches a subset
   while looking complete is this project's recurring defect, and I wrote a
   fresh one.

2. **A killed process impersonating an exit code.** `e.status ?? 1` turned a
   spawn killed under load into `code 1` — the CLI's "could not perform the
   lookup" code — so an environment failure read as a product bug in the
   refusal path. The harness now throws on a null status instead. An
   environment failure must not be able to impersonate a result; that is the
   same rule the tool applies to its own exit codes.

## Consequences

- Mutation-tested: removing the `renderNextStep` call fails two of five.
- The guidance is prose, so it goes through the `say` sink and stays off
  stdout under `--json` (ADR 0077). A test asserts the document still
  parses and contains no guidance text.
- ADR 0024 Decision 2 can move from open to answered: **refuse, and hand
  over the means to proceed honestly.** Not defaulting, not guessing —
  making the honest path the easy one.
