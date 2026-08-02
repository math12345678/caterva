# Stage 5 Part 2: the golden set and the mutation proof

Stage: 5 (the provenance contract) · Part: 2 · 2026-08-01

## 1. Answers to two of Stage 5's open questions

- **Question 3 (Rule 1 for provenance)**: a golden set of hand-verified
  enzyme/substrate/Km/citation tuples asserted end to end — delivered as
  `Tests/test_golden_set.py` plus the API-level mirror in
  `provenance.test.ts` (Target G).
- **Question 4 (mutation test for the resolver)**: swapping a returned Km
  for a plausible wrong value must make an end-to-end test fail. Both sides
  demonstrated live; the assertions are proven sensitive, not vacuous.

## 2. The golden set

Three tuples, hand-verified against the BRENDA fixtures (captures of real
BRENDA rows; the `*_realrows_debug.py` scripts verified them row by row):

| id | enzyme | substrate | organism | Km | source tier | BRENDA ref | flag |
|----|--------|-----------|----------|----|-------------|-----------|------|
| G1 | lactate dehydrogenase 1.1.1.27 | lactate | Homo sapiens | 10.73 mM | brenda_exact | 740253 | — |
| G2 | acetylcholinesterase 3.1.1.7 | acetyl thiocholine | Homo sapiens | 0.09 mM | brenda_exact | 649716 | — |
| G3 | lactate dehydrogenase 1.1.1.27 | lactate | Mus musculus | 0.0026 mM | brenda_cross_species | 740001 | cross-species (row is Sus scrofa) |

Every tuple is asserted in full — value, unit, organism, source tier,
reference id, URL, cross-species flag — through the **real** resolution
chain (`fallback_logic.resolve_kinetic_value` with the injectable fixture
providers; offline, no network). G3 also pins the deliberate semantics:
a query for an organism with no row falls back cross-species and is
**flagged**, with the row's real organism reported.

The API level mirrors G1 (the only tuple the resolver can reach
deterministically): the science-agent mock payload in `provenance.test.ts`
**is** the captured golden record, so the TS pairing must preserve the
literature tuple. Target G asserts `parameters.km === 10.73`,
`citation` contains `(ref 740253)` and the BRENDA URL, `organism ===
"Homo sapiens"`, `source === "brenda_exact"`, and the flag names 10.73.

## 3. Mutation proof (question 4) — demonstrated live

"Swap a returned Km for a plausible wrong-organism value and require an
end-to-end test to fail. If nothing fails, the trust trail is decorative."

**Python side.** Mutated `fallback_logic.py:176` row selection from
`min(...)` to `max(...)` — the exact-match tier then picks the LDH
fixture's 21.78 mM cancer-tissue row instead of the golden 10.73 (a
plausible-but-wrong value). Ran the golden suite:

```
FAILED Tests/test_golden_set.py::test_golden_tuple_end_to_end[G1: LDH/lactate/Homo sapiens]
E   Expected: 10.73 ± 1.1e-05
```

Mutation reverted; suite green again (6 passed).

**TypeScript side.** Mutated `queryResolver.ts` to drop the `citation`
field from the resolved branch — the "citation and the number it supports
should not be separable by a refactor" case. The provenance suite plus
routes failed **8 tests across 2 files** (`provenance.test.ts`: Target C,
Target F locator path, Target G, mutation predictions; `routes.test.ts`:
the MM resolve route). Mutation reverted; 124 tests green.

**Permanent guard.** Target G's sensitivity test (`provenance.test.ts`):
the agent is made to return the G3 record (0.0026 mM / Sus scrofa /
ref 740001 — a plausible wrong answer for a human query) and the test
asserts the response differs from golden on `km`, citation, and organism.
If a refactor ever lets the swap through, the G1 assertions fail.

## 4. Finding: the cross-species flag dies at the runner boundary

`science_agent_runner.py` drops `cross_species_flag` (only `source`
survives, as the string `brenda_cross_species`). The API therefore cannot
today distinguish "exact match, verified" from "cross-species, flagged"
except by string-matching the source. This is exactly the material for
**question 2** (the `verified`/`flagged`/`rejected` contract): the flag
must cross the boundary as a first-class field before the contract can be
honest. Carried to Part 3.

## 5. Status

Complete and committed. Carried forward:

- question 1 — provenance travelling **with** the parameter through the
  engine (the golden set now guards the pairing at both boundaries; the
  engine-internal channel question remains),
- question 2 — the `verified`/`flagged`/`rejected` citation contract
  (needs the runner to pass `cross_species_flag`; see §4),
- question 5 — widening `km`-in-`mm` vs making narrowness explicit.
