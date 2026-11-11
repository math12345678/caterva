/**
 * What the CLI does with the engine's chooser (ADR 0182).
 *
 * `simulate --resolve` and `resolve` refused when the question named the
 * enzyme but not the substrate or the organism. Since ADR 0182 the engine's
 * chooser (caterva.compose.defaults) picks the best-measured real option
 * from BRENDA, and the CLI shows the choice -- what, why, the alternatives
 * with their row counts -- before anything is cited. These pin the CLI's
 * half: how it asks, how it reads the three answers, and how it words them.
 * The chooser itself is stubbed: it is the engine's, tested there.
 */
import { askChooser, completeByChoosing, describeChoice, type AutomaticChoice, type ChooserRunner } from '../chooseMissing';
import { describeParsedSystem } from '../confirmSystem';

const GLUCOSE: AutomaticChoice = {
  role: 'substrate',
  chosen: 'D-glucose',
  why: 'most Km and kcat rows for EC 2.7.1.1 in Homo sapiens',
  alternatives: [
    { name: 'ATP', rows: { km: 106 } },
    { name: 'D-mannose', rows: { km: 9, kcat: 1 } },
  ],
  considered: 12,
};

const HUMAN: AutomaticChoice = {
  role: 'organism',
  chosen: 'Homo sapiens',
  why: 'most Km rows for EC 2.7.1.1',
  alternatives: [{ name: 'Rattus norvegicus', rows: { km: 40 } }],
  considered: 30,
};

/** A runner that answers each role from a table, and records each call. */
function stub(answers: Record<string, { status: number; choice?: AutomaticChoice | null; note?: string }>) {
  const calls: string[][] = [];
  const run: ChooserRunner = (args) => {
    calls.push(args);
    const role = args[args.indexOf('--role') + 1]!;
    const answer = answers[role] ?? { status: 1 };
    return {
      status: answer.status,
      stdout: JSON.stringify({ choice: answer.choice ?? null, note: answer.note ?? '' }),
      stderr: '',
    };
  };
  return { run, calls };
}

describe('askChooser reads the three answers the chooser can give', () => {
  it('exit 0 with a choice is a choice', () => {
    const { run, calls } = stub({ substrate: { status: 0, choice: GLUCOSE, note: 'chose' } });
    const answer = askChooser({ ec: '2.7.1.1', role: 'substrate', organism: 'Homo sapiens' }, run);
    expect(answer).toEqual({ kind: 'chosen', choice: GLUCOSE, note: 'chose' });
    expect(calls[0]).toEqual(['--ec', '2.7.1.1', '--role', 'substrate', '--json', '--organism', 'Homo sapiens']);
  });

  it('exit 3 is "BRENDA has nothing usable", with the note saying what is missing', () => {
    const { run } = stub({ substrate: { status: 3, note: 'BRENDA lists no Km row for EC 3.4.21.79 in Homo sapiens.' } });
    expect(askChooser({ ec: '3.4.21.79', role: 'substrate', organism: 'Homo sapiens' }, run)).toEqual({
      kind: 'nothing',
      note: 'BRENDA lists no Km row for EC 3.4.21.79 in Homo sapiens.',
    });
  });

  it('any other exit is "not asked", never "nothing exists"', () => {
    const run: ChooserRunner = () => ({ status: 1, stdout: '', stderr: "No module named caterva.compose.defaults" });
    const answer = askChooser({ ec: '2.7.1.1', role: 'substrate' }, run);
    expect(answer.kind).toBe('unavailable');
    expect(answer.kind === 'unavailable' && answer.reason).toContain('No module named');
  });

  it('exit 0 with no well-formed choice is not taken as one', () => {
    const run: ChooserRunner = () => ({ status: 0, stdout: '{"choice": {"chosen": ""}}', stderr: '' });
    expect(askChooser({ ec: '2.7.1.1', role: 'substrate' }, run).kind).toBe('unavailable');
  });
});

describe('completeByChoosing', () => {
  it('chooses the organism first, then the substrate in that organism', () => {
    const { run, calls } = stub({
      organism: { status: 0, choice: HUMAN },
      substrate: { status: 0, choice: GLUCOSE },
    });
    const done = completeByChoosing({ enzyme: 'hexokinase', ec: '2.7.1.1' }, run);
    expect(calls.map((a) => a[a.indexOf('--role') + 1])).toEqual(['organism', 'substrate']);
    expect(calls[1]).toContain('Homo sapiens');
    expect(done).toEqual({
      kind: 'complete',
      system: {
        enzyme: 'hexokinase',
        substrate: 'D-glucose',
        organism: 'Homo sapiens',
        ec: '2.7.1.1',
        choices: [HUMAN, GLUCOSE],
      },
    });
  });

  it('chooses nothing that was named', () => {
    const { run, calls } = stub({ substrate: { status: 0, choice: GLUCOSE } });
    const done = completeByChoosing({ enzyme: 'hexokinase', ec: '2.7.1.1', organism: 'Homo sapiens', organismTyped: 'humans' }, run);
    expect(calls).toHaveLength(1);
    expect(done.kind === 'complete' && done.system.organismTyped).toBe('humans');
  });

  it('passes the chooser\'s "nothing usable" on, naming the role', () => {
    const { run } = stub({ substrate: { status: 3, note: 'nothing measured' } });
    expect(completeByChoosing({ ec: '3.4.21.79', organism: 'Homo sapiens' }, run)).toEqual({
      kind: 'nothing',
      role: 'substrate',
      note: 'nothing measured',
    });
  });

  it('asks nothing without an EC number', () => {
    const { run, calls } = stub({});
    expect(completeByChoosing({ enzyme: 'lactate dehydrogenase' }, run).kind).toBe('not-chosen');
    expect(calls).toEqual([]);
  });
});

describe('the choice is said in words a person can act on', () => {
  it('names what was chosen, why, the others with their rows, and the flag', () => {
    expect(describeChoice(GLUCOSE)).toBe(
      'No substrate named; using D-glucose (most Km and kcat rows for EC 2.7.1.1 in Homo sapiens). ' +
        'Others: ATP (Km 106 rows), D-mannose (Km 9 rows, kcat 1 row). Pass --substrate to use another.',
    );
  });

  it('is on the confirmation screen, and the chosen parts are marked', () => {
    const screen = describeParsedSystem({
      enzyme: 'hexokinase',
      substrate: 'D-glucose',
      organism: 'Homo sapiens',
      ec: '2.7.1.1',
      ecName: 'hexokinase',
      choices: [GLUCOSE],
    });
    expect(screen).toMatch(/substrate\s+D-glucose\s+\(chosen: you named none\)/);
    expect(screen).not.toMatch(/organism.*chosen/);
    expect(screen).toContain('No substrate named; using D-glucose');
    expect(screen).toContain('ATP (Km 106 rows)');
  });
});
