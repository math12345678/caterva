/**
 * Turn the sentence a student typed into the command that would work.
 *
 * THE PROBLEM
 * -----------
 * A student follows the pitch — "ask a question in plain language" — and
 * types:
 *
 *     simulate "michaelis menten of lactate dehydrogenase on pyruvate in Homo sapiens"
 *
 * Caterva reports that km, vmax and s0 have "no literature match", and then
 * advises: *"name a system to resolve them from literature with --resolve."*
 *
 * They did name the system. It is in the sentence. The enzyme, the substrate
 * and the organism are all there, and the tool asked them to say it again in
 * a syntax it did not show.
 *
 * WHY NOT JUST RESOLVE IT
 * -----------------------
 * Because `ScientificPipelineRequest.system` is deliberately NOT inferred
 * from the query, and the reason is good:
 *
 *   "Guessing an enzyme, substrate or organism out of free text would attach
 *    a real citation to a system the user never named — provenance for the
 *    wrong measurement, which is worse than no provenance."
 *
 * That holds. A regex that reads "lactate dehydrogenase" out of a sentence
 * is not evidence about what the student meant, and BRENDA ref 740253
 * stamped onto the wrong system is a worse failure than refusing.
 *
 * THE DISTINCTION THIS MODULE RESTS ON
 * ------------------------------------
 * Inferring silently and **offering** are not the same act. Nothing here
 * resolves anything, attaches a citation, or runs. It prints a command. The
 * student reads it, sees the three names written out, and runs it or fixes
 * it — and by running it they have named the system explicitly, which is
 * exactly what the constraint requires.
 *
 * So the guess never becomes provenance without a human in between. That is
 * the whole design, and it is why this is a suggestion printer and not a
 * parser wired into the pipeline.
 *
 * CONSERVATIVE ON PURPOSE
 * -----------------------
 * It fires only on a clear pattern and returns `null` otherwise. A wrong
 * suggestion costs a student a confusing command and teaches them the tool
 * guesses badly; no suggestion costs them the generic message they were
 * already getting. The bias is toward silence.
 */

export interface ParsedSystem {
  enzyme: string;
  substrate: string;
  organism: string;
}

/** Words that are never an enzyme, substrate or organism. */
const NOISE = new Set([
  'simulate',
  'simulation',
  'run',
  'the',
  'a',
  'an',
  'model',
  'kinetics',
  'michaelis',
  'menten',
  'mm',
  'please',
]);

function clean(fragment: string): string {
  return fragment
    .trim()
    .replace(/^(the|a|an)\s+/i, '')
    .replace(/[.,;:!?]+$/, '')
    .trim();
}

function plausible(fragment: string): boolean {
  const value = clean(fragment);
  if (value.length < 2 || value.length > 60) return false;
  // A fragment made only of noise words names nothing. Checked on the whole
  // fragment rather than word by word: "lactate dehydrogenase" contains no
  // noise, and "the model" is noise entire.
  const words = value.toLowerCase().split(/\s+/);
  return !words.every((w) => NOISE.has(w));
}

/**
 * `<enzyme> on <substrate> in <organism>`, the phrasing the help text's own
 * examples use, plus the two nearest variants.
 *
 * Anchored on the prepositions rather than on position, because "simulate
 * michaelis menten of X on Y in Z" and "X on Y in Z" must parse the same —
 * a student who drops the preamble has not asked a different question.
 */
const PATTERNS: RegExp[] = [
  /\bof\s+(.+?)\s+on\s+(.+?)\s+in\s+(.+)$/i,
  /\bfor\s+(.+?)\s+on\s+(.+?)\s+in\s+(.+)$/i,
  /^(.+?)\s+on\s+(.+?)\s+in\s+(.+)$/i,
  /\bof\s+(.+?)\s+with\s+(.+?)\s+in\s+(.+)$/i,
];

export function parseSystemFromQuery(query: string): ParsedSystem | null {
  const text = query.trim();
  if (text.length === 0) return null;

  for (const pattern of PATTERNS) {
    const match = text.match(pattern);
    if (!match) continue;
    const [, enzyme, substrate, organism] = match;
    if (enzyme === undefined || substrate === undefined || organism === undefined) {
      continue;
    }
    if (!plausible(enzyme) || !plausible(substrate) || !plausible(organism)) {
      continue;
    }
    return {
      enzyme: clean(enzyme),
      substrate: clean(substrate),
      organism: clean(organism),
    };
  }
  return null;
}

/**
 * The command, quoted so it survives a copy-paste into a shell.
 *
 * `--s0` is included with a placeholder rather than omitted. It is an
 * experimental condition the student chooses, no database reports it, and a
 * suggested command that still fails on the next run is worse than no
 * suggestion — they would reasonably conclude the tool is broken rather than
 * that they owe it one more number.
 */
export function formatResolveCommand(
  system: ParsedSystem,
  /**
   * Values the user ALREADY typed, as `{ s0: '10mM', vmax: '1.2mM/s' }`.
   *
   * WHY THIS PARAMETER EXISTS
   * -------------------------
   * The tail was a fixed `--s0 10mM --enzyme-conc 0.001mM`, appended
   * regardless of the command line it was suggesting a replacement for.
   * Measured:
   *
   *   $ simulate "michaelis menten of lactate dehydrogenase on pyruvate
   *               in Homo sapiens" --s0 10mM --vmax 1.2mM/s
   *   -> suggests: ... --s0 10mM --enzyme-conc 0.001mM
   *
   * **The user's `--vmax 1.2mM/s` is gone.** It was replaced by an
   * `--enzyme-conc` intended to DERIVE Vmax from kcat x [E]0 — and running
   * the suggested command verbatim exits 2, "Cannot run", because the kcat
   * it now depends on is not there.
   *
   * So the guidance took a user whose own flags were nearly sufficient and
   * handed them a command that fails, having discarded the value that would
   * have worked. Not merely unhelpful: a regression on their own input.
   *
   * `--vmax` and `--enzyme-conc` are ALTERNATIVES — supply Vmax directly, or
   * supply [E]0 so it can be bridged from kcat. Offering both at once is
   * what makes the command wrong.
   */
  supplied: Readonly<Record<string, string>> = {},
): string {
  const q = (value: string): string => `"${value.replace(/"/g, '\\"')}"`;

  const lines = [
    'scientific simulate "michaelis menten" --resolve \\',
    `  --enzyme ${q(system.enzyme)} \\`,
    `  --substrate ${q(system.substrate)} \\`,
    `  --organism ${q(system.organism)} \\`,
  ];

  // Carried through, not replaced. A flag the user typed is a decision they
  // made; a suggestion that silently drops it is overruling them.
  const tail: string[] = [];
  tail.push(`--s0 ${supplied['s0'] ?? '10mM'}`);

  if (supplied['vmax']) {
    // They gave Vmax outright, so there is nothing to bridge and
    // `--enzyme-conc` would be noise at best and misdirection at worst.
    tail.push(`--vmax ${supplied['vmax']}`);
  } else {
    tail.push(`--enzyme-conc ${supplied['enzyme-conc'] ?? '0.001mM'}`);
  }

  // Anything else they typed survives too — km, ki, i0. Sorted so the
  // suggestion is stable across runs rather than dependent on key order.
  for (const name of Object.keys(supplied).sort()) {
    if (name === 's0' || name === 'vmax' || name === 'enzyme-conc') continue;
    tail.push(`--${name} ${supplied[name]}`);
  }

  lines.push(`  ${tail.join(' ')}`);
  return lines.join('\n');
}
