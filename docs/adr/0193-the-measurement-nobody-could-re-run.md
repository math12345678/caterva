# ADR 0193: The measurement nobody could re-run

**Status:** Accepted, implemented

**Date:** 2026-08-29

**Context:** `scripts/verify_export_opens_elsewhere.py`, `Makefile`

**Closes a gap named in:** [ADR 0189](0189-a-tool-that-did-not-write-it.md)

## Context

ADR 0189 measured, by hand, that Tellurium and COPASI can open Terrium's
COMBINE export. It closed by naming what that left:

> **Nothing automated does this.** It was run by hand once. No test
> reproduces it, because the pinned environment cannot import tellurium, so
> a test would need a second interpreter to be meaningful.

ADR 0186 made exactly this argument about a different hand-run procedure —
that a measurement which is right only when somebody remembers to run it
correctly is a habit, not a check — and turned it into a script. This is
that argument applied to my own.

## Decision

`scripts/verify_export_opens_elsewhere.py` builds an archive with the
**pinned** interpreter, hands it to a **second** one named by
`TERRIUM_INTEROP_PYTHON`, and compares what comes back: the archive opens,
a reader integrates it, the CVTerms are visible, and the trajectory matches
Terrium's own within `1e-6`.

**It is not called `check_`, and that is the point.** This project's rule is
that "a guard is not delivered until something runs it unasked", and nothing
can run this unasked: no CI here has a second environment. Naming it
`check_*` would have claimed a status it cannot have —
`check_guard_wiring` globs `check_*.py` and would have demanded a harness
that does not exist. It is a reproducible procedure, reachable through
`make interop READER=...`, deliberately outside `make guards` so it cannot
sit permanently red — the failure ADR 0179 spent a commit removing.

**A missing reader is exit 3.** "No reader available" is not "the archive
opens", and the three-state discipline is the whole reason this is worth
having rather than a script that quietly passes on a machine with nothing
installed.

## Two defects in the first version, both mine

**It reported a false failure against COPASI.** The reader snippet wrote the
SBML with `open(path, "w")` and no encoding; the model carries non-ASCII, so
a reader whose default encoding is not UTF-8 raised `UnicodeEncodeError` —
and the guard reported that as *the export* failing.

**Worse, it conflated "not there" with "nobody looked".** The COPASI
environment has no standalone `libsbml` (COPASI bundles its own), so the URI
list came back empty and the check announced *"the evidence CVTerm did not
reach the reader"*. That is false: nothing had inspected the model. It is
also the exact three-state failure this project keeps recording, committed
by a script written to close one. The reader now reports whether annotations
were **readable at all**, and an unreadable case prints `NOT CHECKED:` and
passes the rest, rather than failing on an absence it never established.

## Verification

Both readers, through `make interop`:

| reader | result | substrate at t=10 | relative |
|---|---|---|---|
| Tellurium 2.2.13.1 | opens, integrates, 3 CVTerms visible | `7.585665132813549` | 5.63e-07 |
| COPASI 4.46.300 | opens, integrates, annotations not inspectable | `7.585661077467333` | 2.80e-08 |

Terrium's own: `7.585660864700605`. The COPASI figure reproduces ADR 0189's
hand measurement to every digit, which is the point — the automated version
agrees with the manual one it replaces.

Selftest: no reader configured → exit 3; a reader path that does not exist →
exit 3; and the tolerance admits 2.8e-08 while rejecting a 1% difference.
`make interop` with no `READER` exits 3 and says why.

## Consequences

- ADR 0189's central claim can be re-run by anyone with a second
  environment, instead of being a sentence about something I once did.
- The COPASI result is now reproducible to the digit rather than quoted.

**What this does not check.**

- **Still two of four tools.** JWS Online and the BioSimulators runners
  remain inference.
- **Nothing runs it unasked**, by construction. If nobody types `make
  interop`, nothing here notices the export breaking — this makes the
  measurement repeatable, not automatic.
- **One archive, one domain, one parameter set.** Michaelis-Menten only.
- **COPASI's annotations were never inspected**, in the hand run or this
  one. That the CVTerms are in the bytes is established by libSBML; that
  COPASI surfaces them to a user is not.
