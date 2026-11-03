/**
 * The system a question names, read with the shared Python tables.
 *
 * WHY THIS IS NOT IN suggestResolveCommand.ts
 * -------------------------------------------
 * `parseSystemFromQuery` is a pure, offline reader anchored on prepositions
 * ("X on Y in Z"). Two things it cannot do without a second copy of a table
 * this repository already keeps in one place:
 *
 *   1. Know that "humans" is Homo sapiens. BRENDA is indexed by binomial, and
 *      "hexokinase on glucose in humans" was refused as "BRENDA holds this km
 *      only for other organisms (... Homo sapiens ...)" -- the organism
 *      asked for, listed as somebody else's. The normaliser is
 *      caterva.enzymes.index (organism_code / organism_binomial), the one
 *      `caterva enzymes`, the finder and the literature runner all read.
 *
 *   2. Bound an enzyme name without prepositions. "hexokinase glucose
 *      human" has no word that says where the enzyme ends; only the enzyme
 *      nomenclature does (caterva.enzymes.question).
 *
 * A TypeScript copy of either table is the duplicated-source-of-truth
 * defect this project keeps writing ADRs about. So this asks Python, the
 * way every literature lookup already does, and treats a failure to ask as
 * "not read" rather than as a reading: the organism then goes through as
 * typed (the runner canonicalises it again on its side), and an unparsed
 * question falls back to the template it always got. Nothing here resolves
 * or cites anything; confirmSystem still shows the reading and waits.
 */
import { spawnSync } from 'child_process';
import * as path from 'path';

import { REPO_ROOT, resolvePythonExecutable } from '../engine/catervaBridge';
import { parseSystemFromQuery, type ParsedSystem } from './suggestResolveCommand';

const SCRIPT = 'from caterva.enzymes.question import main; main()';

function ask(payload: Record<string, string>): Record<string, unknown> | null {
  const proc = spawnSync(resolvePythonExecutable(REPO_ROOT), ['-c', SCRIPT], {
    cwd: REPO_ROOT,
    input: JSON.stringify(payload),
    encoding: 'utf-8',
    timeout: 60_000,
    env: {
      ...process.env,
      PYTHONPATH: [process.env['PYTHONPATH'], REPO_ROOT].filter(Boolean).join(path.delimiter),
    },
  });
  if (proc.status !== 0 || !proc.stdout) return null;
  try {
    return JSON.parse(proc.stdout) as Record<string, unknown>;
  } catch {
    return null;
  }
}

/** The organism as BRENDA files it, and what was typed when that differs. */
export function canonicalOrganism(typed: string): { organism: string; typed?: string } {
  const out = ask({ organism: typed });
  const organism = typeof out?.['organism'] === 'string' ? (out['organism'] as string) : typed;
  return organism === typed ? { organism } : { organism, typed };
}

function withCanonicalOrganism(system: ParsedSystem): ParsedSystem {
  const { organism, typed } = canonicalOrganism(system.organism);
  return typed === undefined ? system : { ...system, organism, organismTyped: typed };
}

/**
 * `parseSystemFromQuery` first (offline, the prepositional phrasings), then
 * the nomenclature-bounded orderings; the organism canonicalised either way.
 */
export function readSystemFromQuery(query: string): ParsedSystem | null {
  const parsed = parseSystemFromQuery(query);
  if (parsed) return withCanonicalOrganism(parsed);
  const out = ask({ query });
  const system = out?.['system'] as Record<string, unknown> | null | undefined;
  if (
    !system ||
    typeof system['enzyme'] !== 'string' ||
    typeof system['substrate'] !== 'string' ||
    typeof system['organism'] !== 'string'
  ) {
    return null;
  }
  const typed = typeof system['typed'] === 'string' ? (system['typed'] as string) : undefined;
  return {
    enzyme: system['enzyme'] as string,
    substrate: system['substrate'] as string,
    organism: system['organism'] as string,
    ...(typed !== undefined && typed !== system['organism'] ? { organismTyped: typed } : {}),
  };
}
