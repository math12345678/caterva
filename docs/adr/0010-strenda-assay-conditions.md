# ADR 0010: A resolved kinetic constant without assay conditions cannot be `verified`

**Status:** Accepted

## Context

Stage 5 built the provenance contract: per-parameter `origin`
(`resolved` / `user` / `default`), locatable citations, and a two-tier
`citationStatus` (`verified` for an exact organism-and-substrate match from a
primary source, `flagged` for cross-species or inferred).

That contract answers *where did this number come from*. It does not answer
*under what conditions was it measured*, and for enzyme kinetic constants
those are not separable questions.

**Km is not a property of an enzyme.** It is a property of an enzyme measured
under specific conditions, and it varies with them. The same enzyme and
substrate yield different Km values at different pH and temperature. A Km
reported without them cannot be reproduced by another laboratory and cannot be
compared against another laboratory's figure.

The community standard states this as a hard requirement:

> "The temperature, pH and pressure (if other than atmospheric) of the assay
> **must** always be included, even if previously published."
>
> — STRENDA Guidelines v1.4.0, Beilstein-Institut

STRENDA (Standards for Reporting Enzymology Data) is registered in
FAIRsharing and recommended to authors by more than 60 international
biochemistry journals. It is the reporting standard for exactly the data
Caterva resolves.

Two further facts made this a defect rather than a limitation:

1. **The data was available and being discarded.** BRENDA — the source
   Caterva resolves from — stores pH optimum, temperature optimum, and an
   experimental-conditions commentary alongside every Km entry (Schomburg
   *et al.*, *Nucleic Acids Research*). Caterva's `ParameterProvenance` had no
   field for any of them.
2. **The value was still being labelled `verified`.** So Caterva was
   presenting, as independently checked, a number that by the standard
   governing its own source was incompletely reported.

This is the FAIR principle R1.2 — *data are associated with detailed
provenance* (Wilkinson *et al.* 2016) — applied to the one field where
Caterva's product claim actually rests.

## Decision

**Assay conditions are part of provenance, and their absence degrades the
citation tier rather than being silently tolerated.**

1. `ParameterProvenance` gains `assayConditions?: AssayConditions` — `ph`,
   `temperatureC`, and an optional `buffer`.
2. It gains `strendaStatus?: "complete" | "incomplete"`, set only on resolved
   parameters that are kinetic constants.
3. `STRENDA_GOVERNED_FIELDS` names the parameters the standard applies to:
   `km`, `vmax`, `kcat`, `ki`. Only `km` currently has a lookup path; the
   others are listed so that adding one cannot silently bypass the
   requirement. **The set states the rule, not the implementation.**
4. **A resolved kinetic constant with incomplete assay conditions cannot hold
   `citationStatus: "verified"`.** It degrades to `flagged`, carrying a note
   naming exactly which mandatory field is missing.
5. `buildResolvedKineticProvenance()` applies the degradation in one place, so
   no call site can forget it. It degrades only — a cross-species match with
   perfect conditions is still cross-species; completeness cannot buy a tier.

`pressure` is deliberately omitted. STRENDA requires it only when other than
atmospheric, and no Caterva path resolves a non-atmospheric measurement.
Adding it later is a field addition, not a contract change.

## Why degrade rather than reject

Rejecting would be the wrong shape and would lose real information. The value
may well be correct; what is missing is the ability to *check* it. That is
precisely the distinction Rule 2 draws between impossible and implausible,
carried over from physics to reporting completeness: the simulation still
runs, the warning travels with it, and nothing is silently accepted.

Degrading also keeps the failure visible in the product rather than in a log.
A student sees `flagged` and a reason; a rejected value would simply be
absent.

## Consequences

- Every currently-resolved Km degrades to `flagged` until an assay-conditions
  extraction path exists in the BRENDA client. **This is the honest state:**
  Caterva does not presently capture pH or temperature, so it cannot claim
  those values are verified. The status quo was not better — it was the same
  situation, labelled `verified`.
- `Tests/brenda_client.py` needs to extract pH and temperature from the
  commentary field. That work is scoped and not done here; this ADR
  establishes the contract the extraction will satisfy, so the extraction
  cannot land without wiring into it.
- Non-kinetic parameters are unaffected. The requirement is about enzyme
  kinetic constants, not every number in the system, and the validator
  enforces that boundary in both directions.
- A `strendaStatus` that contradicts its own `assayConditions` is a hard
  validation violation, not a warning. Self-inconsistent provenance is worse
  than absent provenance, for the same reason a fabricated citation is worse
  than no citation (Stage 4 Part 4).

## References

- **STRENDA Guidelines**, v1.4.0, Beilstein-Institut.
  <https://www.beilstein-strenda-db.org/strenda/public/guidelines.xhtml>
  Registered in FAIRsharing (FAIRsharing.8ntfwm); recommended by 60+
  biochemistry journals.
- **Wilkinson, M. D. *et al.* (2016).** The FAIR Guiding Principles for
  scientific data management and stewardship. *Scientific Data* **3**, 160018.
  DOI 10.1038/sdata.2016.18. Principle R1.2: data are associated with
  detailed provenance.
- **Schomburg, I. *et al.*** BRENDA, the enzyme database. *Nucleic Acids
  Research* — kinetic entries carry pH optimum, temperature optimum, and an
  experimental-conditions commentary.
