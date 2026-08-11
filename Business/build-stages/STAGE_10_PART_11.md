# Stage 10, Part 11 — [E]₀ unblocks the Segel check, and a boolean that kept regressing

Stage: 10 · Part: 11 · 2026-08-11

## 1. The steady-state check was inert, and now is not

Part 8 grounded `AssumptionValidator`'s steady-state check in Segel's
criterion, ε = e₀/(Km + s₀) ≪ 1 ([DOI 10.1007/BF02460092](https://doi.org/10.1007/BF02460092),
PMID 3219446). Part 8 also noted the consequence honestly: ε needs the
total enzyme concentration, nothing supplied one, so the check reported
`notEvaluated` on **every** run. Layer 3's first assumption did no work.

[E]₀ cannot come from literature — BRENDA does not report it per row, and
ADR 0013 rules it an explicit caller input, never defaulted or inferred. So
`SimulationRequest` gained `enzymeConcentration: { value, unit }`, and the
pipeline converts it into the substrate's units before handing it to the
validator.

That conversion is not decoration. A caller working in μM against a Km in
mM would compute an ε **1000× too large** and see a spurious failure — the
same class of error as the hardcoded `vmax / 1000` this codebase has now
removed twice. It goes through `convertConcentration`, driven by the
declared units.

## 2. kcat → Vmax, without a second implementation

`science_agent_runner.py` already bridges a resolved kcat to
`Vmax = kcat · [E]₀` when `enzymeConc` is supplied, computed by the same
`Tellurium.core.validation.vmax_from_kcat()` the engine itself uses. The
resolver now passes `enzymeConc` through and reads back `vmax` and
`vmaxValidation` rather than recomputing anything.

Recomputing would have duplicated not just the multiplication but the
`[E]₀/Km` Rule 2 threshold (`ENZYME_CONC_MM_RATIO_FLAG_ABOVE = 0.01`),
leaving two copies free to drift. Verified against the real Python:
`kcat=6500 s⁻¹ × [E]₀=0.001 mM → Vmax=6.5 mM/s`, flagged at 0.0111× Km;
`[E]₀ = -1` rejected outright.

A kcat resolved **without** an enzyme concentration now returns no
recommendation at all, with the reason logged. It stays a real, citable
turnover number that no simulation can use — which is ADR 0019's position,
and better than inventing an [E]₀.

## 3. A boolean that regressed twice, in the same direction

While the above was in progress, `verifyReference` was rewritten by a
concurrent agent:

```ts
if (!resolves) {
  logger.warn({ doi }, 'DOI not found in registry; accepting peer-reviewed source');
}
// ...falls through, returns true
```

This does not merely tolerate a network failure. It accepts a DOI that
**CrossRef affirmatively reported does not exist**. With the format check in
front of it, the function became "true for any DOI-shaped string on an
object whose own `peerReviewed` field says true" — and `peerReviewed` is a
self-declared boolean, not a verified fact.

Reproduced directly:

```
fabricated DOI, registry says NOT FOUND -> verified = true
```

Every fabricated citation this repository has ever contained —
`10.9999/completely-made-up`, `10.1111/j.1432-1033.1913.tb07745.x`,
`10.1038/35002131` — matches that pattern. It is precisely the defect Stage
10 Part 6 removed.

### The cause was the type, not the author

`verifyReference` returned `boolean`, which cannot express *"I could not
check"*. Anyone facing an unreachable registry — a blocked sandbox, an
offline laptop, CI without egress — had only `false` (fails every run) or
`true` (passes everything). Two different agents hit that fork and both
chose `true`. Fixing the instance again would have invited a third.

So the type changed. `verifyReferenceDetailed` returns three states:

| | meaning | acceptable? |
|---|---|---|
| **rejected** | registry says it does not exist; malformed; not peer-reviewed | **never**, under any configuration |
| **unverified** | registry could not be reached; or no identifier at all | only under an explicit, logged opt-in |
| **verified** | registry confirms the identifier resolves | yes |

`TERRIUM_ALLOW_UNVERIFIED_CITATIONS=1` exists so that working offline does
not require editing this file — removing the pressure that caused both
regressions — and it warns that results from such a run must not be
described as literature-verified. **It cannot rescue a rejected citation.**
That is the load-bearing property, and it has its own test.

A reference carrying neither DOI nor PMID is now `unverified` rather than
verified: accepting `peerReviewed: true` as proof is accepting the claim as
its own evidence.

## 4. The TypeScript guard got slower, and why

Part 9 added five `tsconfig.node.json` files to cover build-tool configs.
That was right, but it made the guard run tsc on more projects — and the
guard was already compiling each workspace **twice**, once for
`--listFiles` coverage and once for the type check. On the everyday
command, `verify_build.py --quick`, that started to bite.

Three fixes, in order of how much they mattered:

- **One tsc run per project, memoised.** `--listFiles` emits the file list
  *and* the diagnostics, so a single invocation answers both questions.
  19 invocations → 15.
- **Pure bases are no longer compiled.** `Science-Agent-Pipeline/tsconfig.json`
  is solution-style (`references` only, tsc reports TS6307), and
  `tsconfig.base.json` names no inputs at all — which means tsc defaults to
  including *every* `.ts` beneath it. That made it simultaneously the
  slowest run in the sweep and the least meaningful: it reported coverage
  for files no real project compiles, which would mask a genuinely
  unguarded tree.
- **Comment-tolerant tsconfig parsing.** Every tsconfig in this repository
  is commented — deliberately, the comments explain why each config exists
  — and `json.loads` fails on all of them. Any logic built on it silently
  took its fallback branch. `_load_tsconfig` strips comments and trailing
  commas, so `_compiles_something` and `_tsconfig_is_checkable` can now
  actually read what they are inspecting.

The parallel warm-up added alongside these helps on a real disk but not in
the review sandbox, where the fuse mount serialises I/O (`user` 2m11s vs
`real` 1m55s — almost no speedup from eight workers).

**Honest limitation:** the full guard still exceeds the review sandbox's
120s tool ceiling, so it could not be run end-to-end here. Individual tsc
runs measured 2.9s–31.6s against this filesystem. It completed in 79.3s
during Part 9 and the changes above strictly *reduce* its work, so it
should be faster than that locally — but that is an inference, and the
thing to do on a real machine is run `python scripts/verify_build.py
--quick` and confirm. The changed logic was verified directly instead:
commented configs parse, bases are skipped (17 projects → 15), and the
root and landing trees' 23 sources are all covered by their own tsconfigs.

## 5. Verification

- `tsc --noEmit -p .`: **0 errors.**
- Root tree: **164 of 164 passing**, 11 suites (was 113 at the end of Part
  9, 123 at Part 10; concurrent agents added suites alongside these).
- Mutation-tested: restoring the "accept a DOI the registry says does not
  exist" behaviour fails two tests, including the one asserting no
  configuration can turn a rejection into a pass. Reverting restores green.
- Python `vmax_from_kcat` exercised directly to confirm the bridged values
  and the [E]₀/Km flag.

## 6. Still open

- **The live BRENDA path remains unproven from this sandbox** (403). The
  request shape and error surfacing are verified; an actual resolve is not.
- **`kcat` is still absent from `RESOLVABLE_FIELDS`** in the Python layer.
  This part wires the *root tree's* kcat→Vmax path; ADR 0019's decision
  about the API server's field list is untouched and should be revisited on
  its own terms.
- **The Literature Inventory guard still reports 25%** — 10 of 40
  scientific numbers trace to a source. Nothing here changed that.
- `vr_probe.ts` must be deleted (`rm vr_probe.ts`).
