# ADR 0024: Refusing versus defaulting an unsourced parameter — challenged externally

**Status:** Under review

**Date:** 2026-08-12

**Relates to:** ADR 0012 / 0013 (never default a parameter), ADR 0008
(parameter provenance), ADR 0018 (cross-species resolution)

## Context

ADR 0012/0013 established the rule the whole project is built on: a
parameter that cannot be sourced stops the run. No `km = 5.2` fallback, no
plausible-looking default. Every guard, test and error path in the codebase
assumes it.

On 2026-08-12 that rule was challenged directly, by the person best placed
to challenge it.

**Herbert Sauro** — Professor of Bioengineering at the University of
Washington, Director of the NIH Center for Reproducible Biomedical
Modeling, and author of libRoadRunner and Antimony, which this engine is
built on — was asked whether refusing to emit an unsourced constant
addresses a real gap in reproducible modelling. He replied in seven
minutes:

> If Brenda or pubmed has no value for a particular km I would just give it
> a default value, say 0.5 and write a warning comment in the antimony file
> you generate.

That is the opposite of what Terrium does, from someone whose
reproducibility credentials exceed this project's entirely.

## The disagreement, stated fairly

**The case for defaulting (Sauro).** The model runs. The warning is in the
generated file, where a modeller will see it. A modeller's workflow is
iterative — you get a model working, then refine parameters — and a tool
that refuses to produce a runnable model blocks the first step. Reproducibility
is served by the warning being *recorded*, not by the run being *prevented*.

**The case for refusing (Terrium as built).** Terrium's user is a student in
a teaching lab, not a modeller. They never open the Antimony file. They see
a number on a screen. A default of 0.5 with a comment they do not read
teaches them that parameters appear from nowhere — which is the habit the
project exists to break.

## What is probably true

These are different use cases, and the rule was written as though there
were only one.

Sauro is likely right for model development. Terrium's rule is likely right
for teaching. The error in the current design is not the rule itself but
that it is stated unconditionally, when the correct scope may be narrower.

**A second inconsistency, self-inflicted.** Terrium already does something
close to Sauro's suggestion in a neighbouring case. When no same-organism
Km exists, it does not refuse — it returns the cross-species value and warns
loudly that it was measured in another organism (ADR 0018). That is
precisely "use it, but say so."

So the project already accepts "proceed with a caveat" when the alternative
is refusal — for cross-species — and rejects it when nothing is found at
all. That may be defensible (a rabbit Km is a real measurement; 0.5 is not
a measurement of anything) but it has never been argued for explicitly, and
it should be.

## Decision

**None yet, deliberately.** This ADR records an open question rather than
settling it, because the honest state is that a serious objection has been
raised and not yet answered.

Two questions were put back to Sauro:

1. Should the line be drawn by use case — default when a model must run,
   refuse when a student is being taught?
2. Is the cross-species behaviour (use with a loud warning) the right shape
   throughout, making the refusal rule the inconsistent one?

Nothing in the codebase changes until that comes back. If the answer is
"default with a warning," it is a significant change and will get its own
ADR superseding ADR 0012/0013 rather than an edit to this one.

## A separate finding, about language

The same day, **Daniel S. Katz** (NCSA, co-founder of JOSS) was asked
whether per-value citation was novel. He replied:

> I don't really understand the idea of per constant citation. Most
> constants are well known and are not typically cited.

He is right about constants. He is describing `c`, Avogadro's number,
Planck's constant — quantities with one agreed value that nobody cites.

He is not describing what Terrium resolves. A Michaelis constant is a
**measurement**: different in humans and rabbits, different at pH 6.8 and
7.4, and two papers can report legitimately different values for the same
enzyme under different conditions.

**The misunderstanding was caused by our word.** The outreach email said
"constant," which invites exactly that reading. That is a documentation
defect of the kind this project already has a guard for in other forms: a
claim that is true-sounding and misleading.

**Action taken:** prefer "measured parameter" or "measured quantity" over
"constant" in outreach, on the website, and in user-facing copy. The
codebase already uses the right term internally — the measured-quantity
versus experimental-condition distinction is enforced in
`validateParameterProvenance`. The external language had drifted from it.

Katz also confirmed JOSS is out of scope for Terrium, on the grounds that
it is not software researchers use to do research. That is accepted and
needs no further action.

## Consequences

- ADR 0012/0013 remain in force until this resolves. No behaviour changes
  on the strength of one email.
- The cross-species inconsistency is now on the record and needs an
  argument either way.
- User-facing language stops saying "constant."
- This ADR is a live example of the project's own standard applied to
  itself: an external check found something, and the response is to record
  the challenge accurately rather than to defend the existing design.
