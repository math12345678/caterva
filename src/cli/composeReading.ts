/**
 * The question read the way `caterva compose` reads it, by compose itself.
 *
 * WHY THE CLI ASKS COMPOSE
 * ------------------------
 * The adversarial round of 2026-11-11 put the same sentences to the CLI,
 * compose and Caterva Studio. Compose and Studio read them with one reader;
 * the CLI had two of its own (a prepositional parser and a partial reader
 * that accepted a bare enzyme name and an organism, nothing more), and:
 *
 * - `simulate "hexokinase Michaelis-Menten kinetics" --resolve` and five
 *   other sentences compose measures were refused with "--resolve needs
 *   --substrate, --organism, and either --enzyme or --ec";
 * - "acetylcholinesterase inhibited by donepezil in human" was confirmed as
 *   the substrate "inhibited by donepezil", and the lookup timed out;
 * - "lactate dehydrogenase with pyruvate in human" was refused, where
 *   compose takes EC 1.1.1.27, the one candidate with human Km rows;
 * - with an inhibitor named and no organism, the organism was chosen for
 *   Km and kcat alone (human), and the Ki then could not be found, where
 *   compose chose Bos taurus, the organism with the inhibitor's Ki row.
 *
 * So the CLI asks `python -m caterva.compose.read`, which runs compose's own
 * reading (read_description, the enzyme policy, the ADR 0182 choosers) and
 * prints it as JSON. Nothing here reads a word of the question.
 *
 * `CATERVA_SENTENCE_READER` names a script run with the same arguments in
 * the reader's place (as CATERVA_DEFAULTS_RUNNER does for the chooser), so
 * tests are offline; "off" skips it, and the question is read by the CLI's
 * older readers (readSystem.ts), which is what the test setup does for the
 * suites about something else (src/testSupport/jestSetupEnv.ts).
 */
import { spawnSync } from 'child_process';
import * as path from 'path';

import { REPO_ROOT, resolvePythonExecutable } from '../engine/catervaBridge';
import type { AutomaticChoice } from './chooseMissing';

/** One choice, with compose's own sentence for it. */
export type ReadChoice = AutomaticChoice & { note?: string };

/** `caterva.compose.read.read()`. */
export interface ComposeReading {
  enzymeText: string | null;
  ec: string | null;
  isoform: string | null;
  organism: string | null;
  organismText: string | null;
  substrate: string | null;
  inhibitor: string | null;
  rule: string | null;
  tables: string[];
  named: { organism?: string; substrate?: string; inhibitor?: string };
  choices: ReadChoice[];
  notes: string[];
  refusal: string | null;
}

/** Flags that win over the sentence, exactly as they do for compose. */
export interface ReadFlags {
  subject?: string;
  organism?: string;
  substrate?: string;
  inhibitor?: string;
  isoform?: string;
  /** Read only: choose no organism, substrate or inhibitor. */
  noChoose?: boolean;
}

export type ReadAnswer =
  | { kind: 'read'; reading: ComposeReading }
  /** The reader is off, absent, crashed or timed out. */
  | { kind: 'unavailable'; reason: string; timedOut?: boolean };

/**
 * How long the reader may take. Choosing an organism reads every organism's
 * rows on the page: acetylcholinesterase has 63, and a reader that took five
 * minutes under load was cut off at 180 s, after which the older reader said
 * the question "needs an enzyme" (fifth round, XS5-01). Set
 * CATERVA_COMPOSE_READ_TIMEOUT_MS to change it.
 */
export function readerTimeoutMs(env: NodeJS.ProcessEnv = process.env): number {
  const raw = Number(env['CATERVA_COMPOSE_READ_TIMEOUT_MS']);
  return Number.isFinite(raw) && raw > 0 ? raw : 600_000;
}

const text = (value: unknown): string | null =>
  typeof value === 'string' && value.trim() ? value : null;

function isChoice(value: unknown): value is ReadChoice {
  const c = value as ReadChoice | null;
  return (
    typeof c === 'object' && c !== null && typeof c.chosen === 'string' && c.chosen.length > 0 &&
    typeof c.role === 'string' && typeof c.why === 'string' && Array.isArray(c.alternatives)
  );
}

/** The reader's JSON as a ComposeReading, or null. */
export function parseComposeReading(stdout: string): ComposeReading | null {
  let raw: Record<string, unknown>;
  try {
    const value: unknown = JSON.parse(stdout.trim());
    if (typeof value !== 'object' || value === null || Array.isArray(value)) return null;
    raw = value as Record<string, unknown>;
  } catch {
    return null;
  }
  if (!('ec' in raw)) return null;
  const namedRaw = (typeof raw['named'] === 'object' && raw['named'] !== null ? raw['named'] : {}) as Record<
    string,
    unknown
  >;
  const named: ComposeReading['named'] = {};
  for (const key of ['organism', 'substrate', 'inhibitor'] as const) {
    const v = text(namedRaw[key]);
    if (v) named[key] = v;
  }
  return {
    enzymeText: text(raw['enzyme_text']),
    ec: text(raw['ec']),
    isoform: text(raw['isoform']),
    organism: text(raw['organism']),
    organismText: text(raw['organism_text']),
    substrate: text(raw['substrate']),
    inhibitor: text(raw['inhibitor']),
    rule: text(raw['rule']),
    tables: Array.isArray(raw['tables']) ? raw['tables'].filter((t): t is string => typeof t === 'string') : [],
    named,
    choices: Array.isArray(raw['choices']) ? raw['choices'].filter(isChoice) : [],
    notes: Array.isArray(raw['notes']) ? raw['notes'].filter((n): n is string => typeof n === 'string') : [],
    refusal: text(raw['refusal']),
  };
}

/** Compose's reading of `sentence` with `flags`. Never throws. */
export function readWithCompose(sentence: string, flags: ReadFlags = {}): ReadAnswer {
  const stand = process.env['CATERVA_SENTENCE_READER'];
  if (stand === 'off') return { kind: 'unavailable', reason: 'the sentence reader is off' };
  const args = [sentence, '--json'];
  for (const [flag, value] of [
    ['--subject', flags.subject], ['--organism', flags.organism], ['--substrate', flags.substrate],
    ['--inhibitor', flags.inhibitor], ['--isoform', flags.isoform],
  ] as const) {
    if (value) args.push(flag, value);
  }
  if (flags.noChoose) args.push('--no-choose');
  const argv = stand ? [stand, ...args] : ['-m', 'caterva.compose.read', ...args];
  const proc = spawnSync(resolvePythonExecutable(REPO_ROOT), argv, {
    cwd: REPO_ROOT,
    encoding: 'utf-8',
    // BRENDA is fetched live for the choices: 5-60 s is usual.
    timeout: readerTimeoutMs(),
    env: {
      ...process.env,
      PYTHONPATH: [process.env['PYTHONPATH'], REPO_ROOT, path.join(REPO_ROOT, 'Tests')]
        .filter(Boolean)
        .join(path.delimiter),
    },
  });
  // Exit 3 is a reading too: no enzyme, or a refusal it states.
  const reading = proc.status === 0 || proc.status === 3 ? parseComposeReading(proc.stdout ?? '') : null;
  if (reading) return { kind: 'read', reading };
  const code = (proc.error as NodeJS.ErrnoException | undefined)?.code;
  if (code === 'ETIMEDOUT') {
    const seconds = Math.round(readerTimeoutMs() / 1000);
    return {
      kind: 'unavailable',
      timedOut: true,
      reason: `it did not finish within ${seconds} s; set CATERVA_COMPOSE_READ_TIMEOUT_MS to wait longer`,
    };
  }
  const why = ((proc.stderr || proc.stdout || '') + (proc.error ? String(proc.error) : '')).trim().split('\n').pop();
  // A reader killed from outside has no exit status, only a signal: say
  // that, not "exited null" (sixth round, XS5R2-09).
  const how = proc.signal
    ? `the reader was stopped by a signal (${proc.signal})`
    : `the reader exited with status ${proc.status}`;
  return { kind: 'unavailable', reason: why || how };
}

/** The --model a sentence's rule is, when the CLI has one for it. */
export const MODEL_OF_RULE: Record<string, 'mm' | 'competitive' | 'noncompetitive' | 'product'> = {
  michaelis_menten: 'mm',
  competitive_inhibition: 'competitive',
  noncompetitive_inhibition: 'noncompetitive',
  product_inhibition: 'product',
};

/** The sentence to read when the question names no mechanism the grammar builds. */
export const SENTENCE_OF_MODEL: Record<string, string> = {
  mm: 'Michaelis-Menten',
  competitive: 'Michaelis-Menten with a competitive inhibitor',
  noncompetitive: 'noncompetitive inhibition',
  product: 'product inhibition',
};

/** Compose's notes that say a flag and the sentence named different things. */
export function contradictions(reading: ComposeReading): string[] {
  return reading.notes.filter((n) => /because a flag wins over (?:the description|what )/.test(n));
}
