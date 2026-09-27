import {
  confirmSystem,
  describeParsedSystem,
  type ConfirmIO,
} from '../confirmSystem';

/**
 * The human-in-the-loop that lets a sentence replace six flags.
 *
 * `simulate --resolve` refused without `--enzyme`, `--substrate` and
 * `--organism`, because "attaching a real citation to a system you did not
 * name is provenance for the wrong measurement." That constraint stands.
 * What changed is the recognition that it asks whether a PERSON named the
 * system — not whether a regex was involved.
 *
 * Every test below is about the moment a citation becomes attachable. If any
 * of them regress, Caterva is silently inferring a system and stamping real
 * BRENDA references onto it, which is the single worst thing this codebase
 * can do.
 */

function io(overrides: Partial<ConfirmIO> = {}): ConfirmIO & { output: () => string } {
  const chunks: string[] = [];
  return {
    isTTY: true,
    write: (text: string) => chunks.push(text),
    ask: async () => 'y',
    output: () => chunks.join(''),
    ...overrides,
  };
}

const SYSTEM = {
  enzyme: 'lactate dehydrogenase',
  substrate: 'pyruvate',
  organism: 'Homo sapiens',
};

describe('confirming a system read out of a question', () => {
  it('proceeds when the student says yes', async () => {
    const result = await confirmSystem(SYSTEM, io({ ask: async () => 'y' }));
    expect(result.confirmed).toBe(true);
  });

  it('accepts the spelled-out "yes" too', async () => {
    const result = await confirmSystem(SYSTEM, io({ ask: async () => 'Yes' }));
    expect(result.confirmed).toBe(true);
  });

  /**
   * THE DEFAULT IS NO, AND THAT IS THE POINT.
   *
   * An empty line is somebody pressing return to make a prompt go away.
   * Reading it as consent would make the confirmation decorative — the
   * prompt would be in the code, visible in review, and functionally a
   * silent inference.
   */
  it('does NOT proceed on a bare return', async () => {
    const result = await confirmSystem(SYSTEM, io({ ask: async () => '' }));
    expect(result.confirmed).toBe(false);
  });

  it.each([['n'], ['no'], ['q'], ['maybe'], ['   ']])(
    'does not proceed on %p',
    async (answer) => {
      const result = await confirmSystem(SYSTEM, io({ ask: async () => answer }));
      expect(result.confirmed).toBe(false);
    },
  );

  /**
   * With no terminal there is nobody to ask. A default-confirm here would be
   * exactly the silent inference the constraint forbids, with a prompt in
   * the code path that nobody ever sees — so a pipe, a CI job or a `| head`
   * gets a refusal, never a guess.
   */
  it('refuses rather than assuming, with no terminal attached', async () => {
    const result = await confirmSystem(SYSTEM, io({ isTTY: false }));
    expect(result).toEqual({ confirmed: false, reason: 'no-terminal' });
  });

  it('never asks a question it cannot receive an answer to', async () => {
    let asked = false;
    await confirmSystem(
      SYSTEM,
      io({
        isTTY: false,
        ask: async () => {
          asked = true;
          return 'y';
        },
      }),
    );
    expect(asked).toBe(false);
  });

  it('reports declined and no-terminal as different facts', async () => {
    const declined = await confirmSystem(SYSTEM, io({ ask: async () => 'n' }));
    const headless = await confirmSystem(SYSTEM, io({ isTTY: false }));
    // Only one of them means "try again, interactively".
    expect(declined).toEqual({ confirmed: false, reason: 'declined' });
    expect(headless).toEqual({ confirmed: false, reason: 'no-terminal' });
  });
});

describe('--yes', () => {
  it('proceeds without asking', async () => {
    let asked = false;
    const result = await confirmSystem(
      SYSTEM,
      io({
        isTTY: false,
        ask: async () => {
          asked = true;
          return 'n';
        },
      }),
      { assumeYes: true },
    );
    expect(result.confirmed).toBe(true);
    expect(asked).toBe(false);
  });

  /**
   * `--yes` skips the QUESTION, not the DISCLOSURE. A batch run whose
   * citations came from a parse has to say so in its own transcript, or
   * nobody can audit afterwards which system was actually cited.
   */
  it('still prints what it read, so the run can be audited later', async () => {
    const sink = io({ isTTY: false });
    await confirmSystem(SYSTEM, sink, { assumeYes: true });
    const out = sink.output();
    expect(out).toContain('lactate dehydrogenase');
    expect(out).toContain('pyruvate');
    expect(out).toContain('Homo sapiens');
    expect(out).toContain('--yes');
  });
});

describe('what the student is shown before deciding', () => {
  it('lists all three names on their own lines', () => {
    const text = describeParsedSystem(SYSTEM);
    expect(text).toMatch(/enzyme\s+lactate dehydrogenase/);
    expect(text).toMatch(/substrate\s+pyruvate/);
    expect(text).toMatch(/organism\s+Homo sapiens/);
  });

  /**
   * A student who does not know what a wrong organism costs cannot judge the
   * question being put to them. The consequence is named, not implied.
   */
  it('says what getting it wrong would cost', () => {
    expect(describeParsedSystem(SYSTEM)).toMatch(/worse than\s*\n?no citation at all/);
  });
});
