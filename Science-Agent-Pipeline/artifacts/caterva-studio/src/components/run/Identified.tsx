/**
 * Text with its identifiers set in DM Mono: an EC number ("EC 1.1.1.27"), a
 * PDB entry ("PDB 1AKI"), a seed ("seed 988813188"). They are the part of a
 * run's title a person scans for and compares digit by digit, so they take
 * the tabular figures the numbers elsewhere do. Everything else is left as
 * written.
 */
import { Fragment, type ReactNode } from "react";

const IDENTIFIER = /(\bEC \d+(?:\.(?:\d+|-))+|\bPDB [0-9][A-Za-z0-9]{3}\b|\bseed \d+\b)/g;

export function Identified({ text }: { text: string }): ReactNode {
  const parts = text.split(IDENTIFIER);
  return (
    <>
      {parts.map((part, i) =>
        i % 2 === 1 ? (
          <span key={i} className="font-mono ident">
            {part}
          </span>
        ) : (
          <Fragment key={i}>{part}</Fragment>
        ),
      )}
    </>
  );
}
