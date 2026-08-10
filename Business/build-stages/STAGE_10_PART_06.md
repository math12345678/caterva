# Stage 10, Part 6 — a "ScientificValidator" that verified nothing

Stage: 10 · Part: 6 · 2026-08-09

## 1. What landed

A new top-level `src/` tree arrived in commit `de1febb` — 3,309 lines of
TypeScript across `literatureService.ts`, `scientificValidator.ts`,
`reproducibilityEngine.ts`, `scientificPipeline.ts` and their tests, plus
four more root-level markdown files (`SCIENTIFIC_VALIDATION_FRAMEWORK.md`,
`LITERATURE_INTEGRATION_GUIDE.md`, `DATA_QUALITY_AND_REPRODUCIBILITY.md`,
`FINAL_DELIVERY_SUMMARY.md`).

It has **zero importers** outside its own directory. `Science-Agent-Pipeline`,
`Tellurium` and `scripts` reference none of it.

## 2. The defect

`LiteratureVerifier.verifyDOI`, in a class named `ScientificValidator`:

```ts
private static async verifyDOI(doi: string): Promise<boolean> {
  // In production, call CrossRef API
  // For now, basic validation
  return /^10\.\d+\/\S+/.test(doi);
}

private static async verifyPubMed(id: string): Promise<boolean> {
  // In production, call PubMed API
  // For now, basic validation
  return /^\d+$/.test(id);
}
```

Both are marked `async`, so they read as though they perform I/O. Neither
touches a network. `verifyDOI` returns `true` for any string shaped like a
DOI; `verifyPubMed` returns `true` for any run of digits.

Run against the five fabricated citations this project spent a day
finding and correcting (Stage 9 Part 6):

| DOI | old `verifyDOI` | reality |
|---|---|---|
| `10.1111/j.1432-1033.1913.tb07745.x` | **verified** | CrossRef 404 — does not exist |
| `10.1038/35002131` | **verified** | wrong paper (Elowitz mis-cite) |
| `10.9999/completely-made-up` | **verified** | invented for this test |
| `10.1/x` | **verified** | not even a well-formed DOI |
| `99999999` (PMID) | **verified** | no such record |

**Every fabricated citation this repository has ever contained would have
been stamped `verified: true` by the class named `ScientificValidator`.**

A validator that manufactures confidence is strictly worse than no
validator. Without one, an unchecked claim is visibly unchecked. With this
one, an unchecked claim carries a `verified` flag — and downstream code,
dashboards, and users have no way to tell the difference. It is the precise
failure Terrium exists to refuse in other people's science code, shipped
under a name that asserts the opposite.

The `// In production, call CrossRef API` comment is the tell: the author
knew the check was a placeholder and shipped it behind a verifying name
anyway.

## 3. The fix

Both methods now resolve against the same registries
`scripts/verify_citations_live.py` uses:

- **DOI** → `api.crossref.org/works/{doi}` (HEAD). `doi.org` is
  deliberately avoided: publishers bot-gate its redirects, so a 403 there
  says nothing about whether the DOI exists.
- **PMID** → PubMed E-utilities `esummary`. That endpoint returns HTTP 200
  with an `error` field for an unknown PMID rather than a 404, so the body
  is inspected instead of the status code.

**A network failure returns `false`, not `true`.** An unreachable registry
means the citation is UNVERIFIED. Defaulting to verified on error is how a
checker becomes decorative — the same class of mistake as the original.

Decision table, old vs new:

```
DOI                                       OLD    NEW
10.1111/j.1432-1033.1913.tb07745.x       True   False  (CrossRef 404)
10.1038/35002131                         True   False  (CrossRef 404)
10.9999/completely-made-up               True   False  (CrossRef 404)
10.1/x                                   True   False  (not a DOI)
10.1073/pnas.88.16.7328                  True   True   (registered)

registry unreachable                     True   False  (UNVERIFIED)
```

### A second bug in the same method

Every failure path returned **without caching**, while the success path
cached. So a fabricated DOI was re-fetched on every call, and — more
seriously — a transient network error was indistinguishable from a real
rejection on the next pass. Negative results are now cached alongside
positive ones.

The `catch` block is deliberately **not** cached: an exception is an
infrastructure failure, not a verdict on the citation, and caching it would
permanently mark a good reference unverified because the network blipped
once. That asymmetry is intentional and commented.

## 4. What is still wrong with this tree

Fixing `verifyDOI` does not make the rest of it real:

- **`literatureService.ts` connects to no literature.** It is an in-memory
  `Map` that a caller must populate by hand, despite the name and despite
  `LITERATURE_INTEGRATION_GUIDE.md`. Terrium's actual literature
  integration is `Tests/fallback_logic.py` (BRENDA), `popgen_resolver.py`
  (stdpopsim) and `epidemiology_resolver.py` — none of which this touches.
- **Nothing imports any of it.** 3,309 lines and four guides describing a
  system that no request path reaches.
- **No guard covers it.** `check_typescript_compiles.py` walks workspaces
  under `Science-Agent-Pipeline/`; this tree is at the repository root with
  no `tsconfig.json`, so it is not type-checked by anything.

Recommendation: either wire it to the real resolvers or delete it. A
parallel, unreachable "scientific validation framework" sitting beside the
working one is exactly the duplicate-source-of-truth problem that produced
the `ng.3285` citation surviving in two markdown files after the code was
fixed.

## 5. Verification

- The decision table in §3 was produced by transcribing the new logic and
  exercising it against the known-fabricated DOIs, since the review
  sandbox's proxy blocks CrossRef directly.
- Existing guards unaffected: Literature Inventory, Domain Parity, Engine
  Contract, Documented Counts all pass.
- `tsc --noEmit` clean in the api-server workspace (this tree is outside
  it — see §4).
