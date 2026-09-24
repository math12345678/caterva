# ADR 0175: A threshold finer than the method is a distinction that cannot be real

**Status:** Accepted

**Date:** 2026-09-08

**Relates to:** ADR 0173 (the compositional builder this ranks the gaps of),
ADR 0170 (models are values — why a perturbed network is a new value), ADR
0028 (a check that fires too broadly stops being read — the same failure
mode, approached from the other side), ADR 0048 (selection ties).

## Context

`Terium/compose/` builds a three-tier phosphorylation cascade from a
description and reports that twelve rate constants are unmeasured. "Go and
measure twelve things" is not advice. `compose/sensitivity.py` was written to
turn that list into a ranking: the relative sensitivity

    S = (dy/dp) * (p/y)

by central differences, so that the report can say which constants the answer
actually rests on.

It shipped with three constants chosen by rule of thumb:

```python
RELATIVE_STEP = 1e-6   # "sqrt of machine epsilon"
NEGLIGIBLE    = 1e-6   # below this, report as negligible
DOMINANT      = 1.0    # at or above this, call it dominant
```

Every one of them was wrong, and each was wrong in a different way that the
others hid.

### The step assumed an accuracy the quantities do not have

Measured on `dX/dt = ks - kd*X`, where both answers are known in closed form:

| quantity | exact value | worst relative error |
|---|---|---|
| steady state | `ks/kd` | 1.8e-16 |
| settling time | `1/kd` | **1.0e-08** |

The steady state is a root solved to a 1e-14 residual on a rate law that
evaluates in floating point, so it lands at machine precision. The settling
time is `1 / |smallest eigenvalue real part|` of a **finite-difference**
Jacobian, and inherits that approximation's error — eight orders of magnitude
worse.

Differentiating the settling time with a step of 1e-6 divided a 1e-8 error by
a 1e-6 step. It reported **S = 0.004 for `ks`**, a parameter the settling time
does not depend on at all: `1/kd` contains no `ks`. Three orders of magnitude
above the "negligible" cutoff, so it would have been printed, ranked, and read
as a real dependency.

The rule of thumb was also misremembered. `sqrt(eps)` is the forward-difference
step. For a central difference the error is

    (h^2 / 6) * |f'''| + eps_f * |f| / h

which is smallest near `h = cbrt(eps_f)`, and leaves a smallest trustworthy
sensitivity of about `eps_f ** (2/3)`.

### The dominance threshold was decided by rounding

`|S| = 1` is the commonest exact answer in the subject — every first-order rate
constant has it. On the turnover model:

    x_ks:  +0.9999999999621   ->  not dominant
    x_kd:  -1.0000000000510   ->  dominant

Same model, same true answer, opposite classification, decided by a few parts
in 1e11. A comparison at a threshold the arithmetic cannot resolve is a coin
flip wearing a decision's clothes.

### The refusal was disarmed by a search set below its own measured default

`steady_state_of` refuses when more than one stable state is found, because a
derivative through a choice between attractors describes the choice. It passed
`starts_per_species=4` to be quick — below `analysis.py`'s own measured default
of 8. Measured, stable states found by search depth:

| model | 4 | 8 | 16 |
|---|---|---|---|
| toggle switch | **1** | 2 | 2 |
| two-enzyme competition | 1 | **1** | 2 |

At 4 the toggle switch reports one stable state when it has two, so the
refusal never fired and a derivative was taken straight through a bistable
system without a word. The second row is worse: at the *measured default* a
real five-species model still reports one state when it has two.

### And one threshold was answering two questions

Fixing the floor exposed a conflation. With the noise floor put where the
arithmetic actually is — 4e-10 rather than 1e-6 — the saturated cascade's
eight upstream constants stopped reading as "no measurable influence" and
turned out to sit at about **1e-8**: two orders of magnitude clear of the
noise, entirely real, and still not worth a week at the bench.

## Decision

**1. The step and the noise floor are derived from the quantity's declared
accuracy, not from `float`'s.**

```python
def step_for(precision):       return precision ** (1/3)
def resolution_for(precision): return SAFETY * precision ** (2/3)
```

A `Quantity` declares its own `precision`. `steady_state_of` declares
`MACHINE_PRECISION`; `settling_time` declares `SOLVER_PRECISION = 1e-8`,
measured against the analytic `1/kd` and rounded up because the measurement is
one model's. A plain callable is taken to be exact — it is the caller's own
function, `precision=` overrides it, and assuming the worst case for everything
would call real sensitivities noise.

`SensitivityReport.resolution` carries the floor that actually applied and the
summary prints it. A floor means nothing without saying a floor on what.

**2. Comparisons against `DOMINANT` carry the resolution as slack** — the same
number, not a second epsilon. A separate one would be a second opinion about
the same arithmetic, free to drift from the first (ADR 0027's shape).

**3. Two thresholds, because there are two questions.**

| | test | meaning |
|---|---|---|
| `unresolvable` | `\|S\| < resolution` | the arithmetic cannot tell this from its own rounding |
| `negligible` | `\|S\| < NEGLIGIBLE_INFLUENCE` (0.01) | real, measured, and too small to act on |

The first is about floating point and moves with the quantity. The second is a
judgement about biochemistry and does not: enzyme constants are rarely known
better than ±20%, so at `|S| = 0.01` a constant wrong by half moves the answer
by half a percent, under anything an assay would resolve.

Reporting a real 1e-8 as "no measurable influence" overstates what was found.
Reporting it without saying it is too small to chase understates what the
reader should do. The summary says both, separately.

**4. The refusal never searches below the analysis module's measured default.**
`STARTS_PER_SPECIES = 16`, a measured floor for the models in the library and
not a proof for anything outside it. The module states the competition
counterexample where the refusal is made, because no number of starting points
turns "did not find another" into "there is not another".

**5. Perturbed evaluations continue from the base state rather than
re-searching.** `analysis.analyse` gained `extra_starts`; with
`starts_per_species=0` they are the only starts. This is a correctness matter
before it is a speed one: a global multistart makes no promise to return the
same branch twice, so the quotient of two globally-searched steady states over
a tiny step is not a derivative of anything. Anchoring makes both halves of a
central difference provably about one branch.

It is also what makes the feature affordable. Ranking twelve constants costs
twenty-five evaluations; unanchored at 16 starts per species on a six-species
cascade, that ran thousands of global solves and did not finish.

A failed continuation **refuses** rather than falling back to a global search.
A fallback would re-enable the exact failure this exists to prevent, at the
moment it is most likely — a continuation failing is itself evidence the branch
is doing something interesting.

## Consequences

The ranking is now reachable: `compose/report.py` orders the table of
unmeasured constants by influence and prints S in a column, and
`--rank-against` / `--no-ranking` expose it at the terminal. A capability
nobody can reach is not a capability (ADR 0090), and this one was in a module
nothing called.

The cascade's real answer is visible for the first time:

```
tier3_kcat_kin      S = +9.1e-05
tier3_kcat_pptase   S = -9.1e-05
...
tier2_Km_pptase     S = +1.5e-09
```

Four orders of magnitude, tier 3 dominating everything upstream, and the
kinase/phosphatase pairs **exactly opposed** — the cycle's steady state depends
on their ratio, so `S(kin) = -S(pptase)` for every tier at every value. That is
now a test, and it is the kind of check the previous thresholds could not have
supported: at a 1e-6 cutoff, eleven of those twelve numbers did not exist.

The honest consequence is less flattering. **No constant in that table clears
the act-on threshold**, so the report says measuring any one of them would not
move the answer — and says that the saturation is itself an artefact of the
placeholder values, which is a reason to ground the model rather than a licence
to leave it ungrounded. The earlier version's caption, "measuring the top of
this list buys more than measuring the bottom", was advice about a list where
the top was not worth measuring either.

### The two-threshold split turned out to be a diagnostic

Not planned, and worth recording because it is the strongest argument for
having made the distinction at all.

Ranking every composable model in the library surfaced four whose sensitivities
are **exactly zero for every constant** — substrate inhibition, competitive
inhibition, sequential feedback, allosteric activation. The saturation caption
fitted the shape of that result and was the wrong reason for it. These are
CLOSED systems: substrate inhibition conserves `S + P`, and started at S = 1,
P = 0 it ends at P = 1 whatever kcat and Km are. The rate constants set how
fast it arrives, never where.

Saturation and conservation produce the same empty priority list and demand
opposite advice. Under saturation nothing is worth measuring anywhere; under
conservation the question was asked of the wrong quantity and a time course
answers it. They are told apart by `unresolvable` versus `negligible`:

    cascade (saturated)        |S| = 9e-5 down to 1e-9   real, four orders
                                                          above the floor
    substrate inhibition       |S| = 0 exactly            below any floor

`conservation_pinning` requires BOTH signals — every sensitivity unresolvable
AND the species named in a conservation law — because either alone is wrong.
All-zero could be a quantity the solver cannot move; a law containing the
species is true of every closed system, the cascade's own tiers included. The
cascade is the case that proves the conjunction is needed: `tier3_Xp` IS
conserved, and a test for the law alone would have rerouted it to the wrong
caption.

Found in the same sweep: `_default_target` returned `None` for a binding
motif, which declares partners and a COMPLEX but no product, so "reversible
binding of a ligand to a receptor" got no ranking at all — silence rather than
a refusal with a reason. Products are now tried across every instance first,
complexes second. It ranks `complex_AB` at |S| = 0.16 and points at `kon` and
`koff`, with the signs the chemistry requires.

### Two more things the sweep found

**Advice that pointed at nothing.** The pinned caption said "ask for the
settling time instead" — one function call away, and it did not make the call.
Advice a tool could have taken itself is a gap wearing a recommendation's
clothes. `dossier` now falls back to ranking the settling time when the steady
state is pinned, and the answers are sharp: settling scales as Km/kcat, so
substrate inhibition ranks `kcat` at exactly −1 and `Km` at +1, and the
three-step pathway splits the burden evenly at −0.5 per tier. The report
carries the conservation law forward so the table says WHY it switched — `kcat`
at −1 with no explanation is a claim about where the system lands, and it means
how fast it arrives.

**A caption for a measurement nobody took.** The allosteric-activation model's
activator starts at zero and is conserved, so it stays zero, synthesis is off,
and the answer is zero — which makes every relative sensitivity *undefined*
rather than small. All four parameters are skipped and `sensitivities` is
empty, and the empty list fell through to the saturation branch: "no constant
influences this answer". That is a finding reported from a run that found
nothing, which is the worst of the three misreadings in this record. It now
says nothing was measured, gives the skip reasons, and points at the starting
amount that left the mechanism switched off.

### The method that found most of this

Four of the defects in this record were found the same way, and none of them by
working on the module in isolation: **running the whole dossier across every
buildable model in the library** rather than the one under development. That
sweep produced the conservation pinning, the empty-ranking caption, the missing
binding target, and the double-wrapped refusal below. Nine of eleven models
produced correct documents; the interesting information was entirely in the
other two and in the four whose numbers were right for a reason the prose got
wrong.

**A refusal that explains itself was being re-explained.** Three of the eleven
reach a refusal, and each note read

    no influence ranking: the quantity could not be computed at the base
    point, so there is nothing to differentiate: <the actual, precise reason>

with the open system's saying "differentiate" twice in one sentence. `analyse`
now re-raises `SensitivityUnavailable` unchanged and wraps only exceptions that
carry no reason of their own — a `KeyError` out of a caller's callable does need
saying where it happened; "2 stable states at these values, so a steady-state
derivative is undefined" does not.

### What this does not fix

The multistability refusal remains a search result. The competition
counterexample is in the module docstring and in a test, so the limit is stated
where the claim is made, but it is a limit and not a bound.

`SOLVER_PRECISION` is one model's measurement. A quantity whose Jacobian is
worse conditioned than a two-species linear system's will carry more error than
1e-8, and nothing here detects that — it is a declared number, and it is
declared conservatively, but it is not verified per model.

### Mutation table

`docs/mutations/adr-0175-a-threshold-finer-than-the-method.json`, under
`scripts/mutate.py`. **21 caught, 0 not caught, 0 indeterminate**, against a
green 91-test baseline. Each mutation restores one of the original defects
exactly, because every one of them was a constant that read plausibly and the
wrong version does not look wrong.

Two things the harness taught while grading, both worth more than the score:

**The set was refused outright on the first attempt.** The test command ended
in `-q`, which under this repo's pytest configuration suppresses the final
`N passed` line entirely — and `mutate.py` reads that line to establish the
suite actually RAN. Rather than grade twelve mutations against a count it could
not see, it reported "the baseline suite did not execute any tests" and changed
nothing. That is the harness's whole purpose working: `0 total` is not
`0 failed`, and a suite that cannot be counted has judged nothing.

**M6 was replaced, and its first NOT CAUGHT verdict was correct.** That version
kept `extra_starts=[anchor]` and merely re-enabled the global search alongside
it — which cannot change the answer, because `extra_starts` are prepended and
`_continue_from` returns `fixed_points[0]`, so the anchor's root converges first
and wins by position. An inert mutation reads exactly like an untested claim
(ADR 0167, F2). The replacement removes the anchor, which is the real defect,
and is caught. The implementation now records that the anchor wins by position
rather than by luck, because that was not obvious until a mutation proved it.

Grading the replacement took about twenty minutes against ninety seconds for
every other mutation, and that slowdown is not an inconvenience: it is the
performance half of this decision, reproduced on demand.

### Generalisation

The rule this ADR is named for applies past this module. Any threshold in this
repository that classifies a computed number needs to be coarser than the
computation's own error, or it classifies noise. The three defects above were
one defect: constants chosen for how they read rather than derived from the
method that produces the numbers they judge.
