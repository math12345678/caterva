/**
 * `simulate --resolve` looks each constant up the way BRENDA files it.
 *
 * WHAT WAS WRONG
 * --------------
 * An inhibition model's Ki was looked up under the SUBSTRATE's name, with no
 * inhibitor and no mode:
 *
 *     resolveKinetic({ ..., substrate: options.substrate, quantity: 'ki' })
 *
 * BRENDA files a Ki under its inhibitor, so the lookup asked for a Ki "of"
 * pyruvate and came back with one, or with nothing. `caterva compose` stopped
 * doing this on 2026-09-29 (each constant under its own compound) and the API
 * the same day (queryResolver: a Ki under the inhibitor the query names, none
 * looked up when it names none); since 2026-09-30 the API also sends its
 * model's inhibition mode. This was the third front door, still asking the
 * old way.
 *
 * And `--allow-cross-species`, documented for this command and suggested by
 * every one of its literature refusals, never reached a lookup at all.
 *
 * HOW IT IS TESTED
 * ----------------
 * The resolver is mocked at the module boundary and the tests assert what
 * each lookup SENDS: the payload is where both defects lived, and a fake
 * answer cannot hide a wrong question. The runs are made to stop at the
 * refusal (no `--s0`), so nothing reaches the engine; what the refusal says
 * is asserted from the `--json` document, which is the one output a script
 * reads. The Ki the runner actually chooses for a mode is tested on the
 * committed BRENDA pages in Tests/test_ki_mode_resolution.py, not here.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { ResolverQuery, ResolverResult } from '../../literature/literatureResolver';

vi.mock('../../literature/literatureResolver', async (importOriginal) => {
  const original = await importOriginal<typeof import('../../literature/literatureResolver')>();
  return { ...original, resolveKinetic: vi.fn() };
});

import { resolveKinetic } from '../../literature/literatureResolver';
import { commandSimulateResolved, type SimulateResolvedOptions } from '../commandSimulateResolved';

const NOTHING = (quantity: 'km' | 'ki' | 'kcat'): ResolverResult => ({
  found: false,
  quantity,
  logs: [],
  candidates: [],
  source: 'not_found',
  isoformsAvailable: [],
  variantCandidatesAvailable: [],
  crossSpeciesOrganismsAvailable: [],
  modesAvailable: [],
});

const LDH: SimulateResolvedOptions = {
  ec: '1.1.1.27',
  substrate: 'pyruvate',
  organism: 'Homo sapiens',
  // Km and Vmax supplied, so the only lookup a model makes is its Ki.
  overrides: { km: '0.1mM', vmax: '0.01mM/s' },
  json: true,
};

let out: string[];

beforeEach(() => {
  out = [];
  vi.mocked(resolveKinetic).mockReset();
  vi.spyOn(process.stdout, 'write').mockImplementation(((chunk: string) => {
    out.push(String(chunk));
    return true;
  }) as typeof process.stdout.write);
  vi.spyOn(process.stderr, 'write').mockImplementation(((chunk: string) => {
    out.push(String(chunk));
    return true;
  }) as typeof process.stderr.write);
});

afterEach(() => {
  vi.restoreAllMocks();
});

/** Every query the command sent the resolver, in order. */
const sent = (): ResolverQuery[] =>
  vi.mocked(resolveKinetic).mock.calls.map((call) => call[0]);

/** The one `--json` document the run wrote. */
const document = (): { ok: boolean; status: string; unresolved: string[] } =>
  JSON.parse(out.join(''));

describe('--allow-cross-species reaches every lookup', () => {
  it('is sent with the Km and the kcat lookup when given', async () => {
    vi.mocked(resolveKinetic).mockImplementation(async (q) => NOTHING(q.quantity ?? 'km'));
    await commandSimulateResolved({
      ...LDH,
      overrides: {},
      enzymeConc: '0.001mM',
      allowCrossSpecies: true,
    });
    const queries = sent();
    expect(queries.map((q) => q.quantity)).toEqual(['km', 'kcat']);
    for (const q of queries) expect(q.allowCrossSpecies).toBe(true);
  });

  it('is sent as false when not given, never left to a default', async () => {
    vi.mocked(resolveKinetic).mockImplementation(async (q) => NOTHING(q.quantity ?? 'km'));
    await commandSimulateResolved({ ...LDH, overrides: {}, enzymeConc: '0.001mM' });
    for (const q of sent()) expect(q.allowCrossSpecies).toBe(false);
  });
});
