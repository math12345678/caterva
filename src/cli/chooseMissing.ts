/**
 * Ask the engine's chooser for a substrate, inhibitor or organism the
 * question did not name (ADR 0182).
 *
 * WHY THE CLI CHOOSES NOW
 * -----------------------
 * `simulate --resolve` and `resolve` refused when the substrate or the
 * organism was missing: "--resolve needs --substrate, --organism, and
 * either --enzyme or --ec". The reason was sound -- a Km is the constant of
 * one substrate, and a lookup without one returns whichever row comes
 * first -- and it left a student who typed "hexokinase in humans" with no
 * numbers at all while BRENDA held 25 measured glucose rows.
 *
 * The rule since ADR 0182: choose the best-measured REAL option from
 * BRENDA, show the choice (what, why, and the alternatives with their row
 * counts), and proceed with it. The choosing is the engine's, in one place
 * (caterva.compose.defaults); this file runs it, reads its JSON and words
 * it. Nothing here counts a row or ranks a name.
 *
 * The chooser's CLI contract:
 *
 *   python -m caterva.compose.defaults --ec EC [--organism ORG]
 *       [--substrate S] [--role substrate|inhibitor|organism] --json
 *   -> {"choice": <Choice json or null>, "note": "..."}
 *   exit 0 when a choice exists, 3 when BRENDA has nothing usable.
 *
 * `CATERVA_DEFAULTS_RUNNER` names a script run with the same arguments in
 * its place, the way CATERVA_LITERATURE_RUNNER stands in for the literature
 * runner: so the CLI's tests are offline and never ask BRENDA.
 */
import { spawnSync } from 'child_process';
import * as path from 'path';

import { REPO_ROOT, resolvePythonExecutable } from '../engine/catervaBridge';

export type ChoiceRole = 'substrate' | 'inhibitor' | 'organism';

/** One alternative the chooser counted, with BRENDA's rows per table. */
export interface ChoiceOption {
  name: string;
  rows: Record<string, number>;
}

/** caterva.compose.defaults.Choice.to_json(). */
export interface AutomaticChoice {
  role: ChoiceRole | 'enzyme';
  chosen: string;
  why: string;
  alternatives: ChoiceOption[];
  considered: number;
}

export type ChooserAnswer =
  /** A real option was chosen. `note` is the chooser's own sentence. */
  | { kind: 'chosen'; choice: AutomaticChoice; note: string }
  /** Exit 3: BRENDA holds nothing usable. `note` says what is missing. */
  | { kind: 'nothing'; note: string }
  /** The chooser could not be asked (absent, crashed, unreadable). */
  | { kind: 'unavailable'; reason: string };

export interface ChooserQuestion {
  ec: string;
  role: ChoiceRole;
  organism?: string;
  /** For an organism or an inhibitor: the substrate already named. */
  substrate?: string;
}

/** What spawning returned; a seam so tests need no Python. */
export interface ChooserProcess {
  status: number | null;
  stdout: string;
  stderr: string;
}

export type ChooserRunner = (args: string[]) => ChooserProcess;

/** The real chooser, or the CATERVA_DEFAULTS_RUNNER stand-in. */
export const spawnChooser: ChooserRunner = (args) => {
  const stand = process.env['CATERVA_DEFAULTS_RUNNER'];
  const argv = stand ? [stand, ...args] : ['-m', 'caterva.compose.defaults', ...args];
  const proc = spawnSync(resolvePythonExecutable(REPO_ROOT), argv, {
    cwd: REPO_ROOT,
    encoding: 'utf-8',
    // BRENDA is fetched live: 5-30 s is usual.
    timeout: 120_000,
    env: {
      ...process.env,
      PYTHONPATH: [process.env['PYTHONPATH'], REPO_ROOT].filter(Boolean).join(path.delimiter),
    },
  });
  return {
    status: proc.status,
    stdout: proc.stdout ?? '',
    stderr: proc.stderr ?? (proc.error ? String(proc.error) : ''),
  };
};

function isChoice(value: unknown): value is AutomaticChoice {
  const c = value as AutomaticChoice | null;
  return (
    typeof c === 'object' &&
    c !== null &&
    typeof c.chosen === 'string' &&
    c.chosen.length > 0 &&
    typeof c.role === 'string' &&
    typeof c.why === 'string' &&
    Array.isArray(c.alternatives)
  );
}

/** The chooser's JSON document: its last stdout line, or null. */
function lastJsonLine(stdout: string): { choice?: unknown; note?: unknown } | null {
  try {
    const value: unknown = JSON.parse(stdout.trim().split('\n').pop() ?? '');
    return typeof value === 'object' && value !== null ? (value as { choice?: unknown; note?: unknown }) : null;
  } catch {
    return null;
  }
}

/** Ask the chooser one question. Never throws: an error is `unavailable`. */
export function askChooser(
  question: ChooserQuestion,
  run: ChooserRunner = spawnChooser,
): ChooserAnswer {
  const args = ['--ec', question.ec, '--role', question.role, '--json'];
  if (question.organism) args.push('--organism', question.organism);
  if (question.substrate) args.push('--substrate', question.substrate);
  const proc = run(args);
  const parsed = lastJsonLine(proc.stdout);
  const note = typeof parsed?.note === 'string' ? parsed.note : '';
  if (proc.status === 0 && parsed && isChoice(parsed.choice)) {
    return { kind: 'chosen', choice: parsed.choice, note };
  }
  if (proc.status === 3) {
    return { kind: 'nothing', note };
  }
  // Exit 1 from `python -m` of a module that does not exist yet, a crash,
  // or a timeout. Reported as not asked -- never as "BRENDA has nothing".
  const why = (proc.stderr || proc.stdout).trim().split('\n').pop() ?? '';
  return { kind: 'unavailable', reason: why || `chooser exited ${proc.status}` };
}

const TABLE_LABEL: Record<string, string> = { km: 'Km', kcat: 'kcat', ki: 'Ki' };

/** "ATP (Km 106 rows), D-mannose (Km 9 rows)". */
export function describeAlternatives(alternatives: readonly ChoiceOption[], shown = 5): string {
  const listed = alternatives.slice(0, shown).map((a) => {
    const rows = Object.entries(a.rows)
      .map(([t, n]) => `${TABLE_LABEL[t] ?? t} ${n} row${n === 1 ? '' : 's'}`)
      .join(', ');
    return rows ? `${a.name} (${rows})` : a.name;
  });
  const more = alternatives.length - listed.length;
  return listed.join(', ') + (more > 0 ? `, and ${more} more` : '');
}

/** The flag that chooses the role yourself. */
const FLAG: Record<ChoiceRole | 'enzyme', string> = {
  substrate: '--substrate',
  inhibitor: '--inhibitor',
  organism: '--organism',
  enzyme: '--ec',
};

/**
 * The confirmation line, e.g.
 *
 *   No substrate named; using D-glucose (most Km and kcat rows in Homo
 *   sapiens). Others: ATP (Km 106 rows), D-mannose (Km 9 rows). Pass
 *   --substrate to use one of them.
 */
export function describeChoice(choice: AutomaticChoice): string {
  const why = choice.why.trim().replace(/[.\s]+$/, '');
  const others = describeAlternatives(choice.alternatives);
  return (
    `No ${choice.role} named; using ${choice.chosen} (${why}). ` +
    (others ? `Others: ${others}. ` : 'No other candidate had usable rows. ') +
    `Pass ${FLAG[choice.role] ?? `--${choice.role}`} to use another.`
  );
}

/** What the question and the flags named, before anything is chosen. */
export interface NamedParts {
  enzyme?: string;
  ec?: string;
  ecName?: string;
  organism?: string;
  organismTyped?: string;
  substrate?: string;
}

export type Completed =
  /** Every part named or chosen; `choices` lists the chosen ones. */
  | {
      kind: 'complete';
      system: {
        enzyme: string;
        substrate: string;
        organism: string;
        organismTyped?: string;
        ec?: string;
        ecName?: string;
        choices: AutomaticChoice[];
      };
    }
  /** The chooser answered that BRENDA has nothing usable for `role`. */
  | { kind: 'nothing'; role: ChoiceRole; note: string }
  /** Nothing could be chosen: no EC number, or the chooser was not there. */
  | { kind: 'not-chosen'; reason: string };

/**
 * Fill the organism, then the substrate, from the chooser.
 *
 * The organism first, told the substrate when one was named, so the
 * substrate is then counted in the organism the value will come from -- the
 * order the API's runner chooses in too (science_agent_runner.choose_missing).
 * An EC number is required: the chooser counts one enzyme's rows, and an
 * enzyme name that is not one EC offline is not a question it can answer.
 */
export function completeByChoosing(
  named: NamedParts,
  run: ChooserRunner = spawnChooser,
): Completed {
  if (!named.ec) {
    return { kind: 'not-chosen', reason: 'the enzyme is not one EC number offline' };
  }
  const choices: AutomaticChoice[] = [];
  let organism = named.organism;
  if (!organism) {
    const answer = askChooser(
      { ec: named.ec, role: 'organism', ...(named.substrate ? { substrate: named.substrate } : {}) },
      run,
    );
    if (answer.kind === 'nothing') return { kind: 'nothing', role: 'organism', note: answer.note };
    if (answer.kind === 'unavailable') return { kind: 'not-chosen', reason: answer.reason };
    organism = answer.choice.chosen;
    choices.push(answer.choice);
  }
  let substrate = named.substrate;
  if (!substrate) {
    const answer = askChooser({ ec: named.ec, role: 'substrate', organism }, run);
    if (answer.kind === 'nothing') return { kind: 'nothing', role: 'substrate', note: answer.note };
    if (answer.kind === 'unavailable') return { kind: 'not-chosen', reason: answer.reason };
    substrate = answer.choice.chosen;
    choices.push(answer.choice);
  }
  return {
    kind: 'complete',
    system: {
      enzyme: named.enzyme ?? `EC ${named.ec}`,
      substrate,
      organism,
      ...(named.organism && named.organismTyped ? { organismTyped: named.organismTyped } : {}),
      ec: named.ec,
      ...(named.ecName ? { ecName: named.ecName } : {}),
      choices,
    },
  };
}
