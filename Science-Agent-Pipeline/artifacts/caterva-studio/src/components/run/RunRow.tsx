/**
 * One run in a list (Home's recent runs, History): its state mark, title,
 * kind, when, and the line that says how it ended, in its own words.
 */
import { Link } from "wouter";

import type { RunSummary } from "@/api/types";
import { RunStatusMark, runStatusLabel } from "@/components/shell/RunStatusMark";

import { Identified } from "./Identified";
import { networkFailureOf, networkSentence, plain } from "@/lib/copy";
import { formatWhen } from "@/lib/format";
import { runHref } from "@/lib/jobs";

/**
 * A refusal's summary is often its reason's first line (bind, structure):
 * printed as "summary: reason" the same sentence appeared twice in a row,
 * so a summary the reason already contains, or the other way round, is
 * said once.
 */
export function outcomeLine(run: Pick<RunSummary, "status" | "outcome">): string {
  if (run.outcome) {
    const { summary, reason, meaning } = run.outcome;
    if (meaning === "network") return networkSentence(run.outcome.network ?? networkFailureOf(reason));
    // A run recorded before the server named an outage as one: its reason still carries the exception.
    const legacy = meaning === "refused" ? networkFailureOf(reason) : null;
    if (legacy) return networkSentence(legacy);
    if (meaning === "produced" || !reason) return plain(summary);
    const first = reason.split("\n")[0].trim();
    const said = summary.trim();
    if (!said || said.includes(first)) return plain(said || first);
    if (first.includes(said)) return plain(first);
    return plain(`${said}: ${first}`);
  }
  return runStatusLabel(run.status, null);
}

export function RunRow({
  run,
  href,
  selected = false,
  onSelect,
}: {
  run: RunSummary;
  href?: string;
  selected?: boolean;
  onSelect?: () => void;
}) {
  const body = (
    <>
      <span className="run-row-mark">
        <RunStatusMark status={run.status} meaning={run.outcome?.meaning ?? null} />
      </span>
      <span className="run-row-title">
        <Identified text={run.title} />
      </span>
      <span className="run-row-time">{formatWhen(run.created_at)}</span>
      <span className="run-row-sub">
        <span className="font-mono">{run.kind}</span> · {outcomeLine(run)}
      </span>
    </>
  );
  if (onSelect) {
    return (
      <button type="button" className="run-row" data-selected={selected ? "true" : undefined} aria-pressed={selected} onClick={onSelect}>
        {body}
      </button>
    );
  }
  return (
    <Link href={href ?? runHref(run)} className="run-row">
      {body}
    </Link>
  );
}
