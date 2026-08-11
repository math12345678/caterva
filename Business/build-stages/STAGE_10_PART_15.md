# Stage 10, Part 15 — `simulate --resolve`, and the four things blocking it

Stage: 10 · Part: 15 · 2026-08-11

## 1. What now works

```
$ scientific simulate mm --resolve \
    --enzyme "lactate dehydrogenase" --substrate pyruvate \
    --organism "Homo sapiens" --s0 10mM --enzyme-conc 0.001mM

Parameters and where they came from
  s0    10 mM      user
  e0    0.001 mM   user
  km    0.14 mM    brenda_exact  BRENDA ref 12345
  vmax  0.25 mM/s  brenda_cross_species → kcat x [E]0  BRENDA ref 649716
        ⚠ measured in Oryctolagus cuniculus, not the organism requested

  2 of 4 parameter(s) carry a literature citation.

Result
  initial    10.0000 mM
  final      7.5395 mM
  consumed   2.4605 mM
  points     101
```

Kinetics resolved from BRENDA, Vmax bridged from kcat × [E]₀ by the
engine's own `vmax_from_kcat`, simulation run by the real Python engine,
and **every number on screen says where it came from**. Anything that
cannot be sourced stops the run instead of being defaulted.

Getting there required removing four separate blockers, each of which made
the literature path structurally impossible.

## 2. `simulate` was hardcoded to lactate dehydrogenase

```ts
const literature = await fetchRealLiterature('lactate dehydrogenase', 'lactate');
```

Those two strings, literally, for every simulation of every system. And the
`Literature` objects it built carried `extractedParameters: []`, so the
recommender had no values to recommend — which is why every run died with
`NO_LITERATURE` no matter what was asked.

It also set `peerReviewed: true` with the comment *"Papers in PubMed are
peer-reviewed by definition"*. That is false: PubMed indexes preprints (the
NIH preprint pilot), editorials, letters, comments and retracted articles.
The field feeds `LiteratureVerifier`, which trusts it. Now `false` — the
DOI is what gets checked; review status is left unasserted rather than
invented.

## 3. The validator demanded citations for things nobody measures

Every run failed at Layer 1 with *"Parameter 's0' has no literature
backing"*.

Km, Ki, kcat and Vmax are **properties of an enzyme** — somebody measured
them, and a value without a source is an unsupported claim. But s0, [E]₀,
temperature and pH are **choices the experimenter makes**. Nobody measures
"the initial substrate concentration of lactate dehydrogenase", because it
does not have one. Demanding a citation for it is a category error, and it
made every simulation impossible however well-sourced its kinetics were.

`EXPERIMENTAL_CONDITIONS` is now an explicit, deliberately small set — not
a heuristic like "anything ending in 0", which would quietly exempt a
future measured quantity and turn the exemption into a hole. A condition
still has to be *stated*; it just cannot be *cited*, and it is reported as
user-supplied rather than dressed up as literature-backed.

## 4. Provenance was lost between resolution and validation

A Km resolved live from BRENDA — with a real reference id — reached
`buildParameterMetadata`, which looked literature up in the **in-memory
database** (empty), found none, and failed the run. The parameter had just
been sourced.

Two changes: `ParameterRecommendation`'s citations are carried onto the
resolved parameter, and `SimulationRequest` gained `providedProvenance` so
a caller that resolved something itself can say where it came from. The
CLI's `--resolve` path needs this because it performs the kcat → Vmax
bridge the pipeline's own resolver does not cover, then hands the pipeline
plain numbers.

`SimulationResponse` now returns `parameterProvenance` too — one
resolution, one provenance record, emitted by whoever did the work rather
than reconstructed by each caller.

## 5. Layer 2 collapsed "rejected" and "unverified"

It called the boolean `verifyReference` and failed the run on anything not
`true`. That treated two different facts identically:

- **rejected** — the registry says this DOI does not exist, or the source
  is not peer-reviewed. A fabricated citation; the run must stop.
- **unverified** — no identifier to check, or the registry unreachable.
  Nothing is known either way.

Collapsing them made every BRENDA-sourced value unusable: a BRENDA
reference id is a real pointer into the primary literature, but it is not a
DOI or PMID, so there is nothing for CrossRef to confirm. The value is
genuinely sourced *and* genuinely not DOI-verified, and Layer 2 now reports
exactly that — rejecting fabrications, warning on unverified, and never
calling either "verified".

This is the three-state verifier from Part 11 finally being used by the
layer that most needed it.

## 6. A bug of my own worth recording

`commandSimulateResolved` printed the result block before checking
`response.validated`. The pipeline returns a fully-shaped response even
when validation stops the run — empty trajectory, `finalValue: 0`, blank
reproducibility key — so the output read:

```
Result
  initial    undefined mM
  points     0
```

and exited **0**. A success report for a simulation that never executed —
the exact defect class this repository keeps correcting, written by me
while fixing it. Now checked before anything is presented, exit 2.

## 7. Verification

- Root tree: **205 / 205** passing, 13 suites (was 199).
- api-server: **422 / 422**, `tsc` clean.
- Python engine: 285 passed, same 9 `stdpopsim` failures.
- Guards: Engine Contract, Guard Wiring, Plausibility Constants, Domain
  Parity, Documented Counts all pass. The last one *failed first* — it
  caught that I had added tests and literature references without updating
  the README (1,303 → 1,308; 289 → 294). A guard doing precisely its job.
- 7 new `--resolve` end-to-end tests spawning the real binary, including
  the refusal paths: unresolved Vmax without `--enzyme-conc`, missing s0,
  a system not named on the command line, and an unreachable registry.

Two test-hygiene bugs fixed along the way: stub scripts written to fixed
filenames were being rewritten by concurrent ts-node processes, so a kcat
query occasionally got answered with the km branch. Every stub now gets a
unique path.

## 8. Still open

- The live BRENDA path remains unproven from this sandbox (403). Every
  `--resolve` behaviour is verified against a stub that returns the real
  runner's shape; the first thing worth doing on a networked machine is a
  real lookup.
- `--cite` emitting BibTeX for everything a run touched.
- `check-integrity` and `verify` operate on in-memory job IDs that do not
  survive the process, so they remain unusable from the CLI.
- The five Part 12 audit findings are still open.
