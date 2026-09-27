# ADR 0122: Fifteen domains nobody could find

**Status:** Accepted, implemented

**Date:** 2026-08-18

**Context:** `src/cli/commandDomains.ts`, `src/cli/domainCatalogue.ts`,
`scripts/check_domain_examples_run.py`,
`Science-Agent-Pipeline/artifacts/api-server/src/lib/caterva_runner.py`

## The product's breadth was invisible

Caterva advertises fifteen teaching domains. Nothing could tell a student
what they are.

| where a student would look | what it lists |
|---|---|
| `scientific help` | nine commands, all enzyme kinetics or generic |
| `python -m caterva.cli --help` | seven subcommands, all popgen and Gillespie |
| either, about the other | nothing |

Neither names epidemiology, PCR, Monte Carlo or molecular dynamics —
domains the engine runs, verified against closed-form solutions and
published minima, with over a thousand tests behind them.

**Two disjoint CLIs, and neither knows the other exists.** A capability
nobody can find is not a capability; [ADR 0090](0090-the-capability-nobody-could-reach.md)
says that about exported functions, and it is worse for a product surface,
because the person who cannot find it is the person the product is for.

`scientific domains` now prints all fifteen, each with a sentence saying
what question it answers and a command that runs it.

## The list is asked of the engine

`caterva_runner.py --list-domains` emits `DISPATCH` — the table the engine
actually dispatches on — so a domain cannot appear in the catalogue unless
it really runs, and cannot be missing from it because somebody forgot a doc.

That file already carried the warning: its membership test and its call site
once indexed two tables *"kept equal by hand (they have diverged before)"*.

Descriptions cannot be derived — generating one from an identifier produces
"Mm" and "Sir" — so they are written, and **reconciled**:

- **`undescribed`** — in `DISPATCH`, described nowhere. A domain the engine
  runs and no student can find: this defect, arriving again the next time
  somebody adds a domain.
- **`phantom`** — described here, absent from `DISPATCH`. Worse in kind: its
  example command cannot run, and a catalogue listing what the tool cannot
  do teaches a reader to distrust the rest of it.

Both are reported and fail the command, never filtered. Filtering would make
it a catalogue that agrees with itself and not with the engine.

`sbml` is excluded as the one judgement call — a generic ingest path, not a
teaching domain, which is why README says fifteen against DISPATCH's
sixteen. `check_documented_counts.py` declines to derive that number for the
same reason.

## The tests passed on a command that could not run

`domainCatalogue.test.ts` checks the examples *look* like commands: they
start with `simulate` or `python -m caterva.cli`, they contain a digit, they
carry no `<PLACEHOLDER>`. Thirty-six cases, all green — while this was in
the file:

```
python -m caterva.cli wf --n 100 --p0 0.5 --generations 200 --seed 1
```

`--n` and `--p0` are not flags. The real ones are `--population-size` and
`--starting-frequency`. **A shape assertion cannot tell the difference**,
which makes it the shape of a test that cannot fail — and I wrote it.

Running the example is what found it, which is the whole lesson of this
pass: the previous three passes were about verification machinery, and the
defect was found by pasting a command.

## Then the fix broke a working example

Reading the true flag names with

```
python3 -m caterva.cli ssa --help | grep -oE '\-\-[a-z-]+'
```

reported `--a` and `--b`. The character class has no digits, so `--a0`
arrived as `--a`, and a **correct** example was "corrected" into

```
ssa --bimolecular --a 100 --b 100 ...
error: ambiguous option: --b could match --bimolecular, --b0
```

Third time in one session that a matcher narrower than the thing it measures
produced a confident wrong answer ([ADR 0102](0102-the-probe-nobody-read.md),
[ADR 0104](0104-the-title-of-the-paper.md), here) — this time in the tooling
used to check the tooling, on a one-character omission.

All five engine examples are now verified by execution, not by reading.

## The guard that runs them

`check_domain_examples_run.py` extracts every `example:` from the catalogue
and **runs** the engine-CLI ones. Verified to fail: breaking one flag
produces exit 1 naming the command and the error.

Scope is stated rather than implied. Only the `python -m caterva.cli`
examples run here; the ten `simulate` ones need a Node toolchain and would
take the guard past the per-call ceiling several times over, so they stay
with `documentedExamplesRun.test.ts`. **A `simulate` example can rot without
this guard noticing**, and that is written into its docstring.

It also refuses to pass when it parses nothing — if the catalogue moves or
its quoting changes, "checked nothing" must not read as "checked and fine".

## Consequences

- 65 guards. `scientific domains` is the first command a student should run
  and the last one to have existed.
- The catalogue cannot silently drift from the engine in either direction.
- Ten `simulate` examples are covered only by the jest side, which — per
  [ADR 0119](0119-the-sentence-is-enough-if-you-confirm-it.md) — has a cache
  that can manufacture a false pass. Worth knowing before trusting them.

## Related

- [ADR 0090](0090-the-capability-nobody-could-reach.md) — a capability
  nobody can reach
- [ADR 0102](0102-the-probe-nobody-read.md),
  [ADR 0104](0104-the-title-of-the-paper.md) — a matcher narrower than what
  it measures, twice before
- [ADR 0115](0115-the-question-that-named-the-system.md),
  [ADR 0119](0119-the-sentence-is-enough-if-you-confirm-it.md) — the other
  two usability findings from running the product
