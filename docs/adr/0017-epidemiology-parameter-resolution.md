# ADR 0017: Epidemiology parameters (R0, infectious period) are resolved from a hand-curated registry, not yet wired to RESOLVABLE_FIELDS

**Status:** Accepted

**Date:** 2026-08-08

**Relates to:** ADR 0012 / 0013 (kcat → Vmax: the same shape of "resolved but
not yet reachable" staging), ADR 0003 (shared plausibility bounds)

## Context

Every literature-resolvable field in Terrium so far (`km`, `ki`,
`mutation_rate`) is backed by a queryable source: BRENDA for enzyme
kinetics, stdpopsim for population genetics. Both let a resolver take a
name (enzyme, organism) and look up a value programmatically, with the
underlying database doing the curation.

No equivalent exists for epidemiological parameters. There is no keyless,
programmatically queryable database mapping disease name → (R0, infectious
period) the way BRENDA maps EC number → Km rows. Building `RESOLVABLE_FIELDS`
support for the SIR/SEIR domains therefore means a different kind of
sourcing: hand-verified golden tuples, pulled directly from peer-reviewed
papers via PubMed, the same way a BRENDA fixture's golden values are
hand-verified against a captured real page -- just without a live query
path behind them.

This surfaced a subtler problem while researching real values. `simulate_sir`
takes `beta` and `gamma` directly; the literature reports `R0` and some
notion of "infectious period," and `validate_sir_params` already defines
`R0 = beta / gamma` internally. Converting a resolved R0 into (beta, gamma)
is arithmetic once both quantities are in hand -- structurally identical to
ADR 0013's `Vmax = kcat * [E]0` bridge.

The part that is *not* identical to kcat: kcat → Vmax was blocked because
`[E]0` is a property of an experiment, unrecoverable from literature at all.
R0 and infectious period are both intrinsic disease properties -- in
principle both resolvable. The actual difficulty was methodological: R0 and
"infectious period" are estimated by different studies using different
model structures (two-compartment SIR vs. SEIR-style latent/infectious
decomposition, different serial-interval definitions), and pairing a
systematic review's R0 with an unrelated paper's infectious-period estimate
risks silently combining incompatible assumptions into a beta/gamma that
neither source actually supports.

Concretely, during this work:

- Guerra et al. (2017), *Lancet Infect Dis* 17(12):e420-e428, DOI
  [10.1016/S1473-3099(17)30307-9](https://doi.org/10.1016/S1473-3099(17)30307-9),
  PMID 28757186 -- the standard measles R0 systematic review -- explicitly
  found that "R0 estimates vary more than the often cited range of 12-18"
  and reports medians stratified by covariates, not one clean number in the
  abstract; the paper is not open-access, so the stratified table could not
  be pulled.
- Biggerstaff et al. (2014), *BMC Infect Dis* 14:480, DOI
  [10.1186/1471-2334-14-480](https://doi.org/10.1186/1471-2334-14-480),
  PMID 25186370, gives a clean point estimate for seasonal influenza (median
  R0 = 1.28, IQR 1.19-1.37), but the infectious-period paper found alongside
  it (Cori et al. 2012, PMID 22939310) decomposes duration into a 1.6-day
  latent stage plus a 1.0-day infectious stage for an SEIR-style model --
  not the same quantity a simple-SIR R0 estimate implicitly assumes.

Neither pairing was used. Inventing a matched pair by picking a
plausible-sounding number for the missing half would be exactly the
fabricated-precision failure ADR 0012 refused to commit for enzyme
concentration.

## Decision

**Disease parameters are resolved only when R0 and infectious period come
from the same paper (or explicitly compatible methodology), and the
registry starts with exactly one verified entry.**

Concretely:

1. `Tests/epidemiology_resolver.py::resolve_disease_parameters(disease)`
   returns a hand-curated `EpidemiologyResult` — found=True only for
   diseases in `_DISEASE_REGISTRY`, each entry carrying its PMID, DOI, and
   full citation for *both* r0 and infectious_period_days together.
2. The sole registered entry: **COVID-19 (SARS-CoV-2, ancestral strain)**,
   R0 = 3.14 (95% CI 2.69-3.59), mean serial interval = 5.45 days (95% CI
   4.23-6.66), both from Hussein et al. (2021), *Ann Surg* 273(3):416-423,
   DOI [10.1097/SLA.0000000000004400](https://doi.org/10.1097/SLA.0000000000004400),
   PMID 33214421 — a single 39-study meta-analysis reporting both
   quantities together, so no cross-paper mismatch is possible.
3. `Tellurium/core/validation.py::beta_gamma_from_r0(r0, infectious_period_days)`
   does the arithmetic bridge (`gamma = 1/infectious_period_days`,
   `beta = r0 * gamma`), returning `(beta, gamma, ParameterValidation)`.
   Impossible inputs (non-finite, non-positive) are rejected here; an
   implausible resulting R0 is left to `validate_sir_params`'s existing
   `R0_IMPLAUSIBLE_ABOVE` flag, avoiding two thresholds that could drift
   apart — the same layering `vmax_from_kcat` uses for the enzyme/Km ratio.
4. `RESOLVABLE_FIELDS` in `provenance.ts` is **not** touched by this ADR.
   Wiring disease-name resolution through the API (Python bridge → TS →
   `RESOLVABLE_FIELDS.sir`) is deliberately deferred to a follow-up ADR,
   exactly as ADR 0012 stopped at "resolved and tested" before ADR 0013
   did the runner wiring for kcat. This keeps the two questions —"is this
   citation real and internally consistent" and "should the API expose
   it" — decided separately.

### The serial-interval-as-infectious-period simplification, named explicitly

`infectious_period_days` here is a mean **serial interval** (time between
symptom onset in successive cases), not a virologically-measured shedding
duration. For a two-compartment SIR model with no separate exposed/latent
stage, the serial interval *is* the standard proxy for the model's
characteristic generation time (1/gamma) — this is not a shortcut invented
for Terrium, it is the conventional simplification any introductory SIR
model makes in the absence of an E compartment. `EpidemiologyResult` carries
this in `infectious_period_measure` explicitly rather than leaving a caller
to assume it means something more precise than it does.

### Why measles and influenza are not registered yet

Both are real, extremely well-studied diseases. Neither has a single source
(or a pair of sources using compatible methodology) that this pass could
verify cleanly — see the two rejected pairings above. Adding either later
requires either finding a matched-methodology source pair or accepting an
explicitly-flagged cross-study composite (mirroring BRENDA's
`cross_species_flag` tier) — a decision for a future ADR, not a default
taken here.

## Consequences

**Easier.** A resolved (R0, infectious period) pair can now produce a
runnable SIR simulation via `beta_gamma_from_r0`, verified end-to-end
against the independently-derivable peak condition
`S(t_peak) = N / R0` (see `Tellurium/tests/test_beta_gamma_from_r0.py`),
not against the engine's own output. Registering a new disease later is
additive — nothing built here needs revisiting.

**Harder.** A query naming a disease outside the one-entry registry gets
`found=False`, same as any other resolver's genuine gap — not a fabricated
number. Wiring this through the API surface still requires the same rigor
Stage 5 gave `km`: a Python-bridge quantity dispatch, a TS-side contract
test, and only then a `RESOLVABLE_FIELDS` entry.

**Unchanged.** `simulate_sir`'s signature, every existing SIR/SEIR golden
trajectory, and `RESOLVABLE_FIELDS` itself.

## Verification

- 15 tests in `Tellurium/tests/test_beta_gamma_from_r0.py`: arithmetic
  correctness, Rule 2's impossible/implausible distinction (mirroring
  `vmax_from_kcat`'s), and an end-to-end check against the SIR peak
  condition `S(t_peak) = N/R0` using the real Hussein et al. values —
  mutation-tested by replacing `beta = r0 * gamma` with `beta = r0 + gamma`
  and confirming 4 of the 15 tests fail, including the peak-condition
  check, then reverting.
- 11 tests in `Tests/test_epidemiology_resolver.py`: known-disease
  resolution, citation completeness, name/alias normalisation, and —
  the regression this ADR exists to prevent — that `measles` and
  `influenza`, both real diseases, correctly return `found=False` rather
  than a fabricated value.

## References

- **Hussein, M. et al. (2021).** Meta-analysis on Serial Intervals and
  Reproductive Rates for SARS-CoV-2. *Annals of Surgery* 273(3), 416–423.
  DOI [10.1097/SLA.0000000000004400](https://doi.org/10.1097/SLA.0000000000004400).
  PMID 33214421. Pooled R0 = 3.14 (95% CI 2.69–3.59); mean serial interval
  = 5.45 days (95% CI 4.23–6.66); 39 studies, searched through 2020-05-10.
- **Guerra, F.M. et al. (2017).** The basic reproduction number (R0) of
  measles: a systematic review. *Lancet Infectious Diseases* 17(12),
  e420–e428. DOI [10.1016/S1473-3099(17)30307-9](https://doi.org/10.1016/S1473-3099(17)30307-9).
  PMID 28757186. Cited here as the reason measles is *not* yet registered
  — no single clean point estimate was extractable without full-text access.
- **Biggerstaff, M. et al. (2014).** Estimates of the reproduction number
  for seasonal, pandemic, and zoonotic influenza: a systematic review of
  the literature. *BMC Infectious Diseases* 14, 480. DOI
  [10.1186/1471-2334-14-480](https://doi.org/10.1186/1471-2334-14-480).
  PMID 25186370. Median seasonal-influenza R0 = 1.28 (IQR 1.19–1.37).
  Cited as the reason influenza is not yet registered — no compatible
  infectious-period source was found alongside it.
- **ADR 0012 / 0013** — the kcat → Vmax precedent this staging follows.
- **ADR 0003** — plausibility bounds as a cross-layer contract; the same
  discipline applies to `R0_IMPLAUSIBLE_ABOVE`.
