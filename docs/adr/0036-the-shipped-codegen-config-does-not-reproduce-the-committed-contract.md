# ADR 0036: The shipped codegen config does not reproduce the committed contract

**Note:** Renumbered from 0035 to 0036. Two agents took 0035 within
four minutes of each other, each having looked at the directory and
seen it free. Caught by scripts/check_adr_index.py, which had been
written minutes earlier for exactly this.

**Status:** Resolved 2026-08-14 — there was no decision to make. The two
modes emit byte-identical output; see Resolution.

**Date:** 2026-08-14

**Relates to:** ADR 0034 (the staleness guard, which missed this), ADR 0030
(the version pin), ADR 0029 (`allowVariants`, blocked on this)

## What was found

`orval.config.ts` declares the zod target as `mode: "split"`. The committed
`lib/api-zod/src/generated/api.ts` is what `mode: "single"` produces.

They are not interchangeable. orval honours the `override.zod.coerce` block
in `single` mode and **ignores it in `split`**, so the same spec and the same
override emit different validators:

| mode | emitted for a `date-time` field |
|---|---|
| `single` | `zod.coerce.date()` — coerces the string to a `Date` |
| `split` | `zod.string().datetime({ offset: true })` — validates, stays a string |

A caller reading `completedAt` gets a `Date` from the committed contract and
a `string` from the one the shipped config would produce.

`mode: "split"` is in `HEAD`, so this is not a recent regression. The config
and the committed output have disagreed for as long as both have existed,
and running the documented command has never reproduced the tree.

## How it stayed hidden, including from the guard written to find it

ADR 0034 added `check_codegen_loads.py` precisely to catch "the committed
generated file is not what codegen produces." It reported **OK**.

The reason is worth stating plainly, because it is the same mistake three
times in this codebase now: **the guard's verification config restated the
settings instead of deriving them.** It hardcoded `client`, `mode`,
`formatter`, and pulled in only the `zod` override — and it hardcoded
`mode: "single"`.

So the guard regenerated in `single` mode and compared against a `single`-mode
artifact. It agreed with itself. The one setting that mattered was the one it
had copied wrong, and the copy was invisible because it looked like
configuration rather than like a claim.

This is the identical shape as ADR 0027's parity test — two implementations
pinned against a shared fixture while the *call site* passed different
arguments — and as ADR 0031/0034's earlier findings. A verification artifact
that maintains its own copy of what it verifies, verifies the copy.

`orval.probe.config.ts` now spreads the shipped `zod` target and replaces
**only** `workspace`. It also throws if `mainConfig.zod.output` is absent,
rather than silently verifying an empty config — a guard that cannot find its
subject must say so, not pass.

With that change the guard immediately reported 409 differing lines.

## Why this ADR does not fix it

Two modes produce two contracts and only one can be committed. Choosing
between them is a decision about the API's behaviour, not a formatting
preference:

- **Adopt `single`** — matches the committed files and today's runtime
  behaviour. Timestamps stay `Date`. Nothing downstream changes. But
  `split`'s per-type files (`types/simulationRequest.ts` and the rest,
  currently committed and imported) are not produced in `single` mode, so
  they would have to go somewhere.
- **Adopt `split`** — matches the declared config and keeps the per-type
  files. Timestamps become `string`. Every consumer of `completedAt`,
  `createdAt` and `updatedAt` changes type, and `check_codegen_loads.py`
  will name each one.

The second is a breaking change to the wire contract's TypeScript surface.
Making it silently, inside a task about protein variants, is exactly the kind
of unrelated change ADR 0027 refused to smuggle in — and refusing to smuggle
it is why that ADR hand-patched a field, which is what created the staleness
in the first place. The cycle closes here rather than continuing.

**So it is reported with the evidence and left to the owner.**

## Consequences

- `check_codegen_loads.py` is now **red**, and correctly so. It was green
  because it was wrong.
- `openapi.yaml` gains `allowVariants` (ADR 0029). The generated files do
  **not** — regenerating them requires resolving the mode question first, and
  hand-patching them again would recreate the defect this ADR is about.
  Nothing references the field yet, so the tree compiles: `tsc --noEmit`
  clean, 559 Python tests passing.
- `allowVariants` therefore remains unreachable over HTTP. The spec describes
  it; the schema does not yet accept it. That is a smaller gap than before —
  the source of truth is updated and the blocker is now one decision rather
  than an unexamined "drift".

## What to do

```bash
# 1. Decide: does the zod target generate `single` or `split`?
# 2. Make orval.config.ts say so.
pnpm --filter @workspace/api-spec run codegen
python3 scripts/check_codegen_loads.py     # must go green
```

If `split` is chosen, expect the date-field type change and read every line
the guard reports before accepting it.

---

## Resolution (2026-08-14)

**The choice this ADR escalated does not exist.** Under the pinned
orval 8.21.0, `mode: "single"` and `mode: "split"` produce *byte-identical*
output for the `zod` target. Nothing had to be decided, and no breaking
change to the wire contract was ever pending.

That was established by running it rather than reasoning about it. A
throwaway config spread the shipped `zod` target and replaced exactly two
keys — `workspace` and `mode` — so the mode was the only variable:

```
single vs split, full recursive diff:   BYTE-IDENTICAL
`coerce` occurrences in api.ts:         11 in single, 11 in split
`datetime({ offset: true })`:           0 in single, 0 in split
```

The override table in "What was found" above is therefore wrong. The
`zod.string().datetime({ offset: true })` output attributed to `split` is not
what `split` emits. It is what an *unpinned* zod version emits — ADR 0030's
finding — and it was misread as a mode difference.

### Each of the three blocking claims, tested

1. **"`split`'s per-type files are not produced in `single` mode, so they
   would have to go somewhere."** False. Both modes emit all 21 files,
   `types/` included. `schemas: { path: "generated/types" }` is what produces
   those files, and it is independent of `mode` — a third run in `mode:
   "tags"` also emits the full `types/` tree.

2. **"orval honours `override.zod.coerce` in `single` and ignores it in
   `split`."** False, as the counts above show.

3. **"Adopting `split` is a breaking change: timestamps become `string`."**
   False, and it follows from (2). `completedAt` is `zod.coerce` in both.

### The experiment was checked before it was believed

An experiment whose knob is not wired reports "no difference" for every
question, which is the same failure mode as a guard that cannot fail. So
before the equality was accepted, a third run set `mode: "tags"` — which
emitted `health.ts` and `simulate.ts` in place of `api.ts`. The override
demonstrably reaches orval, so `single ≡ split` is a measurement rather than
a plumbing artefact.

### Where the 409 lines actually came from

The staleness was real. The **attribution** was not.

`orval.probe.config.ts` was fixed and the guard went from green to 409
differing lines in one step, so the mode — the setting that had just been
corrected — was read as the cause. It was not. Regenerating from HEAD's
committed files against both modes gives the same diff:

```
HEAD's committed files vs single-mode regeneration: 893 differing lines
HEAD's committed files vs split-mode regeneration:  893 differing lines
```

Identical. The drift was the accumulated staleness the guard had never been
able to see, because until it was fixed it had been comparing the tree
against a regeneration of itself. When a broken guard is repaired and
immediately goes red, the redness is about *everything it had not been
checking* — not about the input that was changed to repair it. One change,
one new failure, and the causal link looks obvious; it was a coincidence of
timing.

This is the ADR's own lesson turned on the ADR: a verification artefact that
restates what it verifies, verifies the copy — and when you stop it doing
that, the backlog it had been hiding arrives all at once and misattributes
easily.

### State now

- `check_codegen_loads.py` is **green**, and correctly so: the committed
  contract is byte-identical to what the shipped config produces.
- `orval.config.ts` keeps `mode: "split"`. It was never wrong.
- `allowVariants` (ADR 0029) is **no longer blocked**. It is in
  `openapi.yaml`, in the generated `api.ts` and `types/simulationRequest.ts`,
  and read by `routes/simulate.ts`. The "Consequences" section above, which
  says it remains unreachable over HTTP, is superseded.
- Four scratch files from this investigation are deleted:
  `orval.regen.config.ts`, `orval.tmp.config.ts`,
  `lib/api-zod/src/__codegen_verify__.ts`, and the throwaway
  `orval.mode-experiment.config.ts` that produced the numbers above. Three
  had carried "`rm` this" notes since the sandbox that wrote them could not
  unlink on the host mount. `orval.config.ts` and `orval.probe.config.ts` are
  the only two configs left, which is the number there should be.

### No guard was added for this

The equivalence of `single` and `split` is a fact about orval 8.21.0, and
nothing in the tree depends on it — the committed files are generated from
the shipped config, whatever it says. `check_codegen_loads.py` already fails
if that output changes for any reason, mode included. A dedicated
mode-equivalence check would assert a fact with no consumer, which is the
unexercised-code problem this codebase has spent several passes removing.
