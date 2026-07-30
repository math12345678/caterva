# Stage 1, Part 1 — Project Charter & the Non-Negotiable Engineering Standards

## 0. Where this fits

This is the first part of the first stage of a 100-stage build plan for
Terrium. Before any new domain code gets written by OpenCode, FreeBuff, or
anyone else, there has to be a single document every future agent, in every
future stage, gets pointed at first — the constitution. Not a style guide.
A constitution: the small number of rules that are not up for
re-litigation by whichever coding agent happens to be running that day.

The reason this has to be Part 1, before anything about Monte Carlo or
population genetics or molecular dynamics, is a lesson this exact codebase
already paid for once. Over the course of building the first three domains
(Michaelis-Menten kinetics, SIR/SEIR epidemiology, PCR amplification), three
real mistakes happened and got fixed:

1. `libroadrunner==2.9.0` got pinned in `requirements.txt` with no wheel
   available for the Python version CI actually used, and CI went red.
2. `httpx` and `pydantic` got imported in `brenda_client.py` without ever
   being added to `requirements.txt` — it worked locally because they were
   already installed as transitive dependencies of something else, and
   broke in a clean environment.
3. `gamma` — the natural, obvious name for a recovery rate constant in an
   SIR model — turned out to be a reserved word in antimony, the modeling
   language this engine translates into SBML. Nobody would guess that
   without either reading antimony's grammar or hitting the error.

None of these were stupid mistakes. They were the normal cost of building
something for the first time. But they are not mistakes that should happen
*again*, now that they're known, just because a different tool wrote the
next piece of code and didn't have this history in its context window. That
is the entire reason Part 1 exists: to take everything that is now known
and turn it into an artifact that travels with every future prompt, instead
of living only in one person's memory of one long conversation.

## 1. What "done" means for this part

By the end of this part, three things exist:

- A single canonical document (this one, later split into
  `docs/CONSTITUTION.md` as the stable, always-referenced file) that states
  the non-negotiable rules for all future Terrium engineering work.
- A concrete, mechanical checklist that can be run against any diff,
  from any agent, to determine pass/fail before it's allowed to merge.
- A prompt template — the "preamble" — that gets prepended to literally
  every future implementation prompt handed to OpenCode, FreeBuff, or any
  other coding agent, for the rest of the 100-stage build.

This part does not write any simulation code. It does not touch
`tellurium_engine.py`. Its only output is process and documentation. That
is deliberate: you cannot meaningfully review code against a standard that
doesn't exist yet in writing, and every later stage depends on this one
being right.

## 2. Why a multi-agent pipeline needs a constitution more than a single dev does

If you, alone, were writing every line of Terrium's code, the standards
above could live entirely in your head, and "meticulous" would just mean
"be careful." The moment a second contributor exists — human or model — a
gap opens up between what you know and what they know, and that gap is
exactly where regressions live. A multi-agent pipeline with five different
tools (Claude, OpenCode, FreeBuff, Kimi, Perplexity) makes that gap worse in
a specific way: none of these tools share memory with each other, and most
of them don't retain memory across their own separate sessions either. Every
single invocation of OpenCode or FreeBuff, unless told otherwise, starts
from zero. Zero knowledge of the antimony reserved-word problem. Zero
knowledge that this codebase's actual standard for "tested" means checked
against a closed-form solution, not just "the function returns a plausible
number." Zero knowledge that a new import needs a matching line in
`requirements.txt` in the same commit, not a follow-up.

This is not a criticism of any of those tools. It is a structural fact
about stateless coding agents, and the fix is not "hope the agent
infers the right conventions from reading the codebase" — that is what
happened before you had a constitution, and it is exactly how you got the
three bugs listed in Section 0. The fix is to make the standards an
explicit, mandatory input to every prompt, every time, forever. That is
what "constitution" means in this document: not inspiration, not
guidelines to keep in mind — a required precondition, checked mechanically,
before anything is trusted.

## 3. The non-negotiable standards, in full

These are organized as numbered rules, each with the reasoning behind it,
because a rule without its reasoning gets silently dropped the first time
someone (or some model) thinks it's being overly cautious for no reason.

### Rule 1 — Every numerical claim is checked against an independent source of truth

A simulation function is not "done" when it runs without crashing and
returns numbers that look like the right shape of curve. It is done when
its output has been checked against one of: an exact closed-form analytic
solution, a known-correct independent solver or library, or a physical
invariant that must hold regardless of implementation (conservation of
mass, a monotonicity property, a symmetry). "Looks right" is not a
verification method — it is the thing that let three separate, real,
regression-worthy bugs into three different layers of this system before
anyone paid attention to it as a formal rule.

Concretely: when the Michaelis-Menten domain was built, the test suite
didn't just run the simulation and eyeball the curve. It checked the output
against the implicit closed-form solution `Km*ln(S0/S) + (S0-S) = Vmax*t`,
which is analytically true for that ODE regardless of what the simulation
code does internally. When SIR was built, the tests checked against the
SIR conserved quantity `S + I - (N/R0)*ln(S) = const` and the known final-size
equation, both of which exist independently of this codebase, in the
epidemiology literature, and would hold for *any* correct SIR implementation
anywhere.

The implication for every future domain: before a single line of
implementation code is written, the closed-form/invariant/independent-solver
check has to be identified and written down. If nobody can name one, that
is not a reason to skip this rule — it is a signal that the domain isn't
understood well enough yet to implement correctly, and the research stage
(Perplexity/Kimi, see Section 6) needs to run first.

### Rule 2 — Physical impossibility is rejected; implausible-but-real is flagged, never silently accepted

Every domain in this codebase distinguishes between two categories of bad
input, and conflating them is a real bug, not a stylistic choice. A
parameter can be:

- **Physically impossible.** A negative reaction rate. A recovery rate
  greater than 1 for a probability-per-timestep formulation. These get
  rejected outright — the model is never built, `ModelBuildError` is
  raised immediately, and no simulation ever runs on impossible physics.
- **Physically possible but implausible.** A Km value of 500 mM is not
  impossible, but it is astronomically unlikely for any real enzyme in the
  literature — most enzyme Km values fall within roughly `1e-7` to `1e3`
  mM, and 500 sits at the edge of what's been observed, not beyond physics.
  These get **flagged**, not rejected: the model still builds, the
  simulation still runs, but the result carries a `flagged=True` and a
  `flag_reason` that a human or downstream consumer can see and act on.

This distinction exists as a formal contract (`ParameterValidation`, with
`ok` and `flagged` as separate fields) precisely because collapsing it in
either direction is a real failure mode. Collapse toward "reject anything
unusual" and the tool becomes useless for edge-case teaching scenarios
(what if an instructor *wants* to show students what happens with an
implausible Km, as a teaching moment about outliers?). Collapse toward
"accept everything that technically doesn't crash the solver" and you get
a tool that will happily simulate physically impossible enzyme kinetics
and hand a student a confident-looking chart with no warning attached.
Every future domain must implement this same two-tier contract, using the
same field names (`ok`, `flagged`, `flag_reason`) so that a caller working
across multiple domains doesn't have to special-case each one.

### Rule 3 — Domain modeling choice (continuous vs. discrete) is a decision, made explicitly, before implementation

This codebase translates models into antimony, then SBML, then integrates
them with roadrunner — an ODE solver pipeline built for continuous-time
processes. That pipeline is correct for enzyme kinetics and epidemiology,
because those are genuinely continuous-time phenomena governed by
differential equations. It would have been actively wrong for PCR
amplification, because PCR is not continuous — it happens in discrete
cycles, and copy number at cycle *n* is an exact, closed-form function of
copy number at cycle *n-1*, with no meaningful "in-between" state to
integrate through. Forcing PCR through the ODE pipeline would have meant
introducing numerical integration error into a process that has an *exact*
answer with no error at all — strictly worse accuracy, for no benefit,
because of an unexamined default.

The rule going forward: for every new domain, before any code is written,
explicitly answer "is this continuous-time (→ antimony/roadrunner) or
discrete (→ direct recurrence in Python, no solver involved)?" and write
the answer down as part of that domain's spec, with the reasoning. Do not
let this default silently to "whatever the previous domain did," because
the previous domain's answer was correct for *that* domain's physics, not
because continuous-time is the house style.

### Rule 4 — Shared constraints across layers must be enforced by a test, not a comment

The literature layer (`Tests/brenda_client.py`, doing BRENDA/KEGG/PubMed
lookups) and the simulation layer (`Tellurium/tellurium_engine.py`) both
have opinions about what counts as a "plausible" Km value. Those two
opinions have to agree — if the literature layer will happily hand back a
value the simulation layer would flag as implausible, or vice versa, the
system is internally inconsistent in a way a user would eventually notice
and lose trust over. The rule is not "remember to keep these in sync." The
rule is: there exists an automated test whose entire job is to import both
layers' bounds and assert they're equal, so that if a future change to
either one drifts, the test suite — not a future user, not a future
code review — is what catches it, immediately, mechanically, every single
run.

This generalizes: any time two parts of the system encode the same
constraint independently (because they're different layers, different
languages, different modules), the sync between them must be enforced by
an executable test, not a comment saying "keep this consistent with X."
Comments get stale. Tests fail loudly.

### Rule 5 — Undeclared dependencies are a category of bug that gets a permanent automated guard, not a one-time fix

When `httpx` and `pydantic` were used in `brenda_client.py` without being
declared in `requirements.txt`, the fix wasn't just "add the two missing
lines." The fix was `scripts/check_dependencies_declared.py` — a static
AST-based scanner that walks every Python file, finds every top-level
import, and fails loudly if any of them aren't declared in
`requirements.txt`, wired into the test suite itself
(`test_dependencies_declared.py`) so it runs on every single CI invocation
forever, not just the one time someone remembers to check. The general
principle: when a bug is discovered that could plausibly recur because a
class of mistake exists (not just a one-off typo), the fix is not just
patching the instance — it's building the mechanical guard that makes the
entire *class* of mistake fail loudly and immediately, every time, without
relying on anyone's memory or diligence.

This matters enormously for a multi-agent pipeline specifically, because
OpenCode or FreeBuff adding a new import in a future domain has no memory
of this exact incident. The guard doesn't need them to remember — it's
already running, in CI, regardless of who wrote the code or what they did
or didn't know about this document.

### Rule 6 — Mutation testing is how you verify the test suite, not just the code

A test suite that has never had a single line of correct code deliberately
broken in front of it, to confirm the tests actually fail when they
should, is a test suite whose value is unverified. This codebase's actual
practice, used for the PCR domain, is: after writing tests, deliberately
introduce a specific, realistic bug (change exponential growth to linear
growth; remove the plateau-saturation logic), run the suite, confirm the
expected test(s) fail, then revert the mutation and confirm the suite is
clean again. This is not optional polish. A test suite that passes on both
correct code and broken code is providing false confidence, which is worse
than providing no confidence, because it looks like safety.

Every future domain's implementation is required to include at least one
documented mutation test — a specific, named mutation, the specific test
that caught it, and confirmation that reverting the mutation restores a
clean suite. This gets written into the spec for every domain (see Part 2
of this stage) as a checklist item, not left as something an implementer
does if they feel like it.

### Rule 7 — The umbrella package is banned, permanently, with the reasoning preserved

`pip install tellurium` is not used anywhere in this codebase, on purpose.
The umbrella `tellurium` package pulls in `python-libcombine` and
`python-libnuml`, which exist to handle COMBINE archives and numerical
markup language — neither of which this project uses, and neither of which
has prebuilt wheels on many platforms, meaning the install falls back to
building from source and needs `cmake` and `swig`, which is exactly the
kind of fragile, unnecessary dependency surface that breaks CI for reasons
totally unrelated to the actual product. Instead, the three packages that
actually do the necessary work are used directly: `libroadrunner` for ODE
integration, `antimony` for the human-readable model definition language
that compiles to SBML, and `python-libsbml` for SBML validation. This is
recorded formally in `docs/adr/0001-no-tellurium-umbrella-package.md`
specifically so that a future contributor — or a future coding agent asked
to "make sure the tellurium dependency is installed" — doesn't undo this
decision by reflexively reaching for the obvious-sounding package name.

### Rule 8 — Every architecturally significant decision gets an ADR, not just a comment or a Slack message

An Architecture Decision Record is short, follows a fixed shape (Status,
Context, Decision, Consequences), and exists specifically so that six
months from now, or with a completely different coding agent doing the
work, the *reasoning* behind a non-obvious choice is retrievable, not just
the choice itself. The four that exist today (no umbrella package, PCR as
discrete not ODE, shared plausibility bounds enforced by test, gamma
reserved-keyword workaround) set the pattern. Every future stage that makes
a decision of this shape — not "which variable name," but "which entire
approach, and why not the obvious alternative" — writes a new ADR before
moving on, numbered sequentially, and cross-references it from any spec
that depends on it.

### Rule 9 — Conservative defaults over irreversible optimism, everywhere the two conflict

This shows up in two different places in the existing repo, and the
underlying principle generalizes to all future work: the LICENSE defaults
to all-rights-reserved rather than a permissive open-source license,
because Terrium's business model assumes institutional licensing revenue,
and giving the codebase away permissively before that model is validated
forecloses an option rather than preserving one — the decision to open
things up can be made later, deliberately, with legal input; the decision
to have given it away can't be undone. Similarly, the pnpm supply-chain
policy (`minimumReleaseAge: 1440` in `pnpm-workspace.yaml`) delays adopting
any package version until it's been out for 24 hours, specifically as a
defense against supply-chain attacks that get caught and yanked within
that window — a small, deliberate friction chosen over the "always take
latest" default. The general rule for every future stage: when a choice is
easily reversible later, optimize for velocity now. When a choice would be
expensive or impossible to reverse later (giving away IP, adopting an
unvetted dependency, a data-modeling choice that everything downstream
depends on), default conservative and revisit deliberately, not by default.

## 4. The mechanical checklist (for use at Stage 3 of every future part's pipeline — see Part 2)

This is the literal, run-every-time checklist a reviewer (Claude, in this
pipeline) applies to any diff from any implementer, before it's trusted:

1. Does every new numerical claim have an identified closed-form solution,
   independent solver, or invariant it's checked against? Is that check
   actually present as an assertion in a test file, not just described in
   a docstring?
2. Does the domain distinguish `ok=False` (rejected, impossible) from
   `ok=True, flagged=True` (accepted, implausible, warned) using the exact
   same field names and shape as the existing `ParameterValidation`
   contract?
3. Was the continuous-vs-discrete modeling choice made explicitly, in
   writing, before implementation — and does the implementation match
   that stated choice?
4. If this domain shares any constraint with another layer of the system
   (a bound, a unit, a naming convention), is that sync enforced by an
   executable test?
5. Does every new top-level import have a matching line added to the
   relevant `requirements.txt` or `package.json` in the *same* diff?
6. Has at least one mutation test been performed and documented — a
   specific bug deliberately introduced, the specific test that caught it
   named, and the suite confirmed clean again after reverting?
7. Does this change touch antimony model generation? If so, has every new
   variable/parameter name been checked against antimony's reserved words?
8. Is there an architecturally significant decision buried in this diff
   that isn't yet an ADR? If yes, write the ADR before merging, don't defer
   it.
9. Does the LICENSE/dependency-freshness posture of this change lean
   conservative where the choice is hard to reverse later?
10. Does the full test suite pass, run directly by the reviewer (not taken
    on the implementer's report), with zero unexplained skips?

A diff that fails any of these ten items is not "mostly done." It goes
back to the implementer with the specific failing item named, exactly the
way a real code review would work, except mechanical and non-negotiable
rather than a matter of reviewer taste.

## 5. How this maps onto the five-tool pipeline, specifically for this part

**Claude's role in this part:** everything above — Claude wrote this
document, because this is meta-level process work (deciding what the
rules are), not implementation, and that's squarely the orchestrator's
job as defined in `Business/BUILD_PIPELINE.md`. There is no code for
OpenCode or FreeBuff to write in this part; there's a document for them to
be pointed at, permanently, starting with Part 2.

**OpenCode / FreeBuff's role in this part:** none, deliberately. Handing
implementation agents a "write the constitution" task would be exactly
backwards — they're stateless per-session and have no independent stake in
which rules should be non-negotiable across 100 stages of future work.
This is the one kind of task in the whole pipeline that's reserved for the
orchestrator alone.

**Kimi / Perplexity's role in this part:** none. Research tools are for
grounding domain-specific technical questions (what's the correct governing
equation for allele frequency drift in population genetics, what's a known
reference implementation for a given Monte Carlo technique) — not for
deciding what this project's internal engineering standards should be.
Those standards come from this project's own history, documented above,
not from external research.

**Why this matters as a pattern going forward:** not every part of not
every stage needs all five tools involved. A pipeline that mechanically
runs research → implement → review → verify on every single part, even
when a part is pure process/documentation work like this one, is
performing the pipeline instead of using it. The actual discipline is
knowing which stages need which tools, and saying so explicitly in each
part's write-up — which is exactly what this section just did.

## 6. The prompt (the permanent preamble)

This is the block of text that gets prepended, verbatim, to every future
prompt given to OpenCode or FreeBuff for the remainder of the 100-stage
build. It is intentionally not domain-specific — Part 2 of this stage adds
the domain-specific spec template on top of this preamble, but this part
of the prompt never changes:

```
You are implementing a piece of Terrium, a scientific simulation engine
for teaching labs. Before you write any code, internalize these
non-negotiable standards — they exist because each one was learned from a
real bug in this exact codebase, not as generic best practice:

1. Every numerical claim you implement must be checked, in a test, against
   an exact closed-form solution, a known-correct independent solver, or a
   physical invariant. "The output looks like a reasonable curve" is not
   verification and will be rejected in review.

2. Distinguish physically-impossible parameters (reject with
   ok=False, raise ModelBuildError, never simulate) from
   physically-possible-but-implausible parameters (ok=True, flagged=True,
   flag_reason set, simulation still runs). Use exactly these field names.
   Do not collapse this distinction in either direction.

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
   rather than silently picking one — this project writes an ADR for
   decisions of that shape, and needs to know one might be warranted.

10. Report back explicitly: what you implemented, what closed-form/
    invariant/solver you verified against, what mutation test you ran and
    what it caught, and any judgment call you made that wasn't fully
    specified in the task. Do not report "tests pass" without this detail
    — a bare pass/fail is not sufficient for this project's review process.

[DOMAIN-SPECIFIC SPEC GOES HERE — see Stage 1, Part 2]
```

## 7. What Part 2 will cover

Part 2 of Stage 1 takes this constitution and turns it into the concrete
Stage 0 spec-writing process described in `Business/BUILD_PIPELINE.md` —
specifically, the exact template Claude fills in for *any* future domain
before handing work to OpenCode/FreeBuff, with a fully worked example
using the next real domain on the roadmap so the template isn't abstract.
Part 3 covers the verification harness in mechanical detail — the exact
commands, the exact mutation-testing procedure, written so precisely that
running it doesn't depend on remembering how it was done for PCR. Part 4
covers how disagreement between OpenCode and FreeBuff on an identical spec
gets resolved, with worked examples of what "meaningful divergence" versus
"cosmetic difference" actually looks like. Part 5 covers the research-stage
protocol for Perplexity/Kimi in full — what kinds of questions belong there,
how their output gets folded into a spec without letting ungrounded claims
skip verification, and how to sanity-check literature/algorithm claims that
research tools return before trusting them enough to implement against.
