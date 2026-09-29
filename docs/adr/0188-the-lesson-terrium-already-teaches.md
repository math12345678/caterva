# ADR 0188: The lesson Terrium already teaches

**Status:** Research. **No decision is made here and nothing is
implemented.** The choice it informs is the owner's.

**Date:** 2026-08-28

**Context:** [ADR 0181](0181-what-seven-people-who-build-this-said.md),
[ADR 0202](0202-ask-before-you-tell.md),
[ADR 0180](0180-the-equation-the-document-never-named.md)

## The disagreement, restated

Two of the seven experts contradicted Terrium's central thesis. Ursula
Kummer (COPASI):

> there is a rather clear answer to that question: Yes, it is certainly
> better to have an estimated parameter than nothing at all.

Ron Milo declined a rule and proposed a shape:

> I would tend to allow using rough numbers, but when supplying the results
> give them a very clear different "form" using color or the like that would
> be connected to a clear statement of how they were derived.

ADR 0181 recorded both and left the decision open. It has stayed open, which
is a reason to bring evidence to it rather than restate it again.

## Kummer's strongest argument is not about convenience

Of her three reasons, two are about coverage — you will not find a
reasonably sized system with every parameter known; in-vitro Km values "are
not the real values anyway". The third is different:

> Some parameters values are not really important for the systems at all. It
> is important to find out which (these parameters carry no control over the
> system) […] Without having initial values you can't do that at all.

That is not "an estimate is better than nothing". It is: **refusing to run
withholds the finding that the parameter did not matter.** A student who
cannot source a Km learns nothing — not even that their answer would have
been the same whatever the Km was.

## The teaching literature points at the same activity

Parameter *identifiability* and *sensitivity* — which parameters can be
determined, and which the answer is actually sensitive to — are a live
teaching subject in computational biology. The recent literature treats the
mechanism as interactive: change a value or a measurement scheme, watch the
verdict move.

**Stated as a limit:** a search summary attributed to this literature a
specific claim that such notebooks are "particularly effective in graduate
courses". I could not extract that sentence from the primary source
(Alsammani, *A Tutorial on Symbolic Structural Identifiability Analysis of
ODE Models in Julia*, arXiv:2605.18910 — title and author verified, the
passage not), so it is not quoted here and should not be relied on. What is
verified is that identifiability and sensitivity are the subject and that
interactive artefacts are how the field teaches them.

## Terrium already does this, and gates it behind a citation

This is the part that changes the shape of the question.

The lesson layer (ADR 0202) takes the disagreement Terrium found in the
literature, runs the model at each value, and asks the student to predict
the result before showing it:

> The evidence ranked 2 values of km equal: 0.03 to 0.398 […] the substrate
> remaining at t=10 ranges from 7.509 to 7.609. **A factor of 1.01.**

A thirteen-fold disagreement in the input producing a one per cent
difference in the answer **is a sensitivity finding.** It is precisely
Kummer's point — this parameter carries little control over this system —
delivered as a lesson, with the mechanism explained from the run's own rate
law (ADR 0180).

So Terrium does not lack the ability to teach what Kummer says refusal
prevents. It has it, and reaches it **only when the literature supplied two
or more values.** For an unsourced Km, the student gets a refusal and learns
nothing about whether it mattered.

## A shape that might satisfy both

Terrium refuses to *report a value* it cannot source. It does not follow
that it must refuse to *run the model*.

A sweep over a range, reporting only the spread of outcomes and never a
value — *"across any Km between 0.01 and 10, the substrate at t=10 moves by
1%"* or *"…moves by a factor of 40"* — teaches the thing Kummer wants taught
and asserts no number Terrium could not source. The refusal stays intact;
the lesson arrives anyway. It is also Milo's "very clear different form",
arrived at from the other direction: not a number in a different colour, but
an answer that is structurally not a number.

**The obvious risk, and it is not small.** A student may read a sweep as an
endorsement of the range, and a range Terrium chose is still a number
Terrium chose — the bounds would need the same provenance discipline as
everything else, or the refusal has been reintroduced one level up. Whether
that is a real escape or a relabelling of the problem is exactly the
judgement this record is not making.

## Not decided, and not implemented

Nothing in this commit changes what Terrium refuses. This is the evidence
for a decision, laid out so it can be made on something other than my
summary of two emails.

**What this does not establish.**

- **No pedagogy paper was found that addresses sourced versus assumed
  parameters directly.** The search returned identifiability and estimation
  methods; the connection to Terrium's question is mine, and it is an
  argument rather than a citation.
- **Nobody has taught with Terrium.** ADR 0202's first named gap is
  unchanged: no human has taken the lesson it already has, so "Terrium
  teaches this well" is a claim about a design, not an observation.
- **The sweep is a sketch.** Nothing here checks that a spread over a range
  is intelligible to a student, or that the bounds can be chosen without
  inventing them.