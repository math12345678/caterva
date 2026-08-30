# ADR 0170: Fluent invention is not usage

**Status:** Accepted — recording a rejected approach

**Date:** 2026-08-23

## Context

After ADR 0169 the classifier's largest remaining error was no longer
scoring. It was **coverage**: 37 queries across the three independent
fixtures matched no keyword at all and were answered `mm` by fallback — 21 of
72 in one fixture alone.

They fail because students paraphrase. The fixtures ask for the repressilator
as *"that biological timer circuit I read about"*, for two-locus
recombination as *"genes mixing and swapping"*, for predator-prey as
*"hunters and hunted"*. No one writing a keyword table from a paper's title
thinks to include those.

The vocabulary that would fix it is sitting in the fixtures, and reading it
off them is precisely what must not happen: terms lifted from the test set
make the test pass and measure nothing. That is ADR 0191's shared-author
failure one level down — instead of writing the questions and the vocabulary,
one would be writing the vocabulary *from* the questions.

## Decision

**Ask a model for the lay vocabulary, from the domain definition alone — and,
having measured it, reject the result.**

A generator asked `mistral-small-latest` for the everyday words a student
might use for each domain, shown only `DOMAIN_MEANINGS[domain]`: one
sentence, the same one the resolver sees, never the fixtures and never the
keyword table. Mistral was chosen because it authored one fixture and not the
other two, so the Groq and OpenRouter sets stayed held-out for this change.

It produced 251 terms across 13 domains, filtered for length (≥4 characters,
after ADR 0192's `"ki"` detour), for genericness, and for cross-domain
collisions.

**The approach does not work, and the code is reverted.**

## Verification

| fixture | before merge | after merge |
|---|---|---|
| Groq `gpt-oss-120b`, 78 (held out) | 89.7% | 89.7% |
| OpenRouter `gpt-4o-mini`, 78 (held out) | 76.9% | **78.2%** |
| Mistral, 72 (vocabulary source — no longer independent) | 56.9% | 56.9% |

One query, on one fixture, for 251 terms and a generation-and-merge pipeline.

The reason is visible in the terms themselves. Asked for how a student
describes the repressilator, the model returned:

> gene timer · molecular switch · **buzzing genes** · pulsing dna · gene clock ·
> rhythmic genes · toggle switch · **gene flicker** · blinking genes ·
> **gene heartbeat** · stop-start genes · **gene pendulum** · gene flash ·
> **gene metronome** · gene wave · **gene chatter** · gene rhythm ·
> gene switchboard · **gene bounce**

Fluent, evocative, and not what anybody writes. Against the three real
repressilator queries that fell through, those nineteen terms score **zero
hits**. Across the whole set: **7 of 251 terms match any of the 228 fixture
queries.** Ninety-seven per cent is dead weight.

The finding generalises past this table. A model asked *"what words would
someone use"* answers from fluency, not from usage — it produces plausible
paraphrase rather than observed paraphrase, and the two are not close. Which
is notable given that the same model, asked to *be* a student and write a
query, produces usable text: **generating an instance works, describing the
distribution does not.**

Also measured, since ADR 0169 promised to re-check it before any vocabulary
widening: **over-promotion remained zero** across all 228 queries with the
251 terms merged. That risk did not materialise. It is simply that the terms
never fired.

## Consequences

`generateDomainVocabulary.ts` and the merge in `queryResolver.ts` are
deleted. The generated file is kept at
`docs/measurements/adr-0170-generated-vocabulary.json`, marked REJECTED, with
the prompt recorded so the measurement can be redone. **Nothing reads it.**

Classifier behaviour is unchanged from ADR 0169: 89.7% / 76.9% / 56.9%, 696
tests passing. This record adds no code. It exists so the next person to
notice the coverage gap does not spend the same afternoon on the same idea.

**What this does not check.**

- **One generator, one model, one prompt.** A different model, or a prompt
  asking for completions of real student sentences rather than a list of
  terms, might do better. Nothing here tests that, and the negative result
  should not be read as "no LLM can supply vocabulary" — only that this
  straightforward way of asking produced almost nothing usable.
- **The coverage gap is untouched.** 37 fallbacks remain, and this record
  makes no progress on them. It closes off one route.
- **The obvious remaining route is the one that cannot be taken cleanly.**
  The paraphrases in the fixtures would work, and using them would make the
  fixtures worthless as measurement. Real student queries would solve both
  problems at once and nobody has collected any — which is now the third
  consecutive record to end on that sentence.
