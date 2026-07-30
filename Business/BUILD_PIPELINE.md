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

**Claude (me) — orchestrator, not implementer.**
I don't write the domain code in this setup. My job is the four things an
LLM coding agent won't reliably do for itself: hold the standards across
sessions, write the spec each implementer works from, review the diff
against that spec before it's trusted, and run the actual verification
(tests, mutation testing, dependency scan) rather than taking an agent's
word that it works.

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

## The pipeline, stage by stage

### Stage 0 — I scope the task

Input: you telling me what's next (e.g., "start Monte Carlo"). Output: a
spec document, written the way `docs/API.md` and the ADRs are written —
concrete signatures, concrete test invariants, explicit "don't do X because
ADR 000Y says Y broke before." This stage doesn't touch code.

### Stage 1 — research (optional, only when grounding is missing)

If the domain needs literature/algorithm grounding I don't already have
confidently, this is where Perplexity or Kimi gets used — a scoped question
like "what's the standard closed-form or reference implementation to
validate a Monte Carlo integrator against for the birthday-problem-style
sanity checks used in scientific computing." Output folds into the Stage 0
spec, doesn't go straight to an implementer.

### Stage 2 — implementation (OpenCode and/or FreeBuff)

Give the exact same spec to whichever implementer(s) you're running.
Below are the two prompt templates to paste in.

### Stage 3 — I review the diff

Before anything gets treated as done, I check it against the spec: does
the closed-form/invariant test actually exist and actually check what it
claims to. Does it touch `tellurium_engine.py`'s shared bounds/`ok`/
`flagged` pattern correctly. Does it collide with any antimony reserved
word. Does `requirements.txt` get updated if a new import was added (this
is exactly the bug `test_dependencies_declared.py` now catches
automatically — but a human/orchestrator check catches it before CI has to).

### Stage 4 — verification (I run this, not the implementer's self-report)

```bash
make test                              # full suite, nothing skipped silently
python3 scripts/check_dependencies_declared.py   # the guard this repo already built
```

Plus the mutation-testing step for the new code specifically: deliberately
break the implementation (flip a sign, remove a bounds check, swap `<` for
`<=`), confirm the relevant test actually fails, then restore it. This is
the same method used for the PCR domain this session — it's cheap and it's
the actual reason to trust a test suite instead of just having one.

### Stage 5 — commit

I write the commit message (matches the pattern already established: what
changed, why, what was verified, what wasn't). You decide when to push.

## Prompt templates

### For a new simulation domain (OpenCode or FreeBuff)

```
You're implementing [DOMAIN NAME] for the Terrium simulation engine, in
Tellurium/tellurium_engine.py, following the exact patterns already in that
file for [closest existing domain — e.g. PCR or SIR].

Read these first and match their conventions exactly:
- Tellurium/tellurium_engine.py (existing domain implementations)
- docs/adr/0001-no-tellurium-umbrella-package.md
- docs/adr/0002-pcr-not-modeled-as-an-ode.md
- docs/adr/0003-shared-plausibility-bounds.md
- docs/adr/0004-gamma-reserved-keyword.md
- docs/API.md

Spec:
[PASTE STAGE 0 SPEC HERE — signature, params, ok/flagged bounds, whether
this is continuous (antimony/roadrunner) or discrete (direct recurrence,
see PCR for the pattern), the exact closed-form/invariant to test against]

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

When done, report: what you implemented, what you tested it against, and
any judgment call you made that wasn't explicit in the spec.
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

- Nothing gets called "done" on your side until it's passed Stage 4 here —
  an implementer saying "tests pass" isn't the same as me having actually
  run them and mutation-tested the new code.
- If OpenCode and FreeBuff genuinely diverge on the same spec, that goes to
  me before either version lands — divergence on a spec this concrete
  usually means the spec was ambiguous, which is useful information, not
  just noise to break a tie on.
- Scope stays inside what you've already decided: per `ROADMAP.md`, the
  next real domains (Monte Carlo, population genetics, molecular dynamics)
  are scoped and ready, but check with yourself first whether this is still
  the right use of time given funding/backend-hire are still open — that's
  a call this document doesn't make for you.
