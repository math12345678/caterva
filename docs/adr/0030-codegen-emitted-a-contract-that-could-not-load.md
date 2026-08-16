# ADR 0030: Codegen emitted a contract that could not load

**Status:** Accepted, implemented

**Date:** 2026-08-14

**Relates to:** ADR 0027 (which recorded this as formatting drift and
understated it), ADR 0015 (a constitution rule that nothing executes is not
enforced)

## Context

ADR 0027 needed a new field on `SimulationRequest`. Running the documented
codegen command produced the new field *and* rewrote every date in the
contract from `zod.coerce.date()` to `zod.iso.datetime({ offset: true })`.

That was recorded as a zod/orval version drift, judged too risky to ship as
a side effect, and worked around by hand-patching the generated files. The
drift was left as a named, unfixed finding.

**The assessment was wrong in the direction that mattered.** It is not that
the two forms validate differently. It is that one of them does not exist:

```
$ node -e "const z = require('zod'); console.log(typeof z.iso)"
undefined                                   # zod 3.25.76
```

`zod.iso` is `undefined` on the installed zod. A full regeneration produced
a contract that **throws on import**. The documented command — the one
CONTRIBUTING points at — broke the API server, and the only reason nobody
hit it is that the committed files predated the zod bump and nobody had
regenerated.

The hand-patching in ADR 0027 was not merely cautious. It was load-bearing,
for a reason that ADR did not know.

## The mechanism

1. orval's `override.zod.version` defaults to `"auto"`, which inspects the
   installed zod.
2. zod 3.25 ships a **`zod/v4` subpath**. Detection saw v4 capability and
   emitted v4 syntax.
3. The generated import is plain `"zod"` — where `iso` does not exist.

The v4 API is genuinely available in that install, at `require("zod/v4")`.
orval emitted code for it and imported from the v3 entry point.

## Why every existing check missed it

**`tsc --noEmit` cannot see this defect.** `zod.iso` is present in zod
3.25's *type declarations* even though it is absent from the default
export at *runtime*. The generated file type-checks perfectly and crashes
on load.

That gap — between a package's declared surface and its actual one — is the
whole defect, and it is precisely what a type-checker is not looking at.
This repository has now been bitten four times by checks that were true and
blind; this is the first where the blindness is structural to the tool
rather than to how the check was written.

## Decision

### 1. Pin the version; never leave it to `auto`

`override: { zod: { version: 3 } }` in `lib/api-spec/orval.config.ts`, with
the reasoning and the one-line reproduction at the site.

`auto` is not a convenience here, it is a guess about a package's runtime
surface made from its version string. The comment says to raise it to 4 in
the same commit that moves the workspace to zod@^4, and not before.

### 2. The hand-patches are gone

With the pin in place, `physiologicalReference` regenerates correctly.
The ADR 0027 hand-edits to `api.ts`, `api.schemas.ts` and
`simulationRequest.ts` have been replaced by generated output, and the
"do not edit manually" headers are true again.

### 3. A guard that checks the runtime surface, not the version string

`scripts/check_generated_client_loads.py` asserts three things:

1. orval pins a zod major explicitly (absence of a pin is itself a failure).
2. The pinned major matches the installed zod's major.
3. The generated schema contains no v4-only syntax when the installed zod
   has no `iso`.

(3) is what makes the others more than bookkeeping: the guard **asks the
installed package what it can do** rather than trusting its version number.
A future zod that ships `iso` on the default export in a 3.x release would
satisfy the runtime check honestly, and one that removes it would fail
regardless of what the version string says.

It deliberately does **not** duplicate the runtime parse check.
`schemas.test.ts` and `physiologicalReferenceRoute.test.ts` already import
`RunSimulationBody` and parse with it, so a contract that fails to load
fails those. This guard catches the configuration drift *upstream* of that,
where the message can name the cause instead of showing a TypeError.

### 4. Orval appends to index.ts, and that is now written down twice

`clean: true` does not clean the hand-maintained `src/index.ts` files —
orval **appends** its exports on every run. A previous agent found three
identical copies accumulated and deduped them by hand; this regeneration
re-appended, exactly as their note predicted.

Deduped again, note preserved and sharpened. The `custom-fetch` exports in
`api-client-react/src/index.ts` are hand-written and survive regeneration;
they must not be removed by a future dedupe that assumes everything in the
file is generated.

## Verification

Three mutations, all caught:

| Mutation | Result |
|---|---|
| the pin is removed (back to `auto`) | exit 1 |
| the pin says 4 while zod is 3 | exit 1 |
| **the original defect** — v4 syntax in the generated file | exit 1 |

The mutation harness verifies its own backups with `cmp` before starting and
again after restoring, because the previous session's mutation run wrote
backups to a `/tmp` that was not writable, every restore silently failed,
and the mutations accumulated into a meaningless result. A verification
procedure whose setup can fail silently produces confident numbers about
nothing.

Both trees compile; the 67 tests covering the request schema and the
withheld paths pass against the regenerated contract.

## Consequences

- `pnpm --filter @workspace/api-spec run codegen` is now safe to run. It was
  not before, and nothing said so.
- ADR 0027's "still open" drift item is closed. Its description of the
  problem is corrected here rather than edited there, because the wrong
  assessment is part of the record: a finding judged cosmetic stayed open
  for a day while being a crash.
- `allowVariants` (ADR 0029) can now be exposed over HTTP through
  regeneration rather than hand-patching. That is the next step and is not
  done here.
- The generated diff includes formatting churn beyond the new fields,
  because the committed files were produced by a different toolchain. That
  churn is now *correct* output rather than drift, and future diffs will be
  small.

## What this does not fix

The workspace is still on zod 3.25 with a v4 subpath present, which is an
inherently confusing state for any tool that sniffs capability. Moving to
zod 4 properly — updating the catalog pin, the config, and every
`z.coerce`/`z.iso` call site together — is a separate piece of work with its
own risks, and pinning to 3 is what makes it a *choice* rather than
something a regeneration does to the repository by accident.
