/**
 * Copy at the page's edge: the engine's sentences, in the page's language.
 *
 * The engine writes for a terminal. Its messages name command-line flags
 * ("re-run with --organism set to ..."), the script behind a command
 * ("cite.py"), use `--` and a long dash as punctuation, print a Python
 * exception as if it were a finding ("ReadTimeout: HTTPSConnectionPool(...)")
 * and quote whole request URLs. This module rewrites those known phrasings
 * for the window and for nothing else: every rewrite only rephrases, never
 * adds a fact, and every one is tested with the engine's own string as input
 * (src/__tests__/copy.test.ts).
 *
 * Nothing here decides an outcome. The server classifies an upstream outage
 * (docs/studio/CONTRACT.md 6); `networkFailureOf` reads the same signatures
 * for the places the page meets raw text that is not an outcome (the network
 * check, a 503 `unavailable` body).
 */
import type { NetworkFailure } from "@/api/types";

// ------------------------------------------------------------------ plurals

/** "1 run", "8 runs". The count is written in figures, thousands grouped. */
export function plural(n: number, one: string, many?: string): string {
  const count = Number.isFinite(n) ? n.toLocaleString("en-US") : String(n);
  return `${count} ${n === 1 ? one : (many ?? `${one}s`)}`;
}

// ------------------------------------------------------------------- hosts

const HOST_NAMES: Record<string, string> = {
  "www.brenda-enzymes.org": "BRENDA",
  "rest.uniprot.org": "UniProt",
  "search.rcsb.org": "the RCSB search",
  "files.rcsb.org": "the RCSB files",
  "data.rcsb.org": "the RCSB data",
  "eutils.ncbi.nlm.nih.gov": "NCBI",
  "pubchem.ncbi.nlm.nih.gov": "PubChem",
  "rest.kegg.jp": "KEGG",
};

/** A database host named the way a person says it; an unknown host is shown as written. */
export function hostLabel(host: string): string {
  return HOST_NAMES[host] ?? host;
}

const URL_IN_TEXT = /https?:\/\/([A-Za-z0-9.-]+)(?::\d+)?(?:\/[^\s)'"]*)?/g;

/** Every request URL in `text` replaced by its host's name: the path and query are not a sentence. */
export function withoutUrls(text: string): string {
  return text.replace(URL_IN_TEXT, (_all, host: string) => hostLabel(host));
}

// ----------------------------------------------------------------- network

const NETWORK_SIGNATURE =
  /ReadTimeout|ConnectTimeout|ConnectionError|ConnectionPool|Max retries exceeded|Read timed out|Connect timed out|Temporary failure in name resolution|Name or service not known|nodename nor servname|RemoteDisconnected|ConnectionResetError|URLError|HTTPError: \d{3}|\d{3} (?:Server|Client) Error|could not reach the PDB/;

/**
 * The upstream outage a piece of engine text is, or null. The same signatures
 * as `contract.network_failure`; an offline-mode refusal does not match.
 */
export function networkFailureOf(text: string | null | undefined): NetworkFailure | null {
  if (!text || !NETWORK_SIGNATURE.test(text)) return null;
  const host = /host='([^']+)'/.exec(text)?.[1] ?? /https?:\/\/([A-Za-z0-9.-]+)/.exec(text)?.[1] ?? null;
  const status = /HTTPError: (\d{3})|(\d{3}) (?:Server|Client) Error/.exec(text);
  return {
    host,
    status: status ? Number(status[1] ?? status[2]) : null,
    timed_out: /ReadTimeout|ConnectTimeout|Read timed out|Connect timed out/.test(text),
  };
}

/** "UniProt did not answer. Check the network, then search again." `again` finishes the sentence. */
export function networkSentence(failure: NetworkFailure | null, again = "try again"): string {
  const who = failure?.host ? hostLabel(failure.host) : "A database";
  const verb =
    failure?.status !== null && failure?.status !== undefined && failure.status < 500 && failure.status !== 429
      ? "refused the request"
      : "did not answer";
  const cap = who.charAt(0).toUpperCase() + who.slice(1);
  return `${cap} ${verb}. Check the network, then ${again}.`;
}

// ------------------------------------------------------------ the rewrites

/** What a flag is called where the page has a field for it. */
const FLAG_FIELD: Record<string, string> = {
  organism: "Organism",
  substrate: "Substrate",
  inhibitor: "Inhibitor",
  isoform: "Isoform",
  subject: "Enzyme",
  ec: "EC number",
  enzyme: "Enzyme",
  seed: "Seed",
  temperature: "Temperature",
  ph: "pH",
  "ionic-strength": "ionic strength",
  "no-cache": "the cache setting",
  chimerax: "the ChimeraX file",
  robustness: "Robustness",
  validate: "Cross-checks",
  validation: "Cross-checks",
  gene: "gene",
  uniprot: "UniProt entry",
  vmax: "Vmax",
  s0: "the starting substrate amount",
  ns: "the replica length",
  top: "the number of entries",
  pdb: "PDB entry",
  chain: "Chain",
  replicas: "Replicas",
  out: "the output folder",
  end: "the end time",
};

type Rewrite = string | ((match: string, ...groups: string[]) => string);

const SENTENCE_PATTERNS: [RegExp, Rewrite][] = [
  // "Read --organism 'human' as Homo sapiens."
  [/Read --organism ('[^']*') as /g, "Read $1 as "],
  // "re-run with --organism set to one the provenance table lists ... -- start with ..."
  [/re-run with --organism set to /gi, "set Organism to "],
  [/Re-run with --seed N\./g, "Set Seed and run it again."],
  // "pass --isoform with the isoform's name as the papers write it (for example --isoform LDH-A) to take each constant ..."
  [
    /pass --isoform with the isoform's name as the papers write it \(for example --isoform ([^)]+)\)/g,
    "set Isoform to the name the papers write (for example $1)",
  ],
  [/pass the one simulated \(--isoform\)/g, "set Isoform to the one simulated"],
  // "not run -- pass --validate (or `validation=`) for the cross-module consistency check"
  [/pass --validate \(or `validation=`\)/g, "tick Cross-checks"],
  [/pass --robustness \(or `robustness=`\)/g, "tick Robustness to the placeholders"],
  // "Choose with --gene or --uniprot: LDHA (P00338, 46 entries), ..."
  [/Choose with --gene or --uniprot:/g, "Choose one by its gene or its UniProt entry:"],
  // "physiological default; override with --ionic-strength"
  [/override with --ionic-strength/g, "set the ionic strength to change it"],
  [/override with --ns\b/g, "set the replica length to change it"],
  // "the default of cite.py --vmax; chosen for this run"
  [/the default of cite\.py --([a-z0-9-]+)/g, (_m, flag) => `the stated default for ${FLAG_FIELD[flag] ?? flag}`],
  // "chosen: 310 K, set with --temperature"
  [/set with --([a-z0-9-]+)/g, (_m, flag) => `set in ${FLAG_FIELD[flag] ?? flag}`],
  // "caterva compose: error: --robustness needs at least one sample"
  [/^caterva [a-z]+: error: /g, ""],
  // The terminal commands a description points at ("(caterva compose --export csv)").
  [/ \(caterva [a-z]+(?: [^)]*)?\)/g, ""],
  // The script behind a command.
  [/\(cite\.py's own check\)/g, "(the command's own check)"],
  [/\b(?:python3 )?(?:scripts\/)?cite\.py\b/g, "the lab-report command"],
];

/** Bare flags the specific patterns above did not name. */
function flagsToFields(text: string): string {
  return text.replace(/(?<![\w-])--([a-z][a-z0-9-]*)\b/g, (_m, flag: string) => FLAG_FIELD[flag] ?? flag.replace(/-/g, " "));
}

/** "constant(s)" and "8 run(s)": proper plurals. */
function pluralise(text: string): string {
  return text
    .replace(/(\d[\d,]*) ([A-Za-z]+)\(s\)/g, (_m, n: string, word: string) => {
      const count = Number(n.replace(/,/g, ""));
      return `${n} ${count === 1 ? word : `${word}s`}`;
    })
    .replace(/([A-Za-z]+)\(s\)/g, "$1s");
}

/** " -- " and a long dash are punctuation the page does not use: a sentence break, a semicolon or a comma. */
function dashes(text: string): string {
  return text
    .replace(/ -- (?=https?:\/\/)/g, ": ")
    .replace(/ -- ([A-Za-z])/g, (_m, c: string) => (/[A-Z]/.test(c) ? `, ${c}` : `. ${c.toUpperCase()}`))
    .replace(/ \u2014 ([A-Za-z])/g, (_m, c: string) => (/[A-Z]/.test(c) ? `, ${c}` : `; ${c}`))
    .replace(/\u2014/g, ",");
}

/**
 * The engine's sentence in the page's language: flags named by the field that
 * sets them, no script names, no `--` or long dash as punctuation, proper
 * plurals. Text that has none of these is returned unchanged.
 */
export function plain(text: string): string {
  if (!text) return text;
  let out = text;
  for (const [pattern, to] of SENTENCE_PATTERNS) {
    out = typeof to === "string" ? out.replace(pattern, to) : out.replace(pattern, to);
  }
  out = flagsToFields(out);
  out = dashes(out);
  return pluralise(out);
}

// ------------------------------------------------------------- identifiers

const CONSTANT_NAMES: Record<string, string> = {
  kcat: "kcat",
  km: "Km",
  ki: "Ki",
  vmax: "Vmax",
};

/**
 * A model identifier in words. `reaction_kcat` is "kcat of the reaction";
 * `competitive_inhibition.kcat` is "kcat of competitive inhibition". The
 * identifier itself stays available where the page keeps it (a title, a
 * disclosure): this only changes how a sentence says it.
 */
export function humaniseIdentifier(id: string): string {
  const dotted = /^([a-z][a-z0-9_]*)\.([A-Za-z][A-Za-z0-9_]*)$/.exec(id);
  if (dotted) return `${CONSTANT_NAMES[dotted[2].toLowerCase()] ?? dotted[2]} of ${dotted[1].replace(/_/g, " ")}`;
  const owned = /^([a-z][a-z0-9]*)_(kcat|Km|Ki|Vmax|km|ki|vmax)$/.exec(id);
  if (owned) return `${CONSTANT_NAMES[owned[2].toLowerCase()]} of the ${owned[1]}`;
  return id;
}

/** Every identifier in a progress sentence replaced by its words ("Looking up reaction_kcat in BRENDA's kcat table"). */
export function humaniseStage(label: string): string {
  return label.replace(/\b[a-z][a-z0-9]*_(?:kcat|Km|Ki|Vmax|km|ki|vmax)\b/g, (id) => humaniseIdentifier(id));
}

// ------------------------------------------------------ placeholder reasons

export interface PlaceholderReading {
  /** "kcat of competitive inhibition". */
  what: string;
  /** The identifier as the engine writes it, for a title. */
  identifier: string;
  /** BRENDA's table that would hold the measurement, or null. */
  table: string | null;
  /** The engine's own words for why no table serves it, when it says so. */
  noTable: boolean;
}

const LIBRARY_VALUE =
  /^ILLUSTRATIVE PLACEHOLDER: Caterva's motif library value for (\S+?)\. No publication supplies this number and nobody measured it\. It is here so the structure can be checked, dimensioned and simulated(?:; the measurement that would replace it is in the (\S+) table|; no database table serves it, so it is resolvable only from a paper)\.?$/;

/**
 * The boilerplate every unmeasured constant carries, split into what differs
 * per row (which constant, which table) and what is the same on every row
 * (stated once above the table). Null when the text is anything else, so a
 * reason the engine wrote for one constant is shown whole.
 */
export function readPlaceholder(reason: string): PlaceholderReading | null {
  const m = LIBRARY_VALUE.exec(reason.trim());
  if (!m) return null;
  return { what: humaniseIdentifier(m[1]), identifier: m[1], table: m[2] ?? null, noTable: m[2] === undefined };
}

/** The sentence every placeholder shares, said once. The words are the engine's, in sentence case. */
export const PLACEHOLDER_SHARED =
  "A placeholder is Caterva's library value for a constant. No publication supplies it and nobody measured it. It is here so the structure can be checked, dimensioned and simulated.";

/** The per-row reason, in sentence case, short enough to read in one glance. */
export function placeholderRowReason(reading: PlaceholderReading): string {
  return reading.noTable
    ? `Library value for the ${reading.what}. No database table serves it; only a paper can supply it.`
    : `Library value for the ${reading.what}. A measurement would be in BRENDA's ${reading.table} table.`;
}

// ------------------------------------------------------------ markdown prose

/**
 * `plain` over a Markdown document's prose only: fenced blocks and inline
 * code are commands and file names as written, and stay exactly as they are.
 */
export function plainMarkdown(source: string): string {
  return source
    .split(/(^```[^\n]*\n[\s\S]*?^```[^\n]*$)/m)
    .map((chunk) =>
      chunk.startsWith("```")
        ? chunk
        : chunk
            .split(/(`[^`\n]*`)/)
            .map((piece) => (piece.startsWith("`") ? piece : plain(piece)))
            .join(""),
    )
    .join("");
}

// ------------------------------------------------------------ source tokens

/**
 * What the resolver's `source` token says, in the words of the engine's own
 * account of the six outcomes (caterva/agents/adapters.py). An unknown token
 * is shown with its underscores as spaces, never guessed at.
 */
const SOURCE_WORDS: Record<string, string> = {
  brenda_exact: "found in BRENDA, in the organism asked for",
  brenda_cross_species: "found in BRENDA, in another organism, which you allowed",
  cross_species_withheld: "exists in another organism, which you did not allow",
  cross_species_too_distant: "exists, but in an organism too distant to offer",
  literature_candidates: "no database value; papers that may hold one",
  not_found: "nothing found anywhere that was searched",
};

export function describeSource(token: string): string {
  return SOURCE_WORDS[token] ?? token.replace(/_/g, " ");
}

// ------------------------------------------------------- compounds with a Ki

export interface CompoundList {
  /** The refusal's own first sentence: "No Ki for 'oxamate' with EC 1.1.1.27 in Homo sapiens." */
  lead: string;
  compounds: string[];
}

/**
 * bind's refusal for an inhibitor with no rows ends in "Compounds that do
 * have one: a; b; c", sometimes thirty IUPAC names long. Read as data so the
 * page can offer them as a list to choose from; null for any other text.
 */
export function readCompoundList(reason: string): CompoundList | null {
  const m = /^([\s\S]*?)\n?Compounds that do have one: ([\s\S]+)$/.exec(reason.trim());
  if (!m || !m[1].trim()) return null;
  const compounds = m[2].split("; ").map((c) => c.trim()).filter(Boolean);
  return compounds.length ? { lead: m[1].trim(), compounds } : null;
}
