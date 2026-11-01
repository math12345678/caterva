# ADR 0146: The artifact that did not reproduce

**Status:** Accepted (document written after the fact — see the note below)

**Date:** work landed circa 2026-08-18; this document 2026-08-29

## A note on this record's history

This ADR number appeared in the index with a full summary row and **no
document behind it** — no file, in any commit, on any branch. Three audit
passes (ADRs 0165–0167) found the dead link, measured whether the work the
row describes exists, and left the resolution to a decision rather than
retracting silently. This file is that resolution: the work IS in the
tree, verified against the row's own claims, so the missing document is
written rather than the true row deleted. What cannot be reconstructed —
which session wrote the row, why the file never landed — is not invented
here.

## Context

`simulate --export-model` wrote the model with its parameter values **as
typed**. The CLI reads `--vmax 12.8` as 12.8 µM/min (its documented
assumed unit) and integrates accordingly; the exported SBML said
`Vmax = 12.8` with no unit anywhere — which every SBML consumer reads in
the file's own (undeclared, therefore arbitrary) system.

Measured, not reasoned: re-running the exported file exhausted the
substrate by t = 2.2 s, while Caterva had just printed S = 8.245 at
t = 12,930 s. **The reproducibility artifact contradicted its own run by
60,000×**, in valid SBML with zero read errors. It is the artifact that
outlives the terminal, gets attached to a report, and is the only thing a
reviewer can check.

## Decision

Convert every exported value into **the substrate's units per second** —
the system the engine integrated in and the printed trajectory is in —
before the payload crosses to the Python exporter
(`src/cli/scientificCLI.ts`, the block above the `exportModel` call). The
unit is written into each parameter's `<notes>` so a human is not left
guessing. `--export-model` was also made reachable without BRENDA: an
export of user-supplied values needs no lookup.

**The gap this leaves is named rather than papered over**, in the code
comment itself: without unit declarations the file still says `2.13e-4`
rather than `2.13e-4 mM/s`. That needs `unitDefinition` support in the
Python exporter — which is ADR 0150.

## Verification

The row's claims, checked against the tree on 2026-08-23 before this
document existed: the conversion code and its comment are at the
`exportModel` call site, `vmaxInSubstrateUnitsPerSecond` exists and is
called, and the "units only in `<notes>`" caveat matched the code
verbatim. The end-to-end export tests in
`src/cli/__tests__/cliEndToEnd.test.ts` pin the converted values.

## Consequences

The file is internally consistent and reproduces its run — and remains
mute about its unit system to any consumer that cannot read prose. That
is ADR 0150's subject, closed there.
