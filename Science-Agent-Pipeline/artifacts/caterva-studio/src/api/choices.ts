/**
 * What the engine chose for the person, and how the page reads it (ADR 0182).
 *
 * A compose request that names an enzyme and leaves the substrate, the
 * inhibitor or the organism blank no longer refuses: the engine
 * (caterva/compose/defaults.py) picks the best-measured real option BRENDA
 * has, runs with its cited values, and records each pick in the result's
 * `search.choices`, in the order it made them, beside a plain-English note
 * in the report. Each pick names what was chosen, why, and the other options
 * with how many usable rows of each constant BRENDA holds for them, so the
 * person can switch with one click.
 *
 * WHY THESE SHAPES LIVE HERE AND NOT IN types.ts
 * types.ts is mirrored key by key against caterva/studio/contract.py
 * (caterva/tests/test_studio_contract.py). The choice was added to the engine
 * and to the page in parallel; reading it through `choicesOf` keeps the page
 * honest about a result that predates it (an old run has no `choices` key at
 * all, and shows no panel) without declaring a contract key the Python side
 * may not have yet. Once contract.SearchSummary carries `choices`, the same
 * key goes on SearchSummary in types.ts and these interfaces move with it.
 */
import type { ComposeResult } from "./types";

/** Which field of the request an automatic choice filled. "enzyme" is the subject (an EC number). */
export type ChoiceRole = "substrate" | "inhibitor" | "organism" | "enzyme";

/** One option BRENDA had for a role, with how many usable rows of each constant it holds ({"km": 9, "kcat": 4}). */
export interface ChoiceOption {
  name: string;
  rows: Record<string, number>;
}

/** caterva/compose/defaults.py `Choice.to_json()`: what was chosen, the plain-English why, and what else there was. */
export interface SearchChoice {
  role: ChoiceRole;
  chosen: string;
  why: string;
  alternatives: ChoiceOption[];
  /** How many options were weighed in all, listed as alternatives or not. */
  considered: number;
}

/** The request fields a re-run can set: one per choice role ("enzyme" is the subject). */
export type RerunField = "subject" | "organism" | "substrate" | "inhibitor";
export type RerunPatch = Partial<Record<RerunField, string>>;

export const FIELD_OF_ROLE: Record<ChoiceRole, RerunField> = {
  substrate: "substrate",
  inhibitor: "inhibitor",
  organism: "organism",
  enzyme: "subject",
};

const ROLES = new Set<string>(Object.keys(FIELD_OF_ROLE));

function isOption(x: unknown): x is ChoiceOption {
  if (!x || typeof x !== "object") return false;
  const o = x as Record<string, unknown>;
  return typeof o.name === "string" && !!o.rows && typeof o.rows === "object";
}

/**
 * The choices a result carries, or [] for a result that has none (every run
 * before ADR 0182, and a run where nothing was left to choose). A malformed
 * entry is dropped rather than drawn half-empty: a chip with no name would
 * re-run with nothing set.
 */
export function choicesOf(result: ComposeResult): SearchChoice[] {
  const raw = (result.search as unknown as { choices?: unknown }).choices;
  if (!Array.isArray(raw)) return [];
  const out: SearchChoice[] = [];
  for (const c of raw) {
    if (!c || typeof c !== "object") continue;
    const r = c as Record<string, unknown>;
    if (typeof r.role !== "string" || !ROLES.has(r.role) || typeof r.chosen !== "string" || !r.chosen) continue;
    out.push({
      role: r.role as ChoiceRole,
      chosen: r.chosen,
      why: typeof r.why === "string" ? r.why : "",
      alternatives: Array.isArray(r.alternatives) ? r.alternatives.filter(isOption) : [],
      considered: typeof r.considered === "number" ? r.considered : 0,
    });
  }
  return out;
}

/** How the engine's row-count keys read on a chip. */
const CONSTANT_WORD: Record<string, string> = { km: "Km", kcat: "kcat", ki: "Ki", ic50: "IC50", kcat_km: "kcat/Km" };

/** "9 Km, 4 kcat": the rows BRENDA holds for an option, in the order the engine listed them; "" when none are listed. */
export function rowsLine(rows: Record<string, number>): string {
  return Object.entries(rows)
    .filter(([, n]) => typeof n === "number")
    .map(([k, n]) => `${n} ${CONSTANT_WORD[k.toLowerCase()] ?? k}`)
    .join(", ");
}

/**
 * The request a chip runs: that choice's field set to the option, and every
 * choice made BEFORE it kept as it was made. The choices are ordered: a
 * substrate chosen after the organism was counted in that organism's rows,
 * so the row counts on its chips are true only while the organism stays put.
 * Letting the engine choose the earlier ones again could move them and make
 * the chip's numbers wrong. Choices made after the clicked one are left to
 * the engine, which chooses them again for the new value.
 */
export function rerunPatch(choices: readonly SearchChoice[], index: number, option: string): RerunPatch {
  const patch: RerunPatch = {};
  for (const earlier of choices.slice(0, index)) patch[FIELD_OF_ROLE[earlier.role]] = fieldValue(earlier.role, earlier.chosen);
  patch[FIELD_OF_ROLE[choices[index].role]] = fieldValue(choices[index].role, option);
  return patch;
}

/** An EC number anywhere in a string: "EC 4.1.3.7 (citrate (Si)-synthase)" -> "4.1.3.7". */
const EC_IN = /\b(\d+\.\d+\.\d+\.n?\d+)\b/;

/**
 * What a chosen or offered name puts in its request field. An enzyme
 * alternative is written for a reader ("EC 2.3.3.1 (citrate (Re)-synthase)",
 * caterva/compose/defaults.py), and the subject field takes the bare EC
 * number: sent as written, the run would get no subject at all and a name
 * to read instead, which is not the enzyme the chip named. Every other role
 * is the name itself.
 */
export function fieldValue(role: ChoiceRole, name: string): string {
  if (role !== "enzyme") return name;
  return EC_IN.exec(name)?.[1] ?? name;
}

/**
 * A note the engine writes when a field the person set contradicts the
 * description (caterva/compose/__main__.py): "Your description names
 * 'granzyme B' (EC 3.4.21.79); --subject 1.14.19.48 was used, because a flag
 * wins over the description." The organism has the same sentence with
 * "--organism". The name is a Python repr, so either quote may wrap it.
 */
const MISMATCH = /^Your description names (['"])(.+?)\1 \(([^)]+)\); --(subject|organism) (.+?) was used, because a flag wins over the description\.?$/;

export interface Mismatch {
  note: string;
  field: "subject" | "organism";
  /** What the description names, as written ("granzyme B", "human"). */
  named: string;
  /** What the engine read it as: the EC number for the subject, the binomial for the organism. */
  readAs: string;
  /** What the run used instead. */
  used: string;
}

export function mismatchOf(note: string): Mismatch | null {
  const m = MISMATCH.exec(note.trim());
  if (!m) return null;
  const field = m[4] as "subject" | "organism";
  const readAs = field === "subject" ? m[3].replace(/^EC\s+/, "") : m[3];
  return { note, field, named: m[2], readAs, used: m[5] };
}
