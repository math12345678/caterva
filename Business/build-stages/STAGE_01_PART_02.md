# Stage 1, Part 2 — The Spec-Writing Process and the Prompts That Carry It

## 0. Why this part is prompt-heavy on purpose

Part 1 established the rules. This part answers the operational question:
what specifications are provided to implementers (OpenCode, FreeBuff) and
in what order, so that project standards are preserved when working with
implementers that lack prior project context.

The pipeline diagram and the plan matter, but they are short, because they
are simple. The prompts are what actually determines whether the next 99
stages produce code that meets this project's standard or code that looks
fine until someone runs the numbers. So this part is organized to spend
most of its length on prompt text, worked all the way through with a real
example, rather than describing the process abstractly and leaving the
prompt as an afterthought.

## 1. The plan, briefly

Every future domain or feature, before any implementation happens, goes
through a fixed sequence:

1. Claude identifies what's being built and pulls the relevant prior art
   from the codebase (closest existing analog, relevant ADRs).
2. Claude fills in the **Domain Spec Template** below — a fixed-shape
   document, not free-form prose, so that nothing required gets forgotten
   because it slipped a paragraph's mind.
3. If the spec has an unfilled research gap (the governing equations
   aren't confidently known, or the right closed-form check isn't
   obvious), Claude runs the **Research Prompt** against Perplexity or Kimi
   first, and folds the answer back into the spec before moving on.
4. The completed spec gets wrapped in the Part 1 preamble and sent to
   OpenCode and, separately, FreeBuff, as two independent implementation
   attempts against the identical spec.
5. Claude reviews both outputs against the Part 1 ten-point checklist, and
   against each other.
6. If they agree in substance, Claude picks the better-written of the two
   (or merges), runs full verification itself, and that's the artifact
   that lands. If they diverge in substance, Claude runs the **Divergence
   Resolution Prompt** (Section 6) before either version is trusted.

That's the whole plan. Everything below is what step 2 through step 6
actually look like as text you can paste.

## 2. The Domain Spec Template

This is the fixed-shape document Claude produces at step 2, every time,
for every new domain. It is deliberately a form to fill in, not a blank
page, because a blank page is where required details get skipped.

```
DOMAIN SPEC — [domain name]
Stage: [N]   Part: [N]

1. ONE-SENTENCE DEFINITION
   What is this domain, in one sentence a non-specialist could understand?

2. GOVERNING MODEL
   The actual equation(s), recurrence, or algorithm. Written out in full,
   not referenced vaguely. If this required a research pass, the answer
   goes here, with its source noted.

3. CONTINUOUS OR DISCRETE — AND WHY
   State explicitly: does this belong in the antimony -> SBML -> roadrunner
   pipeline, or as a direct Python recurrence? Justify with the actual
   physics/math of the domain, not by analogy to a previous domain.

4. PUBLIC FUNCTION SIGNATURE(S)
   Exact Python signature(s), matching the existing style in
   tellurium_engine.py (see simulate_pcr, simulate_sir for the pattern).
   Every parameter named, typed, and given its physical meaning and unit.

5. VALIDATION CONTRACT
   For each parameter: what makes it ok=False (impossible, rejected)?
   What makes it ok=True, flagged=True (implausible, allowed with a
   warning)? What's the plausible range, and what's it based on (a
   citation, a physical bound, an order-of-magnitude sanity check)?

6. VERIFICATION TARGET
   The exact closed-form solution, invariant, or independent
   solver/reference this domain's tests must check against. This is not
   optional and not deferred to the implementer to figure out — if this
   isn't confidently known before this line is filled in, stop and run the
   Research Prompt first.

7. RELEVANT ADRs
   Which existing ADRs apply, and what they mean concretely for this
   domain (e.g., "ADR 0004 applies: check every new parameter name against
   antimony's reserved word list before use").

8. SHARED-CONSTRAINT CHECK
   Does this domain's plausibility bounds, units, or naming overlap with
   any existing layer (literature layer, another domain)? If yes, what
   test will enforce that they stay in sync?

9. OUT OF SCOPE FOR THIS SPEC
   Explicitly list what this task does NOT include, so an implementer
   doesn't over-scope or under-scope the change. (e.g., "Does not include
   any frontend UI work — Tellurium/tellurium_engine.py and its tests only.")

10. DELIVERABLES CHECKLIST
    - [ ] Implementation in Tellurium/tellurium_engine.py
    - [ ] validate_[domain]_params() following the ParameterValidation contract
    - [ ] simulate_[domain]() following the SimulationResult contract
    - [ ] Tests in Tellurium/tests/test_[domain]_correctness.py, Hypothesis-based, max_examples=200
    - [ ] At least one documented mutation test
    - [ ] requirements.txt updated if any new import was added
    - [ ] Explicit report of any judgment call not covered by this spec
```

## 3. Worked example — filling the template for Monte Carlo simulation

This is the next domain on the actual roadmap (`Business/ROADMAP.md`,
Phase 2), so it's used here as the real worked example rather than an
invented placeholder, so the template above isn't left abstract.

```
DOMAIN SPEC — Monte Carlo simulation (particle-counting / stochastic
sampling domain)
Stage: 4 (projected)   Part: 1

1. ONE-SENTENCE DEFINITION
   Estimate a quantity (an integral, a probability, an expected value)
   by generating many random samples and averaging, with a reported
   confidence interval, rather than solving an equation directly.

2. GOVERNING MODEL
   For an estimator of E[f(X)] where X ~ some distribution: draw N iid
   samples x_1..x_N, compute the sample mean mu_hat = (1/N) * sum(f(x_i)),
   and the standard error se = sample_std(f(x_i)) / sqrt(N). This is the
   basic Monte Carlo estimator; the standard error's sqrt(N) convergence
   rate is itself the thing to verify against (see Section 6).

3. CONTINUOUS OR DISCRETE — AND WHY
   Discrete. There is no continuous-time process here at all — each
   sample is an independent draw, not a state evolving over time. This
   does NOT belong in the antimony/roadrunner pipeline. It's a direct
   Python implementation using numpy's random number generation, following
   the same "discrete recurrence, no solver" precedent PCR set in ADR 0002.

4. PUBLIC FUNCTION SIGNATURE(S)
   def simulate_monte_carlo(
       estimator: str,          # which built-in estimator, e.g. "pi_estimation"
       n_samples: int,          # number of samples to draw
       seed: int | None = None, # for reproducibility
   ) -> SimulationResult
   (Exact estimator set and any estimator-specific parameters to be
   finalized in review — this spec covers the general contract; a specific
   estimator, "pi_estimation" via unit-circle sampling, is used below as
   the first concrete case because it has an exactly known true answer.)

5. VALIDATION CONTRACT
   n_samples: ok=False if <= 0 or non-integer. flagged=True if < 100
   (technically runs, but the standard error will be too large to be a
   meaningful estimate — this is the "implausible but not impossible"
   case: nothing crashes, but the result carries a warning).
   seed: no validation needed, any integer or None is valid.

6. VERIFICATION TARGET
   For the pi-estimation case specifically: the true value of pi is known
   exactly. The test checks that as n_samples grows (1e3, 1e5, 1e7), the
   estimate's error shrinks at the theoretically-predicted sqrt(N) rate,
   AND that a fixed seed produces bit-identical output across repeated
   runs (reproducibility is itself a testable, exact claim, separate from
   statistical accuracy).

7. RELEVANT ADRs
   ADR 0002 applies directly: this is the second domain (after PCR) that
   is explicitly discrete and must NOT be routed through antimony. Worth
   drafting an ADR update or a new ADR explicitly stating "stochastic
   sampling domains are a third category, alongside continuous-ODE and
   discrete-recurrence" if this pattern generalizes to further domains.

8. SHARED-CONSTRAINT CHECK
   No overlap with the literature layer (BRENDA/KEGG/PubMed) — this domain
   has no literature-derived parameters. No overlap with existing
   plausibility-bounds sync test. New: this domain needs its OWN new sync
   consideration if a future domain (e.g., population genetics) also uses
   random sampling with a shared seed-handling convention — flag this for
   whoever builds that domain next to check.

9. OUT OF SCOPE FOR THIS SPEC
   Does not include a general-purpose arbitrary-distribution sampler.
   Does not include variance-reduction techniques (importance sampling,
   antithetic variates) — those are a plausible future extension, not
   part of this first implementation. Frontend UI is out of scope.

10. DELIVERABLES CHECKLIST
    [same checklist as template, domain name substituted]
```

## 4. The actual prompts — full text, ready to paste

This is the section that matters most. Three prompts follow: the
implementation prompt sent to OpenCode/FreeBuff (built by wrapping the
filled spec in the Part 1 preamble), the review prompt Claude uses
internally against the returned diff, and the research prompt for when
step 3 of the plan is needed.

### 4.1 The full implementation prompt (preamble + spec, combined, ready to send)

This is exactly what gets pasted into OpenCode, and separately into
FreeBuff — identical text to both, so any difference in what comes back is
attributable to the tool, not to a difference in what was asked.

```
You are implementing a piece of Terrium, a scientific simulation engine
for teaching labs. Before you write any code, internalize these
non-negotiable standards — they exist because each one was learned from a
real bug in this exact codebase, not as generic best practice:

1. Every numerical claim you implement must be checked, in a test, against
   an exact closed-form solution, a known-correct independent solver, or a
   physical invariant. "The output looks like a reasonable curve" is not
   verification and will be rejected in review.

2. Distinguish physically-impossible parameters (reject with ok=False,
   raise ModelBuildError, never simulate) from physically-possible-but-
   implausible parameters (ok=True, flagged=True, flag_reason set,
   simulation still runs). Use exactly these field names. Do not collapse
   this distinction in either direction.

3. Before writing any simulation logic, explicitly state whether this
   domain is continuous-time (belongs in the antimony -> SBML -> roadrunner
   pipeline) or discrete (belongs as a direct Python recurrence, no ODE
   solver). Do not default to whichever pattern the last domain used
   without checking it's actually correct for this domain's physics.

4. If this domain shares any constraint (a bound, a unit, a name) with
   another part of the system, that sync must be enforced by an executable
   test that would fail if the two drifted apart — not just a comment.

5. Every new import needs a corresponding line added to requirements.txt
   (or package.json) in the same change. Do not leave this for CI to catch.

6. After writing your tests, perform at least one mutation test:
   deliberately break your own implementation in a specific, realistic way,
   confirm the relevant test fails, then revert and confirm the suite is
   clean again. Document exactly what you broke and which test caught it.

7. Never `pip install tellurium` (the umbrella package) or suggest it.
   Use libroadrunner, antimony, and python-libsbml directly.

8. If antimony model generation is involved, check every new
   variable/parameter name against antimony's reserved words before using
   it directly — `gamma` is one known collision, there may be others.

9. If you're making a decision that a different, equally-reasonable
   engineer might have made differently (not just a variable name, but a
   real architectural choice), flag it explicitly in your final report
   rather than silently picking one.

10. Report back explicitly: what you implemented, what closed-form/
    invariant/solver you verified against, what mutation test you ran and
    what it caught, and any judgment call you made that wasn't fully
    specified in the task. A bare "tests pass" is not sufficient.

---

DOMAIN SPEC — Monte Carlo simulation (pi-estimation case)
Stage: 4   Part: 1

1. ONE-SENTENCE DEFINITION
   Estimate a quantity by generating many random samples and averaging,
   with a reported confidence interval, rather than solving an equation
   directly.

2. GOVERNING MODEL
   For E[f(X)], X ~ distribution: draw N iid samples, compute sample mean
   mu_hat = (1/N) * sum(f(x_i)), standard error se = sample_std(f(x_i)) /
   sqrt(N). Concrete first case: estimate pi by sampling points uniformly
   in [-1,1]x[-1,1] and computing 4 * (fraction landing inside the unit
   circle).

3. CONTINUOUS OR DISCRETE — AND WHY
   Discrete/stochastic. No continuous-time state to integrate. Direct
   Python + numpy implementation, NOT routed through antimony/roadrunner.
   This follows the precedent set by PCR in ADR 0002 (discrete processes
   don't get forced through the ODE pipeline) — read that ADR before
   starting.

4. PUBLIC FUNCTION SIGNATURE(S)
   def simulate_monte_carlo_pi(
       n_samples: int,
       seed: int | None = None,
   ) -> SimulationResult
   Result should expose the pi estimate, the standard error, and the
   samples-vs-convergence data needed for the verification in Section 6.

5. VALIDATION CONTRACT
   n_samples: ok=False if <= 0 or not an integer.
   flagged=True if n_samples < 100 (runs, but standard error will be too
   large for a meaningful estimate — implausible-but-not-impossible case).
   seed: no validation needed.

6. VERIFICATION TARGET
   True value of pi is known exactly (math.pi). Test must confirm: (a)
   error shrinks at the theoretical sqrt(N) rate across at least three
   sample sizes spanning several orders of magnitude, (b) a fixed seed
   produces bit-identical output across repeated calls, (c) the reported
   standard error is itself statistically consistent with observed error
   across many repeated runs at a fixed n_samples (not just eyeballed).

7. RELEVANT ADRs
   ADR 0002 applies directly — read it, this is the second explicitly
   discrete domain after PCR, do not route this through antimony.

8. SHARED-CONSTRAINT CHECK
   No overlap with the literature layer. No existing sync test applies.
   If you introduce any convention here (e.g., how seeds are handled) that
   a future stochastic domain might need to reuse, say so explicitly in
   your report — don't just implement it silently as a one-off.

9. OUT OF SCOPE FOR THIS SPEC
   No general-purpose arbitrary-distribution sampler. No variance-
   reduction techniques (importance sampling, antithetic variates) in this
   first implementation. No frontend/UI work. No changes outside
   Tellurium/tellurium_engine.py and its tests.

10. DELIVERABLES CHECKLIST
    - [ ] simulate_monte_carlo_pi() in Tellurium/tellurium_engine.py
    - [ ] validate_monte_carlo_params() following the ParameterValidation contract
    - [ ] SimulationResult-compatible return, following existing conventions
    - [ ] Tests in Tellurium/tests/test_monte_carlo_correctness.py
    - [ ] At least one documented mutation test
    - [ ] requirements.txt updated if numpy or any new import isn't already declared
    - [ ] Explicit report of any judgment call (e.g., which RNG algorithm,
          how exactly the standard-error consistency check in 6(c) was
          implemented) not fully pinned down by this spec
```

### 4.2 The internal review prompt (Claude uses this against each returned diff)

This prompt is not sent to an external tool — it's the structure Claude's
own review pass follows, made explicit here so the review isn't ad hoc
from one domain to the next.

```
Reviewing a diff against DOMAIN SPEC — Monte Carlo simulation (pi-estimation).

Check, in order, and stop at the first failure (fix before continuing to
the next check):

1. Verification target: is there an actual assertion comparing the pi
   estimate's error against a theoretically-predicted sqrt(N) rate, across
   multiple sample sizes? Is the fixed-seed reproducibility check a real
   bit-identical comparison, not an approximate one? Is the standard-error
   consistency check (6c) actually implemented, or silently dropped?

2. Validation contract: does validate_monte_carlo_params() reject
   n_samples <= 0 or non-integer with ok=False? Does it flag (not reject)
   n_samples < 100 with flagged=True and a specific flag_reason string?

3. Discrete-not-continuous: confirm no antimony/SBML/roadrunner code path
   was introduced for this domain. If it was, this is an automatic fail —
   go back to ADR 0002 with the implementer.

4. Import declarations: if numpy (or anything else) is a new import,
   confirm requirements.txt was updated in the same diff, and confirm the
   version pin doesn't have the same "no wheel for our Python version"
   problem libroadrunner had — check the pin against currently available
   wheels.

5. Mutation test: is there a specific, named mutation described (not
   vague), the specific test that caught it named, and confirmation the
   suite is clean after reverting? If this is missing, the diff is not
   done, regardless of whether the "real" tests pass.

6. Judgment calls: did the implementer flag any decision not covered by
   the spec (RNG choice, exact standard-error consistency method)? If a
   real judgment call was made silently, without being flagged, that's
   itself a process failure worth noting back to the implementer, even if
   the choice itself was reasonable — the spec-and-report loop only works
   if implementers actually use the "flag judgment calls" instruction
   rather than treating it as optional.

7. Run `make test` directly. Do not accept "I ran the tests and they
   passed" from the implementer's report as sufficient — confirm it
   yourself, in this environment, right now.

8. If OpenCode and FreeBuff were both run against this spec: diff their
   two implementations. Flag any point of substantive disagreement
   (different validation bounds, different verification approach, a
   different judgment call on the same unspecified decision) for the
   Divergence Resolution Prompt in Section 6 of this document. Cosmetic
   differences (variable naming, comment style) don't need escalation.
```

### 4.3 The research prompt (Perplexity / Kimi), fully worked for this example

Used at step 3 of the plan, only when a genuine grounding gap exists. For
the Monte Carlo domain, most of the math above is standard enough not to
need this — but here's what it would look like if, say, a future domain
extension needed variance-reduction technique grounding:

```
I need grounding for implementing a Monte Carlo variance-reduction
technique as a verified simulation feature, not a general explanation.
Specifically:

1. What is antithetic variates, in exact mathematical form I could
   implement directly — not a conceptual summary?
2. Under what conditions does it provably reduce variance versus plain
   Monte Carlo sampling, and is there a standard test case (a specific
   estimator, a specific expected variance reduction ratio) I could use to
   verify a correct implementation actually achieves the claimed
   reduction?
3. What's a common, realistic implementation mistake specific to
   antithetic variates (e.g., incorrectly pairing samples, breaking the
   negative-correlation property the technique depends on) that a test
   suite should specifically guard against?

Cite sources for the mathematical claims, not just the general technique
name — I need to verify this against a primary or textbook source before
it becomes part of an implementation spec, not take it on your word alone.
```

The reason this prompt is this specific, rather than "explain antithetic
variates to me": a vague research prompt gets a vague, textbook-summary
answer that reads well but doesn't hand back anything a spec's Section 6
(verification target) can actually use. The research prompt has to ask for
the same level of concreteness the spec itself demands — an exact,
checkable claim, not an explanation.

## 5. Pipeline diagram for this part, in words

Claude (spec) → [optional: Perplexity/Kimi research, folded back into
spec] → identical prompt sent to OpenCode and FreeBuff independently →
Claude reviews both against the 8-point internal review prompt above →
agreement → Claude runs full verification itself → merge. Disagreement →
Divergence Resolution Prompt (Part 4 of this stage) before either version
is trusted.

## 6. What Part 3 will cover

Part 3 goes deep on step 5 of this plan — the exact mechanical verification
commands (not just "run make test," but the literal mutation-testing
procedure, step by step, including how to actually simulate "deliberately
break this line, confirm the test fails, revert" as a repeatable script
rather than a one-off manual exercise) and how CI's automated guards (the
dependency scanner, the plausibility-bounds sync test) fit alongside this
manual review rather than replacing it.
