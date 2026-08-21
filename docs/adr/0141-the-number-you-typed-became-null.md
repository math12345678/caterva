# ADR 0141: The number you typed became null, and the report blamed you for it

**Status:** Accepted, implemented

**Date:** 2026-08-20

**Context:** `src/cli/reportQuantities.ts`, `src/cli/scientificCLI.ts`,
`scripts/report_lab.py`

**Relates to:** ADR 0133 (`report`), ADR 0136 (the Result section it
suppressed), ADR 0139 (the previous first-minute barrier), ADR 0003 / 0027 /
0086 (one job, two implementations)

## What was measured

`report` built its payload like this:

```ts
supplied: [{ name: 's0', value: Number(flagValue(rest, '--s0')), unit: 'mM' }]
```

The CLI's own help teaches `--s0 10mM` for `simulate`, so that is what a
student carries over. And:

```
Number('10mM')                     -> NaN
JSON.stringify({ s0: NaN })        -> {"s0": null}
```

`report_lab.py` then built its supplied list with a comprehension filtering
on `s.get("value") is not None`, which **deleted the entry**. Driven end to
end through the real script, the document came back with:

```
the simulation was not run: s0 is missing — yours to choose — how much
substrate you put in, not a property of the enzyme
```

**They chose it.** The tool lost the number and then lectured them for not
providing it.

That refusal is worse than a crash. A crash is obviously the tool's fault. A
refusal that names a plausible cause and reads as actionable sends the
student to fix something that was never wrong — and the sentence doing it is
one written two ADRs ago to be *helpful*, which is how a good message
becomes a bad one when the value reaching it is a lie.

### The second defect is quieter, and worse

`--vmax 0.25` with no unit was passed straight through and used as **mM/s**,
because the engine's other inputs are mM. `parseQuantity` — the reader every
other command uses — assumes **uM/min** for a bare vmax.

So the same three characters meant two things **60,000x apart**, decided by
which command read them. `report`'s own help text contains the sentence
*"assumed unit is reported — vmax in mM/s read as uM/min is off by
60,000x"*, warning about exactly the bug in the command printing it.

A wrong Km fails loudly or looks wrong. A wrong Vmax does neither: it
produces a smooth, plausible trajectory, in a document whose entire purpose
is being handed to a teacher.

## Decision

**`report` reads quantities with the parser every other command uses.**
`src/cli/reportQuantities.ts` routes to `parseQuantity` for the syntax and
`src/units.ts` for the conversion, and does no arithmetic of its own. Both
already existed; the defect was `report` using neither.

Three properties, each pinned:

1. **A value that cannot be read is a stated problem, never a silent null.**
   All problems are collected and shown together — fixing one, re-running a
   BRENDA lookup and meeting the next is how the third gets abandoned.
2. **Every value is converted to the engine's unit**, not assumed to be in
   it. `10000uM` is 10 mM, not 10000.
3. **An assumed unit is recorded as assumed.** `parseQuantity` already
   distinguishes a declared unit from one it chose, and that distinction is
   the provenance argument applied to units, so it travels into the
   document rather than being flattened at the CLI boundary.

**The Python side still checks, and now checks first.** Any caller — the
HTTP API, a notebook, a future front end — can build this payload, and a
`name` with no `value` is a defect in whoever built it. `supplied_values()`
refuses it by name instead of dropping it. It runs **before** the resolver:
the first version of the guard sat after it, so the observed failure was
`Could not resolve 'km': 403 Forbidden` — the network masking the payload
defect completely, and the check untestable without a network.

The help text now shows united values and states the assumed-unit
convention, because an example that teaches the ambiguous form is where this
started.

## Consequences

- 12 jest tests on the parser, 7 pytest tests on the payload guard.
- Six mutations, each asserted to have applied before measuring:

  | mutation | result |
  |---|---|
  | read s0 with `Number()` again | 7 failed |
  | treat a bare vmax as mM/s (the 60,000x error) | 1 failed |
  | stop recording that a unit was assumed | 1 failed |
  | drop a null value silently again | 3 failed |
  | treat `0` as absence | 1 failed |
  | check the payload only after the network call | 1 failed |

- `test_zero_is_a_value` exists because the obvious guard —
  `if not entry.get("value")` — refuses a legitimate `s0` of 0. That is the
  same class of bug as the one being fixed, a real number treated as
  absence, so it is pinned rather than left for a later edit to reintroduce.
- Verified through the real CLI: `--s0 10mM --vmax 0.25mM/s` now reaches
  BRENDA (403 in this sandbox, which is the network, not the tool), and
  `--s0 ten` is refused before anything is fetched with *"'ten' is a name,
  not a quantity"*.

## What this says about the three first-minute defects in a row

ADR 0136 found a section that could never render. ADR 0139 found a flag the
command refused to accept. This one found a value it accepted and destroyed.

All three are the same shape: **`report` was assembled from parts that each
worked, by wiring written fresh at the seam.** Every part had tests; no test
covered the seam, because a seam belongs to neither side.

The generalisable rule, and the one worth carrying forward: **when a command
re-implements something the CLI already does — parsing a number, resolving a
name, running a model — that re-implementation is the bug, and it is
findable without a test by asking what else in the tree already does this
job.** Three for three so far.

## Not done here

`report` still cannot bridge kcat to Vmax. `simulate --resolve` accepts
`--enzyme-conc` and computes `Vmax = kcat x [E]0` (ADR 0013, ADR 0019);
`report` reads neither, so a student must supply a Vmax they have no way of
knowing while Terrium can resolve the kcat behind it from BRENDA.

**This is the same defect class as the two above, and it is the largest
remaining one on this path**, because Vmax is the only required input a
teaching-lab student genuinely cannot produce. Recorded rather than
half-built: the bridge lives in TypeScript
(`src/literature/literatureResolver.ts`) and `report`'s resolution happens in
Python, so connecting them is a decision about which side owns the bridge —
and getting that wrong creates the second implementation this ADR is about.
