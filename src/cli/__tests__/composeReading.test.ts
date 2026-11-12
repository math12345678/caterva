/**
 * The CLI reads a question the way `caterva compose` does (composeReading.ts).
 *
 * Each sentence here was misread or refused by the CLI's own readers in the
 * adversarial round of 2026-11-11, while compose and Studio measured it:
 *
 * - "acetylcholinesterase inhibited by donepezil in human" was confirmed as
 *   the substrate "inhibited by donepezil", and the lookup timed out;
 * - "hexokinase Michaelis-Menten kinetics" (and five more) were refused with
 *   "--resolve needs --substrate, --organism, and either --enzyme or --ec",
 *   contradicting the help, which says what is left out is chosen;
 * - "lactate dehydrogenase with pyruvate in human" was refused, and `resolve
 *   "lactate dehydrogenase"` (the help's own example) said BRENDA and PubMed
 *   "were searched and returned nothing" though nothing was searched.
 *
 * Spawns the real binary, offline: compose's reader is a stand-in
 * (CATERVA_SENTENCE_READER) answering in the real one's shape with what it
 * printed for these sentences against live BRENDA, and the literature runner
 * a stand-in that records what it was asked. The reader itself is pinned by
 * caterva/tests/test_compose_read.py.
 */
import { spawnSync } from 'child_process';
import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';

import { contradictions, parseComposeReading } from '../composeReading';

const REPO_ROOT = path.resolve(__dirname, '..', '..', '..');
const CLI = path.join(REPO_ROOT, 'src', 'cli', 'scientificCLI.ts');
const TS_NODE = path.join(REPO_ROOT, 'node_modules', '.bin', 'ts-node');

jest.setTimeout(180_000);

const choice = (role: string, chosen: string, why: string) => ({
  role, chosen, why, alternatives: [{ name: 'other', rows: { km: 1 } }], considered: 2, note: `${role} note`,
});
const reading = (fields: Record<string, unknown>) => ({
  description: '', enzyme_text: null, ec: null, isoform: null, organism: null, organism_text: null,
  substrate: null, inhibitor: null, rule: null, tables: [], named: {}, choices: [], notes: [], refusal: null,
  ...fields,
});

/** What the real reader printed for each sentence (2026-11-11, live BRENDA), trimmed. */
const READINGS: Record<string, unknown> = {
  'acetylcholinesterase inhibited by donepezil in human': reading({
    enzyme_text: 'acetylcholinesterase', ec: '3.1.1.7', organism: 'Homo sapiens', organism_text: 'human',
    substrate: 'acetylthiocholine', inhibitor: 'donepezil', rule: 'competitive_inhibition',
    tables: ['km', 'kcat', 'ki'], named: { organism: 'Homo sapiens', inhibitor: 'donepezil' },
    choices: [choice('substrate', 'acetylthiocholine', 'it has the most Km and kcat rows')],
  }),
  'chymotrypsin follows Michaelis-Menten kinetics': reading({
    enzyme_text: 'chymotrypsin', ec: '3.4.21.1', organism: 'Homo sapiens',
    substrate: 'L-alanyl-L-alanyl-L-prolyl-L-phenylalanine p-nitroanilide', rule: 'michaelis_menten',
    tables: ['km', 'kcat'],
    choices: [choice('organism', 'Homo sapiens', 'it covers Km and kcat'),
      choice('substrate', 'L-alanyl-L-alanyl-L-prolyl-L-phenylalanine p-nitroanilide', 'most rows')],
  }),
  'lactate dehydrogenase with pyruvate in human': reading({
    enzyme_text: 'lactate dehydrogenase', ec: '1.1.1.27', organism: 'Homo sapiens', organism_text: 'human',
    substrate: 'pyruvate', rule: 'michaelis_menten', tables: ['km', 'kcat'],
    named: { organism: 'Homo sapiens', substrate: 'pyruvate' },
    choices: [choice('enzyme', '1.1.1.27', "your description names 'lactate dehydrogenase', which is not one enzyme; L-lactate dehydrogenase is used because it is the only one with Km rows in Homo sapiens")],
  }),
  'lactate dehydrogenase': reading({
    enzyme_text: 'lactate dehydrogenase', ec: '1.1.1.27', organism: 'Homo sapiens', rule: 'michaelis_menten',
    choices: [choice('enzyme', '1.1.1.27', "your description names 'lactate dehydrogenase', which is not one enzyme; L-lactate dehydrogenase is used because it is the only one with Km rows in Homo sapiens")],
  }),
  'the spread of measles in a school': reading({ refusal: 'No shape in this grammar matches.' }),
};

let dir: string;
beforeAll(() => {
  dir = fs.mkdtempSync(path.join(os.tmpdir(), 'caterva-compose-reading-'));
});
afterAll(() => {
  fs.rmSync(dir, { recursive: true, force: true });
});

function script(name: string, lines: string[]): string {
  const file = path.join(dir, `${name}_${Math.random().toString(36).slice(2)}.py`);
  fs.writeFileSync(file, lines.join('\n') + '\n', 'utf-8');
  return file;
}

/** compose's reader: records its arguments, answers from READINGS. */
function reader(record: string): string {
  return script('reader', [
    'import sys, json',
    `open(${JSON.stringify(record)}, "a").write(json.dumps(sys.argv[1:]) + "\\n")`,
    `readings = json.loads(${JSON.stringify(JSON.stringify(READINGS))})`,
    'r = readings[sys.argv[1]]',
    'print(json.dumps(r))',
    'sys.exit(0 if r["ec"] and not r["refusal"] else 3)',
  ]);
}

/** The literature runner: records what it was asked, finds nothing. */
function literature(record: string, source = 'not_found'): string {
  return script('literature', [
    'import sys, json',
    'p = json.loads(sys.stdin.read())',
    `open(${JSON.stringify(record)}, "a").write(json.dumps(p) + "\\n")`,
    `sys.stdout.write(json.dumps({"ok": True, "found": False, "source": ${JSON.stringify(source)}, "logs": ["stopped"], "literatureCandidates": []}))`,
  ]);
}

function lines(file: string): Array<Record<string, unknown>> {
  return fs.existsSync(file)
    ? fs.readFileSync(file, 'utf-8').trim().split('\n').filter(Boolean).map((l) => JSON.parse(l))
    : [];
}

function run(args: string[], env: NodeJS.ProcessEnv): { out: string; code: number } {
  const proc = spawnSync(TS_NODE, [CLI, ...args], {
    cwd: REPO_ROOT,
    env: { ...process.env, ...env },
    encoding: 'utf-8',
    timeout: 150_000,
  });
  return { out: (proc.stdout ?? '') + (proc.stderr ?? ''), code: proc.status ?? 1 };
}

const SIM = ['--resolve', '--yes', '--s0', '10mM', '--enzyme-conc', '0.001mM'];

describe('simulate --resolve reads the question as compose does', () => {
  it('reads "inhibited by donepezil" as the inhibitor, and looks the Ki up under it', () => {
    const looked = path.join(dir, 'donepezil.jsonl');
    const { out } = run(['simulate', 'acetylcholinesterase inhibited by donepezil in human', ...SIM], {
      CATERVA_SENTENCE_READER: reader(path.join(dir, 'donepezil-read.jsonl')),
      CATERVA_LITERATURE_RUNNER: literature(looked),
    });
    expect(out).not.toMatch(/substrate\s+inhibited by donepezil/);
    expect(out).toMatch(/substrate\s+acetylthiocholine/);
    const asked = lines(looked);
    const km = asked.find((p) => p['quantity'] === 'km');
    const ki = asked.find((p) => p['quantity'] === 'ki');
    expect(km?.['substrate']).toBe('acetylthiocholine');
    expect(ki?.['substrate']).toBe('donepezil');
    expect(asked.every((p) => p['ecNumber'] === '3.1.1.7' && p['organism'] === 'Homo sapiens')).toBe(true);
  });

  it('runs a sentence the old reader refused, for the EC number compose read', () => {
    const looked = path.join(dir, 'chymo.jsonl');
    const { out } = run(['simulate', 'chymotrypsin follows Michaelis-Menten kinetics', ...SIM], {
      CATERVA_SENTENCE_READER: reader(path.join(dir, 'chymo-read.jsonl')),
      CATERVA_LITERATURE_RUNNER: literature(looked),
    });
    expect(out).not.toContain('could not settle the system');
    const asked = lines(looked);
    expect(asked.length).toBeGreaterThan(0);
    expect(asked.every((p) => p['ecNumber'] === '3.4.21.1')).toBe(true);
  });

  it('takes the lactate dehydrogenase compose singles out, sends its EC number, and says so', () => {
    const looked = path.join(dir, 'ldh.jsonl');
    const { out } = run(['simulate', 'lactate dehydrogenase with pyruvate in human', ...SIM], {
      CATERVA_SENTENCE_READER: reader(path.join(dir, 'ldh-read.jsonl')),
      CATERVA_LITERATURE_RUNNER: literature(looked),
    });
    expect(out).toContain('Using EC 1.1.1.27: your description names');
    expect(lines(looked).every((p) => p['ecNumber'] === '1.1.1.27' && p['substrate'] === 'pyruvate')).toBe(true);
  });

  it("says compose's reason when nothing can be read, not that flags are required", () => {
    const { out, code } = run(['simulate', 'the spread of measles in a school', '--resolve', '--yes'], {
      CATERVA_SENTENCE_READER: reader(path.join(dir, 'measles-read.jsonl')),
    });
    expect(code).toBe(1);
    expect(out).toContain('No shape in this grammar matches.');
    expect(out).not.toContain('could not settle the system');
  });

  it('passes the flags to the reader, which lets them win', () => {
    const record = path.join(dir, 'flags-read.jsonl');
    run(['simulate', 'chymotrypsin follows Michaelis-Menten kinetics', ...SIM, '--organism', 'Bos taurus'], {
      CATERVA_SENTENCE_READER: reader(record),
      CATERVA_LITERATURE_RUNNER: literature(path.join(dir, 'flags.jsonl')),
    });
    const args = lines(record)[0] as unknown as string[];
    expect(args.slice(args.indexOf('--organism'), args.indexOf('--organism') + 2)).toEqual(['--organism', 'Bos taurus']);
  });
});

describe('resolve takes the enzyme BRENDA singles out', () => {
  it('sends EC 1.1.1.27 for "lactate dehydrogenase", with the choice said first', () => {
    const looked = path.join(dir, 'resolve-ldh.jsonl');
    const { out } = run(['resolve', 'lactate dehydrogenase', '--substrate', 'pyruvate', '--organism', 'Homo sapiens'], {
      CATERVA_SENTENCE_READER: reader(path.join(dir, 'resolve-read.jsonl')),
      CATERVA_LITERATURE_RUNNER: literature(looked),
    });
    expect(out).toContain('Using EC 1.1.1.27');
    expect(lines(looked)[0]?.['ecNumber']).toBe('1.1.1.27');
  });

  it('does not say BRENDA was searched when the lookup stopped at the name', () => {
    const { out } = run(['resolve', 'some enzyme', '--ec', '9.9.9.9', '--substrate', 'x', '--organism', 'Homo sapiens'], {
      CATERVA_LITERATURE_RUNNER: literature(path.join(dir, 'stopped.jsonl'), 'ec_ambiguous'),
    });
    expect(out).toContain('Nothing was searched: the lookup stopped at the enzyme name');
    expect(out).not.toContain('were searched and returned nothing');
  });
});

describe('parseComposeReading', () => {
  it('reads the shape, and finds the notes where a flag overrode the question', () => {
    const r = parseComposeReading(JSON.stringify(reading({
      ec: '2.7.1.1', notes: ["Your description names 'human' (Homo sapiens); --organism Mus musculus was used, because a flag wins over the description."],
    })));
    expect(r?.ec).toBe('2.7.1.1');
    expect(contradictions(r!)).toHaveLength(1);
    expect(parseComposeReading('Traceback (most recent call last)')).toBeNull();
  });
});
