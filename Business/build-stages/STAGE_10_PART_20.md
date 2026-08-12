# Stage 10, Part 20 — closing the last two audit findings

Stage: 10 · Part: 20 · 2026-08-11

## 1. A citation guard that reported OK on a failed parse

`scripts/check_citation_format.py` finds citations with a regex for
`modelCitations: [ "..." ]`. If that regex stops matching,
`extract_entries` returns `[]`, the loop never runs, `violations` stays
empty, and `main()` prints:

> OK: all modelCitations entries carry authors, a year, and volume/pages, a
> publisher, or a URL.

Nothing has to *break* for that to happen. Renaming the field, moving the
entries to a `const MODEL_CITATIONS = [...]` and spreading it in, or
switching the strings to template literals (the string regex only matches
`"..."`) would each silence the guard completely — and every fabricated
citation in `queryResolver.ts` would pass in silence.

Two sibling guards already refuse this: `check_domain_parity.py` and
`check_literature_inventory.py` both emit *"parsed ZERO … Refusing to
report success."* This one had never been given the same treatment.

Fixed, and mutation-verified: renaming `modelCitations:` to `citations:`
now produces

```
parsed ZERO citation entries from queryResolver.ts. Refusing to report
success: ... A guard that reports OK on a failed parse is worse than no
guard, because it is trusted.
```

with exit 1, where it previously printed OK and exited 0.

## 2. `auditForPublication` called keyword matches publication-ready

```ts
const readyToPublish = counts.pending === 0 && (counts.verified + counts.flagged > 0);
```

Wrong in two ways, and it never called `canPublish` — the per-parameter
gate defined immediately above it, which requires a `flagged` value to
carry a DOI:

- **`unverifiable` was counted, named in the summary string, then ignored
  by the boolean.** A parameter set containing a system default reported
  ready.
- **`flagged` counted as equivalent to `verified`.** But `flagged` is what
  verification returns for a *keyword-matched* value ("use as estimate
  only") and for a literature value with no DOI, PMID or URL — precisely
  the values that must not appear in a paper uncited.

So `{km: keyword-matched, vmax: keyword-matched, s0: default}` returned
`readyToPublish: true` with the summary *"Publication ready: 0 verified, 2
with literature backing"* — while `canPublish` was false for every one of
them.

Now decided per parameter by `canPublish`, with the summary naming how many
parameters cannot be cited and why.

### The existing test caught my over-correction

My first fix blocked publication on **any** unpublishable parameter, and an
existing test failed: a set of `{km: verified+DOI, vmax: verified+DOI, s0:
user}` asserted `readyToPublish: true`.

The test was right and I was wrong. `s0` is an experimental **condition** —
a paper *states* its substrate concentration, it does not cite one. Blocking
on it is the same category error that made Layer 1 reject every run with
"Parameter 's0' has no literature backing" (Part 16) and made the
sensitivity report flag s0 as "not solid" (Part 16 §2).

Publication readiness now means: **every MEASURED quantity can be cited.**
Conditions still have to be reported, and they appear in the parameter
table with `origin: "user"` so a reader can see they were chosen rather
than looked up.

Then my own new test failed — it had used `s0` as the example of an
unverifiable blocker, which is now correctly exempt. Rewritten to use `km`,
with a companion asserting the converse. The two together encode the
distinction:

```
blocks an unverifiable MEASURED quantity        → readyToPublish false
does NOT block on an experimental condition     → readyToPublish true
```

That is the fourth time this session the measured/condition distinction has
had to be applied somewhere new. It is worth stating as a rule rather than
rediscovering: **a citation is required for what someone measured, and
meaningless for what the experimenter chose.**

## 3. Verification

- `tsc --noEmit` clean in both trees.
- api-server: **19 / 19** in the literature-verifier suites, including 5 new
  `auditForPublication` tests.
- `check_citation_format.py`: passes clean, fails on the mutation, passes
  again on revert.
- Root tree: 57/57 validation, 95 passing across the suites that fit in the
  sandbox's timeout.

## 4. Part 12's audit findings: final state

| finding | state |
|---|---|
| `/api/dashboard/health` could not report degraded | fixed, Part 12 |
| `getSuccessRateWithConfidence` returned 100% of zero | fixed, Part 12 |
| `check_constant_usage` could not append a violation | fixed, Part 12 |
| every kcat labelled `unit="mM"` | fixed, Part 12 |
| `check_citation_format` OK on zero parse | **fixed, here** |
| `auditForPublication` treats flagged as ready | **fixed, here** |
| vacuous `kcatProvenance.test.ts` assertion | open |
| locator consistency is opt-in (`provenance.ts:322`) | open |
| four latent silent skips in `verify_citations_live.py` | open (dormant) |

The three remaining are the lowest-severity of the nine: one vacuous test,
one check that binds only entries volunteering for it, and four `if not
path.is_file(): continue` paths that are not currently firing because every
file they name exists.
