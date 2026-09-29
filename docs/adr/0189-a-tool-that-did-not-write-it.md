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

~~**It is not two independent solvers agreeing.**~~ **It now is, because
COPASI was tried too.** Both Terrium and Tellurium integrate through
roadrunner, so that pair showed only that the exported SBML reconstructs the
same model by a different route. COPASI has its own integrator.

| | substrate at t=10 |
|---|---|
| Terrium, in-process, roadrunner | `7.585660864700605` |
| COPASI 4.46.300, via basico | `7.585661077467333` |

Absolute difference **2.13 × 10⁻⁷**, relative **2.80 × 10⁻⁸** — agreement to
about seven significant figures. That residual is the right size for two
adaptive solvers at their default tolerances, and its being non-zero is
itself the evidence that these are different integrators rather than the
same one twice.

COPASI loaded the SBML, found both species (`S`, `P`) and both parameters
(`Vmax`, `Km`), and ran the time course.

~~**COPASI is still untried.**~~ **Half measured now.** `combine_archive.py`
claims an `.omex` "opens in COPASI, Tellurium, JWS Online and the
BioSimulators runners". Two of the four have opened one. JWS Online and the
BioSimulators runners remain inference.

**One archive, one domain.** Michaelis-Menten, one parameter set. Nothing
here says an SEIR export or a competitive-inhibition export opens.

**COPASI read the model, not the archive.** `basico.run_combine_archive`
does not exist in basico 0.86, so the whole-archive path was tested in
Tellurium only. COPASI was handed `model.xml` directly.

**COPASI's per-parameter CVTerms were not confirmed.**
`basico.get_miriam_annotation()` returns the MODEL-level annotation — a
created date — and the API surfaces no obvious per-parameter equivalent.
That the CVTerms are in the bytes is established by the libSBML read-back
above; that COPASI shows them to a user is not.

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