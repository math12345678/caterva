/**
 * Reading the organism the user actually named.
 *
 * WHAT THIS FIXES
 *
 * `extractEntitiesFromQuery` never looked at the query for an organism.
 * It used the `enzymes.ts` table's hardcoded organism, or the literal
 * string "Homo sapiens" for a guessed enzyme name. Measured before this
 * module existed:
 *
 *   "simulate hexokinase in E. coli with glucose ..."
 *     -> km 6 mM, organism "Homo sapiens",
 *        source "brenda_exact", citationStatus "verified"
 *
 *   "simulate hexokinase in Saccharomyces cerevisiae ..."
 *     -> the identical human value, also "brenda_exact" / "verified"
 *
 * The named organism was discarded, and the human value came back badged
 * as an EXACT MATCH -- the highest confidence tier this system has -- for
 * a species nobody asked about.
 *
 * That is strictly worse than the case ADR 0024 was written for. A
 * genuine cross-species value is withheld unless the caller opts in, and
 * arrives "flagged" with the organism named, because "kinetic parameters
 * are species-specific" is the premise of that whole apparatus. Here the
 * apparatus never fired: from its point of view the requested organism
 * matched, because the request had been silently rewritten to match.
 *
 * A teaching lab studying E. coli or yeast metabolism -- which is most of
 * them -- got human numbers under the product's strongest badge.
 *
 * WHAT THIS DELIBERATELY DOES NOT DO
 *
 * It does not guess. A query naming no organism still falls back to the
 * enzyme table's own organism, which is a documented default rather than
 * an inference from the query text. This module only reads what is
 * explicitly there, in the same spirit as statedQuantities.ts.
 *
 * Once the organism is passed through honestly, the existing machinery
 * does the right thing on its own: BRENDA either has a value for that
 * species (exact), or has one for another species (withheld unless
 * `allowCrossSpecies`, and flagged when used), or has nothing (an honest
 * refusal). None of those paths needed changing -- they were simply
 * unreachable.
 */

export interface OrganismEntry {
  pattern: RegExp;
  /** The binomial BRENDA indexes by. */
  organism: string;
}

/**
 * Deliberately short and explicit, like enzymes.ts and diseases.ts.
 *
 * Every pattern is anchored on a word boundary. "coli" is not matched
 * bare -- it would hit "colitis" and any word ending in it -- and the
 * common-name aliases are only those a lab would actually type.
 */
export const ORGANISMS: OrganismEntry[] = [
  {
    pattern: /\bE\.?\s?coli\b|\bEscherichia coli\b/i,
    organism: "Escherichia coli",
  },
  {
    pattern: /\bS\.?\s?cerevisiae\b|\bSaccharomyces cerevisiae\b|\b(?:budding\s+)?yeast\b|\bbaker'?s yeast\b/i,
    organism: "Saccharomyces cerevisiae",
  },
  {
    pattern: /\bHomo sapiens\b|\bhuman\b/i,
    organism: "Homo sapiens",
  },
  {
    pattern: /\bMus musculus\b|\bmouse\b|\bmurine\b/i,
    organism: "Mus musculus",
  },
  {
    pattern: /\bRattus norvegicus\b|\brat\b/i,
    organism: "Rattus norvegicus",
  },
  {
    pattern: /\bB\.?\s?subtilis\b|\bBacillus subtilis\b/i,
    organism: "Bacillus subtilis",
  },
  {
    pattern: /\bD\.?\s?melanogaster\b|\bDrosophila\b|\bfruit fly\b/i,
    organism: "Drosophila melanogaster",
  },
  {
    pattern: /\bC\.?\s?elegans\b|\bCaenorhabditis elegans\b/i,
    organism: "Caenorhabditis elegans",
  },
  {
    pattern: /\bA\.?\s?thaliana\b|\bArabidopsis\b/i,
    organism: "Arabidopsis thaliana",
  },
  {
    pattern: /\bDanio rerio\b|\bzebrafish\b/i,
    organism: "Danio rerio",
  },
  {
    pattern: /\bP\.?\s?aeruginosa\b|\bPseudomonas aeruginosa\b/i,
    organism: "Pseudomonas aeruginosa",
  },
  {
    pattern: /\bM\.?\s?tuberculosis\b|\bMycobacterium tuberculosis\b/i,
    organism: "Mycobacterium tuberculosis",
  },
];

/**
 * The organism named in a query, or undefined when none is.
 *
 * `undefined` is a real answer, not a failure: the caller keeps its
 * existing default rather than being handed a guess.
 */
export function matchOrganism(query: string): string | undefined {
  for (const entry of ORGANISMS) {
    if (entry.pattern.test(query)) return entry.organism;
  }
  return undefined;
}
