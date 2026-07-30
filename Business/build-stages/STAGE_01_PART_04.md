# Stage 1, Part 4 — Resolving Divergence Between Independent Implementers/Reviewers

## 0. This part has a live worked example already

Every previous part in this stage had to invent a worked example (Monte
Carlo, then a hypothetical antithetic-variates extension) because nothing
real had happened yet in the pipeline. This part doesn't need one — it
just happened. OpenCode and FreeBuff were both pointed at the exact same
Part 3 verification procedure, against the exact same Monte Carlo diff,
independently, in separate sessions. Both converged on the same core
conclusion (all 6 steps pass, the implementation is sound). But they did
not produce identical reports, and the difference between them is exactly
the kind of divergence this part exists to define and handle:

- Both independently reproduced a mutation test and got matching failure
  signatures (OpenCode: `rows diverge: [3.0, 2.666..., 1.088...] vs
  [3.0, 4.0, 0.0]` for the seed-ignored mutation reproduced against
  `test_same_seed_produces_bit_identical_output`; FreeBuff: same test, same
  mutation, `rows diverge: [2.0, 2.0, 1.414...] vs [2.0, 4.0, 0.0]` —
  different exact numbers because they used different sample sizes/seeds in
  their reproduction, but the same qualitative failure, for the same
  reason). This is agreement, not divergence — see Section 2.
- OpenCode additionally reproduced Mutation 2 (the missing factor of 4 in
  the standard-error formula) and, in doing so, made a real correction to
  the *original implementer's* report: the original claimed 3 tests would
  catch that mutation, OpenCode's independent run found only 2 actually
  fail (`test_error_scales_with_inverse_sqrt_n` checks the pi estimate's
  convergence, not the SE formula, so it's unaffected by that specific
  mutation and passes regardless). This is a genuinely useful finding — an
  overclaim in the original report, caught by independent reproduction
  exactly as Part 3 intends.
- FreeBuff caught something OpenCode's report never mentioned: the `&&`-
  chaining bug in the mutation-test procedure itself (fixed in Part 3 just
  now, in direct response to this). This is not a disagreement about the
  Monte Carlo implementation — it's a disagreement, in effect, about
  whether the *verification procedure* was fully sound, and it only
  surfaced because two independent runs happened instead of one.

This is the whole case for running more than one implementer/reviewer
against identical work: not because you expect them to disagree about the
main question, but because when they do disagree about something, it is
disproportionately likely to be exactly the kind of thing worth catching —
either an overclaim in a report, or a latent bug in the process itself,
neither of which a single pass reliably surfaces on its own.

## 1. Defining "divergence" precisely, so it isn't just vibes

Not every difference between two outputs against the same spec is
meaningful. The distinction that matters:

**Cosmetic divergence** — different variable names, different comment
style, different ordering of otherwise-equivalent checks, different exact
sample sizes used in an independent reproduction (as in the two mutation
reproductions above — 10,000 samples vs. some other count, doesn't matter,
because the qualitative claim being checked is identical). Cosmetic
divergence needs no escalation. Note it, move on.

**Substantive divergence** — anything where the two outputs would lead a
reasonable engineer to a different decision if only one of them had been
seen. This includes:

- Different validation bounds for the same parameter (one implementer
  flags `n_samples < 100`, another flags `< 50` — this is a real
  disagreement about what "implausible" means for this domain, not
  cosmetic).
- Different verification strategies that aren't equivalent (one checks
  the sqrt(N) convergence rate, another only checks the final estimate is
  "close to pi" with a loose tolerance — the second is a materially
  weaker verification target, not just a different way of writing the same
  check).
- A genuine factual disagreement about what a mutation test result means —
  which is exactly what happened here: the original report said 3 tests
  catch Mutation 2, OpenCode's independent reproduction found 2. That is
  substantive, because it changes what a future reader should believe
  about this domain's test coverage.
- A finding one reviewer surfaces that the other's process never had a
  chance to surface (the `&&`-chaining bug) — not a disagreement in the
  sense of contradicting each other, but a case where relying on only one
  of the two reports would have missed something real.

The practical test: if you read both outputs and one contains a claim the
other would contradict or that the other's process couldn't have caught,
that's substantive. If the two outputs are making the same claims in
different words, that's cosmetic.

## 2. What to do with cosmetic divergence

Nothing, beyond noting it happened. Do not spend review time reconciling
variable names or reordering equivalent checks between two
implementations. This is explicitly called out because the temptation,
especially early in a long build, is to over-invest in making two
independent attempts look identical — which defeats the actual value of
running two (catching real differences) in favor of manufacturing
uniformity that provides no additional information.

## 3. What to do with substantive divergence — the resolution procedure

When a real divergence is found (as with the Mutation 2 test-count
discrepancy above), the procedure is:

1. **State the discrepancy precisely**, citing both sources. Not "the
   reports disagree" — specifically: "Report A claims 3 tests fail under
   Mutation 2 (missing factor of 4 in the SE formula); Report B's
   independent reproduction of that exact mutation found only 2 fail,
   with `test_error_scales_with_inverse_sqrt_n` passing because it checks
   the pi estimate's convergence, not the SE formula."

2. **Reproduce it a third time, yourself**, rather than picking a side by
   inference. This is not optional even though two independent attempts
   already happened — the goal isn't "majority vote," it's "know what's
   actually true." In this case: apply Mutation 2 (remove the `4.0 *` from
   the SE formula), run all three candidate tests
   (`test_standard_error_matches_empirical_variation`,
   `test_z_scores_are_approximately_standard_normal`,
   `test_error_scales_with_inverse_sqrt_n`), read which actually fail and
   why, revert, confirm clean.

3. **Update the permanent record**, not just the immediate conversation.
   If the original implementer's mutation-test report overclaimed, the
   correction belongs in the test file's own mutation-test comment block
   (see `test_monte_carlo_correctness.py`'s "Mutation-test record" section
   from Part 2/3's worked example) — future readers of that file should see
   the corrected claim, not the original overclaim, and should not have to
   re-discover this discrepancy by re-running the mutation themselves.

4. **Decide whether the divergence reveals a process gap, not just a
   fact-correction**, and fix the process if so — exactly what happened
   with the `&&`-chaining finding, which resulted in an actual edit to
   Part 3's procedure rather than just a note-to-self. A substantive
   divergence that only gets corrected in the specific instance, without
   asking "could this class of thing happen again, silently, next time,"
   is a missed opportunity — the same category of reasoning as Rule 5 in
   Part 1 (undeclared dependencies got a permanent scanner, not just a
   one-time fix).

5. **Only after 1-4, decide which artifact actually lands.** In this case:
   the Monte Carlo implementation itself was never in dispute — both tools
   agreed it passes all six verification steps. What changed was the
   test file's own documentation of its mutation coverage (corrected from
   3 to 2 tests catching Mutation 2) and the verification harness
   documentation in Part 3 (patched for the `&&` bug). Neither required
   redoing the implementation — divergence resolution does not always mean
   picking between two competing versions of the *code*; often, as here,
   it means correcting the *documentation and process* that sits around
   already-correct code.

## 4. The prompt for presenting a divergence back to a tool for resolution

Use this when the divergence needs a third opinion — from Claude directly
(as happened in this actual case), or handed to whichever of
OpenCode/FreeBuff didn't originally make the claim being checked, as a
neutral second reproduction:

```
Two independent verification passes disagree on a specific, checkable
claim. I need you to resolve this by direct reproduction, not by judging
which report sounds more confident.

Claim in dispute: [state both versions precisely — e.g., "Report A: 3
tests fail under Mutation X. Report B: only 2 tests fail under the same
Mutation X, specifically test_Y is unaffected because [reason given]."]

Do this:
1. Apply the exact mutation described: [exact before/after code].
2. Run every test named in either report as potentially affected by this
   mutation: [list all tests named across both reports].
3. Report which specifically failed, with the exact failure message for
   each, and which passed despite the mutation.
4. State plainly which of the two original claims was correct, or if
   neither was fully correct, what the actual truth is.
5. Revert the mutation and confirm the full suite is clean.

Do not average the two reports or split the difference — one specific,
checkable fact is true here, and step 1-3 will show you which.
```

## 5. Why this matters going forward, at scale

This stage's example involved two tools and one small discrepancy. At
stage 40 or 70 of a 100-stage build, with more domains, more implementers,
and inevitably more fatigue about re-verifying things that "already passed
review once," the temptation will be to treat agreement between two tools
as sufficient on its own, without the third-reproduction step in Section
3.2. That temptation should be resisted for the same reason Part 1's Rule
6 (mutation testing) exists at all: a check that isn't actually run,
because it's assumed to be redundant, provides zero value while looking
identical to one that was run. Two tools agreeing is a good sign, not a
substitute for the reviewer (Claude, in this pipeline) actually confirming
the specific disputed fact directly, every time a real dispute — not a
cosmetic one — comes up.

## 6. What Part 5 will cover

Part 5 finishes Stage 1 by writing the actual `docs/CONSTITUTION.md` file
that Parts 1 through 4 have been building toward in pieces — consolidating
the nine standards, the ten-point checklist, the domain spec template, the
full implementation/review/research prompts, the six-step verification
procedure (now including the `&&`/trap fix), and the divergence-resolution
procedure, into the single canonical document every future stage's Part 1
points back to, plus the commit that lands Stage 1 itself and the exact
report format used to close out a stage before Stage 2 begins.
