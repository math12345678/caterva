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

- [x] Monte Carlo pi estimation -- real engine code, verified against the
      CLT error rate, mutation-tested
- [x] Population genetics -- Wright-Fisher (neutral drift, selection,
      structured populations, two-locus with recombination), verified
      against Kimura's fixation probability and the exact Markov-chain
      layer, mutation-tested
- [x] Molecular dynamics -- Lennard-Jones cluster (velocity Verlet),
      verified against energy/momentum conservation and published
      global-minimum energies (Hoare & Pal 1971), mutation-tested
- [x] Two further domains beyond the original Phase 2 scope also shipped:
      Gillespie SSA (first-order decay and bimolecular association),
      verified against exact closed forms and hand-verified golden
      trajectories
- [ ] Multiple pilot courses/institutions, not just one -- unchanged from
      Phase 1; expanding domains does not substitute for this

## Phase 3 -- Scale

- [ ] Institutional adoption beyond individual pilot courses
- [ ] Sustainable pricing model actually validated by paying customers, not
      just the pricing-tier draft in the pitch deck

## A note on scope discipline

Phase 2's domains got built anyway, ahead of funding and the backend hire
closing -- this file previously said that was a deliberate deferral, and by
the time this line was corrected (2026-08-09) that was no longer true and
had not been for a while. The actual bottleneck now is unchanged from
Phase 1: no pilot course, no real student use, funding still open. Domain
count was never the constraint; validation is. Building more domains
without a pilot to put them in front of remains effort spent on the wrong
bottleneck -- the correction here is to the *status*, not the underlying
principle.
