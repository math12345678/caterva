# ADR 0189: A tool that did not write it

**Status:** Accepted. A measurement, not a code change.

**Date:** 2026-08-28

**Context:** `Terium/core/combine_archive.py`,
[ADR 0181](0181-what-seven-people-who-build-this-said.md),
[ADR 0187](0187-how-the-value-is-known-as-a-term.md)

## Context

Three records carried the same admission. `combine_archive.py`:

> NOT verified here: that other tools accept it. libSEDML is the reference
> implementation and that is good evidence, not proof. No COPASI or
> Tellurium install exists in this environment to try it against, and saying
> "opens in COPASI" without having opened it in COPASI is the kind of claim
> this project does not make elsewhere.

That was correct discipline and it went unresolved for as long as it was
cheaper to restate than to test. One was installed and it was tried.

## What was measured

Two virtualenvs, because they cannot be one — see below. The **pinned**
environment produced the archive; the **tellurium** environment read it.

| | |
|---|---|
| archive opens | yes — `CITATION.cff`, `manifest.xml`, `model.xml`, `provenance.json`, `simulation.sedml` |
| `te.loadSBMLModel(model.xml)` | loads |
| simulates | 11 × 3, last row `[10.0, 7.5857, 2.4143]` |
| CVTerms visible to the reader | `pubmed:16333295`, `eco/ECO:0000269`, `taxonomy:9606` |
| **`te.executeCombineArchive(...)`** | **succeeded** |

The last row is the one that matters. Tellurium read the SED-ML, resolved
**all four** data generators — `time`, `[S]`, `[P]`, `J0` — against the
model, and ran `simulate(start=0.0, end=10.0, steps=50)`: the exact time
course the export recorded, 51 points, independently reconstructed from the
document rather than passed to it.

Terrium's own in-process run at the same parameters gives
`[10.0, 7.5857, 2.4143]`. Identical to four decimal places.

## What this does not establish

**It is not two independent solvers agreeing.** Terrium integrates through
roadrunner and so does Tellurium. The matching trajectory shows the exported
SBML reconstructs the same model by a different route — a fresh parse of the
written bytes rather than the in-process object — not that two
implementations of the mathematics concur. Reporting it as cross-validation
would be the stronger claim, and it is not the one available.

**COPASI is still untried.** `combine_archive.py` says an `.omex` "opens in
COPASI, Tellurium, JWS Online and the BioSimulators runners". That plural is
now one-quarter measured. The other three are still inference from libSEDML
being the reference implementation.

**One archive, one domain.** Michaelis-Menten, one parameter set. Nothing
here says an SEIR export or a competitive-inhibition export opens.

## Tellurium cannot be installed alongside Terrium

Worth recording separately, because it affects anyone who wants both.

`requirements.txt` pins `antimony==2.14.0`. Tellurium 2.2.13.1 requires
`antimony>=3.1.0`, and pip resolves that by upgrading antimony out from
under the pin — silently, in the same command that installs tellurium.

The requirements file already says *"do NOT `pip install tellurium`"*, for a
different and also true reason: the umbrella pulls python-libcombine and
python-libnuml, which fail at the cmake step where no wheels exist. The
version conflict is a second, distinct reason, and it is the one that bites
on a platform where the wheels *do* exist — as here, where the install
succeeded and quietly moved antimony.

That is why this was measured with two environments rather than one, and it
is also the arrangement a real consumer is in: they run Tellurium, Terrium
runs somewhere else, and the archive is what crosses between them.

## Consequences

- The central claim of the COMBINE export — that another tool can open and
  run it — is measured for one tool instead of inferred for four.
- Three "not verified" notes that were true when written are now narrower.

**What this does not check.**

- **Nothing automated does this.** It was run by hand once. No test
  reproduces it, because the pinned environment cannot import tellurium, so
  a test would need a second interpreter to be meaningful — which is
  possible and is not done here.
- **The result was not inspected numerically.** `executeCombineArchive`
  returned the generated script and its data generators; that the *plot
  values* are right was not checked beyond the direct `loadSBMLModel`
  comparison above.