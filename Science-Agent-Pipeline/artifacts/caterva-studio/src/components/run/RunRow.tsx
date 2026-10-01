/**
 * One run in a list (Home's recent runs, History): its state mark, title,
 * kind, when, and the line that says how it ended, in its own words.
 */
import { Link } from "wouter";

import type { RunSummary } from "@/api/types";
import { RunStatusMark, runStatusLabel } from "@/components/shell/RunStatusMark";
import { formatWhen } from "@/lib/format";
import { runHref } from "@/lib/jobs";

export function outcomeLine(run: Pick<RunSummary, "status" | "outcome">): string {
  if (run.outcome) {
    if (run.outcome.meaning === "produced") return run.outcome.summary;
    return run.outcome.reason ? `${run.outcome.summary ? `${run.outcome.summary}: ` : ""}${run.outcome.reason.split("\n")[0]}` : run.outcome.summary;
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
      <span className="run-row-title">{run.title}</span>
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
