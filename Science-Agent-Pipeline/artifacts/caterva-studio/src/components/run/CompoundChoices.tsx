/**
 * The compounds a refusal says do have a measurement, as a short list of
 * buttons that fill the form's Inhibitor field, with a filter box. The
 * engine's sentence can name thirty IUPAC names; as a paragraph that is
 * 2,000 characters nobody reads, as a capped list it is a place to choose.
 * Choosing fills the field; it does not start a run.
 */
import { useId, useState } from "react";

import { plural } from "@/lib/copy";

export const COMPOUND_CAP = 12;

export function CompoundChoices({
  compounds,
  onChoose,
  cap = COMPOUND_CAP,
}: {
  compounds: readonly string[];
  /** Puts this name in the Inhibitor field. */
  onChoose?: (name: string) => void;
  cap?: number;
}) {
  const [query, setQuery] = useState("");
  const id = useId();
  const needle = query.trim().toLowerCase();
  const matches = needle ? compounds.filter((c) => c.toLowerCase().includes(needle)) : compounds;
  const shown = matches.slice(0, cap);
  return (
    <div className="compound-choices">
      {compounds.length > cap ? (
        <div className="field">
          <label className="field-label" htmlFor={`${id}-filter`}>
            Filter the {compounds.length} compounds
          </label>
          <input
            id={`${id}-filter`}
            type="search"
            className="input"
            autoComplete="off"
            spellCheck={false}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>
      ) : null}
      <ul className="compound-list" aria-label="Compounds with a measured Ki">
        {shown.map((name) => (
          <li key={name}>
            <button
              type="button"
              className="btn btn-sm compound-button"
              title={name}
              onClick={() => onChoose?.(name)}
              disabled={!onChoose}
            >
              {name}
            </button>
          </li>
        ))}
      </ul>
      <p className="field-hint" role="status">
        {matches.length === 0
          ? "No compound matches that."
          : matches.length > shown.length
            ? `Showing ${shown.length} of ${plural(matches.length, "compound")}; type to narrow the list.`
            : onChoose
              ? "Choose one to put it in Inhibitor."
              : ""}
      </p>
    </div>
  );
}
