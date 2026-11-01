# ADR 0024: Refusing versus defaulting an unsourced parameter

**Status:** Partially decided — cross-species resolved and built (Decisions
1 and 3); the missing-entirely case (Decision 2) is still open

**Date:** 2026-08-12, revised 2026-08-13

**Relates to:** ADR 0012 / 0013 (never default a parameter), ADR 0008
(parameter provenance), ADR 0010 (STRENDA assay conditions), ADR 0018
(cross-species resolution — **narrowed by this ADR**), ADR 0021 (STRENDA scope)

**External input:** Herbert Sauro (UW), Lisa Jeske (BRENDA/DSMZ), Barbara
Bakker (UMC Groningen), Daniel S. Katz (NCSA). See
[`docs/EXPERT_FEEDBACK.md`](../EXPERT_FEEDBACK.md) for the full record.

## Context

ADR 0012/0013 established the rule the whole project is built on: a
parameter that cannot be sourced stops the run. No `km = 5.2` fallback, no
plausible-looking default. Every guard, test and error path in the codebase
assumes it.

On 2026-08-12 and 2026-08-13 that rule was put to four people who work on
the problem professionally. Three of them answered on the substance, and
**they do not agree with each other.** This ADR exists to record the
disagreement accurately, because the temptation to quote whichever expert
agrees with the existing design is exactly the failure this project claims
to guard against.

## The four positions

### 1. Sauro — default it, and warn

> If Brenda or pubmed has no value for a particular km I would just give it
> a default value, say 0.5 and write a warning comment in the antimony file
> you generate.

Professor of Bioengineering at the University of Washington, Director of
the NIH Center for Reproducible Biomedical Modeling, and an author of
libRoadRunner and Antimony — which this engine runs on. Replied in seven
minutes.

**The case, stated at its strongest.** The model runs. The warning is *in
the artifact*, where it travels with the model rather than living in a
console someone scrolled past. A modeller's workflow is iterative: get
something running, then refine. A tool that refuses to produce a runnable
model blocks step one, and the researcher works around it by hardcoding a
number with no warning at all — a strictly worse outcome caused by the
strict rule. Reproducibility is served by the assumption being *recorded*,
not by the run being *prevented*.

### 2. Jeske — abort, and make cross-species an explicit opt-in

> Enzyme kinetics are species-specific: An enzyme from a thermophilic
> bacterium (which lives at high temperatures) has completely different km
> or kcat values than the same enzyme in a mammal. Transferring a value
> from one species to another is not recommended from a biochemical
> standpoint. […] The simulation should rather abort or leave the value
> empty if there is no exact organism match, instead of providing incorrect
> data. […] the student/teacher must actively check a box ("Allow
> cross-species data"), accompanied by a clear educational warning that
> this is an inaccurate model. […] The software should at least check
> whether the organisms are closely related enough (e.g., two different
> mammals instead of a bacterium and a human).

A curator on the BRENDA team at the Leibniz Institute DSMZ — the source
Caterva reads from, answering about her own data.

**The case, stated at its strongest.** She adds a second argument beyond
species: BRENDA aggregates thousands of papers with different pH,
temperature, cofactors and buffers, so mixing rows produces what she calls
"fantasy numbers" — a model whose parameters were never jointly measured
under any single condition. The warning-on-the-value approach fails because
warnings are read by people looking for a reason to doubt; a checkbox
placed *before* the value exists is the only point at which the user is
actually making a decision.

### 3. Bakker — score it, sample it, reject at the model level

> In practice, we chose the best option, but do not exclude anything a
> priori. We are preparing a publication in which we generated an ensemble
> of models by sampling from a distribution of possible parameters. We gave
> each parameter a score based on its reliability and applicability, such as
> physiological pH and T, species (in our case human was prioritized as we
> built a human-like model) and completeness of assay description. These
> scores were then used to give the parameter a weight in the sampling.

Professor at the University Medical Center Groningen, whose group produces
the kinetic measurements this tool consumes. Reference: Odendaal, Krebs &
Bakker, *Ensemble kinetic modelling links residual enzyme activity to
clinical symptoms in mitochondrial β-oxidation defects*, bioRxiv,
doi:10.64898/2026.05.05.722902 (under revision for PLoS Computational
Biology).

**The case, stated at its strongest.** The binary question is malformed. A
parameter with a poor assay description is not evidence of *nothing* — it is
weak evidence, and weak evidence still constrains a distribution.
Discarding it is a loss of information dressed up as caution. Rejection
belongs at the level of the whole model, after validating against measured
fluxes, because a parameter is only wrong relative to the other parameters
it sits beside.

### 4. Katz — the question is about the word "constant"

> I don't really understand the idea of per constant citation. Most
> constants are well known and are not typically cited.

Chief Scientist at NCSA and a co-founder of JOSS.

He is right about *constants*: `c`, Avogadro's number, Planck's constant —
quantities with one agreed value that nobody cites. He is not describing
what Caterva resolves. A Michaelis constant is a **measurement**: different
in humans and rabbits, different at pH 6.8 and 7.4, and two papers can
report legitimately different values for the same enzyme under different
conditions.

**The misunderstanding was caused by our word.** The outreach email said
"constant," which invites exactly that reading. See "Language" below.

Katz also confirmed JOSS is out of scope, on the grounds that Caterva is
not software researchers use to do research. Accepted; no action.

## Why they disagree

They are answering different questions, and the original rule was written
as though there were only one.

| | User | Cost of a wrong number | Cost of no number |
|---|---|---|---|
| Sauro | modeller iterating | low — they will tune it | high — pipeline dies |
| Jeske | student reading a screen | high — believed as fact | low — they ask why |
| Bakker | researcher publishing | high — but bounded by ensemble spread | high — information discarded |

Caterva's stated user is a student in a teaching lab. On that population
Jeske's column is the one that applies, and it is not close.

## Decision 1 — cross-species is now opt-in (DECIDED, IMPLEMENTED)

**Adopted: Jeske.** ADR 0018 is narrowed. `resolve_kinetic_value` takes
`allow_cross_species`, defaulting to **False**. With the default, a
cross-species hit returns `found=False` with
`source="cross_species_withheld"`.

This also resolves a self-inflicted inconsistency that predates all of this
correspondence. Caterva refused when nothing was found, but silently
substituted another organism's value when something was — accepting
"proceed with a caveat" in one branch and rejecting it in the neighbouring
one, for no argued reason. The project was already doing a weak version of
Sauro's suggestion while claiming Jeske's standard.

**The refusal names what it refused.** `cross_species_withheld` carries
`cross_species_organisms_available`, and the error message names the
organisms and how to opt in. A refusal that cannot say what it refused
leaves the user unable to exercise the very opt-in it demands — the
checkbox Jeske describes is meaningless if nobody is told there is anything
behind it.

**And it stops making a false claim.** `RequiredParametersMissingError`
previously said "could not be resolved from literature" for every
unresolved key. For a withheld cross-species value that sentence is *false*:
the value was resolved from the literature and withheld by policy. A
message that is wrong in a way that sounds authoritative is the failure
mode this project spends most of its effort on, so the error now assembles
per-key reasons from `ParameterProvenance.unresolvedReason` — a
machine-readable field, not a pattern-match on prose.

Concretely, in the golden set: a mouse Km query previously returned a
*Sus scrofa* value, and a mouse gossypol Ki query returned a *Plasmodium
falciparum* value. The second is Jeske's own example made real — an
apicomplexan parasite standing in for a mammal — and nothing in the old
code could tell it apart from a second mammal.

**Verification.** `Tests/test_fallback_logic.py` (5 new tests) and
`Tests/test_golden_set.py` (2 new). Three mutations were introduced and each
was caught: disabling the gate (4 failures), returning no organism names
(1), and collapsing `cross_species_withheld` into `not_found` (2).
TypeScript: `src/__tests__/crossSpeciesWithheld.test.ts`, 8 tests asserting
on the thrown error, which is the only surface a user actually sees.

### The relatedness check — BUILT (2026-08-13)

Jeske's third recommendation is implemented in `Tests/taxonomy.py`. Opting
in permits a value from a *related* organism, not from any organism.

**The threshold is hers, not ours.** `MINIMUM_SHARED_RANK = "class"`. Her
example — "two different mammals instead of a bacterium and a human" — names
Mammalia, which is a class. Any stricter and two mammals fail, which she
explicitly permits; any looser and a human/*Plasmodium* transfer passes,
which she explicitly forbids. The threshold is that sentence translated into
code, which is the only place it can defensibly come from.

**Ranked ancestors, not node counts.** Counting shared lineage nodes looks
more precise and is not: NCBI's tree is far denser in some clades than
others — the human lineage passes through thirty nodes, the *Thermus
thermophilus* lineage through eight — so "shares 20 nodes" measures how
well-studied a clade is at least as much as it measures relatedness. Named
ranks are stable across clades because they are defined independently of how
finely anyone subdivided a branch.

**Three states, not a boolean.** `close_enough` / `too_distant` /
`unknown`. A failed lineage lookup must not read as permission. With a
boolean, the natural implementation of "we could not check" is
False-meaning-not-close — right by accident, and inverted the moment someone
writes `if (!tooDistant)`, silently re-enabling unrestricted substitution
during an NCBI outage.

**Matching is on taxon id, never on name.** The mouse lineage alone contains
"Mus" twice (genus 10088, subgenus 862507), and scientific names are reused
across kingdoms outright. Name matching manufactures relatedness, and it
errs toward *permitting* a transfer — the direction that hurts.

**What it changed, concretely.** Golden tuple G5, a gossypol Ki for *Mus
musculus*, previously resolved to 0.0007 mM measured in *Plasmodium
falciparum* — an apicomplexan parasite's inhibition constant offered as a
rodent's, because "lowest value" was the tie-break and lowest value is not a
scientific criterion. *Plasmodium falciparum* and *Cryptosporidium parvum*
share only the domain Eukaryota with a mouse and are now excluded. The
answer is the *Homo sapiens* value, 0.0014 mM: still cross-species, still
flagged, but two mammals sharing the superorder Euarchontoglires.

**What it is not.** Relatedness is not kinetic similarity. Two mammals can
have genuinely different Km for the same enzyme and substrate, and this
check cannot tell you they do. It removes the most indefensible transfers
and nothing more. That sentence is in the module docstring and in the
user-facing message, because the risk of adding a check is that its
existence gets read as an endorsement of whatever survives it.

**Verification.** 27 tests in `Tests/test_taxonomy.py` against captured NCBI
lineages for eight organisms. Six mutations introduced, six caught:
unknown-permits-transfer, threshold loosened to phylum, threshold tightened
to order, name-matching instead of id-matching, unranked nodes allowed as the
answer, and the gate skipped entirely in the resolver.

*Danio rerio* is in the fixture set for one reason: it is the only organism
that pins the threshold from above. Human and zebrafish share the phylum
Chordata and the subphylum Craniata but sit in different classes, so
loosening the threshold to "phylum" changes their verdict. Without that
pair, every non-mammal also failed at the domain level and the loosening
mutation was caught only by the assertion that literally reads the constant
— a threshold nothing depends on is a threshold that will drift.

A hardcoded list of "mammals" would have satisfied the letter of the
recommendation and violated the constitution's first rule.

## Decision 2 — a parameter with no source anywhere (OPEN)

**No decision.** Sauro's position has not been answered, and answering it
by citing Jeske would be a sleight of hand: she was asked about
cross-species substitution, which is a different question from what to do
when the literature holds nothing at all. A rabbit Km is a real measurement
of something; 0.5 is a measurement of nothing.

The question put back to him is whether the real distinction is a mode —
default when a model must run, refuse when a student is being taught — in
which case this is a UX decision that has been treated as a moral one.

ADR 0012/0013 remain in force meanwhile. If the answer is "default with a
warning," that supersedes them and gets its own ADR rather than an edit to
this one.

## Decision 3 — Bakker's scoring, without Bakker's sampling (BUILT 2026-08-13)

**Adopting:** the scoring axes. The current binary verified/unverified flag
becomes a graded score over her three axes — assay completeness under
STRENDA (already parsed, ADR 0010), distance from physiological pH and
temperature, and organism match (now first-class, Decision 1). Each axis
reported separately rather than collapsed, so a reader can see *why* a
value scored low.

**Declining:** the ensemble. Sampling needs a distribution per parameter
and a flux dataset to validate the resulting models against. A teaching lab
has neither. Without the validation step, ensemble sampling produces spread
with no reason to trust any part of it — which is worse than a single
flagged value, because it *looks* like a rigorous uncertainty estimate.

This must be documented as a deliberate truncation of her method, not an
implementation of it. One question is outstanding with her: how the axes
were weighted relative to each other in practice. Inventing plausible
weights would reproduce, one level up, the exact thing this project refuses
to do with parameters.

**Built in `reliabilityScore.ts`, and it reports no total.** The three axes
are returned separately, alongside a `noAggregateReason` field carried in
the payload rather than left to documentation — so a client that goes
looking for a total finds an explanation instead of an absence it might
paper over with an average of its own. A single number would also be
strictly less informative: "0.61" cannot tell a reader *which* axis was
weak, and that is the only part they can act on.

**The physiological reference has no default, and that is the hard part.**
"Physiological pH and T" has no organism-independent value. 7.4 and 37 °C
describe a mammal and misdescribe *Thermus thermophilus*, whose enzymes are
measured near 70 °C — the very comparison Jeske raised when she warned about
mixing conditions across sources. So the reference is an *experimental
condition* supplied by whoever builds the model, exactly as `s0` and `end`
are (ADR 0012/0013). Absent it, the axis reports `not_assessed` and says
why. Baking in 7.4/37 would have encoded a silent assumption that every
model is mammalian, and would report a confident `far` for a thermophile
assay that was in fact ideal.

24 tests, including the two refusals easiest for a later contributor to
helpfully "fix": that no total is produced, and that a missing reference is
not treated as a pass.

## Language

Prefer "measured parameter" or "measured quantity" over "constant" in
outreach, on the website, and in user-facing copy. The codebase already
uses the right term internally — the measured-quantity versus
experimental-condition distinction is enforced in
`validateParameterProvenance`. The external language had drifted from it,
and Katz's reply is what surfaced the drift.

## A fourth reply, not about the science

Matthias König (HU Berlin / Universität zu Lübeck), an author of Tellurium,
read the outreach email as a claim to have built Tellurium and called it
"very suspicious." He was reacting to a real problem: **Caterva** against
**Tellurium**, in a message about SBML and Antimony, reads as a claim
rather than a coincidence.

Consequence: a disambiguation notice now sits at the top of the README
stating that Caterva is unaffiliated with Tellurium, is not a fork, and
consumes that ecosystem rather than competing with it. The name itself is
recorded as an open question rather than a settled one.

This belongs in an ADR because it is a design consequence, not a social
one: a name that misleads domain experts on first contact is a defect with
the same shape as a misleading error message.

## Consequences

- ADR 0018 is narrowed: cross-species resolution no longer fires
  automatically. Callers that relied on it must pass `allow_cross_species`.
- The wire format gains `allowCrossSpecies` (request) and
  `crossSpeciesOrganismsAvailable` (response).
- `ParameterProvenance` gains `unresolvedReason`.
- `RequiredParametersMissingError` gains `details`, and stops asserting a
  single reason for every missing key.
- ADR 0012/0013 remain in force for the missing-entirely case.
- The relatedness check and the graded reliability score are BUILT. What
  remains named-and-unbuilt is the axis weighting, which is blocked on an
  answer from Bakker rather than on effort.
- `Tests/taxonomy.py` makes NCBI Taxonomy a runtime dependency of the
  cross-species path. It degrades to a refusal, never to a pass.
- Two servers, one CLI and the OpenAPI spec all carry `allowCrossSpecies`.
  The cache key includes it — without that, a cross-species result cached by
  someone who opted in would be served to a student who did not, and Jeske's
  checkbox would be defeated by a cache.
- User-facing language stops saying "constant."
- This ADR is the project's own standard applied to itself: three experts
  disagreed, and the response is to record the disagreement and say which
  column of the table Caterva sits in — not to quote the one who agreed.
