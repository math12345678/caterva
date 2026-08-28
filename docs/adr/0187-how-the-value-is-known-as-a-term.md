# ADR 0187: How the value is known, as a term

**Status:** Accepted, implemented

**Date:** 2026-08-28

**Context:** `Terium/core/sbml_provenance.py`, `Terium/core/miriam.py`,
`Tests/fixtures/identifiers/identifiers_org_namespaces.json`

**Closes a gap named in:** [ADR 0181](0181-what-seven-people-who-build-this-said.md)

## Context

ADR 0181 recorded seven experts' replies and listed, unadopted:

> **Evidence codes are not adopted**, only noted as the answer to a question
> this project already half-solved.

John Gennari, asked whether there is an accepted way to mark an annotation
as computed rather than taken from a source (personal communication,
2026-08-27):

> Yes! There is an established way to indicate an annotation is computed and
> predicted rather than "from the source": An evidence code.

**This is also the one CVTerm use Frank Bergmann's advice positively
endorses.** He warned that provenance *prose* in a CVTerm "changes the
semantic intent … tools reading them would expect them to be ontology-based
not a form of provenance". An ECO term is ontology-based: a class from a
published ontology, resolvable, meaning the same thing to every reader. The
two pieces of advice fit together —

| what | where | on whose advice |
|---|---|---|
| prose | `notes` | Smith, Bergmann |
| identity — which paper, which organism | CVTerm | MIRIAM, pre-existing |
| **how it is known** | **CVTerm, as an ECO class** | Gennari + Bergmann |

## What was researched

ECO (Evidence and Conclusion Ontology) has >1500 terms, is used by GO,
UniProt and model-organism databases, and **is already used inside SBML** —
published genome-scale models carry SBO and ECO terms together. So this is
not a Terrium invention laid over a standard.

Labels were read from the EBI Ontology Lookup Service rather than recalled:

- `ECO:0000269` — *experimental evidence used in manual assertion*
- `ECO:0000501` — *evidence used in automatic assertion*
- `ECO:0000305` — *curator inference used in manual assertion*
- `ECO:0000035` — *no evidence data found*
- `ECO:0008004` — *machine learning method evidence used in automatic assertion*

## Decision

**One origin gets a term, and the reason the others do not is the finding.**

```
resolved  a measurement curated from a publication -> ECO:0000269
user      the person chose it                      -> no term, deliberately
llm       a language model produced it             -> never exported
default   nothing was found                        -> never exported
```

`resolved` is `ECO:0000269`: *experimental* because BRENDA's rows come from
measurements, *manual assertion* because a curator made the claim.

**`user` is not weakly-evidenced — it is not evidence.** An s0 of 10 mM is a
condition of the experiment being run, not a claim about the world, and an
evidence ontology has nothing to say about it. `ECO:0000035` ("no evidence
data found") would be actively wrong: nobody looked for evidence, because
none was called for. Leaving it unannotated is the accurate statement, and
the notes already say the value was supplied.

`llm` and `default` block the run (ADR 0011), so a model carrying one never
reaches the exporter. `ECO:0008004` exists and would fit an LLM-produced
number; mapping it would describe a case that cannot occur.

**Why bother, when the parameter already cites a paper.** A citation says
*which* paper. It does not say whether that paper measured the value,
computed it, or asserted it in passing — which is exactly Gennari's
distinction. It also becomes load-bearing if Terrium ever ships estimated
parameters: Kummer and Milo both argued it should (ADR 0181), Milo asking
for estimates to be given "a very clear different form". An evidence code is
that form, in a vocabulary the field already reads.

## The URI would not have resolved

Adding `eco` to `MINTABLE` and stopping there emits a **dead link**.

`mint()` builds `{BASE}/{prefix}:{accession}`, and ECO accessions already
carry their prefix, so that yields `eco:ECO:0000269` — a double prefix.
Measured:

```
https://identifiers.org/eco:ECO:0000269   404
https://identifiers.org/eco/ECO:0000269   200
```

The colon form is correct for every namespace Terrium already mints —
`pubmed`, `taxonomy`, `doi` and `ec-code` were all checked at the same time
and all resolve — so this is an exception, not a correction.

`mint()`'s own refusal message already names the outcome it could not yet
detect: *"minting it anyway would produce a link that does not resolve."*
That is what it would have done, inside an annotation whose whole purpose is
to be followable.

## And the registry contradicts itself

identifiers.org publishes ECO with `pattern: ^ECO:\d{7}$` and
`sampleId: 0000006`. **The sample does not match the pattern.** The pattern
is the one that is right — the published sample 404s, the pattern-conforming
form resolves.

The fixture keeps the registry's value verbatim. It is a *capture*, and
editing it to be self-consistent would turn a record of what the registry
says into a record of what we wish it said, while destroying the evidence
for the exemption. `test_every_registry_sample_id_mints_in_its_own_namespace`
exempts `eco` and **asserts the failure in the other direction**: the sample
must still be rejected, so if identifiers.org fixes its entry the test fails
and the exemption goes.

## Verification

- Exported OMEX carries three CVTerms on a resolved km — the paper, the
  evidence class, the organism — with `triplesReadBack: 3`, an independent
  parser finding all three in the bytes.
- A `user` parameter carries no `identifiers.org/eco/` URI.
- `mint("eco", ...)` accepts `ECO:0000269`, refuses `0000269` and `ECO:269`.
- **2,345 passed, 1 failed** across both suites; the one failure is the
  known `node_modules` licence test for a JS package.

**Eight existing tests failed first**, all asserting a parameter's complete
URI list. `read_back` is qualifier-blind, so the evidence term appeared in
assertions about *identity*. They now use `identity_uris`, which excludes
the evidence class — a narrowing of scope, not a weakening, since the
evidence term is asserted directly by its own test. The count test went 3→4
and now names all four, because a bare count nobody can decompose is a
number that drifts silently.

## Consequences

- Every exported model states, in a vocabulary the field reads, how each
  sourced value is known — not merely which paper it came from.
- The mechanism that would let Terrium mark an estimate exists, before the
  decision about whether to allow estimates is made.

**What this does not check.**

- **Nobody has read one of these back in COPASI or Tellurium.** Unchanged
  from ADR 0181; libSBML round-trips it, which is evidence and not proof.
- **`ECO:0000269` is a judgement about BRENDA.** It assumes BRENDA's rows
  are experimental measurements curated by a person. That is what BRENDA
  documents; it was not verified row by row, and a computationally-derived
  row would be mislabelled.
- **`bqbiol:isDescribedBy` is the qualifier, and it is imperfect.** The
  parameter is not *described by* an evidence class so much as it *has* one.
  No biological qualifier means "has evidence"; this is the closest, and
  published models use it the same way.
- **The mapping has one entry.** Four origins, one term. That is honest
  today and would need revisiting the moment an origin is added.