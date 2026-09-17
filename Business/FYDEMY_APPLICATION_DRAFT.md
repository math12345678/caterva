# Fydemy application — draft answers

Drafted from what's actually true in the repo and `Business/` docs.
Counts last reconciled against the repository on 2026-08-15 and kept true
by `scripts/check_investor_claims.py` -- this file is operational, not a
record, because somebody will paste these numbers into a real submission. Fields marked **[YOUR INPUT]** are personal, financial, or
judgment calls I'm not going to guess at — fill those in yourself. Everything
else is ready to copy in, but skim it first; it's your application, not mine.

---

## Founder

| Field | Answer |
|---|---|
| Founder name | Smyan Reddy |
| Your role | **[YOUR INPUT]** — CEO/Founder is the natural fit given `CAP_TABLE.md` lists you as "Product & Domain Lead," but pick the title you actually want on record |
| Founder email | reddy.uday@gmail.com |
| Primary decision-maker / contact | Smyan Reddy (you) |
| Phone / WhatsApp | **[YOUR INPUT]** — optional field |
| Number of founders | 2 (you + Shanmuka), plus one open backend/infra role not yet filled — see note below |
| Founder experience | **[YOUR INPUT]** — this needs your actual background/prior work, not something I can write for you |
| LinkedIn | **[YOUR INPUT]** |
| Full-time status | **[YOUR INPUT]** — is this full-time for you right now? |
| Product logo | Not built yet, optional |
| Pitch deck upload | You already have a 14-slide investor deck from earlier in this project — attach that, or provide the written brief below instead |

**Team members**: Shanmuka (AI/ML Lead, per `CAP_TABLE.md`). The backend/infra
role is explicitly open — `CAP_TABLE.md` says not to set an equity number for
it until someone's actually confirmed, so I'd leave it off the team list here
rather than list a placeholder person.

---

## Company

| Field | Answer |
|---|---|
| Company name | Terrium |
| Company website | **[YOUR INPUT]** — `ROADMAP.md` flags the domain check (terrium.ai/.dev/.io) as unconfirmed status; don't put a URL here unless you've actually secured one |
| Product stage | **Prototype** (not "Idea") — you have a working simulation engine, 4,279 passing tests, a live interactive landing page with a real end-to-end simulator, not a mockup |
| Sector | Education / EdTech (closest fit if "SaaS/B2B" is the only option, since the buyer is institutional) |
| Subsector | Scientific computing / research tools |
| Operating country | **[YOUR INPUT]** |
| Operating city | **[YOUR INPUT]** |
| Legal status | **Not Incorporated** — confirmed by `CAP_TABLE.md`: "no entity exists yet" |

---

## Ownership

`CAP_TABLE.md` is explicit that every number here is currently `TBD` —
there's no entity, so there are no real shares yet. I'm not going to fill in
percentages that don't exist. **[YOUR INPUT]** — either leave these at 0 and
explain in the brief that equity split isn't finalized, or resolve the open
questions in `CAP_TABLE.md` first (founder split basis, vesting, backend
hire's equity tier, advisor equity) so the numbers you enter are real.

What can you share today? → Honestly, probably **"None"** or **"Concise
written brief only"** given the cap table's current state — a form entry look
more credible than a guessed split investors will ask about anyway.

---

## Concise written brief

> Terrium is scientific computing for teaching labs. Students ask a question
> in plain language — Terrium resolves the real parameters from the
> literature (BRENDA/KEGG/PubMed), runs the simulation, and shows its work,
> with every number traceable to an independently-checked citation. Three
> domains are live today (enzyme kinetics, SIR/SEIR epidemiology, PCR
> amplification), each verified against exact closed-form solutions or an
> independent solver — not just "looks right." Three more (Monte Carlo,
> population genetics, molecular dynamics) are scoped but deliberately not
> started, pending funding and a backend hire. We've built the full
> foundation — engine, test suite, CI, landing page with a real interactive
> simulator — and are now looking for our first real pilot: a professor or
> course willing to actually use it with students.

## Regulatory dependency

None.

## One-line product description

> Terrium turns a plain-language science question into a verified,
> citable simulation — for teaching labs that can't afford to fake data.

## Problem statement

> Students and instructors running simulations in teaching labs either use
> tools that are too slow/complex to set up for a single class exercise, or
> fall back on made-up parameter values because looking up the real
> literature values is tedious. Terrium removes both frictions: ask in plain
> language, get a real simulation with real, cited parameters.

## Who pays

Institutions (departments, course budgets) — not individual students. This
matches the pricing-tier structure already drafted in the pitch deck.

## Pricing model

Subscription — institutional/course licensing, per the pricing tiers already
drafted in your pitch deck. **[YOUR INPUT]** if the form wants exact tier
numbers; those exist in the deck but I'd confirm they're still current before
quoting them here.

## Gross margin / other unit economics

**[YOUR INPUT]** — no real revenue yet, so there's nothing to compute a
margin from honestly. Leave blank or state "pre-revenue" rather than
estimating.

## Direct competition / alternatives

> General-purpose simulation platforms (MATLAB, COPASI, raw
> roadrunner/antimony) require setup expertise most teaching labs don't have
> time for. The realistic alternative most instructors reach for today is
> manually-entered or made-up parameter values — Terrium's actual
> competition is "just wing it," not another polished product in this exact
> niche.

## Why now / why this team

> Simulation tools have existed for decades, but none of them close the loop
> from "plain-language question" to "cited, verified parameters" to
> "running simulation" in one step built specifically for a classroom
> setting rather than a research lab. **[YOUR INPUT]** — the "why this team"
> half needs your and Shanmuka's actual backgrounds, not something I can
> write credibly for you.

---

## Validation

Being direct about where things actually stand, per `ROADMAP.md` — Phase 1
(first real pilot) hasn't started yet:

| Field | Answer |
|---|---|
| Customer segment | Instructors/departments running teaching labs in biology, chemistry, epidemiology courses |
| Customer acquisition channel | **[YOUR INPUT]** — not yet tested |
| Customer interviews (count) | 0, unless you've had informal conversations not tracked in the repo — **[YOUR INPUT]** if so |
| What you learned from interviews | **[YOUR INPUT]** |
| Active pilots | 0 |
| LOIs / design partners | 0 |
| Active users | 0 |
| Paying customers | 0 |
| Retention | N/A — no users yet |

## Most important metric

| Field | Answer |
|---|---|
| Metric | Verified test coverage / engine correctness (4,279 passing tests, each simulation domain checked against an exact closed-form solution or independent solver) |
| Value | 4,279 tests passing, 0 failing, across 15 live simulation domains |
| Why this is the most important metric | Terrium is pre-pilot — there's no user or revenue metric yet that would honestly represent traction. The metric that actually matters right now is whether the product does what it claims (real, correct, citable simulations), because that's the entire value proposition. Everything else (pilots, revenue) is Phase 1, which hasn't started. |

## MRR

$0 — pre-revenue, confirmed by `FUNDRAISING_TRACKER.md` (no closed funding, applications still "in progress" / "applied").

---

## Fundraising

| Field | Answer |
|---|---|
| Company stage | Bootstrapped |
| Currently raising | Yes — small checks/non-dilutive support (see notes) |
| Capital raised to date | $0 |
| Capital raised currency | USD |
| Prior investors / grants | None closed yet. In flight per `FUNDRAISING_TRACKER.md`: Kickstart Global (KS26B, fellowship not capital, application in progress), LvlUp Ventures (~$2,000 ask, applied, awaiting response), SF Startup Labs (has a $2,400 fee — you flagged this needs your explicit go-ahead before paying it, unconfirmed submitted) |

---

## Priority ask (next 30 days)

| Field | Answer |
|---|---|
| 30-day goal | **[YOUR INPUT]** — suggest: secure a first pilot conversation with an instructor, since that's the actual Phase 1 blocker per `ROADMAP.md` |
| Key blockers | Funding for Phase 0-1 runway (compute/API costs, validation outreach — this is exactly what the $2K LvlUp ask was scoped for) and the still-open backend/infra hire |
| Target milestone | First real pilot: a professor or course actually using Terrium with students |
| Priority counterpart type | Given the actual blocker is "no pilot yet," **Advisors/mentors or a specific instructor introduction** may matter more right now than capital — worth considering over "Angels/VCs/Investors" as the top choice, though $2K-scale funding is also live |
| Geography | **[YOUR INPUT]** |
| Specific counterpart profile | A science instructor (biology/chemistry/epidemiology) at a university willing to pilot a new tool with their students |
| One desired outcome from an introduction | A committed pilot: one course, one semester, real student use, real feedback |

---

## Consent & sharing

Both checkboxes are your call, not mine — read what they actually commit you
to (private Fydemy review vs. external sharing with Boardy/other
counterparts) before checking either.

---

### What I did not fill in, and why

Personal identity (email verified, phone/LinkedIn/full-time status not on
file), equity percentages (cap table is genuinely undecided), specific
pricing tier dollar amounts (exists in your deck but I didn't re-verify it's
current), geography/city, and "why this team" background — these all need
either information I don't have or a decision that's actually yours to make,
not something I should fabricate to make the form look more complete than
your company actually is right now.
