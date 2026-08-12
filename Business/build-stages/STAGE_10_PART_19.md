# Stage 10, Part 19 — harvest, not wire

Stage: 10 · Part: 19 · 2026-08-11

## 1. The method

Three orphans remained after Part 18, each a duplicate of a path that
already works: a second BRENDA client, a second literature service, a
second Python engine bridge. Wiring them would recreate exactly the
duplicate-source problem that produced a kcat labelled "mM" and a
`verifyDOI` that returned true for anything.

So instead: a subagent read each duplicate against its incumbent and
answered one question — *what does this do BETTER?* Across ~820 lines the
answer was **two things, both small**. Every finding below was verified
independently before being acted on.

## 2. Harvested: derived metrics, and a velocity bug in my own code

`tellurium-real.py` computed `conversionPercentage`, `maxVelocity` and
`avgVelocity` alongside the trajectory. The working path did not.

Taking the *idea* rather than the code mattered here, because reading it
carefully exposed a defect in what I had written in Part 9:

```ts
const velocity = previous && dt > 0 ? (previous.value - point.value) / dt : 0;
```

A backward difference against a non-existent predecessor, so the first
point reported **velocity 0**. For Michaelis-Menten, t=0 is where the rate
is *highest* — v₀ = Vmax·s₀/(Km+s₀). Reporting it as zero made
`maxVelocity` miss the true maximum and biased any average downward.

Fixed with a forward difference for that one point, and verified against
the closed form:

```
t=0 velocity : 0.09523593   (computed from the engine's trajectory)
Vmax·s0/(Km+s0): 0.09523810   (analytic)
```

Five significant figures. That agreement checks the fix *and* the engine's
trajectory against the rate law, rather than against itself.

The duplicate also clamped velocity with `max(0, v)` and commented
"velocity is always non-negative". Not taken: a negative velocity in an
irreversible reaction means an integration problem, and clamping it
guarantees the reader never sees the one signal that something is wrong.

## 3. Harvested: the CrossRef polite pool

`real-literature-service.ts` sent a `mailto:` User-Agent. CrossRef operates
a "polite pool" with materially better rate limits for clients that
identify themselves; `verifyDOI` sent no User-Agent at all.

Taken — but from `TERRIUM_CONTACT_EMAIL` rather than the hardcoded personal
address it contained. A fork should not silently identify itself as this
project's author.

## 4. Found while harvesting: the same defect, a fourth time

```ts
// In test environments, skip network verification
if (process.env.NODE_ENV === 'test') {
  return true; // Accept syntactically valid DOIs in tests
}
```

`verifyDOI` returned **true for any well-formed DOI whenever the suite
ran** — including `10.9999/completely-made-up`. A test suite running
against a verifier that cannot say "no" is testing nothing about
verification.

This is the fourth appearance of the defect this file spends most of its
comments on:

| # | where | how it returned true |
|---|---|---|
| 1 | `verifyDOI` (Part 6) | regex on the DOI's shape |
| 2 | `verifyReference` (Part 11) | accepted a DOI CrossRef said does not exist |
| 3 | `TERRIUM_SKIP_DOI_VERIFICATION` (Part 12) | skipping the lookup returned `verified` |
| 4 | `NODE_ENV === 'test'` (here) | bypass under test |

Each arrived by a different route, and each is the same mistake: **a
verdict that does not depend on what is being verified.** Test mode now
throws, which puts the caller on its `unverified` path — the truthful
state, since no registry was consulted — and names `primeRegistryCache` as
the way to seed a deterministic answer.

One existing test failed as a result, correctly. It asserted a DOI verified
with nothing seeded, which was only ever true because of the bypass; it
would have passed just as happily against a fabricated DOI. It now states
its premise — *given CrossRef says this resolves* — and a companion test
asserts the other half: a well-formed DOI the registry has not confirmed
does **not** verify.

## 5. Verdicts on the three duplicates

| module | verdict |
|---|---|
| `brenda-real.ts` | **Nothing to harvest.** It never parses BRENDA — it POSTs to a JSON API and relabels the response. It also defaults `kmUnit → 'mM'`, `vmaxUnit → 'μM/min'`, `temperature → 25`, `pH → 7.0` (STRENDA-governed fields the incumbent explicitly refuses to guess), scores a `dataQuality: 'excellent'` from fields it invented two lines earlier, and sends `ecnumber: ''` so the query is identical for every enzyme. |
| `real-literature-service.ts` | **One header.** Both PubMed calls use `rettype=json` where the parameter is `retmode`, so `response.json()` throws on every call; `validateDOI` returns `false` when CrossRef is unreachable (the Part 11 defect, mirrored); `year` falls back to the *current year* for an unparseable date. |
| `tellurium-real.py` | **The metrics idea.** It also does `km = input_data.get("km", 5.2)` — simulating on an invented 5.2 and returning `success: True` with it echoed back as though the caller had chosen it, which is precisely what ADR 0012/0013 forbid and what `run_mm` refuses. |

That last one is worth stating plainly: the duplicate contains the exact
behaviour the working path was written to prevent.

## 6. Verification

- `tsc --noEmit -p .`: 0 errors.
- Validation suites: **57 / 57** passing, including the two rewritten
  DOI tests.
- Metrics verified against the analytic Michaelis-Menten initial rate to 5
  significant figures.
- 95 tests passing across `src/validation`, `src/__tests__`,
  `src/execution`.

## 7. What is left

The three duplicates are now **read and understood**, and everything worth
taking has been taken. What remains in them is redundant or actively
wrong — `brenda-real.ts` in particular contains four separate instances of
the failure modes this repository documents.

They can be retired whenever you want; nothing is lost. The Orphan Module
Guard will keep reporting them until they go, which is the correct state:
they are code nothing calls.
