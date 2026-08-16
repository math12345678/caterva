# ADR 0049: A refusal still owes you what it found

**Status:** Accepted, implemented

**Date:** 2026-08-14

**Relates to:** ADR 0024 (refusing rather than defaulting — this is about what
the refusal delivers), ADR 0039/0040/0041 (values computed and never
delivered; this is a *file* never delivered), ADR 0012/0013 (why Vmax is the
parameter that most often forces the refusal)

## What was found

Running the command the way a student runs it:

```bash
scientific simulate "michaelis menten" --resolve \
  --substrate pyruvate --organism "Homo sapiens" \
  --enzyme "lactate dehydrogenase" --enzyme-conc 0.01mM --s0 10mM \
  --export-model model.txt --export-citations refs.bib
```

Km resolved — 10.73 mM, BRENDA ref 740253. No kcat was found, so Vmax could
not be bridged, so the run was refused. Correct so far, and the refusal
message is good.

**Neither file was written, and nothing said so.**

`writeExports` is the last statement of `commandSimulateResolved`. The
refusal path `return 2`s about two hundred lines earlier. Both flags were
parsed, validated, and carried in `options` all the way to a function that
this path never reaches.

Nothing failed. Exit code 2 is right, and it is what the user expected.
Against a message saying "cannot run", the natural reading of an absent file
is *of course there is no file, nothing ran* — which is wrong for the
bibliography, and which in any case cannot be distinguished from "written
somewhere I am not looking".

This is the "computed and never delivered" family again (ADR 0039, 0040,
0041) with the undelivered thing being a file rather than a field. It is the
fourth instance found by **running the product** rather than reading it, and
the pattern in how it hid is identical: every unit test of `writeExports`
passes, because they all call `writeExports`.

## Decision

Both flags are honoured on the refusal path, and **the two exports are
treated differently**. The difference is the substance of this ADR.

### Citations are written

A Km resolved from BRENDA with a reference is a real finding. It does not
stop being a real finding because a *different* parameter could not be
resolved. The bibliography describes what the literature said, not what the
simulator managed to do with it.

And the timing matters: a refusal is precisely the moment Terrium is telling
a student to go and read. Withholding the reference list at that moment is
the worst available moment to withhold it.

### The model is not written, and the refusal says so by name

An Antimony file missing `vmax` is not a model. It is a file shaped like one.
It would load into anything that reads Antimony and fail *there* — in a
notebook, in Tellurium, in whatever the student opened it with — instead of
here, where the reason is on screen and actionable.

Writing it would be the same error this tool refuses to make with numbers:
emitting something that looks complete because it looks generated. So it is
withheld, and the user is told, with the path, the cause, and the next step:

```
⚠ Model not written /tmp/exp/model.txt
  The run was refused above, so at least one parameter has no value.
  An Antimony file with a hole in it is not a model — it would load
  and fail in whatever opened it, instead of here where the reason is.
  Supply the missing value and re-run, and the model will be written.
```

Silence was never the honest option. The choice was only ever between
*writing a bad file* and *saying why there is no file*, and the previous
behaviour was neither.

### One function, not two

`writeExports` gained a `runnable` parameter rather than a second
refusal-path exporter being written beside it. Two exporters would be two
lists of which exports exist, and they would disagree the first time a third
export is added — which is ADR 0025's two-collectors problem, prospectively.

## Also fixed, found on the way

`s0` was printed **twice** in every refusal that was missing it:

```
✗ Cannot run. These are unresolved:
    s0 (an experimental condition — supply it, e.g. --s0 10mM)
    s0 (an experimental condition — supply it, e.g. --s0 10mM)
```

`s0` is in every model's `requires` list, so the generic loop over
`INHIBITION_MODELS[model].requires` already reported it; a hardcoded block
further down reported it again with a byte-identical sentence. The block
predated the loop and was left behind when the loop took over.

Two identical lines have an obvious reading — that there are two different
`s0`s — and it is wrong. Deleted at the source rather than de-duplicated at
the print site: suppressing the duplicate at printing would have kept the
second source of truth and hidden it, which is how it survives to cause the
next problem.

## Consequences

- A student whose first run stops on Vmax now leaves with the BRENDA
  reference for the Km that *was* found. That is the common case, not an
  edge case: BRENDA does not report [E]0 per row (ADR 0012/0013), so
  "Km found, Vmax unreachable" is the ordinary way a first run ends.
- `src/cli/__tests__/refusalStillDelivers.test.ts` spawns the real CLI. It
  asserts the message, not merely the file's absence — asserting
  `existsSync === false` alone would have **passed against the original
  defect**, which also wrote no file, silently. The message is the entire
  fix, so the message is what is asserted.
- Both fixes were mutation-tested. Removing the refusal-path
  `writeExports` call fails two tests and leaves the success-path test
  passing; restoring the duplicate `s0` push fails the other two, printing
  the duplicated line verbatim in the failure output.
- A third test pins the success path — a change that suppressed the model
  export entirely would satisfy "does not write a model with a hole in it"
  while destroying the feature.
