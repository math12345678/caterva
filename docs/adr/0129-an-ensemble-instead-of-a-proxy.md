# ADR 0129: An ensemble instead of a proxy

**Status:** Accepted, implemented

**Date:** 2026-08-19

**Context:** `Tests/fallback_logic.py`, `Tests/spread_consequence.py`

**Relates to:** ADR 0024 (cross-species opt-in; Sauro's default declined),
ADR 0111 (the tie run through the model), ADR 0051

## The reply that dissolved the question

Herbert Sauro was asked two questions: whether default-versus-refuse should
depend on the use case, and whether the cross-species proxy is the pattern
to apply generally. He answered neither:

> I thought you'd decided to build an ensemble when values are unknown?

That is not a dodge. It says the question was wrong. Default-versus-refuse
is a choice between two bad options, and he is pointing out that a third
exists — and he is the **second** professor to point at it. Barbara Bakker's
recommendation was an ensemble too, and ADR 0024 Decision 3 declined it.

Two independent experts, from opposite directions, at the same mechanism.
That is worth more than either recommendation alone.

## What Bakker and Sauro are each talking about

They are not the same case, and conflating them is how "we built an
ensemble" would become false:

| | situation | answered by |
|---|---|---|
| **Bakker** | values EXIST and disagree | ADR 0111 — the tie, run through the model |
| **Sauro** | no value for THIS organism | this ADR |

ADR 0111 already runs the model at every value the evidence ranked equal.
Sauro's case is the one where the requested organism has nothing at all —
where Terrium currently either withholds, or (with the opt-in) substitutes
one organism's number as a proxy.

## The three existing options were all bad

- **Default 0.5.** Invents a number. The objection has never been that it is
  a bad number; it is that it is not a measurement of anything.
- **Refuse.** Gives a student nothing to look at, and ADR 0024 chose it on
  the teaching-lab argument.
- **Proxy.** Returns a rabbit's Km as the answer for a human. Jeske's
  objection, and the reason cross-species became opt-in.

Running the model at **every** organism's measured value is none of the
three. Nothing is invented; nothing is presented as the requested organism's
value; and the student sees something.

## The refusal already knew the numbers

The withheld branch computed `broad` — every cross-species row, with its
value, organism, reference and commentary — and kept only the organism
names:

```python
organisms = sorted({e.organism for e in broad if e.organism})
```

The rest was discarded at the point of refusal. The information Sauro's
ensemble needs was already in the function that refused to give it.

`cross_species_candidates` now carries those rows, shaped as
`TiedCandidate`, and `spread_consequence.consequence_of` consumes them
**unchanged**. One ensemble mechanism, two sources of candidates — a second
implementation would be a second place the reasoning could drift, and the
two cases really are the same act: *the literature reports these numbers and
Terrium will not pick between them.*

## What this does NOT become

`found` stays `False`, `value` stays `None`, and no candidate is marked
`selected`. Carrying a rabbit's number so a student can see what it does to
their model is a different act from returning it as the answer, and the
difference has to survive in the fields, not just in the prose. A test pins
each.

It is still not an uncertainty estimate. ADR 0111's disclaimer applies
unchanged: the spread is bounded by which papers are in BRENDA, not by any
statement about the true value. And Bakker's weighting question — how the
axes trade against each other — remains unanswered, so nothing here is
weighted.

## Consequences

- The answer to Sauro's question 2 is now "neither": not a proxy, not a
  refusal.
- Four mutations. Two caught (marking a candidate `selected`; dropping the
  reference that makes it checkable), two were **my errors, not the tests'**:
  `cross_species_candidates=[] or [...]` evaluates to the second operand in
  Python and changed nothing, and the no-value filter is unexercised because
  all 8 fixture rows carry values. The second is now said out loud in the
  code: a guard nobody can fail is worth keeping and not worth believing in.
- Still open, and now the only thing blocking a full answer to Sauro:
  nothing yet RENDERS this. The candidates reach `KineticResult`; the CLI
  and the API still report a plain refusal. That is the same "reaches the
  reader" gap ADR 0128 closed for the identity failures, and it is the next
  step.
