# ADR 0131: The ensemble both professors asked for

**Status:** Accepted, implemented (core). CLI/API rendering outstanding — see
Consequences.

**Date:** 2026-08-20

**Context:** `Tests/ensemble.py`, `Tests/test_ensemble.py`

**Supersedes in part:** [ADR 0024](0024-refusing-versus-defaulting-an-unsourced-parameter.md)
Decision 3, which recorded Bakker's sampling as *declined*.

## What was actually asked for

Read from the correspondence rather than from this repository's summary of
it, which had drifted.

**Prof. Barbara Bakker** (UMC Groningen), 13 August 2026, answering whether
"flag it, don't use it" is right for a value missing its assay conditions:

> "In practice, we chose the best option, but **do not exclude anything a
> priori**. We are preparing a publication in which we generated an ensemble
> of models by sampling from a distribution of possible parameters. We gave
> each parameter a score based on its reliability and applicability, such as
> physiological pH and T, species […] and completeness of assay description.
> **These scores were then used to give the parameter a weight in the
> sampling.**"

**Prof. Herbert Sauro** (UW, Director of the NIH Center for Model
Reproducibility), the same day, having been told about both options:

> "Barbara Bakker's approach is better. With Jessie's approach you don't get
> any simulation, with Barbara's you can sample and get an ensemble
> distribution. **That is the right way to do it.**"

The reply agreed to build it. On **19 August** Sauro followed up:

> "I thought you'd decided to build an ensemble when values are unknown?"

`docs/EXPERT_FEEDBACK.md` recorded the item as *"half adopted — scoring
shipped, sampling declined."* Two independent experts converged on one
answer, it was agreed to in writing, and the codebase declined it.

## Why the scoring shipped and the sampling did not

Not laziness — a structural reason worth stating, because it explains why
this was one function away rather than a rewrite.

`science_agent_runner.py` scores exactly **one** value: the winner. That is
all a single-value answer needs. There was never a per-candidate score to
weight anything with, so the sampling had nothing to consume.

The rows on the non-dominated frontier already carry everything
`score_reliability` wants — `assay_ph`, `assay_temperature_c`,
`assay_unreported`, `organism`. `ensemble_from_entries` scores each of them
with **the same function** the winner is graded by, which is ADR 0027's rule:
one implementation, not two.

## What it does, on real data

```
$ python3 ensemble.py --fixture fixtures/brenda_ldh_fixture.html \
      --substrate pyruvate --seed 1 --draws 2000

  The literature does not agree on this Km.

  2 published measurement(s), sampled 2000 times with each
  weighted by how well evidenced it is:

          0.03 mM   drawn  50.0% of the time  [ref 286469]
                   absent / not_assessed / exact
         0.398 mM   drawn  50.0% of the time  [ref 286442]
                   absent / not_assessed / exact

  Spread: 0.03 to 0.398, a 13.3-fold range   (median 0.398)
```

Caterva's answer today is **0.03** — `min()` over the frontier. The ensemble's
answer is *the literature contains 0.03 and 0.398, equally well evidenced,
thirteen-fold apart*. Both rows score identically here, so the weights are
equal; that is the axes correctly reporting that they cannot discriminate,
not a failure to weight.

## The three design decisions, and what defends each

### Multiplicative weights, and the numbers are a policy

`reliability.py` deliberately refuses to combine its axes into a total,
because the trade-off is an empirical question nobody has answered. Sampling
needs a scalar; there is no way around that.

So the factors are **chosen, not measured**, and say so. What *can* be
defended is the ordering within each axis, which is the ordering
`evidence_rank.py` already uses for Pareto dominance. The table is exported
as `DEFAULT_WEIGHT_POLICY`, overridable per call, and echoed back in the
result — and every weight carries its `(axis, grade, factor)` breakdown, so
a reader can audit the arithmetic that produced their ensemble.

Multiplicative rather than additive: defects compound. Addition lets a row
launder one fatal weakness behind two strengths.

`not_assessed` ranks **above** `far` on purpose. "We could not check" is a
weaker signal than "we checked and it is wrong", and ranking a row beneath a
known-distant one because the *caller* supplied no reference would punish the
measurement for the user's omission.

An axis on which every candidate scores the same cannot discriminate, and
does not — identical factors cancel under normalisation. Pinned by a test,
because the common case (nobody supplies a physiological reference, so every
row is `not_assessed`) would otherwise quietly reweight every ensemble.

### Resampling observed values, not fitting a distribution

Bakker samples "from a distribution of possible parameters". With two to six
published measurements, fitting a parametric form would invent shape the data
does not contain — a lognormal through three points is mostly an assumption.

So this draws with replacement from the observed values. The consequence is
stated rather than hidden: **the ensemble can never produce a value nobody
measured**, and percentiles are nearest-rank rather than interpolated for the
same reason. A histogram with three bars is the honest shape of three
measurements.

### It is not an uncertainty estimate, and says so in the output

ADR 0024's objection was correct and is not waved away:

> a teaching lab has no flux data to reject against, and spread without a
> validation step looks like a rigorous uncertainty estimate while being
> nothing of the kind.

Bakker's published ensemble **rejects** models against measured flux.
Caterva has no such data. So the answer is not to hide the spread; it is to
make the sentence inseparable from it. `EnsembleResult.disclaimer` travels
with the numbers, `_format_report` prints it, and a test asserts it is there.

## Verification

17 tests. The load-bearing ones are about the weights actually steering the
sampling — without that this is an unweighted bootstrap wearing Bakker's
name, which would be worse than not building it:

| | |
|---|---|
| better-evidenced value drawn more often | >95% share at 1.0 vs 0.011 |
| **the ratio matches the declared policy** | 0.30–0.37 for an expected 1:2 |
| the weakest evidence is still sampled | Bakker: "do not exclude anything a priori" |
| an all-equal axis does not tilt anything | probabilities identical with/without a reference |
| same seed, same ensemble | reproducible or it is not evidence |
| unknown grade raises | a silent 1.0 would reweight every ensemble unnoticed |
| all-zero policy refuses | no uniform fallback at the moment somebody should look |
| never invents a value nobody measured | draws ⊆ observed |
| percentiles are always observed values | nearest-rank, not interpolated |

The second row is the one that matters most: a sampler that always returned
the best candidate would pass the first test and be wrong — it would have
excluded the weaker evidence entirely, which is precisely what Bakker said
not to do.

## Consequences

- `seed` is a **required** argument, not defaulted. An ensemble nobody can
  re-derive is not evidence.
- Runnable today, offline, against a saved BRENDA table:
  `python3 Tests/ensemble.py --fixture … --substrate … --seed …`
- **Not yet rendered by the CLI or the API.** That is the remaining work and
  it is named rather than implied: this module is presently reachable only by
  running it directly, which is the "capability nobody can find" shape
  ([ADR 0122](0122-fifteen-domains-nobody-could-find.md)). It should reach
  both front ends together — `docs/one-sided-findings.txt` exists because
  they drift.
- ADR 0024 Decision 3's *"sampling declined"* is superseded. Its **reason**
  is not: it survives as the disclaimer.

## Related

- [ADR 0024](0024-refusing-versus-defaulting-an-unsourced-parameter.md) —
  refusing versus defaulting; the decision this reverses, and the objection
  it keeps
- [ADR 0027](0027-one-reliability-score-not-two.md) — one implementation of
  the score, which is why candidates are graded by the same function
- [ADR 0047](0047-selection-by-evidence-not-by-magnitude.md) — the
  non-dominated frontier this samples over
