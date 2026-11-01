# ADR 0028: Buffers are compared by chemical identity, not by string

**Status:** Accepted, implemented

**Date:** 2026-08-14

**Relates to:** ADR 0026 (cross-parameter assay coherence), ADR 0010
(STRENDA assay conditions), ADR 0024 (the correspondence that produced
this), ADR 0012/0013 (never default a parameter)

## Context

Lisa Jeske named four things that make kinetic values incomparable across
papers:

> Reaction conditions: **pH value, temperature, cofactors, and buffers** play
> a huge role in the reactions. The values in BRENDA come from thousands of
> different papers, each with different laboratory conditions. If you simply
> mix these together, the simulation will end up calculating with "fantasy
> numbers".

ADR 0026 built the coherence check and compared **two** of the four. It said
so in its own consequences section rather than implying it had covered her
sentence. This closes the third.

The buffer was already parsed and carried on every resolved value since ADR
0010. It had never been compared.

## Why string equality is the wrong tool

The real strings in this repository's fixtures are:

```
"0.5 M Tris-HCl buffer"
"0.1 M MOPS buffer"
"phosphate"
```

`"0.5 M Tris-HCl buffer" !== "Tris-HCl"` is true as strings and false as
chemistry. A check built on string equality would report a difference
between two measurements made in the same buffer, and it would do it
constantly — the **false-positive** direction, which is the one that gets a
warning ignored. A warning that cries wolf on the common case trains the
reader to skip the line where the real finding will eventually appear.

That is a worse outcome than not building the check.

## Why the PubChem *parent* compound

Resolving each name to a PubChem compound id fixes the wording problem and
introduces a subtler one. Tris and Tris-HCl are different chemical entities
with different CIDs, and a biochemist calls them the same buffer. Reporting
them as different would be the same false positive wearing a lab coat.

PubChem models this directly: a salt's record carries a **parent compound**,
the neutral form, at `cids/JSON?cids_type=parent`. Tris-HCl's parent is
Tris. Identity is therefore compared at the parent — an assertion PubChem
makes about the compound, not a rule this file invents.

**That is the entire reason this goes to an API instead of a lookup table.**
A hardcoded synonym map (`"Tris-HCl" -> "Tris"`, `"PBS" -> "phosphate"`)
would be a set of chemistry claims with no source, embedded in a file nobody
reviews as chemistry, and wrong for every buffer nobody thought of.

## Decision

`Tests/buffer_identity.py` resolves a reported buffer string to a
`BufferIdentity`, and `assayCoherence.ts` compares the resolved identities.

### Three states, never two

`resolved` / `unresolvable` / `not_reported`, and the comparison yields
`same` / `different` / `unknown` / `not_reported`.

`BufferComparison.is_same` is written as `status == "same"` and **not** as
`status != "different"`. With the negative form every `unknown` and
`not_reported` reads as agreement — the inversion the three states exist to
prevent, and one a reviewer skims past. A test asserts the positive form
directly.

### Buffer never changes the pH/temperature verdict

`CoherenceReport.buffer` sits **alongside** `verdict`, not folded into it.

Folding was the obvious move and it is wrong. `verdict` answers "were these
measured at the same pH and temperature", which has a clean answer. Buffer
identity answers a second question whose most common honest answer is "the
sources did not say". Merging them would let a missing buffer string
downgrade a verdict about temperature — degrading a fact that *was*
established because a different fact was not.

Two tests pin this, and the mutation that folds them in fails.

### No string fallback, ever

When an identity is missing the comparison reports `not_reported` or
`unknown`. It does **not** fall back to comparing raw strings, even when
both strings are byte-identical. A fallback that is wrong in the common case
is worse than no fallback, and "identical strings" would be a different
claim than "same compound" reported under the same name.

### Concentration is dropped, and the record says so

`0.5 M Tris-HCl` and `10 mM Tris-HCl` resolve identically and are not the
same experimental condition. The concentration text is stripped for the
lookup and **kept** on the identity, and a `same` verdict states that
concentration was not compared. A limitation a reader can see is different
from one they have to infer.

### Network failure is not an error

A resolved kinetic value with an unresolved buffer is still a resolved
kinetic value. Refusing the lookup because PubChem was slow would turn an
enrichment into a dependency. The runner catches everything and emits
`status: "unresolvable"` with the reason; the coherence check reads that as
"could not check", never as "buffers agree".

A failed **parent** lookup degrades to the compound's own cid rather than
failing the identity: comparing on cid is still better than comparing on
strings, and only the salt/free-base case is lost.

### Lookups are cached, bounded

Without caching, every resolved value costs two PubChem round trips on the
hot path for a string drawn from a vocabulary of about sixteen buffers — a
model resolving a Km and a Ki would make four calls to learn two facts it
already had. Both lookups are memoised for the process lifetime, bounded at
256 entries: if the cache ever needs to be large the input is not a buffer
name and something upstream is wrong.

Only the **default** providers are cached. Injected providers are called
directly, so a test that counts calls counts them accurately — a cache that
swallowed the second call would make "this never hits the network"
untestable.

## Verification

`Tests/test_buffer_identity.py` (28) and nine mutations, all caught:

| Mutation | Failures |
|---|---|
| compare on cid, not parent (salt case) | 1 |
| `is_same` becomes the negative test | 3 |
| unresolvable treated as a match | 2 |
| a failed lookup raises instead of degrading | 1 |
| empty species is sent to PubChem anyway | 3 |
| concentration dropped from the record | 2 |
| a string cid is accepted | 1 |
| the `different` verdict stops naming the buffers | 1 |
| a parent-lookup failure fails the whole identity | 1 |

`assayCoherence.test.ts` (+9, 26 total) and six more, all caught — including
the two that matter most: folding buffer into the conditions verdict, and
adding a string-equality fallback.

**The network is never touched by a test.** Providers are injected
throughout, in the same shape as `taxonomy.py`'s lineage provider, and the
runner contract test stubs `resolve_identity` outright. A contract test that
reached PubChem would be a live-network test wearing a unit test's name.

PubChem is unreachable from the development sandbox (the proxy returns 403),
so **the live path is untested here** and that is stated rather than
implied. The fixtures use the real CIDs (Tris 6503, Tris-HCl 93573,
phosphate 1061, MOPS 70807) so they describe the API this code actually
talks to.

## Consequences

- `assayConditions.bufferIdentity` is new on the wire and in
  `ParameterProvenance`.
- `CoherenceReport.buffer` is new.
- Three exact-equality contract tests needed updating. They were right to
  fail; that is what a wire contract test is for.
- **Cofactors — the fourth item on Jeske's list — are still not extracted at
  all.** Not deferred quietly: BRENDA reports them in free-text commentary
  with no consistent form, and the parser has no cofactor field to carry.
  Named here so the gap is on the record rather than implied closed by an
  ADR about buffers.
- `_BUFFER_RE` in `assay_conditions.py` remains a hardcoded list of sixteen
  buffer names. It is a *lexicon for extraction*, not a chemistry claim —
  identity comes from PubChem — but it does bound which buffers can be
  recognised at all, and a buffer outside the list is invisible rather than
  `unresolvable`. That is the weaker of the two failure modes and it is
  still a limit worth naming.

## What this does not claim

Same buffer species is not same buffer *system*. Concentration, counter-ion
and ionic strength all affect kinetics and none are compared. This removes
the crudest disagreement — phosphate against Tris — and nothing beyond it.

Saying that plainly matters, because the risk of adding a check is that its
existence gets read as an endorsement of whatever survives it. That warning
is copied from `taxonomy.py` deliberately: it applies identically here, and
it is the sentence most likely to be dropped when someone summarises this
feature.
