# ADR 0119: The sentence is enough, if you confirm it

**Status:** Accepted, implemented

**Date:** 2026-08-18

**Context:** `src/cli/confirmSystem.ts`, `src/cli/suggestResolveCommand.ts`,
`src/cli/scientificCLI.ts`

**Follows:** [ADR 0115](0115-the-question-that-named-the-system.md), which
printed the command and left the real fix open.

## Six flags to run one simulation

```
scientific simulate "michaelis menten" --resolve \
  --enzyme "lactate dehydrogenase" --substrate "pyruvate" \
  --organism "Homo sapiens" --s0 10mM --enzyme-conc 0.001mM
```

That is not *"a student asks a question in plain language."* It is a student
retyping, in a syntax nothing showed them, three names they had already
written into their sentence.

`--resolve` refused without those flags, and the refusal's reason was good:

> The system is never inferred from the query text: attaching a real
> citation to a system you did not name is provenance for the wrong
> measurement.

## The constraint asks about a person, not a regex

That sentence forbids provenance for a system **nobody named**. So the
question it actually asks is whether a person named it — not whether a
regular expression was involved in reading it.

A confirmation answers that:

```
Your question names a system. Terrium read it as:

    enzyme      lactate dehydrogenase
    substrate   pyruvate
    organism    Homo sapiens

These decide which measurement gets cited. A wrong organism here
attaches a real reference to the wrong enzyme, which is worse than
no citation at all.

Resolve for this system? [y/N]
```

At the instant a citation becomes attachable, somebody has read the three
names and agreed to them. That is **more** explicit than three flags, which
are typed once and never re-read.

So the sentence is now enough:

```
$ simulate "michaelis menten of lactate dehydrogenase on pyruvate in Homo sapiens" \
    --resolve --s0 10mM --enzyme-conc 0.001mM
```

resolves Km = 10.73 mM from BRENDA ref 740253, with its reliability axes.

## The three ways this could become silent inference

Each is a mutation, and each is caught.

| # | mutation | result |
|---|---|---|
| Y1 | a bare return counts as consent | caught |
| Y2 | a headless run auto-confirms instead of refusing | caught |
| Y3 | `--yes` stops disclosing what it read | caught |

**Y1** is the likeliest careless change: `answer !== 'n'` reads as friendlier
and is the bug. An empty line is somebody pressing return to make a prompt
go away, and treating that as agreement makes the confirmation decorative —
present in review, functionally a silent inference. The default is no.

**Y2** is the one that would pass every interactive test, because those have
a terminal. With no TTY there is nobody to ask, so a pipe, a CI job or
`| head` gets a refusal and the explicit command — never a guess. A
default-confirm there is exactly what the constraint forbids, with a prompt
in the code that nobody ever sees.

**Y3**: `--yes` skips the *question*, not the *disclosure*. A batch run whose
citations came from a parse must say so in its own transcript, or nobody can
audit afterwards which system was cited.

## Y4 was reported NOT CAUGHT, and the verdict is wrong

Y4 mutates `plausible()` to accept any fragment, so a question that names
nothing would still produce a suggestion. Direct execution of the mutated
module:

```
under mutation -> {"enzyme":"model","substrate":"model","organism":"model"}
```

and the test asserts `toBeNull()` on that exact query. **The test must
fail.** Jest reported 15 of 15 passing.

The behaviour changed, an assertion covers it, and the runner did not see
the change — which is [ADR 0083](0083-the-harness-that-disagreed-with-itself.md)
verbatim: a JavaScript runner's transform cache manufacturing a false NOT
CAUGHT. `--no-cache` was passed **twice** (injected by `mutate.py`, and again
in the `--test` override) and did not prevent it.

`NOT-YET-REPRODUCIBLE.txt` recorded ADR 0083's fix as *"reasoned and
harmless, and unproven for the case it was written for"*, because the
confirming run never fit the sandbox ceiling. This is that case, in a suite
small enough to fit, and it says **the fix is not sufficient**. That file now
records it.

**No past verdict is retracted**, and the reason is ADR 0083's asymmetry: a
stale cache can only manufacture a false NOT CAUGHT, never a false "caught".
Every `caught` in this repository stands. What is now in doubt is every NOT
CAUGHT recorded against a jest suite.

Y4's property is verified — by the direct execution printed above — and
**not** by this harness. It is recorded as unverified-by-mutation rather than
claimed as caught, because a verdict the harness never established is the
thing this directory exists to prevent.

## Consequences

- A plain-language question plus `--s0`/`--enzyme-conc` runs a
  literature-backed simulation. Two flags, not six, and the two remaining
  are experimental conditions no database can report.
- `--yes` exists for scripts and still prints the parse.
- 30 tests across the two new modules; 9 of the parser's are about staying
  silent.
- **Open, and larger than this pass:** every NOT CAUGHT against a jest suite
  in this repository is now suspect. Somebody should find what actually
  defeats ts-jest's cache before another one is believed.

## Related

- [ADR 0115](0115-the-question-that-named-the-system.md) — the same defect,
  one step less far
- [ADR 0083](0083-the-harness-that-disagreed-with-itself.md) — the cache,
  and the asymmetry that saves the `caught` verdicts
- [ADR 0024](0024-refusing-versus-defaulting-an-unsourced-parameter.md) —
  Sauro on a tool that refuses without offering a way forward
