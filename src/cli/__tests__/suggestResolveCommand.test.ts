import {
  parseSystemFromQuery,
  formatResolveCommand,
} from '../suggestResolveCommand';

/**
 * The bridge between "refuses to invent" and "usable".
 *
 * A student following the pitch types a plain-language question, and every
 * parameter comes back "no literature match" — because the pipeline
 * deliberately does NOT infer the system from free text:
 *
 *   "Guessing an enzyme, substrate or organism out of free text would attach
 *    a real citation to a system the user never named."
 *
 * That constraint is right and is not being relaxed. What was wrong was the
 * advice printed next to it — *"name a system to resolve them from
 * literature with --resolve"* — to a reader who had just named all three in
 * the sentence.
 *
 * Offering the command is not inferring. Nothing here resolves, cites, or
 * runs; the student names the system by choosing to run what is printed.
 *
 * The cases below are mostly about SILENCE. A wrong suggestion teaches a
 * student the tool guesses badly, which is worse than the generic message
 * they were already getting, so the bias is toward returning null.
 */

describe('reading the system out of a plain-language question', () => {
  it('parses the phrasing the help text itself uses', () => {
    expect(
      parseSystemFromQuery(
        'simulate michaelis menten of lactate dehydrogenase on pyruvate in Homo sapiens',
      ),
    ).toEqual({
      enzyme: 'lactate dehydrogenase',
      substrate: 'pyruvate',
      organism: 'Homo sapiens',
    });
  });

  /**
   * A student who drops the preamble has not asked a different question, so
   * the patterns anchor on the prepositions rather than on position.
   */
  it('parses the same question without the preamble', () => {
    expect(
      parseSystemFromQuery('hexokinase on glucose in Saccharomyces cerevisiae'),
    ).toEqual({
      enzyme: 'hexokinase',
      substrate: 'glucose',
      organism: 'Saccharomyces cerevisiae',
    });
  });

  it('accepts "for X on Y in Z" and "of X with Y in Z"', () => {
    expect(parseSystemFromQuery('run a model for catalase on hydrogen peroxide in Bos taurus'))
      .toEqual({
        enzyme: 'catalase',
        substrate: 'hydrogen peroxide',
        organism: 'Bos taurus',
      });
    expect(parseSystemFromQuery('kinetics of pepsin with albumin in Sus scrofa')).toEqual({
      enzyme: 'pepsin',
      substrate: 'albumin',
      organism: 'Sus scrofa',
    });
  });

  it('strips articles and trailing punctuation rather than passing them on', () => {
    const parsed = parseSystemFromQuery(
      'simulate of the hexokinase on the glucose in the Homo sapiens.',
    );
    expect(parsed).toEqual({
      enzyme: 'hexokinase',
      substrate: 'glucose',
      organism: 'Homo sapiens',
    });
  });

  describe('stays silent rather than guessing', () => {
    it.each([
      ['no system at all', 'simulate michaelis menten'],
      ['two of the three parts', 'simulate lactate dehydrogenase on pyruvate'],
      ['an empty query', '   '],
      ['numbers, not a system', 'simulate mm --km 5.2 --vmax 12.8 --s0 10'],
      // Every captured fragment is a noise word, so the sentence names
      // nothing even though it matches the shape.
      ['a shape match that names nothing', 'simulate of the model on the model in the model'],
    ])('%s', (_label, query) => {
      expect(parseSystemFromQuery(query)).toBeNull();
    });
  });

  /**
   * A fragment long enough to be a paragraph is a sentence that happened to
   * contain "on" and "in", not a system name. Suggesting a command built
   * from it would be obviously wrong in a way that discredits the tool.
   */
  it('refuses a fragment too long to be a name', () => {
    const rambling =
      'of ' + 'x'.repeat(80) + ' on pyruvate in Homo sapiens';
    expect(parseSystemFromQuery(rambling)).toBeNull();
  });
});

describe('the command it prints', () => {
  const SYSTEM = {
    enzyme: 'lactate dehydrogenase',
    substrate: 'pyruvate',
    organism: 'Homo sapiens',
  };

  it('names all three, quoted so a shell keeps them together', () => {
    const command = formatResolveCommand(SYSTEM);
    expect(command).toContain('--enzyme "lactate dehydrogenase"');
    expect(command).toContain('--substrate "pyruvate"');
    expect(command).toContain('--organism "Homo sapiens"');
  });

  it('carries --resolve, without which it would not look anything up', () => {
    expect(formatResolveCommand(SYSTEM)).toContain('--resolve');
  });

  /**
   * THE LOAD-BEARING ONE. `s0` and `[E]0` are experimental conditions the
   * student chooses — no database reports them — so a suggested command
   * omitting them would fail on the very next run, and a reader would
   * reasonably conclude the tool is broken rather than that they owe it one
   * more number.
   */
  it('includes the conditions no database can supply, so it actually runs', () => {
    const command = formatResolveCommand(SYSTEM);
    expect(command).toContain('--s0');
    expect(command).toContain('--enzyme-conc');
  });

  it('escapes a quote rather than emitting a broken command', () => {
    const command = formatResolveCommand({
      ...SYSTEM,
      enzyme: 'some "odd" name',
    });
    expect(command).toContain('\\"odd\\"');
  });
});
