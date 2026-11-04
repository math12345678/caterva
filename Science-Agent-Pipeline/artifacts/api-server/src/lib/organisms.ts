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
 * The first word of a longer animal name that ends in one of these
 * common names, and is a different animal.
 *
 * `\bpigs?\b` matched inside "guinea pig". Measured 2026-11-03 on the
 * live API: "hexokinase with glucose in guinea pigs" came back km 0.015,
 * source brenda_exact, organism Sus scrofa, cited "BRENDA (ref 640240)"
 * -- a pig hexokinase II row under the guinea pig's query, badged as an
 * exact match. "naked mole rats" was read as Rattus norvegicus (ref
 * 640259) the same way, and "sea cow" and "pig-tailed macaque" likewise.
 * Before these aliases existed each of those queries fell to the labelled
 * "assumed: organism" default, which is honest; a wrong species with a
 * real citation is not. So a common name counts only when it stands on
 * its own: no listed modifier before it, and no hyphen on either side
 * ("mole-rat", "pig-tailed", "mouse-ear cress", which is Arabidopsis). A
 * longer name this list misses still matches the wrong species: the list
 * is the compound animal names a lab is likely to type, not a closed set.
 */
const COMPOUND_NAME_HEADS = [
  "guinea", "sea", "mole", "kangaroo", "cotton", "wood", "bush", "musk",
  "water", "sand", "pack", "desert", "deer", "field", "spiny", "harvest",
  "pocket", "grasshopper", "jumping", "pygmy", "giant", "bandicoot",
  "cane", "rice", "prairie",
].join("|");

function commonName(word: string): string {
  return (
    `(?<!\\b(?:${COMPOUND_NAME_HEADS})[\\s-]+)(?<![-\\w])` +
    `(?:${word})(?![-\\w])`
  );
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
    pattern: new RegExp(`\\bMus musculus\\b|${commonName("mouse|mice")}|\\bmurine\\b`, "i"),
    organism: "Mus musculus",
  },
  {
    pattern: new RegExp(`\\bRattus norvegicus\\b|${commonName("rats?")}`, "i"),
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
    pattern: new RegExp(`\\bBos taurus\\b|\\bbovine\\b|${commonName("cows?")}|\\bcattle\\b`, "i"),
    organism: "Bos taurus",
  },
  {
    pattern: new RegExp(`\\bSus scrofa\\b|\\bporcine\\b|${commonName("pigs?")}|\\bswine\\b`, "i"),
    organism: "Sus scrofa",
  },
  {
    pattern: /\bOryctolagus cuniculus\b|\brabbits?\b/i,
    organism: "Oryctolagus cuniculus",
  },
  {
    pattern: new RegExp(`\\bGallus gallus\\b|${commonName("chickens?")}`, "i"),
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
 * Assay reagents that carry an animal's name and are not the enzyme's
 * source.
 *
 * Measured 2026-11-03 on the live API: "pseudomonas aeruginosa hexokinase
 * with glucose with bovine serum albumin" came back km 0.047, brenda_exact,
 * organism Bos taurus, BRENDA ref 662842 -- a cow's hexokinase Km under a
 * Pseudomonas query, because "bovine" (added to ORGANISMS on 2026-11-02)
 * sits ahead of Pseudomonas in the list and the first match won. BSA,
 * ovalbumin and gelatin are in half the assay buffers ever written down;
 * the species they name is the reagent's, never the enzyme's. "human serum
 * albumin" had the same defect before any of the new aliases existed.
 *
 * Bare "serum" and "plasma" are NOT here: "lactate dehydrogenase in rat
 * serum" is the rat's own LDH, and setting the rat aside would ground it
 * in the Homo sapiens default instead.
 */
const REAGENT =
  "(?:serum\\s+albumin|albumin|ovalbumin|egg\\s+albumin|" +
  "gamma[\\s-]?globulin|globulins?|IgG|immunoglobulins?|gelatin|BSA|HSA)";

function withoutReagents(query: string): string {
  let out = query;
  for (const entry of ORGANISMS) {
    const org = `(?:${entry.pattern.source})`;
    // "bovine serum albumin", "chicken ovalbumin"; and "BSA from cows",
    // "albumin of the rat".
    out = out
      .replace(new RegExp(`(?:fetal\\s+)?${org}\\s+${REAGENT}\\b`, "gi"), " ")
      .replace(
        new RegExp(`\\b${REAGENT}\\s+(?:from|of)\\s+(?:the\\s+|a\\s+)?(?:fetal\\s+)?${org}`, "gi"),
        " ",
      );
  }
  return out;
}

/**
 * Every distinct organism a query names, reagents set aside, in list
 * order.
 *
 * More than one is a conflict the caller must refuse, not resolve. The
 * matcher used to return the first entry in ORGANISMS' order, so which
 * species a two-species query was grounded in depended on how this file
 * happened to be sorted: "mycobacterium tuberculosis kinase, chicken
 * liver extract" went to Gallus gallus because chicken was listed first.
 * Nothing in the text says which one the enzyme came from, and a guess
 * here attaches a real citation to it.
 */
export function matchOrganisms(query: string): string[] {
  const text = withoutReagents(query);
  const found: string[] = [];
  for (const entry of ORGANISMS) {
    if (entry.pattern.test(text) && !found.includes(entry.organism)) {
      found.push(entry.organism);
    }
  }
  return found;
}

/**
 * The organism named in a query, or undefined when none is -- or when
 * several are (see matchOrganisms; a caller that must tell those two
 * apart calls it directly, as extractEntitiesFromQuery does).
 *
 * `undefined` is a real answer, not a failure: the caller keeps its
 * existing default rather than being handed a guess.
 */
export function matchOrganism(query: string): string | undefined {
  const found = matchOrganisms(query);
  return found.length === 1 ? found[0] : undefined;
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
  let out = withoutReagents(query);
  for (const entry of ORGANISMS) {
    out = out.replace(new RegExp(entry.pattern.source, "gi"), " ");
  }
  return out;
}
