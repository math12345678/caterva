# Stage 4, Part 6 — Closing Report

Stage 4 of 100 is closed. 96 remain.

## 0. Why this stage had six parts

Stages 1–3 each ran five: grounding, spec, implementation, verification,
close. Stage 4 ran six because Part 5 turned out to be a build part (the
citation-format guard) rather than a close, and a stage should not end on an
audit amendment. This part is the actual close.

Worth noting rather than smoothing over: the five-part structure is a
convention that fit the domain stages, not a law. Stage 4 was not a domain
stage.

## 1. What Stage 4 delivered

**The engine became reachable.** At the stage's open, `tellurium_runner.py`
dispatched three domains while the engine exposed eight — every domain built
under the constitution was invisible to the product. All nine entries
(including the typed `sbml` escape hatch) now dispatch, with the
`ok`/`flagged`/`flagReason` contract verified to survive the Python →
TypeScript crossing for each.

**The boundary became self-defending.** `test_boundary_contract.py` loads the
real runner from source and fails if the engine's `__all__` and the runner's
`DISPATCH` table drift in either direction. Verified against a genuine file
edit, not just a monkeypatch: adding `simulate_gillespie_ssa` to `__all__`
fails two tests, and reverting restores them. That is the Stage 6 scenario,
tested before Stage 6 exists.

**Provenance became honest.** Per-parameter `ParameterOrigin`
(`resolved` / `user` / `default`), citations permitted only on resolved
entries, and `citations` renamed to `modelCitations` — a deliberately
breaking change, because a field with the old name sitting beside a parameter
block will keep being misread.

**The citations became true.** Three of seven were wrong. One title did not
exist.

**Three executable guards now run unasked**, in pytest, CI, and
`verify_domain.sh`: RNG convention, declared dependencies, citation format.

**ADRs 0007 and 0008** record the boundary-contract decision and the
provenance contract.

## 2. What Stage 4 taught, which matters more than what it built

### 2.1 Structural tests cannot see semantic emptiness

Part 3's Target A checks that `parameters` and `parameterProvenance` have the
same keys. Target B checks that citations appear only on resolved parameters.
Both passed continuously — while three of seven citations were wrong,
including *"Physical clusters of simple liquids,"* a paper that does not
exist.

A fabricated title is a perfectly well-shaped string. The tests verified the
*shape* of a provenance record and could not, even in principle, see that its
contents were false. Any verification scheme has a class of error it is
structurally blind to, and the useful question about a test suite is not
"does it pass" but "what can it not see."

### 2.2 The same claim keeps being wrong in the same way

Five instances now, across four stages:

| Stage | Claim | Reality |
|---|---|---|
| 2 | report: "3 tests fail under 2N→N" | 2 fail |
| 3 | comment cites `STAGE_04_PART_01 §6.3` | section does not exist |
| 4 P2 | "MD 10k steps ~11s" | never measured; 7.32s |
| 4 P4 | "Hoare & Pal, *Physical clusters of simple liquids*" | title does not exist |
| 4 P5 | "the repo has no workflow files" | two CI jobs, tracked, predates Stage 1 |

Every one: plausible, structurally valid, unchecked, wrong, and cheap to
check. Rule 1 was written for numerical claims. Stage 4 establishes that it
governs **every** factual claim a document or comment makes — bibliographic,
environmental, and timing claims included.

The Part 5 case is the instructive one, because the false premise had a
consequence. Believing there was no CI made enforcement look hypothetical,
so the guard shipped wired to nothing. A wrong belief about the environment
produced real undone work.

### 2.3 A guard is not delivered until something runs it

`check_citation_format.py` was built, correct, and verified — and referenced
by no test, no CI step, and no verification script. It ran only when a human
typed its name.

This is the second occurrence. `check_rng_convention.py` sat the same way
after Stage 2 until a test wrapped it. The lesson did not transfer between
stages, which is the argument for putting it in the constitution rather than
in another closing report.

### 2.4 Green tests can prove nothing at all

During the Part 3 audit, `tellurium_engine.py` was a re-export shim that
imported all 67 public names from the new package **and then redefined all 64
of them below**. Python takes the later definition, so the package was
imported and immediately shadowed.

Every test passed. Not because the refactor worked — because the monolith was
still doing the work. *"The suite is green"* answers "is something producing
correct output," not "is the change I made in effect." Those are different
questions and only the first has a test.

### 2.5 Verifying that a guard fails requires checking the exit code

An early attempt to confirm the citation guard rejects a bad entry piped its
output through `tail` and read `$?` — which reported `tail`'s status. It
appeared to show a guard that printed violations and exited 0, i.e. one that
could never fail CI. It does exit 1.

Small, but it is the same species as the `&&`-chaining hazard from Stage 1:
a shell construct silently answering a different question than the one asked.

## 3. Real defects found and fixed during the stage

| Defect | Found in |
|---|---|
| 5 of 8 engine domains unreachable from the product | Part 1 |
| Two files both numbered ADR 0007, one unindexed and invisible | Part 1 audit |
| `LEVELS_UP` directory-depth heuristic for `REPO_ROOT` | Part 1 |
| MD runtime ceiling bounded `n_steps` but not `N²·steps`; a passing request OOM-killed the worker | Part 2 audit |
| Phantom citation `STAGE_04_PART_01 §6.3` + unmeasured "~11s" | Part 2 audit |
| Engine package split broken: missing exception classes, circular imports masked by a fallback | Part 3 audit |
| `core/validation.py` converts four plausibility **flags** into hard **rejections** | Part 3 audit |
| Three of seven citations wrong; one title fabricated | Part 4 |
| Citation guard enforced nowhere | Part 5 audit |
| False "no workflow files" claim | Part 5 audit |

## 4. Honest status

**Closed.** Domain exposure, boundary contract test, application-layer CI,
`repoRoot.ts`, runtime ceilings including the quadratic MD budget,
per-parameter provenance, `modelCitations` rename, ADRs 0007 and 0008, the
citation guard and its wiring, all seven references verified against primary
sources.

**Open, and blocking a future stage — the engine package split.** The package
under `Tellurium/{core,continuous,discrete,scenarios}/` is complete: all 67
public names resolve from it. The engine does not use it; the shim was rolled
back, so it is orphaned. Fixes applied during the audit (exception classes,
relative imports across 13 modules, `pytest.ini` path, dependency-guard
nested-package support, `conftest.py`) leave it importable and ready.

One thing must be fixed before it lands, and it is not cosmetic:
`core/validation.py` does not reproduce engine semantics. It converts four MD
plausibility flags into hard rejections —

```
engine  validate_md_params(108, 0.9, ...)  ->  ok=True,  flagged=True
core/   validate_md_params(108, 0.9, ...)  ->  ok=False
```

— which violates Rule 2 explicitly and would invert Stage 3's deliberate
decision that a hot cluster is valid-but-implausible physics a student may
want to model. Latent only because nothing imports the package. Full detail
and a four-step completion path in `REFACTOR_STATUS.md`.

**Carried to Stage 5.** Whether a `resolved` citation must satisfy a stricter
format than a `modelCitations` entry (Part 4 §5, ADR 0008). This guard stops
deliberately at `modelCitations`.

## 5. Stage 5

Unchanged from the architecture assessment: **the provenance contract.**

Stage 4 made the API honest about what it knows. Stage 5 makes it know more.
The open questions, in the order they need answering:

1. Does provenance travel **with** the parameter through the Python engine,
   or stay in a parallel channel rejoined at the end? Recommendation: with. A
   citation and the number it supports should not be separable by a
   refactor — today they are, and nothing checks they still correspond.
2. What is the `verified`/`flagged`/`rejected` contract for a *citation*, as
   distinct from a value? Proposal: exact organism and substrate match from a
   primary source is `verified`; cross-species or inferred substrate is
   `flagged`; no source, or LLM-generated with no corroborating record, is
   `rejected`. That last case is the one that matters.
3. What is Rule 1 for provenance? The numeric side has closed forms. The
   provenance side needs an equivalent: a golden set of hand-verified
   enzyme/substrate/Km/citation tuples asserted end to end.
4. What is a mutation test for the resolver? Swap a returned Km for a
   plausible wrong-organism value and require an end-to-end test to fail. If
   nothing fails, the trust trail is decorative.

Only one parameter in one domain (`km` in `mm`) is currently resolved from
literature at all. Stage 5 should decide whether to widen that or to make the
narrowness explicit in the API — and it should decide it deliberately, in
writing, rather than inheriting it.

Gillespie SSA remains first in the domain queue when domains resume at
Stage 6.
