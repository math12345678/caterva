/**
 * The run a kinetics screen was opened on, from `?run=<id>` (History opens
 * a past run this way). The id is only used in /api/runs/{id}, which the
 * server matches against its run-id pattern.
 */
import { useSearch } from "wouter";

export function useReopenedRun(): string | null {
  const search = useSearch();
  return new URLSearchParams(search).get("run");
}

/** The comma- or line-separated names in a text field, trimmed, empties dropped. */
export function names(text: string): string[] {
  return text
    .split(/[,\n]/)
    .map((s) => s.trim())
    .filter(Boolean);
}
