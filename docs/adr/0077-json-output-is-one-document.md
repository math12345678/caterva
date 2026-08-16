# ADR 0077: `--json` is one document, and the exports still happen

**Status:** Accepted, implemented

**Date:** 2026-08-15

**Relates to:** ADR 0049 (fixed this for the human path; the JSON path kept
the defect), ADR 0070/0066/0059 (the same method finding the previous three)

## What was found

Checking that every command advertising `--json` emits a document a script
can parse. `corpus` and `sweep` were clean. `simulate --resolve` had the same
defect in both directions at once.

### The successful path wrote no files at all

```ts
if (options.json) {
  process.stdout.write(JSON.stringify({ ok: true, ... }) + '\n');
  return 0;               // <- writeExports is 70 lines below
}
```

`--export-model` and `--export-citations` produced **no file and no
message** under `--json`. That is precisely the defect ADR 0049 fixed for the
human path, still live for anyone scripting the tool — and quieter there,
because a script does not notice a missing file the way a person reading a
terminal does.

### The refused path corrupted the document

ADR 0049's fix called `writeExports` on the refusal path, and `writeExports`
writes human prose. Under `--json` that prose landed after the JSON:

```
$ simulate ... --json --export-citations refs.bib
json.decoder.JSONDecodeError: Extra data: line 39 column 1 (char 738)
```

**That one was mine**, introduced by ADR 0049 four passes earlier and found
now only because this pass ran `--json` with export flags — a combination the
five tests written for ADR 0049 never tried, because none of them passes
`--json`.

## Decision

**One sink for prose.** Everything `writeExports` says goes through a local
`say()` that writes nothing under `--json`. Suppressing the messages alone
would trade a corrupt document for a silent one, so the outcome is reported
inside the document instead:

```json
"exports": {
  "model": null,
  "citations": "/tmp/refs.bib",
  "modelWithheld": "the run was refused, so at least one parameter has no value"
}
```

`model: null` on the refusal path whatever was requested — an incomplete
model is not written, and echoing the requested path would imply a file that
does not exist. The reason is given rather than left to be inferred.

The success path reports the paths **requested**, not `written: true`. This
function does not stat the files afterwards, and asserting the success of a
write it did not observe is the kind of claim this tool exists to avoid; a
caller can check with one `stat()`.

**Order differs by mode, with one call site.** Human output prints the
refusal first and then the export messages — one of which says "the run was
refused above", which has to be true. JSON writes the exports first (silently)
so the document can report them. That is `if (!json) prose; writeExports();
if (json) document;` — a single `writeExports` call, because two would be two
lists of which exports exist and would disagree the first time a third export
is added.

## A self-inflicted bug worth recording

The `say()` conversion was applied by a scripted find-and-replace of
`process.stdout.write(` → `say(` across the function body. It rewrote the call
**inside `say` itself**:

```ts
const say = (text: string): void => {
  if (!options.json) say(text);   // recurses
};
```

`RangeError: Maximum call stack size exceeded`, surfacing as `✗ Fatal error`
*after* the refusal had already printed — so the run looked like it had merely
failed late, and the exit code went 2 → 1. Caught by running the human path
immediately after the change rather than trusting the type checker, which was
perfectly happy.

This is the second blanket-edit accident in this repository (the first put a
fixed indent on 22 import-mode sites, two of which were nested). The lesson is
the same both times: a mechanical rewrite over a region needs its own
inspection of every site, because the one site that must not change is
usually the definition of the thing being introduced.

## Consequences

- Three tests added to `refusalStillDelivers.test.ts` covering the
  combination its original five missed. The last asserts the whole stream
  parses, rather than checking for particular stray sentences — the next
  message added to `writeExports` would slip past a substring check.
- Mutation-tested: restoring the early `return 0` above `writeExports` fails
  the success-path test while the other two keep passing.
- All four combinations verified by running the CLI directly: refused+json
  (exit 2, valid document, bibliography written, model withheld with reason),
  success+json (exit 0, both files written), and both human paths with their
  original message ordering intact.


---

## Amendment (2026-08-15, same evening): the fix above closed the instance, not the class

The decision above routed `writeExports`' prose through a guarded sink and
stopped there. Auditing the rest of the function immediately afterwards found
**eleven more prose writes reachable while `options.json` was true**, in
branches the new test never entered:

| branch | what it printed ahead of the document |
|---|---|
| `--ki` + `--i0` under plain `mm` | `• Did you mean --model competitive? ...` |
| `--sensitivity` | the entire provenance table, via `printProvenance` |
| product inhibition | `PRODUCT_INHIBITION_CAVEAT` |
| resolver warnings | the warnings list |

Measured:

```
$ simulate ... --resolve --ki 5mM --i0 1mM --json
• Did you mean --model competitive? ...
{ "ok": true, ... }
-> Expecting value: line 2 column 1 (char 1)
```

So `--json` was still corruptible by any of four other paths, and the test
written to pin the fix passed because the single scenario it ran triggered
none of them.

**A per-function sink, not per-call-site.** `commandSimulateResolved` now has
the same `say()` as `writeExports`, so a message added later is quiet by
default. Getting this right by remembering to wrap each new
`process.stdout.write` is precisely the arrangement that had just failed
twice in one evening.

`printProvenance` is a separate function that writes directly, so its one
reachable call site is guarded explicitly rather than being routed — the
sensitivity path calls it and then hands off to `commandSensitivity`, which
emits its own document.

### The scripted rewrite overran, and the type checker caught it

Converting the calls by script again — carefully this time, excluding any
whose call spans a `JSON.stringify` and excluding the sink definition — the
loop ran to the end of the FILE rather than the end of the function, and
converted eight writes inside `printProvenance`, where `say` is not in scope.
`tsc` reported `Cannot find name 'say'` at all eight and they were reverted.

Third blanket-edit accident in this repository, and the first one a compiler
could catch. The two it could not — the indent applied to nested import-mode
sites, and `say` calling itself — were both caught by running the thing.

### The test enumerates combinations, not scenarios

`jsonIsOneDocument.test.ts` lists six flag combinations, each annotated with
the branch it exists to enter, and asserts the same property of all six —
reporting every failure together, because fixing one leak and re-running a
two-minute suite is how the third gets left.

Its second assertion is the guard against overcorrecting: the same run
*without* `--json` must still print `Did you mean` and the provenance table.
A sink that was silent always would satisfy the first assertion perfectly
while deleting the human interface.
