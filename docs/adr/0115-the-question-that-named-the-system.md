# ADR 0115: The question that named the system

**Status:** Accepted, implemented

**Date:** 2026-08-18

**Context:** `src/cli/scientificCLI.ts`, `src/cli/suggestResolveCommand.ts`

## Found by using the product, not by auditing it

Every recent pass has been correctness infrastructure. This one started by
running the CLI as a student would, following the pitch:

> A student asks a question in plain language; Caterva finds the real
> parameters in the scientific literature, runs the simulation, and shows
> where every number came from.

```
$ simulate "simulate michaelis menten of lactate dehydrogenase on pyruvate in Homo sapiens"

ℹ Resolving parameters...
ℹ Validating against literature...

Validation errors:
  1. Parameter 'km': … no user-supplied value and no literature match
  2. Parameter 'vmax': … no user-supplied value and no literature match
  3. Parameter 's0': … no user-supplied value and no literature match

No trajectory was produced, so there are no results to show.
Supply the missing values in the query, or name a system to resolve
them from literature with --resolve.
```

**The headline claim does not work**, and the two things wrong with that
screen are different problems.

## 1. It said it searched the literature. It had not.

Fifteen lines above those messages:

```ts
pipeline.initializeLiterature([]);
```

An **empty** literature database, on purpose — the comment beside it says
*"This one runs the numbers you supply."* Nothing was resolved and no
literature was consulted, and then the tool printed *Resolving
parameters… / Validating against literature…* and reported "no literature
match" for every parameter.

A reader can only conclude Caterva looked and found nothing. That is false,
and it is false in the direction that makes the product look **empty rather
than misconfigured** — a student's reasonable next thought is "this database
has nothing in it," when in fact the search never ran.

Same class as the CLI line that claimed *"BRENDA and PubMed were searched and
returned nothing"* while holding the papers ([ADR 0109](0109-the-second-front-end.md)):
a reassuring progress message that is not true, in the one place the reader
cannot check it. The lines now describe what this path does.

## 2. It asked for something the student had already given

*"name a system to resolve them from literature with `--resolve`"* — to
somebody who had just named the enzyme, the substrate and the organism in
the sentence. The tool asked them to say it again, in a syntax it did not
show.

### Why it does not simply resolve

`ScientificPipelineRequest.system` is deliberately not inferred from the
query, and the reason is good enough to keep:

> Guessing an enzyme, substrate or organism out of free text would attach a
> real citation to a system the user never named — provenance for the wrong
> measurement, which is worse than no provenance.

That holds. A regex reading "lactate dehydrogenase" out of a sentence is not
evidence about what the student meant, and BRENDA ref 740253 stamped onto
the wrong system is a worse failure than refusing.

### Inferring silently and offering are not the same act

Nothing in `suggestResolveCommand.ts` resolves, cites, or runs. It prints a
command:

```
Your question names a system, so Caterva can look these up — it
just will not guess them out of a sentence. Run this and it will:

  scientific simulate "michaelis menten" --resolve \
    --enzyme "lactate dehydrogenase" \
    --substrate "pyruvate" \
    --organism "Homo sapiens" \
    --s0 10mM --enzyme-conc 0.001mM

Check the three names first. They were read from your question,
and a citation attached to the wrong system is worse than none.
```

The student reads the three names, and **by choosing to run it they have
named the system explicitly** — which is exactly what the constraint
requires. The guess never becomes provenance without a human in between.

This is the bridge between *refuses to invent* and *usable*, and it is
Herbert Sauro's objection answered on its own terms: a tool that refuses
without offering a way forward pushes people to hardcode a number somewhere
it carries no warning at all.

## Conservative on purpose

`parseSystemFromQuery` fires on four preposition-anchored patterns and
returns `null` otherwise. A wrong suggestion teaches a student the tool
guesses badly, which is worse than the generic message they were already
getting; no suggestion costs them nothing they had.

Nine of the fourteen tests are about **silence**: two of three parts named,
no system at all, bare numbers, an empty query, a fragment too long to be a
name, and a sentence that matches the shape while every captured fragment is
a noise word (`of the model on the model in the model`).

The suggested command includes `--s0` and `--enzyme-conc` with placeholders.
They are experimental conditions no database reports, and a suggestion that
still fails on the next run is worse than none — the reader would conclude
the tool is broken rather than that they owe it one more number.

## What was already fixed, by someone else, mid-pass

The same investigation found `blockers` — a five-site structure carrying
each unresolved parameter, the flag that supplies it, an example and a
reason — pushed to five times and **read zero times**, with a twenty-line
docstring explaining why leaving a student without it strands them.

A concurrent agent was fixing exactly that while this was being written, and
their version prints the complete runnable command at the end, which is
better than the draft here. Left alone rather than duplicated.

## Consequences

- The plain-language path now tells the truth about what it did, and hands
  back a command that works.
- `parseSystemFromQuery` is used for **display only**. If it is ever wired
  into resolution, the constraint above is what it breaks.
- Not addressed: `simulate` without `--resolve` still cannot resolve at all.
  Making the sentence itself sufficient — with a confirmation step — is the
  real fix, and it is a bigger change than this pass.

## Related

- [ADR 0109](0109-the-second-front-end.md) — a progress message that was
  false in the one place the reader could not check
- [ADR 0024](0024-refusing-versus-defaulting-an-unsourced-parameter.md) —
  Sauro on refusing versus defaulting
