/**
 * Deterministic disease-name matching for the SIR domain, mirroring
 * enzymes.ts's matchEnzyme() shape for the MM domains.
 *
 * Deliberately narrow: only diseases with a verified, single-source (R0,
 * infectious period) golden tuple in Tests/epidemiology_resolver.py's
 * `_DISEASE_REGISTRY` are listed here. Adding an entry here without a
 * matching registry entry would let a query "resolve" a disease name that
 * then fails at the literature-lookup step anyway -- listing only the
 * genuinely resolvable set keeps the two in lockstep. See ADR 0017 for why
 * only COVID-19 is registered so far (measles and influenza were checked
 * and rejected for lacking a compatible-methodology source pair).
 */
export interface DiseaseEntry {
  pattern: RegExp;
  diseaseName: string;
}

export const DISEASES: DiseaseEntry[] = [
  {
    pattern: /covid-?19|covid|sars-cov-2|coronavirus/i,
    diseaseName: "covid-19",
  },
];

export function matchDisease(query: string): DiseaseEntry | undefined {
  const lower = query.toLowerCase();
  for (const entry of DISEASES) {
    if (entry.pattern.test(lower)) {
      return entry;
    }
  }
  return undefined;
}
