/**
 * Reading quantities the user actually stated, in words.
 *
 * THE PROBLEM THIS EXISTS FOR
 *
 * Terrium's promise is "ask a question, get a verified simulation". Measured
 * against the running API, that promise had a 0% success rate for any
 * question not containing CLI syntax:
 *
 *   "model a covid-19 outbreak in a town of 10000 people"
 *     -> FAILED: "s0, i0, r0_recovered, end, points could not be resolved
 *                 from literature and were not supplied in the query."
 *
 * The population is in the sentence. The user said "a town of 10000 people".
 * The only extraction that existed read CLI syntax -- "s0=10000", "s0:10000",
 * "s0 10000" (extractParameterOverrides in queryResolver.ts) -- so a number
 * stated in prose was invisible, and the system demanded it back as a flag.
 *
 * WHY THIS DOES NOT WEAKEN THE "NEVER INVENT" RULE
 *
 * It is the same rule, applied honestly. "Never invent" forbids Terrium
 * supplying a number nobody chose. It does not require ignoring a number the
 * user chose out loud. "A town of 10000 people" is the user specifying a
 * population as surely as "s0=10000" is; the difference is grammar, not
 * provenance. Both are origin "user".
 *
 * The rule this code must not break is the OTHER direction: never bind a
 * number the user did not mean. A misread quantity is worse than a refusal,
 * because a refusal is visible and a wrong number is not -- it produces a
 * plausible trajectory for a question nobody asked. Every design choice
 * below is made against that risk:
 *
 *   - Every pattern is ANCHORED to an explicit noun ("people", "infected",
 *     "cycles") or an explicit unit ("mM", "days"). A bare number is never
 *     harvested. This is what stops "COVID-19" yielding 19 and
 *     "SARS-CoV-2" yielding 2, and it is the same lesson PARAMETER_PATTERN
 *     in queryResolver.ts already learned the hard way: an unanchored regex
 *     there once read "k" out of protein names like CDK1 and ERK2 and
 *     stamped the result origin "user".
 *   - Every extraction carries the SOURCE PHRASE that produced it, so a
 *     reader can audit "s0=9995 because you said 'a town of 10000 people'"
 *     and catch a misreading rather than discovering it in the results.
 *   - Anything ambiguous is left alone for the existing refusal path, which
 *     already names what is missing and how to supply it. Extracting
 *     nothing is always a safe outcome here; extracting the wrong thing is
 *     not.
 *
 * WHAT IS DELIBERATELY NOT HERE: see the comment above TIME_UNITS for why
 * time is domain-aware, and the note on population for why "a town of N"
 * is a TOTAL rather than a susceptible count.
 */
import { matchEnzyme, type EnzymeEntry } from "./enzymes";
import type { SimulationDomain } from "./teriumRunner";

export interface StatedQuantity {
  /** The engine parameter this binds to. */
  key: string;
  /** The value, already converted into the engine's unit for this domain. */
  value: number;
  /**
   * The exact substring that produced it.
   *
   * Not decoration. This is the only thing that makes a misreading
   * catchable: it lets provenance say WHY a parameter has a value, so a
   * wrong binding is visible on the page instead of only in the trajectory.
   */
  sourcePhrase: string;
}

/**
 * Concentration units, expressed as a multiplier into mM.
 *
 * mM is the canonical concentration unit: `src/cli/reportQuantities.ts`
 * declares `ENGINE_CONCENTRATION = 'mM'` and `ENGINE_VMAX = 'mM/s'`, and
 * BRENDA's client normalises Km and Ki to mM (Tests/brenda_client.py,
 * `unit: str = "mM"`). Reading "10 uM" as 10 rather than 0.01 would be a
 * silent 1000x error in a simulation that still looks entirely plausible.
 *
 * THIS DUPLICATES `src/units.ts`, AND THAT IS A KNOWN COMPROMISE.
 *
 * A complete unit layer already exists there -- CONCENTRATION_TO_MOLAR,
 * TIME_TO_SECONDS, convertConcentration -- with the right policy already
 * argued ("Refusing to guess"). This file should import it and does not,
 * because it cannot: the api-server is a separate package whose tsconfig
 * is `rootDir: "src"` / `include: ["src"]`, so the repo-root `src/` tree
 * is outside its compilation entirely. Reaching it means restructuring
 * package boundaries, which is a larger and riskier change than the
 * feature that needs it.
 *
 * Two tables of the same physical constants is exactly the
 * duplicate-source-of-truth defect this repo has been bitten by before
 * (KM_PLAUSIBLE_MAX_MM once differed between the literature layer and the
 * engine, letting a value flagged implausible upstream arrive as
 * "confirmed" downstream; it was pinned equal with a regression test).
 * So the duplication is made non-silent the same way: `statedQuantities`'
 * test file reads `src/units.ts` and fails if the two disagree. Drift gets
 * caught rather than discovered in a wrong simulation.
 *
 * Note the two tables use different bases -- src/units.ts is multipliers
 * into MOLAR, this is multipliers into mM -- so the guard compares RATIOS,
 * not raw values.
 */
export const CONCENTRATION_TO_MM: Record<string, number> = {
  m: 1000,
  mm: 1,
  um: 1e-3,
  "µm": 1e-3, // micro sign
  "μm": 1e-3, // Greek mu
  nm: 1e-6,
};

/**
 * Time units in seconds. Converted into the DOMAIN's native time unit by
 * `timeToDomainUnit` below -- never used raw.
 */
export const TIME_IN_SECONDS: Record<string, number> = {
  second: 1,
  seconds: 1,
  sec: 1,
  secs: 1,
  s: 1,
  minute: 60,
  minutes: 60,
  min: 60,
  mins: 60,
  hour: 3600,
  hours: 3600,
  hr: 3600,
  hrs: 3600,
  h: 3600,
  day: 86400,
  days: 86400,
  week: 604800,
  weeks: 604800,
};

/**
 * The time unit each domain's `end` is expressed in.
 *
 * This is a real trap, not a formality. The two families disagree:
 *
 *   - Epidemiology carries time in DAYS. gamma is 1/infectious_period_days
 *     (Tests/epidemiology_resolver.py stores `infectious_period_days`), so
 *     an `end` of 100 means 100 days.
 *   - Enzyme kinetics carries time in SECONDS. Vmax is mM/s and kcat is 1/s
 *     (queryResolver.ts's bridge messages state both), so an `end` of 10
 *     means 10 seconds.
 *
 * So "over 30 days" is end=30 for sir and end=2,592,000 for mm. Reading it
 * as 30 for both would silently simulate half a minute of an assay the user
 * asked to run for a month.
 *
 * Domains absent from this table get no time extraction at all. That is
 * deliberate: for a domain whose time unit has not been established here,
 * refusing is correct and guessing is not.
 */
const DOMAIN_TIME_UNIT: Partial<Record<SimulationDomain, "seconds" | "days">> =
  {
    mm: "seconds",
    mm_competitive_inhibition: "seconds",
    sir: "days",
    seir: "days",
  };

function timeToDomainUnit(
  seconds: number,
  domain: SimulationDomain,
): number | undefined {
  const unit = DOMAIN_TIME_UNIT[domain];
  if (unit === undefined) return undefined;
  return unit === "seconds" ? seconds : seconds / 86400;
}

/** A number, possibly decimal or with thousands separators stripped. */
const NUM = "([0-9][0-9,]*(?:\\.[0-9]+)?)";

function toNumber(raw: string): number | undefined {
  const n = Number.parseFloat(raw.replace(/,/g, ""));
  return Number.isFinite(n) ? n : undefined;
}

/**
 * Matches a pattern and returns the first capture plus the whole matched
 * text, so the caller keeps the phrase for provenance.
 */
function firstMatch(
  query: string,
  pattern: RegExp,
): { value: number; phrase: string } | undefined {
  const m = pattern.exec(query);
  if (!m) return undefined;
  const value = toNumber(m[1]!);
  if (value === undefined) return undefined;
  return { value, phrase: m[0].trim() };
}

/**
 * How many people are already infected.
 *
 * Anchored on an infection noun, so an ordinary number elsewhere in the
 * sentence cannot become a case count.
 */
const INFECTED_RE = new RegExp(
  `\\b${NUM}\\s+(?:initial\\s+|initially\\s+)?(?:infected|infectious|cases|sick)\\b`,
  "i",
);

/**
 * Total population.
 *
 * "a town of 10000 people", "population of 10000", "10000 people".
 *
 * NOTE THIS IS A TOTAL, NOT s0. In the engine's SIR, s0 is the SUSCEPTIBLE
 * count and N = s0 + i0 + r0_recovered (Terium/core/validation.py's
 * validate_sir_params checks exactly that sum). So "a town of 10000 people
 * with 5 infected" means N=10000, i0=5, and therefore s0=9995. Binding
 * s0=10000 would quietly simulate a town of 10005 -- not the town the user
 * described.
 */
const POPULATION_RE = new RegExp(
  `\\b(?:population|town|city|village|community|cohort|school|group)\\s+of\\s+${NUM}` +
    `|\\b${NUM}\\s+(?:people|persons|individuals|residents|students|inhabitants)\\b`,
  "i",
);

function matchPopulation(
  query: string,
): { value: number; phrase: string } | undefined {
  const m = POPULATION_RE.exec(query);
  if (!m) return undefined;
  // Two alternatives, so the number is in whichever group matched.
  const raw = m[1] ?? m[2];
  if (raw === undefined) return undefined;
  const value = toNumber(raw);
  if (value === undefined) return undefined;
  return { value, phrase: m[0].trim() };
}

const CYCLES_RE = new RegExp(`\\b${NUM}\\s+cycles?\\b`, "i");

/** Wright-Fisher runs in discrete generations -- a count, not a duration. */
const GENERATIONS_RE = new RegExp(`\\b${NUM}\\s+generations?\\b`, "i");

/** A concentration with an EXPLICIT unit. Never a bare number. */
const CONCENTRATION_RE = new RegExp(
  `\\b${NUM}\\s*(m|mm|um|µm|μm|nm)\\b`,
  "i",
);

/** Regex-safe form of a literal substrate name like "NADP+" or "H2O2". */
function escapeRegExp(literal: string): string {
  return literal.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/**
 * An enzyme-kinetics query can state TWO concentrations that mean entirely
 * different things, and telling them apart is the whole job here.
 *
 *   "hexokinase with 50 nM enzyme and 10 mM glucose"
 *                    ^^^^^^^^^^^^^      ^^^^^^^^^^^
 *                    [E]0, enzyme_conc  substrate, s0
 *
 * These differ by five orders of magnitude, because they are different
 * physical quantities: enzymes work at nM-uM, their substrates at uM-mM.
 * An earlier version of this file took the FIRST concentration in the
 * sentence and bound it to s0 unconditionally, so the query above resolved
 * s0 = 0.00005 mM -- the ENZYME's concentration, presented as the
 * substrate's, stamped origin "user" with the source phrase "50 nM". It
 * would have simulated a flat, entirely plausible-looking curve for a
 * question nobody asked. That is the exact invisible-wrong-number failure
 * this module's header says it exists to prevent, and it was reachable the
 * moment a query mentioned its enzyme concentration.
 *
 * (It was not reachable in practice only because Vmax could not resolve at
 * all, so every such query failed earlier for a different reason. Making
 * enzyme_conc readable -- below -- is what would have armed it.)
 *
 * So each concentration is classified by the noun it modifies, and an
 * unclassifiable one is left to the refusal path.
 */
type ConcentrationRole = "enzyme" | "substrate" | "unlabelled";

interface ConcentrationHit {
  /** Already converted into mM. */
  value: number;
  phrase: string;
  role: ConcentrationRole;
  /** Which of the enzyme's known substrates it named, lowercased. */
  substrate?: string;
}

/** "of the total" etc. between a number and the noun it modifies. */
const NOUN_LEAD = "^\\s*(?:of\\s+)?(?:the\\s+)?(?:total\\s+)?";

/** Generic ways to say "the enzyme" without naming it. */
const ENZYME_WORD = "enzyme|catalyst|\\[e\\]\\s*[0₀]";

/** What can sit between a noun and its value: "enzyme at 50 nM". */
const VALUE_CONNECTOR = "(?:concentration\\s+)?(?:of|at|=|:|is)";

/**
 * Decide whether a concentration belongs to the enzyme or the substrate,
 * from the words touching it.
 *
 * Order matters. A noun AFTER the number ("50 nM enzyme", "10 mM glucose")
 * is the strongest signal, because that is the noun the quantity modifies.
 * Only when nothing follows do we look backwards ("enzyme at 50 nM"), and
 * a substrate named after the number always beats an enzyme named before
 * it -- "hexokinase at 10 mM glucose" is a glucose concentration, however
 * oddly it is worded.
 */
function classifyConcentration(
  before: string,
  after: string,
  enzyme: EnzymeEntry | undefined,
): { role: ConcentrationRole; substrate?: string; trailing?: string } {
  const namedEnzyme = enzyme ? `|(?:${enzyme.pattern.source})` : "";

  // 1. "... 50 nM enzyme", "... 1 uM hexokinase"
  const afterEnzyme = new RegExp(
    `${NOUN_LEAD}(?:${ENZYME_WORD}${namedEnzyme})\\b`,
    "i",
  ).exec(after);
  if (afterEnzyme) return { role: "enzyme", trailing: afterEnzyme[0] };

  // 2. "... 10 mM glucose". The substrate list comes from enzymes.ts
  //    rather than a second hardcoded list here -- the same
  //    two-lists-drifting-apart defect that domain classification hit.
  const substrateNames = [
    ...(enzyme?.substrates ?? []).map(escapeRegExp),
    "substrate",
  ];
  const afterSubstrate = new RegExp(
    `${NOUN_LEAD}(${substrateNames.join("|")})\\b`,
    "i",
  ).exec(after);
  if (afterSubstrate) {
    return {
      role: "substrate",
      substrate: afterSubstrate[1]!.toLowerCase(),
      trailing: afterSubstrate[0],
    };
  }

  // 3. "enzyme at 50 nM", "[E]0 = 5 uM". The connector is optional for the
  //    generic word (nothing else "enzyme 50 nM" could mean) but REQUIRED
  //    after a specific name, so the bare "hexokinase 10 mM glucose"
  //    reading stays with the substrate above.
  if (new RegExp(`(?:${ENZYME_WORD})\\s*(?:${VALUE_CONNECTOR})?\\s*$`, "i").test(before)) {
    return { role: "enzyme" };
  }
  if (
    enzyme &&
    new RegExp(
      `(?:${enzyme.pattern.source})\\s*(?:${VALUE_CONNECTOR})\\s*$`,
      "i",
    ).test(before)
  ) {
    return { role: "enzyme" };
  }

  return { role: "unlabelled" };
}

/**
 * The substrate concentration, chosen from every candidate in the query.
 *
 * Michaelis-Menten has ONE substrate, but a query may legitimately name
 * several concentrations ("10 mM glucose and 1 mM ATP"). Picking by
 * position would be arbitrary, so the enzyme's own substrate list decides:
 * enzymes.ts records substrates in order, and the first is the one whose
 * saturation the model describes (glucose for hexokinase, not its ATP
 * co-substrate). When that cannot settle it, this returns nothing and the
 * refusal path asks for s0 by name -- a visible question rather than a
 * silent coin-flip between two numbers the user did state.
 */
function chooseSubstrateConcentration(
  candidates: ConcentrationHit[],
  enzyme: EnzymeEntry | undefined,
): ConcentrationHit | undefined {
  const onlyDistinct = (list: ConcentrationHit[]): ConcentrationHit | undefined =>
    list.length > 0 && list.every((h) => h.value === list[0]!.value)
      ? list[0]
      : undefined;

  const named = candidates.filter((h) => h.substrate !== undefined);
  if (named.length > 0) {
    const primary = enzyme?.substrates[0]?.toLowerCase();
    const onPrimary =
      primary === undefined
        ? undefined
        : named.find((h) => h.substrate === primary);
    return onPrimary ?? onlyDistinct(named);
  }
  return onlyDistinct(candidates);
}

/** A duration with an EXPLICIT unit. Never a bare number. */
const DURATION_RE = new RegExp(
  `\\b(?:for|over|across|during)?\\s*${NUM}\\s*` +
    `(seconds?|secs?|s|minutes?|mins?|hours?|hrs?|h|days?|weeks?)\\b`,
  "i",
);

/**
 * Extract the quantities a query states in words, for a domain.
 *
 * Returns only what it is confident about. An empty result is a normal,
 * safe outcome -- the caller's existing refusal path then asks for what is
 * missing, which is strictly better than a guess.
 *
 * Domain-aware because the same words mean different parameters: "10000
 * people" is a population for sir and for wright_fisher, but those are
 * different parameter names, and "30 days" is a different number in each.
 */
export function extractStatedQuantities(
  query: string,
  domain: SimulationDomain,
): StatedQuantity[] {
  const out: StatedQuantity[] = [];
  const push = (
    key: string,
    hit: { value: number; phrase: string } | undefined,
  ): void => {
    if (hit) out.push({ key, value: hit.value, sourcePhrase: hit.phrase });
  };

  const isEpi = domain === "sir" || domain === "seir";

  if (isEpi) {
    const infected = firstMatch(query, INFECTED_RE);
    push("i0", infected);

    const population = matchPopulation(query);
    if (population) {
      // N is a total; s0 is the susceptible remainder. See POPULATION_RE.
      const i0 = infected?.value ?? 0;
      const s0 = population.value - i0;
      // A stated population smaller than the stated infected count is not a
      // reading this code should force into shape. Leave both to the
      // refusal path rather than emitting a negative or zero susceptible
      // count that would fail validation with a confusing message.
      if (s0 > 0) {
        out.push({
          key: "s0",
          value: s0,
          sourcePhrase: population.phrase,
        });
        // Describing a population and how many of it are infected accounts
        // for all of it: the rest are susceptible, and nobody has been
        // described as already recovered. So r0_recovered = 0 is READ from
        // the sentence, not defaulted into it -- the same reading that makes
        // s0 = N - i0 above, and it would be incoherent to derive s0 from
        // that arithmetic while refusing to state the term it assumed.
        //
        // A query that DOES mention recovered people is a different
        // sentence, and this deliberately does not try to parse it -- the
        // refusal path asks, which is correct when the reading is not
        // obvious.
        if (!/\brecover|\bimmune|\bvaccinat/i.test(query)) {
          out.push({
            key: "r0_recovered",
            value: 0,
            sourcePhrase: population.phrase,
          });
        }
      }
    }
  }

  if (domain === "wright_fisher" || domain === "two_locus_wright_fisher") {
    push("population_size", matchPopulation(query));
    push("generations", firstMatch(query, GENERATIONS_RE));
  }

  if (domain === "pcr") {
    push("cycles", firstMatch(query, CYCLES_RE));
  }

  if (domain === "mm" || domain === "mm_competitive_inhibition") {
    const enzyme = matchEnzyme(query);
    const hits: ConcentrationHit[] = [];
    for (const m of query.matchAll(new RegExp(CONCENTRATION_RE.source, "gi"))) {
      const value = toNumber(m[1]!);
      const factor = CONCENTRATION_TO_MM[m[2]!.toLowerCase()];
      if (value === undefined || factor === undefined) continue;
      const start = m.index;
      const end = start + m[0].length;
      const cls = classifyConcentration(
        query.slice(0, start),
        query.slice(end),
        enzyme,
      );
      hits.push({
        value: value * factor,
        // Keep the noun in the phrase, so provenance can say s0 = 10
        // because you wrote "10 mM glucose" -- naming the noun is what
        // makes a substrate/enzyme mix-up visible on the page.
        phrase: (m[0] + (cls.trailing ?? "")).trim(),
        role: cls.role,
        ...(cls.substrate !== undefined ? { substrate: cls.substrate } : {}),
      });
    }

    // [E]0. ADR 0013 says this is never resolved, inferred, or defaulted --
    // and it still is not. Reading it out of "with 50 nM enzyme" is the
    // user supplying it, in the same sense "enzyme_conc=0.00005" is; the
    // difference is grammar. What it unlocks is ADR 0019's Vmax = kcat x
    // [E]0 bridge, which had a literature kcat available all along and no
    // way for a plain-language question to supply the other half.
    const enzymeHit = hits.find((h) => h.role === "enzyme");
    if (enzymeHit) {
      out.push({
        key: "enzyme_conc",
        value: enzymeHit.value,
        sourcePhrase: enzymeHit.phrase,
      });
    }

    const substrateHit = chooseSubstrateConcentration(
      hits.filter((h) => h.role !== "enzyme"),
      enzyme,
    );
    if (substrateHit) {
      out.push({
        key: "s0",
        value: substrateHit.value,
        sourcePhrase: substrateHit.phrase,
      });
    }
  }

  // Duration -> end, in the domain's own time unit.
  const d = DURATION_RE.exec(query);
  if (d) {
    const value = toNumber(d[1]!);
    const seconds = TIME_IN_SECONDS[d[2]!.toLowerCase()];
    if (value !== undefined && seconds !== undefined) {
      const converted = timeToDomainUnit(value * seconds, domain);
      if (converted !== undefined && converted > 0) {
        out.push({ key: "end", value: converted, sourcePhrase: d[0].trim() });
      }
    }
  }

  return out;
}
