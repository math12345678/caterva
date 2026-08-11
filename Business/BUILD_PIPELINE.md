# Build pipeline — how Terrium gets coded from here

Who does what, in what order, with what prompt, and what has to be true
before anything gets merged. Written because the moment more than one coding
agent touches this codebase, the standards that used to live in one person's
head (mine, this session) have to live in a document instead — otherwise
every agent quietly re-derives its own idea of "done," and the class of bugs
this repo already hit once (undeclared deps, a reserved-keyword collision,
PCR forced through the wrong pipeline) happens again, just with more tools
touching the code.

## Roles

**Orchestrator Role — Claude**
The orchestrator does not write domain code. Responsibilities include: maintaining
standards across sessions, writing specifications for implementers, reviewing diffs
against specifications, and running verification (tests, mutation testing, dependency
scans) rather than accepting unverified claims about code quality.

**OpenCode / FreeBuff — implementers.**
Both write code from a spec I give them. Treat them as replaceable and
parallel, not specialized — the same spec should work for either. Two
reasons to run both instead of picking one: (1) a second independent
implementation of the same spec is a cheap correctness signal — if OpenCode
and FreeBuff produce meaningfully different logic for the same closed-form
check, that's worth looking at before either lands; (2) redundancy against
either tool having an off day, which free/lighter tools do more often than
paid ones.

**Perplexity / Kimi (optional) — research, not implementation.**
Use one of these *before* Stage 1 below, not instead of it, when a new
domain needs grounding you don't already have — the actual governing
equations for population genetics allele-frequency drift, the standard
Monte Carlo variance-reduction techniques worth supporting, what a
molecular dynamics "setup" tool should minimally validate. Their output
becomes input to the spec I write, not code that lands directly. Neither
of them has read this repo's ADRs or test conventions — don't let their
output skip the spec step.

## Why the spec step exists

Every implementer in this pipeline starts each session with zero memory of
`docs/adr/`. If I hand OpenCode "implement Monte Carlo simulation" with no
more context than that, I get code that might be fine, or might repeat a
mistake this repo already made and fixed once — see `docs/adr/0002` (PCR is
a discrete recurrence, not an ODE — the wrong domain would get forced
through antimony/roadrunner if nobody says otherwise), `0003` (Km
plausibility bounds have to stay in sync between the literature layer and
the simulation layer, enforced by a real test, not a comment), `0004`
(`gamma` collides with an antimony reserved word — anything with a rate
constant named that needs the `_rate` suffix trick).

So the spec I write for each new domain has to include, every time:

- Which ADRs are relevant to this domain and what they mean concretely for
  the implementation (continuous vs discrete, naming collisions, shared
  bounds).
- The exact closed-form solution, independent solver, or physical
  invariant the tests must check against — decided *before* implementation
  starts, per `CONTRIBUTING.md`'s own standard, not retrofitted after.
- The `ok` / `flagged` validation contract (`docs/API.md`) and where this
  domain's plausibility bounds come from.
- What mutation-testing this specific change requires — which lines, if
  deliberately broken, must make a specific test fail. This gets written
  into the spec as a checklist, not left to whichever implementer
  remembers to do it.

## How a stage works: the 5-part structure

Every stage follows the same five-part cycle, established and verified
during Stage 1 (Monte Carlo). The Constitution at `docs/CONSTITUTION.md`
is the canonical reference — read it for the operative rules; this section
describes the workflow.

**Part 1 — The standards preamble.** Every implementation prompt is
prefaced with the text in `docs/CONSTITUTION.md` Section 3 (the nine
non-negotiable rules, the mutation-testing requirement, the report-back
requirement). This is not optional — the rules exist because each was
learned from a real bug in this exact codebase.

**Part 2 — The domain-specific spec.** Written by Claude following the
10-field template in `docs/CONSTITUTION.md` Section 4: one-sentence
definition, governing model, continuous-or-discrete (with justification),
public function signatures, validation contract, verification target,
relevant ADRs, shared-constraint check, out-of-scope boundary, and
deliverables checklist. This is the spec sent to OpenCode/FreeBuff.

**Part 3 — Implementation.** OpenCode and/or FreeBuff receive the exact
same spec (prefaced with the Part 1 preamble). Both implement
independently. Output: code + tests + mutation-test report.

**Part 4 — Verification and divergence resolution.** Claude runs the
mechanical verification steps (`scripts/verify_domain.sh <domain>` — see
below), independently reproduces at least one claimed mutation test, and
resolves any substantive divergence between the two implementers' outputs
per `docs/CONSTITUTION.md` Section 7.

**Part 5 — Closing.** The stage-closing report is written (see
`Business/build-stages/STAGE_01_PART_05.md` Section 3 for the format),
and the commit lands with a message stating what shipped, what was
verified, what's still open, and whether the next stage is ready.

### Tools

- **Research groundings** (optional, before Part 2): Perplexity or Kimi
  when a domain needs literature grounding you don't already have. Output
  folds into the spec's Verification Target section — it does not go
  straight to an implementer.
- **Verification script**: `scripts/verify_domain.sh <domain>` runs Steps
  1-3 of the verification procedure mechanically (full suite, dependency
  guard, test collection). Step 4 (mutation-test reproduction) is
  deliberately manual — run it per `docs/CONSTITUTION.md` Section 6, Step
  4, with the `&&`-chaining trap noted there (found by FreeBuff during
  Stage 1's own review).

## Prompt templates

### For a new simulation domain (OpenCode or FreeBuff)

Build the prompt by concatenating:

1. `docs/CONSTITUTION.md` Section 3 (the permanent preamble, verbatim).
2. This domain-specific block:

```
You are implementing [DOMAIN NAME] for the Terrium simulation engine, in
Tellurium/tellurium_engine.py, following the exact patterns already in that
file for [closest existing domain — e.g. PCR or SIR].

Read these first and match their conventions exactly:
- Tellurium/tellurium_engine.py (existing domain implementations)
- docs/adr/0001-no-tellurium-umbrella-package.md
- docs/adr/0002-pcr-not-modeled-as-an-ode.md
- docs/adr/0003-shared-plausibility-bounds.md
- docs/adr/0004-gamma-reserved-keyword.md
- docs/adr/0005-rng-convention.md (all discrete/stochastic domains use
  ``numpy.random.default_rng(seed)`` with ``seed: int | None``)
- docs/API.md
- docs/CONSTITUTION.md (the engineering constitution — the preamble above
  is Section 3; the full document governs what "done" means)

Spec:
[PASTE DOMAIN SPEC HERE — the 10-field template from CONSTITUTION.md
Section 4, fully filled in for this domain]

Requirements:
- Match the ParameterValidation / SimulationResult contract exactly as used
  elsewhere in the file.
- Write tests in Tellurium/tests/test_[domain]_correctness.py using
  Hypothesis property-based testing with max_examples=200, matching the
  style of test_pcr_correctness.py.
- Every numerical claim must be checked against the closed-form/invariant
  specified above — not "looks reasonable," an actual assertion against a
  known-correct value.
- If you add any new import, add it to requirements.txt in the same change
  — do not leave that for CI to catch.
- Do not modify any file outside Tellurium/ unless the spec says to.
- Document at least one mutation test in your report (what you broke, which
  test caught it).

When done, report: what you implemented, what you tested it against, what
mutation test you ran and what it caught, and any judgment call you made
that wasn't explicit in the spec.
```

### For a bugfix / small change

```
Bug: [description]
Reproduction: [exact params/command that trigger it]
Expected: [what should happen, with the source of truth — citation, hand
calculation, independent tool]

Fix it in the minimal way that doesn't touch unrelated code. Add a
regression test that would have caught this bug before your fix, in the
appropriate tests/ file. Do not modify any other file.

Report back: root cause, the fix, and the exact test that now catches it.
```

### For the research stage (Perplexity / Kimi)

```
I need grounding for implementing [X] as a verified simulation domain, not
just a general explanation. Specifically:
1. The exact governing equation(s) / algorithm, in a form I can implement.
2. A closed-form solution, known-correct reference values, or an
   independent tool/library I could cross-check an implementation against.
3. Any standard numerical pitfalls specific to this domain (stability,
   convergence, common implementation bugs).
Cite sources.
```

## Working agreement

- Nothing gets called "done" until verification (Part 4 above) is run
  directly, not taken from an implementer's self-report. An implementer
  saying "tests pass" is not the same as Claude (or a human reviewer)
  having actually run them, run the dependency guard, independently
  reproduced the mutation test, and confirmed the suite is clean after
  reverting.
- If OpenCode and FreeBuff genuinely diverge on the same spec, that goes
  to Claude before either version lands — divergence on a spec this
  concrete usually means the spec was ambiguous, which is useful
  information, not just noise to break a tie on. Resolution procedure:
  `docs/CONSTITUTION.md` Section 7.
- Scope stays inside what the domain spec's "out of scope" section
  explicitly defines. Any diff touching files outside those boundaries
  is a scope violation regardless of whether the extra changes are
  individually good.
- The verification script at `scripts/verify_domain.sh` automates Steps
  1-3 of the mechanical procedure. Step 4 (mutation-test reproduction)
  is deliberately manual — run it yourself per `docs/CONSTITUTION.md`
  Section 6 Step 4 every time.
