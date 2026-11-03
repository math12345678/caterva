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
 * Deliberately short and explicit, like enzymes.ts.
 *
 * Every pattern is anchored on a word boundary. "coli" is not matched
 * bare -- it would hit "colitis" and any word ending in it -- and the
 * common-name aliases are only those a lab would actually type.
 *
 * PLURALS ARE TYPED. `\bhuman\b` did not match "in humans", the way most
 * people phrase it, because the boundary falls after the "s". Measured
 * 2026-11-02: "hexokinase with glucose in humans" was treated as naming
 * no organism, so the Km arrived with "assumed: organism = Homo sapiens
 * ... chosen for you" -- telling the student a choice they had written
 * out had been made for them. "mice" and "rats" failed the same way. The
 * common names below are the ones BRENDA's own organism column is full
 * of for the classic purified enzymes (rabbit muscle, bovine heart,
 * porcine pancreas, chicken liver), each mapped to the binomial BRENDA
 * indexes by; a name not listed here still falls back to the documented
 * default rather than a guess.
 */
export const ORGANISMS: OrganismEntry[] = [
  {
    pattern: /\bE\.?\s?coli\b|\bEscherichia coli\b/i,
    organism: "Escherichia coli",
  },
  {
    pattern: /\bS\.?\s?cerevisiae\b|\bSaccharomyces cerevisiae\b|\b(?:budding\s+)?yeasts?\b|\bbaker'?s yeast\b/i,
    organism: "Saccharomyces cerevisiae",
  },
  {
    pattern: /\bHomo sapiens\b|\bhumans?\b/i,
    organism: "Homo sapiens",
  },
  {
    pattern: /\bMus musculus\b|\bmouse\b|\bmice\b|\bmurine\b/i,
    organism: "Mus musculus",
  },
  {
    pattern: /\bRattus norvegicus\b|\brats?\b/i,
    organism: "Rattus norvegicus",
  },
  {
    pattern: /\bB\.?\s?subtilis\b|\bBacillus subtilis\b/i,
    organism: "Bacillus subtilis",
  },
  {
    pattern: /\bD\.?\s?melanogaster\b|\bDrosophila\b|\bfruit fl(?:y|ies)\b/i,
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
    pattern: /\bDanio rerio\b|\bzebrafish(?:es)?\b/i,
    organism: "Danio rerio",
  },
  {
    pattern: /\bBos taurus\b|\bbovine\b|\bcows?\b|\bcattle\b/i,
    organism: "Bos taurus",
  },
  {
    pattern: /\bSus scrofa\b|\bporcine\b|\bpigs?\b|\bswine\b/i,
    organism: "Sus scrofa",
  },
  {
    pattern: /\bOryctolagus cuniculus\b|\brabbits?\b/i,
    organism: "Oryctolagus cuniculus",
  },
  {
    pattern: /\bGallus gallus\b|\bchickens?\b/i,
    organism: "Gallus gallus",
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

/**
 * The query with every organism phrase it names blanked out.
 *
 * For the enzyme-name guess, which used to hand the whole leftover phrase
 * to UniProt: "glucokinase glucose rat" was looked up as an enzyme called
 * "glucokinase glucose rat", matched nothing, and the refusal blamed the
 * NAME. The organism is still read by `matchOrganism` from the original
 * text; this only stops it being read twice, once as a species and once
 * as part of an enzyme's name.
 */
export function stripOrganisms(query: string): string {
  let out = query;
  for (const entry of ORGANISMS) {
    out = out.replace(new RegExp(entry.pattern.source, "gi"), " ");
  }
  return out;
}
