# Terrium: what it is for, and what it should therefore be

**Status:** Proposed. Nothing below is built yet. This document exists to be
argued with before code is written.

**Date:** 2026-08-17

**Why it exists:** Terrium has ~115 ADRs, ~800 tests, nine CLI commands, an
HTTP API, a dashboard and eighteen repositories. It does not yet have a
person who uses it. Every pass of work has improved a part; no pass has
asked whether the parts add up to a tool. This one does.

---

## 1. The one job

> **Every number in a simulation says where it came from, and getting the
> simulation is easy enough that nobody routes around it.**

Both halves are load-bearing, and Terrium currently has one of them.

The provenance half is genuinely built and genuinely unusual. The easy half
is not built, and without it the provenance half does not matter — because a
tool people abandon has no provenance to speak of.

### The four audiences are one mission, in an order

When asked what Terrium is for, the answer given was "all of the above". That
is right, and it is not vague, provided the four are ordered rather than
pursued at once:

| | | role |
|---|---|---|
| **Teaching labs** | students get trustworthy numbers instead of a textbook's invented ones | **beachhead** — the only audience that will tolerate a young tool, and the one where a wrong number costs a grade rather than a grant |
| **Researchers** | stop pasting unsourced parameters | **expansion** — same claim, higher stakes, harder to earn |
| **No coding required** | describe the system, get a defensible simulation | **the constraint** that makes the first two real. Not a separate goal |
| **A reproducibility layer** | resolver + provenance record others call | **the architecture** that follows if you take the above seriously |

The failure mode of "all of the above" is building for everyone and serving
nobody. The discipline that prevents it: **when two audiences conflict, the
teaching lab wins until a teaching lab is actually using it.**

### What Terrium is NOT

Stating this is half the design, because the current codebase quietly tried
to be several of these.

- **Not a modelling environment.** Tellurium, COPASI and Virtual Cell exist,
  are excellent, and are not what a second-year student needs.
- **Not a database.** BRENDA is the database. Terrium reads it honestly.
- **Not a general simulator.** Fifteen domains is not a strength; it is
  fifteen surfaces each shallowly tested. See §5.
- **Not an AI tool.** Nothing here should guess a scientific value.

---

## 2. What the professors actually said, and what it implies for design

Four experts replied. Their feedback has been treated as a list of features
to implement. Read together it is something better: **a specification of the
one thing Terrium must never do, and the one thing it must always do.**

### Jeske (BRENDA / DSMZ) — mixing conditions gives "fantasy numbers"

A Km measured at pH 7.5/25 °C and a Ki measured at pH 6/37 °C, combined into
one model, produce a number that describes no experiment that was ever run.
Her word for it is *fantasy*.

**Design implication:** conditions are not metadata. They are part of the
value's identity. A design that stores `km: 10.73` and treats conditions as
an optional annotation has already lost — which is why §4 makes the resolved
value a compound object, not a float.

### Bakker (UMCG) — score parameters, and use the scores to *sample*

Her actual words, 2026-08-13:

> In practice, we chose the best option, but **do not exclude anything a
> priori**. We are preparing a publication in which we generated an ensemble
> of models by sampling from a distribution of possible parameters. We gave
> each parameter a score based on its reliability and applicability, such as
> physiological pH and T, species [...] and completeness of assay
> description. **These scores were then used to give the parameter a weight
> in the sampling.**

Method published: *Ensemble kinetic modelling links residual enzyme activity
to clinical symptoms in mitochondrial β-oxidation defects*, bioRxiv
`10.64898/2026.05.05.722902`.

**Correction to an earlier draft of this document.** It said the axis
weighting "was asked for and has not been answered", and that the ensemble
"was declined and should stay declined". Both are wrong, and reading her
reply directly is what showed it. She answered the weighting question in the
sentence that defines it: *the scores are the weights, and what they weight
is the sampling.* The grades were never meant to be three numbers printed
beside a value — they were the mechanism for drawing from the evidence.

**Design implication:** the scores are not a display. Rendering them as a
badge and stopping there implements the vocabulary of her method and none of
it.

### Sauro (UW) — first default it, then: sample it

Sauro answered twice, and **the second answer supersedes the first.** Only
the first was in this document.

*2026-08-13, 00:10* — before he knew of the other replies:

> If Brenda or pubmed has no value for a particular km I would just give it
> a default value, say 0.5 and write a warning comment in the antimony file.

*2026-08-13, 22:17* — shown Jeske's position and Bakker's side by side:

> **Barbara Bakker's approach is better.** With Jessie's approach you don't
> get any simulation, with Barbara's you can sample and get an ensemble
> distribution. **That is the right way to do it.** I would still give a
> warning so the user knows what's happening. If a value is missing, use a
> value from the closest organism and generate a distribution of values. Run
> each through roadrunner. You get a result and you're honest about the
> uncertainty.

This is the director of the NIH Center for Reproducible Biomodels
independently arriving at Bakker's method after being shown all three
options. **Two of the four experts converge on it, and the reply sent back
promised to build it** — "I will work on implementing the ensemble sampling".

His underlying warning survives both answers, and is the sharpest thing any
of the four said: a tool that will not produce a runnable model blocks step
one, so the researcher works around it by hardcoding a number with no
warning at all — a worse outcome, caused by the stricter rule. (That
sentence is this project's restatement. An earlier draft of this document
set it in a quotation block as if it were his. It is not.)

Terrium did not merely risk this; **it instructed it.** The error said "Add
km=<value> and try again", the user found a real number in a real paper,
typed it, and Terrium recorded `origin: user`, no citation. A number with a
source in the world, stripped of that source by the tool whose purpose is not
losing sources.

**Design implication, and it is the central one:** *every* place Terrium
cannot produce a value must offer a way to supply one **with its source
attached**. Refusal without a path is a defect, not rigour. This is why §4
has exactly one refusal shape and it always includes `--cite`.

### Katz (NCSA / Illinois) — "I don't really understand the idea"

Absent from every earlier draft of this document, which is the most
revealing thing about those drafts: he is the only correspondent whose
speciality *is* software citation, and his reply is the only one that
rejects the premise rather than the implementation.

> This is out of scope for JOSS, as it is not software that is used by
> researchers to do their research.
>
> **I don't really understand the idea of per constant citation. Most
> constants are well known and are not typically cited.**

A design document that omits the one expert who does not believe in the
product is not a design document. Two things follow.

**He is right about a class of constants, and it is not this class.** The
gas constant is well known. Avogadro's number is well known. A Km is not a
constant in that sense at all — it is a *measurement*, made once, under
conditions, by someone, and it moves. Terrium's own corpus is the evidence:
ADR 0033 found the same enzyme reported at 21.1 and 327.2 depending on
whether an allosteric activator was present, and ADR 0037 found chicken LDH
at 60 from heart and 1.1 from muscle. Nobody cites *R*. Everybody should
cite a number with a 15-fold spread across the literature.

**This is a naming failure as much as a design one.** "Per-constant
citation" invites exactly his reading, because it calls the thing a
constant. It is per-*measurement* provenance. If the pitch makes a
sympathetic expert think the answer is obvious and the question is silly,
the pitch is wrong before the code is.

**Design implication:** the spread is not a footnote to the answer — it is
the argument for the product. Where the literature agrees, Terrium should
say so plainly and Katz's objection holds. Where it disagrees by 15-fold,
that disagreement is the finding, and it is what §4.2 must show.

### König (HU Berlin) — the email read as a claim of credit

Handled (naming notice, guards). **Design implication for this document:**
Terrium's credibility is its only asset. Every design choice that risks
overclaiming — a confidence number with no basis, a "verified" badge, a
default that looks measured — costs more than the feature is worth.

### The unresolved item

ADR 0024 Decision 2 is open: what to do when a value is missing entirely.
This design answers it, and the answer is neither "refuse" nor "default":

> **Refuse to invent. Never refuse to help.**
> Terrium always produces either a cited value or a stated, sourced,
> user-supplied one — and it always makes the second as easy as the first.

---

## 3. The honest diagnosis of what exists

Measured, not asserted. A student's first minute today:

```
$ simulate "lactate dehydrogenase"
→ does not name a domain this pipeline knows (mm, sir)

$ simulate "michaelis menten" --resolve --substrate pyruvate \
    --organism "Homo sapiens" --enzyme "lactate dehydrogenase"
→ Cannot run: vmax, s0

$ ...and the suggested fix discards a --vmax the user already typed
   (recorded as an open defect in EXPERT_FEEDBACK.md)
```

**Three attempts, six flags, no number.** Every refusal correct. The tool is
optimising for not being wrong and has stopped optimising for being useful —
those are different goals and it noticed only one.

Three structural causes, each of which the new design must not reproduce:

1. **The interface is a flag protocol, not a question.** Six flags is a
   syntax you must be taught. The pitch says "ask a question in plain
   language" and the tool does not accept one.
2. **Breadth bought at the cost of depth.** Fifteen domains, and the flagship
   path still cannot complete a first run unaided.
3. **Nothing was ever finished end to end.** This session alone found: a
   command that never worked across processes, an API that killed its own
   server, a validator that refused a whole domain, hardcoded lactate
   dehydrogenase in four places. Each was a feature "completed" without
   anyone running it.

---

## 4. The design

### 4.1 One command

```
terrium "How does human lactate dehydrogenase behave on pyruvate?"
```

That is the product. Everything else is a flag on it.

Terrium parses the sentence into a **proposed system** and shows it back:

```
  I read that as:
    enzyme      lactate dehydrogenase
    substrate   pyruvate
    organism    Homo sapiens          [Enter to accept, or edit]
```

**Confirming is not the same as inferring.** The parse never becomes
provenance without a human keystroke — this is the constraint that lets
Terrium accept plain language without violating "never attach a citation to a
system the user did not name". `confirmSystem.ts` already implements this
correctly and is under-used.

Non-interactive (`--yes`, or piped) must **not** auto-confirm. It prints the
explicit command and exits. A script that silently accepted a parse would be
the inference we just forbade, wearing a different hat.

### 4.2 The answer has one shape

Whatever the question, the output is the same four blocks. A student learns
it once.

```
  ANSWER      Km = 10.73 mM  ·  lactate dehydrogenase (EC 1.1.1.27)

  SOURCE      BRENDA ref 740253 · Homo sapiens · exact organism match
              measured at pH 7.5, 25 °C

  TRUST       assay completeness   complete
              conditions           pH and temperature both reported
              organism             exact match
              (three grades, never blended — Bakker's weighting is unanswered)

  RESULT      [trajectory]
              final 5.1404 mM after 10 s
```

Nothing in that block is invented. If a field is unknown it says so and says
why, and that is a first-class outcome rather than a gap.

### 4.3 One refusal shape, and it always hands over the next step

Refusals are unavoidable and correct. What must change is that there is
**exactly one** refusal template, and it always contains a way forward:

```
  I cannot give you Vmax.

  WHY         BRENDA reports kcat but never [E]0 — how much enzyme you put
              in the tube is your experiment, not a property of the enzyme.

  YOU CHOOSE  --enzyme-conc 0.01mM      (this is yours to pick, not a gap)

  OR CITE     --cite vmax="Smith 2019, PMID 12345"
              recorded as user-supplied; Terrium does not verify it

  OR WIDEN    --allow-cross-species     related organism, relatedness checked
```

This is the answer to Sauro, made structural: the moment before a user goes
looking for a number is the only moment `--cite` can usefully be offered, and
it is offered every time.

**Distinguishing "you choose this" from "the literature had nothing" is the
single highest-value idea in this document.** They look identical today and
need opposite responses.

### 4.4 Depth over breadth

**Ship one domain, complete: Michaelis–Menten.** Everything else moves behind
`--experimental` or out of the product.

The teaching-lab audience needs enzyme kinetics done perfectly, not
population genetics done adequately. Fifteen shallow domains is why no path
is finished. This is the change that will feel like losing work and is the
one most likely to make Terrium usable.

### 4.5 The layer, made real

Because §4.1–4.3 must be identical in the CLI, the API and the dashboard,
they cannot each own logic. One resolver, one provenance record, three thin
presenters. This session found the same defect three times — one
implementation of the truth and a second copy that drifted (ADR 0003, 0027,
0036, 0086). The layer is not an aspiration; it is the only shape that stops
that recurring.

---

## 5. What gets deleted

A design that only adds is not a design.

- **Fourteen of fifteen domains** → `--experimental` or removed.
- **The dashboard**, unless a teaching lab asks for it. It is a third surface
  for logic that is not yet right on the first.
- **`validate` as a separate command.** It is `simulate` that stops early.
- **The nine-command surface** → one command, flags on it.
- **KEGG** — already gated pending a licence, and the substrate lookup it
  provided should be replaced by the confirmed parse in §4.1.

---

## 6. How we will know it worked

Not "tests pass". Falsifiable claims, tested by running the product:

1. **A student reaches a correct, cited number in one command**, from a
   standing start, with no flag documentation. Measured by running it.
2. **Every refusal names a next step that works** — extract the suggested
   command, run it, require progress. The test pattern from ADR 0116, applied
   to every refusal rather than one.
3. **No number reaches a screen without a source or an explicit
   "you supplied this".** Machine-checked.
4. **One real teaching lab runs one real exercise.** Nothing above matters
   until this happens, and it is the only item on this list that code cannot
   satisfy.

---

## 7. What I am least sure about

Recorded so it can be challenged rather than discovered later.

- **Cutting to one domain may be wrong** if the fundraising story depends on
  breadth. That is a business call, not a technical one. My view: breadth
  that does not work is worse evidence than depth that does.
- **The plain-language parse may be too fragile.** §4.1 rests on parsing a
  sentence well enough to propose a system. It is a suggestion the user
  confirms, so a bad parse is visible rather than dangerous — but if it is
  wrong more than occasionally, the feature is noise.
- ~~**I have not read the professors' emails directly.**~~ **Resolved
  2026-08-18: read in full, and §2 was wrong.** Three errors, all in the
  same direction — the paraphrase was more favourable to what Terrium had
  already built than the sources were:
  1. Bakker's ensemble was recorded as "declined, and should stay declined".
     Sauro, shown all three options, called it *"the right way to do it"*,
     and the reply sent back promised to build it.
  2. Her axis weighting was recorded as "asked for and unanswered". She
     answered it in the defining sentence: the scores *are* the weights, and
     they weight the sampling.
  3. Katz — the one correspondent who rejects the premise — was absent
     entirely.

  The lesson is not "read the primary sources", which everyone already
  knows. It is that **a summary of criticism drifts toward the summariser**,
  and nothing in a paraphrase chain can detect it. The quotes are now inline
  above so a reader can check them without a mailbox.

- **Jeske's concrete recommendations are still not all taken**, and they are
  specific enough to be checked off:
  - *Bulk CSV download over SOAP* — she gave the exact URLs and the reason
    (she is building a REST API; SOAP would be double work by year end).
    Terrium still scrapes per-query HTML.
  - *Check the organisms are closely related enough* — "two different
    mammals instead of a bacterium and a human". §4.3 advertises
    `--allow-cross-species  relatedness checked`; whether the check is real
    relatedness or a lineage string comparison needs verifying before that
    line is left standing.
  - *SABIO-RK* — recommended as a second source, unexamined.
- **"All of the above" may still be too much.** §1 orders the audiences, but
  ordering is a promise about sequencing that is easy to make and hard to
  keep.

---

## 8. Next

This document is the deliverable. It is deliberately not accompanied by code,
because the failure being corrected is code written before the shape was
agreed.

The build order, once §1–§5 survive review:

1. §4.2 — one answer shape, applied to the existing MM path
2. §4.3 — one refusal shape, applied to every refusal
3. §4.1 — the single command with confirm-don't-infer
4. §5 — the deletions
5. §4.5 — collapse the three surfaces onto one resolver

Each step verified by running the product, not by the suite going green.
