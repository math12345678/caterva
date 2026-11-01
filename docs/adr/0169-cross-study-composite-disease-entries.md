# ADR 0169: Influenza enters the disease registry as an explicitly-flagged cross-study composite; measles stays out, now with its refusal cited

**Status:** Accepted

**Date:** 2026-09-04

**Relates to:** ADR 0017 (which anticipated exactly this decision and
deferred it: "accepting an explicitly-flagged cross-study composite
(mirroring BRENDA's cross_species_flag tier) — a decision for a future
ADR"), ADR 0024 (the flagged-not-verified tier this mirrors), ADR 0020
(how registry entries reach beta/gamma).

## Context

The disease registry has held exactly one entry — COVID-19 — since ADR
0017, because its rule is strict: R0 and infectious period must come from
the same paper, and only Hussein et al. (2021) supplied both together.
Measles and influenza queries refuse with `disease_not_registered`.

ADR 0017 rejected two specific pairings and said why:

- **Measles**: Guerra et al. (2017) — the standard R0 systematic review —
  concludes that R0 estimates "vary more than the often cited range of
  12-18" and endorses no single value. No point estimate, no entry.
- **Influenza**: Biggerstaff et al. (2014) gives a clean R0 (median
  seasonal 1.28), but the infectious-period source found alongside it
  (Cori et al. 2012) measures an SEIR-style latent/infectious
  decomposition — a different quantity than a simple-SIR R0 assumes.

What was missing in 2026-08 was a *methodologically matched* second half.
That half exists, and was verified against its actual PubMed record on
2026-09-04 (all four abstracts re-fetched and read, not recalled):

- **Vink, Bootsma & Wallinga (2014)**, *Am J Epidemiol* 180(9):865-875,
  DOI [10.1093/aje/kwu209](https://doi.org/10.1093/aje/kwu209),
  PMID 25294601 — a systematic review that REANALYZED the underlying
  household-outbreak data with one common statistical method, reporting
  mean serial intervals: influenza A(H3N2) 2.2 days, influenza
  A(H1N1)pdm09 2.8 days, measles 11.7 days (and six other diseases).

Two facts make Vink the right pairing where Cori was not:

1. **It is the same quantity the registry already uses.** ADR 0017 names
   the COVID entry's `infectious_period_days` as a mean *serial interval*
   standing in for 1/gamma — the conventional two-compartment-SIR
   simplification. Vink reports serial intervals. Carrat et al. (2008)
   (mean shedding 4.80 days) was considered and rejected for this entry:
   shedding duration is a virological quantity, not the model's
   generation-time proxy, and influenza sheds for roughly twice its
   serial interval — the two halves would disagree by ~2x about what
   gamma means.
2. **One method across diseases.** Vink's values are mutually consistent
   by construction, so future entries drawing from it inherit the same
   definition instead of a new one per disease.

## Decision

**1. A second registry tier exists: the cross-study composite.** An entry
whose R0 and serial interval come from two different systematic reviews
may be registered if and only if:

- both halves are systematic reviews or meta-analyses (never single
  studies),
- the serial-interval half reports the same quantity the registry's
  convention requires (a mean serial interval, per ADR 0017),
- the entry is marked `cross_study_composite = True`, and
- the bridge emits `citationStatus: "flagged"` — NEVER `"verified"` —
  with a note naming both sources and the specific mismatch. This mirrors
  exactly how a cross-species BRENDA Km is admitted: usable, cited, and
  visibly weaker than a same-source value.

**2. Two influenza entries are registered under that tier:**

- **influenza A(H1N1)pdm09 (2009 pandemic)**: R0 = 1.46 (Biggerstaff
  2014, median of 78 estimates, IQR 1.30-1.70) + serial interval = 2.8
  days (Vink 2014). The two halves are STRAIN-MATCHED — both describe
  A(H1N1)pdm09 — so the only composite dimension is cross-study.
- **influenza (seasonal)**: R0 = 1.28 (Biggerstaff 2014, median of 47
  estimates, IQR 1.19-1.37) + serial interval = 2.2 days (Vink 2014,
  A(H3N2)). Composite on TWO axes, both named in the note: cross-study,
  and cross-strain (Biggerstaff's "seasonal" pools H3N2/H1N1/B; Vink's
  2.2 days is H3N2-specific). Registered anyway because seasonal
  influenza is the question a teaching lab actually asks, and H3N2 has
  dominated seasonal severity in most seasons — but the entry says so
  rather than hiding it.

Derived engine parameters go through the existing
`beta_gamma_from_r0` bridge unchanged:
pdm09: gamma = 1/2.8 ≈ 0.357, beta = 1.46 x gamma ≈ 0.521.
seasonal: gamma = 1/2.2 ≈ 0.455, beta = 1.28 x gamma ≈ 0.582.

**3. Measles remains unregistered — and its refusal now carries the
evidence.** The blocker was never the serial interval (Vink: 11.7 days);
it is that the best available R0 review concludes no single value is
defensible. The `disease_not_registered` refusal for measles cites
Guerra et al. (2017) explicitly: "not registered because the standard
systematic review found R0 varies too widely across settings (published
range spans roughly 1.4-770 across contexts) for one number to be
honest; supply beta and gamma for YOUR setting." A refusal that cites
why is the product's promise applied to its own gaps.

**4. Composites never upgrade silently.** If a future single paper
reports both halves for influenza, replacing the composite with a
same-source entry is a new ADR, and the flagged tier drops away with it.
Nothing in this ADR permits relaxing "flagged" to "verified" for a
composite.

## Consequences

**Easier.** "model a flu outbreak in a school of 800 with 2 infected over
90 days" resolves and runs, with two followable citations and a
provenance note stating exactly what was combined. Two of the twelve
measured headline questions that previously refused now run honestly.

**Harder.** The bridge and provenance layers must carry a per-entry
flagged status instead of assuming every registry hit is verified; tests
must pin that a composite can never surface as "verified".

**Unchanged.** COVID-19's entry and status; `beta_gamma_from_r0`;
`validate_sir_params`; the refusal path for every other unregistered
disease.

## Verification

- Registry tests: both influenza entries resolve with both citations and
  `cross_study_composite = True`; measles still returns `found=False`
  and its refusal text names Guerra 2017.
- Bridge tests: a composite entry reaches `parameterProvenance` as
  `citationStatus: "flagged"` with both sources in the note; mutation
  check — hard-coding `"verified"` for composites must fail the suite.
- Arithmetic: end-to-end SIR peak condition S(t_peak) = N/R0 for the
  pdm09 values, the same independent check ADR 0017 used for COVID.
- Citation truth: all four PMIDs (25186370, 25294601, 28757186,
  33214421) were re-fetched from PubMed on 2026-09-04 and the numbers
  above transcribed from the abstracts, not from memory or prior notes.

## References

- **Biggerstaff, M. et al. (2014).** Estimates of the reproduction number
  for seasonal, pandemic, and zoonotic influenza: a systematic review.
  *BMC Infect Dis* 14:480.
  DOI [10.1186/1471-2334-14-480](https://doi.org/10.1186/1471-2334-14-480).
  PMID 25186370. Median R: seasonal 1.28 (IQR 1.19-1.37); 2009 pandemic
  1.46 (IQR 1.30-1.70); 1918 1.80; 1957 1.65; 1968 1.80.
- **Vink, M.A., Bootsma, M.C.J., Wallinga, J. (2014).** Serial intervals
  of respiratory infectious diseases: a systematic review and analysis.
  *Am J Epidemiol* 180(9):865-875.
  DOI [10.1093/aje/kwu209](https://doi.org/10.1093/aje/kwu209).
  PMID 25294601. Mean serial intervals: influenza A(H3N2) 2.2 d,
  A(H1N1)pdm09 2.8 d, measles 11.7 d.
- **Guerra, F.M. et al. (2017).** The basic reproduction number (R0) of
  measles: a systematic review. *Lancet Infect Dis* 17(12):e420-e428.
  DOI [10.1016/S1473-3099(17)30307-9](https://doi.org/10.1016/S1473-3099(17)30307-9).
  PMID 28757186. Cited as the standing reason measles has no entry.
- **Carrat, F. et al. (2008).** Time lines of infection and disease in
  human influenza. *Am J Epidemiol* 167(7):775-785.
  DOI [10.1093/aje/kwm375](https://doi.org/10.1093/aje/kwm375).
  PMID 18230677. Considered for the influenza period and REJECTED:
  4.80 days of viral shedding is not a serial interval, and using it
  would redefine gamma mid-registry.
- **ADR 0017** — the rule this ADR extends, and the deferral it resolves.
