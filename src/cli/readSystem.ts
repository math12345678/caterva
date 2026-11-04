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

function identityOf(out: Record<string, unknown> | null): { ec?: string; ecName?: string } {
  const identity = out?.['identity'] as Record<string, unknown> | null | undefined;
  if (!identity || typeof identity['ec'] !== 'string') return {};
  return {
    ec: identity['ec'] as string,
    ...(typeof identity['name'] === 'string' ? { ecName: identity['name'] as string } : {}),
  };
}

function withCanonicalOrganism(system: ParsedSystem): ParsedSystem {
  // One Python call for both: the binomial, and the EC the enzyme name
  // resolves to under it, which the confirmation shows.
  const out = ask({ organism: system.organism, enzyme: system.enzyme });
  const organism = typeof out?.['organism'] === 'string' ? (out['organism'] as string) : system.organism;
  return {
    ...system,
    organism,
    ...(organism !== system.organism ? { organismTyped: system.organism } : {}),
    ...identityOf(out),
  };
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
    ...identityOf(out),
  };
}

/** Flags typed alongside a question that names a system. */
export interface GivenFlags {
  enzyme?: string;
  substrate?: string;
  organism?: string;
  ec?: string;
}

const same = (a: string, b: string): boolean =>
  a.trim().replace(/\s+/g, ' ').toLowerCase() === b.trim().replace(/\s+/g, ' ').toLowerCase();

/**
 * Every flag the sentence's reading contradicts, as "--organism human, but
 * the question says mouse (Mus musculus)". Empty when they agree.
 *
 * WHY THIS IS A REFUSAL AND NOT A PRECEDENCE RULE
 * -----------------------------------------------
 * `simulate "hexokinase glucose mouse" --organism human --resolve --yes`
 * replaced all three names with the sentence's, dropped `--organism human`
 * without a word, and cited BRENDA refs 758915 and 674800 -- mouse
 * measurements -- for a run whose command line said human (found
 * 2026-11-03). Either choice made silently is a citation for a system one
 * of the two inputs did not name, so neither is made: the run stops and
 * names both. `organismOfFlag` is the flag's canonical binomial, so
 * `--organism human` agrees with a sentence that says "humans".
 */
export function flagsContradicting(
  parsed: ParsedSystem,
  given: GivenFlags,
  organismOfFlag: (typed: string) => string,
): string[] {
  const out: string[] = [];
  if (given.enzyme !== undefined && !same(given.enzyme, parsed.enzyme)) {
    out.push(`--enzyme "${given.enzyme}", but the question says "${parsed.enzyme}"`);
  }
  if (given.substrate !== undefined && !same(given.substrate, parsed.substrate)) {
    out.push(`--substrate "${given.substrate}", but the question says "${parsed.substrate}"`);
  }
  if (given.organism !== undefined && !same(organismOfFlag(given.organism), parsed.organism)) {
    const said = parsed.organismTyped !== undefined
      ? `"${parsed.organismTyped}" (${parsed.organism})`
      : `"${parsed.organism}"`;
    out.push(`--organism "${given.organism}", but the question says ${said}`);
  }
  if (given.ec !== undefined && parsed.ec !== undefined && !same(given.ec, parsed.ec)) {
    out.push(`--ec ${given.ec}, but "${parsed.enzyme}" in the question is EC ${parsed.ec}` +
      (parsed.ecName ? ` (${parsed.ecName})` : ''));
  }
  return out;
}
