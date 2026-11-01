import * as readline from 'readline';

import type { ParsedSystem } from './suggestResolveCommand';

/**
 * Ask the student whether the system read out of their question is right.
 *
 * WHY A CONFIRMATION AND NOT A SILENT PARSE
 * -----------------------------------------
 * `simulate --resolve` refuses without `--enzyme`, `--substrate` and
 * `--organism`, and the refusal states why:
 *
 *   "The system is never inferred from the query text: attaching a real
 *    citation to a system you did not name is provenance for the wrong
 *    measurement."
 *
 * That is correct and is not being relaxed. The constraint is about
 * **provenance for a system nobody named** — so the question it really asks
 * is whether a person named it, not whether a regex was involved.
 *
 * A confirmation answers that. Caterva reads three names out of the
 * sentence, prints them, and does nothing until a human says yes. At the
 * moment the citation is attached, a person has read "lactate
 * dehydrogenase / pyruvate / Homo sapiens" and agreed to it — which is
 * strictly more explicit than typing three flags, because the flags are
 * typed once and never re-read.
 *
 * THE COST THIS REMOVES
 * ---------------------
 * Six flags to run one simulation. `--resolve --enzyme X --substrate Y
 * --organism Z --s0 10mM --enzyme-conc 0.001mM` is not "ask a question in
 * plain language", and a student who has already written the enzyme,
 * substrate and organism into their sentence is being asked to type them
 * again in a syntax nothing showed them.
 *
 * NON-INTERACTIVE MUST NOT AUTO-CONFIRM
 * -------------------------------------
 * With no terminal attached there is nobody to ask, and a script that
 * "confirms" by default is exactly the silent inference the constraint
 * forbids — it would just have a prompt in the code path that nobody ever
 * sees. So a pipe, a CI job or a `| head` gets a refusal and the explicit
 * command, never a guess.
 *
 * `--yes` is the deliberate override, and it is still a person naming the
 * system: they read the parse, then re-ran with the flag.
 */

export type ConfirmOutcome =
  | { confirmed: true }
  | { confirmed: false; reason: 'declined' | 'no-terminal' };

/** Written as an object so tests can drive it without a real terminal. */
export interface ConfirmIO {
  isTTY: boolean;
  write: (text: string) => void;
  ask: (question: string) => Promise<string>;
}

export function describeParsedSystem(system: ParsedSystem): string {
  return [
    '',
    'Your question names a system. Caterva read it as:',
    '',
    `    enzyme      ${system.enzyme}`,
    `    substrate   ${system.substrate}`,
    `    organism    ${system.organism}`,
    '',
    // Named consequences, not a generic "is this ok?". A student who does
    // not know what a wrong organism costs cannot judge the question.
    'These decide which measurement gets cited. A wrong organism here',
    'attaches a real reference to the wrong enzyme, which is worse than',
    'no citation at all.',
    '',
  ].join('\n');
}

export async function confirmSystem(
  system: ParsedSystem,
  io: ConfirmIO,
  options: { assumeYes?: boolean } = {},
): Promise<ConfirmOutcome> {
  if (options.assumeYes === true) {
    // Still printed. `--yes` skips the question, not the disclosure: a run
    // whose citations came from a parse should say so in its own transcript,
    // or the log of a batch job cannot be audited afterwards.
    io.write(describeParsedSystem(system));
    io.write('Confirmed by --yes.\n');
    return { confirmed: true };
  }

  if (!io.isTTY) {
    return { confirmed: false, reason: 'no-terminal' };
  }

  io.write(describeParsedSystem(system));
  const answer = (await io.ask('Resolve for this system? [y/N] ')).trim().toLowerCase();
  // Default is NO. An empty line is somebody pressing return to make a
  // prompt go away, and reading that as consent would make the confirmation
  // decorative.
  if (answer === 'y' || answer === 'yes') {
    return { confirmed: true };
  }
  return { confirmed: false, reason: 'declined' };
}

/** The real terminal, wired to stderr so `--json` on stdout stays one document. */
export function terminalIO(): ConfirmIO {
  return {
    isTTY: process.stdin.isTTY === true && process.stderr.isTTY === true,
    write: (text: string) => process.stderr.write(text),
    ask: (question: string) =>
      new Promise<string>((resolve) => {
        const rl = readline.createInterface({
          input: process.stdin,
          output: process.stderr,
        });
        rl.question(question, (answer) => {
          rl.close();
          resolve(answer);
        });
      }),
  };
}
