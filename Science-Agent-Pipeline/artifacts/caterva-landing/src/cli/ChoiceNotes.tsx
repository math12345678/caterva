/**
 * The names Caterva chose because the question did not give them (ADR 0182).
 *
 * The API states every automatic choice as a flag beginning "substrate
 * chosen:", "inhibitor chosen:" or "organism chosen:" -- what was chosen,
 * why, and the alternatives with their BRENDA row counts. Those flags used
 * to sit among the small yellow chips with every other caveat, and on the
 * refusal path the page dropped flags altogether, so a Km looked up for a
 * substrate the student never typed could arrive with nothing on screen
 * naming it. A cited number is the constant of ONE substrate; the reader
 * has to see which before they read the number. So these get their own
 * block, above the other flags, in full sentences.
 *
 * Nothing is decided here: the sentences are the server's, shown as sent.
 */

const CHOICE_FLAG = /^(substrate|inhibitor|organism|enzyme) chosen: /;

/** The flags that state an automatic choice, and the rest, in order. */
export function splitChoiceFlags(flags: readonly string[]): {
  choices: string[];
  others: string[];
} {
  const choices: string[] = [];
  const others: string[] = [];
  for (const flag of flags) (CHOICE_FLAG.test(flag) ? choices : others).push(flag);
  return { choices, others };
}

export default function ChoiceNotes({ flags }: { flags: readonly string[] }) {
  const { choices } = splitChoiceFlags(flags);
  if (choices.length === 0) return null;
  return (
    <div
      data-testid="choice-notes"
      className="mb-2 rounded border border-sky-500/20 bg-sky-500/[0.05] px-2 py-1.5"
    >
      <div className="text-[9px] uppercase tracking-wide text-sky-400/80 mb-1">
        chosen for you -- your question did not name these
      </div>
      <ul className="space-y-1">
        {choices.map((choice, i) => (
          <li key={i} className="text-[10px] leading-relaxed text-fg/80">
            {choice}
          </li>
        ))}
      </ul>
    </div>
  );
}
