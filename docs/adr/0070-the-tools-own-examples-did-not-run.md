# ADR 0070: The tool's own examples did not run

**Status:** Accepted, implemented

**Date:** 2026-08-15

**Relates to:** ADR 0066, 0059, 0049 (the same method — running the product —
finding the previous three), ADR 0015 (a rule nothing executes is not
enforced; documentation nothing executes is not documentation)

## What was found

Copying an example out of `scientific help` and running it verbatim.

### `sweep` — the example could only fail

```
$ sweep --parameter s0 --range 1:20:1 --km 0.5mM --vmax 0.1mM/s
✗ Every point in the sweep failed. The first reason was:
    Query 'sweep' does not name a domain this pipeline knows (mm, sir).
```

The dispatcher read the model from `rest[0]`, and when absent defaulted it to
the literal string `'sweep'`:

```ts
query: rest[0] && !rest[0].startsWith('--') ? rest[0] : 'sweep',
```

`'sweep'` is not a domain, so every point failed. The example — printed in
`help` and again in the command's own usage error — omitted the model, so it
could only ever produce that failure.

A default that is guaranteed to fail is worse than a required argument. It
defers the refusal until after N simulations have been attempted, and it
reports a usage mistake as a modelling failure. The model is now required,
and refused with the reason the rest of the CLI gives: the system is never
inferred, because sweeping the wrong one is not a partial answer.

### `validate` — the command could not succeed for any input

```
$ validate "lactate dehydrogenase km=5.2"
✗ VALIDATION FAILED
  1. Query '...' does not name a domain this pipeline knows (mm, sir)
```

Two separate defects. The example named no domain — but fixing only that
exposed the real one:

```
$ validate "michaelis menten" --km 5.2 --vmax 12.8 --s0 10
  1. Parameter 'km': Required parameter 'km' for domain 'mm' has no
     user-supplied value and no literature match
```

`commandValidate(query, params?)` builds its parameters from `params`. **No
call site ever passed one.** `params` was always `undefined`, the object was
always `{}`, and every required parameter was reported missing no matter what
the user typed. `validate` could not succeed for any input, ever.

An optional argument that every call site omits is a dead parameter, and the
branch reading it is unexercised code — which is where confidently wrong
behaviour lives. `simulate`, two cases below in the same switch, has always
built and passed this. The two drifted apart silently because nothing
compared them.

## Decision

Fix all three, and **make the examples executable documentation**.

`src/cli/__tests__/documentedExamplesRun.test.ts` extracts the `Example:`
lines from the CLI's real `help` output and runs each one.

The examples are **read out of `help`, not listed in the test**. A hardcoded
copy would be a second source of truth that keeps passing after someone edits
the help text — verifying the copy, which is the failure this repository has
now found three times (ADR 0034, ADR 0036).

## What it deliberately does not cover, and why that is stated

Only examples that succeed with no network and no prior state are asserted to
exit 0. The rest are excluded **by name, with a reason each**:

| example | why excluded |
|---|---|
| `resolve` | reaches BRENDA/PubMed over the network |
| `literature` | reaches PubMed and CrossRef |
| `corpus` | needs a BRENDA bulk download the user fetches themselves |
| `verify job_001` | the job id is illustrative and has no record |
| `check-integrity job_001` | same illustrative id |

All nine are still checked for a *dispatchable command name*, which is cheap
and catches a rename.

Two assertions guard the guard:

- **The extraction found something.** If the `Example:` regex silently
  matched nothing, every other assertion would pass vacuously. It requires at
  least five.
- **The offline set spans at least three commands.** Otherwise someone could
  make this file green by moving every command into the exclusion list, and
  the suite would pass over an empty set.

## Consequences

- Mutation-tested: restoring the old `sweep` example fails the suite and
  names it — `$ scientific sweep --parameter s0 --range 1:20:1 ...  exit 1` —
  with the tail of its output. Reported for all failing examples together
  rather than one at a time, since fixing one and re-running a
  ninety-second suite between each is how the second one gets left.
- `validate`'s help entry now describes what it does (checks parameters are
  present, plausible and dimensionally sound, without running the model) and
  says parameters are flags rather than text inside the query string. The old
  entry, "Validate a query against literature", described the literature
  fetch that ADR 0059 removed as misleading.
- This is the fourth defect in four passes found by running the product
  rather than reading it, and the third of those that no unit test could have
  caught: the failures live in argument dispatch, in cross-process state, and
  in documentation — three places unit tests do not look.
