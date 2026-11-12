/**
 * The query read the way `caterva compose` reads it, by compose itself.
 *
 * WHY THE API DOES NOT READ THE SENTENCE ITSELF ANY MORE
 * ------------------------------------------------------
 * The adversarial round of 2026-11-11 put the same sentences to the API,
 * `caterva compose`, Caterva Studio and the TypeScript CLI. Compose and
 * Studio read them with one reader; the API kept its own (a curated regex
 * table and an "-ase window" guesser), and it misread them:
 *
 * - "chymotrypsin follows Michaelis-Menten kinetics" was TRYPSIN (the
 *   /trypsin/ pattern matched inside "chymotrypsin"), cited to EC 3.4.21.4;
 * - "hexokinase Michaelis-Menten kinetics" asked for the Km of a substrate
 *   called "michaelis-menten kinetics", and refused;
 * - "competitive inhibition of xanthine oxidase by allopurinol" carried
 *   BRENDA's Km of allopurinol AS A SUBSTRATE as the model's Km;
 * - "HK2 with glucose" dropped the isoform and carried a hexokinase-I row;
 * - the organism was the table's default, never a stated choice, so the
 *   allopurinol query landed on human, where no allopurinol Ki exists.
 *
 * A second reader of one sentence is a second answer to it. So the API asks
 * `python -m caterva.compose.read`, which runs compose's own reading
 * (`read_description`, the enzyme policy, the ADR 0182 choosers) and prints
 * it as JSON. Nothing here reads a word of the query.
 *
 * `CATERVA_SENTENCE_READER` names a script run with the same arguments in
 * the reader's place (as CATERVA_DEFAULTS_RUNNER does for the CLI's
 * chooser), so the tests that pin this file are offline; "off" skips the
 * reader, and the query is then read by the API's older reader
 * (queryResolver's extractEntitiesFromQuery), which is what the test
 * configuration does for the suites that are about something else.
 */
import { spawn } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { readChoices, type AutomaticChoice } from "./automaticChoice";
import { logger } from "./logger";
import { resolvePythonExecutable } from "./python";
import { findRepositoryRoot } from "./repoRoot";

/** `caterva.compose.read.read()`, as the API uses it. */
export interface SentenceReading {
  /** The words read as the enzyme, or null. */
  enzymeText: string | null;
  /** The EC number the enzyme was taken as, or null (none read, or refused). */
  ec: string | null;
  isoform: string | null;
  /** The organism named or chosen. */
  organism: string | null;
  organismText: string | null;
  substrate: string | null;
  inhibitor: string | null;
  /** The grammar rule the sentence builds: "michaelis_menten", "competitive_inhibition", ... */
  rule: string | null;
  /** What the sentence (or a flag) NAMED, as opposed to what was chosen. */
  named: { organism?: string; substrate?: string; inhibitor?: string };
  /** Every automatic choice, in the order made. */
  choices: AutomaticChoice[];
  /** Every other sentence compose's report carries about the reading. */
  notes: string[];
  /** Why nothing can be looked up for the sentence, or null. */
  refusal: string | null;
}

const _dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = findRepositoryRoot(_dirname);

/** BRENDA is read live for the choices: 5-30 s is usual. */
const READER_TIMEOUT_MS = 120_000;

const text = (value: unknown): string | null =>
  typeof value === "string" && value.trim() ? value : null;

/** The reader's JSON as a SentenceReading, or null when it is not one. */
export function parseReading(stdout: string): SentenceReading | null {
  let raw: Record<string, unknown>;
  try {
    const value: unknown = JSON.parse(stdout.trim());
    if (typeof value !== "object" || value === null || Array.isArray(value)) return null;
    raw = value as Record<string, unknown>;
  } catch {
    return null;
  }
  if ("error" in raw && !("ec" in raw)) return null;
  const namedRaw = (typeof raw.named === "object" && raw.named !== null ? raw.named : {}) as Record<
    string,
    unknown
  >;
  const named: SentenceReading["named"] = {};
  for (const key of ["organism", "substrate", "inhibitor"] as const) {
    const v = text(namedRaw[key]);
    if (v) named[key] = v;
  }
  return {
    enzymeText: text(raw.enzyme_text),
    ec: text(raw.ec),
    isoform: text(raw.isoform),
    organism: text(raw.organism),
    organismText: text(raw.organism_text),
    substrate: text(raw.substrate),
    inhibitor: text(raw.inhibitor),
    rule: text(raw.rule),
    named,
    choices: readChoices(raw.choices),
    notes: Array.isArray(raw.notes) ? raw.notes.filter((n): n is string => typeof n === "string") : [],
    refusal: text(raw.refusal),
  };
}

/**
 * Compose's reading of `query`, or null when the reader is off, could not
 * be run, or answered with something that is not a reading (said in the
 * log; the caller then reads the query the older way).
 */
export async function readSentence(query: string): Promise<SentenceReading | null> {
  const stand = process.env["CATERVA_SENTENCE_READER"];
  if (stand === "off") return null;
  const args = stand
    ? [stand, query, "--json"]
    : ["-m", "caterva.compose.read", query, "--json"];
  return new Promise((resolve) => {
    let stdout = "";
    let stderr = "";
    let settled = false;
    const done = (value: SentenceReading | null) => {
      if (!settled) {
        settled = true;
        resolve(value);
      }
    };
    let proc;
    try {
      proc = spawn(resolvePythonExecutable(REPO_ROOT), args, {
        cwd: REPO_ROOT,
        env: {
          ...process.env,
          PYTHONPATH: [process.env.PYTHONPATH, REPO_ROOT, path.join(REPO_ROOT, "Tests")]
            .filter(Boolean)
            .join(path.delimiter),
        },
      });
    } catch (err) {
      logger.warn({ err }, "sentence reader could not be started");
      done(null);
      return;
    }
    const timer = setTimeout(() => {
      logger.warn({ query }, "sentence reader timed out");
      proc.kill();
      done(null);
    }, READER_TIMEOUT_MS);
    proc.stdout.on("data", (chunk: Buffer) => {
      stdout += chunk.toString("utf-8");
    });
    proc.stderr.on("data", (chunk: Buffer) => {
      stderr += chunk.toString("utf-8");
    });
    proc.on("error", (err) => {
      clearTimeout(timer);
      logger.warn({ err }, "sentence reader could not be started");
      done(null);
    });
    proc.on("close", (code) => {
      clearTimeout(timer);
      // Exit 3 is a reading too: no enzyme, or a refusal it states.
      const reading = code === 0 || code === 3 ? parseReading(stdout) : null;
      if (reading === null) {
        logger.warn({ code, stderr: stderr.slice(-500) }, "sentence reader gave no reading");
      }
      done(reading);
    });
  });
}
