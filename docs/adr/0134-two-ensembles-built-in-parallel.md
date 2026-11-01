# ADR 0134: Two ensembles, built in parallel

**Status:** Accepted, implemented

**Date:** 2026-08-20

**Context:** `Tests/spread_consequence.py`, `Tests/ensemble.py`,
`Tests/model_ensemble.py`, `Tests/test_ensembles_agree.py`

**Reconciles:** ADR 0111 and ADR 0129 with ADR 0131 and ADR 0132

## What happened

Two agents implemented the professors' ensemble recommendation in the same
week, neither aware of the other:

| | module | method |
|---|---|---|
| ADR 0111, 0129 | `spread_consequence.py` | enumerate the reported values, run the model at each, report every outcome beside its paper. Unweighted, deterministic |
| ADR 0131, 0132 | `ensemble.py` + `model_ensemble.py` | score each value on Bakker's axes, sample with those weights, run the model per draw, report a percentile band |

**Neither ADR mentions the other.** This is the duplication the repository
forbids everywhere else, and it arrived while both authors were being
careful — each read the professors' mail, each found the same
recommendation, each built it.

It also produced something valuable that neither could have produced alone,
and that is the reason this ADR does not delete either one.

## The other agent had a quote I did not

ADR 0129 was written from Sauro's one-line reply — *"I thought you'd decided
to build an ensemble when values are unknown?"* — and treated Bakker's
weighting as an open question, refusing to weight anything because she had
not answered how she weighted hers.

`ensemble.py` carries a fuller quote from the same correspondence:

> Barbara Bakker's approach is better. With Jessie's approach you don't get
> any simulation, with Barbara's you can sample and get an ensemble
> distribution. **That is the right way to do it.**

That is a direct endorsement of weighted sampling, and it settles the
question ADR 0129 declined to answer. My refusal to weight was correct
given what I had read and wrong given what was available to read.

## Decision: keep both, and bind them

They answer different questions, and a lab report wants both:

- **Which paper does what.** Every measured value, its outcome, and the
  reference it came from. A student defending a number to a teacher needs
  the specific row, not a percentile.
- **What the model does across the evidence.** A band, weighted by
  reliability, which is Bakker's published method and what Sauro endorsed.

What was missing was anything forcing them to agree. Two implementations of
one recommendation that can drift are worse than either alone, because a
reader sees two sections of one report making claims about the same numbers
with nothing guaranteeing they are consistent.

`sample_ensemble` resamples **discretely** from the candidate values:

```python
population = [w.candidate.value for w in weighted]
```

so every draw is one of the values `spread_consequence` runs at. That gives
an exact property:

> **The band cannot reach outside the enumerated outcomes.**

`test_ensembles_agree.py` asserts it against the real resolver, on real
cross-species rows. Widening the band by 10% fails it — verified by
mutation, so the check is load-bearing rather than decorative.

Three further properties are pinned:

- Every drawn value is a value somebody measured. A draw *between* two
  reported values would be a number nobody published, which is the
  fabrication the whole project refuses.
- Both modules are handed the same rows — asserted, not assumed, because a
  filter on one path and not the other would make every comparison
  meaningless while still passing.
- Neither presents itself as an uncertainty estimate. If one quietly began
  calling its band a confidence interval, a reader comparing two sections
  of one document would get two different claims about the same numbers.

## What this says about working in parallel

Every mechanism this repository has for preventing duplication is about
*code* — `check_scripts_reachable`, `check_guard_wiring`,
`check_both_front_ends_read_it`. None of them can see that two modules
answer the same question, because both are reachable, both are wired, and
both are tested.

The duplication was visible only in the ADR index, where two entries a few
numbers apart describe the same professor's recommendation. Nobody reads an
index while writing the thing that belongs in it.

No new guard is proposed. A guard that flagged "these two modules look
similar" would fire constantly and be suppressed. The honest control is the
one used here: when a new module implements a named recommendation, search
the ADR index for that name first — and when duplication is found anyway,
bind the two with a property rather than deleting the newer one.

## Consequences

- Both ensembles stay, with their relationship stated and asserted.
- ADR 0129's refusal to weight is superseded by the fuller Sauro quote;
  `ensemble.py`'s weighting is the answer to Bakker's axes, and
  `spread_consequence`'s enumeration is what a citation-level reader needs.
- `lab_report` currently quotes the enumeration only. Adding the band to
  the report is the next step, and it is now safe to do: the two cannot
  contradict each other without a test failing.
