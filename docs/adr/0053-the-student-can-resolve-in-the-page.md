# ADR 0053: The student can resolve a parameter in the page, with its provenance

**Status:** Accepted, implemented

**Date:** 2026-08-14

**Relates to:** ADR 0042 (stop displaying invented numbers), ADR 0044 (stop
offering invented ones), ADR 0048 (the harness that made this testable),
ADR 0024 (cross-species opt-in), ADR 0029 (variants), ADR 0012/0013
(measured quantity vs chosen condition)

## Context

Three passes closed three holes in the same wall and left the doorway open.

ADR 0042 removed seven fabricated metrics from the dashboard. ADR 0044
removed `km value="5.2"` from the form and rewrote the refusal so it names
what is missing. ADR 0048 built the harness that proves the refusal fires.

After all three, the page told a student *"this page will not invent a Km for
you"* — and then offered no way to get one. The resolver existed, the CLI
used it, the API server used it, and the surface a student actually opens
had no route to it. **A refusal with no alternative is not a standard, it is
an obstacle.** The honest reading of the previous state is that we had made
the page correct by making it useless.

## Decision

### `GET /api/resolve` in `src/web/server.ts`

It imports the **same** `resolveKinetic` the CLI imports. Not a second
implementation — ADR 0027 is what a second implementation costs, and the
parity test that was supposed to catch it could not, because it pinned two
implementations against a shared fixture rather than two call sites.

Three outcomes, deliberately distinct:

| Status | Meaning |
|---|---|
| `400` | the request did not name enzyme, substrate **and** organism |
| `200` `found: true/false` | the resolver looked, and did or did not find |
| `503 RESOLVER_UNAVAILABLE` | the resolver could not run |

The third is the one that matters. Folding it into `found: false` would make
"we could not look" read as "the literature has nothing" — a gap in *this
program* presented as a gap in *science*. That is the same category error
ADR 0012/0013 exist to prevent, one level up, and it is the third time this
project has had to name it.

### `resolveKm()` and `renderProvenance()` in `dashboard.html`

The endpoint returns the whole resolved object and the page renders it. The
number alone would be a worse product than a textbook: the citation, assay
conditions, protein variant, cofactors and reliability axes are the part that
makes it different from a guess.

Rendered, with what an absence looks like:

- **organism** — as returned, never as assumed
- **citation** — or *"none returned — treat as unverified"*
- **assay conditions** — or *"not reported"*, per condition
- **buffer identity** — the PubChem parent compound, or nothing at all when
  unresolved (a wrong buffer name is worse than no buffer name)
- **cross-species** — warned, never silent
- **variant** — including `unstated`, which is the majority case in BRENDA
  and is **not** wild-type
- **effectors** — absences printed as loudly as presences

### An `organism` field on the form

Added because the code did not have one and needed to. See below.

## The defect this feature introduced, and how it was caught

The first draft of `resolveKm()`:

```javascript
const organism = document.getElementById('organism')
  ? document.getElementById('organism').value
  : 'Homo sapiens';
```

The page had no `organism` element. So the ternary always took the second
branch, and the page would have quietly looked up a **human** Km for a
student who never said human.

Lisa Jeske's objection — that mixing conditions and species produces
*"fantasy numbers"* — is the reason ADR 0024 exists. **The substitution she
objected to was reintroduced by the feature built to honour her.**

It was not caught by reading the code. I read that code. It was caught by
writing the test, which had to ask "what does the page send?" and found the
answer was "something the student never typed."

The refusal now names each field separately:

```javascript
const need = [];
if (!enzyme) need.push('enzyme');
if (!substrate) need.push('substrate');
if (!organism) need.push('organism');
```

with the reason attached: *"An organism is required and is never assumed.
Kinetic parameters are species-specific, so 'the enzyme' does not have one
Km."* A student who reads "required field" types something plausible. A
student who reads *why* does not.

## Verification

Four mutations. The first is the one that earned the rewrite:

| Mutation | First run | After fix |
|---|---|---|
| restore `\|\| 'Homo sapiens'` | **passed** | 2 failures |
| drop the `503` branch, report it as `found: false` | 1 failure | — |
| fill the km field when `found: false` | 2 failures | — |
| stop rendering the `unstated` variant line | 1 failure | — |

The organism mutation passed because the single blanket refusal test blanked
enzyme **and** substrate at once, so it never isolated a missing organism.
Replaced with `it.each(['enzyme','substrate','organism'])` plus two tests
that check the organism is *sent*, not merely *demanded*.

**A test that blanks every field proves the form rejects an empty form. It
proves nothing about any one field.**

One false red on the way: `sends the organism the student typed` failed while
the code was correct — `URLSearchParams` encodes a space as `+`, which
`decodeURIComponent` leaves alone, so `Escherichia+coli` did not match.
Fixed in the assertion, not the code. Worth recording because the instinct
under a red test is to change the code.

25 tests. `tsc --noEmit` clean. `check_no_unsourced_ui_numbers.py` green —
the resolved Km is written at run time, which is exactly the distinction that
guard encodes.

## Consequences

- The dashboard is now a route into the literature rather than a wall in
  front of it. A student can type an enzyme, a substrate and an organism and
  get a value that arrives with its evidence.
- The provenance panel is verbose on purpose. Every line that reads *"not
  reported"* is a line that a prettier design would have omitted, and
  omitting it is how a value stops being distinguishable from a guess.
- `503` is now a shape the front end must handle. Any future client that
  treats non-200 as "not found" reintroduces the conflation; there is a test
  pinning the branch but nothing pinning future clients.

## What it does not do

The panel renders the reliability axes as returned. It does not weight them
against each other, because **Barbara Bakker has not answered how they weight
against each other** and inventing a weighting would be the same fabrication
in a more respectable costume.

Herbert Sauro's suggestion — default a missing Km to ~0.5 and warn — remains
unimplemented and undecided. This page refuses instead. That is a live
disagreement with a reviewer, not a settled question, and it is recorded here
so it stays visible rather than quietly hardening into policy by default.

Nothing here is rendered by a browser in CI. The VM harness runs the real
inline script against a stub DOM; a misspelled `onclick` still passes.
