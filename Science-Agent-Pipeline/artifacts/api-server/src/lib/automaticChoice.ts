/**
 * A name Caterva chose because the question did not give one (ADR 0182).
 *
 * WHY CHOICES EXIST AT ALL
 * ------------------------
 * An unnamed substrate used to be read as "any substrate": the runner took
 * KEGG's first listed substrate, or BRENDA's rows unfiltered, and the Km of
 * whichever substrate's row came first arrived with nothing naming it. The
 * fix after that (ADR 0178/0181) refused instead, and a student who asked
 * about "hexokinase in humans" got placeholders while BRENDA held 25
 * measured glucose rows for it.
 *
 * The rule now: choose the best-measured real option from BRENDA, run with
 * its real, cited values, and SAY SO -- what was chosen, why, and what the
 * alternatives were with their row counts, so the reader can switch. The
 * choosing is done once, in Python (caterva.compose.defaults, the chooser
 * `caterva compose` uses), and the runners send each choice back as
 * `Choice.to_json()`. This file only words it; it decides nothing.
 */

/** One alternative the chooser considered, with its measured rows per table. */
export interface ChoiceOption {
  name: string;
  /** Rows BRENDA holds per table, e.g. `{ km: 25, kcat: 61 }` or `{ ki: 7 }`. */
  rows: Record<string, number>;
}

/** `caterva.compose.defaults.Choice.to_json()`, exactly as the runner sends it. */
export interface AutomaticChoice {
  role: "substrate" | "inhibitor" | "organism" | "enzyme";
  chosen: string;
  /** The chooser's own sentence: why this one. */
  why: string;
  alternatives: ChoiceOption[];
  /** How many candidates were counted. */
  considered: number;
}

/** How many alternatives a flag lists before saying "and N more". */
const ALTERNATIVES_SHOWN = 5;

const TABLE_LABEL: Record<string, string> = { km: "Km", kcat: "kcat", ki: "Ki" };

/** "Km 25 rows, kcat 61 rows". */
export function describeRows(rows: Record<string, number>): string {
  return Object.entries(rows)
    .map(([table, n]) => `${TABLE_LABEL[table] ?? table} ${n} row${n === 1 ? "" : "s"}`)
    .join(", ");
}

/** "ATP (Km 106 rows); D-mannose (Km 9 rows), and 4 more". Empty when none. */
export function describeAlternatives(alternatives: readonly ChoiceOption[]): string {
  const shown = alternatives.slice(0, ALTERNATIVES_SHOWN).map((a) => {
    const rows = describeRows(a.rows);
    return rows ? `${a.name} (${rows})` : a.name;
  });
  const more = alternatives.length - shown.length;
  return shown.join("; ") + (more > 0 ? `, and ${more} more` : "");
}

/** How a reader of the API overrides each role in a free-text query. */
const HOW_TO_CHOOSE: Record<AutomaticChoice["role"], string> = {
  substrate: 'name the substrate in the query ("<enzyme> with <substrate>") to use another',
  inhibitor: 'name the inhibitor in the query ("inhibited by <compound>") to use another',
  organism: 'name the organism in the query ("in <organism>") to use another',
  enzyme: "name the enzyme in the query to use another",
};

/**
 * The flag a choice becomes, e.g.
 *
 *   substrate chosen: D-glucose -- most Km+kcat rows in Homo sapiens.
 *   Alternatives: ATP (Km 106 rows); D-mannose (Km 9 rows). Name the
 *   substrate in the query ("<enzyme> with <substrate>") to use another.
 *
 * Starts with "<role> chosen:" so a client can find every automatic choice
 * among the flags by prefix, the way it finds "assumed: organism".
 */
export function choiceFlag(choice: AutomaticChoice): string {
  const why = choice.why.trim().replace(/[.\s]+$/, "");
  const alternatives = describeAlternatives(choice.alternatives);
  const how = HOW_TO_CHOOSE[choice.role] ?? "name it in the query to use another";
  return (
    `${choice.role} chosen: ${choice.chosen} -- ${why}. ` +
    (alternatives ? `Alternatives: ${alternatives}. ` : "No other candidate had usable rows. ") +
    how.charAt(0).toUpperCase() + how.slice(1) + "."
  );
}

/**
 * The choices a runner payload carries, kept only when well formed. A
 * malformed entry is dropped rather than guessed at: a flag built from half
 * a choice would name a substrate without saying why.
 */
export function readChoices(raw: unknown): AutomaticChoice[] {
  if (!Array.isArray(raw)) return [];
  return raw.filter(
    (c): c is AutomaticChoice =>
      typeof c === "object" &&
      c !== null &&
      typeof (c as AutomaticChoice).role === "string" &&
      typeof (c as AutomaticChoice).chosen === "string" &&
      (c as AutomaticChoice).chosen.length > 0 &&
      typeof (c as AutomaticChoice).why === "string" &&
      Array.isArray((c as AutomaticChoice).alternatives),
  );
}

/** True when a flag states an automatic choice (see choiceFlag). */
export function isChoiceFlag(flag: string): boolean {
  return /^(substrate|inhibitor|organism|enzyme) chosen: /.test(flag);
}
