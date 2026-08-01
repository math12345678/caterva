# Stage 5 Part 1: resolved citations must be locatable

Stage: 5 (the provenance contract) · Part: 1 · 2026-08-01

## 1. Stage context

Stage 5 makes the API "know more" (Stage 4 close, `STAGE_04_PART_06.md`).
Its open questions, in order:

1. Provenance travels **with** the parameter through the Python engine
   (vs a parallel channel rejoined at the end). Recommendation: with.
2. The `verified`/`flagged`/`rejected` contract for a *citation*.
3. Rule 1 for provenance: a golden set of hand-verified
   enzyme/substrate/Km/citation tuples asserted end to end.
4. A mutation test for the resolver (wrong-organism swap must fail).
5. Whether to widen the single literature-resolved parameter (`km` in `mm`)
   or make the narrowness explicit.

Plus the item explicitly **carried** from Stage 4's close (Part 4 §5,
ADR 0008): whether a `resolved` citation must satisfy a stricter format
than a `modelCitations` entry. This part resolves that item.

## 2. The defect being closed

`queryResolver.ts` rendered a resolved citation with a single template
(two duplicated copies):

```
`${citation.source} (ref ${citation.referenceId ?? "n/a"})` + (url ? ... : "")
```

When a lookup returned a citation with no reference id and no URL
(reachable: BRENDA rows with `reference_id = None`, which also have
`url = None` per `test_citation_from_entry_with_no_reference_id_has_no_url`),
the API emitted:

```
BRENDA (ref n/a)
```

A locator-shaped string that locates nothing. The presence rule
(resolved ⇒ citation exists) was satisfied; the string was useless.

## 3. Decision

A `resolved` citation is attached to a **number**; its job is to let a
human re-find the exact source of that number. `modelCitations` entries
describe models and are allowed to be book-style; a resolved citation is
not.

**Locatable** = the string carries a URL, or a `(ref <id>)` whose id is
not the `n/a` placeholder.

- `lib/provenance.ts`: new `isLocatableCitation()`; `validateParameterProvenance`
  rejects any resolved citation that is not locatable:
  `"<key> is marked resolved but its citation carries no locator (ref id or URL)"`.
  Runs on every response (both resolver paths call it and throw on
  violations), so it is self-enforcing.
- `lib/queryResolver.ts`: one `formatResolvedCitation()` helper replaces
  the two duplicated templates. It refuses to fabricate: no ref id and no
  URL ⇒ `undefined`, and the parameter degrades to origin `default` with an
  honest `note` ("Found a Km but its citation carries no locator...") plus a
  flag. `resolved` now means *value with a locatable citation*, not merely
  *value found*. The API never emits "(ref n/a)" again.

## 4. Why degrade rather than emit

Three options existed for the found-but-unlocatable case:

1. Emit the source only (`"BRENDA"`) with origin resolved — violates the
   new locator rule; validation would throw.
2. Emit `(ref n/a)` as before — the defect.
3. Degrade to `default` + note. Chosen: it is the only non-throwing,
   honest representation of "a value exists but cannot be re-found". The
   note preserves the information that a lookup happened and what it found.

## 5. Tests

`src/__tests__/provenance.test.ts`, +11 tests (122 total, all passing):

- `isLocatableCitation` unit tests: ref id ✓, URL ✓, `(ref n/a)` ✗,
  bare source ✗.
- Strict-format validation: `(ref n/a)` rejected, bare source rejected,
  ref id accepted, URL accepted.
- **Target F** — honest degradation: the mocked agent returns a found Km
  whose citation is `{ source: "BRENDA" }` only; the resolver must report
  origin `default`, no citation, a `note` mentioning the locator, and the
  string `(ref n/a)` must not appear anywhere in the response. The standard
  mock path still resolves.
- **Mutation 6** — reintroducing the `(ref n/a)` template is caught by
  the locator rule (prediction test, same pattern as Mutations 1–3).

Typecheck: clean. Guard enforcement: the strictness rule lives inside
`validateParameterProvenance`, which both resolver paths run before
returning; nothing new to wire.

## 6. Status

Complete and committed. Carried forward to later parts of Stage 5:

- provenance travelling **with** the parameter through the engine (open
  question 1 — unresolved; today the citation and its number remain
  separable by a refactor),
- the `verified`/`flagged`/`rejected` citation contract (question 2),
- the golden set (question 3),
- the resolver mutation test against a wrong-organism swap (question 4),
- widening `km`-in-`mm` vs making narrowness explicit (question 5).
