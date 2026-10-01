/**
 * While a compose run searches the literature, the constants it is looking
 * up, one line each as the adapter reports them ("Looking up reaction_Km
 * in BRENDA's km table for EC 1.1.1.27"), so the wait has a shape: which
 * constants, from which table, for which enzyme.
 *
 * The lines are the server's stage labels, verbatim. Once a later stage
 * arrives the lookups are over, and the line says only that: whether each
 * one found a measurement is the result's to say, in the table of where
 * the numbers came from, not this list's to guess.
 */
import type { StageEvent } from "@/api/types";

type Stage = Pick<StageEvent, "stage" | "label" | "fraction" | "at">;

export function lookups(stages: readonly Stage[]): string[] {
  return stages.filter((s) => s.stage === "search" && /^Looking up /.test(s.label)).map((s) => s.label);
}

export function ComposeProgress({ stages }: { stages: readonly Stage[] }) {
  const asked = lookups(stages);
  if (asked.length === 0) return null;
  const last = stages[stages.length - 1];
  const over = last ? last.stage !== "search" : false;
  return (
    <section className="k-lookups" aria-label="Constants being looked up" aria-live="polite">
      <h3 className="k-eyebrow">{over ? "Looked up. What each one found goes in the table of where the numbers come from" : "Looking up"}</h3>
      <ol>
        {asked.map((label, i) => (
          <li key={`${label}-${i}`} data-state={over ? "asked" : i === asked.length - 1 ? "current" : "asked"}>
            <span className="k-lookup-dot" aria-hidden="true" />
            <span className="font-mono">{label}</span>
          </li>
        ))}
      </ol>
    </section>
  );
}
