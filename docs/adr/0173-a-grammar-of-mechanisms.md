# ADR 0173: A grammar of mechanisms — composing models deterministically, and checking their dimensions

**Status:** Accepted

**Date:** 2026-09-07

**Relates to:** ADR 0172 (the assay window, written concurrently), ADR 0170 (a model is a value — the reaction-network IR this
emits), ADR 0171 (the agent architecture that parameterises what this
builds), ADR 0013 (Vmax is never resolved), ADR 0044 (a pre-filled
experimental condition is not fabrication), ADR 0028 (a check that fires too
broadly stops being read).

## Context

The front door answers three of twenty realistic queries. Measured, with a
committed harness (`frontDoorCoverage.test.ts`).

Of the seventeen refusals, **eleven are compositional**: a three-step
phosphorylation cascade, two enzymes competing for one substrate, a toggle
switch, an open system with constant inflow, feedback inhibition in a
pathway. None is in the catalogue and none ever will be, because the set of
compositions is not enumerable — "three step" becomes "four step", and a
catalogue entry is needed for each.

Terrium already has a path meant for this: `networkResolver.ts` asks a
language model for the structure. It returns `null` without an API key,
which is the state of this checkout and of any deployment nobody has
configured. The capability is unavailable exactly when a lab tries the tool
for the first time.

But the mechanisms a teaching lab asks about are not a long tail. A cascade,
a toggle switch, competition, feedback — these have canonical structures
that have not changed since the 1970s, and recognising them is pattern
matching rather than inference.

## Decision

`Terium/compose/` is a deterministic compositional model builder.

```
motifs.py     what a motif is: ports, parameters, rate-law templates
library.py    thirteen mechanisms, each carrying its licensing assumption
builder.py    instantiation, prefixing, and three wiring operators
units.py      unit algebra and dimensional checking of rate laws
grammar.py    English -> composition, with no language model
pipeline.py   the join to the agent architecture
```

Four decisions carry it.

### 1. Recognise a SHAPE, never a SUBJECT

"Cascade" is a shape. "Glycolysis" is a subject. A grammar that produced
*something* for glycolysis would produce a plausible wrong pathway — the
failure that is worse than a refusal, and the reason
`UnrecognizedQueryError` exists at all. Named pathways are refused with the
reason (they need KEGG or Reactome, which Terrium does not read) and that
refusal is carried through the runner as a distinct `kind`, because "I do
not know that word" and "that needs a database I do not have" send a
researcher to different places.

### 2. Writing the mechanism out removes the quantity that had to be refused

A catalytic step is

```
kcat * E * S / (Km + S)
```

not the textbook `Vmax * S / (Km + S)`. The two are the same equation with
`Vmax = kcat × [E]₀`, and the difference is entirely about provenance.
`Vmax` is a single parameter no paper can supply for YOUR assay, so ADR 0013
blocks it forever. `kcat` and `Km` are properties of the enzyme that BRENDA
holds, and `E` is a species whose initial concentration is a scenario choice
like any other starting amount.

**Composed models are therefore MORE resolvable than catalogue ones.** The
fabrication the catalogue has to refuse does not arise, because the lumped
parameter that caused it is gone. A test asserts no motif ever reintroduces
one.

### 3. Dimensional checking, with scale

A rate law with the wrong dimensions parses, compiles, integrates, and draws
a smooth curve that is wrong by whatever factor the mistake introduced.
Nothing downstream looks. `units.py` checks every composed rate law at
composition time — before anything compiles, so a model that will be refused
costs nothing to refuse.

It tracks **scale as well as dimension**, which plain dimensional analysis
cannot: mM and µM have identical dimensions and differ by a thousand.

And it handles **symbolic exponents**, which a naive checker must give up
on. `K^n / (K^n + X^n)` is dimensionless for every n — but only because the
same symbol raises bases with the same units. Tracking which symbol carries
which dimensions lets the addition be confirmed and the division cancel;
without it, every cooperative term in biology reads as unverifiable. The
scale under an exponent is tracked too, so `K^n + R^n` with K in mM and R in
µM is reported as differing by `1000^n` — an unknown amount, and certainly
an error.

### 4. Nothing is searched for when nothing was named

A composed model of "two enzymes competing for the same substrate" has four
unknown constants and no subject. Sending scouts would return "not found"
four times and report a failed search that never happened. The honest output
is the structure plus the list of measurements that would complete it: a
smaller claim than a simulation and a more useful one than a refusal.

The subject is never inferred. "A MAP kinase cascade" does not silently
become MAP2K1 — that would attach a real protein's measured constants to a
generic three-tier model, which is ADR 0076's adjacent-paper miscitation in
other clothes.

## Consequences

**Eleven of twenty benchmark queries build**, and the nine refusals are
almost exactly the catalogue's own queries — epidemiology, population
genetics, PCR. The paths are complementary rather than competing, and a
regression in either direction is pinned by `TestCoverage`.

**It works with no API key**, offline, and gives the same answer every time.
That is the property the language-model path cannot offer and the reason
this exists alongside it rather than instead of it.

**Conservation laws are derived, not asserted.** A three-tier cascade yields
`tier1_X + tier1_Xp` per tier without anyone saying phosphorylation conserves
protein. The competition case yields `enzyme1_S + enzyme1_P + enzyme2_P` —
one pool feeding two products, which is the proof that the competition is
real rather than two enzymes with private substrates.

**An open system is reported by naming what it does NOT conserve.** The
binary "are there laws" question misses the point: an open system still
conserves its enzyme, while the fed species appears in no law at all.

### Three bugs found by the tests, recorded because each is a class

- `"a"` was in the number words, so **"a phosphorylation cascade" parsed as
  a one-tier cascade** — an indefinite article read as a count, producing a
  model that is not a cascade while looking like a successful match.
- The competition rule required the prefix `"compet"`, so **"competitive
  inhibition of an enzyme by a substrate analogue" built an enzyme
  COMPETITION model** — a completely different model, silently, from a
  phrase that names its own mechanism. Found by writing the test that proves
  priority decides between two matching rules: the ordering was right and
  the matching was not.
- The cascade-wiring test built its own composition instead of going through
  `recognise()`, so mutating the grammar's wiring left it passing — the most
  important biochemical property in the module, tested where it could not
  see the code that decides it.

### What this does not do

- **No named pathways.** Refused with the reason, as above.
- **Feedback is noted, not wired.** "MAP kinase cascade with negative
  feedback" is a real request, and ERK feeds back on both SOS and Raf by
  different routes. Picking one would be inventing a mechanism, so the model
  is built without it and the note says so — which is a different thing from
  silently omitting it.
- **No epidemiology or population genetics motifs.** Those are the
  catalogue's, and reaching for them here would duplicate a verified
  implementation with an unverified one.
