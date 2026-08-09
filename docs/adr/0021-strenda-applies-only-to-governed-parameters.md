# ADR 0021: The STRENDA rule applies only to STRENDA-governed parameters, enforced by a mandatory `parameterKey`

**Status:** Accepted

**Date:** 2026-08-09

**Relates to:** ADR 0010 (the STRENDA rule this scopes), ADR 0008 (parameter
provenance), ADR 0017 / 0020 (epidemiology), ADR 0019 (kcat → Vmax)

## Context

`buildResolvedKineticProvenance()` exists so that "no caller can forget the
STRENDA rule" (ADR 0010): a resolved kinetic constant whose assay pH and
temperature are unknown is downgraded from `verified` to `flagged`, gets a
`strendaStatus`, and gets a note naming what's missing.

It applied that rule to **every** entry it built, regardless of which
parameter the entry was for. That is correct for `km`, `ki`, `kcat`, and
`vmax` — the contents of `STRENDA_GOVERNED_FIELDS` — and wrong for anything
else.

`validateParameterProvenance` already encoded the correct scope, in a rule
directly adjacent to the one the helper implements:

```ts
if (!strendaGoverned && prov.strendaStatus !== undefined) {
  violations.push(
    `${key} carries a STRENDA status but is not a resolved kinetic constant`,
  );
}
```

So the helper produced entries the validator rejects. And
`provenanceViolations()` does not warn on violations — `resolveQuery()`
**throws** on them:

```ts
throw new Error(`Internal error: invalid parameter provenance: ...`);
```

The concrete consequence: `applyPopgenResolution()` used the helper for
`mutation_rate`, a per-generation per-base-pair substitution rate that
STRENDA does not govern and that has no assay pH at all. Every
**successful** literature resolution of a mutation rate therefore:

1. had its citation silently downgraded `verified` → `flagged`;
2. gained a `strendaStatus: "incomplete"`;
3. gained a note reading "Assay pH and temperature not reported by the
   source; STRENDA requires them for kinetic data" — about a mutation rate;
4. and then **crashed the whole query** with "Internal error: invalid
   parameter provenance".

A working literature lookup was turned into a 500. This was reproduced
directly (helper output fed to the validator, one violation returned)
before any fix was written.

### Why CI never caught it

`stdpopsim` is not installable in the review sandbox (it needs `libgsl-dev`
to build `msprime`'s C extension). Without it `popgen_resolver` always
returns `found=False`, so the branch containing the bug never executed in
any test run. The 9 permanently-failing `test_popgen_resolver.py` tests are
a known, documented sandbox gap — and that gap was hiding a real defect on
the other side of it. On a machine with `stdpopsim` present (the actual
development machine, where those 9 tests pass), the crash was live.

This is the second time the same shape of problem has appeared: a helper
that silently does the right thing for the fields it was written for, and
the wrong thing for a field added later. ADR 0020 hit it first and worked
around it by hand-rolling `beta`/`gamma` provenance rather than using the
helper — a workaround, not a fix, and one that would not have protected the
next caller.

## Decision

**`buildResolvedKineticProvenance()` takes a mandatory `parameterKey`, and
skips the entire STRENDA block — status, downgrade, and note — when that
key is not in `STRENDA_GOVERNED_FIELDS`.**

`parameterKey` is **required, not optional**, and that is the substantive
part of this decision. An optional parameter would have defaulted to the
old, wrong behaviour, leaving the bug latent for exactly the callers most
likely to hit it: new ones, for new non-kinetic fields, written by someone
who does not know this ADR exists. Making it required means every existing
call site had to state which parameter it builds for (a compile error until
it does), and every future call site must too.

With the helper made safe, ADR 0020's hand-rolled `beta`/`gamma` workaround
and the equivalent block in `applyPopgenResolution` were both reverted to
use the helper again. There is now one implementation of provenance
construction, and it is correct for governed and non-governed fields alike.

## Verification

- Bug reproduced directly before fixing: helper output for a
  `mutation_rate` entry, fed to `validateParameterProvenance`, returned
  `["mutation_rate carries a STRENDA status but is not a resolved kinetic
  constant"]` — the exact string `provenanceViolations` throws on.
- 5 regression tests in `src/__tests__/popgenProvenance.test.ts`:
  `mutation_rate` carries no `strendaStatus` and stays `verified`;
  `mutation_rate` produces **zero** validator violations (the assertion
  that would have caught the crash); `beta` likewise; and — the other half,
  which matters just as much — `km` **still** degrades to `flagged` with a
  STRENDA note when conditions are absent, and **still** stays `verified`
  when they are complete.
- Mutation-tested: disabling the new guard (`if (false && ...)`) failed
  exactly the 3 non-STRENDA tests while both `km` tests kept passing —
  confirming the fix is scoped, not a blanket disable of ADR 0010.
  Reverted, re-confirmed green.
- 4 further tests in `src/__tests__/popgenResolutionE2E.test.ts` close the
  gap that *hid* the bug: they mock at the science-agent boundary (as
  `kiProvenance.test.ts` already does) so `applyPopgenResolution`'s success
  branch runs on every CI run whether or not `stdpopsim` is installed.
  Mutation-tested too — with the guard disabled these reproduce the
  original production failure verbatim:
  `Internal error: invalid parameter provenance: mutation_rate carries a
  STRENDA status but is not a resolved kinetic constant`. That is the
  end-to-end proof the crash was real and is now caught.
- Full suite: 28 test files, 399/399 passing; `tsc --noEmit -p .` clean.
  Python: 280 passing (the 9 `stdpopsim` sandbox failures unchanged and
  unrelated).

## Consequences

**Easier.** Any future literature-resolved parameter — a diffusion
coefficient, a rate constant, a population parameter — can use the standard
provenance helper without either inheriting an enzymology reporting
standard that does not apply to it or hand-rolling its own entry.

**Harder.** Nothing. The mandatory key is one extra argument at four call
sites.

**Unchanged.** ADR 0010's rule itself, and its behaviour for every field it
actually governs (`km`, `ki`, `kcat`, `vmax`) — verified by the two `km`
tests above, which the mutation test confirms are load-bearing.

**Closed by this ADR.** The `stdpopsim` sandbox gap had a demonstrated
cost: it hid a crash for as long as it has existed. The mocked
`popgenResolutionE2E.test.ts` now exercises that branch unconditionally, so
the gap can no longer hide a defect on that code path. Installing
`libgsl-dev` in CI would still be worth doing — it would let the 9 skipped
`test_popgen_resolver.py` tests run — but it is no longer load-bearing for
catching this class of bug.

**A general lesson worth stating.** A permanently-failing test group that
everyone has learned to ignore is not a neutral cost. For as long as those
9 failures were "the known sandbox gap", they were also an unmonitored
region of the codebase. Any environment gap that disables a code path
should come with a mocked substitute that keeps the path covered.

## References

- ADR 0010 — the STRENDA assay-conditions rule this scopes.
- ADR 0020 — where the same problem was first hit and worked around by
  hand; that workaround is removed by this ADR.
- STRENDA Guidelines v1.4.0, Beilstein-Institut — the standard's own scope
  is enzymology data, which is precisely the scope this ADR restores.
