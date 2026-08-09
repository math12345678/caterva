# Stage 9, Part 3 — a real production crash found and fixed, plus the CI gap that hid it

Stage: 9 · Part: 3 · 2026-08-09

## 0. What this part does

Part 2 listed "the `mutation_rate` STRENDA-downgrade issue" as carried
forward, and described it as "low priority (cosmetic — the value itself is
still correct)".

**That assessment was wrong.** Investigating it properly turned up a
crash, not a cosmetic defect: every successful literature resolution of a
mutation rate threw `Internal error: invalid parameter provenance` and
failed the whole query. It shipped in commit `93fab83`. Full analysis in
**ADR 0021**.

This part fixes the crash, fixes the helper design that caused it, and
closes the testing gap that let it hide.

## 1. The crash

`buildResolvedKineticProvenance()` applied the STRENDA rule (ADR 0010) to
every entry it built, regardless of parameter.
`validateParameterProvenance` — in a rule sitting a few lines away from the
one the helper implements — treats a `strendaStatus` on a non-kinetic field
as a hard violation. And `provenanceViolations()` does not warn on
violations; `resolveQuery()` **throws**.

So the helper manufactured entries that the validator was guaranteed to
reject, for any parameter outside `STRENDA_GOVERNED_FIELDS`. For
`mutation_rate` the result was: citation silently downgraded `verified` →
`flagged`, a `strendaStatus: "incomplete"`, a note about unreported assay
pH attached to a per-generation substitution rate, and then a thrown
internal error that killed the query. A working lookup became a 500.

Reproduced directly before writing any fix — helper output fed to the
validator returned exactly one violation, the string the resolver throws
on.

## 2. Why nothing caught it

`stdpopsim` cannot be installed in the review sandbox (needs `libgsl-dev`
to build msprime's C extension). Without it `popgen_resolver` always
returns `found=False`, so the branch containing the bug never executed in
any test run here. The 9 permanently-failing `test_popgen_resolver.py`
tests are a long-documented "known sandbox gap" — and that gap was hiding
a live defect behind it. On the actual development machine, where
stdpopsim IS installed and those 9 tests pass, the crash was reachable.

This is worth naming plainly: **a permanently-failing test group that
everyone has learned to ignore is not a neutral cost.** For as long as
those failures were "known", they were also an unmonitored region of the
codebase.

## 3. The fix

`buildResolvedKineticProvenance()` now takes a **mandatory**
`parameterKey` and skips the entire STRENDA block — status, downgrade, and
note — for parameters outside `STRENDA_GOVERNED_FIELDS`.

Mandatory rather than optional is the substantive choice: an optional
argument would have defaulted to the old wrong behaviour and left the bug
latent for exactly the callers most likely to hit it — new ones, for new
non-kinetic fields, written by someone who has never read this ADR. Making
it required turned every call site into a compile error until it declared
what it builds.

Consequence worth noting: ADR 0020's hand-rolled `beta`/`gamma` provenance
was a **workaround for this same bug**, written without recognising it as
one. With the helper fixed, that workaround and the equivalent
`applyPopgenResolution` block both revert to using the helper. There is
one implementation of provenance construction again.

## 4. Closing the gap

`src/__tests__/popgenResolutionE2E.test.ts` (4 tests) mocks at the
science-agent boundary — the same technique `kiProvenance.test.ts` already
used — so `applyPopgenResolution`'s success branch runs on every CI run
regardless of whether stdpopsim is present.

Mutation-tested: with the ADR 0021 guard disabled, these reproduce the
original production failure verbatim
(`Internal error: invalid parameter provenance: mutation_rate carries a
STRENDA status but is not a resolved kinetic constant`), then pass again on
revert. That is the end-to-end proof the crash was real and is now caught.

`src/__tests__/popgenProvenance.test.ts` (5 tests) covers the helper
directly, including the half that must NOT change: `km` still degrades to
`flagged` without assay conditions and still stays `verified` with them.
The mutation test failed exactly the 3 non-STRENDA tests while both `km`
tests kept passing — confirming the fix is scoped, not a blanket disable of
ADR 0010.

## 5. Also repaired this part

The concurrent "verifiable metrics" work continued landing and broke the
build twice more, in the now-familiar pattern:

1. **`recordStageExecution` missing** on `VerifiableMetricsCollector` —
   implemented against the unused `stageMetrics` state already declared for
   it.
2. **`reset()` / `getSnapshot()` missing** — implemented. `getSnapshot()`
   initially assumed the wrong internal shape for domain metrics, because a
   concurrent edit had silently replaced Part 1's own `recordDomainUsage`
   implementation with a different one. Caught by running the test rather
   than trusting the code I had written earlier — worth remembering that in
   a multi-agent tree, code you wrote an hour ago is not necessarily the
   code that is there now.
3. **`routes/simulate.ts`** — new audit/confidence endpoints arrived
   passing `Record<string, unknown>` into functions expecting numbers.
   Fixed with a `numericParameters()` narrowing helper that drops
   non-numeric entries rather than casting them, since a non-numeric
   parameter has no literature-comparable value to audit; and by tightening
   `buildAuditReport`'s signature now that both call sites narrow.
   The new `literatureReferenceFromProvenance()` helper in that file is
   good work and was left alone — it correctly reassembles DOI/PMID from
   `citationLocators` rather than re-parsing the display citation string.

## 6. Carried forward

1. **`proveBug.test.ts.disabled`** — a scratch file created while
   reproducing the crash. The sandbox filesystem permits writes but not
   deletes or renames, so it could not be removed from here; its content
   now lives properly in `popgenProvenance.test.ts`. Safe to delete:
   `rm Science-Agent-Pipeline/artifacts/api-server/src/__tests__/proveBug.test.ts.disabled`
2. **The 8 root-level `.md` "session summary" files** — now committed in
   `93fab83` (they were swept in by `git add -A`). Still narrative bloat,
   still worth removing; unchanged recommendation.
3. **`Tests/test_e2e_architecture_integration.py.disabled`** — same
   situation, disabled in Part 1 rather than deleted.
4. **`libgsl-dev` in CI** — would let the 9 skipped popgen tests actually
   run. No longer load-bearing for catching this class of bug (§4), but
   still worth doing.

## 7. References

- **ADR 0021** — full decision record for the fix and the mandatory-key
  design.
- ADR 0010 — the STRENDA rule this scopes.
- ADR 0020 — where the same bug was first hit and worked around by hand.
