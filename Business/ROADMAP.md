# Roadmap

The phase structure from the pitch deck, kept here so it's checkable against
actual progress instead of only living in a .pptx nobody re-opens.

## Phase 0 -- Foundation (mostly done)

- [x] Literature layer: BRENDA/KEGG/PubMed scraping, organism resolution,
      citation formatting (124 tests)
- [x] Simulation engine: antimony/roadrunner pipeline, verified against
      exact closed-form solutions and an independent solver
- [x] Two ODE domains live: Michaelis-Menten enzyme kinetics, SIR/SEIR
      epidemiology
- [x] Third domain live: PCR amplification (discrete-cycle, exact
      closed-form growth -- no solver needed for this one)
- [x] Reproducible dev environment: Makefile, CI, Docker/devcontainer sandbox
- [x] Landing page with a real interactive simulator (not a mockup)
- [ ] Domain/trademark check (terrium.ai/.dev/.io, USPTO TESS) -- flagged
      earlier as a Week 1 item, status unconfirmed
- [ ] Backend/infra hire finalized -- in progress, not closed

## Phase 1 -- Validation

- [ ] First real pilot: a professor or course willing to actually use
      Terrium with students, not just review it
- [ ] Direct feedback loop from real student use -- what breaks, what's
      confusing, what's actually valuable vs. what we assumed was valuable
- [ ] Funding to cover Phase 0-1 runway (see `FUNDRAISING_TRACKER.md`)

## Phase 2 -- Expand domains

- [ ] Remaining three domains: Monte Carlo simulation, population genetics,
      molecular dynamics setup -- each needs the same treatment PCR just
      got: real engine code, a real test suite, mutation-tested, not a
      placeholder "planned" tag on the landing page
- [ ] Multiple pilot courses/institutions, not just one

## Phase 3 -- Scale

- [ ] Institutional adoption beyond individual pilot courses
- [ ] Sustainable pricing model actually validated by paying customers, not
      just the pricing-tier draft in the pitch deck

## A note on scope discipline

Phase 2's new domains are deliberately not started yet -- funding and the
backend hire are still open, and building three more domains before either
of those is resolved would be effort spent on the wrong bottleneck. This
file exists so that's a visible, deliberate choice, not something that just
quietly didn't happen.
