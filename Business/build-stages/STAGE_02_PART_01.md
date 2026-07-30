# Stage 2, Part 1 — Domain Choice, Grounding, and the Constitution Applied to Population Genetics

## 0. What Part 1 means now, versus what it meant in Stage 1

Stage 1's Part 1 was unusual: it built the constitution itself, because
none existed yet. Per the 5-part structure that Stage 1 established and
`Business/BUILD_PIPELINE.md` now documents, Part 1 of every stage from here
on is "the standards preamble" — which does *not* mean re-deriving the
nine rules again. `docs/CONSTITUTION.md` Section 3 is fixed text, pasted
verbatim into every implementation prompt; there is nothing to rewrite.

What Part 1 *does* mean for every stage after the first is: apply the
existing constitution concretely to this stage's specific domain, decide
which rules are load-bearing here versus which barely apply, surface any
genuinely new question the constitution doesn't yet have an answer for,
and ground the actual science well enough that Part 2's spec isn't written
from a shaky understanding. That's what this document does for population
genetics. It is shorter than Stage 1's Part 1 by design — the rules
already exist; this is their application, not their invention.

## 1. Why population genetics, over molecular dynamics setup, for Stage 2

`Business/ROADMAP.md` lists three remaining Phase 2 domains: Monte Carlo
(done, Stage 1), population genetics, and molecular dynamics setup. Between
the two remaining, population genetics goes second, not molecular dynamics,
for a reason that follows directly from Rule 1 of the constitution
(**every numerical claim is checked against an independent source of
truth**): population genetics has exact, textbook-standard closed-form
verification targets available immediately — Kimura's fixation
probability formula, the exact heterozygosity decay recursion — the same
way Monte Carlo had `math.pi` as an unimpeachable ground truth. "Molecular
dynamics setup," by contrast, is a vaguer target as written in the
roadmap — it says "setup," not "a full MD engine," and what exactly a
teaching-lab-appropriate MD *setup* tool should minimally validate isn't
yet a solved question the way population genetics' core case is. Rather
than force a fuzzy scope into a domain spec and discover mid-implementation
that the verification target was never actually pinned down, population
genetics goes now, because its Rule 1 answer is already known cold, and
molecular dynamics gets its own future stage once a Perplexity/Kimi
research pass (per the constitution's research-stage protocol) narrows
"setup" into something with an equally concrete verification target.

This is itself an example of the constitution being used as intended: the
choice of *which* domain to build next was made by asking "which one has
an answer to Rule 1 ready today," not by roadmap order alone.

## 2. The actual science, grounded before any spec gets written

### 2.1 The model: Wright-Fisher, single locus, two alleles, neutral drift

The standard, simplest, well-verified starting case in population
genetics is the **Wright-Fisher model**: a population of constant size
$N$ (diploid, so $2N$ allele copies), one genetic locus, two alleles (call
them $A$ and $a$). Each generation, the next generation's allele copies are
formed by sampling $2N$ times, with replacement, from the current
generation's allele pool — i.e., if the current frequency of allele $A$ is
$p$, the number of $A$ copies in the next generation is a **binomial random
variable**: $X_{t+1} \sim \text{Binomial}(2N, p_t)$, and the next
generation's frequency is $p_{t+1} = X_{t+1} / 2N$.

This is a discrete-generation, stochastic-sampling process — no
continuous-time differential equation describes it, and there is no
selection, mutation, or migration in this first (neutral) case: allele
frequency changes only because of the finite-population sampling itself
(genetic drift). This is the same *category* of process Monte Carlo was —
independent sampling producing a stochastic estimator — but the actual
governing math (binomial sampling of allele copies across generations,
rather than i.i.d. draws averaged into a single estimator) is genuinely
different, so Monte Carlo's implementation is a structural precedent, not
a template to copy formulas from.

### 2.2 The two closed-form verification targets

**Target A — expected heterozygosity decay (exact, deterministic
recursion).** Heterozygosity $H_t$ — the probability two randomly-drawn
allele copies in generation $t$ are different alleles — decays under
neutral drift according to an *exact* recursion with no approximation:

$$H_{t+1} = \left(1 - \frac{1}{2N}\right) H_t$$

so after $t$ generations, $H_t = H_0 \left(1 - \frac{1}{2N}\right)^t$.
This is not an asymptotic approximation — it's the exact expected value of
heterozygosity under the Wright-Fisher model, derivable directly from the
binomial sampling variance, and it is the population-genetics equivalent
of Monte Carlo's `sqrt(N)` convergence rate: a precise, checkable
mathematical claim about how a stochastic process behaves in expectation
over many independent replicate populations.

**Target B — fixation probability (Kimura's result, exact for the neutral
case).** For a neutral allele starting at frequency $p_0$ in a population
of size $N$, the probability it eventually reaches fixation (frequency 1,
with the other allele lost) is, for the neutral case, exactly:

$$P(\text{fixation}) = p_0$$

This specific result — that under pure neutral drift, an allele's
fixation probability equals its starting frequency exactly, independent of
population size — is one of the cleanest, most surprising, most citable
results in population genetics (it falls directly out of the fact that
allele frequency is a martingale under neutral Wright-Fisher dynamics: its
expected value never changes generation to generation, so its expectation
at the fixation/loss absorbing boundary must equal its starting value).
This is an excellent Rule-1 verification target for exactly the reason
`math.pi` was for Monte Carlo: it's exact, it's independently well-known
(this is Kimura's 1962 fixation-probability result, foundational and
textbook-standard, not an obscure or disputed claim), and it doesn't
depend on any detail of *how* the simulation code happens to be written —
any correct Wright-Fisher implementation must reproduce it, over enough
replicate simulated populations.

### 2.3 Why these two targets together, not just one

Target A checks the *trajectory* (heterozygosity decaying at the correct
rate over time, within a single run or averaged across runs at each
generation). Target B checks the *absorbing-boundary outcome* (did the
right fraction of many independent replicate populations end up fixed for
the starting-frequency-consistent allele). These are different enough
properties of the same model that a bug affecting one might not affect
the other — for instance, an off-by-one error in how the "next
generation" sampling step is coded could distort the heterozygosity decay
rate while still, by chance, preserving the correct fixation probability
over enough replicates, or vice versa. Requiring both, the way Monte
Carlo's spec required checking both convergence rate *and* reported
standard-error consistency (two different properties of the same
estimator), is a deliberate design choice carried over from that
precedent, not duplicated effort.

## 3. Applying the nine constitution rules to this specific domain

**Rule 1 (independent verification)** — satisfied by Section 2.2 above,
concretely. Both targets are exact, not approximate, which is the same
standard Monte Carlo held itself to (bit-identical seed reproducibility,
not "close enough").

**Rule 2 (`ok`/`flagged` contract)** — this domain introduces at least one
genuinely new plausibility question the constitution's existing rule
doesn't answer by itself: what counts as an implausible-but-real
population size or starting frequency for a *teaching lab* context,
versus a value that's simply wrong? A population size of $N=1$ is
degenerate but not impossible (heterozygosity would decay to zero
immediately — $H_1 = 0$ exactly per the formula above, since $1 - 1/(2 \cdot
1) = 0.5$... actually check: $2N=2$, so $H_1 = 0.5 \cdot H_0$, not zero;
the degenerate case is $N \to$ very small, not literally broken). This
needs a real decision in Part 2's spec, not deferred — see Section 5
below for the specific question Part 2 must resolve.

**Rule 3 (continuous vs. discrete, explicit)** — discrete. Wright-Fisher
is fundamentally a discrete-generation model; there is no meaningful
continuous-time state between generation $t$ and generation $t+1$ to
integrate through (this is analogous to the reasoning that put PCR and
Monte Carlo outside the antimony/roadrunner pipeline — ADR 0002's logic
extends cleanly here). This is not routed through antimony/SBML/roadrunner.
Direct Python, using binomial sampling (`numpy.random.Generator.binomial`),
following Monte Carlo's precedent of `numpy.random.default_rng(seed)` as
the RNG source.

**Rule 4 (shared constraints enforced by test)** — this is the first
domain since PCR/Monte Carlo that doesn't share a plausibility bound with
any existing layer (the literature layer's Km bounds are irrelevant here;
there's no BRENDA/KEGG equivalent database of "plausible population
sizes" this codebase is drawing from). What it *does* share, and this is
worth flagging explicitly as a genuinely new instance of Rule 4: the RNG
seeding convention. Monte Carlo established `numpy.random.default_rng(seed)`
as the house pattern (documented as a judgment call in its own
implementation comment, per the constitution's Rule 9 instruction to flag
judgment calls rather than pick silently). Population genetics should
follow that same convention rather than deviating without a stated reason
— and if a future domain deviates from it, that deviation needs its own
justification, per the exact language Monte Carlo's own code comment
already anticipated ("if a future stochastic domain needs correlated or
low-discrepancy sequences, it should document why it deviates from this
default rather than picking a different generator silently"). This isn't
yet a test-enforced sync (there's no automated check that two RNG-using
domains use the same generator class), which is worth flagging as an open
question for Part 2 to resolve explicitly rather than silently inheriting.

**Rule 5 (dependency declarations)** — `numpy` is already declared
(`requirements.txt`, confirmed working with the current CI Python matrix
per Stage 1's closing verification). No new dependency is anticipated for
the neutral Wright-Fisher case; if a future extension needs a specialized
population-genetics library (e.g., something like `msprime` for
coalescent simulation), that's explicitly out of scope for this stage —
see Section 5.

**Rule 6 (mutation testing)** — at least one mutation must be identified
in Part 2's spec before implementation, the way Monte Carlo's spec didn't
pre-specify mutations but the implementation's own report documented three
after the fact. For population genetics, a natural candidate mutation to
anticipate: using `2N` versus `N` inconsistently in the binomial sampling
size (a classic off-by-a-factor-of-2 error specific to diploid population
genetics, analogous to Monte Carlo's "missing factor of 4" SE-formula
mutation that OpenCode's independent reproduction caught) — this is worth
naming explicitly in Part 2 as a mutation the implementer should
deliberately test against, rather than leaving mutation choice entirely
to whichever bug the implementer happens to think of.

**Rule 7 (no umbrella `tellurium` package)** — not applicable; this domain
never touches antimony/roadrunner/SBML at all, so the umbrella-package
question doesn't arise here the same way it did for the ODE domains.
Worth noting explicitly rather than silently skipping this rule's
checklist item, so a future reader of this document doesn't wonder if it
was overlooked.

**Rule 8 (ADRs for architecturally significant decisions)** — this stage
likely warrants one new ADR: formalizing "discrete/stochastic domains
share an RNG convention (`numpy.random.default_rng(seed)`), and any domain
that deviates from it must say why" as its own numbered decision, since
this question has now come up in two domains (Monte Carlo, and now
population genetics) and is exactly the kind of decision ADR 0002/0003/0004
already exist to formalize instead of leaving as a scattered code comment.
This gets drafted in Part 2 or Part 4, once the actual implementation
either confirms or complicates this plan.

**Rule 9 (conservative defaults, judgment calls flagged)** — the choice of
*which* population-genetics case to implement first (neutral drift, no
selection/mutation/migration) is itself a Rule 9 judgment call, made
explicitly here rather than silently: selection, mutation pressure, and
migration all introduce real additional complexity and additional
verification targets (e.g., a selection coefficient changes the fixation
probability formula from the simple $P = p_0$ neutral case to a more
complex expression involving $s$ and $N$), and bundling all of that into
one spec risks the same kind of scope pressure Monte Carlo's spec
explicitly guarded against with its variance-reduction-is-out-of-scope
boundary. Neutral drift alone, with the two closed-form targets above, is
the conservative, well-verified starting point; selection/mutation/
migration are explicitly deferred, not silently dropped — see Section 5.

## 4. What's genuinely new here versus what Monte Carlo already settled

It's worth being precise about this, since treating every stage as
starting from zero would waste the entire point of having a constitution.
Already settled, inherited without re-litigation: the `ParameterValidation`/
`SimulationResult` contract shape, the discrete-domain-bypasses-antimony
pattern, the RNG convention (`default_rng(seed)`), the requirement that
mutation tests be independently reproduced by the reviewer rather than
taken on report, and the entire five-part stage structure itself. Newly
introduced by this domain specifically: a *second* stochastic domain
sharing the RNG convention (which surfaces the open Rule 4 question above
about whether that convention should become a test-enforced constraint,
not just a documented convention), a domain whose core verification targets
are about population-level statistical properties across replicate
simulated populations rather than about a single estimator's convergence,
and the first real candidate for a fifth ADR.

## 5. Explicitly out of scope for this stage

Following the same discipline Monte Carlo's spec used (variance-reduction
techniques named and explicitly deferred, not silently ignored):

- **Selection.** No selection coefficient, no fitness differential between
  alleles. Neutral drift only.
- **Mutation.** No new-allele-introduction mutation rate. The two starting
  alleles are fixed; the simulation only tracks their frequencies changing
  via drift.
- **Migration / population structure.** Single, unstructured population.
  No multiple demes, no migration rate between them.
- **Multiple loci / linkage.** Single locus only. No linkage disequilibrium,
  no recombination.
- **Coalescent-based simulation** (the alternative, backward-in-time
  approach to population genetics simulation, as opposed to this stage's
  forward-in-time Wright-Fisher approach). Forward simulation is chosen
  because its verification targets (Sections 2.2) are more directly
  checkable with the closed-form results already identified; coalescent
  methods are a legitimate future extension, not this stage's job.
- **Any population-genetics-specific external library** (e.g., `msprime`,
  `simuPOP`). This stays a direct, from-scratch Python implementation,
  matching the standard already set by PCR and Monte Carlo — no new
  runtime dependency for something implementable directly and verifiably
  in under a hundred lines.

## 6. What Part 2 has to resolve, inherited from this part

Three specific open items, carried forward explicitly rather than left
implicit for Part 2's spec to silently paper over:

1. The exact `ok`/`flagged` bounds for population size $N$ and starting
   frequency $p_0$ — what counts as "technically valid but a teaching lab
   probably didn't mean this" (e.g., $N$ absurdly small, or $p_0$ at
   exactly 0 or 1, which is valid but degenerate — the allele is already
   fixed/lost before the simulation starts).
2. Whether the RNG-convention question (Rule 4, Section 3) becomes an
   actual ADR in this stage or gets deferred to whenever a third
   stochastic domain makes the pattern undeniable — Part 2 should decide
   this explicitly, not let it drift.
3. The specific mutation to pre-specify in the spec (the `2N`-vs-`N`
   diploid sampling-size error named in Section 3's Rule 6 discussion),
   so the implementer isn't left to invent a mutation test from scratch
   the way Monte Carlo's implementer was — this stage tries pre-specifying
   at least one mutation in the spec itself, as a small process
   improvement worth testing.

Part 2 writes the full 10-field domain spec using the template already
fixed in `docs/CONSTITUTION.md` Section 4, resolving all three of the
above, ready to hand to OpenCode and FreeBuff exactly the way Monte
Carlo's Part 2 did.
